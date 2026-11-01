"""merge.sources.heat 单测：首次读取 / 幂等 / 重建去重 / 坏行。"""

import shutil

from pathlib import Path

from merge.sources.heat import read_new

FIXTURE = Path(__file__).parent / "fixtures" / "heat_sample.jsonl"


def _copy_to(tmp_path: Path, name: str) -> Path:
    dest = tmp_path / name
    shutil.copyfile(FIXTURE, dest)
    return dest


def test_read_once(tmp_path):
    path = _copy_to(tmp_path, "heat_records.jsonl")
    events, inode, offset = read_new(path, None)
    assert len(events) == 4
    assert all(e["kind"] == "heat" for e in events)
    assert all(e["fp"] for e in events)
    assert len({e["fp"] for e in events}) == 4
    assert inode > 0 and offset == path.stat().st_size


def test_idempotent(tmp_path):
    path = _copy_to(tmp_path, "heat_records.jsonl")
    events, inode, offset = read_new(path, None)
    assert len(events) == 4
    again, inode2, offset2 = read_new(path, (inode, offset))
    assert again == []
    assert (inode2, offset2) == (inode, offset)


def test_rescan_dedupe(tmp_path):
    path = _copy_to(tmp_path, "heat_records.jsonl")
    events, inode, offset = read_new(path, None)
    seen = {e["fp"] for e in events if e["kind"] == "heat"}

    # 模拟文件被替换（新 inode）：从头重扫，靠 fp 去重
    new_path = _copy_to(tmp_path, "heat_records2.jsonl")
    events2, inode2, _ = read_new(new_path, (inode, offset))
    assert inode2 != inode
    fresh = [e for e in events2 if e["kind"] == "heat"]
    assert len(fresh) == 4
    assert len({e["fp"] for e in fresh} & seen) == len(fresh)  # 全部是老指纹
    # 若上游只认新 fp，去重后应剩 0 条
    deduped = [e for e in fresh if e["fp"] not in seen]
    assert deduped == []


def test_bad_line(tmp_path):
    path = _copy_to(tmp_path, "heat_records.jsonl")
    events, inode, offset = read_new(path, None)
    assert len(events) == 4

    with open(path, "a", encoding="utf-8") as fh:
        fh.write('{"reaction_count": 999, "detection_time": oops\n')
    again, inode2, offset2 = read_new(path, (inode, offset))
    assert len(again) == 1
    assert again[0]["kind"] == "bad"
    assert "oops" in again[0]["raw"]
    assert offset2 > offset


def test_abnormal_normalize():
    """反向映射回归：成功=0（正常），失败=1（异常）。"""
    from merge.sources.heat import _abnormal, _abnormal_type

    assert _abnormal("成功") == 0
    assert _abnormal("失败") == 1
    assert _abnormal("未判定") is None
    assert _abnormal(0) == 0 and _abnormal(1) == 1
    assert _abnormal("奇怪值") is None
    assert _abnormal_type("3") == 3
    assert _abnormal_type(None) == 0
