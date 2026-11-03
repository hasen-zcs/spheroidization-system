# TASK-10 登录页增强：账号下拉选择 + 记住密码

## 老板要求（内网环境，明确说不必考虑安全问题）
1. 登录页「账号」输入框加**下拉栏**，列出所有账号，可直接选，减少手输
2. 加「**记住密码**」勾选框；勾选后登录成功即记住该账号密码；
   **之后选择这个账号时密码自动填入**（前提：之前用该账号登录过且勾了记住）

## A. 后端：账号列表接口（app/api/user.py）
- 新增 `GET /api/users/accounts`，**公开接口**（免登录，加进 permissions.py 的 PUBLIC_PATHS）
- 只返回**启用中**（enabled=1）的账号名：`ok([{"username": "..."}])`，按用户名排序
- 不返回密码哈希、不返回 is_admin 之外的任何敏感字段（就 username 一个字段）
- 复用现有 UserAccount 仓储，**不许新写 SQL**（仓储已有列表方法；若没有，仓储层补一个最小方法）
- 注意路由顺序：放在 `@router.get("")` 附近，别被别的 GET 吞掉

## B. 前端 Login.vue
1. 账号输入框改「输入 + 原生下拉」：`<input list="account-list">` + `<datalist id="account-list">`
   - 用 datalist 而不是 select：既能下拉选，也能手输，接口挂了还能正常登录（优雅降级）
   - `onMounted` 拉 `/api/users/accounts` 填充 options；失败静默（不影响登录）
2. 「记住密码」勾选框（默认不勾），样式沿用登录卡片现有表单风格
3. 记住密码逻辑（localStorage，键 `sphero_saved_passwords`，值 `JSON: {用户名: 密码}`）：
   - **登录成功**：勾了记住 → 写入/覆盖该用户名的密码；没勾 → 删掉该用户名的记录
   - **账号变化时**（select/change 事件）：有该用户名的已存密码 → 自动填入密码框
4. 提交逻辑、错误提示、redirect 逻辑**一律不动**

## C. 测试（tests/test_login_page_enhance.py，3 条）
1. 游客 `GET /api/users/accounts` → 200，只含 enabled 账号
2. 建一个停用账号 → 列表不含它
3. 响应体只有 username 字段（无密码/权限字段）

## D. 验收
- `cd frontend && npm run build` 成功
- 全量 pytest 通过（基线 275，只能增）
- 红线：不许改登录鉴权逻辑、不许 git commit、不许提问、不许等确认
- 产出 TASK-10-RESULT.md
