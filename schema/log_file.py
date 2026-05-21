from __future__ import annotations

from pydantic import ConfigDict, Field

from backend.common.schema import SchemaBase


class LogFileItem(SchemaBase):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)

    file_id: str = Field(serialization_alias='fileId')
    relative_path: str = Field(serialization_alias='relativePath')
    name: str
    group: str
    size: int
    mtime: str
    suffix: str


class LogFileLine(SchemaBase):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)

    line: str
    message: str
    stream_seq: int
    level: str = 'INFO'
    code: str | None = None
    file_id: str | None = Field(default=None, serialization_alias='fileId')


class LogFileTailResponse(SchemaBase):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)

    file_id: str = Field(serialization_alias='fileId')
    exists: bool
    lines: list[LogFileLine]
    limit: int
    truncated: bool = False


class LogFileFollowResponse(SchemaBase):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)

    file_id: str = Field(serialization_alias='fileId')
    following: bool
    lease_id: str = Field(serialization_alias='leaseId')
    lease_expires_in: int = Field(serialization_alias='leaseExpiresIn')
    watcher_count: int = Field(serialization_alias='watcherCount')
