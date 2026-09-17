"""pytest 的公共夹具（conftest.py 是 pytest 的约定文件名，不用手动 import）。

每个测试函数拿到的都是**一个全新的空库**——pytest 给的 tmp_path，跑完自动清理。
所以测试之间互不干扰，也不会碰到 data/spheroidization.db 里你自己的数据。

夹具是层层叠上去的，后面的在前面基础上多建一点数据：

    连接          空库 + 一条连接
    空容器        空库 + 装配好的 Container（走的是 API 层同一条链路）
    有标准的容器   在空容器上先建好 2 条标准，当前生效的是第 2 条
    有记录的容器   再有 3 条球化记录：第 1 条正常、第 2 条异常、第 3 条机器没给判定

测试要什么就从后往前挑最靠后的那个，比如测处置就只要 有记录的容器。
"""

import sys
from pathlib import Path

import pytest

# pytest 只把 tests/ 加进 import 路径，项目根目录要自己加，否则 import app 会失败
系统根目录 = Path(__file__).resolve().parents[1]
if str(系统根目录) not in sys.path:
    sys.path.insert(0, str(系统根目录))

from app.dependencies import Container
from app.infrastructure.database.connection import init_database


@pytest.fixture
def 连接(tmp_path):
    """一个全新的 SQLite 库。tmp_path 是 pytest 给的临时目录，跑完自动删。"""
    conn = init_database(tmp_path / "test.db")
    yield conn
    conn.close()


@pytest.fixture
def 空容器(连接):
    """空库 + 装配好的 Container。和 API 层用的是同一个 Container 类。"""
    return Container(conn=连接)


@pytest.fixture
def 有标准的容器(空容器):
    """已经建了两条标准，当前生效的是第 2 条。"""
    空容器.create_standard().execute(65.0, 125.0, 1500.0, "张三", "初始标准")
    空容器.create_standard().execute(70.0, 130.0, 1500.0, "李四", "调整")
    return 空容器


@pytest.fixture
def 有记录的容器(有标准的容器):
    """再建三条球化记录。"""
    c = 有标准的容器
    c.create_spheroidization().execute(
        "2026-09-05 08:30:15", "2026-09-05 08:30:20", "2026-09-05 08:31:25", 65.0, 0
    )
    c.create_spheroidization().execute(
        "2026-09-05 09:15:32", "2026-09-05 09:15:40", "2026-09-05 09:16:55", 75.0, 1
    )
    c.create_spheroidization().execute(
        "2026-09-05 10:20:08", "2026-09-05 10:20:15", "2026-09-05 10:21:16", None, None
    )
    return c
