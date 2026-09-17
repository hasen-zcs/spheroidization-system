<script setup lang="ts">
import { onMounted, ref } from "vue"
import { useRoute } from "vue-router"

import {
  getSpheroidization,
  queryReviews,
  createReview,
  processSpheroidization,
} from "../api"
import type {
  ReviewRecord,
  SpheroidizationRecord,
} from "../api"

const route = useRoute()

const record = ref<SpheroidizationRecord | null>(null)
const reviews = ref<ReviewRecord[]>([])
const loading = ref(true)

const reviewResult = ref("正常")
const reviewRemark = ref("")
const reviewer = ref("测试用户")

const processedBy = ref("测试用户")

async function loadData() {
  loading.value = true

  try {
    const recordId = Number(route.params.id)

    const recordResult = await getSpheroidization(recordId)

    if (recordResult.code === 200) {
      record.value = recordResult.data
    }

    const reviewResultData = await queryReviews(recordId)

    if (reviewResultData.code === 200) {
      reviews.value = reviewResultData.data
    }
  } finally {
    loading.value = false
  }
}

async function submitReview() {
  if (!record.value) {
    return
  }

  if (!reviewRemark.value.trim()) {
    alert("请输入复核说明")
    return
  }

  const result = await createReview({
    spheroidization_record_id: record.value.id,
    review_result: reviewResult.value,
    review_remark: reviewRemark.value,
    reviewer: reviewer.value,
  })

  if (result.code === 200) {
    reviewRemark.value = ""
    await loadData()
  }
}

async function processRecord() {
  if (!record.value) {
    return
  }

  if (!processedBy.value.trim()) {
    alert("请输入处理人")
    return
  }

  const result = await processSpheroidization(
    record.value.id,
    processedBy.value,
  )

  if (result.code === 200) {
    await loadData()
  }
}

onMounted(() => {
  loadData()
})
</script>

<template>
  <div class="detail-page">

    <div v-if="loading">
      正在加载数据...
    </div>

    <div v-else-if="!record">
      记录不存在
    </div>

    <div v-else>

      <!-- 页面标题 -->

      <div class="page-header">

        <div>
          <h1>球化记录详情</h1>

          <p>
            记录 ID：{{ record.id }}
          </p>
        </div>

        <router-link to="/spheroidization">
          返回记录列表
        </router-link>

      </div>


      <!-- 基本信息 -->

      <section class="card">

        <h2>基本信息</h2>

        <div class="info-grid">

          <div class="info-item">
            <span>检测时间</span>
            <strong>
              {{ record.detection_time }}
            </strong>
          </div>

          <div class="info-item">
            <span>球化开始时间</span>
            <strong>
              {{ record.spheroidization_start_time }}
            </strong>
          </div>

          <div class="info-item">
            <span>球化结束时间</span>
            <strong>
              {{ record.spheroidization_end_time }}
            </strong>
          </div>

        </div>

      </section>


      <!-- 检测结果 -->

      <section class="card">

        <h2>机器检测结果</h2>

        <div class="result-summary">

          <div class="result-item">

            <span>机器检测结果</span>

            <strong
              :class="
                record.spheroidization_abnormal
                  ? 'abnormal'
                  : 'normal'
              "
            >
              {{
                record.spheroidization_abnormal
                  ? "异常"
                  : "正常"
              }}
            </strong>

          </div>

        </div>


        <div class="info-grid">

          <div class="info-item">
            <span>实际球化时间</span>
            <strong>
              {{
                record.actual_spheroidization_time ??
                "--"
              }}
            </strong>
          </div>

          <div class="info-item">
            <span>标准球化时间</span>
            <strong>
              {{ record.standard_spheroidization_time }}
            </strong>
          </div>

          <div class="info-item">
            <span>球化异常</span>
            <strong
              :class="
                record.spheroidization_abnormal
                  ? 'abnormal'
                  : 'normal'
              "
            >
              {{
                record.spheroidization_abnormal
                  ? "异常"
                  : "正常"
              }}
            </strong>
          </div>

        </div>

      </section>


      <!-- 人工复核 -->

      <section class="card">

        <div class="section-header">

          <h2>人工复核</h2>

          <span>
            共 {{ reviews.length }} 条
          </span>

        </div>


        <div
          v-if="reviews.length === 0"
          class="empty"
        >
          暂无人工复核记录
        </div>


        <div
          v-for="review in reviews"
          :key="review.id"
          class="review-item"
        >

          <div class="review-header">

            <strong
              :class="
                review.review_result === '异常'
                  ? 'abnormal'
                  : 'normal'
              "
            >
              {{ review.review_result }}
            </strong>

            <span>
              {{ review.reviewer }}
              ·
              {{ review.reviewed_at }}
            </span>

          </div>

          <p>
            {{ review.review_remark }}
          </p>

        </div>


        <!-- 新增复核 -->

        <div class="review-form">

          <h3>新增复核</h3>

          <div class="form-row">

            <label>
              复核结果

              <select v-model="reviewResult">

                <option value="正常">
                  正常
                </option>

                <option value="异常">
                  异常
                </option>

              </select>

            </label>


            <label>
              复核人

              <input
                v-model="reviewer"
                placeholder="请输入复核人"
              />

            </label>

          </div>


          <label class="remark-label">

            复核说明

            <textarea
              v-model="reviewRemark"
              placeholder="请输入复核说明"
            ></textarea>

          </label>


          <button @click="submitReview">
            提交复核
          </button>

        </div>

      </section>


      <!-- 处理状态 -->

      <section class="card">

        <h2>处理状态</h2>

        <div class="process-status">

          <strong
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
          </strong>

          <span v-if="record.processed">
            处理人：{{ record.processed_by }}
          </span>

          <span v-if="record.processed">
            处理时间：{{ record.processed_at }}
          </span>

        </div>


        <div
          v-if="!record.processed"
          class="process-form"
        >

          <input
            v-model="processedBy"
            placeholder="请输入处理人"
          />

          <button @click="processRecord">
            标记为已处理
          </button>

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


/* 信息 */

.info-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 16px;
}

.info-item {
  display: flex;
  justify-content: space-between;
  padding: 14px;
  background: #f7f7f7;
}

.info-item span {
  color: #666;
}


/* 检测结果 */

.result-summary {
  margin-bottom: 20px;
}

.result-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px;
  background: #f7f7f7;
}


/* 状态 */

.normal {
  color: #16803c;
}

.abnormal {
  color: #c62828;
}

.unprocessed {
  color: #d97706;
}


/* 复核 */

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.section-header > span {
  color: #888;
}

.review-item {
  padding: 16px;
  margin-bottom: 12px;
  background: #f7f7f7;
}

.review-header {
  display: flex;
  justify-content: space-between;
  margin-bottom: 10px;
}

.review-header span {
  color: #888;
}

.review-item p {
  line-height: 1.6;
}

.review-form {
  margin-top: 24px;
  padding-top: 24px;
  border-top: 1px solid #eee;
}

.review-form h3 {
  margin-bottom: 16px;
}

.form-row {
  display: flex;
  gap: 24px;
  margin-bottom: 16px;
}

.form-row label {
  display: flex;
  align-items: center;
  gap: 12px;
}

.remark-label {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-bottom: 16px;
}

input,
select,
textarea {
  padding: 9px 12px;
  border: 1px solid #ccc;
  border-radius: 4px;
}

textarea {
  width: 100%;
  max-width: 600px;
  height: 100px;
  resize: vertical;
}


/* 处理 */

.process-status {
  display: flex;
  gap: 24px;
  align-items: center;
  margin-bottom: 20px;
}

.process-form {
  display: flex;
  gap: 12px;
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

.detail-page {
  min-height: calc(100vh - 40px);
  padding: 14px;
  background: #f5f7fa;
}

.detail-page .page-header {
  margin: 0 0 10px;
  padding: 14px 16px;
  background: #fff;
  border: 1px solid #d9d9d9;
}

.detail-page .page-header h1 {
  margin-bottom: 4px;
  color: #003399;
  font-size: 18px;
}

.detail-page .page-header a {
  color: #1890ff;
  font-size: 12px;
  text-decoration: none;
}

.detail-page .card {
  max-width: 1200px;
  margin: 0 auto 10px;
  padding: 14px 16px;
  background: #fff;
  border: 1px solid #d9d9d9;
}

.detail-page .page-header + .card {
  margin-top: 0;
}

.detail-page .card h2 {
  margin-bottom: 14px;
  font-size: 15px;
}

.detail-page .info-grid {
  gap: 8px;
}

.detail-page .info-item {
  padding: 11px 12px;
}

.detail-page .review-item {
  padding: 12px;
  margin-bottom: 8px;
}

.detail-page .review-form {
  margin-top: 16px;
  padding-top: 16px;
}

@media (max-width: 720px) {
  .detail-page .info-grid {
    grid-template-columns: 1fr;
  }

  .detail-page .page-header {
    align-items: flex-start;
    flex-direction: column;
    gap: 10px;
  }

  .detail-page .form-row,
  .detail-page .process-form {
    flex-direction: column;
    align-items: stretch;
  }

  .detail-page .form-row label {
    justify-content: space-between;
  }
}

</style>
