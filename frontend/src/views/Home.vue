<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from "vue"

import {
  getSpheroidizationStats,
  querySpheroidization,
} from "../api"
import type { SpheroidizationStats } from "../api"
import type { SpheroidizationRecord } from "../api"

const records = ref<SpheroidizationRecord[]>([])
const loading = ref(true)
const errorMessage = ref("")
const statistics = ref<SpheroidizationStats>({
  total: 0,
  abnormal: 0,
  processed: 0,
  unprocessed: 0,
})

async function loadRecords(silent = false) {
  if (!silent) {
    loading.value = true
  }
  errorMessage.value = ""

  try {
    const [recordsResult, statsResult] = await Promise.all([
      querySpheroidization({ page: 1, page_size: 5 }),
      getSpheroidizationStats(),
    ])

    if (recordsResult.code !== 200 || statsResult.code !== 200) {
      errorMessage.value =
        recordsResult.message || statsResult.message || "加载失败"
      return
    }

    records.value = recordsResult.data?.items ?? []
    if (statsResult.data) {
      statistics.value = statsResult.data
    }
  } finally {
    loading.value = false
  }
}

const totalCount = computed(() => {
  return statistics.value.total
})

const abnormalCount = computed(() => {
  return statistics.value.abnormal
})

const processedCount = computed(() => {
  return statistics.value.processed
})

const unprocessedCount = computed(() => {
  return statistics.value.unprocessed
})

const recentRecords = computed(() => {
  return [...records.value].sort((a, b) => b.id - a.id)
})

// 后端已允许部分时间字段为空，空值统一显示成 —，
// 不能对可能为 null 的值直接调 toFixed / slice
function display(value: string | number | null | undefined) {
  return value === null || value === undefined || value === ""
    ? "—"
    : value
}

// 自动轮询：每 30 秒静默刷新一次，新数据入库后无需手动刷新
const POLL_INTERVAL_MS = 30000
let pollTimer: number | null = null
let visibilityHandler: (() => void) | null = null

function startPolling() {
  if (pollTimer !== null) {
    return
  }
  pollTimer = window.setInterval(() => {
    void loadRecords(true)
  }, POLL_INTERVAL_MS)
  // 从后台切回页面时立即刷新一次
  visibilityHandler = () => {
    if (document.visibilityState === "visible") {
      void loadRecords(true)
    }
  }
  document.addEventListener("visibilitychange", visibilityHandler)
}

onUnmounted(() => {
  if (pollTimer !== null) {
    window.clearInterval(pollTimer)
    pollTimer = null
  }
  if (visibilityHandler) {
    document.removeEventListener("visibilitychange", visibilityHandler)
    visibilityHandler = null
  }
})

onMounted(() => {
  loadRecords()
  startPolling()
})
</script>

<template>
  <div class="dashboard">
    <div class="page-header">
      <div>
        <h1>球化监测系统</h1>
        <p>球化检测运行情况概览</p>
      </div>

      <button
        class="secondary-button"
        type="button"
        @click="loadRecords()"
      >
        刷新
      </button>
    </div>

    <div
      v-if="loading"
      class="empty-state panel"
    >
      正在加载数据...
    </div>

    <div
      v-else-if="errorMessage"
      class="empty-state panel"
    >
      {{ errorMessage }}
    </div>

    <template v-else>
      <div class="statistics">
        <div class="stat-card">
          <span>总记录数</span>
          <strong>{{ totalCount }}</strong>
        </div>

        <div class="stat-card">
          <span>异常记录</span>
          <strong class="status-abnormal">
            {{ abnormalCount }}
          </strong>
        </div>

        <div class="stat-card">
          <span>已处理</span>
          <strong class="status-normal">
            {{ processedCount }}
          </strong>
        </div>

        <div class="stat-card">
          <span>未处理</span>
          <strong class="status-unprocessed">
            {{ unprocessedCount }}
          </strong>
        </div>
      </div>

      <section class="panel data-panel">
        <div class="section-header">
          <h2>最近检测记录</h2>

          <router-link
            class="text-link"
            to="/records/spheroidization"
          >
            查看全部
          </router-link>
        </div>

        <div
          v-if="recentRecords.length === 0"
          class="empty-state"
        >
          暂无检测记录
        </div>

        <div
          v-else
          class="table-scroll"
        >
          <table>
            <thead>
              <tr>
                <th>ID</th>
                <th>检测时间</th>
                <th>球化开始时间</th>
                <th>球化结束时间</th>
                <th>检测结果</th>
                <th>处理状态</th>
                <th>操作</th>
              </tr>
            </thead>

            <tbody>
              <tr
                v-for="record in recentRecords"
                :key="record.id"
              >
                <td>{{ record.id }}</td>
                <td>{{ record.detection_time }}</td>
                <td>
                  {{ display(record.spheroidization_start_time) }}
                </td>
                <td>
                  {{ display(record.spheroidization_end_time) }}
                </td>
                <td>
                  <span
                    :class="
                      record.spheroidization_abnormal
                        ? 'status-abnormal'
                        : 'status-normal'
                    "
                  >
                    {{
                      record.spheroidization_abnormal
                        ? "异常"
                        : "正常"
                    }}
                  </span>
                </td>
                <td>
                  <span
                    :class="
                      record.processed
                        ? 'status-normal'
                        : 'status-unprocessed'
                    "
                  >
                    {{
                      record.processed
                        ? "已处理"
                        : "未处理"
                    }}
                  </span>
                </td>
                <td>
                  <router-link
                    class="text-link"
                    :to="`/spheroidization/${record.id}`"
                  >
                    查看详情
                  </router-link>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      <section class="panel data-panel">
        <div class="section-header">
          <h2>快捷操作</h2>
        </div>

        <div class="quick-actions">
          <router-link
            class="quick-action"
            to="/records/spheroidization"
          >
            查看球化记录
          </router-link>

          <router-link
            class="quick-action"
            to="/records/standard"
          >
            管理检测标准
          </router-link>
        </div>
      </section>
    </template>
  </div>
</template>

<style scoped>
.dashboard {
  min-height: 100%;
  padding: 12px;
  background: #f5f7fa;
}

.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 20px;
  margin-bottom: 12px;
  padding: 14px 16px;
  background: #fff;
  border: 1px solid #d9d9d9;
}

.page-header h1 {
  margin-bottom: 4px;
  color: #003399;
  font-size: 18px;
}

.page-header p {
  color: #777;
  font-size: 12px;
}

.statistics {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
  margin-bottom: 10px;
}

.stat-card {
  padding: 16px;
  background: #fff;
  border: 1px solid #d9d9d9;
}

.stat-card span {
  display: block;
  margin-bottom: 8px;
  color: #777;
  font-size: 12px;
}

.stat-card strong {
  font-size: 26px;
}

.data-panel {
  margin-bottom: 10px;
  padding: 14px 16px;
}

.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 12px;
}

.section-header h2 {
  color: #1a2a3a;
  font-size: 15px;
}

.text-link {
  color: #1890ff;
  font-size: 12px;
  text-decoration: none;
}

.table-scroll {
  overflow-x: auto;
}

table {
  width: 100%;
  min-width: 720px;
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

tbody tr:hover {
  background: #f5fbff;
}

.quick-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.quick-action {
  padding: 9px 14px;
  color: #1890ff;
  font-size: 12px;
  text-decoration: none;
  background: #f0f8ff;
  border: 1px solid #bae0ff;
}

.quick-action:hover {
  background: #e6f7ff;
}

@media (max-width: 900px) {
  .statistics {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 520px) {
  .statistics {
    grid-template-columns: 1fr;
  }

  .page-header {
    align-items: flex-start;
  }
}
</style>
