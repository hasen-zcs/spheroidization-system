const API_BASE_URL = "http://127.0.0.1:8000"

export interface ApiResponse<T> {
  code: number
  message: string
  data: T
}

export interface SpheroidizationRecord {
  id: number
  detection_time: string
  spheroidization_start_time: string
  spheroidization_end_time: string
  actual_spheroidization_time: number | null
  spheroidization_abnormal: boolean
  standard_spheroidization_time: number
  processed: boolean
  processed_at: string | null
  processed_by: string | null
}

export interface StandardRecord {
  id: number
  standard_spheroidization_time: number
  standard_entry_length: number
  weighing_standard: number
  created_at: string | null
  created_by: string
  remark: string | null
}

export interface ReviewRecord {
  id: number
  spheroidization_record_id: number
  review_result: string
  reviewer: string
  review_remark: string | null
  reviewed_at: string | null
}

export interface CreateSpheroidizationInput {
  detection_time: string
  spheroidization_start_time: string
  spheroidization_end_time: string
  actual_spheroidization_time: number | null
  spheroidization_abnormal: boolean | null
}

export interface CreateReviewInput {
  spheroidization_record_id: number
  review_result: string
  review_remark: string
  reviewer: string
}

export interface CreateStandardInput {
  standard_spheroidization_time: number
  standard_entry_length: number
  weighing_standard: number
  created_by: string
  remark: string
}


// ====================
// 系统
// ====================

export async function health(): Promise<
  ApiResponse<{ status: string }>
> {
  const response = await fetch(
    `${API_BASE_URL}/api/health`
  )

  return response.json()
}


// ====================
// 球化记录
// ====================


export async function createSpheroidization(
  data: CreateSpheroidizationInput
): Promise<ApiResponse<SpheroidizationRecord>> {
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


export async function querySpheroidization(): Promise<
  ApiResponse<SpheroidizationRecord[]>
> {
  const response = await fetch(
    `${API_BASE_URL}/api/spheroidization`
  )

  return response.json()
}


export async function getSpheroidization(
  recordId: number
): Promise<ApiResponse<SpheroidizationRecord | null>> {
  const response = await fetch(
    `${API_BASE_URL}/api/spheroidization/${recordId}`
  )

  return response.json()
}


export async function queryAbnormalSpheroidization(): Promise<
  ApiResponse<SpheroidizationRecord[]>
> {
  const response = await fetch(
    `${API_BASE_URL}/api/spheroidization/abnormal`
  )

  return response.json()
}


export async function processSpheroidization(
  recordId: number,
  processedBy: string
): Promise<ApiResponse<SpheroidizationRecord>> {
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

export async function createReview(
  data: CreateReviewInput
): Promise<ApiResponse<ReviewRecord>> {
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
): Promise<ApiResponse<ReviewRecord[]>> {
  const response = await fetch(
    `${API_BASE_URL}/api/reviews/${recordId}`
  )

  return response.json()
}


// ====================
// 检测标准
// ====================

export async function createStandard(
  data: CreateStandardInput
): Promise<ApiResponse<StandardRecord>> {
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


export async function getCurrentStandard(): Promise<
  ApiResponse<StandardRecord | null>
> {
  const response = await fetch(
    `${API_BASE_URL}/api/standards/current`
  )

  return response.json()
}


export async function getStandardHistory(): Promise<
  ApiResponse<StandardRecord[]>
> {
  const response = await fetch(
    `${API_BASE_URL}/api/standards/history`
  )

  return response.json()
}
