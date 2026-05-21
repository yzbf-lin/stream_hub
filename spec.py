from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable
import re


SnapshotLoader = Callable[[int | str | None], Awaitable[dict[str, Any]]]


def _validate_name(value: str, *, field: str) -> str:
    if not value or not re.fullmatch(r"[A-Za-z0-9_]+", value):
        raise ValueError(f"{field} must contain only letters, numbers, and underscore")
    return value


@dataclass(frozen=True)
class TailPolicy:
    limit: int = 600
    ttl_seconds: int = 6 * 60 * 60
    terminal_ttl_seconds: int = 60 * 60
    max_line_bytes: int = 4096
    max_payload_bytes: int = 8192


@dataclass(frozen=True)
class StreamHubStreamSpec:
    domain: str
    stream: str
    resource: str | None = None
    features: frozenset[str] = field(default_factory=frozenset)
    fixed_room: bool = False
    snapshot_loader: SnapshotLoader | None = None
    snapshot_feature: str = "snapshot"

    def __post_init__(self) -> None:
        _validate_name(self.domain, field="domain")
        _validate_name(self.stream, field="stream")
        _validate_name(self.snapshot_feature, field="snapshot_feature")
        if self.resource is not None:
            _validate_name(self.resource, field="resource")

        object.__setattr__(self, "features", frozenset(self.features))

    def event(self, feature: str) -> str:
        _validate_name(feature, field="feature")
        return f"{self.domain}_{self.stream}_{feature}"

    @property
    def subscribe_event(self) -> str:
        return f"{self.domain}_{self.stream}_subscribe"

    @property
    def unsubscribe_event(self) -> str:
        return f"{self.domain}_{self.stream}_unsubscribe"

    def room(self, resource_id: int | str | None = None) -> str:
        if self.fixed_room:
            return f"{self.domain}:{self.stream}"
        return f"{self.domain}:{self.stream}:{resource_id}"

    @property
    def id_key(self) -> str | None:
        if self.fixed_room or self.resource is None:
            return None
        return f"{self.resource}_id"


@dataclass(frozen=True)
class StreamHubLogStreamSpec(StreamHubStreamSpec):
    tail: TailPolicy = field(default_factory=TailPolicy)

    def tail_key(self, resource_id: int | str) -> str:
        return f"{self.domain}:{self.stream}:tail:{resource_id}"

    def seq_key(self, resource_id: int | str) -> str:
        return f"{self.domain}:{self.stream}:seq:{resource_id}"
