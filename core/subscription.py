from __future__ import annotations

from typing import Any

from backend.common.log import log

from .publisher import StreamHubPublisher
from .spec import StreamHubStreamSpec


def bind_stream_hub(
    sio: Any,
    spec: StreamHubStreamSpec,
    publisher: StreamHubPublisher | None = None,
) -> None:
    stream_hub_publisher = publisher or StreamHubPublisher(sio=sio)

    @sio.on(spec.subscribe_event)
    async def subscribe(sid: str, data: dict[str, Any] | None = None) -> None:
        resource_id = _resolve_resource_id(spec, data)
        if not spec.fixed_room and resource_id is None:
            return

        await sio.enter_room(sid, spec.room(resource_id))

        snapshot_loader = getattr(spec, "snapshot_loader", None)
        if snapshot_loader is not None:
            try:
                snapshot = await snapshot_loader(resource_id)
            except Exception as exc:
                log.warning(
                    f"stream hub snapshot failed: "
                    f"event={spec.subscribe_event}, resource_id={resource_id}, error={exc!s}",
                )
                return
            await stream_hub_publisher.publish_to_sid(
                spec,
                spec.snapshot_feature,
                sid,
                snapshot,
                resource_id=resource_id,
            )

    @sio.on(spec.unsubscribe_event)
    async def unsubscribe(sid: str, data: dict[str, Any] | None = None) -> None:
        resource_id = _resolve_resource_id(spec, data)
        if not spec.fixed_room and resource_id is None:
            return

        await sio.leave_room(sid, spec.room(resource_id))


def _resolve_resource_id(
    spec: StreamHubStreamSpec,
    data: dict[str, Any] | None,
) -> int | str | None:
    if spec.fixed_room:
        return None

    if not isinstance(data, dict) or spec.id_key is None:
        return None

    resource_id = data.get(spec.id_key)
    if type(resource_id) is int:
        return resource_id

    if isinstance(resource_id, str) and resource_id:
        return resource_id

    return None
