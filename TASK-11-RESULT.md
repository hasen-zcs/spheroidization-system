# TASK-11 完成结果：A-01 修复——admin.py 直连 SQL 下沉到仓储 + 用例层

- 全量 pytest：**284 passed**（基线 278 既有全绿 + 新增 6，无失败、无跳过、无删除）
- 红线校验：`grep -n "execute(\|SELECT\|UPDATE " app/api/admin.py` **输出为空**（API 层已无任何裸 SQL）
- 未 git commit；只在 `~/spheroidization-lab` 改，未动 `~/spheroidization-prod`

## 行为不变证明

- **278 条既有测试一条未改未删，全绿**（含 `test_admin_data.py` 全部软删/恢复/处理状态/权限/审计/幂等/迁移用例）。
- 写路径 SQL **一字不改逻辑**，只是从 `app/api/admin.py` 原样搬到仓储：软删/恢复的 `UPDATE ... SET deleted_at=...`、`AND deleted_at IS NULL/IS NOT NULL` 幂等守卫、处理状态 0/1 的 by/at 分写，都照搬 admin.py 原语句。
- 返回语义一致：仓储用 `cursor.rowcount > 0` 判定"本次真改没改"，用例据此映射 `not_found / already / created`，API 层按这三个状态给响应（404 / 幂等成功不写审计 / 写审计后成功），和原 admin.py 的 `(status, before, after)` 三分支一一对应。
- 审计快照口径不变：`_KEY_FIELDS`（原 `_TABLES` 的 key_fields）搬到用例层，仍取业务关键字段 + 软删三列，**不含图片 BLOB**；审计动作码 / 对象类型映射（`_DELETE_ACTIONS`/`_RESTORE_ACTIONS`）留在 API 层未动。
- 当前生效标准保护逻辑不变：从 endpoint 内联判断移到用例 `soft_delete(kind="standard")`，命中即 `raise BusinessException("该标准当前生效，请先切换标准后再作废", 400)`，经 main.py 统一处理器产出与 `fail(...,400)` 完全相同的信封（`test_当前生效标准不许软删` 验证 code=400 + 精确 message）。
- reason 必填、404、403 权限（`require_permission`）均未动。

## 文件清单

### 新增
| 文件 | 说明 |
|---|---|
| `app/application/admin/__init__.py` | 新包空 `__init__` |
| `app/application/admin/manage.py` | `ManageDataUseCase` + `DeleteResult`（dataclass）；`_KEY_FIELDS` 审计关键字段映射 |
| `tests/test_manage_data_usecase.py` | 6 条验收测试（见下） |

### 改动
| 文件 | 改动 |
|---|---|
| `app/domain/spheroidization/repositories.py` | 加抽象方法 `get_by_id_including_deleted` / `soft_delete` / `restore` / `set_processed`（仅本仓储多一个 set_processed） |
| `app/domain/standard/repositories.py` | 加 `get_by_id_including_deleted` / `soft_delete` / `restore` |
| `app/domain/standard/switchlog_repositories.py` | 同上（主键名 `switch_log_id`）；补 `Optional` 导入 |
| `app/domain/review/repositories.py` | 同上（主键名 `review_record_id`）；补 `Optional` 导入 |
| `app/infrastructure/database/sqlite.py` | 四个 Sqlite 仓储各实现 3 组方法（spheroid 多 `set_processed`）；SQL 照搬 admin.py，事务用 `with self._conn:`，`rowcount>0` 决定返回值；`get_by_id_including_deleted` 的 SELECT 不带 `deleted_at IS NULL` |
| `app/dependencies.py` | 导入 `ManageDataUseCase`；`Container.manage_data()` 装配四个仓储 + `query_standard()`；新增 provider `get_manage_data_uc` |
| `app/api/admin.py` | **删掉** `_now`/`_TABLES`/`_fetch_row`/`_snapshot`/`_soft_delete`/`_restore`/`_set_processed` 及 `datetime`/`Container`/`get_container` 导入；三个 endpoint（删除/恢复/改处理状态）改为注入 `ManageDataUseCase` 并按 `DeleteResult.status` 给响应。全文件不再有 `conn.execute` 或任何 SQL 字符串 |

## 新增测试（6 条，`tests/test_manage_data_usecase.py`）

1. `test_仓储软删真删True再删False`：`soft_delete` 首次 `True`，已删再删 `False`，不存在 `False`
2. `test_仓储恢复真恢复True未删False`：未删恢复 `False`，已删恢复 `True`，恢复后再恢复 `False`
3. `test_including_deleted能取到已删行而get_by_id取不到`：已删后 `get_by_id`→None、`get_by_id_including_deleted`→带软删三列的实体
4. `test_用例软删当前生效标准抛400`：`uc.soft_delete("standard", 当前id, ...)` 抛 `BusinessException` 且 `code==400`，库未动
5. `test_用例set_processed零一往返且by_at随check变化`：0→1 时 by/at 写入，1→0 时 by/at 清空
6. `test_api删SQL后删除恢复行为不变`：TestClient 全链路 删除→详情404/列表归零→再删幂等→不存在404→恢复→列表回来→未删再恢复幂等（复用 `test_admin_data` 的 env 风格）

## 验收结果

```
$ .venv/bin/python -m pytest tests/test_manage_data_usecase.py -q
6 passed

$ .venv/bin/python -m pytest            # 全量
284 passed, 1 warning in 82.30s

$ grep -n "execute(\|SELECT\|UPDATE " app/api/admin.py
（无输出）
```
