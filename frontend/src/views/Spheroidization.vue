<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from "vue"
import { useRouter } from "vue-router"

import {
  processSpheroidization,
  querySpheroidization,
} from "../api"
import type { SpheroidizationRecord } from "../api"
import { can } from "../auth"
import {
  abnormalResultLabel,
  abnormalTone,
  abnormalTypeLabel,
} from "../constants"

const props = withDefaults(
  defineProps<{
    abnormalOnly?: boolean
  }>(),
  {
    abnormalOnly: false,
  }
)

const router = useRouter()

// 标记处理按钮按 action:process 权限显示
const canProcess = computed(() => can("action:process"))

const records = ref<SpheroidizationRecord[]>([])
const loading = ref(true)
const errorMessage = ref("")
const page = ref(1)
const pageSize = 20
const totalRecords = ref(0)
const processingId = ref<number | null>(null)

const resultFilter = ref("all")
const processFilter = ref("all")

const startTimeInput = ref("")
const endTimeInput = ref("")
const activeStartTime = ref("")
const activeEndTime = ref("")

function toBackendTime(value: string, isEnd: boolean): string {
  if (!value) return ""
  const [date, time] = value.split("T")
  const hh = time.split(":")[0]
  return isEnd ? `${date} ${hh}:59:59` : `${date} ${hh}:00:00`
}

const activeTimeLabel = computed(() => {
  if (!activeStartTime.value && !activeEndTime.value) return ""
  const s = activeStartTime.value ? activeStartTime.value.slice(0, 16) : "…"
  const e = activeEndTime.value
    ? activeEndTime.value.slice(0, 13) + "00"
    : "…"
  return `${s} ~ ${e}`
})

// 后端已允许部分字段为空，空值统一显示成 —，
// 不能对可能为 null 的值直接调 toFixed / slice
function display(value: string | number | null | undefined) {
  return value === null || value === undefined || value === ""
    ? "—"
    : value
}

// 进线-亮光差 = 进线时长 - 实际球化时长（秒）。
// 合并层已把迟到值弃用成 null（显示 —），这里对库里的老数据兜底：>90s 标暗赭色。
const FEED_END_LAG_LIMIT_S = 90

function feedLagDiff(record: SpheroidizationRecord): number | null {
  const total = record.spheroidization_wire_entry_total_duration
  const light = record.actual_spheroidization_time
  if (
    total === null ||
    total === undefined ||
    light === null ||
    light === undefined
  ) {
    return null
  }
  return total - light
}

function feedLagText(record: SpheroidizationRecord): string {
  const diff = feedLagDiff(record)
  return diff === null ? "—" : `${diff.toFixed(1)}s`
}

function isFeedLagLate(record: SpheroidizationRecord): boolean {
  const diff = feedLagDiff(record)
  return diff !== null && diff > FEED_END_LAG_LIMIT_S
}

async function loadRecords(silent = false) {
  if (!silent) {
    loading.value = true
  }
  errorMessage.value = ""

  try {
    const abnormal =
      resultFilter.value === "all"
        ? undefined
        : resultFilter.value === "abnormal"

    const processed =
      processFilter.value === "all"
        ? undefined
        : processFilter.value === "processed"

    const result = await querySpheroidization({
      page: page.value,
      page_size: pageSize,
      abnormal,
      processed,
      start_time: activeStartTime.value || undefined,
      end_time: activeEndTime.value || undefined,
    })

    if (result.code !== 200) {
      errorMessage.value = result.message || "加载失败"
      return
    }

    records.value = result.data?.items ?? []
    totalRecords.value = result.data?.total ?? 0
  } finally {
    loading.value = false
  }
}

// 自动轮询：每 30 秒静默刷新一次，数据入库后无需手动刷新页面
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
  // 从后台切回页面时立即刷新一次（后台期间可能漏了数据）
  visibilityHandler = () => {
    if (document.visibilityState === "visible") {
      void loadRecords(true)
    }
  }
  document.addEventListener("visibilitychange", visibilityHandler)
}

function stopPolling() {
  if (pollTimer !== null) {
    window.clearInterval(pollTimer)
    pollTimer = null
  }
  if (visibilityHandler) {
    document.removeEventListener("visibilitychange", visibilityHandler)
    visibilityHandler = null
  }
}

onUnmounted(() => {
  stopPolling()
})

// 点击整行 = 点击“查看详情”，直接进入球化记录详情页
function openDetail(record: SpheroidizationRecord, event: MouseEvent) {
  const target = event.target as Element | null

  // 行内的链接/按钮自己会处理，这里不重复处理
  if (target?.closest("a, button")) {
    return
  }

  router.push(`/spheroidization/${record.id}`)
}

async function markProcessed(record: SpheroidizationRecord) {
  const confirmed = window.confirm(
    "处置不可逆，确认将该记录标记为已处理吗？"
  )
  if (!confirmed) {
    return
  }

  processingId.value = record.id
  try {
    // 处理人由后端按登录态取，前端不再传
    const result = await processSpheroidization(record.id)

    if (result.code === 200) {
      await loadRecords(true)
    } else {
      alert(result.message || "标记处理失败")
    }
  } finally {
    processingId.value = null
  }
}

const totalPages = computed(() =>
  Math.max(1, Math.ceil(totalRecords.value / pageSize))
)

function applyFilters() {
  page.value = 1
  loadRecords()
}

function applyTimeFilter() {
  activeStartTime.value = toBackendTime(startTimeInput.value, false)
  activeEndTime.value = toBackendTime(endTimeInput.value, true)
  page.value = 1
  loadRecords()
}

function clearTimeFilter() {
  startTimeInput.value = ""
  endTimeInput.value = ""
  activeStartTime.value = ""
  activeEndTime.value = ""
  page.value = 1
  loadRecords()
}

function changePage(nextPage: number) {
  if (nextPage < 1 || nextPage > totalPages.value) {
    return
  }
  page.value = nextPage
  loadRecords()
}

watch(
  () => props.abnormalOnly,
  (abnormalOnly) => {
    resultFilter.value = abnormalOnly ? "abnormal" : "all"
    processFilter.value = "all"
    startTimeInput.value = ""
    endTimeInput.value = ""
    activeStartTime.value = ""
    activeEndTime.value = ""
    page.value = 1
    loadRecords()
  }
)

onMounted(() => {
  resultFilter.value = props.abnormalOnly ? "abnormal" : "all"
  page.value = 1

  loadRecords()
  startPolling()
})
</script>

<template>
  <div class="records-page">
    <div class="page-heading">
      <div>
        <h1>
          {{ abnormalOnly ? "异常记录" : "球化记录" }}
        </h1>
        <p>
          {{
            abnormalOnly
              ? "查看机器检测产生的异常记录"
              : "查询和管理球化检测记录"
          }}
        </p>
      </div>

      <div class="header-actions">
        <button
          class="secondary-button"
          type="button"
          @click="loadRecords()"
        >
          刷新
        </button>
      </div>
    </div>

    <section class="panel search-panel">
      <div class="form-group">
        <label>检测结果</label>

        <select
          v-model="resultFilter"
          :disabled="abnormalOnly"
        >
          <option value="all">全部</option>
          <option value="normal">正常</option>
          <option value="abnormal">异常</option>
        </select>
      </div>

      <div class="form-group">
        <label>处理状态</label>

        <select v-model="processFilter">
          <option value="all">全部</option>
          <option value="processed">已处理</option>
          <option value="unprocessed">未处理</option>
        </select>
      </div>

      <div class="time-range-group">
        <label>起</label>
        <input
          v-model="startTimeInput"
          type="datetime-local"
          class="time-input"
        />
        <label>止</label>
        <input
          v-model="endTimeInput"
          type="datetime-local"
          class="time-input"
        />
        <button
          class="time-apply-btn"
          type="button"
          @click="applyTimeFilter"
        >
          应用
        </button>
        <a
          v-if="activeTimeLabel"
          class="time-clear-link"
          href="javascript:void(0)"
          @click.prevent="clearTimeFilter"
        >
          清除
        </a>
      </div>

      <span
        v-if="activeTimeLabel"
        class="time-range-label"
      >
        {{ activeTimeLabel }}
      </span>

      <button
        class="primary-button search-button"
        type="button"
        @click="applyFilters"
      >
        查询
      </button>
    </section>

    <section class="panel table-panel">
      <div
        v-if="loading"
        class="empty-state"
      >
        正在加载数据...
      </div>

      <div
        v-else-if="errorMessage"
        class="empty-state"
      >
        {{ errorMessage }}
      </div>

      <div
        v-else-if="records.length === 0"
        class="empty-state"
      >
        暂无符合条件的记录
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
              <th>铁水重量</th>
              <th>铁水温度</th>
              <th>测温时间</th>
              <th>球化开始时间</th>
              <th>球化结束时间</th>
              <th>进线开始时间</th>
              <th>进线结束时间</th>
              <th>标准/实际球化时长</th>
              <th>实际进线时间</th>
              <th>进线-亮光差</th>
              <th v-if="abnormalOnly">异常类型</th>
              <th v-if="abnormalOnly">异常原因</th>
              <th>检测结果</th>
              <th>复核状态</th>
              <th>处理状态</th>
              <th>操作</th>
            </tr>
          </thead>

          <tbody>
            <tr
              v-for="record in records"
              :key="record.id"
              class="row-clickable"
              @click="openDetail(record, $event)"
            >
              <td>{{ record.id }}</td>
              <td>{{ record.detection_time }}</td>
              <td>{{ display(record.spheroidization_weight) }}</td>
              <td>{{ display(record.temperature) }}</td>
              <td>{{ display(record.temperature_time) }}</td>
              <td>{{ display(record.spheroidization_start_time) }}</td>
              <td>{{ display(record.spheroidization_end_time) }}</td>
              <td>
                {{ display(record.spheroidization_wire_entry_start_time) }}
              </td>
              <td>
                {{ display(record.spheroidization_wire_entry_end_time) }}
              </td>
              <td>
                {{ record.standard_spheroidization_time }} /
                {{ display(record.actual_spheroidization_time) }}
              </td>
              <td>
                {{ display(record.spheroidization_wire_entry_total_duration) }}
              </td>
              <td>
                <span :class="{ 'feed-lag-late': isFeedLagLate(record) }">
                  {{ feedLagText(record) }}
                </span>
                <span
                  v-if="isFeedLagLate(record)"
                  class="feed-lag-late-mark"
                >
                  迟到
                </span>
              </td>
              <td
                v-if="abnormalOnly"
                class="status-abnormal"
              >
                {{ abnormalTypeLabel(record.abnormal_type) }}
              </td>
              <td v-if="abnormalOnly">
                {{ display(record.abnormal_reason) }}
              </td>
              <td>
                <span
                  :class="`status-${abnormalTone(record.spheroidization_abnormal)}`"
                >
                  {{
                    abnormalResultLabel(record.spheroidization_abnormal)
                  }}
                </span>
              </td>
              <td>
                <!-- 最新一条复核的结论；一次都没复核过就留空 -->
                <span
                  v-if="record.review_result"
                  :class="
                    record.review_result === '异常'
                      ? 'status-abnormal'
                      : 'status-normal'
                  "
                >
                  {{ record.review_result }}
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
              <td class="action-cell">
                <router-link
                  class="table-link"
                  :to="`/spheroidization/${record.id}`"
                >
                  查看详情
                </router-link>

                <button
                  v-if="!record.processed && canProcess"
                  class="text-button"
                  :disabled="processingId !== null"
                  type="button"
                  @click="markProcessed(record)"
                >
                  {{
                    processingId === record.id
                      ? "处理中..."
                      : "标记处理"
                  }}
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <div
        v-if="totalRecords > 0"
        class="pagination"
      >
        <button
          class="secondary-button"
          type="button"
          :disabled="page <= 1"
          @click="changePage(page - 1)"
        >
          上一页
        </button>

        <span>
          第 {{ page }} / {{ totalPages }} 页，共 {{ totalRecords }} 条
        </span>

        <button
          class="secondary-button"
          type="button"
          :disabled="page >= totalPages"
          @click="changePage(page + 1)"
        >
          下一页
        </button>
      </div>
    </section>
  </div>
</template>

<style scoped>
.records-page {
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

.search-panel {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 16px;
  margin-bottom: 10px;
  padding: 10px 14px;
}

.form-group {
  display: flex;
  align-items: center;
  gap: 8px;
  color: #666;
  font-size: 12px;
}

.form-group select {
  min-width: 120px;
  min-height: 30px;
  padding: 4px 8px;
  color: #1a2a3a;
  background: #fff;
  border: 1px solid #d9d9d9;
  border-radius: 2px;
}

.form-group select:disabled {
  color: #888;
  background: #f5f5f5;
}

.search-button {
  margin-left: auto;
}

.pagination {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 12px;
  padding: 12px 14px 0;
  color: #666;
  font-size: 12px;
}

.table-panel {
  min-height: 220px;
}

.table-scroll {
  overflow: auto;
}

table {
  width: 100%;
  min-width: 2350px;
  font-size: 12px;
  border-collapse: collapse;
}

th,
td {
  padding: 9px 10px;
  text-align: left;
  white-space: nowrap;
  border-bottom: 1px solid #e8e8e8;
}

th {
  position: sticky;
  top: 0;
  z-index: 1;
  color: #333;
  font-weight: 700;
  background: #fafafa;
  border-bottom-color: #d9d9d9;
}

tbody tr:nth-child(even) {
  background: #fafafa;
}

tbody tr:hover {
  background: #e6f7ff;
}

.row-clickable {
  cursor: pointer;
}

.table-link {
  margin-right: 10px;
  color: #1890ff;
  text-decoration: none;
}

.table-link:hover {
  text-decoration: underline;
}

.action-cell {
  white-space: nowrap;
}

.feed-lag-late {
  color: #8a3b2e;
  font-weight: 600;
}

.feed-lag-late-mark {
  margin-left: 4px;
  color: #8a3b2e;
  font-size: 11px;
}

.time-range-group {
  display: flex;
  align-items: center;
  gap: 6px;
  color: #666;
  font-size: 12px;
}

.time-range-group label {
  color: #666;
  font-size: 12px;
  white-space: nowrap;
}

.time-input {
  min-height: 30px;
  padding: 4px 8px;
  color: #1a2a3a;
  background: #fff;
  border: 1px solid #d9d9d9;
  border-radius: 2px;
  font-size: 12px;
}

.time-apply-btn {
  min-height: 30px;
  padding: 4px 12px;
  color: #fff;
  background: #B08D3E;
  border: 1px solid #B08D3E;
  border-radius: 2px;
  font-size: 12px;
  cursor: pointer;
}

.time-apply-btn:hover {
  background: #9a7a34;
  border-color: #9a7a34;
}

.time-clear-link {
  color: #1890ff;
  font-size: 12px;
  text-decoration: none;
  white-space: nowrap;
}

.time-clear-link:hover {
  text-decoration: underline;
}

.time-range-label {
  color: #B08D3E;
  font-size: 12px;
  white-space: nowrap;
  border: 1px solid #B08D3E;
  border-radius: 2px;
  padding: 3px 8px;
  background: #fdf8ef;
}

@media (max-width: 600px) {
  .page-heading {
    align-items: flex-start;
    flex-direction: column;
  }

  .search-button {
    margin-left: 0;
  }
}
</style>
