# TASK-11 修复 A-01：admin.py 直连 SQL 下沉到仓储+用例层

## 背景（代码治理阶段2，只在副本 ~/spheroidization-lab 改，不动 prod/不上东贝）
审计发现 A-01：`app/api/admin.py` 的 `_fetch_row`/`_soft_delete`/`_restore`/`_set_processed` 4 个函数
直接 `container.conn.execute(...)` 拼裸 SQL（含动态表名），绕开了仓储的事务边界/实体映射/用例编排。
目标：**行为完全不变**（278 测试必须全绿且通过既有 API 契约），把写 SQL 从 API 层下沉到 infrastructure 仓储 + application 用例。

## A. domain 层：4 个仓储接口各加方法（抽象方法，带 docstring）
文件：`app/domain/{spheroidization,standard,switchlog,review}/repositories.py`
- 每个仓储加：
  - `get_by_id_including_deleted(record_id: int) -> Optional[Entity]`（含已删除行）
  - `soft_delete(record_id: int, deleted_by: str, delete_reason: str) -> bool`（True=本次真删了；False=不存在或已删）
  - `restore(record_id: int) -> bool`（True=本次真恢复了；False=不存在或未删）
- **仅 SpheroidizationRepository** 额外加：
  - `set_processed(record_id: int, processed: int, processed_by: str) -> bool`（1=写 by/at，0=清空 by/at；遵守表上 CHECK）
- 主键参数名沿用各仓储现有命名（record_id / standard_record_id / switch_log_id / review_record_id，看现有签名）

## B. infrastructure 层：sqlite.py 实现这 4 组方法
- SQL 照搬 admin.py 里现有的写语句（`UPDATE ... SET deleted_at=...` 等），**一字不改逻辑**，只是搬到仓储
- 事务用 `with conn:`
- 返回值语义和上面接口一致（用 `rowcount` 判断真改没改）
- `get_by_id_including_deleted` 的 SELECT 不带 `deleted_at IS NULL` 过滤

## C. application 层：新增 ManageDataUseCase
文件：`app/application/admin/manage.py`（新目录 app/application/admin/__init__.py 也要建）
```
class ManageDataUseCase:
    def __init__(self, spheroid_repo, standard_repo, switchlog_repo, review_repo, standard_query_uc):
        # standard_query_uc 用来判断"当前生效标准"（复用现有 QueryStandardUseCase.get_current）
    def soft_delete(self, kind, record_id, actor, reason) -> DeleteResult
    def restore(self, kind, record_id) -> DeleteResult
    def set_processed(self, record_id, processed, actor) -> DeleteResult
```
- `kind` ∈ {"record","standard","switch_log","review"}，内部按 kind 路由到对应仓储（可保留一个 kind→(repo, 审计关键字段) 的映射）
- `DeleteResult`：dataclass，字段 `status`（not_found/already/created）、`before`（dict 关键字段+删除三列）、`after`（dict）
- **当前生效标准保护**在 `soft_delete(kind="standard")` 里做：若 `standard_query_uc.get_current()` 的 id == record_id → 抛 `BusinessException("该标准当前生效，请先切换标准后再作废", 400)`（和现在 admin.py 的行为一致）
- `before/after` 快照：取该 kind 的业务关键字段（沿用 admin.py 里 `_TABLES` 的 key_fields）+ deleted_at/deleted_by/delete_reason，**不含图片 BLOB**

## D. API 层：admin.py 改造
- **删掉** `_fetch_row`/`_soft_delete`/`_restore`/`_set_processed` 4 个裸 SQL 函数
- 删掉 `_TABLES` 里表名/主键的 SQL 用途（审计 key_fields 映射搬到用例层的 `_KEY_FIELDS`）
- endpoint 改为：依赖注入 `ManageDataUseCase`（在 dependencies.py 加 provider）→ 调用例 → 按 `DeleteResult.status` 给响应：
  - not_found → fail("目标不存在", 404)
  - already → ok(message="...无需重复操作")（**不写审计**，和现在一致）
  - created → 写审计（actor/action/target + before/after）→ ok
- `change_processed` endpoint 同理调用例 `set_processed`
- **reason 必填校验、404、403 权限、审计动作码**全部保持不变
- 最终 admin.py 里 **不许再出现 `conn.execute` 或任何 SQL 字符串**

## E. 测试
- 既有 278 必须全绿（这是行为不变的硬验证）
- 新增 `tests/test_manage_data_usecase.py`（≥6 条）：
  1. 仓储 soft_delete 真删返回 True，再删返回 False
  2. 仓储 restore 真恢复 True，未删的恢复 False
  3. get_by_id_including_deleted 能取到已删行，get_by_id 取不到
  4. 用例 soft_delete 当前标准 → 抛 400
  5. 用例 set_processed 0↔1，by/at 字段随 CHECK 变化
  6. API 层删 SQL 后行为不变：走一遍 删除→404→恢复（复用 test_admin_data 的风格）

## 红线
- 只在 ~/spheroidization-lab 改；不动 ~/spheroidization-prod
- **行为不变**：278 既有测试一条不能挂、不能删
- admin.py 改完 `grep -n "execute(\|SELECT\|UPDATE " app/api/admin.py` 必须为空
- 不许 git commit（我验收后提交）、不许提问、不许等确认
- 产出 TASK-11-RESULT.md
