from __future__ import annotations

from typing import Any

from backend.common.socketio.server import sio
from backend.plugin.stream_hub.service.file_log_tail_service import (
    STREAM_HUB_FILE_LOG_STREAM,
)
from backend.plugin.stream_hub.service.log_file_service import (
    LogFileService,
    log_file_service,
)


def bind_file_log_stream(
    *,
    sio: Any,
    log_file_service: LogFileService = log_file_service,
) -> None:
    @sio.on(STREAM_HUB_FILE_LOG_STREAM.subscribe_event)
    async def file_log_subscribe(sid: str, data: dict[str, Any] | None = None) -> None:
        file_id = _resolve_file_id(data, log_file_service)
        if file_id is None:
            return

        await sio.enter_room(sid, STREAM_HUB_FILE_LOG_STREAM.room(file_id))

    @sio.on(STREAM_HUB_FILE_LOG_STREAM.unsubscribe_event)
    async def file_log_unsubscribe(sid: str, data: dict[str, Any] | None = None) -> None:
        file_id = _resolve_file_id(data, log_file_service)
        if file_id is None:
            return

        await sio.leave_room(sid, STREAM_HUB_FILE_LOG_STREAM.room(file_id))


def _resolve_file_id(
    data: dict[str, Any] | None,
    log_file_service: LogFileService,
) -> str | None:
    if not isinstance(data, dict):
        return None

    raw_file_id = data.get("fileId") or data.get("file_id")
    if not isinstance(raw_file_id, str):
        return None

    file_id = raw_file_id.strip()
    if not file_id:
        return None

    try:
        log_file_service.resolve_file(file_id)
    except ValueError:
        return None

    return file_id


bind_file_log_stream(sio=sio)
