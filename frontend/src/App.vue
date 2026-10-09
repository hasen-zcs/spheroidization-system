<script setup lang="ts">
import { onMounted, ref } from "vue"

import { health } from "./api"

type SystemStatus = "checking" | "online" | "offline"

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

onMounted(() => {
  checkSystemStatus()
})
</script>

<template>
  <div class="app-shell">
    <header class="nav-bar">
      <router-link
        class="logo"
        to="/"
      >
        <span class="logo-icon"></span>
        采集管理
      </router-link>

      <nav class="nav-links">
        <router-link to="/">
          浇注工位监控
        </router-link>

        <router-link to="/records/abnormal">
          异常记录
        </router-link>
      </nav>

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
    </header>

    <main class="app-content">
      <router-view />
    </main>
  </div>
</template>
