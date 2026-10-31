import time
import json
import struct
import sys
import datetime
import os
import snap7



# ============ 按钮确认文件输出配置 ============
BUTTON_LOG_FILE = os.getenv(
    "BUTTON_ROLLING_FILE", "/root/Get_Allinfomation/button_confirm_time.json"
)   # 只保留最近 N 条
ALL_BUTTON_FILE = os.getenv(
    "BUTTON_ALL_FILE", "/root/Get_Allinfomation/all_button_confirm_time.jsonl"
)  # 保留全部
BUTTON_KEEP = int(os.getenv("BUTTON_KEEP", "10"))
# 连按去重：同一个上升沿之后 D 秒内的再次按下视为同一次（现场连按策略未定，
# 先给个保守值；真要改成"取最后一次"，只需把这里换成长按结束判定）
BUTTON_DEBOUNCE_S = float(os.getenv("BUTTON_DEBOUNCE_S", "2.0"))

# ============ 连接参数 ============
PLC_IP = '192.168.10.1'
RACK   = 0
SLOT   = 1

# ============ 触发位地址表 ============
# 字段: (名称, DB号, 字节偏移, 位号, 时间补偿秒数)
TRIGGERS = [
    ("按钮确认", 200, 128, 0, 0),
    ("喂丝开始", 200, 129, 2, 0),
    ("喂丝结束", 200, 129, 3, 24),
]

# ============ 附带读取的数据地址表 ============
# 字段: (键名, DB号, 起始字节, 长度, 类型)
EXTRA = [
    ("weight", 200, 8,  4, "REAL"),
]

POLL_S = 0.1


# ============ 连接 ============
def connect():
    c = snap7.client.Client()
    c.connect(PLC_IP, RACK, SLOT)
    return c


def read_bit(client, db, byte, bit):
    raw = client.db_read(db, byte, 1)
    return (raw[0] >> bit) & 1


def read_value(client, db, start, size, dtype):
    raw = client.db_read(db, start, size)
    if dtype == "REAL":
        return struct.unpack(">f", bytes(raw))[0]
    if dtype == "INT":
        return struct.unpack(">h", bytes(raw))[0]
    if dtype in ("UINT", "WORD"):
        return struct.unpack(">H", bytes(raw))[0]
    if dtype == "DINT":
        return struct.unpack(">i", bytes(raw))[0]
    if dtype in ("DWORD", "UDINT"):
        return struct.unpack(">I", bytes(raw))[0]
    raise ValueError(f"未知类型: {dtype}")


def fmt_time(dt):
    return dt.strftime("%Y-%m-%d %H:%M:%S")


class ButtonEdge:
    """按钮上升沿检测 + 连按去抖（纯逻辑，不碰 PLC，方便单测）。

    - 首次看到某一位只登记，不产生事件（避免启动瞬间误报）
    - 0→1 且距上次接受已超过 debounce 秒 → 产生一次事件
    - 距上次不足 debounce 秒 → 记为 suppressed，由调用方打日志
    """

    def __init__(self, debounce_s: float = BUTTON_DEBOUNCE_S):
        self.debounce_s = float(debounce_s)
        self.last_accepted = None
        self.suppressed = 0
        self._prev = None

    def feed(self, bit: int, now):
        """喂一个采样点，返回 (event_time | None)。"""
        bit = int(bit)
        if self._prev is None:
            self._prev = bit
            return None
        prev, self._prev = self._prev, bit
        if not (bit == 1 and prev == 0):
            return None
        if self.last_accepted is not None:
            gap = (now - self.last_accepted).total_seconds()
            if gap < self.debounce_s:
                self.suppressed += 1
                return None
        self.last_accepted = now
        return now


def button_event_json(dt):
    """给 bridge 的标准输出事件（bridge 见到 event=button_confirm 会分流）。"""
    return json.dumps(
        {
            "event": "button_confirm",
            "button_confirm_time": fmt_time(dt),
            "source": "button",
        },
        ensure_ascii=False,
    )

# ---------- 追加模式:同一个文件,保留所有 ----------
def append_all_button_confirm(t):
    os.makedirs(os.path.dirname(ALL_BUTTON_FILE), exist_ok=True)
    rec = {"button_confirm_time": fmt_time(t)}
    with open(ALL_BUTTON_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")

# ---------- 滚动模式:每次一个新文件,只保留最近 N 个 ----------
def write_button_confirm_rolling(t):
    os.makedirs(os.path.dirname(BUTTON_LOG_FILE), exist_ok=True)
    rec = {"button_confirm_time": fmt_time(t)}
    records = []
    if os.path.exists(BUTTON_LOG_FILE):
        try:
            with open(BUTTON_LOG_FILE, "r", encoding="utf-8") as f:
                content = f.read().strip()
            if content:
                records = json.loads(content)
                if not isinstance(records, list):
                    records = []
        except Exception as e:
            print(f"读取 {BUTTON_LOG_FILE} 失败,按空数组处理: {e}", file=sys.stderr, flush=True)
            records = []
    records.append(rec)
    records = records[-BUTTON_KEEP:]
    tmp = BUTTON_LOG_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, BUTTON_LOG_FILE)

# ============ 主循环 ============
def main():
    client = connect()
    print("PLC 连接成功,开始监控触发位 ...\n", file=sys.stderr, flush=True)

    prev = {}
    pending_start = None
    button_edge = ButtonEdge()

    try:
        while True:
            try:
                for name, db, byte, bit, offset_s in TRIGGERS:
                    cur = read_bit(client, db, byte, bit)

                    if name == "按钮确认":
                        # 单独走去抖逻辑：喂采样点 → 需要时才产生事件
                        t = button_edge.feed(cur, datetime.datetime.now())
                        if t is not None:
                            try:
                                append_all_button_confirm(t)
                                write_button_confirm_rolling(t)
                            except Exception as we:
                                print(f"写按钮确认文件失败: {we}", file=sys.stderr, flush=True)
                            # 关键：必须打到 stdout，bridge 才能分流给合并层；
                            # 只写文件的话下游永远拿不到按钮时刻。
                            print(button_event_json(t), flush=True)
                        prev[name] = cur
                        continue

                    if name not in prev:
                        prev[name] = cur          # 首次只记录,不输出
                    elif cur == 1 and prev[name] == 0:
                        # 0→1 上升沿
                        t = datetime.datetime.now()
                        if offset_s:
                            t = t - datetime.timedelta(seconds=offset_s)

                        if name == "喂丝开始":
                            pending_start = t
                        elif name == "喂丝结束":
                            # 计算总时长（秒,保留 3 位小数）
                            if pending_start:
                                duration = round((t - pending_start).total_seconds(), 3)
                            else:
                                duration = None

                            record = {
                                "spheroidization_wire_entry_start_time": fmt_time(pending_start) if pending_start else None,
                                "spheroidization_wire_entry_end_time": fmt_time(t),
                                "spheroidization_wire_entry_total_duration": duration,
                            }

                            for ename, edb, estart, esize, edtype in EXTRA:
                                try:
                                    v = read_value(client, edb, estart, esize, edtype)
                                    if isinstance(v, float):
                                        v = round(v, 3)
                                    record["spheroidization_"+ename] = v
                                except Exception as e:
                                    record["spheroidization_"+ename] = None

                            print(json.dumps(record, ensure_ascii=False), flush=True)
                            pending_start = None

                        prev[name] = cur
                    else:
                        prev[name] = cur

            except Exception as e:
                print(f"读取异常: {e},尝试重连...", file=sys.stderr, flush=True)
                try:
                    client.disconnect()
                except Exception:
                    pass
                while True:
                    try:
                        client = connect()
                        print("重连成功", file=sys.stderr, flush=True)
                        prev.clear()
                        pending_start = None
                        button_edge = ButtonEdge()
                        break
                    except Exception as ce:
                        print(f"重连失败: {ce},3 秒后重试", file=sys.stderr, flush=True)
                        time.sleep(3)

            time.sleep(POLL_S)

    except KeyboardInterrupt:
        print("\n用户终止", file=sys.stderr, flush=True)
    finally:
        try:
            client.disconnect()
        except Exception:
            pass


if __name__ == "__main__":
    main()