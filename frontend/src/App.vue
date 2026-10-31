<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from "vue"
import { useRoute, useRouter } from "vue-router"

import { health, logout } from "./api"
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
  clearSession()
  void router.push("/")
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
  </div>
</template>
