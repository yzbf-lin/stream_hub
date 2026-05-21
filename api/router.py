from fastapi import APIRouter

from backend.core.conf import settings
from backend.plugin.stream_hub import actions as actions
from backend.plugin.stream_hub.api.v1.log_file import router as log_file_router

v1 = APIRouter(prefix=f'{settings.FASTAPI_API_V1_PATH}/stream-hub', tags=['流式事件中心'])
v1.include_router(log_file_router)
