<script setup lang="ts">
import { onMounted, ref } from "vue"
import { useRoute, useRouter } from "vue-router"

import { getAccounts, login } from "../api"
import { applySession, isLoggedIn } from "../auth"

const route = useRoute()
const router = useRouter()

const username = ref("")
const password = ref("")
const rememberPassword = ref(false)
const errorMessage = ref("")
const submitting = ref(false)
const accountOptions = ref<string[]>([])

// 记住密码存 localStorage：值是一个 {用户名: 密码} 的 JSON 对象
const SAVED_PASSWORDS_KEY = "sphero_saved_passwords"

function loadSavedPasswords(): Record<string, string> {
  try {
    const raw = localStorage.getItem(SAVED_PASSWORDS_KEY)
    const parsed = raw ? (JSON.parse(raw) as unknown) : {}
    if (
      parsed &&
      typeof parsed === "object" &&
      !Array.isArray(parsed)
    ) {
      return parsed as Record<string, string>
    }
    return {}
  } catch {
    return {}
  }
}

function persistSavedPasswords(saved: Record<string, string>): void {
  localStorage.setItem(SAVED_PASSWORDS_KEY, JSON.stringify(saved))
}

function onUsernameChange() {
  // 换账号：有存过的密码就自动填入；没有就清空，
  // 免得上一个账号的密码被误用到新账号上
  const name = username.value.trim()
  const saved = loadSavedPasswords()
  password.value = name in saved ? saved[name] : ""
}

function applyRememberedPassword(name: string): void {
  // 登录成功：勾了记住 → 写入/覆盖；没勾 → 删掉该账号的记录
  const saved = loadSavedPasswords()
  if (rememberPassword.value) {
    saved[name] = password.value
  } else {
    delete saved[name]
  }
  persistSavedPasswords(saved)
}

// redirect 参数只接受站内路径，防止跳到外部地址
function safeRedirectPath(): string {
  const target = route.query.redirect
  if (
    typeof target === "string" &&
    target.startsWith("/") &&
    !target.startsWith("//")
  ) {
    return target
  }
  return "/"
}

onMounted(() => {
  // 已登录状态访问本页，直接跳回首页
  if (isLoggedIn()) {
    void router.replace("/")
  }

  // 拉账号下拉列表；失败静默忽略，手输照样能登录
  void getAccounts().then((result) => {
    if (result.code === 200 && Array.isArray(result.data)) {
      accountOptions.value = result.data.map((item) => item.username)
    }
  })
})

async function submit() {
  if (submitting.value) {
    return
  }

  const name = username.value.trim()
  if (!name || !password.value) {
    errorMessage.value = "请输入用户名和密码"
    return
  }

  submitting.value = true
  errorMessage.value = ""

  try {
    const result = await login(name, password.value)

    if (result.code === 200 && result.data) {
      // 按勾选决定记住/清除该账号的密码
      applyRememberedPassword(name)
      // token 与用户信息写入登录态，跳回 redirect 页面（没有则回首页）
      applySession(result.data)
      void router.push(safeRedirectPath())
      return
    }

    // 密码错误/账号不存在统一提示，不区分；
    // 但后端给出的其他业务提示（如「账号已停用」）和网络错误原样显示
    errorMessage.value =
      result.message && result.message !== "用户名或密码不正确"
        ? result.message
        : "用户名或密码不正确"
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <div class="login-page">
    <form
      class="login-card"
      @submit.prevent="submit"
    >
      <h1 class="login-title">
        浇注工位AI智能化系统
      </h1>
      <p class="login-subtitle">
        采集管理 · 请登录
      </p>

      <label class="login-field">
        <span>用户名</span>
        <input
          v-model="username"
          list="account-list"
          autocomplete="username"
          placeholder="请输入用户名"
          @change="onUsernameChange"
        />
        <datalist id="account-list">
          <option
            v-for="name in accountOptions"
            :key="name"
            :value="name"
          />
        </datalist>
      </label>

      <label class="login-field">
        <span>密码</span>
        <input
          v-model="password"
          autocomplete="current-password"
          placeholder="请输入密码"
          type="password"
        />
      </label>

      <label class="login-remember">
        <input
          v-model="rememberPassword"
          type="checkbox"
        >
        <span>记住密码</span>
      </label>

      <div
        v-if="errorMessage"
        class="login-error"
      >
        {{ errorMessage }}
      </div>

      <button
        class="login-button primary-button"
        :disabled="submitting"
        type="submit"
      >
        {{ submitting ? "登录中..." : "登录" }}
      </button>
    </form>
  </div>
</template>
