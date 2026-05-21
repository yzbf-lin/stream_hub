from __future__ import annotations

import base64
import re
from pathlib import Path, PurePosixPath
from typing import Iterable

_FILE_ID_PATTERN = re.compile(r'^[A-Za-z0-9_-]+$')


def _to_posix_path(relative_path: str) -> str:
    return str(relative_path).replace('\\', '/')


def encode_log_file_id(relative_path: str) -> str:
    posix_path = _to_posix_path(relative_path)
    encoded = base64.urlsafe_b64encode(posix_path.encode('utf-8')).decode('ascii')
    return encoded.rstrip('=')


def decode_log_file_id(file_id: str) -> str:
    if not file_id:
        raise ValueError('Invalid log file id')
    if not _FILE_ID_PATTERN.fullmatch(file_id):
        raise ValueError('Invalid log file id')

    padding = '=' * (-len(file_id) % 4)
    try:
        decoded = base64.b64decode(
            (file_id + padding).encode('ascii'),
            altchars=b'-_',
            validate=True,
        ).decode('utf-8')
    except Exception as exc:
        raise ValueError('Invalid log file id') from exc

    posix_path = _to_posix_path(decoded)
    if encode_log_file_id(posix_path) != file_id:
        raise ValueError('Invalid log file id')

    return posix_path


def resolve_log_file_path(
    *,
    root: Path,
    file_id: str,
    allowed_dirs: Iterable[str],
    allowed_suffixes: Iterable[str],
) -> Path:
    relative_path = decode_log_file_id(file_id)
    posix_path = PurePosixPath(relative_path)
    parts = posix_path.parts

    if not parts or relative_path == '.':
        raise ValueError('Invalid log file path')
    if posix_path.is_absolute() or any(part == '..' for part in parts):
        raise ValueError('Invalid log file path')
    if len(parts) > 1 and parts[0] not in set(allowed_dirs):
        raise ValueError('Disallowed log file directory')
    if posix_path.suffix not in set(allowed_suffixes):
        raise ValueError('Disallowed log file suffix')

    try:
        root_path = Path(root).resolve(strict=True)
        candidate = root_path / Path(*parts)
        _reject_symlink_path(candidate, root_path)
        resolved = candidate.resolve(strict=True)
    except FileNotFoundError as exc:
        raise ValueError('Log file does not exist') from exc

    if not resolved.is_relative_to(root_path):
        raise ValueError('Log file escapes root')
    if not resolved.is_file():
        raise ValueError('Log file is not a regular file')

    return resolved


def _reject_symlink_path(candidate: Path, root_path: Path) -> None:
    relative = candidate.relative_to(root_path)
    current = root_path
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise ValueError('Log file symlink is not allowed')
