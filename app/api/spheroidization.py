"""球化检测记录的路由。

只做四件事：收请求 → 转参数 → 调 UseCase → 包响应。
业务规则（标准快照、处置不可逆）全在 UseCase 里，这里一行都不写。
"""

from fastapi import APIRouter, Depends, Query, Response

from app.application.spheroidization.create import CreateSpheroidizationUseCase
from app.application.spheroidization.process import ProcessSpheroidizationUseCase
from app.application.spheroidization.query import QuerySpheroidizationUseCase
from app.dependencies import (
    get_create_spheroidization_uc,
    get_process_spheroidization_uc,
    get_query_spheroidization_uc,
)
from app.schemas.common import fail, ok
from app.schemas.spheroidization import (
    SpheroidizationCreateRequest,
    SpheroidizationProcessRequest,
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
    records, total = uc.list_page(
        page=page,
        page_size=page_size,
        abnormal=abnormal,
        processed=processed,
    )
    latest_reviews = uc.latest_review_results(records)
    items = [
        to_response(
            record,
            review_result=latest_reviews.get(record.spheroidization_record_id),
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
):
    record = uc.execute(
        detection_time=data.detection_time,
        spheroidization_start_time=data.spheroidization_start_time,
        spheroidization_end_time=data.spheroidization_end_time,
        actual_spheroidization_time=data.actual_spheroidization_time,
        spheroidization_temperature=data.spheroidization_temperature,
        spheroidization_temperature_time=data.spheroidization_temperature_time,
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
        spheroidization_image=data.spheroidization_image,
    )
    # 创建响应不回带图片：上游刚把图发过来，再 base64 回去纯属浪费带宽。
    return ok(to_response(record), "球化记录创建成功")


@router.get("")
def query_spheroidization(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    abnormal: bool | None = Query(None),
    processed: bool | None = Query(None),
    uc: QuerySpheroidizationUseCase = Depends(get_query_spheroidization_uc),
):
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
    return ok(uc.stats())


@router.get("/{record_id}")
def get_spheroidization(
    record_id: int,
    uc: QuerySpheroidizationUseCase = Depends(get_query_spheroidization_uc),
):
    record = uc.get_by_id(record_id)
    if record is None:
        return fail("记录不存在", 404)
    # 详情是唯一带图的地方：只取一条，几百 KB 可以接受。
    # 上面两个列表接口刻意不带（见 schemas/spheroidization.py 的 to_response）。
    latest_reviews = uc.latest_review_results([record])
    return ok(
        to_response(
            record,
            with_image=True,
            review_result=latest_reviews.get(record.spheroidization_record_id),
        )
    )


@router.get("/{record_id}/image")
def get_spheroidization_image(
    record_id: int,
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
    data: SpheroidizationProcessRequest,
    uc: ProcessSpheroidizationUseCase = Depends(get_process_spheroidization_uc),
):
    # 记录不存在、或已经是已处理状态，都会抛 BusinessException，
    # 由 main.py 的处理器统一转成 {code: 400, message, data: null}
    record = uc.execute(record_id=record_id, processed_by=data.processed_by)
    return ok(to_response(record), "处理成功")
