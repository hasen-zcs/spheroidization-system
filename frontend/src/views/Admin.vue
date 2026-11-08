<script setup lang="ts">
import { computed, onMounted, onUnmounted, reactive, ref } from "vue"

import {
  adminGetCurrentStandardId,
  adminQueryRecords,
  adminQueryReviews,
  adminQueryStandards,
  adminQuerySwitchLogs,
  changeProcessed,
  deleteRecord,
  deleteReview,
  deleteStandard,
  deleteSwitchLog,
  restoreRecord,
  restoreReview,
  restoreStandard,
  restoreSwitchLog,
} from "../api/admin"
import type {
  AdminRecordItem,
  AdminReviewItem,
  AdminStandardItem,
  AdminSwitchLogItem,
} from "../api/admin"
import { abnormalResultLabel, abnormalTone } from "../constants"

// 管理员「数据管理」页。入口权限 action:manage_data（路由守卫已拦），
// 页内四个 tab 各自独立分页（page_size=20），右上角「显示已删除」独立开关。
// 全部软删除：删除要原因（必填），恢复无需原因。

type TabKey = "records" | "standards" | "switches" | "reviews"

const TABS: Array<{ key: TabKey; label: string }> = [
  { key: "records", label: "球化记录" },
  { key: "standards", label: "检测标准" },
  { key: "switches", label: "切换记录" },
  { key: "reviews", label: "复核记录" },
]

const PAGE_SIZE = 20

interface TabState {
  page: number
  total: number
  includeDeleted: boolean
  loading: boolean
  error: string
  loaded: boolean
}

function newTabState(): TabState {
  return {
    page: 1,
    total: 0,
    includeDeleted: false,
    loading: false,
    error: "",
    loaded: false,
  }
}

const activeTab = ref<TabKey>("records")
const tabs = reactive<Record<TabKey, TabState>>({
  records: newTabState(),
  standards: newTabState(),
  switches: newTabState(),
  reviews: newTabState(),
})

const activeState = computed(() => tabs[activeTab.value])

const records = ref<AdminRecordItem[]>([])
const standardsAll = ref<AdminStandardItem[]>([])
const currentStandardId = ref<number | null>(null)
const switchLogs = ref<AdminSwitchLogItem[]>([])
const reviews = ref<AdminReviewItem[]>([])

// 检测标准历史接口不分页（一次给全量），分页在前端切
const standardItems = computed(() => {
  const state = tabs.standards
  const start = (state.page - 1) * PAGE_SIZE
  return standardsAll.value.slice(start, start + PAGE_SIZE)
})

// 空值统一显示成 —
function display(value: string | number | null | undefined) {
  return value === null || value === undefined || value === ""
    ? "—"
    : value
}

function deleteMeta(row: {
  deleted_at: string | null
  deleted_by: string | null
  delete_reason: string | null
}): string {
  if (!row.deleted_at) {
    return ""
  }
  return [row.deleted_by, row.deleted_at, row.delete_reason]
    .filter(Boolean)
    .join(" · ")
}

function processedMeta(record: AdminRecordItem): string {
  return [record.processed_by, record.processed_at]
    .filter(Boolean)
    .join(" · ")
}

function standardText(
  id: number | null | undefined,
  value: number | null
): string {
  if (id === null || id === undefined) {
    return "（无）"
  }
  return value === null ? `标准${id}` : `标准${id}（${value}s）`
}

function rangeText(standard: AdminStandardItem): string {
  const lower = standard.standard_spheroidization_time_lower
  const upper = standard.standard_spheroidization_time_upper
  return `${lower === null ? "—" : lower}s ~ ${upper === null ? "—" : upper}s`
}

// ====================
// 加载
// ====================

async function loadTab(key: TabKey, silent = false) {
  const state = tabs[key]
  if (!silent) {
    state.loading = true
  }
  state.error = ""

  try {
    if (key === "records") {
      const result = await adminQueryRecords({
        page: state.page,
        page_size: PAGE_SIZE,
        include_deleted: state.includeDeleted,
      })
      if (result.code !== 200) {
        throw new Error(result.message || "加载球化记录失败")
      }
      records.value = result.data?.items ?? []
      state.total = result.data?.total ?? 0
    } else if (key === "standards") {
      const result = await adminQueryStandards(state.includeDeleted)
      if (result.code !== 200) {
        throw new Error(result.message || "加载检测标准失败")
      }
      standardsAll.value = result.data ?? []
      state.total = standardsAll.value.length
      // 当前生效标准单独取：删除按钮要禁用它
      currentStandardId.value = await adminGetCurrentStandardId()
    } else if (key === "switches") {
      const result = await adminQuerySwitchLogs({
        page: state.page,
        page_size: PAGE_SIZE,
        include_deleted: state.includeDeleted,
      })
      if (result.code !== 200) {
        throw new Error(result.message || "加载切换记录失败")
      }
      switchLogs.value = result.data?.items ?? []
      state.total = result.data?.total ?? 0
    } else {
      const result = await adminQueryReviews({
        page: state.page,
        page_size: PAGE_SIZE,
        include_deleted: state.includeDeleted,
      })
      if (result.code !== 200) {
        throw new Error(result.message || "加载复核记录失败")
      }
      reviews.value = result.data?.items ?? []
      state.total = result.data?.total ?? 0
    }
    state.loaded = true
  } catch (error) {
    state.error = error instanceof Error ? error.message : "加载失败"
  } finally {
    state.loading = false
  }
}

function switchTab(key: TabKey) {
  activeTab.value = key
  // 切回来不重复拉：首次激活才加载
  if (!tabs[key].loaded) {
    void loadTab(key)
  }
}

function changePage(next: number) {
  const state = activeState.value
  if (next < 1 || next > totalPages(state)) {
    return
  }
  state.page = next
  void loadTab(activeTab.value)
}

function totalPages(state: TabState): number {
  return Math.max(1, Math.ceil(state.total / PAGE_SIZE))
}

function toggleDeleted(checked: boolean) {
  const state = activeState.value
  state.includeDeleted = checked
  state.page = 1
  void loadTab(activeTab.value)
}

function reloadActive() {
  void loadTab(activeTab.value)
}

// ====================
// 成功提示（沿用现有 notice-bar 机制，失败沿用 alert）
// ====================

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

// ====================
// 删除（原因必填，trim 后为空禁用确定）
// ====================

interface DeleteTarget {
  tab: TabKey
  id: number
  label: string
}

const deleteTarget = ref<DeleteTarget | null>(null)
const deleteReason = ref("")
const deleteBusy = ref(false)
const canConfirmDelete = computed(() => deleteReason.value.trim().length > 0)

function openDeleteDialog(tab: TabKey, id: number, label: string) {
  deleteTarget.value = { tab, id, label }
  deleteReason.value = ""
}

async function submitDelete() {
  const target = deleteTarget.value
  if (!target || !canConfirmDelete.value || deleteBusy.value) {
    return
  }

  deleteBusy.value = true
  try {
    const reason = deleteReason.value.trim()
    const result =
      target.tab === "records"
        ? await deleteRecord(target.id, reason)
        : target.tab === "standards"
          ? await deleteStandard(target.id, reason)
          : target.tab === "switches"
            ? await deleteSwitchLog(target.id, reason)
            : await deleteReview(target.id, reason)

    if (result.code === 200) {
      deleteTarget.value = null
      flashNotice(result.message || "删除成功")
      await loadTab(target.tab)
    } else {
      alert(result.message || "删除失败")
    }
  } finally {
    deleteBusy.value = false
  }
}

// ====================
// 处理状态 0 ↔ 1（球化记录 tab，原因必填）
// ====================

const processedTarget = ref<AdminRecordItem | null>(null)
const processedReason = ref("")
const processedBusy = ref(false)
const canConfirmProcessed = computed(
  () => processedReason.value.trim().length > 0
)

function openProcessedDialog(record: AdminRecordItem) {
  processedTarget.value = record
  processedReason.value = ""
}

async function submitProcessed() {
  const target = processedTarget.value
  if (!target || !canConfirmProcessed.value || processedBusy.value) {
    return
  }

  processedBusy.value = true
  try {
    const next = target.processed ? 0 : 1
    const result = await changeProcessed(
      target.id,
      next,
      processedReason.value.trim()
    )

    if (result.code === 200) {
      processedTarget.value = null
      flashNotice(result.message || "处理状态已更新")
      await loadTab("records")
    } else {
      alert(result.message || "操作失败")
    }
  } finally {
    processedBusy.value = false
  }
}

// ====================
// 恢复（无需原因）
// ====================

const restoringId = ref<number | null>(null)

async function restore(tab: TabKey, id: number) {
  if (restoringId.value !== null) {
    return
  }

  restoringId.value = id
  try {
    const result =
      tab === "records"
        ? await restoreRecord(id)
        : tab === "standards"
          ? await restoreStandard(id)
          : tab === "switches"
            ? await restoreSwitchLog(id)
            : await restoreReview(id)

    if (result.code === 200) {
      flashNotice(result.message || "恢复成功")
      await loadTab(tab)
    } else {
      alert(result.message || "恢复失败")
    }
  } finally {
    restoringId.value = null
  }
}

// 自动轮询：管理员数据页每 30 秒静默刷新当前 tab；
// 删除/标记/恢复弹窗打开时暂停，避免把正在操作的行刷掉
const POLL_INTERVAL_MS = 30000
let pollTimer: number | null = null
let visibilityHandler: (() => void) | null = null

function isInteracting() {
  return (
    deleteTarget.value !== null ||
    processedTarget.value !== null ||
    deleteBusy.value ||
    processedBusy.value ||
    restoringId.value !== null
  )
}

function pollRefresh() {
  if (isInteracting()) {
    return
  }
  void loadTab(activeTab.value, true)
}

function startPolling() {
  if (pollTimer !== null) {
    return
  }
  pollTimer = window.setInterval(pollRefresh, POLL_INTERVAL_MS)
  visibilityHandler = () => {
    if (document.visibilityState === "visible") {
      pollRefresh()
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

onMounted(() => {
  void loadTab("records")
  startPolling()
})
</script>

<template>
  <div class="admin-page">
    <div class="page-shell">
      <div class="page-heading">
        <div>
          <span class="overline">Data Management</span>
          <h1>数据管理</h1>
          <p>四类数据的软删除 / 恢复 / 处理状态维护，删除可恢复</p>
        </div>

        <div class="header-actions">
          <button
            class="secondary-button"
            type="button"
            @click="reloadActive"
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

      <div class="tab-bar">
        <button
          v-for="tab in TABS"
          :key="tab.key"
          class="tab-item"
          :class="{ active: activeTab === tab.key }"
          type="button"
          @click="switchTab(tab.key)"
        >
          {{ tab.label }}
        </button>
      </div>

      <section class="panel table-panel">
        <div class="tab-toolbar">
          <span class="tab-count">
            共 {{ activeState.total }} 条
          </span>

          <label class="deleted-switch">
            <input
              :checked="activeState.includeDeleted"
              type="checkbox"
              @change="
                toggleDeleted(($event.target as HTMLInputElement).checked)
              "
            />
            <span>显示已删除</span>
          </label>
        </div>

        <div
          v-if="activeState.loading"
          class="empty-state"
        >
          正在加载数据...
        </div>

        <div
          v-else-if="activeState.error"
          class="empty-state"
        >
          {{ activeState.error }}
        </div>

        <!-- Tab1 球化记录 -->
        <template v-else-if="activeTab === 'records'">
          <div
            v-if="records.length === 0"
            class="empty-state"
          >
            暂无记录
          </div>

          <div
            v-else
            class="table-scroll"
          >
            <table>
              <thead>
                <tr>
                  <th>检测时间</th>
                  <th>实际球化时长</th>
                  <th>判定</th>
                  <th>处理状态</th>
                  <th>删除状态</th>
                  <th>操作</th>
                </tr>
              </thead>

              <tbody>
                <tr
                  v-for="record in records"
                  :key="record.id"
                  :class="{ 'row-deleted': record.deleted_at !== null }"
                >
                  <td>{{ record.detection_time }}</td>
                  <td>
                    {{ display(record.actual_spheroidization_time) }}{{
                      record.actual_spheroidization_time !== null ? "s" : ""
                    }}
                  </td>
                  <td>
                    <span
                      :class="
                        `status-${abnormalTone(record.spheroidization_abnormal)}`
                      "
                    >
                      {{ abnormalResultLabel(record.spheroidization_abnormal) }}
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
                      {{ record.processed ? "已处理" : "未处理" }}
                    </span>
                    <div
                      v-if="processedMeta(record)"
                      class="cell-meta"
                    >
                      {{ processedMeta(record) }}
                    </div>
                  </td>
                  <td>
                    <span
                      v-if="record.deleted_at"
                      class="deleted-tag"
                    >
                      已删除
                    </span>
                    <span
                      v-else
                      class="status-normal"
                    >
                      正常
                    </span>
                    <div
                      v-if="record.deleted_at"
                      class="cell-meta"
                    >
                      {{ deleteMeta(record) }}
                    </div>
                  </td>
                  <td class="action-cell">
                    <template v-if="record.deleted_at">
                      <button
                        class="text-button"
                        type="button"
                        @click="restore('records', record.id)"
                      >
                        恢复
                      </button>
                    </template>

                    <template v-else>
                      <button
                        class="text-button"
                        type="button"
                        @click="openProcessedDialog(record)"
                      >
                        {{
                          record.processed ? "撤销处理" : "标记已处理"
                        }}
                      </button>
                      <button
                        class="text-button text-button-del"
                        type="button"
                        @click="
                          openDeleteDialog(
                            'records',
                            record.id,
                            `球化记录 #${record.id}`
                          )
                        "
                      >
                        删除
                      </button>
                    </template>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </template>

        <!-- Tab2 检测标准 -->
        <template v-else-if="activeTab === 'standards'">
          <div
            v-if="standardItems.length === 0"
            class="empty-state"
          >
            暂无标准
          </div>

          <div
            v-else
            class="table-scroll"
          >
            <table>
              <thead>
                <tr>
                  <th>ID</th>
                  <th>球化时长</th>
                  <th>上下限</th>
                  <th>称重标准</th>
                  <th>创建时间</th>
                  <th>创建人</th>
                  <th>备注</th>
                  <th>状态</th>
                  <th>操作</th>
                </tr>
              </thead>

              <tbody>
                <tr
                  v-for="standard in standardItems"
                  :key="standard.id"
                  :class="{ 'row-deleted': standard.deleted_at !== null }"
                >
                  <td>{{ standard.id }}</td>
                  <td>{{ standard.standard_spheroidization_time }}s</td>
                  <td>{{ rangeText(standard) }}</td>
                  <td>{{ standard.weighing_standard }}</td>
                  <td>{{ display(standard.created_at) }}</td>
                  <td>{{ standard.created_by }}</td>
                  <td>{{ display(standard.remark) }}</td>
                  <td>
                    <span
                      v-if="standard.deleted_at"
                      class="deleted-tag"
                    >
                      已删除
                    </span>
                    <span
                      v-else-if="standard.id === currentStandardId"
                      class="current-tag"
                    >
                      生效中
                    </span>
                    <span
                      v-else
                      class="status-pending"
                    >
                      历史
                    </span>
                    <div
                      v-if="standard.deleted_at"
                      class="cell-meta"
                    >
                      {{ deleteMeta(standard) }}
                    </div>
                  </td>
                  <td class="action-cell">
                    <template v-if="standard.deleted_at">
                      <button
                        class="text-button"
                        type="button"
                        @click="restore('standards', standard.id)"
                      >
                        恢复
                      </button>
                    </template>

                    <template v-else>
                      <button
                        class="text-button text-button-del"
                        type="button"
                        :disabled="standard.id === currentStandardId"
                        :title="
                          standard.id === currentStandardId
                            ? '当前生效标准不能作废，请先切换'
                            : ''
                        "
                        @click="
                          openDeleteDialog(
                            'standards',
                            standard.id,
                            `检测标准 #${standard.id}`
                          )
                        "
                      >
                        删除
                      </button>
                    </template>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </template>

        <!-- Tab3 标准切换记录 -->
        <template v-else-if="activeTab === 'switches'">
          <div
            v-if="switchLogs.length === 0"
            class="empty-state"
          >
            暂无切换记录
          </div>

          <div
            v-else
            class="table-scroll"
          >
            <table>
              <thead>
                <tr>
                  <th>切换时间</th>
                  <th>原标准</th>
                  <th>新标准</th>
                  <th>操作人</th>
                  <th>原因</th>
                  <th>状态</th>
                  <th>操作</th>
                </tr>
              </thead>

              <tbody>
                <tr
                  v-for="log in switchLogs"
                  :key="log.id"
                  :class="{ 'row-deleted': log.deleted_at !== null }"
                >
                  <td>{{ log.switched_at }}</td>
                  <td>
                    {{
                      standardText(
                        log.from_standard_record_id,
                        log.from_value
                      )
                    }}
                  </td>
                  <td>
                    {{ standardText(log.to_standard_record_id, log.to_value) }}
                  </td>
                  <td>{{ log.operated_by }}</td>
                  <td>{{ display(log.reason) }}</td>
                  <td>
                    <span
                      v-if="log.deleted_at"
                      class="deleted-tag"
                    >
                      已删除
                    </span>
                    <span
                      v-else
                      class="status-normal"
                    >
                      正常
                    </span>
                    <div
                      v-if="log.deleted_at"
                      class="cell-meta"
                    >
                      {{ deleteMeta(log) }}
                    </div>
                  </td>
                  <td class="action-cell">
                    <template v-if="log.deleted_at">
                      <button
                        class="text-button"
                        type="button"
                        @click="restore('switches', log.id)"
                      >
                        恢复
                      </button>
                    </template>

                    <template v-else>
                      <button
                        class="text-button text-button-del"
                        type="button"
                        @click="
                          openDeleteDialog(
                            'switches',
                            log.id,
                            `切换记录 #${log.id}`
                          )
                        "
                      >
                        删除
                      </button>
                    </template>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </template>

        <!-- Tab4 球化复核记录 -->
        <template v-else-if="activeTab === 'reviews'">
          <div
            v-if="reviews.length === 0"
            class="empty-state"
          >
            暂无复核记录
          </div>

          <div
            v-else
            class="table-scroll"
          >
            <table>
              <thead>
                <tr>
                  <th>记录ID</th>
                  <th>复核结果</th>
                  <th>复核人</th>
                  <th>复核时间</th>
                  <th>备注</th>
                  <th>状态</th>
                  <th>操作</th>
                </tr>
              </thead>

              <tbody>
                <tr
                  v-for="review in reviews"
                  :key="review.id"
                  :class="{ 'row-deleted': review.deleted_at !== null }"
                >
                  <td>{{ review.spheroidization_record_id }}</td>
                  <td>
                    <span
                      :class="
                        review.review_result === '异常'
                          ? 'status-abnormal'
                          : 'status-normal'
                      "
                    >
                      {{ review.review_result }}
                    </span>
                  </td>
                  <td>{{ review.reviewer }}</td>
                  <td>{{ display(review.reviewed_at) }}</td>
                  <td>{{ display(review.review_remark) }}</td>
                  <td>
                    <span
                      v-if="review.deleted_at"
                      class="deleted-tag"
                    >
                      已删除
                    </span>
                    <span
                      v-else
                      class="status-normal"
                    >
                      正常
                    </span>
                    <div
                      v-if="review.deleted_at"
                      class="cell-meta"
                    >
                      {{ deleteMeta(review) }}
                    </div>
                  </td>
                  <td class="action-cell">
                    <template v-if="review.deleted_at">
                      <button
                        class="text-button"
                        type="button"
                        @click="restore('reviews', review.id)"
                      >
                        恢复
                      </button>
                    </template>

                    <template v-else>
                      <button
                        class="text-button text-button-del"
                        type="button"
                        @click="
                          openDeleteDialog(
                            'reviews',
                            review.id,
                            `复核记录 #${review.id}`
                          )
                        "
                      >
                        删除
                      </button>
                    </template>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </template>

        <div
          v-if="activeState.total > 0"
          class="pagination"
        >
          <button
            class="secondary-button"
            type="button"
            :disabled="activeState.page <= 1"
            @click="changePage(activeState.page - 1)"
          >
            上一页
          </button>

          <span>
            第 {{ activeState.page }} / {{ totalPages(activeState) }} 页，共
            {{ activeState.total }} 条
          </span>

          <button
            class="secondary-button"
            type="button"
            :disabled="activeState.page >= totalPages(activeState)"
            @click="changePage(activeState.page + 1)"
          >
            下一页
          </button>
        </div>
      </section>

      <!-- 删除弹窗（原因必填，trim 后为空禁用确定） -->
      <div
        v-if="deleteTarget"
        class="dialog-overlay"
        @click.self="deleteTarget = null"
      >
        <div class="dialog">
          <h3>
            删除 — {{ deleteTarget.label }}
          </h3>

          <p class="dialog-hint">
            软删除：数据不会物理清除，之后可以在「显示已删除」里恢复。
          </p>

          <label class="dialog-field">
            <span>原因</span>
            <input
              v-model="deleteReason"
              placeholder="必填"
            />
          </label>

          <div class="dialog-actions">
            <button
              class="secondary-button"
              type="button"
              @click="deleteTarget = null"
            >
              取消
            </button>

            <button
              class="primary-button"
              :disabled="deleteBusy || !canConfirmDelete"
              type="button"
              @click="submitDelete"
            >
              {{ deleteBusy ? "删除中..." : "确认删除" }}
            </button>
          </div>
        </div>
      </div>

      <!-- 处理状态弹窗（球化记录 tab） -->
      <div
        v-if="processedTarget"
        class="dialog-overlay"
        @click.self="processedTarget = null"
      >
        <div class="dialog">
          <h3>
            {{
              processedTarget.processed ? "撤销处理" : "标记已处理"
            }}
            — 记录 #{{ processedTarget.id }}
          </h3>

          <p class="dialog-hint">
            {{
              processedTarget.processed
                ? "撤销后处理人 / 处理时间将被清空。"
                : "处理人取当前登录账号，不可修改。"
            }}
          </p>

          <label class="dialog-field">
            <span>原因</span>
            <input
              v-model="processedReason"
              placeholder="必填"
            />
          </label>

          <div class="dialog-actions">
            <button
              class="secondary-button"
              type="button"
              @click="processedTarget = null"
            >
              取消
            </button>

            <button
              class="primary-button"
              :disabled="processedBusy || !canConfirmProcessed"
              type="button"
              @click="submitProcessed"
            >
              {{ processedBusy ? "提交中..." : "确认" }}
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* 880px 内容中轴；配色全部沿用 style.css 既有 token，不新增色值 */
.admin-page {
  min-height: 100%;
  padding: 12px;
  background: #f0f2f5;
}

.page-shell {
  max-width: 880px;
  margin: 0 auto;
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

.overline {
  display: block;
  margin-bottom: 4px;
  color: #888;
  font-size: 11px;
  letter-spacing: 2px;
  text-transform: uppercase;
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

.tab-bar {
  display: flex;
  margin-bottom: 10px;
  background: #fff;
  border: 1px solid #d9d9d9;
}

.tab-item {
  padding: 10px 18px;
  color: #666;
  font-size: 13px;
  background: transparent;
  border: 0;
  border-bottom: 1px solid transparent;
  cursor: pointer;
}

.tab-item.active {
  color: #003399;
  font-weight: 700;
  border-bottom-color: #d48806;
}

.table-panel {
  min-height: 220px;
  padding: 10px 16px 16px;
}

.tab-toolbar {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 16px;
  margin-bottom: 8px;
  color: #666;
  font-size: 12px;
}

.tab-count {
  color: #888;
  font-size: 11px;
  letter-spacing: 1px;
}

.deleted-switch {
  display: flex;
  align-items: center;
  gap: 6px;
  cursor: pointer;
}

.deleted-switch input {
  width: 15px;
  height: 15px;
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

/* 已删除行：整行降低不透明度 */
tbody tr.row-deleted {
  opacity: 0.55;
}

.cell-meta {
  margin-top: 4px;
  color: #888;
  font-size: 11px;
}

.deleted-tag {
  display: inline-block;
  padding: 1px 7px;
  color: #d48806;
  font-size: 11px;
  letter-spacing: 1px;
  background: #fff7e6;
  border: 1px solid #ffd591;
  border-radius: 2px;
}

.current-tag {
  display: inline-block;
  padding: 1px 7px;
  color: #16803c;
  font-size: 11px;
  letter-spacing: 1px;
  background: #f6ffed;
  border: 1px solid #b7eb8f;
  border-radius: 2px;
}

.action-cell {
  white-space: nowrap;
}

.action-cell .text-button {
  margin-right: 10px;
}

.text-button-del {
  color: #c62828;
}

.text-button-del:hover {
  color: #c62828;
}

.text-button:disabled {
  color: #888;
  cursor: not-allowed;
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

@media (max-width: 700px) {
  .page-heading {
    align-items: flex-start;
    flex-direction: column;
  }
}
</style>
