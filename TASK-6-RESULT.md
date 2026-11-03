# TASK-6 结果

## 改动（只动了 `app/infrastructure/database/sqlite.py` 的 Spheroidization 仓储类，3 处）

| 方法 | 改动前 | 改动后 |
|---|---|---|
| `list_page`（分页列表） | `ORDER BY spheroidization_record_id DESC` | `ORDER BY detection_time DESC, spheroidization_record_id DESC` |
| `list_abnormal`（异常页） | `ORDER BY spheroidization_record_id` | `ORDER BY detection_time DESC, spheroidization_record_id DESC` |
| `list_all`（全量/导出） | `ORDER BY spheroidization_record_id` | `ORDER BY detection_time ASC, spheroidization_record_id ASC` |

- `list_page` / `list_abnormal` 降序：最新检测在前，与老板要求一致；
- `list_all` 保持升序：CSV 导出/全量拉取按时间正序是导出惯例；
- 主键一律做次级排序键：同一检测时间多条时顺序稳定，分页翻页不漂移；
- `list_page` 处加了注释，说明为什么（补录/回补的历史数据主键晚于检测时间，光按主键排会让旧时间记录顶在最前，"表是乱的"）；
- detection_time 是 TEXT（`YYYY-MM-DD HH:MM:SS.fff`，NOT NULL），字符串序=时间序，直接排；
- 其他仓储类（Standard/FlashSegment/Review/Temperature/SwitchLog/User 等）一律未动；
- 未改：merge/ 目录、检测、auth、schema.sql（纯 ORDER BY，无 schema 变更）；未 git commit。

## 测试

新增 `tests/test_list_time_order.py`，5 条用例（直接打在 `SqliteSpheroidizationRepository` 仓储层）：

1. `list_page` 第 1 页按检测时间降序：先插 3 条 11-03（id 1-3），再补录 2 条 10-30 / 11-02（id 4-5），补录的旧时间记录不得出现在 11-03 记录之前；
2. `list_page` 翻页（limit=3 两页）不重不漏、顺序为时间降序；
3. 同一 detection_time 两条：`list_page` 按主键降序稳定、`list_all` 按主键升序兜底；
4. `list_abnormal` 按检测时间降序（混入一条正常记录，确认筛选不受影响）；
5. `list_all` 按检测时间升序（补录的旧记录沉在导出最前面）。

## 验收

- 变更前基线：`246 passed`
- 变更后全量：`.venv/bin/python -m pytest tests/ -q` → **251 passed**（246 + 新增 5，只增未减）
- 变异验证：把 `list_page` / `list_abnormal` 临时改回按主键排序后，新用例中 3 条立即失败，确认用例真的锁住了时间排序行为，随后已还原。
