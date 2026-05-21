from __future__ import annotations

import asyncio
import contextlib
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from backend.common.exception.errors import RequestError
from backend.core.conf import settings
from backend.plugin.stream_hub.log_stream import stream_hub_log_stream
from backend.plugin.stream_hub.schema.log_file import LogFileFollowResponse
from backend.plugin.stream_hub.service.log_file_service import (
    LogFileService,
    log_file_service,
)
from backend.plugin.stream_hub.spec import StreamHubLogStreamSpec


STREAM_HUB_FILE_LOG_STREAM = StreamHubLogStreamSpec(
    domain="stream_hub",
    stream="file_log",
    resource="file",
    features=frozenset({"append"}),
)


@dataclass
class LeaseState:
    lease_id: str
    expires_at: float


@dataclass
class WatcherState:
    file_id: str
    path: Path
    offset: int
    inode: int | None
    leases: dict[str, LeaseState]
    last_active_at: float
    task: asyncio.Task | None = None
    poll_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    partial_buffer: bytes = b""
    partial_buffer_truncated: bool = False
    deleted_at: float | None = None
    delete_event_sent: bool = False


class FileLogTailManager:
    def __init__(
        self,
        *,
        log_file_service: LogFileService = log_file_service,
        log_stream: Any = stream_hub_log_stream,
        lease_ttl_seconds: int | None = None,
        idle_ttl_seconds: int | None = None,
        poll_interval_seconds: float = 1.0,
        max_watchers: int | None = None,
        read_chunk_bytes: int | None = None,
        max_line_buffer_bytes: int | None = None,
        deletion_idle_ttl_seconds: int | None = None,
    ) -> None:
        self.log_file_service = log_file_service
        self.log_stream = log_stream
        self.lease_ttl_seconds = (
            settings.STREAM_HUB_FILE_LOG_LEASE_TTL_SECONDS
            if lease_ttl_seconds is None
            else lease_ttl_seconds
        )
        self.idle_ttl_seconds = (
            settings.STREAM_HUB_FILE_LOG_IDLE_TTL_SECONDS
            if idle_ttl_seconds is None
            else idle_ttl_seconds
        )
        self.poll_interval_seconds = poll_interval_seconds
        self.max_watchers = (
            settings.STREAM_HUB_FILE_LOG_MAX_WATCHERS
            if max_watchers is None
            else max_watchers
        )
        self.read_chunk_bytes = (
            settings.STREAM_HUB_FILE_LOG_READ_CHUNK_BYTES
            if read_chunk_bytes is None
            else read_chunk_bytes
        )
        self.max_line_buffer_bytes = (
            max(1, self.read_chunk_bytes * 4)
            if max_line_buffer_bytes is None
            else max(1, max_line_buffer_bytes)
        )
        self.deletion_idle_ttl_seconds = (
            self.idle_ttl_seconds
            if deletion_idle_ttl_seconds is None
            else deletion_idle_ttl_seconds
        )
        self._watchers: dict[str, WatcherState] = {}
        self._lock = asyncio.Lock()

    @property
    def active_watcher_count(self) -> int:
        return len(self._watchers)

    async def follow(self, file_id: str) -> LogFileFollowResponse:
        path = self._resolve_file(file_id)
        now = self._now()
        async with self._lock:
            watcher = self._watchers.get(file_id)
            if watcher is None:
                if len(self._watchers) >= self.max_watchers:
                    raise RequestError(msg="File log watcher limit reached")
                stat = path.stat()
                watcher = WatcherState(
                    file_id=file_id,
                    path=path,
                    offset=stat.st_size,
                    inode=self._inode(stat),
                    leases={},
                    last_active_at=now,
                )
                self._watchers[file_id] = watcher
                watcher.task = asyncio.create_task(self._watch_loop(file_id))
            else:
                watcher.path = path
                watcher.last_active_at = now

            lease_id = uuid.uuid4().hex
            watcher.leases[lease_id] = LeaseState(
                lease_id=lease_id, expires_at=now + self.lease_ttl_seconds
            )
            return self._follow_response(file_id=file_id, lease_id=lease_id)

    async def heartbeat(self, *, file_id: str, lease_id: str) -> LogFileFollowResponse:
        now = self._now()
        async with self._lock:
            watcher = self._watchers.get(file_id)
            if watcher is None:
                raise RequestError(msg="File log watcher does not exist")
            lease = watcher.leases.get(lease_id)
            if lease is None:
                raise RequestError(msg="File log lease does not exist")
            lease.expires_at = now + self.lease_ttl_seconds
            watcher.last_active_at = now
            return self._follow_response(file_id=file_id, lease_id=lease_id)

    async def unfollow(self, *, file_id: str, lease_id: str) -> None:
        task: asyncio.Task | None = None
        async with self._lock:
            watcher = self._watchers.get(file_id)
            if watcher is None:
                raise RequestError(msg="File log watcher does not exist")
            if lease_id not in watcher.leases:
                raise RequestError(msg="File log lease does not exist")
            watcher.leases.pop(lease_id, None)
            watcher.last_active_at = self._now()
            if not watcher.leases:
                task = self._pop_watcher_locked(file_id)
        await self._cancel_watcher_task(task)

    async def cleanup_expired(self) -> None:
        now = self._now()
        tasks: list[asyncio.Task] = []
        async with self._lock:
            for file_id, watcher in list(self._watchers.items()):
                expired = [
                    lease_id
                    for lease_id, lease in watcher.leases.items()
                    if lease.expires_at <= now
                ]
                for lease_id in expired:
                    watcher.leases.pop(lease_id, None)
                if not watcher.leases:
                    task = self._pop_watcher_locked(file_id)
                    if task is not None:
                        tasks.append(task)
        for task in tasks:
            await self._cancel_watcher_task(task)

    async def close(self) -> None:
        tasks: list[asyncio.Task] = []
        async with self._lock:
            for file_id in list(self._watchers):
                task = self._pop_watcher_locked(file_id)
                if task is not None:
                    tasks.append(task)
        for task in tasks:
            await self._cancel_watcher_task(task)

    async def poll_once_for_tests(self, file_id: str) -> None:
        async with self._lock:
            watcher = self._watchers.get(file_id)
            if watcher is None:
                raise RequestError(msg="File log watcher does not exist")
        await self._poll_watcher(watcher)

    async def _watch_loop(self, file_id: str) -> None:
        try:
            while True:
                await asyncio.sleep(self.poll_interval_seconds)
                task: asyncio.Task | None = None
                async with self._lock:
                    watcher = self._watchers.get(file_id)
                    if watcher is None:
                        return
                    task = self._cleanup_watcher_expired_leases_locked(file_id, watcher)
                    if task is not None:
                        watcher = None
                if task is not None:
                    await self._cancel_watcher_task(task)
                    return
                if watcher is not None:
                    await self._poll_watcher(watcher)
        except asyncio.CancelledError:
            raise
        except Exception:
            await self._release_watcher(file_id)

    def _cleanup_watcher_expired_leases_locked(
        self, file_id: str, watcher: WatcherState
    ) -> asyncio.Task | None:
        now = self._now()
        expired = [
            lease_id
            for lease_id, lease in watcher.leases.items()
            if lease.expires_at <= now
        ]
        for lease_id in expired:
            watcher.leases.pop(lease_id, None)
        if not watcher.leases:
            return self._pop_watcher_locked(file_id)
        return None

    async def _poll_watcher(self, watcher: WatcherState) -> None:
        async with watcher.poll_lock:
            try:
                await self._poll_watcher_unlocked(watcher)
            except Exception:
                await self._release_watcher(watcher.file_id)
                raise

    async def _poll_watcher_unlocked(self, watcher: WatcherState) -> None:
        now = self._now()
        if not watcher.path.exists():
            if watcher.delete_event_sent:
                deleted_at = (
                    watcher.deleted_at if watcher.deleted_at is not None else now
                )
                if now - deleted_at >= self.deletion_idle_ttl_seconds:
                    await self._append_system(watcher.file_id, "WATCHER_STOPPED")
                    await self._release_watcher(watcher.file_id)
                return

            watcher.delete_event_sent = True
            watcher.deleted_at = now
            watcher.partial_buffer = b""
            watcher.partial_buffer_truncated = False
            await self._append_system(watcher.file_id, "FILE_DELETED")
            return

        try:
            path = self._resolve_file(watcher.file_id)
        except RequestError:
            await self._append_system(watcher.file_id, "WATCHER_STOPPED")
            await self._release_watcher(watcher.file_id)
            return

        watcher.path = path
        stat = watcher.path.stat()
        inode = self._inode(stat)
        size = stat.st_size
        if watcher.inode is not None and inode != watcher.inode:
            watcher.inode = inode
            watcher.offset = size
            watcher.partial_buffer = b""
            watcher.partial_buffer_truncated = False
            watcher.deleted_at = None
            watcher.delete_event_sent = False
            await self._append_system(watcher.file_id, "FILE_ROTATED")
            return

        if size < watcher.offset:
            watcher.offset = 0
            watcher.partial_buffer = b""
            watcher.partial_buffer_truncated = False
            await self._append_system(watcher.file_id, "FILE_TRUNCATED")

        watcher.inode = inode
        watcher.deleted_at = None
        watcher.delete_event_sent = False
        await self._read_new_lines(watcher)

    async def _read_new_lines(self, watcher: WatcherState) -> None:
        read_size = max(1, self.read_chunk_bytes)
        with watcher.path.open("rb") as file:
            file.seek(watcher.offset)
            data = file.read(read_size)
        if not data:
            return

        watcher.offset += len(data)
        buffer = watcher.partial_buffer + data
        if b"\n" not in buffer:
            watcher.partial_buffer = buffer
            await self._trim_partial_buffer(watcher)
            return

        parts = buffer.split(b"\n")
        complete_parts = parts[:-1]
        watcher.partial_buffer = parts[-1]
        watcher.partial_buffer_truncated = False
        await self._trim_partial_buffer(watcher)
        for line in complete_parts:
            if line.endswith(b"\r"):
                line = line[:-1]
            await self.log_stream.append(
                STREAM_HUB_FILE_LOG_STREAM,
                resource_id=watcher.file_id,
                message=line.decode("utf-8", errors="replace"),
                level="INFO",
                channel="file",
                extra={"fileId": watcher.file_id},
            )

    async def _trim_partial_buffer(self, watcher: WatcherState) -> None:
        if len(watcher.partial_buffer) <= self.max_line_buffer_bytes:
            return
        watcher.partial_buffer = watcher.partial_buffer[-self.max_line_buffer_bytes :]
        if watcher.partial_buffer_truncated:
            return
        watcher.partial_buffer_truncated = True
        await self._append_system(watcher.file_id, "LINE_TOO_LONG_TRUNCATED")

    async def _append_system(self, file_id: str, code: str) -> None:
        payload = {"code": code, "fileId": file_id}
        await self.log_stream.append(
            STREAM_HUB_FILE_LOG_STREAM,
            resource_id=file_id,
            message=code,
            level="SYSTEM",
            channel="file",
            payload=payload,
            extra=payload,
        )

    async def _release_watcher(self, file_id: str) -> None:
        async with self._lock:
            task = self._pop_watcher_locked(file_id)
        await self._cancel_watcher_task(task)

    def _pop_watcher_locked(self, file_id: str) -> asyncio.Task | None:
        watcher = self._watchers.pop(file_id, None)
        if watcher is None:
            return None
        return watcher.task

    async def _cancel_watcher_task(self, task: asyncio.Task | None) -> None:
        if task is None:
            return
        current_task = asyncio.current_task()
        if task is current_task:
            return
        if not task.done():
            task.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await task

    def _resolve_file(self, file_id: str) -> Path:
        try:
            return self.log_file_service.resolve_file(file_id)
        except ValueError as exc:
            raise RequestError(msg=str(exc)) from exc

    def _follow_response(self, *, file_id: str, lease_id: str) -> LogFileFollowResponse:
        return LogFileFollowResponse(
            file_id=file_id,
            following=True,
            lease_id=lease_id,
            lease_expires_in=max(0, int(self.lease_ttl_seconds)),
            watcher_count=self.active_watcher_count,
        )

    @staticmethod
    def _inode(stat_result: Any) -> int | None:
        return getattr(stat_result, "st_ino", None)

    @staticmethod
    def _now() -> float:
        return time.monotonic()


file_log_tail_manager = FileLogTailManager()
