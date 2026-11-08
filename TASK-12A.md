# TASK-12A 检测标准管理：标准条增加「修改」「删除」+ 权限改名

> 工头：小白 · 2026-11-06 · 环境：~/spheroidization-lab（git master，基线 284 测试全绿）
> 总设计见老板批过的实施文档要点（本文档自包含，照做即可）。
> 完成后必须：`.venv/bin/python -m pytest -q` 全绿 + `cd frontend && npm run build` 0 错误，并把两条命令的末尾输出贴回。

## 背景

- 后端 `app/api/standard.py` 目前只有 POST(新增) / GET /current / GET /history / POST /switch / GET /switch-logs，**没有修改、删除端点**。
- 仓储 `app/infrastructure/database/sqlite.py` 的 StandardRecord 仓储已有 `soft_delete / restore / get_by_id_including_deleted`（v6），**没有 update**。
- `app/infrastructure/database/schema.sql`：StandardRecord 只有 `CHECK(standard_spheroidization_time > 0)`（docstring 里 65~75 的说法过时，顺手修掉）。
- 球化记录存标准快照（SpheroidizationRecord.standard_spheroidization_time），原地改标准不影响历史。
- 管理端已有 `app/application/admin/manage.py` 的 `ManageDataUseCase.soft_delete(kind, record_id, actor, reason)`，kind="standard" 时**拒绝删当前生效标准（400「该标准当前生效，请先切换标准后再作废」）、行不存在 404、已删幂等**。删除端点**必须复用它**，不许另写软删逻辑。

## A. 后端

### A1. 仓储层：加 update
文件：`app/domain/standard/repositories.py` + `app/infrastructure/database/sqlite.py`
- 抽象接口加：
  ```python
  def update(self, standard_record_id: int,
             standard_spheroidization_time: float,
             standard_spheroidization_time_upper: float | None,
             standard_spheroidization_time_lower: float | None,
             weighing_standard: float,
             remark: str) -> Optional[StandardRecord]:
  ```
  语义：按主键 UPDATE 这 5 个字段；行不存在返回 None；用 `with conn:` 事务；`rowcount` 判断。
- docstring 同步改：类约定第 5 条「不提供 update 方法」已过时，改为说明 update 只做字段修订、不改 created_at/created_by；save 的 docstring 里 65~75 的说法改为 >0。
- sqlite 实现：`UPDATE StandardRecord SET ... WHERE standard_record_id=? AND deleted_at IS NULL`（已软删的行不允许再改，返回 None）。

### A2. 用例层
- 新建 `app/application/standard/update.py`：
  ```python
  class UpdateStandardUseCase:
      def __init__(self, standard_repo): ...
      def execute(self, standard_record_id, standard_spheroidization_time,
                  standard_spheroidization_time_upper, standard_spheroidization_time_lower,
                  weighing_standard, remark) -> StandardRecord
  ```
  行不存在/已删 → 抛 `app.core` 里现成的 BusinessException（404，文案「标准不存在」；先看 switch.py/create.py 怎么抛 404，照抄风格）。
- `app/dependencies.py`：Container 加 `update_standard()` 工厂 + `get_update_standard_uc` 依赖（照 create 的写法）。

### A3. 审计枚举
`app/domain/audit/entities.py`：`AuditAction` 加 `UPDATE_STANDARD = "update_standard"  # 修改检测标准`。

### A4. schema
`app/schemas/standard.py` 加：
```python
class StandardUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    standard_spheroidization_time: float = Field(gt=0)
    weighing_standard: float
    standard_spheroidization_time_upper: float | None = Field(default=None, gt=0)
    standard_spheroidization_time_lower: float | None = Field(default=None, gt=0)
    remark: str = ""
```
（与 StandardCreateRequest 的校验完全对齐。）

### A5. 路由
`app/api/standard.py` 加两个端点，**必须放在 /current、/history、/switch、/switch-logs 之后**（现有注释已警告路径吞并）：
- `PUT /api/standards/{standard_id}`：
  - 依赖 `require_permission(P.ACTION_CREATE_STANDARD)`（复用现有 import）+ `get_update_standard_uc` + 审计；
  - 调用例 → 成功后 `audit.record(actor=..., action=AuditAction.UPDATE_STANDARD, target_type=AuditTarget.STANDARD, target_id=..., detail={5字段}, ip=client_ip(request))` → `ok(to_response(standard), "标准修改成功")`。
- `DELETE /api/standards/{standard_id}`：
  - body `StandardDeleteRequest {reason: str}`（strip 后判空 → 422，照 StandardSwitchRequest 的 `_not_blank` 写法）；
  - 权限同 `P.ACTION_CREATE_STANDARD`；
  - **调 `ManageDataUseCase.soft_delete("standard", standard_id, session.username, reason)`**（依赖 `get_manage_data_uc`，TASK-11 已加在 dependencies.py）；
  - 返回语义与 admin 删除端点一致：not_found → 404「目标不存在」；already → ok「该标准已删除，无需重复操作」；created → 审计（AuditAction.DELETE_STANDARD，detail 带 before/after 关键字段，不含 BLOB）→ ok「标准已删除」。
  - 先读 `app/api/admin.py` 现有删除端点怎么消费 DeleteResult，行为保持一致。

## B. 前端

### B1. 权限常量
`frontend/src/constants.ts`：`{ key: "action:create_standard", label: "新增检测标准" }` 的 label 改为 **"检测标准管理"**（key 不动）。

### B2. API 封装
`frontend/src/api/index.ts`：加
```ts
export function updateStandard(standardId: number, data: { standard_spheroidization_time: number; standard_spheroidization_time_upper: number | null; standard_spheroidization_time_lower: number | null; weighing_standard: number; remark: string })
export function deleteStandard(standardId: number, reason: string)
```
照现有 createStandard/switchStandard 的 fetch 写法（PUT / DELETE 带 JSON body，DELETE 也有 body）。

### B3. Standard.vue
- `canCreate` 改名 `canManage`（`can("action:create_standard")`），注释写明「检测标准管理：控制增/改/删」。
- 「标准记录」表：最后一列列名「应用标准」→「操作」（表头 + colspan 数字不变，仍是 9 列）；每行该列按钮：
  - 当前标准行：disabled「当前标准」+ 修改 + 删除；
  - 非当前行：`canSwitch` 时「切换标准」+ 修改 + 删除；
  - 修改/删除按钮 `v-if="canManage"`，样式沿用 `apply-button`（两个按钮并排，间距 6px）。
- **修改弹窗**（新 dialog，结构照现有切换弹窗）：标题「修改标准 — 标准N」；5 个字段预填该行值（球化时间/下限/上限/称重为 number input，备注为 textarea）；提交 → `updateStandard` → code 200 关弹窗 + `loadData()`；失败 `alert(result.message || "修改标准失败")`。
- **删除弹窗**：标题「删除标准 — 标准N（X 秒）」；提示文案「删除后该标准不再出现在标准记录与切换列表；若为当前标准将被拒绝。此操作会留审计记录。」；原因输入（必填，空则 alert「请填写删除原因，原因为空不允许提交」）；提交 → `deleteStandard` → 200 关弹窗 + `loadData()`；失败 `alert(result.message)`（当前标准被删时后端 400 文案会自然显示）。
- 注意：本任务**不动**「新增检测标准」表单里的备注 textarea（R2 任务会改）。

## C. 测试（新增 tests/test_standard_update_delete.py）
照 tests/test_admin_data.py / test_access_control.py 的夹具风格（先看它们怎么建库、怎么登录、怎么造标准），至少覆盖：
1. 无 action:create_standard 权限的账号：PUT / DELETE → 403
2. PUT 成功：字段全部更新，GET /current 反映新值，created_by 不变
3. PUT 非法值（time=0 / upper=-1 / 多传字段）→ 422
4. PUT 不存在的 id → 404
5. DELETE 当前生效标准 → 400（文案含「当前生效」）
6. DELETE 历史标准成功 → GET /history 不再含它；重复 DELETE → 200 幂等文案
7. DELETE 原因空白 → 422
跑法：`.venv/bin/python -m pytest -q`（要求：284 基线 + 新增全绿，一个不许红）。

## D. 完成判定（贴回证据）
1. `pytest -q` 末尾 `N passed` 输出
2. `cd frontend && npm run build` 成功输出
3. 改动文件清单（git status --short）
