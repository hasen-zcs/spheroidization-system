<script setup lang="ts">
import { computed } from "vue"
import { useRoute } from "vue-router"

const route = useRoute()

const activeTitle = computed(() => {
  return String(route.meta.title ?? "")
})

const recordsViewKey = computed(() => {
  return route.fullPath
})
</script>

<template>
  <div class="records-wrapper">
    <aside class="sidebar">
      <div class="sidebar-header">
        功能菜单
      </div>

      <router-link
        class="menu-item"
        to="/records/home"
      >
        首页
      </router-link>

      <router-link
        class="menu-item"
        to="/records/spheroidization"
      >
        球化记录
      </router-link>

      <router-link
        class="menu-item"
        to="/records/abnormal"
      >
        异常记录
      </router-link>

      <router-link
        class="menu-item"
        to="/records/standard"
      >
        检测标准
      </router-link>
    </aside>

    <section class="records-content">
      <nav class="tabs">
        <router-link
          class="tab"
          to="/records/home"
        >
          首页
        </router-link>

        <div
          v-if="route.path !== '/records/home'"
          class="tab active"
        >
          {{ activeTitle }}
        </div>
      </nav>

      <div class="records-view">
        <router-view
          :key="recordsViewKey"
        />
      </div>
    </section>
  </div>
</template>

<style scoped>
.records-wrapper {
  display: flex;
  height: calc(100vh - 40px);
  overflow: hidden;
  background: #f0f2f5;
}

.sidebar {
  display: flex;
  flex: 0 0 180px;
  flex-direction: column;
  background: #fff;
  border-right: 1px solid #d9d9d9;
}

.sidebar-header {
  padding: 10px 15px;
  color: #1890ff;
  font-size: 12px;
  font-weight: 700;
  background: #e6f7ff;
  border-bottom: 1px solid #d9d9d9;
}

.menu-item {
  display: flex;
  align-items: center;
  min-height: 38px;
  padding: 10px 15px;
  color: #333;
  font-size: 12px;
  text-decoration: none;
  border-bottom: 1px solid #f0f0f0;
  border-right: 3px solid transparent;
}

.menu-item:hover {
  background: #f5f5f5;
}

.menu-item.router-link-active {
  color: #1890ff;
  background: #e6f7ff;
  border-right-color: #1890ff;
}

.records-content {
  display: flex;
  flex: 1;
  flex-direction: column;
  min-width: 0;
  padding: 10px;
  overflow: hidden;
}

.tabs {
  display: flex;
  flex: 0 0 auto;
  min-height: 34px;
  background: #e6e6e6;
  border: 1px solid #ccc;
  border-bottom: 0;
}

.tab {
  display: flex;
  align-items: center;
  min-width: 80px;
  padding: 7px 15px;
  color: #555;
  font-size: 12px;
  text-decoration: none;
  background: #f0f0f0;
  border-right: 1px solid #ccc;
}

.tab:hover {
  background: #f7f7f7;
}

.tab.active,
.tab.router-link-active {
  color: #1890ff;
  background: #fff;
}

.records-view {
  flex: 1;
  min-height: 0;
  overflow: auto;
}

@media (max-width: 768px) {
  .sidebar {
    flex-basis: 104px;
  }

  .menu-item {
    padding-inline: 10px;
  }
}
</style>
