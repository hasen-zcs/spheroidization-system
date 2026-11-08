"""TASK-11 验收：写 SQL 从 API 层下沉到仓储 + 用例后行为不变。

覆盖任务书 E 节最小集：
- 仓储层 soft_delete 真删 True / 再删 False
- 仓储层 restore 真恢复 True / 未删 False
- get_by_id_including_deleted 能取到已删行，get_by_id 取不到
- 用例 soft_delete 当前生效标准 → 抛 BusinessException(400)
- 用例 set_processed 0↔1，by/at 随 CHECK 变化
- API 层删 SQL 后行为不变：删除 → 404 → 恢复（走 TestClient 全链路）
"""

import sqlite3

import pytest
from fastapi.testclient import TestClient

from app.core.exceptions import BusinessException
from app.dependencies import Container, get_container
from app.infrastructure.database.connection import create_tables
from app.infrastructure.state.active_standard import JsonStandardApplicationState
from app.main import app

from tests.conftest import create_record, create_standard, create_user


# ============================================================
# 仓储层
# ============================================================

def test_仓储软删真删True再删False(有记录的容器):
    repo = 有记录的容器.spheroid_repo
    rid = repo.list_all()[0].spheroidization_record_id

    assert repo.soft_delete(rid, "root", "误录") is True
    # 已删：再删应返回 False（幂等，不重复置值）
    assert repo.soft_delete(rid, "root", "再删") is False
    # 不存在的行：返回 False
    assert repo.soft_delete(99999, "root", "x") is False


def test_仓储恢复真恢复True未删False(有记录的容器):
    repo = 有记录的容器.spheroid_repo
    rid = repo.list_all()[0].spheroidization_record_id

    # 未删的行：恢复应返回 False（本来就没删）
    assert repo.restore(rid) is False
    repo.soft_delete(rid, "root", "误录")
    # 已删：恢复真恢复，返回 True
    assert repo.restore(rid) is True
    # 恢复后再恢复：返回 False
    assert repo.restore(rid) is False


def test_including_deleted能取到已删行而get_by_id取不到(有记录的容器):
    repo = 有记录的容器.spheroid_repo
    rid = repo.list_all()[0].spheroidization_record_id

    # 未删时两个都能取到
    assert repo.get_by_id(rid) is not None
    assert repo.get_by_id_including_deleted(rid) is not None

    repo.soft_delete(rid, "root", "误录")
    # 已删：get_by_id 视为不存在，including_deleted 仍能取到
    assert repo.get_by_id(rid) is None
    deleted = repo.get_by_id_including_deleted(rid)
    assert deleted is not None
    assert deleted.deleted_by == "root"
    assert deleted.delete_reason == "误录"
    assert deleted.deleted_at is not None


# ============================================================
# 用例层
# ============================================================

def test_用例软删当前生效标准抛400(有标准的容器):
    uc = 有标准的容器.manage_data()
    current_id = 有标准的容器.query_standard().get_current().standard_record_id

    with pytest.raises(BusinessException) as exc:
        uc.soft_delete("standard", current_id, "root", "想删当前标准")
    assert exc.value.code == 400
    # 库没动：当前标准仍不是已删
    assert 有标准的容器.standard_repo.get_by_id_including_deleted(
        current_id
    ).deleted_at is None


def test_用例set_processed零一往返且by_at随check变化(有记录的容器):
    uc = 有记录的容器.manage_data()
    repo = 有记录的容器.spheroid_repo
    rid = repo.list_all()[0].spheroidization_record_id

    r1 = uc.set_processed(rid, 1, "root")
    assert r1.status == "created"
    assert r1.before["processed"] == 0 and r1.before["processed_by"] is None
    assert r1.after["processed"] == 1
    assert r1.after["processed_by"] == "root"
    assert r1.after["processed_at"] is not None

    r0 = uc.set_processed(rid, 0, "root")
    assert r0.status == "created"
    assert r0.before["processed"] == 1
    assert r0.after["processed"] == 0
    assert r0.after["processed_by"] is None
    assert r0.after["processed_at"] is None


# ============================================================
# API 层：删 SQL 后行为不变（删除 → 404 → 恢复）
# ============================================================

@pytest.fixture
def env(tmp_path):
    """空库 + 容器 + TestClient：超管 + 两条标准 + 一条异常记录。"""
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    create_tables(conn)
    container = Container(
        conn=conn,
        standard_application_state=JsonStandardApplicationState(
            tmp_path / "active_standard.json"
        ),
    )
    app.dependency_overrides[get_container] = lambda: container
    with TestClient(app) as client:
        create_user(container, "root", is_admin=True)
        create_standard(container, 65.0, "root", remark="初始")
        create_standard(container, 70.0, "root", remark="调整")
        rec = create_record(container, "2026-11-03 08:00:00", 70.0, abnormal=1)
        yield client, container, rec
    app.dependency_overrides.clear()
    conn.close()


def _login(client, username, password="pass1234"):
    token = client.post(
        "/api/users/login",
        json={"username": username, "password": password},
    ).json()["data"]["token"]
    return {"Authorization": f"Bearer {token}"}


def test_api删SQL后删除恢复行为不变(env):
    client, container, rec = env
    headers = _login(client, "root")
    rid = rec.spheroidization_record_id

    # 删：成功
    assert client.post(
        f"/api/admin/records/{rid}/delete", json={"reason": "误录"}, headers=headers
    ).json()["code"] == 200
    # 软删后详情 404、列表不含
    assert client.get(f"/api/spheroidization/{rid}", headers=headers).json()["code"] == 404
    assert client.get("/api/spheroidization", headers=headers).json()["data"]["total"] == 0

    # 再删：幂等成功，不报 404
    assert client.post(
        f"/api/admin/records/{rid}/delete", json={"reason": "再删"}, headers=headers
    ).json()["code"] == 200
    # 不存在的 id：404
    assert client.post(
        "/api/admin/records/99999/delete", json={"reason": "x"}, headers=headers
    ).json()["code"] == 404

    # 恢复：成功，记录回来
    assert client.post(
        f"/api/admin/records/{rid}/restore", json={}, headers=headers
    ).json()["code"] == 200
    assert client.get("/api/spheroidization", headers=headers).json()["data"]["total"] == 1
    # 未删再恢复：幂等成功
    assert client.post(
        f"/api/admin/records/{rid}/restore", json={}, headers=headers
    ).json()["code"] == 200
