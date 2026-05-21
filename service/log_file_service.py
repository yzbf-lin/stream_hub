from __future__ import annotations

from datetime import datetime
from pathlib import Path

from backend.core.conf import settings
from backend.core.path_conf import LOG_DIR
from backend.plugin.stream_hub.schema.log_file import (
    LogFileItem,
    LogFileLine,
    LogFileTailResponse,
)
from backend.plugin.stream_hub.utils.log_file_path import (
    encode_log_file_id,
    resolve_log_file_path,
)
from backend.utils.timezone import timezone


class LogFileService:
    allowed_dirs = {'celery_tasks', 'env_task_runs'}
    allowed_suffixes = {'.log', '.jsonl', '.txt'}

    def __init__(self, root: Path | str | None = None) -> None:
        self.root = Path(root) if root is not None else LOG_DIR

    def encode_file_id(self, relative_path: str) -> str:
        return encode_log_file_id(relative_path)

    def list_files(self) -> list[LogFileItem]:
        root = self.root
        if not root.exists():
            return []

        items: list[LogFileItem] = []
        for path in self._iter_allowed_files(root):
            relative_path = path.relative_to(root).as_posix()
            items.append(self._build_item(path, relative_path))

        return sorted(items, key=lambda item: (item.group, item.relative_path))

    def resolve_file(self, file_id: str) -> Path:
        return resolve_log_file_path(
            root=self.root,
            file_id=file_id,
            allowed_dirs=self.allowed_dirs,
            allowed_suffixes=self.allowed_suffixes,
        )

    def tail(self, *, file_id: str, limit: int | None = None) -> LogFileTailResponse:
        effective_limit = self._clamp_limit(limit)
        path = self.resolve_file(file_id)
        text_lines, truncated = _tail_text_lines(
            path,
            limit=effective_limit,
            chunk_size=settings.STREAM_HUB_FILE_LOG_READ_CHUNK_BYTES,
        )
        line_count = len(text_lines)
        lines = [
            LogFileLine(
                line=line,
                message=line,
                stream_seq=index - line_count,
                file_id=file_id,
            )
            for index, line in enumerate(text_lines)
        ]
        return LogFileTailResponse(
            file_id=file_id,
            exists=True,
            lines=lines,
            limit=effective_limit,
            truncated=truncated,
        )

    def download_path(self, file_id: str) -> Path:
        return self.resolve_file(file_id)

    def safe_download_name(self, file_id_or_path: str | Path) -> str:
        if isinstance(file_id_or_path, Path):
            return _sanitize_download_name(file_id_or_path.name)
        return _sanitize_download_name(self.resolve_file(file_id_or_path).name)

    def _iter_allowed_files(self, root: Path) -> list[Path]:
        candidates: list[Path] = []
        for child in root.iterdir():
            if child.is_file() and child.suffix in self.allowed_suffixes:
                candidates.append(child)

        for directory in self.allowed_dirs:
            base_dir = root / directory
            if not base_dir.exists() or not base_dir.is_dir():
                continue
            for path in base_dir.rglob('*'):
                if path.is_file() and path.suffix in self.allowed_suffixes:
                    candidates.append(path)

        return [path for path in candidates if self._is_allowed_list_file(path)]

    def _is_allowed_list_file(self, path: Path) -> bool:
        try:
            self.resolve_file(self.encode_file_id(path.relative_to(self.root).as_posix()))
        except ValueError:
            return False
        return True

    def _build_item(self, path: Path, relative_path: str) -> LogFileItem:
        stat = path.stat()
        parts = relative_path.split('/')
        group = 'backend/log' if len(parts) == 1 else parts[0]
        mtime = datetime.fromtimestamp(stat.st_mtime, tz=timezone.tz_info).isoformat()
        return LogFileItem(
            file_id=self.encode_file_id(relative_path),
            relative_path=relative_path,
            name=path.name,
            group=group,
            size=stat.st_size,
            mtime=mtime,
            suffix=path.suffix,
        )

    @staticmethod
    def _clamp_limit(limit: int | None) -> int:
        requested = settings.STREAM_HUB_FILE_LOG_TAIL_DEFAULT if limit is None else limit
        return max(0, min(requested, settings.STREAM_HUB_FILE_LOG_TAIL_MAX))


def _tail_text_lines(path: Path, limit: int, chunk_size: int) -> tuple[list[str], bool]:
    if limit <= 0:
        return [], False

    safe_chunk_size = max(1, chunk_size)
    with path.open('rb') as file:
        file.seek(0, 2)
        end = file.tell()
        buffer = b''
        lines: list[bytes] = []
        position = end
        while position > 0 and len(lines) <= limit:
            read_size = min(safe_chunk_size, position)
            position -= read_size
            file.seek(position)
            buffer = file.read(read_size) + buffer
            lines = buffer.splitlines()
        selected = lines[-limit:]

    return [line.decode('utf-8', errors='replace') for line in selected], len(lines) > limit


def _sanitize_download_name(filename: str) -> str:
    safe_name = filename.translate(str.maketrans('', '', '\r\n";'))
    return safe_name or 'log-file'


log_file_service = LogFileService()
