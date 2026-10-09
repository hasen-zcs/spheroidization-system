"""功能完整性测试：7 个 UseCase 的全部方法 + 数据库层的约束。

跑法：

    pytest

不经过 FastAPI，也不碰 data/spheroidization.db。
用的是真实 SQLite（每个测试一个临时空库，见 conftest.py），
走的是 dependencies.Container 那条链路——也就是 API 层真正在走的那条。

只管"业务规则有没有生效"。接口层的东西在 tests/e2e_test.py 里，那个要先把服务起起来。
本文件和 conftest.py 是**可以安全跑**的那一半：每个用例一个临时空库，碰不到真实数据。
e2e_test.py / check_db_connection.py 不是——它们往真库写数据，所以没随交付包一起发。
"""

import base64
import sqlite3

import pytest
from pydantic import ValidationError

from app.core.exceptions import BusinessException
from app.dependencies import Container
from app.infrastructure.state.active_standard import JsonStandardApplicationState
from app.schemas.spheroidization import SpheroidizationCreateRequest, to_response
from conftest import create_record, create_standard


def insert_record_raw(conn, **overrides):
    """直接往球化记录表插一行，绕过 UseCase，用来试数据库自己的约束。

    表上 12 个 NOT NULL 列在这里填齐固定值，用例只覆盖它要考的那一列。
    不这么做的话会先被 NOT NULL 拦下，测到的就不是想考的那条约束了。
    想把某列留空就把它覆盖成 None。
    """
    values = {
        "standard_record_id": 1,
        "detection_time": "2026-01-01 00:00:00",
        "spheroidization_start_time": "2026-01-01 00:00:01",
        "spheroidization_end_time": "2026-01-01 00:00:02",
        "actual_spheroidization_time": 65.0,
        "standard_spheroidization_time": 70.0,
        "spheroidization_temperature": 1520.0,
        "spheroidization_temperature_time": "2026-01-01 00:00:03",
        "spheroidization_wire_entry_start_time": "2026-01-01 00:00:04",
        "spheroidization_wire_entry_end_time": "2026-01-01 00:00:05",
        "spheroidization_wire_entry_total_duration": 80.0,
        "spheroidization_weight": 1608.0,
    }
    values.update(overrides)
    columns = ", ".join(values)
    placeholders = ", ".join("?" * len(values))
    conn.execute(
        f"INSERT INTO SpheroidizationRecord ({columns}) VALUES ({placeholders})",
        list(values.values()),
    )


class Test检测标准:
    """标准只增不改：每建一条，它立即成为当前有效标准，历史全部保留。"""

    def test_没有标准时当前标准是空的(self, 空容器):
        assert 空容器.query_standard().get_current() is None

    def test_没有标准时历史是空列表(self, 空容器):
        assert 空容器.query_standard().get_history() == []

    def test_主键由数据库自增分配(self, 空容器):
        s1 = create_standard(空容器, 65.0, "张三", remark="初始标准")
        s2 = create_standard(空容器, 70.0, "李四", remark="调整")
        assert (s1.standard_record_id, s2.standard_record_id) == (1, 2)

    def test_创建时间由实现方生成(self, 空容器):
        s = create_standard(空容器, 65.0, "张三", remark="初始标准")
        assert isinstance(s.created_at, str)

    def test_当前标准是最新创建的那条(self, 有标准的容器):
        assert 有标准的容器.query_standard().get_current().standard_record_id == 2

    def test_历史标准全部保留(self, 有标准的容器):
        历史 = [x.standard_record_id for x in 有标准的容器.query_standard().get_history()]
        assert 历史 == [1, 2]


class Test标准应用状态:
    def test_应用旧标准后当前标准立即变化(self, 有标准的容器):
        c = 有标准的容器
        c.apply_standard().execute(1)
        assert c.query_standard().get_current().standard_record_id == 1

    def test_应用状态在重建容器后仍然保留(self, 有标准的容器):
        c = 有标准的容器
        c.apply_standard().execute(1)
        state_path = c.standard_application_state.path

        restarted = Container(
            conn=c.conn,
            standard_application_state=JsonStandardApplicationState(state_path),
        )
        assert restarted.query_standard().get_current().standard_record_id == 1

    def test_应用不存在的标准被拒绝(self, 有标准的容器):
        with pytest.raises(BusinessException):
            有标准的容器.apply_standard().execute(9999)

    def test_新建标准会自动成为当前应用标准(self, 空容器):
        standard = create_standard(空容器, 70.0, "张三")
        application = 空容器.standard_application_state.load()
        assert application.standard_record_id == standard.standard_record_id


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

    def test_新增的物性字段原样落盘(self, 有记录的容器):
        # 2026-09 新增的列，本系统只存储不做运算，所以验的就是"原样"
        r1 = 有记录的容器.query_spheroidization().get_by_id(1)
        assert r1.spheroidization_temperature == 1520.0
        assert r1.spheroidization_temperature_time == "2026-09-05 08:30:22"
        assert r1.spheroidization_wire_entry_start_time == "2026-09-05 08:30:40"
        assert r1.spheroidization_wire_entry_end_time == "2026-09-05 08:32:00"
        assert r1.spheroidization_wire_entry_total_duration == 80.0
        assert r1.spheroidization_weight == 1608.0

    def test_没传图片时是None(self, 有记录的容器):
        r1 = 有记录的容器.query_spheroidization().get_by_id(1)
        assert r1.spheroidization_image is None

    def test_图片按字节原样存取(self, 有标准的容器):
        # 用 0x00~0xFF 全字节序列，专治 base64 / 编码转换引入的偏差
        blob = bytes(range(256))
        created = create_record(
            有标准的容器,
            "2026-09-05 11:00:00",
            65.0,
            abnormal=0,
            spheroidization_image=blob,
        )
        read_back = 有标准的容器.query_spheroidization().get_by_id(
            created.spheroidization_record_id
        )
        assert read_back.spheroidization_image == blob


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


class Test图片编解码:
    """图片在 JSON 里是 base64 字符串，在库里是 BLOB，转换点在 schemas 层。

    这组测试单独立出来，是因为接口自测看不见这个问题：如果编解码两头都漏了，
    进来是文本字节、出去还是同一段文本字节，请求和响应照样"对得上"，
    只有直查数据库才发现存的根本不是图。e2e 里那条对账就是这么抓出来的。
    """

    # 请求体的骨架，只留必填项，各用例按需覆盖
    @staticmethod
    def _请求体(**overrides):
        body = {
            "detection_time": "2026-09-05 08:30:15",
            "spheroidization_start_time": "2026-09-05 08:30:20",
            "spheroidization_end_time": "2026-09-05 08:31:25",
            "actual_spheroidization_time": 65.0,
            "spheroidization_temperature": 1520.0,
            "spheroidization_temperature_time": "2026-09-05 08:30:22",
            "spheroidization_wire_entry_start_time": "2026-09-05 08:30:40",
            "spheroidization_wire_entry_end_time": "2026-09-05 08:32:00",
            "spheroidization_wire_entry_total_duration": 80.0,
            "spheroidization_weight": 1608.0,
        }
        body.update(overrides)
        return body

    def test_base64字符串解码成原始字节(self):
        # 用 0x00~0xFF 全字节序列：UTF-8 编解码、base64 往返，哪里出偏差都会露馅
        blob = bytes(range(256))
        req = SpheroidizationCreateRequest(
            **self._请求体(spheroidization_image=base64.b64encode(blob).decode())
        )
        assert req.spheroidization_image == blob

    def test_不传图片时是None(self):
        assert SpheroidizationCreateRequest(**self._请求体()).spheroidization_image is None

    def test_坏base64当场被拒(self):
        # 宁可 422 也不能存进去一张悄悄坏掉的图——本系统只存不处理，事后没人查得出来
        with pytest.raises(ValidationError):
            SpheroidizationCreateRequest(**self._请求体(spheroidization_image="这不是base64!!!"))

    def test_折过行的base64也能收(self):
        # MIME 那种按行折的 base64，换行要先去掉再解码
        blob = bytes(range(256))
        text = base64.b64encode(blob).decode()
        req = SpheroidizationCreateRequest(
            **self._请求体(spheroidization_image="\n".join(
                text[i : i + 60] for i in range(0, len(text), 60)
            ))
        )
        assert req.spheroidization_image == blob

    def test_详情响应把字节编回base64(self, 有记录的容器):
        blob = bytes(range(256))
        created = create_record(
            有记录的容器, "2026-09-05 12:00:00", 65.0, abnormal=0,
            spheroidization_image=blob,
        )
        record = 有记录的容器.query_spheroidization().get_by_id(
            created.spheroidization_record_id
        )
        assert to_response(record, with_image=True)["spheroidization_image"] == (
            base64.b64encode(blob).decode()
        )

    def test_列表响应默认不带图片字段(self, 有记录的容器):
        record = 有记录的容器.query_spheroidization().get_by_id(1)
        # 不是"值为 None"，是整个键都不该出现
        assert "spheroidization_image" not in to_response(record)


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
        # 状态和事实对不上，两个方向都要拦。只拦一边等于没拦：
        # 不拦"未处理却有处理人"，处置时间就会被悄悄写进去；
        # 不拦"已处理却没处理时间"，统计"本月处理了多少条"就会算错。
        with pytest.raises(sqlite3.IntegrityError, match="CHECK"):
            insert_record_raw(连接, processed=0, processed_by="张三")  # 未处理，却有处理人
        with pytest.raises(sqlite3.IntegrityError, match="CHECK"):
            insert_record_raw(连接, processed=1, processed_by="张三")  # 已处理，却没处理时间

    def test_机器判定只能存0或1(self, 有记录的容器, 连接):
        # 0 正常 / 1 异常，存 2 说明上游传了脏数据。
        # match 里点名是哪条 CHECK：这张表上有三条 CHECK，
        # 只写 match="CHECK" 的话换一条约束触发也会通过。
        with pytest.raises(sqlite3.IntegrityError, match="spheroidization_abnormal IN"):
            insert_record_raw(连接, spheroidization_abnormal=2)

    def test_处置状态只能存0或1(self, 有记录的容器, 连接):
        with pytest.raises(sqlite3.IntegrityError, match="processed IN"):
            insert_record_raw(连接, processed=2)

    def test_复核结果只能存0或1(self, 有记录的容器, 连接):
        # 球化记录 1 是 有记录的容器 建好的，外键能过，考的就是这条 CHECK
        with pytest.raises(sqlite3.IntegrityError, match="review_result IN"):
            连接.execute(
                "INSERT INTO ReviewRecord (spheroidization_record_id, review_result, "
                "reviewer, reviewed_at) VALUES (1, 2, '张三', '2026-01-01 00:00:00')"
            )

    def test_复核挂在不存在的记录上被拦住(self, 有记录的容器, 连接):
        # 复核表的外键之前没有测试（只测了球化记录那条）。
        # 挂到 9999 上应该报外键失败——Constraint 和 FOREIGN KEY 都是
        # IntegrityError，所以必须点名匹配 "FOREIGN KEY"，否则换个原因失败也会通过。
        with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY"):
            连接.execute(
                "INSERT INTO ReviewRecord (spheroidization_record_id, review_result, "
                "reviewer, reviewed_at) VALUES (9999, 0, '张三', '2026-01-01 00:00:00')"
            )

    def test_必填列留空被拦住(self, 有记录的容器, 连接):
        # 12 个 NOT NULL 列只测一个：NOT NULL 是逐列生效的，
        # 十二条全测一遍不会多出任何信息。
        with pytest.raises(sqlite3.IntegrityError, match="NOT NULL"):
            insert_record_raw(连接, detection_time=None)

    def test_球化时长非正数被CHECK拦住(self, 空容器, 连接):
        # 2026-09 起范围从写死的 65~75 放宽成"> 0"，
        # 上下限改由 standard_spheroidization_time_upper / _lower 两列表达。
        with pytest.raises(sqlite3.IntegrityError, match="CHECK"):
            连接.execute(
                "INSERT INTO StandardRecord (standard_spheroidization_time, "
                "weighing_standard, created_at, created_by) "
                "VALUES (0.0, 1500.0, '2026-01-01 00:00:00', '张三')"
            )

    def test_球化时长放宽后76是允许的(self, 空容器, 连接):
        # 同样的语句，旧的 65~75 约束会拒 76.0，新的 >0 约束放行。
        # 这条测试是用来钉住"放宽是有意的"，别哪天又被改回去。
        连接.execute(
            "INSERT INTO StandardRecord (standard_spheroidization_time, "
            "weighing_standard, created_at, created_by) "
            "VALUES (76.0, 1500.0, '2026-01-01 00:00:00', '张三')"
        )
        assert 连接.execute(
            "SELECT COUNT(*) FROM StandardRecord "
            " WHERE standard_spheroidization_time = 76.0"
        ).fetchone()[0] == 1

    def test_没人引用的标准可以正常删除(self, 有标准的容器, 连接):
        # 上一条验的是"拦住"，这条验 RESTRICT 不是一刀切禁止删除。
        # 现建一条再删，不蹭别的测试的数据。
        待删 = create_standard(有标准的容器, 68.0, "张三", remark="待删")
        连接.execute(
            f"DELETE FROM StandardRecord WHERE standard_record_id = {待删.standard_record_id}"
        )
        剩 = 连接.execute(
            "SELECT COUNT(*) FROM StandardRecord WHERE standard_record_id = ?",
            (待删.standard_record_id,),
        ).fetchone()[0]
        assert 剩 == 0

    def test_删除中间标准后新标准ID不重叠(self, 空容器, 连接):
        create_standard(空容器, 65.0, "张三")
        create_standard(空容器, 66.0, "李四")
        create_standard(空容器, 67.0, "王五")
        连接.execute("DELETE FROM StandardRecord WHERE standard_record_id = 2")

        created = create_standard(空容器, 68.0, "赵六")
        assert created.standard_record_id == 4

    def test_删除最后一条标准后下一条复用该ID(self, 空容器, 连接):
        create_standard(空容器, 65.0, "张三")
        create_standard(空容器, 66.0, "李四")
        create_standard(空容器, 67.0, "王五")
        连接.execute("DELETE FROM StandardRecord WHERE standard_record_id = 3")

        created = create_standard(空容器, 68.0, "赵六")
        assert created.standard_record_id == 3

    def test_删除最后一条球化记录后下一条复用该ID(self, 有记录的容器, 连接):
        连接.execute(
            "DELETE FROM SpheroidizationRecord WHERE spheroidization_record_id = 3"
        )
        created = create_record(
            有记录的容器,
            "2026-09-27 12:00:00",
            65.0,
            abnormal=0,
        )
        assert created.spheroidization_record_id == 3

    def test_删除最后一条复核后下一条复用该ID(self, 有记录的容器, 连接):
        c = 有记录的容器
        c.create_review().execute(1, 0, "张三", "第一条")
        c.create_review().execute(1, 1, "李四", "第二条")
        连接.execute("DELETE FROM ReviewRecord WHERE review_record_id = 2")
        created = c.create_review().execute(1, 0, "王五", "第三条")
        assert created.review_record_id == 2

    def test_三张表的序列同步触发器都存在(self, 连接):
        names = {
            row[0]
            for row in 连接.execute(
                "SELECT name FROM sqlite_master WHERE type = 'trigger'"
            )
        }
        assert {
            "standard_sync_sequence",
            "spheroidization_sync_sequence",
            "review_sync_sequence",
        } <= names
