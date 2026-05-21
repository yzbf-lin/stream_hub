from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from typing import Any

from backend.common.socketio.server import sio
from backend.database.redis import redis_client
from backend.plugin.stream_hub.spec import StreamHubLogStreamSpec
from backend.utils.timezone import timezone


_APPEND_LOG_SCRIPT = """
local tail_key = KEYS[1]
local seq_key = KEYS[2]
local payload = cjson.decode(ARGV[1])
local limit = tonumber(ARGV[2])
local ttl = tonumber(ARGV[3])

local seq = redis.call("INCR", seq_key)
payload["stream_seq"] = seq
local encoded = cjson.encode(payload)

redis.call("LPUSH", tail_key, encoded)
redis.call("LTRIM", tail_key, 0, limit - 1)
redis.call("EXPIRE", tail_key, ttl)
redis.call("EXPIRE", seq_key, ttl)

return encoded
"""


class StreamHubLogStream:
    def __init__(self, redis: Any, sio: Any) -> None:
        self.redis = redis
        self.sio = sio

    async def append(
        self,
        spec: StreamHubLogStreamSpec,
        resource_id: int | str,
        message: str,
        level: str | None = None,
        channel: str | None = None,
        payload: Any | None = None,
        extra: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        truncated = False
        message, message_truncated = _truncate_utf8(message, spec.tail.max_line_bytes)
        truncated = truncated or message_truncated

        payload, payload_truncated = _normalize_payload(payload, spec.tail.max_payload_bytes)
        truncated = truncated or payload_truncated

        event_payload = _sanitize_extra(extra)
        if spec.id_key:
            event_payload[spec.id_key] = resource_id
        event_payload.update(
            {
                "message": message,
                "level": level or "INFO",
                "channel": channel or "console",
                "payload": payload,
                "created_time": timezone.now().isoformat(),
                "truncated": truncated,
            }
        )

        tail_key = spec.tail_key(resource_id)
        seq_key = spec.seq_key(resource_id)
        serialized = _json_dumps(event_payload)
        stored_payload = await self.redis.eval(
            _APPEND_LOG_SCRIPT,
            2,
            tail_key,
            seq_key,
            serialized,
            spec.tail.limit,
            spec.tail.ttl_seconds,
        )
        if isinstance(stored_payload, bytes):
            stored_payload = stored_payload.decode("utf-8")
        event_payload = json.loads(stored_payload)

        await self.sio.emit(
            spec.event("append"),
            event_payload,
            room=spec.room(resource_id),
        )
        return event_payload

    async def tail(
        self,
        spec: StreamHubLogStreamSpec,
        resource_id: int | str,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        tail_key = spec.tail_key(resource_id)
        items = await self.redis.lrange(tail_key, 0, max(limit - 1, 0))

        events: list[dict[str, Any]] = []
        for item in items:
            if isinstance(item, bytes):
                item = item.decode("utf-8")
            try:
                decoded = json.loads(item)
            except (TypeError, ValueError, json.JSONDecodeError):
                continue
            if isinstance(decoded, dict):
                events.append(decoded)

        events.reverse()
        return events

    async def clear(
        self,
        spec: StreamHubLogStreamSpec,
        resource_ids: Iterable[int | str],
    ) -> None:
        keys: list[str] = []
        for resource_id in resource_ids:
            keys.append(spec.tail_key(resource_id))
            keys.append(spec.seq_key(resource_id))
        if keys:
            await self.redis.delete(*keys)


def _truncate_utf8(value: str, max_bytes: int) -> tuple[str, bool]:
    encoded = value.encode("utf-8")
    if len(encoded) <= max_bytes:
        return value, False

    truncated = encoded[:max(max_bytes, 0)]
    while truncated:
        try:
            return truncated.decode("utf-8"), True
        except UnicodeDecodeError:
            truncated = truncated[:-1]
    return "", True


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, allow_nan=False)


def _normalize_payload(payload: Any | None, max_payload_bytes: int) -> tuple[Any | None, bool]:
    if payload is None:
        return None, False

    try:
        serialized = _json_dumps(payload)
    except (TypeError, ValueError):
        return None, True

    if len(serialized.encode("utf-8")) > max_payload_bytes:
        return None, True

    return payload, False


def _sanitize_extra(extra: Mapping[str, Any] | None) -> dict[str, Any]:
    safe_extra: dict[str, Any] = {}
    if not extra:
        return safe_extra

    for key, value in extra.items():
        if not isinstance(key, str):
            continue
        try:
            _json_dumps(value)
        except (TypeError, ValueError):
            continue
        safe_extra[key] = value
    return safe_extra


stream_hub_log_stream = StreamHubLogStream(redis=redis_client, sio=sio)
