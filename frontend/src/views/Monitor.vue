<script setup lang="ts">
import { computed, onMounted, ref } from "vue"
import { useRouter } from "vue-router"

import { querySpheroidization } from "../api"
import type { SpheroidizationRecord } from "../api"

const router = useRouter()

const videoFeed1 = "/video_feed1"
const videoFeed2 = "/video_feed2"

const records = ref<SpheroidizationRecord[]>([])
const loading = ref(true)
const videoErrors = ref([false, false])

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

const tableRows = computed(() => {
  return [...records.value]
    .sort((a, b) => {
      return (
        new Date(b.detection_time).getTime() -
        new Date(a.detection_time).getTime()
      )
    })
    .slice(0, 5)
})

const latestRecord = computed(() => {
  return tableRows.value[0] ?? null
})

const statusInfo = computed(() => {
  const record = latestRecord.value

  return {
    recordStatus: record
      ? record.processed
        ? "已处理"
        : "待处理"
      : "--",
    spheroidizationTime: record
      ? `${record.standard_spheroidization_time} / ${record.actual_spheroidization_time ?? "--"}`
      : "--",
    detectionTime: record
      ? record.detection_time
      : "--",
    machineResult: record
      ? record.spheroidization_abnormal
        ? "异常"
        : "正常"
      : "--",
    processedBy: record
      ? record.processed_by ?? "--"
      : "--",
  }
})

function getAbnormalReason(record: SpheroidizationRecord) {
  const reasons: string[] = []

  if (record.spheroidization_abnormal) {
    reasons.push("球化异常")
  }

  return reasons.length > 0
    ? reasons.join("、")
    : "无"
}

function openCreateForm() {
  router.push({
    path: "/records/spheroidization",
    query: {
      create: "1",
    },
  })
}

onMounted(() => {
  loadRecords()
})
</script>

<template>
  <div class="home-wrapper">
    <div class="page-title">
      浇注工位AI智能化系统
    </div>

    <div class="video-wrap">
      <div class="video-box">
        <img
          :src="videoFeed1"
          alt="摄像头1"
          @load="videoErrors[0] = false"
          @error="videoErrors[0] = true"
        />

        <div
          v-if="videoErrors[0]"
          class="video-placeholder"
        >
          等待视频流接入
        </div>

        <span class="cam-label">
          浇注工位 #01
        </span>

        <span
          class="live-dot"
          :class="{ offline: videoErrors[0] }"
        >
          {{ videoErrors[0] ? "未连接" : "视频流" }}
        </span>
      </div>

      <div class="video-box">
        <img
          :src="videoFeed2"
          alt="摄像头2"
          @load="videoErrors[1] = false"
          @error="videoErrors[1] = true"
        />

        <div
          v-if="videoErrors[1]"
          class="video-placeholder"
        >
          等待视频流接入
        </div>

        <span class="cam-label">
          浇注工位 #02
        </span>

        <span
          class="live-dot"
          :class="{ offline: videoErrors[1] }"
        >
          {{ videoErrors[1] ? "未连接" : "视频流" }}
        </span>
      </div>
    </div>

    <button
      class="btn-bar"
      type="button"
      @click="openCreateForm"
    >
      新增一行数据
    </button>

    <div
      v-if="loading"
      class="empty-state"
    >
      正在加载数据...
    </div>

    <div
      v-else
      class="table-scroll"
    >
      <table>
        <thead>
          <tr>
            <th>序号</th>
            <th>称重时间</th>
            <th>进场时间</th>
            <th>离场时间</th>
            <th>球化结果</th>
            <th>报警原因</th>
          </tr>
        </thead>

        <tbody>
          <tr
            v-for="row in tableRows"
            :key="row.id"
          >
            <td>{{ row.id }}</td>
            <td>{{ row.detection_time }}</td>
            <td>{{ row.spheroidization_start_time }}</td>
            <td>{{ row.spheroidization_end_time }}</td>
            <td>
              {{
                row.spheroidization_abnormal
                  ? "异常"
                  : "正常"
              }}
            </td>
            <td>{{ getAbnormalReason(row) }}</td>
          </tr>

          <tr v-if="tableRows.length === 0">
            <td
              class="empty-cell"
              colspan="6"
            >
              暂无检测记录
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <div class="info-panel">
      <div class="info-column">
        <div>
          当前记录状态：
          <input
            :value="statusInfo.recordStatus"
            readonly
          />
        </div>

        <div>
          标准/实际球化时间：
          <input
            :value="statusInfo.spheroidizationTime"
            readonly
          />
        </div>

        <div>
          检测时间：
          <input
            :value="statusInfo.detectionTime"
            readonly
          />
        </div>
      </div>

      <div class="info-column">
        <div>
          检测结果：
          <input
            :value="statusInfo.machineResult"
            readonly
          />
        </div>

        <div>
          处理人：
          <input
            :value="statusInfo.processedBy"
            readonly
          />
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.home-wrapper {
  min-height: calc(100vh - 40px);
  padding: 10px 12px;
  background: #f0f4f8;
}

.page-title {
  margin-bottom: 8px;
  color: #003399;
  font-size: 15px;
  font-weight: 700;
  letter-spacing: 2px;
  text-align: center;
}

.video-wrap {
  display: flex;
  gap: 4px;
  margin-bottom: 8px;
}

.video-box {
  position: relative;
  width: 50%;
  aspect-ratio: 16 / 9;
  overflow: hidden;
  background: #1a1a2e;
  border-radius: 4px;
}

.video-box img {
  display: block;
  width: 100%;
  height: 100%;
  object-fit: contain;
  background: #0a0a1a;
}

.video-placeholder {
  position: absolute;
  inset: 0;
  display: grid;
  color: #9fb3c8;
  font-size: 12px;
  background: #0a0a1a;
  place-items: center;
}

.cam-label {
  position: absolute;
  bottom: 8px;
  left: 12px;
  padding: 2px 9px;
  color: rgba(255, 255, 255, 0.85);
  font-size: 11px;
  background: rgba(0, 0, 0, 0.5);
  border-radius: 3px;
}

.live-dot {
  position: absolute;
  top: 8px;
  right: 12px;
  color: #00ff88;
  font-size: 11px;
}

.live-dot::before {
  color: #00ff88;
  content: "● ";
}

.live-dot.offline,
.live-dot.offline::before {
  color: #ff9f43;
}

.btn-bar {
  width: 100%;
  margin-bottom: 6px;
  padding: 4px;
  color: #003399;
  font-size: 11px;
  font-weight: 700;
  text-align: center;
  background: #eee;
  border: 1px solid #ddd;
  border-radius: 4px;
  user-select: none;
}

.btn-bar::before {
  font-size: 13px;
  content: "+ ";
}

.btn-bar:hover {
  background: #dde8f5;
  border-color: #4a8af4;
}

table {
  width: 100%;
  min-width: 820px;
  font-size: 12px;
  border-collapse: collapse;
  background: #fff;
}

.table-scroll {
  width: 100%;
  margin-bottom: 8px;
  overflow-x: auto;
}

th {
  padding: 4px 7px;
  color: #1a2a3a;
  font-weight: 700;
  background: #ffdd00;
  border: 1px solid #333;
}

td {
  padding: 4px 7px;
  color: #1a2a3a;
  text-align: center;
  background: #fff;
  border: 1px solid #333;
}

.empty-cell {
  color: #888;
}

.info-panel {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  padding: 6px 12px;
  background: #e6f2ff;
  border: 1px solid #b8d4e8;
  border-radius: 4px;
}

.info-column {
  display: grid;
  gap: 3px;
}

.info-column > div {
  font-size: 12px;
  line-height: 1.2;
  white-space: nowrap;
}

.info-panel input {
  width: 138px;
  padding: 1px 6px;
  color: #003399;
  font-size: 12px;
  font-weight: 500;
  background: #fff;
  border: 1px solid #b8d4e8;
  border-radius: 3px;
  outline: none;
}

@media (max-width: 768px) {
  .video-wrap {
    flex-direction: column;
  }

  .video-box {
    width: 100%;
  }

  .info-panel {
    flex-direction: column;
  }

}
</style>
