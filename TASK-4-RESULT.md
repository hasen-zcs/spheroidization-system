# TASK-4 自检结果：进线结束/进线时长放宽为可空

日期：2026-11-03。全部规则执行完毕，验收全绿。

## 一、改动的文件（git 工作区，未 commit）

| 文件 | 改动 |
|---|---|
| `app/infrastructure/database/schema.sql` | 仅 `SpheroidizationRecord` 建表语句里两列去掉 `NOT NULL`，注释改为「（PLC 采不到时为空）」；其它列（含 `spheroidization_wire_entry_start_time`、`spheroidization_weight`）一律未动 |
| `app/domain/spheroidization/entities.py` | 两字段改为 `str \| None = None` / `float \| None = None`。因 dataclass 要求带默认值字段排在无默认值字段之后，把无默认值的 `spheroidization_weight`、`standard_spheroidization_time` 前移（全部构造点都是关键字传参，已核实 create.py / sqlite.py `_to_entity(**dict(row))` / gen_perf_data.py，无位置传参） |
| `app/schemas/spheroidization.py` | 请求模型两字段改 `str \| None = None` / `float \| None = None`；响应模型同样改 `str \| None` / `float \| None`；原「表上这几列都是 NOT NULL，所以这里也都是必填」注释改为只描述 start/weight 必填、end/时长可空。`to_response` 对这两字段是直接透传、无 `str()`/`round()`，None 天然能过，未改 |
| `app/application/spheroidization/create.py` | `execute` 与 `execute_idempotent` 两处签名中两字段改 `str \| None = None` / `float \| None = None`（同样把 `spheroidization_weight` 前移以满足默认值排序；全部调用点均为关键字传参）。全文检查过：无对这两字段的非空断言/自洽校验；`_payload_sha` 里时长本就走 None 安全的 `_r3()`，结束时间原样进 JSON（None 合法），指纹对 None 稳定，未新增任何会拒 None 的校验 |
| `app/infrastructure/database/sqlite.py` | **未改**。确认 INSERT 为参数化绑定（None → SQL NULL）、SELECT 走 `**dict(row)`，读写路径无 `str()`/算术/长度判断等对 None 会炸的操作 |
| `scripts/migrate_db.py` | 新增 v5（详见下节） |
| `frontend/src/api/index.ts` | `SpheroidizationRecord`（约 39~40 行）与 `CreateSpheroidizationInput`（约 112~113 行）两处：`string` → `string \| null`、`number` → `number \| null`。未引入任何新依赖；展示层 `display()` 本就接受 null（返回「—」），三个 .vue 文件未改 |
| `tests/test_nullable_wire_entry.py` | 新增（只增不改，老测试断言零改动） |

`merge/`、检测相关代码、`abnormal_type`/`abnormal_reason` 语义、老测试文件：全部未动（git status 核实）。

## 二、迁移 v5

- **判定函数**：`scripts/migrate_db.py` 新增 `_needs_nullable_relax(conn) -> bool`——读 `sqlite_master` 里 `SpheroidizationRecord` 的建表 DDL，`spheroidization_wire_entry_end_time` / `spheroidization_wire_entry_total_duration` 任一列声明后仍带 `NOT NULL` 即返回 True。
- **并入判定**：`_is_migrated()` 追加 `and not _needs_nullable_relax(conn)`；`migrate()` 的 `needs_rebuild` 条件追加 `or _needs_nullable_relax(conn)`。
- **复用既有重建路径**：没有另写重建逻辑。「列齐全但两列仍 NOT NULL」的 v4 老库命中 `needs_rebuild`，走原有那段：`_main_table_ddl()` 读改后的 schema.sql → 建 `SpheroidizationRecord__new`（天然可空）→ 按共有列 `INSERT ... SELECT` 拷数据 → **行数对不上抛错回滚** → `verify_schema` 自检；温度搬运等 v1→v4 逻辑原样未动。
- **幂等验证方式**：重建后 DDL 不再含这两列的 NOT NULL，`_needs_nullable_relax` 转 False → 二次 `migrate` 打印「已经是正式版结构，无需迁移。」直接返回 0。测试 `test_迁移v5_二次运行幂等不重建` 断言：二次运行 rc==0、stdout 以该句结尾（没有再走备份/建表/重建段）、DDL 与行数前后一致。

## 三、验收测试（均在 `tests/test_nullable_wire_entry.py`，5 个）

| 验收点 | 测试函数 |
|---|---|
| 接口：两字段=null POST 200 入库；GET 详情两字段原样返回 null；库里是真 NULL；abnormal 保持 0 不被置 1（数据缺口≠工艺异常） | `test_进线结束和时长为null也入库且详情原样返回null` |
| 接口（合并层 heat 口径）：带 device_id/external_id、两字段不传（默认 None）→ 200；同内容重放 existing=true 命中、不重复建 | `test_幂等路径同样接受null且重放命中` |
| v5 判定：v4 老库（两列 NOT NULL）判「未迁移」；新版空库判「已迁移」且 `_needs_nullable_relax` 为 False | `test_v5判定_老库识别为新库不识别` |
| v5 迁移：老库（2 行非空数据）跑 migrate → ① 两列可空（能插两列为 NULL 的新行）② 原 2 行数据/行数不丢 | `test_迁移v5_放开两列且数据不丢` |
| v5 幂等：二次 migrate 返回 0、不重建、DDL/行数不变 | `test_迁移v5_二次运行幂等不重建` |

老结构库的造法：取当前 schema.sql 主表 DDL 后给这两列加回 `NOT NULL`（与正式版逐字仅差这两列约束），建齐 v3/v4 表，插 2 行这两列非空的记录。

## 四、数字

- `.venv/bin/python -m pytest tests/ -q` → **243 passed**（基线 238 + 新增 5，只增不减，老断言未改）
- `frontend` 下 `npm run build`（vue-tsc 类型检查 + vite）→ **成功**（55 modules，built in ~618ms），类型放宽后 TS 无报错
- 改动前基线复跑确认 238 全绿；改动后全量复跑 243 全绿

## 五、遗留问题

无。

备注（非问题）：
- `entities.py` / `create.py` 因 Python 语法（带默认值参数/字段必须排在无默认值之后）把 `spheroidization_weight` 前移了位置，纯顺序调整，全部调用点均为关键字传参，已全量测试验证。
- 迁移脚本每次真实迁移仍会在 `data/backups/` 生成备份（既有行为）；测试里已通过 monkeypatch 把备份目录指到临时区，仓库无测试残留。
