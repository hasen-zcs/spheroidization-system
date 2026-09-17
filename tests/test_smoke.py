"""功能完整性测试：7 个 UseCase 的全部方法 + 数据库层的约束。

跑法：

    pytest

不经过 FastAPI，也不碰 data/spheroidization.db。
用的是真实 SQLite（每个测试一个临时空库，见 conftest.py），
走的是 dependencies.Container 那条链路——也就是 API 层真正在走的那条。

只管"业务规则有没有生效"。接口层的东西在 tests/e2e_test.py 里，那个要先把服务起起来：

    .venv/Scripts/python.exe -m uvicorn app.main:app --port 8000
    .venv/Scripts/python.exe tests/e2e_test.py
"""

import sqlite3

import pytest

from app.core.exceptions import BusinessException


class Test检测标准:
    """标准只增不改：每建一条，它立即成为当前有效标准，历史全部保留。"""

    def test_没有标准时当前标准是空的(self, 空容器):
        assert 空容器.query_standard().get_current() is None

    def test_没有标准时历史是空列表(self, 空容器):
        assert 空容器.query_standard().get_history() == []

    def test_主键由数据库自增分配(self, 空容器):
        s1 = 空容器.create_standard().execute(65.0, 125.0, 1500.0, "张三", "初始标准")
        s2 = 空容器.create_standard().execute(70.0, 130.0, 1500.0, "李四", "调整")
        assert (s1.standard_record_id, s2.standard_record_id) == (1, 2)

    def test_创建时间由实现方生成(self, 空容器):
        s = 空容器.create_standard().execute(65.0, 125.0, 1500.0, "张三", "初始标准")
        assert isinstance(s.created_at, str)

    def test_当前标准是最新创建的那条(self, 有标准的容器):
        assert 有标准的容器.query_standard().get_current().standard_record_id == 2

    def test_历史标准全部保留(self, 有标准的容器):
        历史 = [x.standard_record_id for x in 有标准的容器.query_standard().get_history()]
        assert 历史 == [1, 2]


class Test球化检测记录:
    def test_主键由数据库自增分配(self, 有记录的容器):
        ids = [x.spheroidization_record_id for x in 有记录的容器.query_spheroidization().list_all()]
        assert ids == [1, 2, 3]

    def test_球化时长快照取自当前标准(self, 有记录的容器):
        r1 = 有记录的容器.query_spheroidization().get_by_id(1)
        assert r1.standard_spheroidization_time == 70.0

    def test_溯源的standard_record_id指向当时的标准(self, 有记录的容器):
        assert 有记录的容器.query_spheroidization().get_by_id(1).standard_record_id == 2

    def test_检测时间是字符串(self, 有记录的容器):
        r1 = 有记录的容器.query_spheroidization().get_by_id(1)
        assert isinstance(r1.detection_time, str)

    def test_新建记录一律未处理(self, 有记录的容器):
        r1 = 有记录的容器.query_spheroidization().get_by_id(1)
        assert (r1.processed, r1.processed_at, r1.processed_by) == (0, None, None)

    def test_机器没给判定时字段留空(self, 有记录的容器):
        r3 = 有记录的容器.query_spheroidization().get_by_id(3)
        assert r3.spheroidization_abnormal is None

    def test_异常列表只返回标记为异常的(self, 有记录的容器):
        ids = [
            x.spheroidization_record_id
            for x in 有记录的容器.query_spheroidization().list_abnormal()
        ]
        assert ids == [2]

    def test_查不存在的记录返回空(self, 有记录的容器):
        assert 有记录的容器.query_spheroidization().get_by_id(9999) is None


class Test人工处置:
    """处置不可逆：一条记录只能处理一次，重复处理报错且不覆盖原处理人。"""

    def test_处置后状态和处理人落盘(self, 有记录的容器):
        p = 有记录的容器.process_spheroidization().execute(1, "王五")
        assert (p.processed, p.processed_by) == (1, "王五")

    def test_处理时间由实现方生成(self, 有记录的容器):
        p = 有记录的容器.process_spheroidization().execute(1, "王五")
        assert isinstance(p.processed_at, str)

    def test_处置不改动机器检测事实(self, 有记录的容器):
        p = 有记录的容器.process_spheroidization().execute(1, "王五")
        assert p.detection_time == "2026-09-05 08:30:15"

    def test_重复处置被拦住(self, 有记录的容器):
        c = 有记录的容器
        c.process_spheroidization().execute(1, "王五")
        with pytest.raises(BusinessException):
            c.process_spheroidization().execute(1, "赵六")

    def test_被拒绝后原处理人没被覆盖(self, 有记录的容器):
        c = 有记录的容器
        c.process_spheroidization().execute(1, "王五")
        with pytest.raises(BusinessException):
            c.process_spheroidization().execute(1, "赵六")
        assert c.query_spheroidization().get_by_id(1).processed_by == "王五"

    def test_处置不存在的记录被拦住(self, 有记录的容器):
        with pytest.raises(BusinessException):
            有记录的容器.process_spheroidization().execute(9999, "王五")


class Test人工复核:
    """复核只追加：一条记录可以复核多次，复核不改机器结果、不改处置状态。"""

    def test_主键自增且结果存整数(self, 有记录的容器):
        v = 有记录的容器.create_review().execute(2, 0, "李四", "人工确认正常")
        assert (v.review_record_id, v.review_result) == (1, 0)
        assert isinstance(v.reviewed_at, str)

    def test_同一条记录可以有多条复核(self, 有记录的容器):
        c = 有记录的容器
        c.create_review().execute(2, 0, "李四", "人工确认正常")
        c.create_review().execute(2, 1, "王五", "二次复核认为异常")
        assert [x.review_record_id for x in c.query_review().execute(2)] == [1, 2]

    def test_没有复核的记录返回空列表(self, 有记录的容器):
        assert 有记录的容器.query_review().execute(3) == []

    def test_给不存在的记录提交复核被拦住(self, 有记录的容器):
        with pytest.raises(BusinessException):
            有记录的容器.create_review().execute(9999, 0, "李四")

    def test_复核不改变处置状态(self, 有记录的容器):
        c = 有记录的容器
        c.create_review().execute(2, 1, "王五", "认为异常")
        r = c.query_spheroidization().get_by_id(2)
        assert (r.processed, r.spheroidization_abnormal) == (0, 1)


class Test数据库层约束:
    """这些规则靠 schema.sql 保证，不靠 Python 代码。"""

    def test_外键开关真的打开了(self, 连接):
        # SQLite 默认是关的，connection.py 里显式 PRAGMA 打开了，这里验一下
        assert 连接.execute("PRAGMA foreign_keys").fetchone()[0] == 1

    def test_删掉被球化记录引用的标准被拦住(self, 有记录的容器, 连接):
        # 三条记录的快照都取自标准 2，所以删 2 会被 ON DELETE RESTRICT 拦下
        with pytest.raises(sqlite3.IntegrityError):
            连接.execute("DELETE FROM StandardRecord WHERE standard_record_id = 2")

    def test_幽灵数据被CHECK拦住(self, 有记录的容器, 连接):
        # 状态是"未处理"，却带着处理人——不该存在的行
        with pytest.raises(sqlite3.IntegrityError):
            连接.execute(
                "INSERT INTO SpheroidizationRecord (standard_record_id, detection_time, "
                "spheroidization_start_time, spheroidization_end_time, "
                "standard_spheroidization_time, processed, processed_by) "
                "VALUES (1, '2026-01-01 00:00:00', '2026-01-01 00:00:01', "
                "'2026-01-01 00:00:02', 70.0, 0, '张三')"
            )

    def test_球化时长超出65到75被CHECK拦住(self, 空容器, 连接):
        with pytest.raises(sqlite3.IntegrityError):
            连接.execute(
                "INSERT INTO StandardRecord (standard_spheroidization_time, standard_entry_length, "
                "weighing_standard, created_at, created_by) "
                "VALUES (99.0, 130.0, 1500.0, '2026-01-01 00:00:00', '张三')"
            )

    def test_没人引用的标准可以正常删除(self, 有标准的容器, 连接):
        # 上一条验的是"拦住"，这条验 RESTRICT 不是一刀切禁止删除。
        # 现建一条再删，不蹭别的测试的数据。
        待删 = 有标准的容器.create_standard().execute(68.0, 128.0, 1500.0, "张三", "待删")
        连接.execute(
            f"DELETE FROM StandardRecord WHERE standard_record_id = {待删.standard_record_id}"
        )
        剩 = 连接.execute(
            "SELECT COUNT(*) FROM StandardRecord WHERE standard_record_id = ?",
            (待删.standard_record_id,),
        ).fetchone()[0]
        assert 剩 == 0
