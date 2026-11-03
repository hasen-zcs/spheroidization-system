# TASK-8 完成结果：管理员数据管理（后端）软删除 + 处理状态 + 权限码

全量 pytest：**273 passed**（基线 257 + 新增 16，无失败、无跳过）。

## A. 权限码
- `app/core/permissions.py`：新增 `ACTION_MANAGE_DATA = "action:manage_data"`，加入 `ALL_PERMISSIONS`；顶部注释 `9 个 / action:* 五个` → `10 个 / action:* 六个`。`PUBLIC_PATHS` 未动。

## B. Schema v6
- `app/infrastructure/database/schema.sql`：四张表（`SpheroidizationRecord` / `StandardRecord` / `StandardSwitchLogs` / `ReviewRecord`）各加三列 `deleted_at` / `deleted_by` / `delete_reason`（全部可空 TEXT，NULL=未删除）；文件头加 v6 段说明。
- `scripts/migrate_db.py`：
  - 新增 `SOFT_DELETE_TABLES` / `SOFT_DELETE_COLUMNS`、`_has_v6_columns()`、`_ensure_v6_columns()`。
  - `_ensure_v6_columns` 用 `ALTER TABLE ADD COLUMN`（不重建表），逐列查 `PRAGMA table_info` 幂等跳过，加完做**行数前后一致校验**（不一致即抛错回滚）。
  - `_is_migrated()` 增加 v6 列判断；两条迁移分支（只加列 / 重建）都在提交前调 `_ensure_v6_columns`。
  - 文档串补第 7 条 v6 说明。
- `app/infrastructure/database/connection.py`：`REQUIRED_COLUMNS` 增补四表的三列 → 未迁移老库启动即失败（指向迁移脚本），fail-fast。

## C. 读路径过滤（`deleted_at IS NULL`）
- `app/infrastructure/database/sqlite.py`：
  - 球化仓储：`get_by_id` / `list_all` / `list_abnormal` / `list_page` / `count` 全部默认过滤（`list_page`/`count` 走 `_where_clause`，新增 `include_deleted` 开关）。
  - 标准仓储：`get_by_id` / `get_current`（当前标准回退查询，**已过滤**，删掉的标准不会继续生效）/ `get_history`。
  - 复核仓储：`list_by_spheroid_id` / `get_latest_results`（子查询里过滤，已删复核不算“最新”）。
  - 切换日志仓储：`list_all`。
- `app/application/reports/service.py`：`_where` 基础条件恒带 `deleted_at IS NULL`，覆盖 summary 里全部 10 处 `FROM SpheroidizationRecord`（含 `{where}` 拼接、`_tail` 挪动的 durations/export、`covered`/`by_gun` 子查询）；标准维度 JOIN 一处因两表都有 `deleted_at` 列，显式限定为 `s.deleted_at IS NULL`；`_latest_reviews` 的 `FROM ReviewRecord` 也加过滤。

## D. 新增管理员 API
- `app/api/admin.py`（新文件，前缀 `/api/admin`）：9 个接口（records/standards/switch-logs/reviews 各自的 delete/restore + records 的 processed），全部 `Depends(require_permission(P.ACTION_MANAGE_DATA))`，全部写 `AuditLog`（actor 取登录账号）。
  - `reason` 去空格为空 → 400「请填写原因」
  - 当前生效标准软删 → 400「该标准当前生效，请先切换标准后再作废」
  - 已删再删 / 未删再恢复 → 幂等成功（不重复写审计）
  - `processed=1` 写 `processed_by`(登录账号)+`processed_at`；`processed=0` 三字段清空
  - 目标不存在 → 404；响应统一 `ok()/fail()` 信封
  - 审计 detail 记 `{before, after}` 关键字段（含 reason），**不含图片 BLOB**
- `app/domain/audit/entities.py`：`AuditAction` 增 `DELETE_RECORD/DELETE_STANDARD/DELETE_SWITCH_LOG/DELETE_REVIEW` + 对应 `RESTORE_*` + `CHANGE_PROCESSED`；`AuditTarget` 增 `SWITCH_LOG`。
- `app/main.py`：`import admin` + `app.include_router(admin.router)`。

## E. 列表接口支持看已删除（给恢复用）
- 四个列表加可选参数 `include_deleted: bool = False`，默认 False（业务页行为不变）；True 时校验 `action:manage_data`（游客 401 / 无权限 403），已删除行响应带 `deleted_at`/`deleted_by`/`delete_reason`：
  - 球化记录列表：`GET /api/spheroidization`（参数级权限校验写在路由内，`?include_deleted=true` 绕不开）
  - 标准列表：`GET /api/standards/history`
  - 切换日志列表：`GET /api/standards/switch-logs`
  - 复核列表：`GET /api/reviews/{record_id}`
- 打通链路：仓储 → 用例 → 路由；`app/schemas/{spheroidization,standard,review}.py` 的 `to_response` 补三字段（未删除时均为 `None`）。

## F. 测试
- `tests/test_admin_data.py`（新文件，16 条），覆盖任务书 F 节全部 13 个验收点：
  1 软删记录→列表/count/报表 summary 减；2 软删→详情 404 且 `get_by_id` None；3 软删→UploadLedger/FlashSegment 行数不变（无物理删/无级联）；4 当前生效标准软删→400 且 `deleted_at` 仍 NULL；5 非当前标准软删→成功且 `/current` 不变；6 软删标准→历史列表不含；7 软删切换日志→列表不含、标准仍可查；8 软删复核→该记录复核列表不含；9 处理状态 1↔0 往返（三字段齐/清空）+ 原因必填；10 游客 401 / 无权限 403 / 有权限放行 + `include_deleted` 权限；11 每次操作写 1 条审计且 actor/action/target_id 正确、detail 不含图片；12 重复删除/恢复幂等不新增审计；13 迁移脚本跑两遍幂等、行数不变、`deleted_at` 全 NULL。
- 唯一改动的既有测试：`tests/test_api_frontend_parity.py` 第 198 行对复核响应做精确键集合断言，随契约新增 `deleted_at/deleted_by/delete_reason` 三键同步更新（其余精确断言均为“子集/信封”形式，不受影响）。

## grep 核对（任务书验收办法）
`grep -rn "FROM SpheroidizationRecord|FROM StandardRecord|FROM StandardSwitchLogs|FROM ReviewRecord" app/` 命中并逐条确认：
- `app/application/reports/service.py`：87/98/111/125/137/160/202/221/272/322（10 处 `FROM SpheroidizationRecord`）+ 395（`FROM ReviewRecord`）——**全部已过滤**。
- `app/infrastructure/database/connection.py`：40/52/64 与 `app/infrastructure/database/schema.sql`：187/198/209 —— 是 `AFTER DELETE` 序列回退触发器里的 `SELECT MAX(id)`（物理删除时把 AUTOINCREMENT 序列回退到当前最大 ID 的完整性计算），**不是业务读路径**，按任务书口径保留并加了注释说明（软删除后这些表不发生物理 DELETE，触发器实际不触发）。
- 仓储层的 `SELECT * FROM {self._table_name}` 用变量表名，不落在上面这条 grep 里，已单独在 sqlite.py 逐方法核对（见 C 节）。

## 红线遵守
- 未动 `frontend/`、`merge/`、检测模块、auth 登录逻辑（`git status` 确认无相关改动）。
- 未写任何 `DELETE FROM`；四类数据全部软删除。
- 未 `git commit`、未提问、未等确认。
- 全量 pytest 通过（273 > 基线 257，只增）。

## 部署注意（给后续）
- 现场生产库 `data/spheroidization.db` 目前是 v5（无软删除列）。本改动把 v6 列纳入启动自检，**换新代码前必须先跑一次** `python scripts/migrate_db.py`（幂等、自动备份、行数校验）。未迁移直接启动会在 `verify_schema` 处 fail-fast 并提示迁移，不会带病上线。
- `action:manage_data` 需在用户管理页新增勾选框（前端属 TASK-9，本轮未碰）。
