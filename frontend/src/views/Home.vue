<script setup lang="ts">
import { computed, onMounted, ref } from "vue"
import { querySpheroidization } from "../api"

const records = ref<any[]>([])
const loading = ref(true)

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

const totalCount = computed(() => {
  return records.value.length
})

const abnormalCount = computed(() => {
  return records.value.filter(
    (record) =>
      record.spheroidization_abnormal ||
      record.entry_abnormal
  ).length
})

const processedCount = computed(() => {
  return records.value.filter(
    (record) => record.processed
  ).length
})

const unprocessedCount = computed(() => {
  return records.value.filter(
    (record) => !record.processed
  ).length
})

const recentRecords = computed(() => {
  return [...records.value]
    .sort(
      (a, b) =>
        new Date(b.detection_time).getTime() -
        new Date(a.detection_time).getTime()
    )
    .slice(0, 5)
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
        <h1>球化监测系统</h1>

        <p>
          球化检测运行情况概览
        </p>
      </div>

      <button @click="loadRecords">
        刷新
      </button>

    </div>


    <!-- 加载 -->

    <div v-if="loading">
      正在加载数据...
    </div>


    <div v-else>

      <!-- 数据统计 -->

      <div class="statistics">

        <div class="stat-card">

          <span>
            总记录数
          </span>

          <strong>
            {{ totalCount }}
          </strong>

        </div>


        <div class="stat-card">

          <span>
            异常记录
          </span>

          <strong class="abnormal">
            {{ abnormalCount }}
          </strong>

        </div>


        <div class="stat-card">

          <span>
            已处理
          </span>

          <strong class="normal">
            {{ processedCount }}
          </strong>

        </div>


        <div class="stat-card">

          <span>
            未处理
          </span>

          <strong class="unprocessed">
            {{ unprocessedCount }}
          </strong>

        </div>

      </div>


      <!-- 最近记录 -->

      <section class="card">

        <div class="section-header">

          <h2>
            最近检测记录
          </h2>

          <router-link to="/spheroidization">
            查看全部
          </router-link>

        </div>


        <div
          v-if="recentRecords.length === 0"
          class="empty"
        >
          暂无检测记录
        </div>


        <table v-else>

          <thead>

            <tr>

              <th>
                ID
              </th>

              <th>
                检测时间
              </th>

              <th>
                铁水重量
              </th>

              <th>
                检测结果
              </th>

              <th>
                处理状态
              </th>

              <th>
                操作
              </th>

            </tr>

          </thead>


          <tbody>

            <tr
              v-for="record in recentRecords"
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

                <span
                  :class="
                    record.spheroidization_abnormal ||
                    record.entry_abnormal
                      ? 'abnormal'
                      : 'normal'
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
                      ? 'normal'
                      : 'unprocessed'
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
                  :to="
                    `/spheroidization/${record.id}`
                  "
                >
                  查看详情
                </router-link>

              </td>

            </tr>

          </tbody>

        </table>

      </section>


      <!-- 快捷入口 -->

      <section class="card">

        <h2>
          快捷操作
        </h2>

        <div class="quick-actions">

          <router-link
            to="/spheroidization"
            class="action"
          >
            查看球化记录
          </router-link>

          <router-link
            to="/standard"
            class="action"
          >
            管理检测标准
          </router-link>

        </div>

      </section>

    </div>

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


/* 统计 */

.statistics {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
  margin-bottom: 24px;
}

.stat-card {
  background: white;
  border: 1px solid #ddd;
  padding: 24px;
}

.stat-card span {
  display: block;
  color: #666;
  margin-bottom: 12px;
}

.stat-card strong {
  font-size: 30px;
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


/* 标题 */

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
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


/* 状态 */

.normal {
  color: #16803c;
  font-weight: 600;
}

.abnormal {
  color: #c62828;
  font-weight: 600;
}

.unprocessed {
  color: #d97706;
  font-weight: 600;
}


/* 快捷操作 */

.quick-actions {
  display: flex;
  gap: 16px;
}

.action {
  display: inline-block;
  padding: 12px 20px;
  border: 1px solid #ccc;
  text-decoration: none;
  color: #333;
}

.action:hover {
  background: #f5f5f5;
}


/* 空数据 */

.empty {
  padding: 30px;
  text-align: center;
  color: #888;
}

</style>