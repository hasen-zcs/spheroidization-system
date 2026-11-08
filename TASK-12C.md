# TASK-12C 监控页排版：底部蓝卡重排 + 「报警原因」列加宽改名

> 工头：小白 · 2026-11-06 · 环境：~/spheroidization-lab
> 范围：只动 `frontend/src/views/Monitor.vue`（模板 + style + statusInfo computed）。
> 完成后必须：`cd frontend && npm run build` 0 错误 + `.venv/bin/python -m pytest -q` 全绿，贴回末尾输出。

## 现状（已核实）

- 底部蓝色卡片 = `.info-panel`（背景 #e6f2ff），`display:flex` 两列 `.info-column`（grid 竖排）：
  - 左列：当前记录状态 / 标准·实际球化时间 / 检测时间
  - 右列：检测结果 / 处理人 / 铁水温度 / 测温时间
  - 数据来自 `statusInfo` computed（取 `latestRecord` = 最新一条记录）。
- 主表 10 列：序号/铁水重量/进线开始时间/进线结束时间/进线持续时间/球化开始时间/球化结束时间/球化持续时长/球化结果/**报警原因**（末列）。
- 列宽机制：`columnWidths = [46,78,140,140,88,140,140,100,64,72]`，前 9 列固定可拖拽，第 10 列（`LAST_COLUMN_INDEX=9`）= 容器宽 - 前 9 列之和，最小 `LAST_COLUMN_MIN=72`；首屏 `fitColumnsToContainer()` 把前 9 列按 `(container - columnWidths[9])` 等比放大铺满。
- 页面顶部注释（L302~304 附近）写着「最后一列（报警原因）自动吃掉剩余宽度」。
- 记录可用字段（api SpheroidizationRecord）：id、detection_time、spheroidization_weight、abnormal_type、abnormal_reason、processed、processed_by、temperature、temperature_time 等；`display()` 空值兜底「--」；`getAbnormalReason(record)` 已能拼「类型：原因」文案（未判定/无/类型：原因）。

## A. `.info-panel` 重排：2 列 7 项 → **3 列 × 3 行 = 9 项**

新布局（grid `grid-template-columns: repeat(3, minmax(0,1fr))`，行顺序如下，窄屏 <768px 回落 1 列）：

| 行 | 列1 | 列2 | 列3 |
|---|---|---|---|
| 1 | 记录 #（新增，显示 `#{{record.id}}`） | 检测时间 | 检测结果 |
| 2 | 标准/实际球化时间 | 铁水重量（新增） | 异常原因（新增） |
| 3 | 记录状态（原「当前记录状态」，值仍 待处理/已处理） | 处理人 | 铁水温度（合并测温时间：`1350℃（10:23:45）`，无温度时间就只显 `1350℃`，无温度显示 `--`） |

- `statusInfo` computed 同步加字段：`recordId`（`#${record.id}`）、`weight`（`display(record.spheroidization_weight)`）、`abnormalReason`（复用 `getAbnormalReason(record)` 逻辑，无记录时「--」）、`temperature` 合成字段或模板里拼。
- 每项结构保持「标签 + 白底 input(readonly)」现有样式；标签统一宽度对齐（grid 里 `label 96px + input 1fr` 或现有 div+input 风格二选一，视觉整齐优先）；卡片高度会自然变 3 行，`padding` 可微调。
- 旧 7 项全部保留（「当前记录状态」改叫「记录状态」），新增 3 项：记录 #、铁水重量、异常原因。

## B. 主表末列

1. 表头文案「报警原因」→「**异常原因**」（th 里；同步把 L302~304 那段注释里的「报警原因」字样改掉，别留注释代码不一致）。
2. 初始宽度：`columnWidths[9]` 从 `72` 改为 `160`。**`LAST_COLUMN_MIN` 保持 72 不动**（拖拽最小值语义不变）；`fitColumnsToContainer` 逻辑一字不改（它读的就是 `columnWidths[LAST_COLUMN_INDEX]` 当首屏默认末列宽，改初值即生效）。
3. 空态行 `colspan="10"` 不变；拖拽 resizer 机制不动（末列本来就没有 resizer）。

## C. 约束
- 只动 Monitor.vue；不动 Standard.vue / SpheroidizationDetail.vue / 组件 / constants。
- 不动轮询、弹窗(okng)、视频、切换标准弹窗逻辑（TASK-12B 刚改过它的切换弹窗下拉，**别碰那段**）。
- 不引入新依赖。

## D. 完成判定（贴回证据）
1. `npm run build` 成功输出
2. `pytest -q` 末尾 `N passed`
3. `git status --short`
4. 贴出新 `.info-panel` 模板片段（<30 行）+ 改后的 `columnWidths` 数组
