<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from "vue"
import { useRoute, useRouter } from "vue-router"

import { changeOwnPassword, getCurrentUser, health, logout } from "./api"
import {
  can,
  clearSession,
  currentUser,
  isLoggedIn,
} from "./auth"

type SystemStatus = "checking" | "online" | "offline"

const route = useRoute()
const router = useRouter()

const systemStatus = ref<SystemStatus>("checking")

async function checkSystemStatus() {
  systemStatus.value = "checking"

  try {
    const result = await health()
    systemStatus.value =
      result.code === 200 ? "online" : "offline"
  } catch {
    systemStatus.value = "offline"
  }
}

// 登录页是独立整页，不显示顶部导航
const showNav = computed(() => route.path !== "/login")

const username = computed(() => currentUser()?.username ?? "")

async function handleLogout() {
  try {
    await logout()
  } catch {
    // 登出接口失败也要清本地登录态
  }
  const current = route.fullPath
  clearSession()
  // 修：原来 push("/") 与当前路由相同会被 vue-router 当冗余导航丢弃，
  // 守卫不触发 → 退出后停留在原页面（已登出但内容还在）。直接跳登录页。
  void router.push({ path: "/login", query: { redirect: current } })
}

// ====================
// 自查改密（F2：后端接口 /me/password 早就在，前端没接）
// 成功后后端吊销该账号全部 token（含当前）→ 强制重新登录
// ====================
const pwDialogOpen = ref(false)
const oldPassword = ref("")
const newPassword = ref("")
const confirmPassword = ref("")
const pwError = ref("")
const pwSubmitting = ref(false)
const pwChanged = ref(false)

function openPasswordDialog() {
  oldPassword.value = ""
  newPassword.value = ""
  confirmPassword.value = ""
  pwError.value = ""
  pwChanged.value = false
  pwDialogOpen.value = true
}

async function submitPasswordChange() {
  if (!oldPassword.value || !newPassword.value) {
    pwError.value = "请输入旧密码和新密码"
    return
  }
  if (newPassword.value !== confirmPassword.value) {
    pwError.value = "新密码与确认密码不一致"
    return
  }
  // 前端预检与后端策略一致（≥8 位 + 字母 + 数字），最终以后端为准
  if (
    newPassword.value.length < 8 ||
    !/[a-zA-Z]/.test(newPassword.value) ||
    !/\d/.test(newPassword.value)
  ) {
    pwError.value = "新密码需 ≥8 位，且同时包含字母和数字"
    return
  }

  pwSubmitting.value = true
  pwError.value = ""

  try {
    const result = await changeOwnPassword(
      oldPassword.value,
      newPassword.value
    )
    if (result.code === 200) {
      pwChanged.value = true
    } else {
      pwError.value = result.message || "密码修改失败"
    }
  } finally {
    pwSubmitting.value = false
  }
}

function closePasswordDialog() {
  const needRelogin = pwChanged.value
  pwDialogOpen.value = false
  if (needRelogin) {
    clearSession()
    void router.push("/login")
  }
}

// 接口返回 code=403 时的无权限提示（请求层派发事件）
const forbiddenMessage = ref("")
let forbiddenTimer: number | null = null

function handleApiForbidden(event: Event) {
  const detail = (event as CustomEvent<string>).detail
  forbiddenMessage.value = detail || "没有访问权限"

  if (forbiddenTimer !== null) {
    window.clearTimeout(forbiddenTimer)
  }
  forbiddenTimer = window.setTimeout(() => {
    forbiddenMessage.value = ""
  }, 3000)
}

onMounted(() => {
  checkSystemStatus()
  // 本地还存着登录态时，用 /me 验一次：
  // 过期 token 会在请求层触发 401 → 清登录态 → 跳登录页。
  // 不做这一步的话，公开页（监控/首页）用的是游客接口，永远不报 401，
  // 界面上一直挂着"某某已登录"，实际所有写操作都会失败。
  if (isLoggedIn()) {
    void getCurrentUser()
  }
  window.addEventListener("api:forbidden", handleApiForbidden)
})

onUnmounted(() => {
  window.removeEventListener("api:forbidden", handleApiForbidden)
  if (forbiddenTimer !== null) {
    window.clearTimeout(forbiddenTimer)
  }
})
</script>

<template>
  <div class="app-shell">
    <header
      v-if="showNav"
      class="nav-bar"
    >
      <router-link
        class="logo"
        to="/"
      >
        <span class="logo-icon"></span>
        采集管理
      </router-link>

      <nav class="nav-links">
        <!-- 游客只显示「浇注工位监控」与「首页」，其余按权限显示 -->
        <router-link
          to="/"
          active-class="nav-link-idle"
          exact-active-class="router-link-active"
        >
          浇注工位监控
        </router-link>

        <router-link to="/records/home">
          首页
        </router-link>

        <router-link
          v-if="can('page:records')"
          to="/records/spheroidization"
        >
          球化记录
        </router-link>

        <router-link
          v-if="can('page:abnormal')"
          to="/records/abnormal"
        >
          异常记录
        </router-link>

        <router-link
          v-if="can('page:standard')"
          to="/records/standard"
        >
          检测标准
        </router-link>

        <router-link
          v-if="can('page:users')"
          to="/records/users"
        >
          用户管理
        </router-link>

        <router-link
          v-if="can('action:manage_data')"
          to="/admin"
        >
          数据管理
        </router-link>
      </nav>

      <div class="nav-right">
        <span
          v-if="isLoggedIn()"
          class="nav-user"
        >
          {{ username }}
        </span>

        <button
          v-if="isLoggedIn()"
          class="nav-logout"
          type="button"
          @click="openPasswordDialog"
        >
          修改密码
        </button>

        <button
          v-if="isLoggedIn()"
          class="nav-logout"
          type="button"
          @click="handleLogout"
        >
          退出登录
        </button>

        <router-link
          v-else
          class="nav-logout"
          to="/login"
        >
          登录
        </router-link>

        <button
          class="system-status"
          type="button"
          :class="systemStatus"
          @click="checkSystemStatus"
        >
          {{
            systemStatus === "online"
              ? "系统正常"
              : systemStatus === "offline"
                ? "系统离线"
                : "连接中"
          }}
        </button>
      </div>
    </header>

    <main class="app-content">
      <router-view />
    </main>

    <div
      v-if="forbiddenMessage"
      class="forbidden-toast"
    >
      {{ forbiddenMessage }}
    </div>

    <!-- 自查改密弹窗（F2） -->
    <div
      v-if="pwDialogOpen"
      class="dialog-overlay"
      @click.self="closePasswordDialog"
    >
      <div class="dialog">
        <template v-if="!pwChanged">
          <h3>
            修改密码
          </h3>

          <p class="dialog-hint">
            新密码需 ≥8 位，且同时包含字母和数字。修改成功后本账号全部登录态立即失效，需重新登录。
          </p>

          <label class="dialog-field">
            <span>旧密码</span>
            <input
              v-model="oldPassword"
              type="password"
              placeholder="请输入当前密码"
            />
          </label>

          <label class="dialog-field">
            <span>新密码</span>
            <input
              v-model="newPassword"
              type="password"
              placeholder="≥8 位，字母 + 数字"
            />
          </label>

          <label class="dialog-field">
            <span>确认</span>
            <input
              v-model="confirmPassword"
              type="password"
              placeholder="请再次输入新密码"
            />
          </label>

          <p
            v-if="pwError"
            class="dialog-error"
          >
            {{ pwError }}
          </p>

          <div class="dialog-actions">
            <button
              class="secondary-button"
              type="button"
              @click="closePasswordDialog"
            >
              取消
            </button>

            <button
              class="primary-button"
              :disabled="pwSubmitting"
              type="button"
              @click="submitPasswordChange"
            >
              {{ pwSubmitting ? "修改中..." : "确认修改" }}
            </button>
          </div>
        </template>

        <template v-else>
          <h3>
            密码修改成功
          </h3>

          <p class="dialog-hint">
            本账号已退出登录，请使用新密码重新登录。
          </p>

          <div class="dialog-actions">
            <button
              class="primary-button"
              type="button"
              @click="closePasswordDialog"
            >
              去登录
            </button>
          </div>
        </template>
      </div>
    </div>
  </div>
</template>
