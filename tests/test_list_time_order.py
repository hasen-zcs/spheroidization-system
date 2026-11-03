"""TASK-6：球化记录列表按检测时间自动排序。

背景：11-03 补录了检测时间更早的炉次（主键大、检测时间小），
按主键排会让补录的旧记录顶在列表最前，"表是乱的"。
现在三条查询路径统一按 detection_time 排序，主键做次级排序键：

    list_page     detection_time DESC, pk DESC   （分页列表，最新在前）
    list_abnormal detection_time DESC, pk DESC   （异常页，与分页列表一致）
    list_all      detection_time ASC,  pk ASC    （CSV 导出/全量拉取，时间正序）

用例直接打在仓储层（SqliteSpheroidizationRepository），
模拟补录场景：先插 3 条 11-03 的，再插 2 条 10-30 / 11-02 的。
"""

import pytest

from app.domain.spheroidization.entities import SpheroidizationRecord
from app.domain.standard.entities import StandardRecord
from app.infrastructure.database.sqlite import (
    SqliteSpheroidizationRepository,
    SqliteStandardRepository,
)


def _make_record(detection_time, abnormal=None):
    """造一条球化记录，只关心 detection_time 和异常标记。"""
    return SpheroidizationRecord(
        standard_record_id=1,
        detection_time=detection_time,
        spheroidization_start_time="2026-11-03 08:00:05.000",
        spheroidization_end_time="2026-11-03 08:01:10.000",
        actual_spheroidization_time=65.0,
        spheroidization_wire_entry_start_time="2026-11-03 08:00:20.000",
        spheroidization_weight=1600.0,
        standard_spheroidization_time=70.0,
        spheroidization_abnormal=abnormal,
    )


@pytest.fixture
def repo(连接):
    """球化仓储，直接拿 conftest 给的干净连接。

    先建一条标准：球化表的 standard_record_id 有外键，没标准插不进记录。
    """
    SqliteStandardRepository(连接).save(
        StandardRecord(
            standard_spheroidization_time=70.0,
            weighing_standard=1500.0,
            created_by="张三",
        )
    )
    return SqliteSpheroidizationRepository(连接)


@pytest.fixture
def backfill_repo(repo):
    """模拟补录：先插 3 条 11-03 的（id 1-3），再补 2 条更早日期的（id 4-5）。

    主键顺序 = 入库顺序；检测时间顺序跟它交叉，正是线上出问题的形状。
    """
    repo.save(_make_record("2026-11-03 08:00:00.000"))   # id 1
    repo.save(_make_record("2026-11-03 09:00:00.000"))   # id 2
    repo.save(_make_record("2026-11-03 10:00:00.000"))   # id 3
    repo.save(_make_record("2026-10-30 10:00:00.000"))   # id 4 补录
    repo.save(_make_record("2026-11-02 10:00:00.000"))   # id 5 补录
    return repo


def test_list_page第1页按检测时间降序_补录旧记录不顶在最前(backfill_repo):
    page1 = backfill_repo.list_page(offset=0, limit=5)
    ids = [r.spheroidization_record_id for r in page1]
    assert ids == [3, 2, 1, 5, 4]
    # 关键断言：补录的 10-30 / 11-02 记录（id 4、5）不得出现在 11-03 记录之前
    first_three = ids[:3]
    assert set(first_three) == {1, 2, 3}
    assert ids.index(4) > 2 and ids.index(5) > 2


def test_list_page翻页不漂移(backfill_repo):
    page1 = backfill_repo.list_page(offset=0, limit=3)
    page2 = backfill_repo.list_page(offset=3, limit=3)
    ids = [r.spheroidization_record_id for r in page1 + page2]
    # 两页拼起来正好是全部 5 条，不重不漏，顺序是时间降序
    assert ids == [3, 2, 1, 5, 4]


def test_同一检测时间按主键降序稳定(repo):
    repo.save(_make_record("2026-11-03 08:00:00.000"))   # id 1
    repo.save(_make_record("2026-11-03 08:00:00.000"))   # id 2
    page = repo.list_page(offset=0, limit=10)
    assert [r.spheroidization_record_id for r in page] == [2, 1]
    # list_all 同一时刻按主键升序兜底
    assert [r.spheroidization_record_id for r in repo.list_all()] == [1, 2]


def test_list_abnormal按检测时间降序(repo):
    repo.save(_make_record("2026-11-03 10:00:00.000", abnormal=1))   # id 1
    repo.save(_make_record("2026-10-30 10:00:00.000", abnormal=1))   # id 2 补录
    repo.save(_make_record("2026-11-02 10:00:00.000", abnormal=1))   # id 3
    # 混进一条正常的，确认筛选不受排序改动影响
    repo.save(_make_record("2026-11-03 11:00:00.000", abnormal=0))
    abnormal = repo.list_abnormal()
    assert [r.spheroidization_record_id for r in abnormal] == [1, 3, 2]


def test_list_all按检测时间升序(backfill_repo):
    all_ids = [r.spheroidization_record_id for r in backfill_repo.list_all()]
    # 导出惯例：时间正序，补录的旧记录沉在最前面而不是最后面
    assert all_ids == [4, 5, 1, 2, 3]
