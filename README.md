# stream_hub 后端插件使用指南

`stream_hub` 是统一的流式事件中心插件，用于承载任务状态、玩家状态、行为记录、日志 tail 和日志文件增量推送。当前传输层使用 Socket.IO；业务调用方只依赖 stream schema、publisher 和订阅绑定函数，不直接拼事件名、房间名或 Redis key。

插件仓库：

```text
git@github.com:yzbf-lin/stream_hub.git
```

前端配套插件仓库：

```text
git@github.com:yzbf-lin/stream_hub_ui.git
```

## 插件边界

后端目录：

```text
backend/plugin/stream_hub
```

这个插件包含两类能力：

- 通用事件通道：定义 stream、生成事件名/room、绑定订阅、发布增量事件。
- 日志基础能力：Redis tail 缓存、日志 append 推送、`backend/log` 文件列表/tail/follow/download API。

不建议把业务命令放进这里。任务启动、表单提交、状态变更仍应走对应业务 API；`stream_hub` 只负责服务端主动把结果推给前端。

## 推荐接入流程

业务模块接入时只需要关心自己的 stream 定义和发布时机，不需要手写事件名、房间名或 Redis key。

1. 在业务模块中定义 `StreamHubStreamSpec` 或 `StreamHubLogStreamSpec`。
2. 普通资源订阅使用 `bind_stream_hub` 注册；需要权限校验、参数校验或自定义 snapshot 时，在业务 `actions.py` 里手写 subscribe handler。
3. 状态、进度、行为记录等结构化事件使用 `StreamHubPublisher.publish()` 推送。
4. 日志追加使用 `stream_hub_log_stream.append()`，历史日志使用 `stream_hub_log_stream.tail()`。
5. 前端使用同一组 `domain`、`stream`、`resource`、`features` 定义 schema 后订阅。

日志文件 API 是插件提供的运维查看能力，主要用于演示和复用 `backend/log` 文件 tail/follow/download 的基础能力。业务实时日志不要求绑定到日志文件页面；更推荐按业务资源定义自己的日志 stream。

## 核心对象

```python
from backend.plugin.stream_hub import (
    StreamHubLogStreamSpec,
    StreamHubPublisher,
    StreamHubStreamSpec,
    TailPolicy,
    bind_stream_hub,
)
from backend.plugin.stream_hub.log_stream import stream_hub_log_stream
```

- `StreamHubStreamSpec`：定义普通事件流的 `domain`、`stream`、`resource`、`features`。
- `StreamHubLogStreamSpec`：定义日志流，额外包含 Redis tail 策略。
- `StreamHubPublisher`：按 spec 发布事件，并自动补齐资源 id 字段。
- `bind_stream_hub`：为普通流注册 Socket.IO subscribe/unsubscribe。
- `stream_hub_log_stream`：写入 Redis tail，并向日志 room 推送 append 事件。

## 普通事件流

定义 stream：

```python
from backend.common.socketio.server import sio
from backend.plugin.stream_hub import StreamHubPublisher, StreamHubStreamSpec, bind_stream_hub


TASK_RUN_STREAM = StreamHubStreamSpec(
    domain="env_task",
    stream="run",
    resource="run",
    features=frozenset({"snapshot", "status", "finished"}),
)

stream_hub_publisher = StreamHubPublisher(sio=sio)
bind_stream_hub(sio=sio, spec=TASK_RUN_STREAM, publisher=stream_hub_publisher)
```

生成协议：

```text
subscribe event   env_task_run_subscribe
unsubscribe event env_task_run_unsubscribe
feature event     env_task_run_status
room              env_task:run:{run_id}
resource id key   run_id
```

发布事件：

```python
await stream_hub_publisher.publish(
    TASK_RUN_STREAM,
    "status",
    run_id,
    {"status": "RUNNING"},
)
```

`StreamHubPublisher` 会自动把 `run_id` 写入 payload。调用方只需要传业务字段。

## 自定义订阅

如果订阅时需要权限校验、资源校验、额外参数或自定义 snapshot，不要使用 `bind_stream_hub`，在业务 `actions.py` 里手写 handler，但仍复用 spec：

```python
@sio.on(TASK_RUN_STREAM.subscribe_event)
async def task_run_subscribe(sid, data):
    run_id = int((data or {}).get("run_id") or 0)
    if run_id <= 0:
        return

    await sio.enter_room(sid, TASK_RUN_STREAM.room(run_id))
    await stream_hub_publisher.publish_to_sid(
        TASK_RUN_STREAM,
        "snapshot",
        sid,
        {"run_id": run_id, "status": "RUNNING"},
        resource_id=run_id,
    )
```

## 日志流

定义日志流：

```python
TASK_RUN_LOG_STREAM = StreamHubLogStreamSpec(
    domain="env_task",
    stream="run_log",
    resource="run",
    features=frozenset({"append"}),
    tail=TailPolicy(limit=600, ttl_seconds=6 * 60 * 60),
)
```

追加日志：

```python
await stream_hub_log_stream.append(
    TASK_RUN_LOG_STREAM,
    resource_id=run_id,
    message="template started",
    level="INFO",
    channel="console",
    extra={"runId": run_id},
)
```

读取 tail：

```python
logs = await stream_hub_log_stream.tail(
    TASK_RUN_LOG_STREAM,
    resource_id=run_id,
    limit=100,
)
```

日志流会使用 Redis list 缓存最近若干行，并用 `stream_seq` 做去重和排序。Redis key 会按 `TailPolicy.limit` 做 `LTRIM`，并按 `TailPolicy.ttl_seconds` 设置 TTL。

## 日志文件 API

日志文件接口挂在：

```text
/api/v1/stream-hub/log-files
```

接口权限：

```text
stream_hub:log:view
```

主要接口：

- `GET /log-files`：列出 `backend/log` 下的日志文件。
- `GET /log-files/{file_id}/tail`：读取文件尾部。
- `GET /log-files/{file_id}/download`：下载日志文件。
- `POST /log-files/{file_id}/follow`：创建 follow lease。
- `POST /log-files/{file_id}/follow/{lease_id}/heartbeat`：续租 follow lease。
- `DELETE /log-files/{file_id}/follow/{lease_id}`：取消 follow。

文件增量事件：

```text
stream_hub_file_log_append
```

对应 room：

```text
stream_hub:file_log:{fileId}
```

这组 API 被前端插件内置的日志控制台示例页面使用。接入方可以复用 API 和 follow 机制，也可以完全不注册这个页面，只使用事件流和日志流能力。

## 配置项

配置来自 `plugin.toml` 的 `[settings]`，也可以通过环境变量覆盖。

| 配置 | 默认值 | 说明 |
| --- | --- | --- |
| `STREAM_HUB_LOG_TAIL_LIMIT` | `600` | Redis 日志 tail 行数 |
| `STREAM_HUB_LOG_TAIL_TTL_SECONDS` | `21600` | Redis tail TTL |
| `STREAM_HUB_LOG_TERMINAL_TTL_SECONDS` | `3600` | 终态日志 TTL |
| `STREAM_HUB_LOG_MAX_LINE_BYTES` | `4096` | 单行日志最大字节 |
| `STREAM_HUB_LOG_MAX_PAYLOAD_BYTES` | `8192` | 单条 payload 最大字节 |
| `STREAM_HUB_FILE_LOG_ROOT` | `backend/log` | 日志文件根目录 |
| `STREAM_HUB_FILE_LOG_TAIL_DEFAULT` | `500` | 默认 tail 行数 |
| `STREAM_HUB_FILE_LOG_TAIL_MAX` | `1000` | 最大 tail 行数 |
| `STREAM_HUB_FILE_LOG_LEASE_TTL_SECONDS` | `30` | follow lease TTL |
| `STREAM_HUB_FILE_LOG_HEARTBEAT_SECONDS` | `15` | 前端建议心跳秒数 |
| `STREAM_HUB_FILE_LOG_MAX_WATCHERS` | `20` | 单进程最大文件 watcher 数 |
| `STREAM_HUB_FILE_LOG_IDLE_TTL_SECONDS` | `60` | watcher 空闲保留秒数 |
| `STREAM_HUB_FILE_LOG_READ_CHUNK_BYTES` | `131072` | 单次文件读取块大小 |

## 多进程与多服务器

任务被任意 Celery worker 消费不影响 Redis tail 写入，只要 worker 与 API 使用同一套 Redis 配置。

实时广播是否跨 API 进程生效，取决于 Socket.IO 是否启用了 Redis manager 或等价消息总线。未启用时，事件只能可靠送达当前 API 进程上的 socket 客户端。

日志文件 follow 是 API 进程内的文件 watcher。多服务器部署时需要确保被查看的日志文件存在于当前 API 节点的 `STREAM_HUB_FILE_LOG_ROOT`，或者把日志目录挂载为共享存储。

## 内存管理

- Redis tail 使用 `LPUSH + LTRIM + EXPIRE`，不会无限增长。
- `stream_seq` key 与 tail key 使用相同 TTL。
- 文件 follow 使用 lease + heartbeat，客户端断开后会自动过期。
- watcher 数量受 `STREAM_HUB_FILE_LOG_MAX_WATCHERS` 限制。
- watcher 空闲后按 `STREAM_HUB_FILE_LOG_IDLE_TTL_SECONDS` 清理。
- 文件读取按 `STREAM_HUB_FILE_LOG_READ_CHUNK_BYTES` 分块，避免长时间运行时把大文件一次性读入内存。

## 发布到插件仓库

按照 FBA 插件分享规范，后端插件仓库名等于插件名。发布时将 `backend/plugin/stream_hub` 目录中的所有文件提交到：

```text
git@github.com:yzbf-lin/stream_hub.git
```

注意是复制目录内容，不是把 `stream_hub` 目录本身再套一层。
