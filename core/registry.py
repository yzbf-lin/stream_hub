from __future__ import annotations

from .spec import StreamHubStreamSpec


class StreamHubStreamRegistry:
    def __init__(self) -> None:
        self._specs: dict[tuple[str, str], StreamHubStreamSpec] = {}

    def register(self, spec: StreamHubStreamSpec) -> None:
        key = (spec.domain, spec.stream)
        if key in self._specs:
            raise ValueError(f"stream hub stream {spec.domain}.{spec.stream} already registered")

        self._specs[key] = spec

    def get(self, domain: str, stream: str) -> StreamHubStreamSpec | None:
        return self._specs.get((domain, stream))

    def list(self) -> list[StreamHubStreamSpec]:
        return list(self._specs.values())


stream_hub_registry = StreamHubStreamRegistry()
