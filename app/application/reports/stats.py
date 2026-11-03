"""报表用的纯函数：口径计算、日期边界归一、CSV 切块。

纯函数不碰数据库、不碰 FastAPI，方便单测直接调。
统计口径唯一准绳是管理库（SpheroidizationRecord 等表），
SQL 在 service.py，这里只算"拿到数字之后怎么算"。
"""

import csv
import io
import os
import tempfile
from datetime import datetime
from typing import Iterable, Iterator, Sequence


def _parse_bound(value: str, name: str) -> str:
    """校验日期边界，支持 "YYYY-MM-DD" 和 "YYYY-MM-DD HH:MM:SS"。"""
    for fmt in ("%Y-%m-%d", "%Y-%m-%d %H:%M:%S"):
        try:
            datetime.strptime(value, fmt)
            return value
        except ValueError:
            continue
    raise ValueError(f"{name} 格式不合法（要 YYYY-MM-DD）：{value!r}")


def normalize_range(start: str | None, end: str | None) -> tuple[str | None, str | None]:
    """把起止边界归一成可以直接做字符串比较的区间（含头含尾）。

    detection_time 存的是 "YYYY-MM-DD HH:MM:SS" 文本，SQLite 里按字典序比较
    和时间序一致，所以边界也是文本：
      - start 传日期 "2026-09-05" 原样用：当天 00:00:00 之后的都比它大
      - end 传日期 "2026-09-05" 要补到 23:59:59.999，否则当天 00:00:00 之后的全被挡掉
    """
    start_bound = _parse_bound(start, "start") if start else None
    end_bound = _parse_bound(end, "end") if end else None
    if end_bound is not None and len(end_bound) == 10:
        end_bound = end_bound + " 23:59:59.999"
    if start_bound and end_bound and start_bound > end_bound:
        raise ValueError("开始日期不能晚于结束日期")
    return start_bound, end_bound


def duration_stats(values: Sequence[float]) -> dict:
    """球化时长统计（秒，仅非空值）。没有样本时各项都是 None，不是 0——0 秒是假数据。"""
    if not values:
        return {"avg": None, "median": None, "min": None, "max": None}
    values = list(values)
    ordered = sorted(values)
    n = len(ordered)
    if n % 2 == 1:
        median = ordered[n // 2]
    else:
        median = (ordered[n // 2 - 1] + ordered[n // 2]) / 2
    return {
        "avg": round(sum(values) / n, 2),
        "median": round(median, 2),
        "min": round(min(values), 2),
        "max": round(max(values), 2),
    }


def rate(part: int, total: int) -> float:
    """占比，保留 4 位；总数为 0 时给 0.0，不抛除零。"""
    if total <= 0:
        return 0.0
    return round(part / total, 4)


def build_by_type(rows: Iterable[tuple[int, int]]) -> dict:
    """把 GROUP BY 出来的 (类型, 数量) 补齐成 0..6 全键的 dict。

    库里 abnormal_type 可空（机器没给判定），口径里 NULL 归入 0（正常），
    所以 SQL 侧先 COALESCE 过，这里直接按 0..6 铺底。
    """
    by_type = {t: 0 for t in range(7)}
    for type_, count in rows:
        by_type[type_] = count
    return by_type


def iter_csv_chunks(
    header: Sequence[str], rows: Iterable[Sequence[object]], chunk_size: int = 500
) -> Iterator[str]:
    """把行生成器切成 CSV 文本块流式吐出。第一块前面带 UTF-8 BOM。

    用 StringIO 攒块而不是整文件：1 万条不用一次性占内存。
    """
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")

    def flush() -> str:
        text = buffer.getvalue()
        buffer.seek(0)
        buffer.truncate(0)
        return text

    writer.writerow(header)
    yield "\ufeff" + flush()  # BOM 只发一次，Excel 打开中文不乱码

    written = 0
    for row in rows:
        writer.writerow(row)
        written += 1
        if written % chunk_size == 0:
            yield flush()
    tail = flush()
    if tail:
        yield tail


def iter_excel_chunks(
    header: Sequence[str], rows: Iterable[Sequence[object]], chunk_size: int = 64 * 1024
) -> Iterator[bytes]:
    """openpyxl write_only 流式生成 .xlsx，再分块读回吐字节。

    write_only 模式逐行 append 直接落盘（zip 流式写），不把整表行攒在内存里；
    save 完成后按块读临时文件流式吐出，临时文件用完即删。
    客户端提前断开时生成器被 close，finally 里清理临时文件。
    """
    from openpyxl import Workbook

    workbook = Workbook(write_only=True)
    sheet = workbook.create_sheet()
    sheet.append(list(header))
    for row in rows:
        sheet.append(list(row))

    handle = tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False)
    handle.close()
    try:
        workbook.save(handle.name)
        with open(handle.name, "rb") as source:
            while chunk := source.read(chunk_size):
                yield chunk
    finally:
        workbook.close()
        os.unlink(handle.name)
