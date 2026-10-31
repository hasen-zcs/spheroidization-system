"""pytest 的公共夹具（conftest.py 是 pytest 的约定文件名，不用手动 import）。

每个测试函数拿到的都是**一个全新的空库**——pytest 给的 tmp_path，跑完自动清理。
所以测试之间互不干扰，也不会碰到 data/spheroidization.db 里你自己的数据。

夹具是层层叠上去的，后面的在前面基础上多建一点数据：

    连接          空库 + 一条连接
    空容器        空库 + 装配好的 Container（走的是 API 层同一条链路）
    有标准的容器   在空容器上先建好 2 条标准，当前生效的是第 2 条
    有记录的容器   再有 3 条球化记录：第 1 条正常、第 2 条异常、第 3 条机器没给判定

测试要什么就从后往前挑最靠后的那个，比如测处置就只要 有记录的容器。

下面两个 create_xxx() 是给测试用的构造函数：只传关心的字段，其余给固定值。
球化记录表 2026-09 之后有 10 个必填列，散在每个测试里写会把用例淹掉，
收敛到一处，以后再加必填列也只改这里。
"""

import sys
from pathlib import Path

import pytest

# pytest 只把 tests/ 加进 import 路径，项目根目录要自己加，否则 import app 会失败
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.dependencies import Container
from app.infrastructure.state.active_standard import JsonStandardApplicationState
from app.infrastructure.database.connection import init_database


def create_standard(container, spheroidization_time, created_by, **overrides):
    """建一条标准。默认称重标准 1500.0，其余走关键字覆盖。"""
    params = {
        "standard_spheroidization_time": spheroidization_time,
        "weighing_standard": 1500.0,
        "created_by": created_by,
    }
    params.update(overrides)
    return container.create_standard().execute(**params)


def create_record(container, detection_time, actual, abnormal=None, **overrides):
    """建一条球化记录。物性字段给的是固定假值，需要时用关键字覆盖。

    abnormal 单独拎出来是因为测试里三种情况都要用到（0 / 1 / None）。
    """
    params = {
        "detection_time": detection_time,
        "spheroidization_start_time": "2026-09-05 08:30:20",
        "spheroidization_end_time": "2026-09-05 08:31:25",
        "actual_spheroidization_time": actual,
        "spheroidization_temperature": 1520.0,
        "spheroidization_temperature_time": "2026-09-05 08:30:22",
        "spheroidization_wire_entry_start_time": "2026-09-05 08:30:40",
        "spheroidization_wire_entry_end_time": "2026-09-05 08:32:00",
        "spheroidization_wire_entry_total_duration": 80.0,
        "spheroidization_weight": 1608.0,
        "spheroidization_abnormal": abnormal,
    }
    params.update(overrides)
    return container.create_spheroidization().execute(**params)


@pytest.fixture
def 连接(tmp_path):
    """一个全新的 SQLite 库。tmp_path 是 pytest 给的临时目录，跑完自动删。"""
    conn = init_database(tmp_path / "test.db")
    yield conn
    conn.close()


@pytest.fixture
def 空容器(连接, tmp_path):
    """空库 + 装配好的 Container。和 API 层用的是同一个 Container 类。"""
    return Container(
        conn=连接,
        standard_application_state=JsonStandardApplicationState(
            tmp_path / "active_standard.json"
        ),
    )


@pytest.fixture
def 有标准的容器(空容器):
    """已经建了两条标准，当前生效的是第 2 条。"""
    create_standard(空容器, 65.0, "张三", remark="初始标准")
    create_standard(空容器, 70.0, "李四", remark="调整")
    return 空容器


@pytest.fixture
def 有记录的容器(有标准的容器):
    """再建三条球化记录。"""
    c = 有标准的容器
    create_record(c, "2026-09-05 08:30:15", 65.0, abnormal=0)
    create_record(c, "2026-09-05 09:15:32", 75.0, abnormal=1)
    create_record(c, "2026-09-05 10:20:08", 65.0, abnormal=None)
    return c
