# TASK-7 喂丝结束信号迟到容错 + 进线-亮光差值列

## 背景（数据分析结论，老板已批准方案）
526 炉统计：正常炉「进线时长-亮光时长」中位 17.8s（点火延迟 13s + 尾段 3.5s，物理结构）。
但 17 条炉（3.3%）差 >60s，最大 548s：亮光早已熄灭，PLC 喂丝结束位（129.3）几分钟后才翻转，
导致进线时长被记成假的大值（如 610s）。老板拍板：
**结束位晚于亮光结束 90s 以上才到达 → 判定为信号迟到，进线结束/时长按无效处理（记 NULL + 类型2语义），原始值写入原因可追溯。**

## A. merge/assemble.py（heat 主源组包，build_payload_from_heat，约 162 行）

在**现有 TASK-5 缺失检查之前**加迟到判定：

```
模块级常量：FEED_END_LAG_LIMIT_S = 90.0
```

判定条件（三个同时满足）：
1. `spheroidization_end_time`（亮光结束）非空
2. `spheroidization_wire_entry_end_time`（喂丝结束）非空
3. `span_seconds(亮光结束, 喂丝结束) > FEED_END_LAG_LIMIT_S`（注意方向：喂丝结束 - 亮光结束，正数=迟到）

满足时：
- `payload["spheroidization_wire_entry_end_time"] = None`
- `payload["spheroidization_wire_entry_total_duration"] = None`
- reason：`"喂丝结束信号迟到（亮光结束后 +{lag:.0f}s 才到达，原值弃用）"`，lag=迟到秒数
- 类型处理**与 TASK-5 缺失检查完全一致**：当前 type 为 0/None → 改 2 + 写 reason；非 0 → 保持 type + reason 追加（用「；」连接）
- 随后 TASK-5 的缺失检查会自然接住（end/duration 已置 None），**不要重复写 reason**——
  所以 TASK-5 那段要改成「end/duration 为 None 且还没有缺失原因时才补」，
  避免同一条记录出现「信号迟到…」+「进线结束时间缺失（PLC 未采集到喂丝结束）」两句。
  验收标准：迟到炉的 abnormal_reason 里**只有**迟到那句，不含「未采集到喂丝结束」。

不判定（保持原样）：
- 亮光结束缺失（算不出 lag）
- 喂丝结束缺失（走原 TASK-5 路径）
- lag ≤ 90s（含恰好 90.0s）

**只改 heat 路径（build_payload_from_heat）**。老 reactions 路径（build_payload）、回捞、游标、上传队列一律不动。

## B. 前端 frontend/src/views/Records.vue（记录列表）

表格加一列「进线-亮光差」：
- 值 = `spheroidization_wire_entry_total_duration - actual_spheroidization_time`，1 位小数 + "s"
- 任一为 null → 显示「—」
- > 90s 的值用暗赭色（#8A3B2E）+ 可加「迟到」小字标记（沿用站点现有配色变量，不许引入新色板）
- 列位置放在「进线时长」列后面；表头、表格行、（如有）异常记录表同组件则一起生效
- 不改排序、分页、筛选逻辑

## C. 测试 tests/test_merge_feed_end_lag.py（6 条）
1. 喂丝结束 = 亮光结束 +120s，原 type 0 → end/duration 置 None，type=2，reason 含「+120」且**不含**「未采集到喂丝结束」
2. 原 type 5（已有 reason）+ 迟到 → type 保持 5，reason = 原 reason +「；」+ 迟到句
3. lag=30s → 字段原样不动
4. 恰好 90.0s → 不动（边界，严格大于才算迟到）
5. 亮光结束缺失 + 喂丝结束存在 → 不动（走不到迟到判定）
6. 喂丝结束缺失（原有 TASK-5 场景回归）→ type 2 +「未采集到喂丝结束」，行为与改动前一致

## 验收
- `.venv/bin/python -m pytest tests/ -q` 全量通过（基线 251，只能增不能减）
- `cd frontend && npm run build` 成功
- 红线：不许改 schema.sql、不许加异常类型、不许动 merge/service.py 回捞逻辑、不许动 auth、不许 git commit、不许提问、不许等确认
- 产出 TASK-7-RESULT.md
