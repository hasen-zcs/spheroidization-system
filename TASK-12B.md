# TASK-12B 下拉条：切换原因 / 复核说明 / 标准备注 改下拉（末项自定义输入）

> 工头：小白 · 2026-11-06 · 环境：~/spheroidization-lab
> 完成后必须：`cd frontend && npm run build` 0 错误 + `.venv/bin/python -m pytest -q` 全绿（后端零改动，只是防回归），贴回末尾输出。

## 背景（现状，行号已核实）

- 切换原因：自由 input 两处 —— `frontend/src/views/Standard.vue` 切换标准弹窗（「切换原因（必填）」）+ `frontend/src/views/Monitor.vue` 切换标准弹窗（同文案）。两处都是 `v-model="switchReason"` + `trim` 后判空 alert。
- 复核说明：`frontend/src/views/SpheroidizationDetail.vue` 「新增复核」表单里的 textarea（`v-model="reviewRemark"`，可选）。
- 标准备注：`frontend/src/views/Standard.vue` 「新增检测标准」表单的 textarea（`v-model="remark"`，可选）+ **修改弹窗的备注字段**（TASK-12A 刚加的，也是 textarea）。
- 后端这些字段都是普通字符串，**本任务零后端改动**。

## A. 共享组件 `frontend/src/components/ReasonSelect.vue`（新建）

props：
- `modelValue: string`（当前值；`""` = 未选）
- `options: string[]`（普通选项，**不含**「其他」）
- `placeholder: string`（select 首项的空值文案）
- `allowEmpty?: boolean` 默认 true（仅用于 placeholder 语义，校验仍由调用方做）

行为：
- 渲染一个 `<select>`：首项 `<option value="">{{ placeholder }}</option>`，然后 `options`，**最后一项固定 `<option value="__other__">其他（请输入）</option>`**。
- 选普通项 → `emit("update:modelValue", 选项文本)`（中文原文直传）。
- 选「其他」→ select 下方显示一个 `<input>`（v-model 自定义值，placeholder「请输入自定义内容」），`modelValue` 跟随输入实时 emit；输入框聚焦态。
- 选回任意普通项或首项空值 → 隐藏输入框并清空自定义缓存。
- 外部 `modelValue` 变化（如弹窗重置）：值等于某选项 → select 显示该项；值非空且不是选项也不是「其他」态 → 自动进入「其他」态并回填输入框；空 → 首项。
- 视觉：与页面现有 form input 风格一致（12px、#d9d9d9 边框、focus 蓝边）；组件样式 scoped。
- 纯展示逻辑，不 import 任何 api。

## B. 选项常量（`frontend/src/constants.ts` 末尾追加）

```ts
// 下拉条预设选项（2026-11-06 三需求 R2，用户视角=车间/工艺员）
export const SWITCH_REASON_OPTIONS: string[] = [
  "标准值更新（工艺优化）",
  "异常炉次后重新标定",
  "新材料试浇",
  "设备仪表标定后",
  "季节温变调整",
  "纠正前期误操作",
]

export const REVIEW_REMARK_OPTIONS: string[] = [
  "机器误判，纠正为正常",
  "机器漏判，纠正为异常",
  "取样验证与机器一致",
  "取样验证与机器不符",
  "设备故障后复测",
  "样品缺失无法复核",
]

export const STANDARD_REMARK_OPTIONS: string[] = [
  "工艺参数优化",
  "异常炉次后重新标定",
  "新材料新牌号试浇",
  "设备变更或标定",
  "季节温变调整",
]
```

## C. 四处接入

1. **Standard.vue 切换弹窗**：input 换成 `<ReasonSelect v-model="switchReason" :options="SWITCH_REASON_OPTIONS" placeholder="请选择切换原因" />`；标签仍「切换原因（必填）」；提交前 `trim` 判空 alert 文案不变（「请填写切换原因，原因为空不允许提交」）。
2. **Monitor.vue 切换弹窗**：同上（同一常量，同一交互）。注意 Monitor.vue 的弹窗结构与 Standard.vue 独立，两处都要改。
3. **SpheroidizationDetail.vue 复核**：textarea 换成 `<ReasonSelect v-model="reviewRemark" :options="REVIEW_REMARK_OPTIONS" placeholder="请选择或输入复核说明" />`；**必填校验保持不动**（现有 `if (!reviewRemark.value.trim()) alert("请输入复核说明")` 原样保留——复核说明是人工纠偏的审计凭据，不许放宽；选预设项即满足必填，选「其他」要输字）。
4. **Standard.vue 新增表单备注 + 修改弹窗备注**：两个 textarea 都换成 `<ReasonSelect v-model="remark" :options="STANDARD_REMARK_OPTIONS" placeholder="请选择或输入备注（可选）" />`。

## D. 约束
- 不改任何后端文件、不改 api/index.ts。
- 不改 Monitor.vue 主表列宽/蓝卡（TASK-12C 的范围），只动它的切换弹窗。
- 提交链路（switchStandard/submitReview/createStandard/updateStandard）参数不变，只是值来源变成下拉。

## E. 完成判定（贴回证据）
1. `npm run build` 成功输出
2. `pytest -q` 末尾 `N passed`（应为 290+，一个不许红）
3. `git status --short` 改动清单
4. 简述四处接入点的选择器/字段绑定方式（每处一行）
