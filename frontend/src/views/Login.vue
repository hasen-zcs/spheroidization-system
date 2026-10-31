<script setup lang="ts">
import { onMounted, ref } from "vue"
import { useRoute, useRouter } from "vue-router"

import { login } from "../api"
import { applySession, isLoggedIn } from "../auth"

const route = useRoute()
const router = useRouter()

const username = ref("")
const password = ref("")
const errorMessage = ref("")
const submitting = ref(false)

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
      // token 与用户信息写入登录态，跳回 redirect 页面（没有则回首页）
      applySession(result.data)
      void router.push(safeRedirectPath())
      return
    }

    // 业务失败统一提示，不区分账号不存在与密码错误；
    // 网络错误（连不上后端）才显示原始信息
    errorMessage.value =
      result.code === -1 ? result.message : "用户名或密码不正确"
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
          autocomplete="username"
          placeholder="请输入用户名"
        />
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
