<script setup lang="ts">
import { onMounted, ref } from "vue"

import {
  getCurrentStandard,
  getStandardHistory,
  createStandard,
} from "../api"

const currentStandard = ref<any>(null)
const standards = ref<any[]>([])
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

  <div class="page">

    <!-- 页面标题 -->

    <div class="page-header">

      <div>
        <h1>检测标准</h1>

        <p>
          管理当前检测标准和历史标准
        </p>
      </div>

      <button @click="loadData">
        刷新
      </button>

    </div>


    <!-- 当前标准 -->

    <section class="card">

      <h2>当前生效标准</h2>

      <div v-if="loading">
        正在加载...
      </div>

      <div
        v-else-if="!currentStandard"
        class="empty"
      >
        暂无检测标准
      </div>

      <div
        v-else
        class="current-standard"
      >

        <div class="standard-item">

          <span>
            球化时间标准
          </span>

          <strong>
            {{ currentStandard.standard_spheroidization_time }}
          </strong>

        </div>


        <div class="standard-item">

          <span>
            入料长度标准
          </span>

          <strong>
            {{ currentStandard.standard_entry_length }}
          </strong>

        </div>


        <div class="standard-item">

          <span>
            称重标准
          </span>

          <strong>
            {{ currentStandard.weighing_standard }}
          </strong>

        </div>


        <div class="standard-item">

          <span>
            创建时间
          </span>

          <strong>
            {{ currentStandard.created_at }}
          </strong>

        </div>


        <div class="standard-item">

          <span>
            创建人
          </span>

          <strong>
            {{ currentStandard.created_by }}
          </strong>

        </div>


        <div class="standard-item">

          <span>
            备注
          </span>

          <strong>
            {{ currentStandard.remark || "无" }}
          </strong>

        </div>

      </div>

    </section>


    <!-- 标准历史 -->

    <section class="card">

      <h2>标准记录</h2>

      <table>

        <thead>

          <tr>

            <th>ID</th>

            <th>
              球化时间
            </th>

            <th>
              入料长度
            </th>

            <th>
              称重标准
            </th>

            <th>
              创建时间
            </th>

            <th>
              创建人
            </th>

            <th>
              备注
            </th>

          </tr>

        </thead>


        <tbody>

          <tr
            v-for="standard in standards"
            :key="standard.id"
          >

            <td>
              {{ standard.id }}
            </td>

            <td>
              {{ standard.standard_spheroidization_time }}
            </td>

            <td>
              {{ standard.standard_entry_length }}
            </td>

            <td>
              {{ standard.weighing_standard }}
            </td>

            <td>
              {{ standard.created_at }}
            </td>

            <td>
              {{ standard.created_by }}
            </td>

            <td>
              {{ standard.remark || "无" }}
            </td>

          </tr>

        </tbody>

      </table>

    </section>


    <!-- 新增标准 -->

    <section class="card">

      <h2>新增检测标准</h2>

      <p class="description">
        新增标准后立即成为当前生效标准。
      </p>


      <div class="form-grid">

        <label>

          <span>
            球化时间标准
          </span>

          <input
            v-model.number="
              standardSpheroidizationTime
            "
            type="number"
          />

        </label>


        <label>

          <span>
            入料长度标准
          </span>

          <input
            v-model.number="
              standardEntryLength
            "
            type="number"
          />

        </label>


        <label>

          <span>
            称重标准
          </span>

          <input
            v-model.number="
              weighingStandard
            "
            type="number"
          />

        </label>


        <label>

          <span>
            创建人
          </span>

          <input
            v-model="createdBy"
            placeholder="请输入创建人"
          />

        </label>


        <label class="remark">

          <span>
            备注
          </span>

          <textarea
            v-model="remark"
            placeholder="请输入标准调整原因或说明"
          ></textarea>

        </label>

      </div>


      <button @click="submitCreate">
        创建标准
      </button>

    </section>

  </div>

</template>


<style scoped>

.page {
  max-width: 1200px;
  margin: 0 auto;
}


/* 页面标题 */

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


/* 卡片 */

.card {
  background: white;
  border: 1px solid #ddd;
  padding: 24px;
  margin-bottom: 20px;
}

.card h2 {
  margin-bottom: 20px;
}


/* 当前标准 */

.current-standard {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 16px;
}

.standard-item {
  display: flex;
  justify-content: space-between;
  padding: 16px;
  background: #f7f7f7;
}

.standard-item span {
  color: #666;
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
}


/* 表单 */

.description {
  margin-bottom: 20px;
  color: #666;
}

.form-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 18px;
  margin-bottom: 20px;
}

.form-grid label {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.form-grid input {
  width: 220px;
  padding: 9px 12px;
  border: 1px solid #ccc;
  border-radius: 4px;
}

.remark {
  grid-column: span 2;
  align-items: flex-start !important;
}

textarea {
  width: 220px;
  height: 90px;
  padding: 9px 12px;
  border: 1px solid #ccc;
  border-radius: 4px;
  resize: vertical;
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


/* 空状态 */

.empty {
  padding: 30px;
  text-align: center;
  color: #888;
}

</style>