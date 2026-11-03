# TASK-2：报表增强（班次/标准/趋势 + Excel 导出 + 打印）（本地开发任务书）

## 背景
本工程是 FastAPI + SQLite 后端（`app/`）+ Vue3 前端（`frontend/`）。
现有报表：`GET /api/reports/summary`（区间统计：总量/类型分布/异常率/时长/温度覆盖/按天分布）
+ `GET /api/reports/export`（CSV 流式导出）。前端 `frontend/src/views/Reports.vue`。
本任务补 4 样东西：班次维度、标准维度、趋势序列、Excel 导出、打印（打印是前端功能）。

## 规则（照此实现，不许自由发挥）
1. `summary` 响应 data 里**新增** 3 个块（原有字段一个都不许动）：
   - `shifts`：两班制统计。班次口径写成服务模块顶部常量，默认
     白班 = 08:00(含)~20:00(不含)，夜班 = 20:00(含)~次日08:00(不含)。
     记录归属班次的时刻字段：与现有「按天分布」用的时刻字段保持一致（先读现有代码确认是
     detection_time 还是 wire_entry_end，沿用同一个，别换口径）。
     每个班次输出：`{shift: "白班"|"夜班", total, abnormal, normal, avg_actual_time}`
     （avg_actual_time 只对 actual_spheroidization_time 非空的记录求平均，4 位小数 round；无数据为 null）。
   - `standards`：按 `standard_record_id` 分组（该列已存在于 SpheroidizationRecord，是溯源外键）。
     JOIN `StandardRecord` 取 `created_at`、`created_by`、`standard_spheroidization_time`。
     每组输出：`{standard_record_id, standard_time, standard_created_at, standard_created_by,
     total, abnormal, avg_actual_time}`（avg 口径同 shifts）。
   - `trend`：区间内逐日升序序列 `[{date: "YYYY-MM-DD", total, abnormal, abnormal_rate, avg_actual_time}]`，
     abnormal_rate 保留 4 位小数；某天无数据 total=0、rate=0、avg=null，序列不许缺天（按天补齐）。
2. 新增接口 `GET /api/reports/export/excel`：参数与 CSV 导出一致（start/end/type），
   权限与 CSV 一致（page:records，游客 401 走统一信封）。
   用 `openpyxl` 的 **write_only** 模式流式生成 .xlsx（别一次性把整表 load 进内存），
   文件名 `spheroidization_YYYYMMDD.xlsx`，Content-Type 用 openpyxl 的
   `openpyxl...EXCEL` 默认即可（`application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`）。
   表头与 CSV 导出一致（复用 `CSV_HEADER` 语义，中文列名）。
   `requirements.txt` 追加 `openpyxl>=3.1`（本地 pip 安装后再测试）。
3. 前端 `Reports.vue`（风格与现有页面一致，别引入任何新前端依赖）：
   - 班次统计表、标准统计表（三线表风格，无竖线）
   - 趋势图：手写 inline SVG 折线（异常率或数量均可，x=日期，带简单轴刻度即可，禁引入图表库）
   - 「导出 Excel」按钮：调新接口，下载方式照现有 CSV 下载逻辑
   - 「打印」按钮：`window.print()`；在 `frontend/src/style.css` 加 `@media print` 规则
     （隐藏按钮/导航/非报表元素，表格保留，页边距合理）
4. 测试（`tests/test_reports.py` 扩展）：
   - 合成数据覆盖班次边界：07:59（夜班）/08:00（白班）/19:59（白班）/20:00（夜班）各一条，断言归属正确
   - standards 分组：两套标准各若干条，断言 total/abnormal/avg 与 JOIN 字段正确
   - trend：区间 3 天、中间一天无数据，断言序列 3 项、缺天补齐、rate 正确
   - excel 接口：登录 200 + 文件能被 openpyxl 读回 + 行数=CSV 同参数行数；游客 401
   - 原有 summary 各字段回归：老测试不许改断言（只许加）

## 红线
- 不许改 summary 原有字段、不许改 CSV 导出行为
- 不许引入新前端依赖（SVG 手写）
- 不许动 merge/ 目录、检测相关代码、auth/登录逻辑
- 全量 `python3 -m pytest tests/ -x -q` 必须全绿（基线 231+，只增不减）
- 前端 `npm run build` 必须成功
- 不许提问、不许等确认

## 产出
1. 代码改动（仓库内直接改）
2. 自检结果写入仓库根目录 `TASK-2-RESULT.md`：改的文件、每条验收测试对应函数、
   pytest 数字、npm build 结果、班次口径常量位置、遗留问题
