# TASK-8 管理员数据管理（后端）：软删除 + 处理状态修改 + 数据管理权限码

## 老板已拍板的规则
1. **四类数据全部软删除**（不物理删）：球化记录、检测标准、标准切换记录、球化复核记录
2. **处理状态只有管理员能改**（0↔1 可来回）
3. **权限**：新增权限码 `action:manage_data`，管理员拥有；可授予他人
4. 单独管理员页面（前端是 TASK-9，本轮不碰 frontend/）

## A. 权限码（app/core/permissions.py）
- 新增 `ACTION_MANAGE_DATA = "action:manage_data"`，加进 `ALL_PERMISSIONS`
- 顶部注释里「一共 9 个…action:* 五个」同步改成 10 个 / action:* 六个
- **不动** PUBLIC_PATHS

## B. Schema v6（app/infrastructure/database/schema.sql + scripts/migrate_db.py）
四张表各加三列（**全部可空，不做重建**，用 `ALTER TABLE ADD COLUMN`）：
```
deleted_at TEXT,     -- 软删除时刻，NULL=未删除
deleted_by TEXT,     -- 删除人（登录账号）
delete_reason TEXT   -- 删除原因，必填（应用层校验）
```
表：`SpheroidizationRecord`、`StandardRecord`、`StandardSwitchLogs`、`ReviewRecord`

迁移要求：
- 版本号提到 v6，写进文件头注释（按现有 v1~v5 的写法）
- 幂等：列已存在就跳过（查 `PRAGMA table_info`），可重复跑
- 老数据 `deleted_at` 全为 NULL，行数前后一致，做行数校验
- 注意本库是 STRICT 表，加可空 TEXT 列合法

## C. 读路径过滤（**最容易漏，逐项核对**）
所有读取默认 `deleted_at IS NULL`：

1. `app/infrastructure/database/sqlite.py`
   - `SqliteSpheroidizationRepository`：`list_page`、`list_all`、`list_abnormal`、`count`、`get_by_id`
   - 标准仓储：列表、按 id 取、取当前标准（`latest`/`current` 这类）——**当前标准查询必须过滤**，否则删掉的标准还在生效
   - 切换日志仓储：列表
   - 复核仓储：按记录列、按 id 取
2. `app/application/reports/service.py`：**10 处** `FROM SpheroidizationRecord` 全部加 `deleted_at IS NULL`（含 where 拼接的那几处），复核统计那处 `FROM ReviewRecord` 也要加
3. `app/infrastructure/database/connection.py`：3 处统计/校验查询按语义加（若是完整性检查全表计数，可保留并注释说明）

**验收办法**：`grep -rn "FROM SpheroidizationRecord\|FROM StandardRecord\|FROM StandardSwitchLogs\|FROM ReviewRecord" app/` 逐个确认，漏一个报表数字就错。

## D. 新增管理员 API（新文件 app/api/admin.py，前缀 /api/admin）
全部 `Depends(require_permission(P.ACTION_MANAGE_DATA))`，全部写 AuditLog（actor 取登录账号）。

| 方法 | 路径 | 作用 |
|---|---|---|
| POST | `/records/{id}/delete` | 软删球化记录，body `{reason}` 必填 |
| POST | `/records/{id}/restore` | 恢复 |
| POST | `/standards/{id}/delete` | 软删标准，body `{reason}` |
| POST | `/standards/{id}/restore` | 恢复 |
| POST | `/switch-logs/{id}/delete` | 软删切换记录，body `{reason}` |
| POST | `/switch-logs/{id}/restore` | 恢复 |
| POST | `/reviews/{id}/delete` | 软删复核记录，body `{reason}` |
| POST | `/reviews/{id}/restore` | 恢复 |
| POST | `/records/{id}/processed` | 改处理状态，body `{processed: 0|1, reason}` |

规则：
- `reason` 去空格后为空 → 400「请填写原因」
- **当前生效标准不许软删** → 400「该标准当前生效，请先切换标准后再作废」
- 已删除的再删 → 幂等成功（不报错，不重复写审计）
- 恢复时要求确实处于已删除态，否则幂等成功
- `processed=1` → 写 `processed_by`(登录账号) + `processed_at`(当前时间)；`processed=0` → 三字段清空
- 目标不存在 → 404
- 响应统一用 `ok()/fail()` 信封，与现有接口一致

审计动作码（app/domain/audit/entities.py 的 AuditAction / AuditTarget 里新增）：
```
DELETE_RECORD / DELETE_STANDARD / DELETE_SWITCH_LOG / DELETE_REVIEW / RESTORE_* / CHANGE_PROCESSED
AuditTarget 补 SWITCH_LOG
```
detail 里记 `{before: {...}, after: {...}}` 关键字段（含 reason），**不含图片 BLOB**。

## E. 列表接口支持看已删除（给恢复用）
球化记录列表 / 标准列表 / 切换日志列表 / 复核列表加可选参数 `include_deleted: bool = False`：
- 默认 False（业务页行为不变）
- True 时**必须**同时校验 `action:manage_data` 权限，无权限 403
- 已删除行的响应体要带上 `deleted_at` / `deleted_by` / `delete_reason`（前端要展示）

## F. 测试 tests/test_admin_data.py（至少 12 条）
1. 软删记录后：列表不返回、count 减 1、报表 summary 总数减 1
2. 软删记录后 get_by_id 返回 None（或 404）
3. 软删记录后 UploadLedger / FlashSegment **行数不变**（证明没物理删/没级联）
4. 当前生效标准软删 → 400，库里 deleted_at 仍 NULL
5. 非当前标准软删 → 成功，`/api/standards/current` 不受影响
6. 软删标准后：标准下拉列表不含它
7. 软删切换日志 → 列表不含，标准仍可查
8. 软删复核记录 → 该记录的复核列表不含
9. `processed: 1` → 三字段齐；`processed: 0` → 三字段清空（往返）
10. 无 `action:manage_data` 权限 → 403；游客 → 401
11. 每次操作写 1 条 AuditLog，actor/action/target_id 正确
12. 重复删除幂等：第二次不新增审计行
13. 迁移脚本跑两遍幂等，行数不变

## G. 红线
- 不动 frontend/、不动 merge/、不动检测模块、不动 auth 登录逻辑
- 不做物理删除（一条 DELETE FROM 都不许写）
- 不许 git commit、不许提问、不许等确认
- 全量 pytest 必须通过（基线 257，只能增）
- 产出 TASK-8-RESULT.md（改了哪些文件、测试数、grep 核对结果）
