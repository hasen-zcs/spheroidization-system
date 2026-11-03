# TASK-6 记录列表按检测时间自动排序

## 背景
球化管理列表接口 `/api/spheroidization`（分页查询）现在按主键 `spheroidization_record_id DESC` 排序。
主键=入库顺序。11-03 补录了 5 条检测时间更早的炉次（id 510-514，检测时间 10-30~11-02），
它们排在列表最前面，把 11-03 当天的记录挤到后面，老板看着「表是乱的」。
老板要求：**列表自动按检测时间排序**（最新的在最前面）。

## 改动（只改后端排序，前端不动）

1. `app/infrastructure/database/sqlite.py` 的 `list_page`（Spheroidization 仓储，约 238 行）：
   `ORDER BY {pk} DESC` 改为 `ORDER BY detection_time DESC, {pk} DESC`
   - detection_time 是 TEXT（`YYYY-MM-DD HH:MM:SS.fff`，NOT NULL），字符串序=时间序，直接排即可
   - 主键做次级排序，保证同一时刻多条时顺序稳定、分页不漂移
   - 注释写明为什么（补录/回补的历史数据主键晚于检测时间，按主键排会乱序）
2. `list_all` / `list_abnormal`（同文件 216 行附近）：
   同样改为 `ORDER BY detection_time ASC, {pk} ASC` / `detection_time DESC, {pk} DESC`
   - 原则：**所有查询路径同一套时间排序**，别让不同入口看到不同顺序
   - list_all 保持升序（它是给 CSV 导出/全量拉取用的，按时间正序是导出惯例）
   - list_abnormal 改降序（异常页展示，最新在前与分页列表一致）
   - 注意：如果 list_all 的现有调用方有依赖升序的断言，保持 ASC 不动即可
3. 其他仓储类（Standard/FlashSegment/UserAccount 等）一律不动——只动 Spheroidization 这一个仓储类。
   判断标准：该类的 `_table_name == "SpheroidizationRecord"`。

## 测试（新增 tests/test_list_time_order.py，3+ 条用例）
- 建库插 5 条：检测时间乱序 vs 主键乱序交叉（模拟补录：先插 3 条 11-03 的，再插 2 条 10-30 的）
- `list_page` 第 1 页：按 detection_time 降序，补录的旧时间记录不得出现在 11-03 记录之前
- 同一 detection_time 两条：按主键降序稳定
- `list_abnormal` 降序 / `list_all` 升序 各一条断言

## 验收
- `.venv/bin/python -m pytest tests/ -q` 全量通过（当前基线 246，只能增不能减）
- 不许改：merge/ 目录、检测、auth、schema.sql（这次纯 ORDER BY，无 schema 变更）
- 不许 git commit、不许提问、不许等确认
- 产出 TASK-6-RESULT.md：改了哪几处、测试数
