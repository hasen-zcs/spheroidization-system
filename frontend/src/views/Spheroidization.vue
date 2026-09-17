<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue"
import { useRoute } from "vue-router"

import {
  createSpheroidization,
  queryAbnormalSpheroidization,
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

const records = ref<SpheroidizationRecord[]>([])
const loading = ref(true)
const showCreateForm = ref(false)

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

async function loadRecords() {
  loading.value = true

  try {
    const result = props.abnormalOnly
      ? await queryAbnormalSpheroidization()
      : await querySpheroidization()

    if (result.code === 200) {
      records.value = result.data
    }
  } finally {
    loading.value = false
  }
}

async function submitCreate() {
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
  })

  if (result.code === 200) {
    showCreateForm.value = false
    await loadRecords()
  }
}

const filteredRecords = computed(() => {
  return records.value.filter((record) => {
    const abnormal = record.spheroidization_abnormal

    if (
      resultFilter.value === "abnormal" &&
      !abnormal
    ) {
      return false
    }

    if (
      resultFilter.value === "normal" &&
      abnormal
    ) {
      return false
    }

    if (
      processFilter.value === "processed" &&
      !record.processed
    ) {
      return false
    }

    if (
      processFilter.value === "unprocessed" &&
      record.processed
    ) {
      return false
    }

    return true
  })
})

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

  openCreateFormIfRequested()
  loadRecords()
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
          @click="loadRecords"
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

          <label class="checkbox-field">
            <span>机器判定异常</span>
            <input
              v-model="spheroidizationAbnormal"
              type="checkbox"
            />
          </label>
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
        @click="loadRecords"
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
        v-else-if="filteredRecords.length === 0"
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
              <th>球化开始时间</th>
              <th>球化结束时间</th>
              <th>标准/实际球化时长</th>
              <th>检测结果</th>
              <th>处理状态</th>
              <th>操作</th>
            </tr>
          </thead>

          <tbody>
            <tr
              v-for="record in filteredRecords"
              :key="record.id"
            >
              <td>{{ record.id }}</td>
              <td>{{ record.detection_time }}</td>
              <td>
                {{ record.spheroidization_start_time }}
              </td>
              <td>
                {{ record.spheroidization_end_time }}
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

.table-panel {
  min-height: 220px;
}

.table-scroll {
  overflow: auto;
}

table {
  width: 100%;
  min-width: 1050px;
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

  .search-button {
    margin-left: 0;
  }
}
</style>
