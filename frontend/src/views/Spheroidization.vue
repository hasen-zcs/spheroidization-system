<script setup lang="ts">
import { computed, onMounted, ref } from "vue"
import { createSpheroidization, querySpheroidization } from "../api"

const records = ref<any[]>([])
const loading = ref(true)

const showCreateForm = ref(false)

const resultFilter = ref("all")
const processFilter = ref("all")

const detectionTime = ref("2026-09-06 18:00:00")
const ironWaterWeight = ref(1500)
const spheroidizationStartTime = ref("2026-09-06 18:00:10")
const spheroidizationEndTime = ref("2026-09-06 18:01:15")
const actualSpheroidizationTime = ref(65)
const actualEntryLength = ref(125)
const machineResult = ref("正常")
const spheroidizationAbnormal = ref(false)
const entryAbnormal = ref(false)

async function loadRecords() {
  loading.value = true

  try {
    const result = await querySpheroidization()

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
    iron_water_weight: ironWaterWeight.value,
    spheroidization_start_time:
      spheroidizationStartTime.value,
    spheroidization_end_time:
      spheroidizationEndTime.value,
    actual_spheroidization_time:
      actualSpheroidizationTime.value,
    actual_entry_length:
      actualEntryLength.value,
    machine_result: machineResult.value,
    spheroidization_abnormal:
      spheroidizationAbnormal.value,
    entry_abnormal:
      entryAbnormal.value,
  })

  if (result.code === 200) {
    showCreateForm.value = false
    await loadRecords()
  }
}

const filteredRecords = computed(() => {
  return records.value.filter((record) => {
    const abnormal =
      record.spheroidization_abnormal ||
      record.entry_abnormal

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

onMounted(() => {
  loadRecords()
})
</script>

<template>
  <div class="page">

    <!-- 页面标题 -->
    <div class="page-header">

      <div>
        <h1>球化记录</h1>
        <p>查看和管理球化检测记录</p>
      </div>

      <div class="header-buttons">

        <button @click="showCreateForm = !showCreateForm">
          {{ showCreateForm ? "关闭新增" : "新增记录" }}
        </button>

        <button @click="loadRecords">
          刷新
        </button>

      </div>

    </div>


    <!-- 新增记录 -->
    <div
      v-if="showCreateForm"
      class="card create-form"
    >

      <h2>新增球化记录</h2>

      <div class="form-grid">

        <label>
          检测时间
          <input v-model="detectionTime" />
        </label>

        <label>
          铁水重量
          <input
            v-model.number="ironWaterWeight"
            type="number"
          />
        </label>

        <label>
          球化开始时间
          <input
            v-model="spheroidizationStartTime"
          />
        </label>

        <label>
          球化结束时间
          <input
            v-model="spheroidizationEndTime"
          />
        </label>

        <label>
          实际球化时间
          <input
            v-model.number="actualSpheroidizationTime"
            type="number"
          />
        </label>

        <label>
          实际入料长度
          <input
            v-model.number="actualEntryLength"
            type="number"
          />
        </label>

        <label>
          机器检测结果
          <select v-model="machineResult">
            <option value="正常">正常</option>
            <option value="异常">异常</option>
          </select>
        </label>

        <label>
          球化异常
          <input
            v-model="spheroidizationAbnormal"
            type="checkbox"
          />
        </label>

        <label>
          入料异常
          <input
            v-model="entryAbnormal"
            type="checkbox"
          />
        </label>

      </div>

      <button @click="submitCreate">
        提交记录
      </button>

    </div>


    <!-- 筛选 -->
    <div class="card filter-bar">

      <div class="filter-item">
        <span>检测结果：</span>

        <select v-model="resultFilter">
          <option value="all">
            全部
          </option>

          <option value="normal">
            正常
          </option>

          <option value="abnormal">
            异常
          </option>
        </select>
      </div>


      <div class="filter-item">
        <span>处理状态：</span>

        <select v-model="processFilter">
          <option value="all">
            全部
          </option>

          <option value="processed">
            已处理
          </option>

          <option value="unprocessed">
            未处理
          </option>
        </select>
      </div>

    </div>


    <!-- 数据表格 -->
    <div class="card">

      <div v-if="loading">
        正在加载数据...
      </div>

      <div
        v-else-if="filteredRecords.length === 0"
        class="empty"
      >
        暂无符合条件的记录
      </div>

      <table v-else>

        <thead>
          <tr>
            <th>ID</th>
            <th>检测时间</th>
            <th>铁水重量</th>
            <th>球化时间</th>
            <th>入料长度</th>
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

            <td>
              {{ record.id }}
            </td>

            <td>
              {{ record.detection_time }}
            </td>

            <td>
              {{ record.iron_water_weight }}
            </td>

            <td>
              {{ record.actual_spheroidization_time }}
            </td>

            <td>
              {{ record.actual_entry_length }}
            </td>

            <td>

              <span
                :class="
                  record.spheroidization_abnormal ||
                  record.entry_abnormal
                    ? 'status-abnormal'
                    : 'status-normal'
                "
              >
                {{
                  record.spheroidization_abnormal ||
                  record.entry_abnormal
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
                :to="`/spheroidization/${record.id}`"
              >
                查看详情
              </router-link>

            </td>

          </tr>

        </tbody>

      </table>

    </div>

  </div>
</template>


<style scoped>

.page {
  max-width: 1400px;
  margin: 0 auto;
}


/* 页面头部 */

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 24px;
}

.page-header h1 {
  margin-bottom: 8px;
}

.page-header p {
  color: #666;
}

.header-buttons {
  display: flex;
  gap: 12px;
}


/* 卡片 */

.card {
  background: white;
  border: 1px solid #ddd;
  padding: 24px;
  margin-bottom: 20px;
}


/* 按钮 */

button {
  padding: 9px 16px;
  border: 1px solid #ccc;
  background: white;
  border-radius: 4px;
  cursor: pointer;
}

button:hover {
  background: #f5f5f5;
}


/* 新增表单 */

.create-form h2 {
  margin-bottom: 20px;
}

.form-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 16px;
  margin-bottom: 20px;
}

.form-grid label {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.form-grid input,
.form-grid select {
  width: 220px;
  padding: 8px;
  border: 1px solid #ccc;
  border-radius: 4px;
}


/* 筛选 */

.filter-bar {
  display: flex;
  gap: 32px;
}

.filter-item {
  display: flex;
  align-items: center;
  gap: 8px;
}

.filter-item select {
  padding: 8px 12px;
}


/* 表格 */

table {
  width: 100%;
  border-collapse: collapse;
}

th,
td {
  padding: 14px 12px;
  border-bottom: 1px solid #eee;
  text-align: left;
}

th {
  background: #f7f7f7;
  font-weight: 600;
}

tbody tr:hover {
  background: #fafafa;
}


/* 状态 */

.status-normal {
  color: #16803c;
  font-weight: 600;
}

.status-abnormal {
  color: #c62828;
  font-weight: 600;
}

.status-unprocessed {
  color: #d97706;
  font-weight: 600;
}


/* 空数据 */

.empty {
  padding: 40px;
  text-align: center;
  color: #888;
}

</style>