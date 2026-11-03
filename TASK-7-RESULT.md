# TASK-7 自检结果

## 改的文件
1. `merge/assemble.py`（只动 heat 主源路径）
   - 新增模块级常量 `FEED_END_LAG_LIMIT_S = 90.0`（assemble.py:28 附近）。
   - `build_payload_from_heat` 内、TASK-5 缺失检查**之前**新增迟到判定：
     - `lag = span_seconds(spheroidization_end_time, spheroidization_wire_entry_end_time)`
       （方向：喂丝结束 − 亮光结束，正数 = 迟到）；
     - 仅当 lag 非 None 且 **严格大于** 90.0 时判定迟到（亮光结束缺失算不出 lag、
       喂丝结束缺失、lag ≤ 90s 含恰好 90.0s，均不判定、原样不动）；
     - 判定迟到时：`spheroidization_wire_entry_end_time` / `spheroidization_wire_entry_total_duration`
       置 None；reason 写「喂丝结束信号迟到（亮光结束后 +{lag:.0f}s 才到达，原值弃用）」；
       类型处理与 TASK-5 完全一致——原 type 0/None → 改 2 + 写 reason，
       非 0 → 保持 type + reason 用「；」追加；`spheroidization_abnormal` 用
       `abnormal_flag` 重算。
   - TASK-5 缺失检查加守卫 `and not feed_end_lag_rejected`：迟到判定已置 null 且
     已写迟到原因的记录，不再补「进线结束时间缺失（PLC 未采集到喂丝结束）」——
     迟到炉的 `abnormal_reason` 里**只有**迟到那一句。
   - `build_payload`（reactions 老路径）、`backfill_plc_from_all_plc`（回捞）、游标、
     上传队列、service.py 一律未动。
2. `frontend/src/views/Spheroidization.vue`（球化记录/异常记录列表同组件，一处改动两表同生效；
   任务书所写 `Records.vue` 是布局壳，表格实际在此组件）
   - 表格在「实际进线时间」（进线时长）列后新增「进线-亮光差」列（表头 + 行）：
     - 值 = `spheroidization_wire_entry_total_duration - actual_spheroidization_time`，
       `toFixed(1)` + "s"；任一为 null/undefined → 显示「—」（沿用现有 `display` 口径）
     - 差值 > 90s → 暗赭色 `#8a3b2e`（.feed-lag-late）+「迟到」小字（.feed-lag-late-mark, 11px）
     - 新增脚本函数 `feedLagDiff` / `feedLagText` / `isFeedLagLate`，阈值常量
       `FEED_END_LAG_LIMIT_S = 90`，与后端 90s 口径一致
   - 未改排序、分页、筛选逻辑；未引入新依赖、新色板体系（仅按任务指定加任务指定的
     #8A3B2E 一个色值）。
3. `tests/test_merge_feed_end_lag.py`（新增，6 条）
4. `tests/test_merge_missing_feed_end.py`（1 处夹具修正，非断言逻辑变更）
   - `test_进线结束非null_行为与原有一致回归` 原夹具喂丝结束取亮光结束 +205s，
     在 TASK-7 新规则下属于迟到形态，会被置 null，与"非 null 原样透传"的回归意图冲突。
     夹具改为亮光结束 +4s（正常尾段，09:02:04.000 / 99.0s），回归意图（非迟到非 null
     原样透传）保持不变，断言结构未动。

## 验收测试函数名（tests/test_merge_feed_end_lag.py）
| 验收项 | 测试函数 |
|---|---|
| ① 喂丝结束 = 亮光结束 +120s、原 type 0 → 结束/时长置 None、type=2、reason 含「+120」且不含「未采集到喂丝结束」 | `test_迟到120s原type0_置null改type2且不重复缺失原因` |
| ② 原 type 5（带原 reason）+ 迟到 → type 保持 5、reason = 原 reason +「；」+ 迟到句 | `test_迟到且原type5_保持type追加迟到句` |
| ③ lag=30s → 字段原样不动（全字段逐值回归） | `test_lag30s_字段原样不动` |
| ④ 恰好 90.0s → 不动（严格大于才算迟到） | `test_lag恰好90s_不动_严格大于才算迟到` |
| ⑤ 亮光结束缺失 + 喂丝结束存在 → 不动（走不到迟到判定） | `test_亮光结束缺失_走不到迟到判定_不动` |
| ⑥ 喂丝结束缺失（TASK-5 原有场景回归）→ type 2 +「未采集到喂丝结束」 | `test_喂丝结束缺失_原TASK5场景回归` |

## 变异自检（防测试空转）
对实现做了 3 处突变再跑测试，均被捕获后已还原（还原后 diff 与改动一致）：
- `>` 改 `>=`（90s 边界放行）→ 用例④ FAILED
- 删掉 TASK-5 块的 `and not feed_end_lag_rejected` 守卫（重复写 reason）→ 用例① FAILED
- 反转 lag 方向（亮光结束 − 喂丝结束）→ 用例① FAILED

## pytest 数字
- 改动前基线：`251 passed`（`.venv/bin/python -m pytest tests/ -q`）
- 改动后全量：**`257 passed`**（基线 251 + 新增 6，无失败无跳过，只增不减）

## build 结果
- `cd frontend && npm run build`（含 `vue-tsc -b` 类型检查 + `vite build`）：**成功**
  （55 modules transformed，✓ built in 388ms）

## 红线核对
- schema.sql 未动；未加异常类型（迟到沿用类型 2 语义）
- merge/service.py 回捞逻辑未动；auth 未动；老 reactions 路径、游标、上传队列未动
- 未 git commit（工作区改动：merge/assemble.py、frontend/src/views/Spheroidization.vue、
  tests/test_merge_missing_feed_end.py、tests/test_merge_feed_end_lag.py、本结果文件）
- 全程未提问、未等确认

## 遗留问题
- 无。
- 备注（非遗留）：已入库的历史迟到炉（3.3% 那批，差值最大 548s）不会被本次改动追溯修正，
  前端新列对这类老数据会按 >90s 显示暗赭色 +「迟到」标记，供人工识别；
  新入队的炉次从合并层起已按 NULL + 类型 2 处理。
