<script setup lang="ts">
import { computed, onMounted, ref } from "vue"

import {
  createStandard,
  getCurrentStandard,
  getStandardHistory,
  getStandardSwitchLogs,
  switchStandard,
} from "../api"
import type {
  StandardRecord,
  StandardSwitchLog,
} from "../api"
import { can } from "../auth"

// 新增按钮按 action:create_standard 权限显示
const canCreate = computed(() => can("action:create_standard"))
// 切换标准按钮按 action:switch_standard 权限显示
const canSwitch = computed(() => can("action:switch_standard"))

const currentStandard = ref<StandardRecord | null>(null)
const standards = ref<StandardRecord[]>([])
const switchLogs = ref<StandardSwitchLog[]>([])
const loading = ref(true)

const standardSpheroidizationTime = ref(70)
const standardSpheroidizationTimeUpper = ref<number | string | null>(75)
const standardSpheroidizationTimeLower = ref<number | string | null>(65)
const weighingStandard = ref(1500)
const remark = ref("")
const errorMessage = ref("")

async function loadData() {
  loading.value = true
  errorMessage.value = ""

  try {
    const currentResult = await getCurrentStandard()

    if (currentResult.code === 200) {
      currentStandard.value = currentResult.data
    } else {
      errorMessage.value = currentResult.message || "加载当前标准失败"
      return
    }

    const [historyResult, logsResult] = await Promise.all([
      getStandardHistory(),
      getStandardSwitchLogs(),
    ])

    if (historyResult.code === 200) {
      standards.value = historyResult.data ?? []
    } else {
      errorMessage.value = historyResult.message || "加载标准历史失败"
    }

    if (logsResult.code === 200) {
      switchLogs.value = logsResult.data ?? []
    }
  } finally {
    loading.value = false
  }
}

// ====================
// 切换标准（原「应用标准」，原因必填）
// ====================

const switchTarget = ref<StandardRecord | null>(null)
const switchReason = ref("")
const switching = ref(false)

function openSwitchDialog(standard: StandardRecord) {
  if (currentStandard.value?.id === standard.id) {
    return
  }

  switchTarget.value = standard
  switchReason.value = ""
}

async function submitSwitch() {
  if (!switchTarget.value || switching.value) {
    return
  }

  const reason = switchReason.value.trim()
  if (!reason) {
    alert("请填写切换原因，原因为空不允许提交")
    return
  }

  switching.value = true
  try {
    const result = await switchStandard({
      standard_id: switchTarget.value.id,
      reason,
    })

    if (result.code === 200) {
      switchTarget.value = null
      await loadData()
    } else {
      alert(result.message || "切换标准失败")
    }
  } finally {
    switching.value = false
  }
}

// 「YYYY-MM-DD 从标准A切换到标准B，原因：xx」
function formatSwitchLog(log: StandardSwitchLog): string {
  const date = (log.switched_at ?? "").slice(0, 10)
  const from =
    log.from_standard_id === null
      ? "无"
      : `标准${log.from_standard_id}（${log.from_value ?? "?"} 秒）`
  const to = `标准${log.to_standard_id}（${log.to_value} 秒）`

  return `${date} 从${from}切换到${to}，原因：${log.reason}`
}

async function submitCreate() {
  const upper =
    standardSpheroidizationTimeUpper.value === "" ||
    standardSpheroidizationTimeUpper.value === null
      ? null
      : Number(standardSpheroidizationTimeUpper.value)
  const lower =
    standardSpheroidizationTimeLower.value === "" ||
    standardSpheroidizationTimeLower.value === null
      ? null
      : Number(standardSpheroidizationTimeLower.value)

  const result = await createStandard({
    standard_spheroidization_time:
      standardSpheroidizationTime.value,
    standard_spheroidization_time_upper:
      upper,
    standard_spheroidization_time_lower:
      lower,
    weighing_standard:
      weighingStandard.value,
    remark:
      remark.value,
  })

  if (result.code === 200) {
    remark.value = ""
    await loadData()
  } else {
    alert(result.message || "创建标准失败")
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
      <div
        v-if="errorMessage"
        class="empty-state"
      >
        {{ errorMessage }}
      </div>

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
          <span>球化时间下限</span>
          <strong>
            {{ currentStandard.standard_spheroidization_time_lower ?? "未设置" }}
          </strong>
        </div>

        <div class="standard-item">
          <span>球化时间上限</span>
          <strong>
            {{ currentStandard.standard_spheroidization_time_upper ?? "未设置" }}
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
              <th>下限</th>
              <th>上限</th>
              <th>称重标准</th>
              <th>创建时间</th>
              <th>创建人</th>
              <th>备注</th>
              <th>应用标准</th>
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
                {{ standard.standard_spheroidization_time_lower ?? "未设置" }}
              </td>
              <td>
                {{ standard.standard_spheroidization_time_upper ?? "未设置" }}
              </td>
              <td>{{ standard.weighing_standard }}</td>
              <td>{{ standard.created_at }}</td>
              <td>{{ standard.created_by }}</td>
              <td>{{ standard.remark || "无" }}</td>
              <td>
                <button
                  v-if="currentStandard?.id === standard.id"
                  class="secondary-button apply-button"
                  type="button"
                  disabled
                >
                  当前标准
                </button>
                <button
                  v-else-if="canSwitch"
                  class="primary-button apply-button"
                  type="button"
                  @click="openSwitchDialog(standard)"
                >
                  切换标准
                </button>
              </td>
            </tr>

            <tr v-if="standards.length === 0">
              <td
                class="empty-cell"
                colspan="9"
              >
                暂无标准记录
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <!-- 切换记录 -->
    <section class="panel switch-log-panel">
      <div class="section-header">
        <h2>切换记录</h2>
        <span>共 {{ switchLogs.length }} 条</span>
      </div>

      <div
        v-if="switchLogs.length === 0"
        class="empty-state"
      >
        暂无切换记录
      </div>

      <ul
        v-else
        class="switch-log-list"
      >
        <li
          v-for="log in switchLogs"
          :key="log.id"
        >
          {{ formatSwitchLog(log) }}
        </li>
      </ul>
    </section>

    <!-- 新增标准：按 action:create_standard 权限显示 -->
    <section
      v-if="canCreate"
      class="panel create-panel"
    >
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
            <span>球化时间下限</span>
            <input
              v-model.number="standardSpheroidizationTimeLower"
              min="0"
              step="0.1"
              type="number"
            />
          </label>

          <label>
            <span>球化时间上限</span>
            <input
              v-model.number="standardSpheroidizationTimeUpper"
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

    <!-- 切换标准弹窗：原因必填 -->
    <div
      v-if="switchTarget"
      class="dialog-overlay"
      @click.self="switchTarget = null"
    >
      <div class="dialog">
        <h3>
          切换标准 — 标准{{ switchTarget.id }}（{{
            switchTarget.standard_spheroidization_time
          }} 秒）
        </h3>

        <p class="dialog-hint">
          切换后只影响之后创建的球化记录，历史记录不会改变。
        </p>

        <label class="dialog-field">
          <span>切换原因（必填）</span>
          <input
            v-model="switchReason"
            placeholder="请填写切换原因"
          />
        </label>

        <div class="dialog-actions">
          <button
            class="secondary-button"
            type="button"
            @click="switchTarget = null"
          >
            取消
          </button>

          <button
            class="primary-button"
            :disabled="switching"
            type="button"
            @click="submitSwitch"
          >
            {{ switching ? "切换中..." : "确认切换" }}
          </button>
        </div>
      </div>
    </div>
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
  min-width: 1080px;
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

.apply-button {
  padding: 5px 10px;
  font-size: 12px;
  white-space: nowrap;
}

.switch-log-list {
  list-style: none;
}

.switch-log-list li {
  padding: 8px 10px;
  font-size: 12px;
  color: #333;
  background: #fafafa;
  border-bottom: 1px solid #eee;
}

.switch-log-list li:last-child {
  border-bottom: 0;
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
