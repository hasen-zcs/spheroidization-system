"""报表接口：summary 统计 + CSV / Excel 导出。

接口都挂在 page:records 权限下，游客一律 401（走 BusinessException
统一信封，HTTP 200 + body.code=401，和全项目其它接口一致）。
"""

from datetime import date, datetime

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse

from app.application.reports.service import ReportsService
from app.application.reports.stats import iter_csv_chunks, iter_excel_chunks
from app.core import permissions as P
from app.dependencies import get_container, require_permission
from app.schemas.common import ok
from app.schemas.reports import CSV_HEADER

router = APIRouter(prefix="/api/reports", tags=["报表"])

# .xlsx 的媒体类型（openpyxl 生成物默认类型）
EXCEL_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def get_reports_service(container=Depends(get_container)) -> ReportsService:
    """报表直查管理库，用 Container 里同一条连接。"""
    return ReportsService(container.conn)


@router.get("/summary")
def get_report_summary(
    start: date | None = Query(default=None),
    end: date | None = Query(default=None),
    _session=Depends(require_permission(P.PAGE_RECORDS)),
    service: ReportsService = Depends(get_reports_service),
):
    """区间统计：总量、类型分布、异常率、时长、温度覆盖、按天分布。"""
    data = service.summary(
        start.isoformat() if start else None,
        end.isoformat() if end else None,
    )
    return ok(data)


@router.get("/export")
def export_report_csv(
    start: date | None = Query(default=None),
    end: date | None = Query(default=None),
    type: int | None = Query(default=None, ge=0, le=6),
    _session=Depends(require_permission(P.PAGE_RECORDS)),
    service: ReportsService = Depends(get_reports_service),
):
    """CSV 流式导出：UTF-8 BOM + 生成器逐块发，1 万条 <30s。"""
    filename = f"spheroidization_{datetime.now():%Y%m%d}.csv"
    return StreamingResponse(
        iter_csv_chunks(
            CSV_HEADER,
            service.iter_export_rows(
                start.isoformat() if start else None,
                end.isoformat() if end else None,
                type,
            ),
        ),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/export/excel")
def export_report_excel(
    start: date | None = Query(default=None),
    end: date | None = Query(default=None),
    type: int | None = Query(default=None, ge=0, le=6),
    _session=Depends(require_permission(P.PAGE_RECORDS)),
    service: ReportsService = Depends(get_reports_service),
):
    """Excel 流式导出：openpyxl write_only 逐行落盘再分块发，表头与 CSV 一致。"""
    filename = f"spheroidization_{datetime.now():%Y%m%d}.xlsx"
    return StreamingResponse(
        iter_excel_chunks(
            CSV_HEADER,
            service.iter_export_rows(
                start.isoformat() if start else None,
                end.isoformat() if end else None,
                type,
            ),
        ),
        media_type=EXCEL_MEDIA_TYPE,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
