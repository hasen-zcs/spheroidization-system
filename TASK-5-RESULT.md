# TASK-5 自检结果

## 改的文件
1. `frontend/src/views/Reports.vue`
   - 默认时间范围：`start` 改为 `daysAgo(29)`（今天往前推 29 天）、`end` 保持 `today()`（今天），
     即**近 30 天**；新增 `formatDate`/`daysAgo` 辅助函数，日期格式与 `today()` 完全一致
     （`YYYY-MM-DD`，如 2026-11-03）。用户手动改日期不受影响（ref 初始值只是默认）。
   - 趋势图单点兜底：`trendChart` computed 返回值新增 `single` 字段——
     `rows.length === 1` 时 `single = { x: pointX(0), y: pointY(rows[0].abnormal_rate) }`，
     多天时 `single: null`；模板里 `v-if="trendChart.single"` 画一个
     `<circle :cx="trendChart.single.x" :cy="trendChart.single.y" r="4" fill="#cf1322" />`
     （与折线同色）。polyline 及其余图表元素一律未动。
   - 未引入任何新前端依赖（package.json 未动）。
2. `merge/assemble.py`
   - 仅 `build_payload_from_heat` 内、组完 payload 之后、`return` 之前加了一段标记逻辑：
     `spheroidization_wire_entry_end_time` 或 `spheroidization_wire_entry_total_duration`
     为 null 时——
     - 原 `abnormal_type` 为 0/None → 改 2，`abnormal_reason` 写「进线结束时间缺失（PLC 未采集到喂丝结束）」
     - 原 `abnormal_type` 非 0 → 保持 type，`abnormal_reason` = 原 reason +「；」+ 缺失说明（原 reason 为空则不加分隔）
     - `spheroidization_abnormal` 用 `abnormal_flag(payload["abnormal_type"])` 重算
   - 位置在 service.py 回捞（`backfill_plc_from_all_plc`，service.py:289）之后
     （`build_payload_from_heat` 调用在 service.py:308），即"回捞过仍缺失"才标记。
   - `build_payload`（reactions 老路径）、`backfill_plc_from_all_plc`、游标、上传队列、
     检测侧一律未动。
3. `tests/test_merge_missing_feed_end.py`（新增，只增不改老断言）

## 验收测试函数名（tests/test_merge_missing_feed_end.py）
| 验收项 | 测试函数 |
|---|---|
| ① null 且原 type=0 → type=2、abnormal=1、reason 含「进线结束时间缺失」 | `test_进线结束null且原type为0_改成type2异常` |
| ② null 且原 type=5（带原 reason）→ type 保持 5、abnormal=1、reason=原 reason＋分隔＋缺失说明 | `test_进线结束null且原type非0_保持type追加reason` |
| ③ 进线结束/时长非 null → payload 与原行为完全一致（回归，全字段逐值断言） | `test_进线结束非null_行为与原有一致回归` |

## pytest 数字
- 改动前基线：`243 passed`（`.venv/bin/python -m pytest tests/ -q`）
- 改动后全量：**`246 passed`**（基线 243 + 新增 3，无失败无跳过，只增不减）

## build 结果
- `npm run build`（frontend/，含 `vue-tsc -b` 类型检查 + `vite build`）：**成功**
  （55 modules transformed，✓ built in 353ms）

## 趋势图默认区间的新值
- `start` = 今天往前推 29 天，`end` = 今天（含两端共 30 天），格式 `YYYY-MM-DD`
  （与 `today()` 一致）。例：今天 2026-11-03 时，start=2026-10-05、end=2026-11-03。

## 遗留问题
- 无。
- 备注（非遗留）：回捞失败仍缺的炉次现在会带着 type=2 正常入库（不再依赖 422 死信路径发现缺口），
  死信附注 `plc_backfill_note` 逻辑未动、对回捞失败场景依旧生效（现有
  `test_no_matching_row_dead_letter_note` / `test_missing_all_plc_file_is_silent` 全绿，未改老断言）。
