const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? "").replace(/\/+$/, "")

export interface ApiResponse<T> {
  code: number
  message: string
  data: T | null
}

export interface SpheroidizationRecord {
  id: number
  detection_time: string
  spheroidization_start_time: string
  spheroidization_end_time: string
  actual_spheroidization_time: number
  spheroidization_abnormal: boolean

  standard_spheroidization_time: number
  spheroidization_temperature: number
  spheroidization_temperature_time: string
  spheroidization_wire_entry_start_time: string
  spheroidization_wire_entry_end_time: string
  spheroidization_wire_entry_total_duration: number
  spheroidization_weight: number

  processed: boolean
  processed_at: string | null
  processed_by: string | null
  review_result: string | null

  // 仅详情接口返回。
  spheroidization_image?: string | null
}

export interface SpheroidizationPage {
  items: SpheroidizationRecord[]
  total: number
  page: number
  page_size: number
  has_more: boolean
}

export interface SpheroidizationStats {
  total: number
  abnormal: number
  processed: number
  unprocessed: number
}

export interface SpheroidizationQuery {
  page?: number
  page_size?: number
  abnormal?: boolean
  processed?: boolean
}

export interface StandardRecord {
  id: number
  standard_spheroidization_time: number
  standard_spheroidization_time_upper: number | null
  standard_spheroidization_time_lower: number | null
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
  actual_spheroidization_time: number
  spheroidization_abnormal: boolean | null
  spheroidization_temperature: number
  spheroidization_temperature_time: string
  spheroidization_wire_entry_start_time: string
  spheroidization_wire_entry_end_time: string
  spheroidization_wire_entry_total_duration: number
  spheroidization_weight: number
  spheroidization_image?: string | null
}

export interface CreateReviewInput {
  spheroidization_record_id: number
  review_result: string
  review_remark: string
  reviewer: string
}

export interface CreateStandardInput {
  standard_spheroidization_time: number
  standard_spheroidization_time_upper: number | null
  standard_spheroidization_time_lower: number | null
  weighing_standard: number
  created_by: string
  remark: string
}


// ====================
// 系统
// ====================

function apiUrl(path: string) {
  return `${API_BASE_URL}${path}`
}

async function request<T>(
  path: string,
  init?: RequestInit
): Promise<ApiResponse<T>> {
  try {
    const response = await fetch(apiUrl(path), init)
    const text = await response.text()

    if (!text) {
      return {
        code: response.ok ? 200 : response.status,
        message: response.ok ? "success" : `请求失败（HTTP ${response.status}）`,
        data: null,
      }
    }

    try {
      return JSON.parse(text) as ApiResponse<T>
    } catch {
      return {
        code: response.status || -1,
        message: `服务器返回了非 JSON 响应（HTTP ${response.status}）`,
        data: null,
      }
    }
  } catch (error) {
    return {
      code: -1,
      message:
        error instanceof Error
          ? `无法连接后端服务：${error.message}`
          : "无法连接后端服务",
      data: null,
    }
  }
}

function jsonOptions(method: "POST", body: unknown): RequestInit {
  return {
    method,
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(body),
  }
}

export function spheroidizationImageUrl(recordId: number) {
  return apiUrl(`/api/spheroidization/${recordId}/image`)
}

export async function health(): Promise<
  ApiResponse<{ status: string }>
> {
  return request("/api/health")
}


// ====================
// 球化记录
// ====================


export async function createSpheroidization(
  data: CreateSpheroidizationInput
): Promise<ApiResponse<SpheroidizationRecord>> {
  return request("/api/spheroidization", jsonOptions("POST", data))
}


export async function querySpheroidization(
  params: SpheroidizationQuery = {}
): Promise<
  ApiResponse<SpheroidizationPage>
> {
  const search = new URLSearchParams()
  search.set("page", String(params.page ?? 1))
  search.set("page_size", String(params.page_size ?? 20))

  if (params.abnormal !== undefined) {
    search.set("abnormal", String(params.abnormal))
  }
  if (params.processed !== undefined) {
    search.set("processed", String(params.processed))
  }

  return request(`/api/spheroidization?${search.toString()}`)
}


export async function getSpheroidization(
  recordId: number
): Promise<ApiResponse<SpheroidizationRecord | null>> {
  return request(`/api/spheroidization/${recordId}`)
}


export async function getSpheroidizationStats(): Promise<
  ApiResponse<SpheroidizationStats>
> {
  return request("/api/spheroidization/stats")
}


export async function processSpheroidization(
  recordId: number,
  processedBy: string
): Promise<ApiResponse<SpheroidizationRecord>> {
  return request(
    `/api/spheroidization/${recordId}/process`,
    jsonOptions("POST", { processed_by: processedBy })
  )
}


// ====================
// 人工复核
// ====================

export async function createReview(
  data: CreateReviewInput
): Promise<ApiResponse<ReviewRecord>> {
  return request("/api/reviews", jsonOptions("POST", data))
}


export async function queryReviews(
  recordId: number
): Promise<ApiResponse<ReviewRecord[]>> {
  return request(`/api/reviews/${recordId}`)
}


// ====================
// 检测标准
// ====================

export async function createStandard(
  data: CreateStandardInput
): Promise<ApiResponse<StandardRecord>> {
  return request("/api/standards", jsonOptions("POST", data))
}


export async function applyStandard(
  standardId: number
): Promise<ApiResponse<StandardRecord>> {
  return request(`/api/standards/${standardId}/apply`, { method: "POST" })
}


export async function getCurrentStandard(): Promise<
  ApiResponse<StandardRecord | null>
> {
  return request("/api/standards/current")
}


export async function getStandardHistory(): Promise<
  ApiResponse<StandardRecord[]>
> {
  return request("/api/standards/history")
}
