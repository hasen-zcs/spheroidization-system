<script setup lang="ts">
import { computed, onMounted, ref } from "vue"

import { downloadReportCsv, getReportSummary } from "../api"
import type { ReportSummary } from "../api"
import { ABNORMAL_TYPE_LABELS } from "../constants"

function today(): string {
  const d = new Date()
  const pad = (n: number) => String(n).padStart(2, "0")
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
}

// 默认区间：今天 ~ 今天
const start = ref(today())
const end = ref(today())
// 类型筛选只作用于 CSV 导出（后端 summary 不支持 type 参数）
const typeFilter = ref<number | null>(null)
const loading = ref(true)
const exporting = ref(false)
const errorMessage = ref("")
const summary = ref<ReportSummary | null>(null)

const typeOptions: Array<{ value: number | null; label: string }> = [
  { value: null, label: "全部类型" },
  ...Object.entries(ABNORMAL_TYPE_LABELS).map(([value, label]) => ({
    value: Number(value),
    label,
  })),
]

function validateRange(): boolean {
  if (!start.value || !end.value) {
    errorMessage.value = "请选择开始日期和结束日期"
    return false
  }
  if (start.value > end.value) {
    errorMessage.value = "开始日期不能晚于结束日期"
    return false
  }
  return true
}

async function load() {
  errorMessage.value = ""
  if (!validateRange()) {
    return
  }
  loading.value = true
  try {
    const result = await getReportSummary(start.value, end.value)
    if (result.code !== 200) {
      errorMessage.value = result.message || "查询失败"
      summary.value = null
      return
    }
    summary.value = result.data ?? null
  } finally {
    loading.value = false
  }
}

async function exportCsv() {
  errorMessage.value = ""
  if (!validateRange()) {
    return
  }
  exporting.value = true
  try {
    await downloadReportCsv({
      start: start.value,
      end: end.value,
      type: typeFilter.value,
    })
  } catch (error) {
    errorMessage.value =
      error instanceof Error ? error.message : "导出失败"
  } finally {
    exporting.value = false
  }
}

// 比率（0-1）显示成百分比
function percent(rate: number): string {
  return `${(rate * 100).toFixed(1)}%`
}

// 空值（时长无样本等）统一显示 —
function displayNumber(value: number | null | undefined): string {
  return value === null || value === undefined ? "—" : String(value)
}

const typeDistribution = computed(() => {
  if (!summary.value) {
    return []
  }
  const entries = Object.entries(summary.value.by_type).map(
    ([value, count]) => {
      const type = Number(value)
      return {
        type,
        label: ABNORMAL_TYPE_LABELS[type] ?? `未知类型(${type})`,
        count,
      }
    }
  )
  const max = entries.reduce((acc, item) => Math.max(acc, item.count), 0)
  return entries.map((item) => ({
    ...item,
    // 纯 CSS 条形：按区间内最大类型数量缩放
    barWidth:
      max > 0 ? `${((item.count / max) * 100).toFixed(1)}%` : "0%",
  }))
})

const dayMaxTotal = computed(() => {
  return summary.value?.by_day.reduce(
    (acc, row) => Math.max(acc, row.total),
    0
  ) ?? 0
})

onMounted(() => {
  void load()
})
</script>

<template>
  <div class="reports">
    <div class="page-header">
      <div>
        <h1>报表</h1>
        <p>球化检测区间统计与 CSV 导出</p>
      </div>
    </div>

    <section class="panel filter-panel">
      <label class="filter-item">
        开始日期
        <input
          v-model="start"
          type="date"
        />
      </label>

      <label class="filter-item">
        结束日期
        <input
          v-model="end"
          type="date"
        />
      </label>

      <label class="filter-item">
        导出类型
        <select v-model="typeFilter">
          <option
            v-for="option in typeOptions"
            :key="String(option.value)"
            :value="option.value"
          >
            {{ option.label }}
          </option>
        </select>
      </label>

      <span class="filter-hint">
        类型筛选只影响导出内容，统计卡按整个日期区间计算
      </span>

      <div class="filter-actions">
        <button
          class="primary-button"
          type="button"
          :disabled="loading"
          @click="load()"
        >
          {{ loading ? "查询中..." : "查询" }}
        </button>

        <button
          class="secondary-button"
          type="button"
          :disabled="exporting"
          @click="exportCsv()"
        >
          {{ exporting ? "导出中..." : "导出 CSV" }}
        </button>
      </div>
    </section>

    <div
      v-if="errorMessage"
      class="error-panel panel"
    >
      {{ errorMessage }}
    </div>

    <div
      v-if="loading"
      class="empty-state panel"
    >
      正在加载数据...
    </div>

    <template v-else-if="summary">
      <div class="statistics">
        <div class="stat-card">
          <span>总记录数</span>
          <strong>{{ summary.total }}</strong>
        </div>

        <div class="stat-card">
          <span>异常数</span>
          <strong class="status-abnormal">
            {{ summary.abnormal_count }}
          </strong>
        </div>

        <div class="stat-card">
          <span>未判定</span>
          <strong class="status-unprocessed">
            {{ summary.unjudged_count }}
          </strong>
        </div>

        <div class="stat-card">
          <span>异常率</span>
          <strong class="status-abnormal">
            {{ percent(summary.abnormal_rate) }}
          </strong>
        </div>

        <div class="stat-card">
          <span>平均球化时长(秒)</span>
          <strong>{{ displayNumber(summary.duration.avg) }}</strong>
        </div>

        <div class="stat-card">
          <span>中位球化时长(秒)</span>
          <strong>{{ displayNumber(summary.duration.median) }}</strong>
        </div>

        <div class="stat-card">
          <span>温度覆盖率</span>
          <strong class="status-normal">
            {{ percent(summary.temperature.coverage_rate) }}
          </strong>
        </div>
      </div>

      <section class="panel data-panel">
        <div class="section-header">
          <h2>类型分布</h2>

          <span class="section-sub">
            覆盖测温 {{ summary.temperature.covered }} /
            {{ summary.temperature.total }} 条
          </span>
        </div>

        <div class="type-list">
          <div
            v-for="item in typeDistribution"
            :key="item.type"
            class="type-row"
          >
            <span class="type-label">
              {{ item.label }}
            </span>

            <span class="type-bar-track">
              <span
                class="type-bar"
                :class="{ 'type-bar-abnormal': item.type !== 0 }"
                :style="{ width: item.barWidth }"
              />
            </span>

            <span class="type-count">
              {{ item.count }}
            </span>
          </div>
        </div>
      </section>

      <section class="panel data-panel">
        <div class="section-header">
          <h2>按天分布</h2>
        </div>

        <div
          v-if="summary.by_day.length === 0"
          class="empty-state"
        >
          该区间内暂无检测记录
        </div>

        <div
          v-else
          class="table-scroll"
        >
          <table>
            <thead>
              <tr>
                <th>日期</th>
                <th>总数</th>
                <th>异常数</th>
                <th class="col-bar">记录量</th>
              </tr>
            </thead>

            <tbody>
              <tr
                v-for="row in summary.by_day"
                :key="row.date"
              >
                <td>{{ row.date }}</td>
                <td>{{ row.total }}</td>
                <td>
                  <span
                    v-if="row.abnormal > 0"
                    class="status-abnormal"
                  >
                    {{ row.abnormal }}
                  </span>
                  <span v-else>
                    {{ row.abnormal }}
                  </span>
                </td>
                <td class="col-bar">
                  <span
                    class="type-bar-track"
                  >
                    <span
                      class="type-bar"
                      :style="{
                        width: dayMaxTotal > 0
                          ? `${(row.total / dayMaxTotal) * 100}%`
                          : '0%',
                      }"
                    />
                  </span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>
    </template>

    <div
      v-else
      class="empty-state panel"
    >
      暂无数据
    </div>
  </div>
</template>

<style scoped>
.reports {
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

.filter-panel {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 12px 16px;
  margin-bottom: 10px;
  padding: 12px 16px;
}

.filter-item {
  display: flex;
  align-items: center;
  gap: 6px;
  color: #333;
  font-size: 12px;
}

.filter-item input,
.filter-item select {
  padding: 5px 8px;
  font-size: 12px;
  color: #333;
  background: #fff;
  border: 1px solid #ccc;
  outline: none;
}

.filter-item input:focus,
.filter-item select:focus {
  border-color: #1890ff;
}

.filter-hint {
  color: #999;
  font-size: 12px;
}

.filter-actions {
  display: flex;
  gap: 8px;
  margin-left: auto;
}

.primary-button,
.secondary-button {
  padding: 7px 14px;
  font-size: 12px;
  cursor: pointer;
  border: 1px solid #ccc;
}

.primary-button {
  color: #fff;
  background: #1890ff;
  border-color: #1890ff;
}

.primary-button:hover:not(:disabled) {
  background: #40a9ff;
}

.secondary-button {
  color: #1890ff;
  background: #fff;
}

.secondary-button:hover:not(:disabled) {
  background: #e6f7ff;
}

.primary-button:disabled,
.secondary-button:disabled {
  cursor: not-allowed;
  opacity: 0.6;
}

.error-panel {
  margin-bottom: 10px;
  padding: 10px 14px;
  color: #cf1322;
  font-size: 12px;
  background: #fff1f0;
  border: 1px solid #ffa39e;
}

.empty-state {
  padding: 28px;
  color: #999;
  font-size: 12px;
  text-align: center;
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

.status-abnormal {
  color: #cf1322;
}

.status-normal {
  color: #389e0d;
}

.status-unprocessed {
  color: #d48806;
}

.data-panel {
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

.section-sub {
  color: #999;
  font-size: 12px;
}

.type-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.type-row {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 12px;
}

.type-label {
  flex: 0 0 90px;
  color: #333;
}

.type-count {
  flex: 0 0 40px;
  color: #333;
  text-align: right;
}

.type-bar-track {
  display: block;
  flex: 1;
  height: 12px;
  overflow: hidden;
  background: #f0f0f0;
}

.type-bar {
  display: block;
  height: 100%;
  background: #389e0d;
}

.type-bar-abnormal {
  background: #cf1322;
}

.table-scroll {
  overflow-x: auto;
}

table {
  width: 100%;
  min-width: 560px;
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

.col-bar {
  width: 40%;
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

  .filter-actions {
    margin-left: 0;
  }
}
</style>
