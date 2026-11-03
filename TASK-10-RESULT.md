# TASK-10 完成结果：登录页增强——账号下拉选择 + 记住密码

- 全量 pytest：**278 passed**（基线 275 + 新增 3，无失败、无跳过）
- 前端 build：**成功**（`vue-tsc -b` 类型检查 + `vite build`，`dist/` 已产出）
- 未 git commit；未动登录鉴权逻辑（`login` 接口、`LoginUseCase`、`require_login/require_permission`、token 会话机制一行未改）；提交/错误提示/redirect 逻辑未动

## 文件清单

### 新增
| 文件 | 说明 |
|---|---|
| `tests/test_login_page_enhance.py` | 3 条验收测试（见下） |

### 改动（后端）
| 文件 | 改动 |
|---|---|
| `app/api/user.py` | 新增 `GET /api/users/accounts`：公开接口（无 `require_*` 依赖），`ok([{"username": ...}])` 信封。注册在 `@router.get("")` **之前**；该路由组没有任何 GET 路径参数路由（`/{user_id}/...` 全是 PUT/POST），不存在被吞的风险 |
| `app/application/user/query.py` | `QueryUserUseCase` 增 `list_enabled_usernames()`：走既有 `user_repo.list_all()`，过滤 `enabled == 1`，按用户名排序。不查权限点，避免为下拉列表付 `list_all()` 的 N+1 权限查询 |
| `app/core/permissions.py` | `PUBLIC_PATHS` 增 `"/api/users/accounts"`（精确路径，沿用既有的精确匹配口径） |

**未新写 SQL**：仓储层复用既有 `SqliteUserRepository.list_all()`，一行 SQL 未动（任务书「若没有列表方法则补最小方法」的兜底分支未触发）。

### 改动（前端）
| 文件 | 改动 |
|---|---|
| `frontend/src/api/index.ts` | 登录区新增 `AccountOption` 接口 + `getAccounts()`，走既有 `request()` 封装 |
| `frontend/src/views/Login.vue` | 见下节 |
| `frontend/src/style.css` | 新增 `.login-remember` 勾选框样式（13px/#555，与 `.login-field` 同口径，`accent-color: #1890ff`），插在 `.login-error` 前 |

## 登录页行为

**账号下拉（datalist，非 select）**
- `<input list="account-list">` + `<datalist id="account-list">`：既能下拉选也能手输；接口挂了 options 为空，手输登录不受影响（优雅降级）
- `onMounted` 拉 `/api/users/accounts`，`code===200` 才填充；请求层自身捕获网络错误返回 `code:-1`，整条链路失败都静默，不碰 `errorMessage`

**记住密码（localStorage 键 `sphero_saved_passwords`，值 `JSON: {用户名: 密码}`）**
- 勾选框默认不勾（`rememberPassword = ref(false)`）
- **登录成功**（`code===200 && data` 分支内、`applySession` 之前）：勾了 → 写入/覆盖该用户名；没勾 → `delete` 该用户名记录。登录失败不写不删
- **账号变化**（input 的 `@change`，即下拉选定/失焦提交值时）：有已存密码 → 自动填入密码框；没有 → 清空密码框（防止上一个账号的已填密码被误提交给新账号）
- 读取时做了防御：JSON 解析失败或存的东西不是对象 → 按空表处理，不让坏数据把登录页搞挂

## 新增测试（3 条，`tests/test_login_page_enhance.py`）

1. `test_游客可拉取启用账号列表`：不带 token 直接 GET → 信封 `code=200`，只含启用账号，按用户名排序（`["li", "zhang"]` 验证排序）
2. `test_停用账号不在列表中`：建 2 个号后 `manage_user().set_enabled(user_id, 0)` 停用一个 → 列表只剩启用那个
3. `test_响应体只有username字段`：`set(items[0].keys()) == {"username"}`，密码哈希/权限/is_admin 等字段一概不存在

## 验收结果

```
$ .venv/bin/python -m pytest tests/test_login_page_enhance.py -v
3 passed

$ .venv/bin/python -m pytest            # 全量
278 passed, 1 warning in 81.45s

$ cd frontend && npm run build
vue-tsc -b 通过，vite build 成功（dist/assets 已重新产出）
```
