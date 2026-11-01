"""追加文件的追尾读取。三个坑都在这儿处理掉：

1. **半行**：文件正在被写，最后一行可能只有半截。只消费到最后一个换行，
   半行留到下一轮——直接 json.loads 会炸，跳过它又会丢数据。
2. **重建/轮转**：inode 变了说明文件被替换，offset 没有意义，从头扫，
   靠内容指纹去重（不是靠 offset）。
3. **变短**：文件被截断重写时 size < offset，同样从头扫。
"""

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Optional, Tuple


def fingerprint(obj: Any) -> str:
    """内容指纹：同一行数据重扫时算出同一个值。"""
    blob = json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:32]


def tail_lines(
    path: Path, cursor: Optional[Tuple[int, int]]
) -> Tuple[list[dict], int, int]:
    """
    :param path: 追加写文件
    :param cursor: (inode, offset)；None 表示第一次读
    :return: (解析出的对象列表, inode, 新 offset)

    调用方拿到结果后要**先入库再提交游标**，否则中间崩溃会丢一批。
    """
    if not path.exists():
        return [], 0, 0

    st = path.stat()
    inode, offset = (cursor or (st.st_ino, 0))
    if inode != st.st_ino or st.st_size < offset:
        # 文件被替换或截断：从头来，指纹去重兜底
        inode, offset = st.st_ino, 0

    with open(path, "rb") as fh:
        fh.seek(offset)
        chunk = fh.read()

    if not chunk:
        return [], inode, offset

    # 只处理到最后一个换行，剩下的半行下轮再说
    end = chunk.rfind(b"\n")
    if end < 0:
        return [], inode, offset
    body = chunk[: end + 1]

    objects: list[dict] = []
    for raw in body.splitlines():
        if not raw.strip():
            continue
        try:
            objects.append(json.loads(raw.decode("utf-8")))
        except (UnicodeDecodeError, json.JSONDecodeError):
            # 坏行不能吞掉：计数并跳过，日志在调用方打
            objects.append({"__bad_line__": raw.decode("utf-8", "replace")})

    return objects, inode, offset + len(body)


def read_all_lines(path: Path) -> list[dict]:
    """全量读（滚动文件专用）。文件不存在返回空列表。"""
    if not path.exists():
        return []
    out: list[dict] = []
    for raw in path.read_bytes().splitlines():
        if not raw.strip():
            continue
        try:
            out.append(json.loads(raw.decode("utf-8")))
        except (UnicodeDecodeError, json.JSONDecodeError):
            continue
    return out


def file_exists(path: Path) -> bool:
    return path.exists() and os.path.getsize(path) > 0
