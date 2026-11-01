"""v3 第一刀：幂等台账 + 分段入库（2026-11-01）。

分三层测：
- 入参校验（pydantic）：脏分段必须 422，不许进库
- 用例层（Container 真库）：幂等三态、事务原子性、老调用兼容
- 落库细节：浮点舍入、分段顺序、详情可回读

为什么并发用例要 monkeypatch：
SQLite 单连接没法真并发。做法是让第一次 find() 假装"台账里没有"，
强制走 INSERT，再撞唯一键 → 正好走到 IntegrityError → 回查台账那条分支。
这条分支不测，"两个合并层同时重传"就会 500。
"""

import sqlite3

import pytest
from pydantic import ValidationError

from app.core.exceptions import BusinessException
from app.domain.flash.entities import FlashSegment
from app.schemas.spheroidization import SpheroidizationCreateRequest
from tests.conftest import create_standard

BASE = {
    "detection_time": "2026-11-01 09:12:27.900",
    "plc_button_time": "2026-11-01 09:12:27.900",
    "spheroidization_start_time": "2026-11-01 09:12:31.400",
    "spheroidization_end_time": "2026-11-01 09:14:06.855",
    "spheroidization_wire_entry_start_time": "2026-11-01 09:12:31.000",
    "spheroidization_wire_entry_end_time": "2026-11-01 09:17:31.000",
    "spheroidization_wire_entry_total_duration": 300.0,
    "spheroidization_weight": 1608.0,
    "actual_spheroidization_time": 95.455,
    "spheroidization_abnormal": 1,
    "abnormal_type": 5,
    "abnormal_reason": "球化过程中间亮光停顿：第 2 段前停顿 15.2s",
}

SEGMENTS = [
    {"seg_index": 1, "start_offset": 0.0, "end_offset": 40.0,
     "gap_before": None, "duration": 40.0},
    {"seg_index": 2, "start_offset": 55.2, "end_offset": 95.455,
     "gap_before": 15.2, "duration": 40.255},
]


def payload(**overrides):
    data = dict(BASE)
    data["segments"] = [dict(s) for s in SEGMENTS]
    data["device_id"] = "casting-1"
    data["external_id"] = "2042"
    data.update(overrides)
    return data


# ==========================================================
# 一、入参校验（脏数据必须在门口挡住）
# ==========================================================

class TestSegmentValidation:
    def test_合法两段通过(self):
        req = SpheroidizationCreateRequest(**payload())
        assert len(req.segments) == 2
        assert req.segments[1].gap_before == 15.2

    def test_段号断档被拒(self):
        bad = [dict(SEGMENTS[0]), dict(SEGMENTS[1], seg_index=3)]
        with pytest.raises(ValidationError, match="段号"):
            SpheroidizationCreateRequest(**payload(segments=bad))

    def test_首段带gap被拒(self):
        bad = [dict(SEGMENTS[0], gap_before=3.0), dict(SEGMENTS[1])]
        with pytest.raises(ValidationError, match="第一段"):
            SpheroidizationCreateRequest(**payload(segments=bad, abnormal_type=3))

    def test_gap与起止对不上被拒(self):
        bad = [dict(SEGMENTS[0]), dict(SEGMENTS[1], gap_before=20.0)]
        with pytest.raises(ValidationError, match="gap_before"):
            SpheroidizationCreateRequest(**payload(segments=bad))

    def test_时长与起止差对不上被拒(self):
        bad = [dict(SEGMENTS[0], duration=35.0), dict(SEGMENTS[1])]
        with pytest.raises(ValidationError, match="duration"):
            SpheroidizationCreateRequest(**payload(segments=bad))

    def test_末段与亮光跨度对不上被拒(self):
        bad = [dict(SEGMENTS[0]), dict(SEGMENTS[1], end_offset=99.0, duration=43.8)]
        with pytest.raises(ValidationError, match="跨度"):
            SpheroidizationCreateRequest(**payload(segments=bad))

    def test_首段起点必须为0(self):
        bad = [dict(SEGMENTS[0], start_offset=2.0, duration=38.0), dict(SEGMENTS[1])]
        with pytest.raises(ValidationError, match="start_offset 必须为 0"):
            SpheroidizationCreateRequest(**payload(segments=bad))

    def test_类型5幂等路径至少要2段(self):
        with pytest.raises(ValidationError, match="至少 2 段"):
            SpheroidizationCreateRequest(**payload(segments=[]))

    def test_类型5老路径允许不带分段(self):
        req = SpheroidizationCreateRequest(**payload(segments=[], device_id=None,
                                                     external_id=None))
        assert req.segments == []

    def test_幂等键必须成对(self):
        with pytest.raises(ValidationError, match="必须同时提供"):
            SpheroidizationCreateRequest(**payload(external_id=None))

    def test_单段记录合法(self):
        one = [{"seg_index": 1, "start_offset": 0.0, "end_offset": 95.455,
                "gap_before": None, "duration": 95.455}]
        req = SpheroidizationCreateRequest(**payload(segments=one, abnormal_type=3))
        assert len(req.segments) == 1


# ==========================================================
# 二、用例层：幂等 + 事务
# ==========================================================

def kwargs(**overrides):
    """用例层用的入参：不含 segments（它单独作为实体列表传）。"""
    data = payload(**overrides)
    data.pop("segments", None)
    return data


def _segments():
    return [FlashSegment(**s) for s in SEGMENTS]


def _create(container, **overrides):
    data = payload(**overrides)
    data.pop("segments")
    data.pop("device_id")
    data.pop("external_id")
    segs = overrides.pop("seg_objs", _segments())
    return container.create_spheroidization().execute_idempotent(
        **data,
        device_id=overrides.get("device_id", "casting-1"),
        external_id=overrides.get("external_id", "2042"),
        segments=segs,
    )


class TestIdempotency:
    def test_同键同内容三次只建一条(self, 有标准的容器):
        uc = 有标准的容器.create_spheroidization()
        first, e1 = uc.execute_idempotent(**kwargs(), segments=_segments())
        second, e2 = uc.execute_idempotent(**kwargs(), segments=_segments())
        third, e3 = uc.execute_idempotent(**kwargs(), segments=_segments())

        assert (e1, e2, e3) == (False, True, True)
        assert first.spheroidization_record_id == second.spheroidization_record_id
        assert second.spheroidization_record_id == third.spheroidization_record_id
        count = 有标准的容器.conn.execute(
            "SELECT COUNT(*) FROM SpheroidizationRecord"
        ).fetchone()[0]
        assert count == 1
        # 分段也不能重复写：第二次是命中，不该再插一遍
        segs = 有标准的容器.conn.execute(
            "SELECT COUNT(*) FROM FlashSegment"
        ).fetchone()[0]
        assert segs == 2

    def test_同键不同内容被拒且不覆盖(self, 有标准的容器):
        uc = 有标准的容器.create_spheroidization()
        uc.execute_idempotent(**kwargs(), segments=_segments())

        with pytest.raises(BusinessException) as exc:
            uc.execute_idempotent(
                **kwargs(spheroidization_weight=9999.0), segments=_segments()
            )
        assert exc.value.code == 409
        assert "拒绝覆盖" in exc.value.message

        row = 有标准的容器.conn.execute(
            "SELECT spheroidization_weight FROM SpheroidizationRecord"
        ).fetchone()
        assert row[0] == 1608.0  # 原数据没被动过
        assert 有标准的容器.conn.execute(
            "SELECT COUNT(*) FROM SpheroidizationRecord"
        ).fetchone()[0] == 1

    def test_并发重放撞唯一键后返回已有(self, 有标准的容器, monkeypatch):
        uc = 有标准的容器.create_spheroidization()
        uc.execute_idempotent(**kwargs(), segments=_segments())

        # 模拟"两个请求同时查台账，都以为没有"
        real_find = 有标准的容器.upload_ledger_repo.find
        calls = {"n": 0}

        def fake_find(device_id, external_id):
            calls["n"] += 1
            if calls["n"] == 1:
                return None          # 第一次假装没查到 → 走 INSERT → 撞键
            return real_find(device_id, external_id)

        monkeypatch.setattr(有标准的容器.upload_ledger_repo, "find", fake_find)
        record, existing = uc.execute_idempotent(**kwargs(), segments=_segments())

        assert existing is True
        assert record.spheroidization_record_id == 1
        assert 有标准的容器.conn.execute(
            "SELECT COUNT(*) FROM SpheroidizationRecord"
        ).fetchone()[0] == 1

    def test_分段写库后能按顺序读回(self, 有标准的容器):
        uc = 有标准的容器.create_spheroidization()
        record, _ = uc.execute_idempotent(**kwargs(), segments=_segments())

        segs = 有标准的容器.query_spheroidization().segments_for(
            record.spheroidization_record_id
        )
        assert [s.seg_index for s in segs] == [1, 2]
        assert segs[0].gap_before is None
        assert segs[1].gap_before == 15.2
        assert segs[0].start_offset == 0.0

    def test_分段写入失败时整条回滚(self, 有标准的容器, monkeypatch):
        """留半条记录比不写更糟：记录在、分段没了，类型 5 就永远没证据。"""

        def boom(*args, **kwargs):
            raise sqlite3.OperationalError("模拟写分段失败")

        monkeypatch.setattr(
            有标准的容器.flash_segment_repo, "save_many_no_commit", boom
        )
        with pytest.raises(sqlite3.OperationalError):
            有标准的容器.create_spheroidization().execute_idempotent(
                **kwargs(), segments=_segments()
            )

        conn = 有标准的容器.conn
        assert conn.execute("SELECT COUNT(*) FROM SpheroidizationRecord").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM FlashSegment").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM UploadLedger").fetchone()[0] == 0

    def test_老调用不带幂等键行为不变(self, 有标准的容器):
        data = payload()
        data.pop("segments")
        data.pop("device_id")
        data.pop("external_id")
        record = 有标准的容器.create_spheroidization().execute(**data)

        assert record.spheroidization_record_id == 1
        assert 有标准的容器.conn.execute(
            "SELECT COUNT(*) FROM UploadLedger"
        ).fetchone()[0] == 0
        # 老调用可以连传两次（没有幂等承诺，这是既有行为）
        有标准的容器.create_spheroidization().execute(**data)
        assert 有标准的容器.conn.execute(
            "SELECT COUNT(*) FROM SpheroidizationRecord"
        ).fetchone()[0] == 2

    def test_浮点统一三位落库(self, 有标准的容器):
        segs = [
            FlashSegment(seg_index=1, start_offset=0.0, end_offset=40.0,
                         gap_before=None, duration=40.0),
            FlashSegment(seg_index=2, start_offset=55.2, end_offset=95.45499999999,
                         gap_before=15.2, duration=40.25499999999),
        ]
        record, _ = 有标准的容器.create_spheroidization().execute_idempotent(
            **kwargs(), segments=segs
        )
        row = 有标准的容器.conn.execute(
            "SELECT end_offset, duration FROM FlashSegment WHERE seg_index = 2"
        ).fetchone()
        assert row[0] == 95.455
        assert row[1] == 40.255
