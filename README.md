# stream_hub

`stream_hub` 是统一的流式事件中心后端插件，提供 Socket.IO 事件协议、订阅绑定、Redis 日志 tail、日志追加推送和日志文件读取能力

业务模块通过声明 stream schema 和发布事件接入，不需要手写事件名、房间名或 Redis key

## Plugin Type

App-level plugin

## Configuration

`.env` 使用以下键配置日志文件根目录和日志读取参数

```dotenv
STREAM_HUB_FILE_LOG_ROOT=backend/log
STREAM_HUB_FILE_LOG_TAIL_DEFAULT=500
STREAM_HUB_FILE_LOG_TAIL_MAX=1000
STREAM_HUB_FILE_LOG_LEASE_TTL_SECONDS=30
STREAM_HUB_FILE_LOG_HEARTBEAT_SECONDS=15
STREAM_HUB_FILE_LOG_MAX_WATCHERS=20
STREAM_HUB_FILE_LOG_IDLE_TTL_SECONDS=60
STREAM_HUB_FILE_LOG_READ_CHUNK_BYTES=131072
```

`plugin.toml` 的 `[settings]` 中包含以下内容

```toml
STREAM_HUB_LOG_TAIL_LIMIT = 600
STREAM_HUB_LOG_TAIL_TTL_SECONDS = 21600
STREAM_HUB_LOG_TERMINAL_TTL_SECONDS = 3600
STREAM_HUB_LOG_MAX_LINE_BYTES = 4096
STREAM_HUB_LOG_MAX_PAYLOAD_BYTES = 8192
STREAM_HUB_FILE_LOG_ROOT = 'backend/log'
STREAM_HUB_FILE_LOG_TAIL_DEFAULT = 500
STREAM_HUB_FILE_LOG_TAIL_MAX = 1000
STREAM_HUB_FILE_LOG_LEASE_TTL_SECONDS = 30
STREAM_HUB_FILE_LOG_HEARTBEAT_SECONDS = 15
STREAM_HUB_FILE_LOG_MAX_WATCHERS = 20
STREAM_HUB_FILE_LOG_IDLE_TTL_SECONDS = 60
STREAM_HUB_FILE_LOG_READ_CHUNK_BYTES = 131072
```

当前项目的 `backend/core/conf.py` 已包含以下字段

```python
    # Plugin 配置
    PLUGIN_PIP_CHINA: bool = True
    PLUGIN_PIP_INDEX_URL: str = 'https://mirrors.aliyun.com/pypi/simple/'
    PLUGIN_PIP_MAX_RETRY: int = 3
    PLUGIN_REDIS_PREFIX: str = 'fba:plugin'
    STREAM_HUB_FILE_LOG_ROOT: str = 'backend/log'
    STREAM_HUB_FILE_LOG_TAIL_DEFAULT: int = 500
    STREAM_HUB_FILE_LOG_TAIL_MAX: int = 1000
    STREAM_HUB_FILE_LOG_LEASE_TTL_SECONDS: int = 30
    STREAM_HUB_FILE_LOG_HEARTBEAT_SECONDS: int = 15
    STREAM_HUB_FILE_LOG_MAX_WATCHERS: int = 20
    STREAM_HUB_FILE_LOG_IDLE_TTL_SECONDS: int = 60
    STREAM_HUB_FILE_LOG_READ_CHUNK_BYTES: int = 128 * 1024
```

## Usage

1. 在业务模块中定义 `StreamHubStreamSpec` 或 `StreamHubLogStreamSpec`
2. 使用 `bind_stream_hub` 绑定普通订阅，复杂订阅在业务 `actions.py` 中复用 stream schema 手写处理
3. 使用 `StreamHubPublisher` 发布状态、进度和行为记录
4. 使用 `stream_hub_log_stream` 追加和读取业务日志 tail
5. 前端使用同一组 `domain`、`stream`、`resource` 和 `features` 定义 schema 后消费事件

## Uninstall

移除插件目录和配套前端插件，清理使用 `stream_hub` 的业务导入、订阅绑定、日志推送集成和菜单数据

清理 Redis 中该插件产生的 tail、seq、follow lease 和插件状态缓存

移除 `.env`、`plugin.toml`、`backend/core/conf.py` 中与该插件相关的配置

## Contact

Author: pd-qa-backend
