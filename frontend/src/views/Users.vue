<script setup lang="ts">
import { computed, onMounted, ref } from "vue"

import {
  createUser,
  listUsers,
  resetUserPassword,
  saveUserPermissions,
  setUserEnabled,
} from "../api"
import type { UserRecord } from "../api"
import { can } from "../auth"
import { PERMISSION_GROUPS } from "../constants"

// 页面入口是 page:users，操作权限是 action:manage_users，两者分开：
// 只有页面权限的账号进来只能看不能改
const canManage = computed(() => can("action:manage_users"))

const users = ref<UserRecord[]>([])
const loading = ref(true)
const errorMessage = ref("")
const notice = ref("")
let noticeTimer: number | null = null

function flashNotice(message: string) {
  notice.value = message
  if (noticeTimer !== null) {
    window.clearTimeout(noticeTimer)
  }
  noticeTimer = window.setTimeout(() => {
    notice.value = ""
  }, 6000)
}

// 空值统一显示成 —
function display(value: string | number | null | undefined) {
  return value === null || value === undefined || value === ""
    ? "—"
    : value
}

async function loadUsers() {
  loading.value = true
  errorMessage.value = ""

  try {
    const result = await listUsers()

    if (result.code === 200) {
      users.value = result.data ?? []
    } else {
      errorMessage.value = result.message || "加载用户列表失败"
    }
  } finally {
    loading.value = false
  }
}

// ====================
// 建用户
// ====================

const showCreateDialog = ref(false)
const newUsername = ref("")
const newPassword = ref("")
const newIsAdmin = ref(false)
const creating = ref(false)

function openCreateDialog() {
  newUsername.value = ""
  newPassword.value = ""
  newIsAdmin.value = false
  showCreateDialog.value = true
}

async function submitCreateUser() {
  if (creating.value) {
    return
  }

  if (!newUsername.value.trim() || !newPassword.value) {
    alert("请输入用户名和密码")
    return
  }

  creating.value = true
  try {
    const result = await createUser({
      username: newUsername.value.trim(),
      password: newPassword.value,
      is_admin: newIsAdmin.value,
    })

    if (result.code === 200) {
      const name = newUsername.value.trim()
      showCreateDialog.value = false
      await loadUsers()
      flashNotice(`用户「${name}」创建成功`)
    } else {
      alert(result.message || "创建用户失败")
    }
  } finally {
    creating.value = false
  }
}

// ====================
// 权限分配
// ====================

const permUser = ref<UserRecord | null>(null)
const permDraft = ref<string[]>([])
const savingPerm = ref(false)

function openPermDialog(user: UserRecord) {
  permUser.value = user
  // 管理员账号拥有全部权限：全部勾上且置灰不可改
  permDraft.value = user.is_admin
    ? PERMISSION_GROUPS.flatMap((group) =>
        group.items.map((item) => item.key)
      )
    : [...user.permission_keys]
}

function permChecked(key: string): boolean {
  return permDraft.value.includes(key)
}

function togglePerm(key: string, checked: boolean) {
  if (!permUser.value || permUser.value.is_admin) {
    return
  }
  permDraft.value = checked
    ? [...permDraft.value, key]
    : permDraft.value.filter((item) => item !== key)
}

async function submitPermissions() {
  if (!permUser.value || savingPerm.value) {
    return
  }

  savingPerm.value = true
  try {
    const result = await saveUserPermissions(
      permUser.value.id,
      permDraft.value
    )

    if (result.code === 200) {
      const name = permUser.value.username
      permUser.value = null
      await loadUsers()
      flashNotice(`权限保存成功，用户「${name}」需重新登录后生效`)
    } else {
      alert(result.message || "保存权限失败")
    }
  } finally {
    savingPerm.value = false
  }
}

// ====================
// 重置密码
// ====================

const resetUser = ref<UserRecord | null>(null)
const resetPassword = ref("")
const resetting = ref(false)

function openResetDialog(user: UserRecord) {
  resetUser.value = user
  resetPassword.value = ""
}

async function submitResetPassword() {
  if (!resetUser.value || resetting.value) {
    return
  }

  if (!resetPassword.value) {
    alert("请输入新密码")
    return
  }

  resetting.value = true
  try {
    const result = await resetUserPassword(
      resetUser.value.id,
      resetPassword.value
    )

    if (result.code === 200) {
      const name = resetUser.value.username
      resetUser.value = null
      flashNotice(
        `已重置用户「${name}」的密码，该用户需重新登录后生效`
      )
    } else {
      alert(result.message || "重置密码失败")
    }
  } finally {
    resetting.value = false
  }
}

// ====================
// 启用 / 禁用
// ====================

const togglingUserId = ref<number | null>(null)

async function toggleEnabled(user: UserRecord) {
  if (togglingUserId.value !== null) {
    return
  }

  const nextEnabled = !user.enabled
  togglingUserId.value = user.id

  try {
    const result = await setUserEnabled(user.id, nextEnabled)

    if (result.code === 200 && result.data) {
      const index = users.value.findIndex((item) => item.id === user.id)
      if (index >= 0) {
        users.value[index] = result.data as UserRecord
      }
      flashNotice(
        `用户「${user.username}」已${result.data.enabled ? "启用" : "禁用"}`
      )
    } else {
      alert(result.message || "操作失败")
    }
  } finally {
    togglingUserId.value = null
  }
}

onMounted(() => {
  void loadUsers()
})
</script>

<template>
  <div class="users-page">
    <div class="page-heading">
      <div>
        <h1>用户管理</h1>
        <p>管理账号、权限与启用状态</p>
      </div>

      <div class="header-actions">
        <button
          v-if="canManage"
          class="primary-button"
          type="button"
          @click="openCreateDialog"
        >
          新建用户
        </button>

        <button
          class="secondary-button"
          type="button"
          @click="loadUsers"
        >
          刷新
        </button>
      </div>
    </div>

    <div
      v-if="notice"
      class="notice-bar"
    >
      {{ notice }}
    </div>

    <section class="panel table-panel">
      <div
        v-if="loading"
        class="empty-state"
      >
        正在加载用户列表...
      </div>

      <div
        v-else-if="errorMessage"
        class="empty-state"
      >
        {{ errorMessage }}
      </div>

      <div
        v-else-if="users.length === 0"
        class="empty-state"
      >
        暂无用户
      </div>

      <div
        v-else
        class="table-scroll"
      >
        <table>
          <thead>
            <tr>
              <th>用户名</th>
              <th>是否管理员</th>
              <th>启用状态</th>
              <th>权限数量</th>
              <th>创建人</th>
              <th>创建时间</th>
              <th v-if="canManage">操作</th>
            </tr>
          </thead>

          <tbody>
            <tr
              v-for="user in users"
              :key="user.id"
            >
              <td>
                {{ user.username }}
                <span
                  v-if="user.is_admin"
                  class="admin-tag"
                >
                  拥有全部权限
                </span>
              </td>

              <td>
                {{ user.is_admin ? "是" : "否" }}
              </td>

              <td>
                <span
                  :class="
                    user.enabled ? 'status-normal' : 'status-disabled'
                  "
                >
                  {{ user.enabled ? "启用" : "禁用" }}
                </span>

                <label
                  v-if="canManage"
                  class="user-switch"
                  :title="user.enabled ? '点击禁用' : '点击启用'"
                >
                  <input
                    :checked="user.enabled"
                    :disabled="togglingUserId !== null"
                    type="checkbox"
                    @change="toggleEnabled(user)"
                  />
                  <span class="user-switch-track" />
                </label>
              </td>

              <td>
                {{
                  user.is_admin
                    ? "全部"
                    : user.permission_keys.length
                }}
              </td>

              <td>{{ display(user.created_by) }}</td>
              <td>{{ display(user.created_at) }}</td>

              <td
                v-if="canManage"
                class="user-actions"
              >
                <button
                  class="text-button"
                  type="button"
                  @click="openPermDialog(user)"
                >
                  分配权限
                </button>

                <button
                  class="text-button"
                  type="button"
                  @click="openResetDialog(user)"
                >
                  重置密码
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <!-- 建用户弹窗 -->
    <div
      v-if="showCreateDialog"
      class="dialog-overlay"
      @click.self="showCreateDialog = false"
    >
      <div class="dialog">
        <h3>新建用户</h3>

        <label class="dialog-field">
          <span>用户名</span>
          <input
            v-model="newUsername"
            placeholder="请输入用户名"
          />
        </label>

        <label class="dialog-field">
          <span>密码</span>
          <input
            v-model="newPassword"
            placeholder="请输入密码"
            type="password"
          />
        </label>

        <label class="dialog-field">
          <span>是否管理员</span>
          <input
            v-model="newIsAdmin"
            type="checkbox"
          />
        </label>

        <p class="dialog-hint">
          管理员账号自动拥有全部权限。
        </p>

        <div class="dialog-actions">
          <button
            class="secondary-button"
            type="button"
            @click="showCreateDialog = false"
          >
            取消
          </button>

          <button
            class="primary-button"
            :disabled="creating"
            type="button"
            @click="submitCreateUser"
          >
            {{ creating ? "创建中..." : "创建" }}
          </button>
        </div>
      </div>
    </div>

    <!-- 权限分配面板 -->
    <div
      v-if="permUser"
      class="dialog-overlay"
      @click.self="permUser = null"
    >
      <div class="dialog">
        <h3>
          分配权限 — {{ permUser.username }}
        </h3>

        <p
          v-if="permUser.is_admin"
          class="dialog-hint"
        >
          管理员账号：拥有全部权限，不可修改。
        </p>

        <div
          v-else
          class="perm-panel"
        >
          <div
            v-for="group in PERMISSION_GROUPS"
            :key="group.key"
            class="perm-group"
          >
            <div class="perm-group-title">
              {{ group.label }}
            </div>

            <label
              v-for="item in group.items"
              :key="item.key"
              class="perm-item"
            >
              <input
                :checked="permChecked(item.key)"
                type="checkbox"
                @change="
                  togglePerm(
                    item.key,
                    ($event.target as HTMLInputElement).checked
                  )
                "
              />
              <span>
                {{ item.label }}
                <em class="perm-key">{{ item.key }}</em>
              </span>
            </label>
          </div>
        </div>

        <div class="dialog-actions">
          <button
            class="secondary-button"
            type="button"
            @click="permUser = null"
          >
            关闭
          </button>

          <button
            v-if="!permUser.is_admin"
            class="primary-button"
            :disabled="savingPerm"
            type="button"
            @click="submitPermissions"
          >
            {{ savingPerm ? "保存中..." : "保存权限" }}
          </button>
        </div>
      </div>
    </div>

    <!-- 重置密码弹窗 -->
    <div
      v-if="resetUser"
      class="dialog-overlay"
      @click.self="resetUser = null"
    >
      <div class="dialog">
        <h3>
          重置密码 — {{ resetUser.username }}
        </h3>

        <label class="dialog-field">
          <span>新密码</span>
          <input
            v-model="resetPassword"
            placeholder="请输入新密码"
            type="password"
          />
        </label>

        <div class="dialog-actions">
          <button
            class="secondary-button"
            type="button"
            @click="resetUser = null"
          >
            取消
          </button>

          <button
            class="primary-button"
            :disabled="resetting"
            type="button"
            @click="submitResetPassword"
          >
            {{ resetting ? "提交中..." : "确认重置" }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.users-page {
  min-height: 100%;
  padding: 12px;
  background: #f5f7fa;
}

.page-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 20px;
  margin-bottom: 10px;
  padding: 14px 16px;
  background: #fff;
  border: 1px solid #d9d9d9;
}

.page-heading h1 {
  margin-bottom: 4px;
  color: #003399;
  font-size: 18px;
}

.page-heading p {
  color: #777;
  font-size: 12px;
}

.header-actions {
  display: flex;
  gap: 8px;
}

.notice-bar {
  margin-bottom: 10px;
  padding: 9px 14px;
  color: #16803c;
  font-size: 12px;
  background: #f6ffed;
  border: 1px solid #b7eb8f;
}

.table-panel {
  min-height: 220px;
  padding: 4px 16px 16px;
}

.table-scroll {
  overflow-x: auto;
}

table {
  width: 100%;
  min-width: 760px;
  border-collapse: collapse;
  font-size: 12px;
}

th,
td {
  padding: 9px 10px;
  text-align: left;
  border-bottom: 1px solid #e8e8e8;
}

th {
  color: #333;
  font-weight: 700;
  background: #fafafa;
}

tbody tr:nth-child(even) {
  background: #fafafa;
}

tbody tr:hover {
  background: #e6f7ff;
}

.admin-tag {
  margin-left: 8px;
  padding: 1px 7px;
  color: #d48806;
  font-size: 11px;
  background: #fff7e6;
  border: 1px solid #ffd591;
  border-radius: 2px;
}

.status-disabled {
  color: #999;
  font-weight: 600;
}

.user-switch {
  position: relative;
  display: inline-block;
  margin-left: 10px;
  vertical-align: middle;
  cursor: pointer;
}

.user-switch input {
  position: absolute;
  opacity: 0;
  width: 0;
  height: 0;
}

.user-switch-track {
  display: inline-block;
  width: 34px;
  height: 18px;
  background: #bfbfbf;
  border-radius: 9px;
  transition: background 0.2s;
  position: relative;
}

.user-switch-track::after {
  position: absolute;
  top: 2px;
  left: 2px;
  width: 14px;
  height: 14px;
  content: "";
  background: #fff;
  border-radius: 50%;
  transition: left 0.2s;
}

.user-switch input:checked + .user-switch-track {
  background: #1890ff;
}

.user-switch input:checked + .user-switch-track::after {
  left: 18px;
}

.user-switch input:disabled + .user-switch-track {
  opacity: 0.5;
}

.user-actions {
  white-space: nowrap;
}

.user-actions .text-button {
  margin-right: 10px;
}

@media (max-width: 700px) {
  .page-heading {
    align-items: flex-start;
    flex-direction: column;
  }
}
</style>
