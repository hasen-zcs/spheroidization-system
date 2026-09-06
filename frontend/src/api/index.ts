const API_BASE_URL = "http://127.0.0.1:8000"


// ====================
// 系统
// ====================

export async function health() {
  const response = await fetch(
    `${API_BASE_URL}/api/health`
  )

  return response.json()
}


// ====================
// 球化记录
// ====================


export async function createSpheroidization(data: {
  detection_time: string
  iron_water_weight: number
  spheroidization_start_time: string
  spheroidization_end_time: string
  actual_spheroidization_time: number
  actual_entry_length: number
  machine_result: string
  spheroidization_abnormal: boolean
  entry_abnormal: boolean
}) {
  const response = await fetch(
    `${API_BASE_URL}/api/spheroidization`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(data),
    }
  )

  return response.json()
}


export async function querySpheroidization() {
  const response = await fetch(
    `${API_BASE_URL}/api/spheroidization`
  )

  return response.json()
}


export async function getSpheroidization(
  recordId: number
) {
  const response = await fetch(
    `${API_BASE_URL}/api/spheroidization/${recordId}`
  )

  return response.json()
}


export async function queryAbnormalSpheroidization() {
  const response = await fetch(
    `${API_BASE_URL}/api/spheroidization/abnormal`
  )

  return response.json()
}


export async function processSpheroidization(
  recordId: number,
  processedBy: string
) {
  const response = await fetch(
    `${API_BASE_URL}/api/spheroidization/${recordId}/process`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        processed_by: processedBy,
      }),
    }
  )

  return response.json()
}


// ====================
// 人工复核
// ====================

export async function createReview(data: {
  spheroidization_record_id: number
  review_result: string
  review_remark: string
  reviewer: string
}) {
  const response = await fetch(
    `${API_BASE_URL}/api/reviews`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(data),
    }
  )

  return response.json()
}


export async function queryReviews(
  recordId: number
) {
  const response = await fetch(
    `${API_BASE_URL}/api/reviews/${recordId}`
  )

  return response.json()
}


// ====================
// 检测标准
// ====================

export async function createStandard(data: {
  standard_spheroidization_time: number
  standard_entry_length: number
  weighing_standard: number
  created_by: string
  remark: string
}) {
  const response = await fetch(
    `${API_BASE_URL}/api/standards`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(data),
    }
  )

  return response.json()
}


export async function getCurrentStandard() {
  const response = await fetch(
    `${API_BASE_URL}/api/standards/current`
  )

  return response.json()
}


export async function getStandardHistory() {
  const response = await fetch(
    `${API_BASE_URL}/api/standards/history`
  )

  return response.json()
}