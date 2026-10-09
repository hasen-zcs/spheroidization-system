"""检测标准的路由。

只做四件事：收请求 → 转参数 → 调 UseCase → 包响应。
"""

from fastapi import APIRouter, Depends

from app.application.standard.create import CreateStandardUseCase
from app.application.standard.apply import ApplyStandardUseCase
from app.application.standard.query import QueryStandardUseCase
from app.dependencies import (
    get_apply_standard_uc,
    get_create_standard_uc,
    get_query_standard_uc,
)
from app.schemas.common import ok
from app.schemas.standard import StandardCreateRequest, to_response

router = APIRouter(
    prefix="/api/standards",
    tags=["检测标准"],
)


@router.post("")
def create_standard(
    data: StandardCreateRequest,
    uc: CreateStandardUseCase = Depends(get_create_standard_uc),
):
    # 标准只增不改：创建一条新的，它立即成为当前有效标准，历史标准全部保留
    standard = uc.execute(
        standard_spheroidization_time=data.standard_spheroidization_time,
        weighing_standard=data.weighing_standard,
        created_by=data.created_by,
        standard_spheroidization_time_upper=data.standard_spheroidization_time_upper,
        standard_spheroidization_time_lower=data.standard_spheroidization_time_lower,
        remark=data.remark,
    )
    return ok(to_response(standard), "标准创建成功")


@router.get("/current")
def get_current_standard(
    uc: QueryStandardUseCase = Depends(get_query_standard_uc),
):
    standard = uc.get_current()
    # 一条标准都没有时返回 null。
    # 不要写成 standards[-1] 那种取法——空表会 IndexError，变成 500。
    return ok(to_response(standard) if standard else None)


@router.get("/history")
def get_standard_history(
    uc: QueryStandardUseCase = Depends(get_query_standard_uc),
):
    return ok([to_response(standard) for standard in uc.get_history()])


@router.post("/{standard_id}/apply")
def apply_standard(
    standard_id: int,
    uc: ApplyStandardUseCase = Depends(get_apply_standard_uc),
):
    standard = uc.execute(standard_id)
    return ok(to_response(standard), "标准应用成功")
