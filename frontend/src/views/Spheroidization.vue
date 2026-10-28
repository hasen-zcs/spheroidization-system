<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from "vue"
import { useRoute, useRouter } from "vue-router"

import {
  createSpheroidization,
  querySpheroidization,
} from "../api"
import type { SpheroidizationRecord } from "../api"

const props = withDefaults(
  defineProps<{
    abnormalOnly?: boolean
  }>(),
  {
    abnormalOnly: false,
  }
)

const route = useRoute()
const router = useRouter()

const records = ref<SpheroidizationRecord[]>([])
const loading = ref(true)
const showCreateForm = ref(false)
const errorMessage = ref("")
const page = ref(1)
const pageSize = 20
const totalRecords = ref(0)

const resultFilter = ref("all")
const processFilter = ref("all")

const detectionTime = ref("2026-09-06 18:00:00")
const spheroidizationStartTime = ref(
  "2026-09-06 18:00:10"
)
const spheroidizationEndTime = ref(
  "2026-09-06 18:01:15"
)
const actualSpheroidizationTime = ref(65)
const spheroidizationAbnormal = ref(false)
const temperature = ref(1520)
const temperatureTime = ref("2026-09-06 18:00:20")
const wireEntryStartTime = ref("2026-09-06 18:00:30")
const wireEntryEndTime = ref("2026-09-06 18:01:40")
const wireEntryTotalDuration = ref(70)
const spheroidizationWeight = ref(1600)
const imageInput = ref<HTMLInputElement | null>(null)
const spheroidizationImageData = ref<string | null>(null)
const spheroidizationImagePreview = ref("")
const spheroidizationImageName = ref("")
const imageError = ref("")

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
    // 新增表单打开时不刷新，避免覆盖用户正在填写的内容
    if (showCreateForm.value) {
      return
    }
    void loadRecords(true)
  }, POLL_INTERVAL_MS)
  // 从后台切回页面时立即刷新一次（后台期间可能漏了数据）
  visibilityHandler = () => {
    if (
      document.visibilityState === "visible" &&
      !showCreateForm.value
    ) {
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

  // 行内的“查看详情”链接自己会跳转，这里不重复处理
  if (target?.closest("a")) {
    return
  }

  router.push(`/spheroidization/${record.id}`)
}

function readFileAsDataUrl(file: File) {
  return new Promise<string>((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(String(reader.result ?? ""))
    reader.onerror = () => reject(new Error("读取图片失败"))
    reader.readAsDataURL(file)
  })
}

async function selectImageFile(file: File) {
  clearSelectedImage()

  try {
    const bytes = new Uint8Array(await file.arrayBuffer())
    const jpegSignature = [0xff, 0xd8, 0xff]

    const isJpeg =
      bytes.length >= jpegSignature.length &&
      jpegSignature.every((value, index) => bytes[index] === value)

    if (!isJpeg) {
      throw new Error("请选择有效的 JPG 图片")
    }

    const dataUrl = await readFileAsDataUrl(file)
    const match = dataUrl.match(/^data:[^,]+;base64,(.+)$/)
    if (!match) {
      throw new Error("JPG 图片编码失败")
    }

    spheroidizationImageData.value = match[1]
    spheroidizationImagePreview.value = dataUrl
    spheroidizationImageName.value = file.name
  } catch (error) {
    clearSelectedImage()
    imageError.value =
      error instanceof Error ? error.message : "图片选择失败"
  }
}

async function handleImageSelect(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (file) {
    await selectImageFile(file)
  }
}

async function openImagePicker() {
  const picker = (
    window as Window & {
      showOpenFilePicker?: (options?: {
        multiple?: boolean
        types?: Array<{
          description?: string
          accept: Record<string, string[]>
        }>
      }) => Promise<Array<{ getFile: () => Promise<File> }>>
    }
  ).showOpenFilePicker

  if (!picker) {
    imageInput.value?.click()
    return
  }

  try {
    const [handle] = await picker({
      multiple: false,
      types: [
        {
          description: "JPG 图片",
          accept: { "image/jpeg": [".jpg", ".jpeg"] },
        },
      ],
    })
    await selectImageFile(await handle.getFile())
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      return
    }
    imageError.value =
      error instanceof Error ? error.message : "打开文件选择器失败"
  }
}

function clearSelectedImage() {
  spheroidizationImageData.value = null
  spheroidizationImagePreview.value = ""
  spheroidizationImageName.value = ""
  imageError.value = ""
  if (imageInput.value) {
    imageInput.value.value = ""
  }
}

async function submitCreate() {
  if (imageError.value) {
    alert(imageError.value)
    return
  }

  const result = await createSpheroidization({
    detection_time: detectionTime.value,
    spheroidization_start_time:
      spheroidizationStartTime.value,
    spheroidization_end_time:
      spheroidizationEndTime.value,
    actual_spheroidization_time:
      actualSpheroidizationTime.value,
    spheroidization_abnormal:
      spheroidizationAbnormal.value,
    spheroidization_temperature: temperature.value,
    spheroidization_temperature_time: temperatureTime.value,
    spheroidization_wire_entry_start_time: wireEntryStartTime.value,
    spheroidization_wire_entry_end_time: wireEntryEndTime.value,
    spheroidization_wire_entry_total_duration:
      wireEntryTotalDuration.value,
    spheroidization_weight: spheroidizationWeight.value,
    spheroidization_image: spheroidizationImageData.value,
  })

  if (result.code === 200) {
    clearSelectedImage()
    page.value = 1
    showCreateForm.value = false
    await loadRecords()
  } else {
    alert(result.message || "新增记录失败")
  }
}

const totalPages = computed(() =>
  Math.max(1, Math.ceil(totalRecords.value / pageSize))
)

function applyFilters() {
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

function openCreateFormIfRequested() {
  if (route.query.create === "1") {
    showCreateForm.value = true
  }
}

watch(
  () => props.abnormalOnly,
  (abnormalOnly) => {
    resultFilter.value = abnormalOnly
      ? "abnormal"
      : "all"
    processFilter.value = "all"
    page.value = 1
    loadRecords()
  }
)

watch(
  () => route.query.create,
  openCreateFormIfRequested
)

onMounted(() => {
  resultFilter.value = props.abnormalOnly
    ? "abnormal"
    : "all"
  page.value = 1

  openCreateFormIfRequested()
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
          class="primary-button"
          type="button"
          @click="showCreateForm = !showCreateForm"
        >
          {{
            showCreateForm
              ? "关闭新增"
              : "新增记录"
          }}
        </button>

        <button
          class="secondary-button"
          type="button"
          @click="loadRecords()"
        >
          刷新
        </button>
      </div>
    </div>

    <section
      v-if="showCreateForm"
      class="panel create-form"
    >
      <div class="section-title">
        <h2>新增球化记录</h2>
        <span>新记录会保存当前生效的检测标准快照</span>
      </div>

      <form @submit.prevent="submitCreate">
        <div class="form-grid">
          <label>
            <span>检测时间</span>
            <input v-model="detectionTime" />
          </label>

          <label>
            <span>球化开始时间</span>
            <input
              v-model="spheroidizationStartTime"
            />
          </label>

          <label>
            <span>球化结束时间</span>
            <input
              v-model="spheroidizationEndTime"
            />
          </label>

          <label>
            <span>实际球化时间</span>
            <input
              v-model.number="actualSpheroidizationTime"
              min="0"
              step="0.1"
              type="number"
            />
          </label>

          <label>
            <span>球化温度</span>
            <input
              v-model.number="temperature"
              step="0.1"
              type="number"
            />
          </label>

          <label>
            <span>测温时间</span>
            <input v-model="temperatureTime" />
          </label>

          <label>
            <span>进线开始时间</span>
            <input v-model="wireEntryStartTime" />
          </label>

          <label>
            <span>进线结束时间</span>
            <input v-model="wireEntryEndTime" />
          </label>

          <label>
            <span>进线总时长</span>
            <input
              v-model.number="wireEntryTotalDuration"
              min="0"
              step="0.1"
              type="number"
            />
          </label>

          <label>
            <span>球化重量</span>
            <input
              v-model.number="spheroidizationWeight"
              min="0"
              step="0.1"
              type="number"
            />
          </label>

          <label class="checkbox-field">
            <span>机器判定异常</span>
            <input
              v-model="spheroidizationAbnormal"
              type="checkbox"
            />
          </label>

          <div class="image-field">
            <label for="spheroidization-image">球化图片（JPG）</label>
            <div class="image-picker">
              <input
                id="spheroidization-image"
                ref="imageInput"
                accept=".jpg,.jpeg,image/jpeg"
                type="file"
                @change="handleImageSelect"
              />

              <button
                class="secondary-button"
                type="button"
                @click="openImagePicker"
              >
                选择 JPG 文件
              </button>

              <span
                v-if="spheroidizationImageName"
                class="image-name"
              >
                {{ spheroidizationImageName }}
              </span>
              <span
                v-else
                class="image-hint"
              >
                未选择图片
              </span>

              <button
                v-if="spheroidizationImagePreview"
                class="secondary-button"
                type="button"
                @click="clearSelectedImage"
              >
                清除图片
              </button>
            </div>

            <span
              v-if="imageError"
              class="field-error"
            >
              {{ imageError }}
            </span>

            <img
              v-if="spheroidizationImagePreview"
              class="image-preview"
              :src="spheroidizationImagePreview"
              alt="球化图片预览"
            />
          </div>
        </div>

        <button
          class="primary-button"
          type="submit"
        >
          提交记录
        </button>
      </form>
    </section>

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
              <th>球化开始时间</th>
              <th>球化结束时间</th>
              <th>进线开始时间</th>
              <th>进线结束时间</th>
              <th>标准/实际球化时长</th>
              <th>实际进线时间</th>
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
              <td>{{ record.spheroidization_weight }}</td>
              <td>{{ record.spheroidization_temperature }}</td>
              <td>
                {{ record.spheroidization_start_time }}
              </td>
              <td>
                {{ record.spheroidization_end_time }}
              </td>
              <td>
                {{ record.spheroidization_wire_entry_start_time }}
              </td>
              <td>
                {{ record.spheroidization_wire_entry_end_time }}
              </td>
              <td>
                {{
                  record.standard_spheroidization_time
                }}
                /
                {{
                  record.actual_spheroidization_time ??
                  "--"
                }}
              </td>
              <td>
                {{ record.spheroidization_wire_entry_total_duration }}
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
              <td>
                <router-link
                  class="table-link"
                  :to="`/spheroidization/${record.id}`"
                >
                  查看详情
                </router-link>
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

.create-form {
  margin-bottom: 10px;
  padding: 14px 16px;
}

.section-title {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 14px;
}

.section-title h2 {
  color: #1a2a3a;
  font-size: 15px;
}

.section-title span {
  color: #888;
  font-size: 12px;
}

.form-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(260px, 1fr));
  gap: 12px 24px;
  margin-bottom: 14px;
}

.form-grid label {
  display: grid;
  grid-template-columns: 120px minmax(0, 1fr);
  align-items: center;
  gap: 10px;
  color: #555;
  font-size: 12px;
}

.form-grid input,
.form-grid select {
  width: 100%;
  min-height: 32px;
  padding: 5px 9px;
  color: #1a2a3a;
  background: #fff;
  border: 1px solid #d9d9d9;
  border-radius: 2px;
  outline: none;
}

.form-grid input:focus,
.form-grid select:focus {
  border-color: #1890ff;
  box-shadow: 0 0 0 2px rgba(24, 144, 255, 0.12);
}

.checkbox-field {
  grid-template-columns: 120px 20px !important;
}

.checkbox-field input {
  width: 16px;
  min-height: 16px;
}

.image-field {
  display: grid;
  grid-template-columns: 120px minmax(0, 1fr);
  grid-column: 1 / -1;
  align-items: start;
  gap: 8px 10px;
  color: #555;
  font-size: 12px;
}

.image-picker {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px 12px;
}

.image-picker input[type="file"] {
  display: none;
}

.image-name,
.image-hint {
  color: #777;
}

.image-preview {
  grid-column: 2;
  display: block;
  width: min(360px, 100%);
  max-height: 220px;
  object-fit: contain;
  border: 1px solid #d9d9d9;
  background: #fafafa;
}

.field-error {
  grid-column: 2;
  color: #c62828;
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
  min-width: 1900px;
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
  color: #1890ff;
  text-decoration: none;
}

.table-link:hover {
  text-decoration: underline;
}

@media (max-width: 900px) {
  .form-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 600px) {
  .page-heading,
  .section-title {
    align-items: flex-start;
    flex-direction: column;
  }

  .form-grid label {
    grid-template-columns: 1fr;
  }

  .checkbox-field {
    grid-template-columns: 1fr 20px !important;
  }

  .image-field {
    grid-template-columns: 1fr;
  }

  .image-preview,
  .field-error {
    grid-column: 1;
  }

  .search-button {
    margin-left: 0;
  }
}
</style>
