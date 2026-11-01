"""球化检测记录的路由。

只做四件事：收请求 → 转参数 → 调 UseCase → 包响应。
业务规则（标准快照、处置不可逆）全在 UseCase 里，这里一行都不写。
"""

from fastapi import APIRouter, Depends, Query, Response

from app.application.spheroidization.create import CreateSpheroidizationUseCase
from app.application.spheroidization.process import ProcessSpheroidizationUseCase
from app.application.spheroidization.query import QuerySpheroidizationUseCase
from app.application.temperature.create import CreateTemperatureUseCase
from app.core import permissions as P
from app.domain.flash.entities import FlashSegment
from app.core.security import Session
from app.dependencies import (
    get_create_spheroidization_uc,
    get_create_temperature_uc,
    get_optional_session,
    get_process_spheroidization_uc,
    get_query_spheroidization_uc,
    require_login,
    require_permission,
)
from app.schemas.common import fail, ok
from app.schemas.spheroidization import (
    SpheroidizationCreateRequest,
    SpheroidizationProcessRequest,
    segments_to_response,
    to_response,
)

router = APIRouter(
    prefix="/api/spheroidization",
    tags=["球化记录"],
)


# 库里只存 BLOB，没有单独的 MIME 列，所以只能靠文件头认。
# 工业相机出的图基本就是 JPEG / PNG，多认几个是顺手的事。
_IMAGE_MAGIC = (
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"GIF87a", "image/gif"),
    (b"GIF89a", "image/gif"),
    (b"BM", "image/bmp"),
)


def _guess_media_type(blob: bytes) -> str:
    """按文件头猜 Content-Type，认不出来就 octet-stream。

    猜错不影响图片本身——字节是原样给的，只是浏览器少了点渲染线索。
    所以这里宁可保守：认不出就是 octet-stream，绝不瞎认。
    """
    for magic, media_type in _IMAGE_MAGIC:
        if blob.startswith(magic):
            return media_type
    # WEBP 是 RIFF 容器，真正的类型在第 8~12 字节
    if blob[:4] == b"RIFF" and blob[8:12] == b"WEBP":
        return "image/webp"
    return "application/octet-stream"


def _page_response(
    uc: QuerySpheroidizationUseCase,
    page: int,
    page_size: int,
    abnormal: bool | None = None,
    processed: bool | None = None,
):
    """三条列表接口共用的分页响应，改一处就全生效。

    前端读的是 data.items / total / page / page_size / has_more，
    不要在某个路由里单独改成裸数组。
    """
    records, total = uc.list_page(
        page=page,
        page_size=page_size,
        abnormal=abnormal,
        processed=processed,
    )
    latest_reviews = uc.latest_review_results(records)
    temperatures = uc.temperatures_for(records)
    items = [
        to_response(
            record,
            review_result=latest_reviews.get(record.spheroidization_record_id),
            temperature=temperatures.get(record.spheroidization_record_id),
        )
        for record in records
    ]
    return ok(
        {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
            "has_more": page * page_size < total,
        }
    )


@router.post("")
def create_spheroidization(
    data: SpheroidizationCreateRequest,
    uc: CreateSpheroidizationUseCase = Depends(get_create_spheroidization_uc),
    temp_uc: CreateTemperatureUseCase = Depends(get_create_temperature_uc),
):
    # 这个接口是上游检测程序调用的，不是人操作，所以不挂权限校验。
    # 也正因为对程序开放，前端不能保留"新增记录"的人工入口——
    # 不登录就能 POST 假数据，删掉按钮拦不住接口本身，只能靠不放人用。
    # 上游给的分段是"校验用模型"，落库用领域实体；换算规则在合并层做完了，
    # 到这里已经是相对秒（见第一刀方案 v2 第 5.3 节）。
    segments = [
        FlashSegment(
            seg_index=seg.seg_index,
            start_offset=seg.start_offset,
            end_offset=seg.end_offset,
            gap_before=seg.gap_before,
            duration=seg.duration,
        )
        for seg in data.segments
    ]
    record, existing = uc.execute_idempotent(
        detection_time=data.detection_time,
        spheroidization_start_time=data.spheroidization_start_time,
        spheroidization_end_time=data.spheroidization_end_time,
        actual_spheroidization_time=data.actual_spheroidization_time,
        spheroidization_wire_entry_start_time=(
            data.spheroidization_wire_entry_start_time
        ),
        spheroidization_wire_entry_end_time=data.spheroidization_wire_entry_end_time,
        spheroidization_wire_entry_total_duration=(
            data.spheroidization_wire_entry_total_duration
        ),
        spheroidization_weight=data.spheroidization_weight,
        # 前端发的是 bool，实体要 0 / 1，球化是否成功
        spheroidization_abnormal=(
            None
            if data.spheroidization_abnormal is None
            else int(data.spheroidization_abnormal)
        ),
        # 异常分类和说明原样透传，后端不判
        abnormal_type=data.abnormal_type,
        abnormal_reason=data.abnormal_reason,
        plc_button_time=data.plc_button_time,
        spheroidization_image=data.spheroidization_image,
        # 没带这两个就是老调用（人工补录/旧上传器），用例内部会走原路径
        device_id=data.device_id,
        external_id=data.external_id,
        segments=segments,
    )
    # 人工补录时随记录带的温度：机器流程一律走 POST /api/temperature，
    # 这条分支只为补录服务，gun_no 默认 0 表示人工录入。
    temperature = None
    # 幂等命中时不再补温度：上一次投递已经把温度落库了，
    # 再来一遍就会给同一条记录挂出第二条读数（枪号时间都一样，纯脏数据）。
    if data.temperature is not None and not existing:
        temperature = temp_uc.execute(
            gun_no=data.gun_no,
            temperature=data.temperature,
            measured_at=data.temperature_time,
            spheroidization_record_id=record.spheroidization_record_id,
        )

    # 创建响应不回带图片：上游刚把图发过来，再 base64 回去纯属浪费带宽。
    payload = to_response(record, temperature=temperature)
    # existing=true 表示这次是幂等命中：数据早就有了，本次没有新建。
    # 合并层靠它区分"新上传成功"和"重复投递"，不用自己再查一遍。
    payload["existing"] = existing
    return ok(
        payload,
        "球化记录已存在（幂等命中）" if existing else "球化记录创建成功",
    )


@router.get("")
def query_spheroidization(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    abnormal: bool | None = Query(None),
    processed: bool | None = Query(None),
    session: Session | None = Depends(get_optional_session),
    uc: QuerySpheroidizationUseCase = Depends(get_query_spheroidization_uc),
):
    # 游客能看正常记录（监控页要用），但异常记录不对游客开放。
    # 光给 /abnormal 挂权限不够：这里带 ?abnormal=true 一样能拿到，
    # 所以参数级判断必须写在这。
    # 已登录用户不再校验 page:abnormal——球化记录页自己就有「异常」筛选，
    # page:records 的用户选这个筛选是正常功能，卡住会让页面直接报错。
    if session is None and abnormal:
        return fail("请先登录后查看异常记录", 403)

    return _page_response(
        uc=uc,
        page=page,
        page_size=page_size,
        abnormal=abnormal,
        processed=processed,
    )


# 注意：/abnormal 必须声明在 /{record_id} 前面。
# 反过来的话，"abnormal" 会被当成 record_id 去转 int，直接 422。
@router.get("/abnormal")
def query_abnormal_spheroidization(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    session: Session = Depends(require_permission(P.PAGE_ABNORMAL)),
    uc: QuerySpheroidizationUseCase = Depends(get_query_spheroidization_uc),
):
    return _page_response(
        uc=uc,
        page=page,
        page_size=page_size,
        abnormal=True,
    )


@router.get("/stats")
def spheroidization_stats(
    uc: QuerySpheroidizationUseCase = Depends(get_query_spheroidization_uc),
):
    # 不挂权限：首页的统计卡片游客也要看得到。
    return ok(uc.stats())


@router.get("/{record_id}")
def get_spheroidization(
    record_id: int,
    session: Session = Depends(require_login),
    uc: QuerySpheroidizationUseCase = Depends(get_query_spheroidization_uc),
):
    # 只要登录，不挂页面权限：详情页对 page:records 和 page:abnormal 的用户
    # 都要能用，挂任何一个都会把另一边挡在门外。
    record = uc.get_by_id(record_id)
    if record is None:
        return fail("记录不存在", 404)
    # 详情是唯一带图的地方：只取一条，几百 KB 可以接受。
    # 上面两个列表接口刻意不带（见 schemas/spheroidization.py 的 to_response）。
    latest_reviews = uc.latest_review_results([record])
    temperatures = uc.temperatures_for([record])
    segments = uc.segments_for(record.spheroidization_record_id)
    return ok(
        to_response(
            record,
            with_image=True,
            review_result=latest_reviews.get(record.spheroidization_record_id),
            temperature=temperatures.get(record.spheroidization_record_id),
            # 详情是唯一返回分段的地方；老记录/单段记录给空列表
            segments=segments_to_response(segments),
        )
    )


@router.get("/{record_id}/image")
def get_spheroidization_image(
    record_id: int,
    session: Session = Depends(require_login),
    uc: QuerySpheroidizationUseCase = Depends(get_query_spheroidization_uc),
):
    """直接把图片字节吐出来，响应体不是 JSON，是图片本身。

    给前端的 <img src> 用的：

        <img :src="`/api/spheroidization/${record.id}/image`">

    比走详情接口拿 base64 省事：浏览器自己会缓存，也不用在 JS 里解码再拼
    blob URL。详情接口里那份 base64 保留着，前端想用哪种都行。

    失败时返回的是普通 JSON 信封（code 404），此时 Content-Type 是 JSON，
    <img> 会显示成裂图——这是预期行为，别指望失败时还能拿到一张占位图。
    """
    record = uc.get_by_id(record_id)
    if record is None:
        return fail("记录不存在", 404)
    if record.spheroidization_image is None:
        return fail("该记录没有图片", 404)

    blob = record.spheroidization_image
    return Response(
        content=blob,
        media_type=_guess_media_type(blob),
        # 记录一落库就不会再改图，可以放心长缓存
        headers={"Cache-Control": "public, max-age=86400"},
    )


@router.post("/{record_id}/process")
def process_spheroidization(
    record_id: int,
    # 前端 processSpheroidization() 是裸 POST、不带 body；这里必须允许空，
    # 否则 FastAPI 直接 422，按钮永远点不动。请求模型本身也是空的（处理人取登录态）。
    data: SpheroidizationProcessRequest | None = None,
    session: Session = Depends(require_permission(P.ACTION_PROCESS)),
    uc: ProcessSpheroidizationUseCase = Depends(get_process_spheroidization_uc),
):
    # 处理人从登录态取，不读 data.processed_by：
    # 谁点的"已处理"必须是可追溯的事实，不能让人随便填。
    # 记录不存在、或已经是已处理状态，都会抛 BusinessException，
    # 由 main.py 的处理器统一转成 {code: 400, message, data: null}
    record = uc.execute(record_id=record_id, processed_by=session.username)
    return ok(to_response(record), "处理成功")
