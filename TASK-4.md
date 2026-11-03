# TASK-4：进线结束/进线时长放宽为可空（容忍级，缺字段降级入库不丢炉）（本地开发任务书）

## 背景
本工程是 FastAPI + SQLite 后端（`app/`）+ Vue3 前端（`frontend/`）的球化管理系统。
球化记录表 `SpheroidizationRecord` 有两列 `spheroidization_wire_entry_end_time`（进线结束时间，TEXT）
和 `spheroidization_wire_entry_total_duration`（进线总时长，REAL），当前是 `NOT NULL`。
请求模型（Pydantic）也把它们设为必填。

现场问题：PLC 偶尔采不到「喂丝结束」信号 → 上游（合并层 heat 路径）组包时这两字段为 null →
后端 422 拒收整条记录 → 该炉次从管理系统彻底消失（5 天丢了 5 炉）。
本任务把这两字段放宽为**可空**，缺了就空着入库，**炉次不再丢**（数据缺口表现为空字段，前端显示「—」）。

参考既有先例：亮光起止 `spheroidization_start_time`/`spheroidization_end_time`/`actual_spheroidization_time`
在 R1~R8 已放宽为可空（schema.sql 里它们就是不带 NOT NULL 的），本次照同样的口径处理进线这两列。

## 规则（照此实现，不许自由发挥）

### 1. 数据库 schema（`app/infrastructure/database/schema.sql`）
- `SpheroidizationRecord` 建表语句里，`spheroidization_wire_entry_end_time TEXT NOT NULL` → 去掉 `NOT NULL`（保留中文注释，改成「进线结束时间（PLC 采不到时为空）」）。
- `spheroidization_wire_entry_total_duration REAL NOT NULL` → 去掉 `NOT NULL`（注释改成「进线总时长（PLC 采不到时为空）」）。
- **只动这两列**，其它列（含 `spheroidization_wire_entry_start_time`、`spheroidization_weight`）一律不动。

### 2. 实体（`app/domain/spheroidization/entities.py`）
- `SpheroidizationRecord` dataclass 里这两字段改为：
  - `spheroidization_wire_entry_end_time: str | None = None`
  - `spheroidization_wire_entry_total_duration: float | None = None`

### 3. 请求/响应模型（`app/schemas/spheroidization.py`）
- **请求模型**（约 102~103 行，`spheroidization_wire_entry_end_time: str` / `..._total_duration: float`）
  改为 `str | None = None` / `float | None = None`。
- **响应模型**（约 250~251 行）同样改为 `str | None` / `float | None`。
- `to_response` 转换器（约 327~331 行）现在是对 record 字段直接透传，None 天然能过，**确认它不会在 None 上报错**（若它对这些字段做了 `str()`/`round()` 之类非 None 处理，要加 None 保护）；其余字段一律不动。
- 请求模型里那条注释「表上这几列都是 NOT NULL，所以这里也都是必填」要同步改成只描述 start/weight 必填、end/时长可空，避免误导。

### 4. 创建逻辑（`app/application/spheroidization/create.py`）
- 两个 `create_*` 方法签名里 `spheroidization_wire_entry_end_time: str` / `..._total_duration: float`
  改为 `str | None = None` / `float | None = None`（约 90/91 行 与 136/137 行两处）。
- 取数处 `fields["spheroidization_wire_entry_end_time"]` 等保持原样（None 会正常透传进实体）。
- **全文检查 create.py 有没有对这两字段「非空」的断言或自洽校验**，若有则对 None 放行；若无则不动。不许新加任何会拒绝 None 的校验。

### 5. 仓储（`app/infrastructure/database/sqlite.py`）
- INSERT/SELECT 已是参数化绑定（约 131/132、153/154 行），None → SQL NULL 天然成立。
- **只确认**读写这两列的代码路径没有 `str()`/算术/长度判断等对 None 会炸的操作；有则加 None 保护，无则不动。

### 6. 迁移脚本（`scripts/migrate_db.py`）—— 本任务最 delicate 的部分，务必照既有模式
现状：`_is_migrated()` 只查「列齐全 + 无旧温度列 + 有 v3/v4 表」，**不查 NOT NULL**。
已经迁到 v4 的老库（列齐全）会被判「已迁移」直接返回，NOT NULL 约束原封不动。
必须新增一步（称 v5）：
- 新增判定函数（如 `_needs_nullable_relax(conn) -> bool`）：读 `sqlite_master` 里 `SpheroidizationRecord`
  的建表 DDL，若 `spheroidization_wire_entry_end_time` 或 `spheroidization_wire_entry_total_duration`
  后面仍带 `NOT NULL`，返回 True。
- `_is_migrated()` 里并入：`not _needs_nullable_relax(conn)` 才算「已迁移」；否则返回 False 继续走迁移。
- `migrate()` 里 `needs_rebuild` 条件并入 `_needs_nullable_relax(conn)`：
  这样「列齐全但这两列还是 NOT NULL」的库会走**既有的安全重建路径**（`_main_table_ddl()` 读的是改后的
  schema.sql → 新表就是可空的；建 `__new` 表 → `INSERT ... SELECT` 按共有列拷数据 → 行数对不上就回滚 →
  `verify_schema` 自检）。**不要另写一套重建逻辑，复用现有那段。**
- **幂等**：重建后两列不再带 NOT NULL，第二次跑 `migrate` 必须打印「已是正式版结构，无需迁移」并直接返回 0，不再重建。
- 温度搬运等既有 v1→v4 逻辑一律不动。

### 7. 前端（`frontend/src/api/index.ts`，**不许引入任何新依赖**）
- 约 39~40 行、112~113 行，这两个字段类型 `string` → `string | null`、`number` → `number | null`（两处接口类型都要改）。
- 展示层 `Spheroidization.vue`/`Monitor.vue` 已经用 `display()` 渲染（`display()` 对 null 返回「—」），**展示代码不用改**，只确认类型放宽后 TS 不报错。

### 8. 测试（`tests/` 扩展，基线 238，只增不改老断言）
- **接口验收**：构造一条带正常亮光/进线开始/重量、但 `spheroidization_wire_entry_end_time=null` 且
  `spheroidization_wire_entry_total_duration=null` 的记录 POST → 断言 200 成功入库；再 GET 详情，断言这两字段为 None/null 原样返回。
- **迁移 v5**：造一个「老结构」库（用**带 NOT NULL 的旧 DDL** 建 `SpheroidizationRecord` 并插 1~2 行含这两列非空值的数据，再建齐 v3/v4 表让 `_is_migrated` 的列检查通过），跑 `migrate`：
  断言 ① 迁移后这两列**不再**带 NOT NULL（能插一行这两列为 NULL 的新记录成功）② 原有行数据/行数不丢 ③ 再跑一次 migrate 幂等（不重建、返回 0）。
- **回归**：原有 summary/导出/幂等/分段等测试一个都不许改断言，必须全绿。

## 红线
- 只放宽「进线结束时间 + 进线总时长」两列，其它 NOT NULL 列一律不动。
- 不改 `abnormal_type`/`abnormal_reason` 语义（缺进线结束是**数据缺口**，不是工艺异常，不许把 abnormal 置 1、不许往 abnormal_reason 塞字）。
- 不改 `merge/` 目录、不改检测相关代码（合并层 heat 路径本来就在发 null，这次只是后端接受它）。
- 不造假数据：缺失就是 NULL，不许填占位时间戳/0。
- 迁移必须复用既有重建路径、必须幂等、必须行数校验+自检。
- 全量 `.venv/bin/python -m pytest tests/ -x -q` 必须全绿（基线 238+，只增不减）。
- 前端 `npm run build` 必须成功。
- 不许 git add/commit（改动留在工作区）。
- 不许提问、不许等确认，一次做完。

## 产出
1. 代码改动（仓库内直接改）。
2. 自检结果写入仓库根目录 `TASK-4-RESULT.md`：改的文件、每条验收测试对应函数名、pytest 数字、
   npm build 结果、迁移 v5 判定函数与幂等验证方式、遗留问题。
