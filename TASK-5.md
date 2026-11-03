# TASK-5：报表趋势图默认区间修正 + 缺进线结束标记为异常（本地开发任务书）

## 背景
本工程是 FastAPI + SQLite 后端（`app/`）+ Vue3 前端（`frontend/`）+ 合并层（`merge/`）的球化系统。

### 问题 A：报表「异常率趋势」有坐标系但看不到曲线
已定位根因（不用重新排查）：`frontend/src/views/Reports.vue` 里
`const start = ref(today())` / `const end = ref(today())` —— 默认时间范围是「今天~今天」，
summary 的 trend 只返回 1 天 → 趋势图 `polyline` 只有 1 个点（SVG 单点画不出线）→
用户看到坐标轴（y 刻度 + 1 个日期标签）但没有曲线。
后端 trend 数据已验证正常（90 天区间返回 95 天、70 天非零）。

### 问题 B：PLC 采不到喂丝结束（进线结束/时长为 null）的炉次要标记为异常
老板拍板：不做死信重试/告警，**缺进线结束直接当作一种异常**。
现有异常分类：0 正常 / 1 进站未球化 / 2 球化线滑动/进线提前中止 / 3 超标准 / 4 低于标准 /
5 中间停顿 / 6 未判定。进线结束缺失归入**类型 2**（进线线异常，语义最贴合，不加新类型、不动 schema）。
实施位置在**合并层 heat 组包**（`merge/assemble.py` 的 `build_payload_from_heat`），因为只有合并层
知道「回捞过 all_plc 仍然缺失」这个事实；后端已接受 null（TASK-4 已上线），不再需要后端判断。

## 规则（照此实现，不许自由发挥）

### A. 前端报表（`frontend/src/views/Reports.vue`，禁引入新前端依赖）
1. 默认时间范围改为**近 30 天**：`start` 默认 = 今天往前推 29 天、`end` 默认 = 今天（日期格式与现有
   `today()` 产出的格式保持一致，先读现有代码确认格式再改）。用户手动改日期不受影响。
2. 趋势图单点兜底：`trendChart` computed 里，当 `rows.length === 1` 时额外返回
   `single: { x: pointX(0), y: pointY(row.abnormal_rate) }`（多天时 `single: null`）；
   模板里 `v-if="trendChart.single"` 画一个 `<circle>`（cx/cy 绑 single，r=4，fill 与折线同色
   `#cf1322`），polyline 保持原样。其余图表元素一律不动。
3. `npm run build` 必须成功。

### B. 合并层标记（`merge/assemble.py`）
在 `build_payload_from_heat` 组完 payload 之后、return 之前：
```
if payload["spheroidization_wire_entry_end_time"] is None or payload["spheroidization_wire_entry_total_duration"] is None:
    t = payload.get("abnormal_type")
    if t in (0, None):
        payload["abnormal_type"] = 2
        payload["abnormal_reason"] = "进线结束时间缺失（PLC 未采集到喂丝结束）"
    else:
        old = payload.get("abnormal_reason")
        payload["abnormal_reason"] = (str(old) + "；" if old else "") + "进线结束时间缺失（PLC 未采集到喂丝结束）"
    payload["spheroidization_abnormal"] = abnormal_flag(payload["abnormal_type"])
```
（上面是逻辑基准，具体写法可微调，但行为必须一致。）
- **reactions 老路径（`build_payload`）一律不动**——它 PLC 缺字段本来就抛 AssembleError，行为不变。
- 回捞逻辑（backfill_plc_from_all_plc）、游标、上传队列一律不动。
- 检测侧（vpmin）一律不动。

### C. 测试（`tests/` 或 `merge/` 既有测试处扩展，只增不改老断言）
- heat 组包：进线结束/时长为 null 且原 abnormal_type=0 → 断言 payload 变成 type=2、abnormal=1、
  reason 含「进线结束时间缺失」
- heat 组包：null 且原 abnormal_type=5（带原 reason）→ 断言 type 保持 5、abnormal=1、
  reason = 原 reason + 分隔 + 「进线结束时间缺失（PLC 未采集到喂丝结束）」
- heat 组包：进线结束/时长非 null → 断言 payload 与原行为完全一致（回归）
- 全量回归必须全绿（基线 243，只增不减）

## 红线
- 不改 schema、不加异常类型（就用类型 2）
- 不改 reactions 老路径、不改回捞/游标/上传队列、不动检测侧
- 不引入新前端依赖
- 全量 `.venv/bin/python -m pytest tests/ -x -q` 全绿（基线 243+）
- `npm run build` 成功
- 不许 git add/commit、不许提问、不许等确认，一次做完

## 产出
1. 代码改动（仓库内直接改）
2. 自检写入 `TASK-5-RESULT.md`：改的文件、每条验收测试函数名、pytest 数字、build 结果、
   趋势图默认区间的新值、遗留问题
