from __future__ import annotations

from typing import Any, Mapping

from .spec import StreamHubStreamSpec


class StreamHubPublisher:
    def __init__(self, sio: Any) -> None:
        self.sio = sio

    async def publish(
        self,
        spec: StreamHubStreamSpec,
        feature: str,
        resource_id: int | str | None,
        payload: Mapping[str, Any],
    ) -> None:
        event_payload = dict(payload)
        self._add_resource_id(spec, event_payload, resource_id)

        await self.sio.emit(
            spec.event(feature),
            event_payload,
            room=spec.room(resource_id),
        )

    async def publish_to_sid(
        self,
        spec: StreamHubStreamSpec,
        feature: str,
        sid: str,
        payload: Mapping[str, Any],
        resource_id: int | str | None = None,
    ) -> None:
        event_payload = dict(payload)
        self._add_resource_id(spec, event_payload, resource_id)

        await self.sio.emit(spec.event(feature), event_payload, to=sid)

    def _add_resource_id(
        self,
        spec: StreamHubStreamSpec,
        payload: dict[str, Any],
        resource_id: int | str | None,
    ) -> None:
        if spec.id_key and resource_id is not None and spec.id_key not in payload:
            payload[spec.id_key] = resource_id
