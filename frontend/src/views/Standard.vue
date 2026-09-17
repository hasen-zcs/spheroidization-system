<script setup lang="ts">
import { onMounted, ref } from "vue"

import {
  createStandard,
  getCurrentStandard,
  getStandardHistory,
} from "../api"
import type { StandardRecord } from "../api"

const currentStandard = ref<StandardRecord | null>(null)
const standards = ref<StandardRecord[]>([])
const loading = ref(true)

const standardSpheroidizationTime = ref(70)
const standardEntryLength = ref(130)
const weighingStandard = ref(1500)
const createdBy = ref("测试用户")
const remark = ref("")

async function loadData() {
  loading.value = true

  try {
    const currentResult = await getCurrentStandard()

    if (currentResult.code === 200) {
      currentStandard.value = currentResult.data
    }

    const historyResult = await getStandardHistory()

    if (historyResult.code === 200) {
      standards.value = historyResult.data
    }
  } finally {
    loading.value = false
  }
}

async function submitCreate() {
  const result = await createStandard({
    standard_spheroidization_time:
      standardSpheroidizationTime.value,
    standard_entry_length:
      standardEntryLength.value,
    weighing_standard:
      weighingStandard.value,
    created_by:
      createdBy.value,
    remark:
      remark.value,
  })

  if (result.code === 200) {
    remark.value = ""
    await loadData()
  }
}

onMounted(() => {
  loadData()
})
</script>

<template>
  <div class="standard-page">
    <div class="page-heading">
      <div>
        <h1>检测标准</h1>
        <p>管理当前检测标准和历史版本</p>
      </div>

      <button
        class="secondary-button"
        type="button"
        @click="loadData"
      >
        刷新
      </button>
    </div>

    <section class="panel current-panel">
      <div class="section-header">
        <h2>当前生效标准</h2>
        <span>最新创建的标准立即生效</span>
      </div>

      <div
        v-if="loading"
        class="empty-state"
      >
        正在加载...
      </div>

      <div
        v-else-if="!currentStandard"
        class="empty-state"
      >
        暂无检测标准
      </div>

      <div
        v-else
        class="standard-grid"
      >
        <div class="standard-item">
          <span>球化时间标准</span>
          <strong>
            {{ currentStandard.standard_spheroidization_time }}
          </strong>
        </div>

        <div class="standard-item">
          <span>入料长度标准</span>
          <strong>
            {{ currentStandard.standard_entry_length }}
          </strong>
        </div>

        <div class="standard-item">
          <span>称重标准</span>
          <strong>
            {{ currentStandard.weighing_standard }}
          </strong>
        </div>

        <div class="standard-item">
          <span>创建时间</span>
          <strong>{{ currentStandard.created_at }}</strong>
        </div>

        <div class="standard-item">
          <span>创建人</span>
          <strong>{{ currentStandard.created_by }}</strong>
        </div>

        <div class="standard-item">
          <span>备注</span>
          <strong>{{ currentStandard.remark || "无" }}</strong>
        </div>
      </div>
    </section>

    <section class="panel history-panel">
      <div class="section-header">
        <h2>标准记录</h2>
        <span>共 {{ standards.length }} 条</span>
      </div>

      <div class="table-scroll">
        <table>
          <thead>
            <tr>
              <th>ID</th>
              <th>球化时间</th>
              <th>入料长度</th>
              <th>称重标准</th>
              <th>创建时间</th>
              <th>创建人</th>
              <th>备注</th>
            </tr>
          </thead>

          <tbody>
            <tr
              v-for="standard in standards"
              :key="standard.id"
            >
              <td>{{ standard.id }}</td>
              <td>
                {{
                  standard.standard_spheroidization_time
                }}
              </td>
              <td>
                {{ standard.standard_entry_length }}
              </td>
              <td>{{ standard.weighing_standard }}</td>
              <td>{{ standard.created_at }}</td>
              <td>{{ standard.created_by }}</td>
              <td>{{ standard.remark || "无" }}</td>
            </tr>

            <tr v-if="standards.length === 0">
              <td
                class="empty-cell"
                colspan="7"
              >
                暂无标准记录
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <section class="panel create-panel">
      <div class="section-header">
        <h2>新增检测标准</h2>
        <span>新增后立即成为当前生效标准</span>
      </div>

      <form @submit.prevent="submitCreate">
        <div class="form-grid">
          <label>
            <span>球化时间标准</span>
            <input
              v-model.number="standardSpheroidizationTime"
              min="0"
              step="0.1"
              type="number"
            />
          </label>

          <label>
            <span>入料长度标准</span>
            <input
              v-model.number="standardEntryLength"
              min="0"
              step="0.1"
              type="number"
            />
          </label>

          <label>
            <span>称重标准</span>
            <input
              v-model.number="weighingStandard"
              min="0"
              step="0.1"
              type="number"
            />
          </label>

          <label>
            <span>创建人</span>
            <input
              v-model="createdBy"
              placeholder="请输入创建人"
            />
          </label>

          <label class="remark-field">
            <span>备注</span>
            <textarea
              v-model="remark"
              placeholder="请输入标准调整原因或说明"
            ></textarea>
          </label>
        </div>

        <button
          class="primary-button"
          type="submit"
        >
          创建标准
        </button>
      </form>
    </section>
  </div>
</template>

<style scoped>
.standard-page {
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

.current-panel,
.history-panel,
.create-panel {
  margin-bottom: 10px;
  padding: 14px 16px;
}

.section-header {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 12px;
}

.section-header h2 {
  color: #1a2a3a;
  font-size: 15px;
}

.section-header span {
  color: #888;
  font-size: 12px;
}

.standard-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px;
}

.standard-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 12px;
  background: #f7fbff;
  border: 1px solid #e6f2ff;
}

.standard-item span {
  color: #777;
  font-size: 12px;
}

.standard-item strong {
  color: #1a2a3a;
  font-size: 12px;
  text-align: right;
}

.table-scroll {
  overflow-x: auto;
}

table {
  width: 100%;
  min-width: 900px;
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

.empty-cell {
  color: #888;
  text-align: center;
}

.form-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(280px, 1fr));
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
.form-grid textarea {
  width: 100%;
  padding: 6px 9px;
  color: #1a2a3a;
  background: #fff;
  border: 1px solid #d9d9d9;
  border-radius: 2px;
  outline: none;
}

.form-grid input {
  min-height: 32px;
}

.form-grid textarea {
  min-height: 72px;
  resize: vertical;
}

.form-grid input:focus,
.form-grid textarea:focus {
  border-color: #1890ff;
  box-shadow: 0 0 0 2px rgba(24, 144, 255, 0.12);
}

.remark-field {
  grid-column: span 2;
  align-items: flex-start !important;
}

@media (max-width: 900px) {
  .standard-grid,
  .form-grid {
    grid-template-columns: 1fr;
  }

  .remark-field {
    grid-column: span 1;
  }
}

@media (max-width: 600px) {
  .page-heading,
  .section-header {
    align-items: flex-start;
    flex-direction: column;
  }

  .form-grid label {
    grid-template-columns: 1fr;
  }
}
</style>
