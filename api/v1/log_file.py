from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query
from fastapi.responses import FileResponse

from backend.common.exception.errors import RequestError
from backend.common.response.response_schema import (
    ResponseModel,
    ResponseSchemaModel,
    response_base,
)
from backend.common.security.jwt import DependsJwtAuth
from backend.common.security.permission import RequestPermission
from backend.common.security.rbac import DependsRBAC
from backend.core.conf import settings
from backend.plugin.stream_hub.schema.log_file import (
    LogFileFollowResponse,
    LogFileItem,
    LogFileTailResponse,
)
from backend.plugin.stream_hub.service.file_log_tail_service import (
    file_log_tail_manager,
)
from backend.plugin.stream_hub.service.log_file_service import log_file_service

router = APIRouter(
    dependencies=[
        DependsJwtAuth,
        Depends(RequestPermission('stream_hub:log:view')),
        DependsRBAC,
    ],
)


def _normalize_log_file_error(exc: ValueError) -> RequestError:
    return RequestError(msg=str(exc))


@router.get('/log-files', summary='获取日志文件列表')
async def get_log_files() -> ResponseSchemaModel[list[LogFileItem]]:
    data = log_file_service.list_files()
    return response_base.success(data=data)


@router.get('/log-files/{file_id}/tail', summary='读取日志文件尾部')
async def tail_log_file(
    file_id: Annotated[str, Path(description='日志文件 ID')],
    limit: Annotated[
        int,
        Query(
            ge=1,
            le=settings.STREAM_HUB_FILE_LOG_TAIL_MAX,
            description='读取行数',
        ),
    ] = settings.STREAM_HUB_FILE_LOG_TAIL_DEFAULT,
) -> ResponseSchemaModel[LogFileTailResponse]:
    try:
        data = log_file_service.tail(file_id=file_id, limit=limit)
    except ValueError as exc:
        raise _normalize_log_file_error(exc) from exc
    return response_base.success(data=data)


@router.get('/log-files/{file_id}/download', summary='下载日志文件')
async def download_log_file(
    file_id: Annotated[str, Path(description='日志文件 ID')],
) -> FileResponse:
    try:
        path = log_file_service.download_path(file_id)
    except ValueError as exc:
        raise _normalize_log_file_error(exc) from exc
    return FileResponse(path, filename=log_file_service.safe_download_name(path))


@router.post('/log-files/{file_id}/follow', summary='关注日志文件')
async def follow_log_file(
    file_id: Annotated[str, Path(description='日志文件 ID')],
) -> ResponseSchemaModel[LogFileFollowResponse]:
    data = await file_log_tail_manager.follow(file_id)
    return response_base.success(data=data)


@router.post('/log-files/{file_id}/follow/{lease_id}/heartbeat', summary='续租日志文件关注')
async def heartbeat_log_file_follow(
    file_id: Annotated[str, Path(description='日志文件 ID')],
    lease_id: Annotated[str, Path(description='关注租约 ID')],
) -> ResponseSchemaModel[LogFileFollowResponse]:
    data = await file_log_tail_manager.heartbeat(file_id=file_id, lease_id=lease_id)
    return response_base.success(data=data)


@router.delete('/log-files/{file_id}/follow/{lease_id}', summary='取消关注日志文件')
async def unfollow_log_file(
    file_id: Annotated[str, Path(description='日志文件 ID')],
    lease_id: Annotated[str, Path(description='关注租约 ID')],
) -> ResponseModel:
    await file_log_tail_manager.unfollow(file_id=file_id, lease_id=lease_id)
    return response_base.success()
