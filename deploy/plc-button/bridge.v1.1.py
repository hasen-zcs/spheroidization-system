import json
import os
import sys
import subprocess
import threading
import time
import re

# ================== 配置模块 ==================
# 根目录
BASE_DIR = os.getenv("BRIDGE_BASE_DIR", "/root")

# 所有 PLC 信息汇总文件（不裁剪，每行一个 JSON）
ALL_PLC_FILE = os.path.join(BASE_DIR, "Get_Allinfomation/all_plc.jsonl")

# 所有测温枪温度汇总文件（不裁剪，每行一个 JSON）
ALL_TEMPERATURE_FILE = os.path.join(
    BASE_DIR, "Get_Allinfomation/all_temperature.jsonl"
)

# PLC 数据文件
PLC_FILE = os.path.join(BASE_DIR, "Get_Allinfomation/plc.jsonl")

# PLC 文件最多保存的数据条数
PLC_KEEP = 10

# 测温枪独立数据保存目录
TEMPERATURE_GUN_DIR = os.path.join(
    BASE_DIR, "Get_Allinfomation/temperture_guns"
)

# 每把测温枪最多保存的数据条数
TEMPERATURE_GUN_KEEP = 50

# 按钮确认（由 PLC 采集程序 stdout 推送，不进 plc.jsonl，避免打乱配对序号）
BUTTON_ROLLING_FILE = os.path.join(
    BASE_DIR, "Get_Allinfomation/button_confirm_time.json"
)
BUTTON_ALL_FILE = os.path.join(
    BASE_DIR, "Get_Allinfomation/all_button_confirm_time.jsonl"
)
BUTTON_KEEP = 10

# 数据采集子程序
WORKERS = [
    (
        "plc",
        os.path.join(BASE_DIR, "Get_Allinfomation/PLC_Moudle"),
        ["uv", "run", "Get_PLCInfo.py"]
    ),
    (
        "csv",
        os.path.join(BASE_DIR, "Get_Allinfomation/Temperature_Module"),
        ["uv", "run", "Get_Temperature.py"]
    ),
]

# 子程序退出后是否自动重启
AUTO_RESTART = True

# 子程序退出后等待多少秒再重启
RESTART_DELAY = 5

# ================== 初始化模块 ==================
# ================== 初始化模块 ==================
os.makedirs(os.path.dirname(PLC_FILE), exist_ok=True)
os.makedirs(TEMPERATURE_GUN_DIR, exist_ok=True)
os.makedirs(os.path.dirname(ALL_PLC_FILE), exist_ok=True)
os.makedirs(os.path.dirname(ALL_TEMPERATURE_FILE), exist_ok=True)

write_lock = threading.Lock()

plc_count = 0
gun_counts = {}

# ================== 计数器模块 ==================
def get_last_reaction_count(file_path):
    if not os.path.exists(file_path):
        return 0

    try:
        with open(file_path, "rb") as f:
            try:
                f.seek(-2, os.SEEK_END)
            except OSError:
                f.seek(0)

            while f.tell() > 0:
                char = f.read(1)
                if char == b"\n":
                    break
                f.seek(-2, os.SEEK_CUR)

            line = f.readline().decode("utf-8").strip()

        if not line:
            return 0

        data = json.loads(line)
        return int(data.get("reaction_count", 0))

    except Exception:
        return 0


def init_counters():
    global plc_count

    plc_count = get_last_reaction_count(PLC_FILE)

    if not os.path.exists(TEMPERATURE_GUN_DIR):
        return

    for filename in os.listdir(TEMPERATURE_GUN_DIR):
        if not filename.endswith(".jsonl"):
            continue

        file_path = os.path.join(
            TEMPERATURE_GUN_DIR,
            filename
        )

        gun_counts[filename] = get_last_reaction_count(
            file_path
        )

# ================== 测温枪识别模块 ==================
def get_device_name(data):
    if isinstance(data, dict):
        return str(
            data.get("device_name", "")
        ).strip()

    if isinstance(data, list) and len(data) > 3:
        return str(data[3]).strip()

    return ""

# ================== 测温枪文件模块 ==================
def get_temperature_gun_file(device_name):
    match = re.search(
        r"(\d+)$",
        device_name
    )

    if match:
        filename = (
            f"temperature_gun"
            f"{match.group(1)}.jsonl"
        )
    else:
        safe_name = re.sub(
            r'[\\/:*?"<>|]',
            "_",
            device_name
        )
        filename = (
            f"temperature_"
            f"{safe_name}.jsonl"
        )

    return os.path.join(
        TEMPERATURE_GUN_DIR,
        filename
    )


def save_temperature_gun(gun_file, line):
    filename = os.path.basename(gun_file)

    if filename not in gun_counts:
        gun_counts[filename] = get_last_reaction_count(
            gun_file
        )

    with open(
        gun_file,
        "a",
        encoding="utf-8"
    ) as f:
        f.write(line + "\n")
        f.flush()


    append_jsonl(ALL_TEMPERATURE_FILE, line)

    if gun_counts[filename] >= TEMPERATURE_GUN_KEEP:
        trim_file(
            gun_file,
            TEMPERATURE_GUN_KEEP
        )

def append_jsonl(file_path, line):
    with open(file_path, "a", encoding="utf-8") as f:
        f.write(line + "\n")
        f.flush()

def trim_file(file_path, keep_count):
    try:
        temp_file = file_path + ".tmp"

        with open(
            file_path,
            "r",
            encoding="utf-8"
        ) as src:
            lines = src.readlines()

        if len(lines) <= keep_count:
            return

        with open(
            temp_file,
            "w",
            encoding="utf-8"
        ) as dst:
            dst.writelines(
                lines[-keep_count:]
            )
            dst.flush()
            os.fsync(dst.fileno())

        os.replace(
            temp_file,
            file_path
        )

    except Exception as e:
        print(
            f"[file] 裁剪失败: {file_path} ({e})",
            file=sys.stderr,
            flush=True
        )

        temp_file = file_path + ".tmp"

        if os.path.exists(temp_file):
            try:
                os.remove(temp_file)
            except Exception:
                pass

# ================== PLC 文件模块 ==================
def save_plc(line):
    global plc_count

    with open(
        PLC_FILE,
        "a",
        encoding="utf-8"
    ) as f:
        f.write(line + "\n")
        f.flush()

    append_jsonl(ALL_PLC_FILE, line)

    if plc_count >= PLC_KEEP:
        trim_file(
            PLC_FILE,
            PLC_KEEP
        )

# ================== 数据写入模块 ==================
def save_button(data):
    """按钮事件旁路落盘：只写按钮自己的两个文件。

    正规流程是 PLC 采集脚本自己写文件、stdout 只做通知；这里默认不再重复写，
    只有显式打开 BUTTON_WRITE_IN_BRIDGE 才补写，防止两份文件互相打架。
    """
    if os.getenv("BUTTON_WRITE_IN_BRIDGE", "0") != "1":
        return
    import datetime

    t = data.get("button_confirm_time") or time.strftime("%Y-%m-%d %H:%M:%S")
    rec = {"button_confirm_time": t}
    with write_lock:
        os.makedirs(os.path.dirname(BUTTON_ALL_FILE), exist_ok=True)
        with open(BUTTON_ALL_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        os.makedirs(os.path.dirname(BUTTON_ROLLING_FILE), exist_ok=True)
        rows = []
        try:
            with open(BUTTON_ROLLING_FILE, "r", encoding="utf-8") as f:
                rows = json.load(f) or []
        except Exception:
            rows = []
        rows.append(rec)
        rows = rows[-BUTTON_KEEP:]
        tmp = BUTTON_ROLLING_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(rows, f, ensure_ascii=False, indent=2)
        os.replace(tmp, BUTTON_ROLLING_FILE)


def emit(source, data):
    global plc_count

    # 按钮事件走旁路：**必须在 plc_count += 1 之前拦下**。
    # 否则每条按钮都会占掉一个配对序号，plc.jsonl 里混进非进线记录，
    # 合并器按序号配对会整体错位（10-27 方案里点出的坑）。
    if source == "plc" and isinstance(data, dict) and data.get("event") == "button_confirm":
        save_button(data)
        print(
            f"[button] {data.get('button_confirm_time')}",
            file=sys.stderr,
            flush=True,
        )
        return

    if source == "plc":
        with write_lock:
            plc_count += 1

            rec = {
                "reaction_count": plc_count,
                "source": "plc",
                "created_at": time.strftime(
                    "%Y-%m-%d %H:%M:%S"
                ),
                **data,
            }

            line = json.dumps(
                rec,
                ensure_ascii=False
            )

            save_plc(line)

    elif source == "csv":
        device_name = get_device_name(data)

        if not device_name:
            print(
                "[csv] 未识别到测温枪名称，跳过",
                file=sys.stderr,
                flush=True
            )
            return

        gun_file = get_temperature_gun_file(
            device_name
        )

        gun_name = os.path.basename(
            gun_file
        )

        with write_lock:
            if gun_name not in gun_counts:
                gun_counts[gun_name] = (
                    get_last_reaction_count(
                        gun_file
                    )
                )

            gun_counts[gun_name] += 1

            rec = {
                "reaction_count": gun_counts[gun_name],
                "source": "csv",
                "created_at": time.strftime(
                    "%Y-%m-%d %H:%M:%S"
                ),
                **data,
            }

            line = json.dumps(
                rec,
                ensure_ascii=False
            )

            save_temperature_gun(
                gun_file,
                line
            )

    else:
        rec = {
            "source": source,
            "created_at": time.strftime(
                "%Y-%m-%d %H:%M:%S"
            ),
            "data": data,
        }

        line = json.dumps(
            rec,
            ensure_ascii=False
        )

        with write_lock:
            with open(
                "/root/Get_Allinfomation/unknown.jsonl",
                "a",
                encoding="utf-8"
            ) as f:
                f.write(line + "\n")
                f.flush()

    print(
        f"[{source}] saved: {line}",
        file=sys.stderr,
        flush=True
    )

# ================== 数据读取模块 ==================
def pump(proc, source):
    for line in proc.stdout:
        line = line.strip()

        if not line:
            continue

        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            print(
                f"[{source}] 非 JSON，忽略: {line}",
                file=sys.stderr,
                flush=True
            )
            continue

        emit(
            source,
            data
        )

# ================== Worker 模块 ==================
class Worker:
    def __init__(self, name, cwd, cmd):
        self.name = name
        self.cwd = cwd
        self.cmd = cmd
        self.proc = None
        self.thread = None
        self.stop = False

    def start_process(self):
        self.proc = subprocess.Popen(
            self.cmd,
            cwd=self.cwd,
            env=os.environ.copy(),
            stdout=subprocess.PIPE,
            stderr=None,
            text=True,
            encoding="utf-8",
            bufsize=1,
        )

        print(
            f"[{self.name}] started "
            f"pid={self.proc.pid} "
            f"cwd={self.cwd}",
            file=sys.stderr,
            flush=True
        )

    def start(self):
        if not os.path.isdir(self.cwd):
            print(
                f"[{self.name}] 目录不存在: {self.cwd}",
                file=sys.stderr,
                flush=True
            )
            return

        try:
            self.start_process()
        except Exception as e:
            print(
                f"[{self.name}] 启动失败: {e}",
                file=sys.stderr,
                flush=True
            )
            return

        self.thread = threading.Thread(
            target=self._run,
            daemon=True
        )
        self.thread.start()

    def _run(self):
        while not self.stop:
            try:
                pump(
                    self.proc,
                    self.name
                )
            except Exception as e:
                print(
                    f"[{self.name}] 读取输出异常: {e}",
                    file=sys.stderr,
                    flush=True
                )

            if self.stop:
                break

            rc = self.proc.poll()

            print(
                f"[{self.name}] 子进程退出 rc={rc}",
                file=sys.stderr,
                flush=True
            )

            if not AUTO_RESTART:
                break

            print(
                f"[{self.name}] "
                f"{RESTART_DELAY} 秒后重启",
                file=sys.stderr,
                flush=True
            )

            try:
                time.sleep(
                    RESTART_DELAY
                )
            except KeyboardInterrupt:
                break

            if self.stop:
                break

            try:
                self.start_process()
            except Exception as e:
                print(
                    f"[{self.name}] 重启失败: {e}",
                    file=sys.stderr,
                    flush=True
                )

                try:
                    time.sleep(
                        RESTART_DELAY
                    )
                except KeyboardInterrupt:
                    break

    def terminate(self):
        self.stop = True

        if (
            self.proc
            and self.proc.poll() is None
        ):
            try:
                self.proc.terminate()
                self.proc.wait(
                    timeout=5
                )
            except Exception:
                try:
                    self.proc.kill()
                except Exception:
                    pass

        print(
            f"[{self.name}] stopped",
            file=sys.stderr,
            flush=True
        )

# ================== Worker 初始化模块 ==================
workers = [
    Worker(
        name,
        cwd,
        cmd
    )
    for name, cwd, cmd in WORKERS
]

# ================== 主程序模块 ==================
if __name__ == "__main__":
    init_counters()

    try:
        for worker in workers:
            worker.start()

        for worker in workers:
            if worker.thread:
                worker.thread.join()

    except KeyboardInterrupt:
        print(
            "\n用户终止",
            file=sys.stderr,
            flush=True
        )

    finally:
        for worker in workers:
            worker.terminate()