<script setup lang="ts">
import { useRouter } from "vue-router"

const router = useRouter()
</script>

<template>
  <div class="forbidden-page">
    <div class="forbidden-card">
      <div class="forbidden-code">
        403
      </div>

      <h1>
        没有访问权限
      </h1>

      <p>
        您没有访问该页面的权限，请联系管理员分配权限。
      </p>

      <button
        class="primary-button"
        type="button"
        @click="router.push('/')"
      >
        返回首页
      </button>
    </div>
  </div>
</template>
