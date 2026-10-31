import { auth, clearSession } from "../auth"

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? "").replace(/\/+$/, "")

export interface ApiResponse<T> {
  code: number
  message: string
  data: T | null
}

export interface SpheroidizationRecord {
  id: number
  detection_time: string
  // 后端已允许为空，显示时需兜底成 —
  spheroidization_start_time: string | null
  spheroidization_end_time: string | null
  actual_spheroidization_time: number | null
  spheroidization_abnormal: boolean

  standard_spheroidization_time: number
  // 2026-10 新增字段
  abnormal_type: number | null
  abnormal_reason: string | null
  temperature: number | null
  temperature_time: string | null
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
  // 三个时间字段可选（后端已允许 NULL）
  spheroidization_start_time?: string | null
  spheroidization_end_time?: string | null
  actual_spheroidization_time: number
  spheroidization_abnormal?: boolean | null
  abnormal_type?: number | null
  abnormal_reason?: string | null
  temperature?: number | null
  temperature_time?: string | null
  spheroidization_wire_entry_start_time: string
  spheroidization_wire_entry_end_time: string
  spheroidization_wire_entry_total_duration: number
  spheroidization_weight: number
  spheroidization_image?: string | null
}

// 复核人由后端按登录态取，前端不再传
export interface CreateReviewInput {
  spheroidization_record_id: number
  review_result: string
  review_remark: string
}

// 创建人由后端按登录态取，前端不再传
export interface CreateStandardInput {
  standard_spheroidization_time: number
  standard_spheroidization_time_upper: number | null
  standard_spheroidization_time_lower: number | null
  weighing_standard: number
  remark: string
}

// ====================
// 登录与用户管理
// ====================

export interface AuthUser {
  username: string
  is_admin: boolean
  permission_keys: string[]
}

export interface LoginData {
  token: string
  user: AuthUser
}

export interface UserRecord {
  id: number
  username: string
  is_admin: boolean
  enabled: boolean
  permission_keys: string[]
  created_by: string | null
  created_at: string | null
}

export interface CreateUserInput {
  username: string
  password: string
  is_admin: boolean
}

// ====================
// 切换标准
// ====================

export interface StandardSwitchLog {
  id: number
  from_standard_id: number | null
  to_standard_id: number
  from_value: number | null
  to_value: number
  reason: string
  switched_at: string
}

// ====================
// 请求基础
// ====================

function apiUrl(path: string) {
  return `${API_BASE_URL}${path}`
}

async function request<T>(
  path: string,
  init?: RequestInit
): Promise<ApiResponse<T>> {
  try {
    const headers = new Headers(init?.headers)

    // 统一带 Authorization: Bearer <token>（未登录不带）
    const token = auth.value?.token
    if (token) {
      headers.set("Authorization", `Bearer ${token}`)
    }

    const response = await fetch(apiUrl(path), {
      ...init,
      headers,
    })
    const text = await response.text()

    let body: ApiResponse<T>

    if (!text) {
      body = {
        code: response.ok ? 200 : response.status,
        message: response.ok ? "success" : `请求失败（HTTP ${response.status}）`,
        data: null,
      }
    } else {
      try {
        body = JSON.parse(text) as ApiResponse<T>
      } catch {
        body = {
          code: response.status || -1,
          message: `服务器返回了非 JSON 响应（HTTP ${response.status}）`,
          data: null,
        }
      }
    }

    // code=401：登录态失效，清登录态并跳登录页（router 监听事件）
    if (body.code === 401) {
      clearSession()
      window.dispatchEvent(new Event("auth:expired"))
      return body
    }

    // code=403：无权限，只弹提示，不跳登录（App 监听事件弹 toast）
    if (body.code === 403) {
      window.dispatchEvent(
        new CustomEvent("api:forbidden", { detail: body.message })
      )
    }

    return body
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

function jsonOptions(method: "POST" | "PUT", body: unknown): RequestInit {
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

// 处理人由后端按登录态取，前端不再传
export async function processSpheroidization(
  recordId: number
): Promise<ApiResponse<SpheroidizationRecord>> {
  return request(`/api/spheroidization/${recordId}/process`, {
    method: "POST",
  })
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

// 切换标准（原 applyStandard 已删除，切换统一走本接口，原因必填）
export async function switchStandard(data: {
  standard_id: number
  reason: string
}): Promise<ApiResponse<StandardRecord>> {
  return request("/api/standards/switch", jsonOptions("POST", data))
}

export async function getStandardSwitchLogs(): Promise<
  ApiResponse<StandardSwitchLog[]>
> {
  return request("/api/standards/switch-logs")
}


// ====================
// 登录 / 登出 / 当前用户
// ====================

export async function login(
  username: string,
  password: string
): Promise<ApiResponse<LoginData>> {
  return request(
    "/api/users/login",
    jsonOptions("POST", { username, password })
  )
}


export async function logout(): Promise<ApiResponse<null>> {
  return request("/api/users/logout", { method: "POST" })
}


export async function getCurrentUser(): Promise<ApiResponse<AuthUser>> {
  return request("/api/users/me")
}


// ====================
// 用户管理
// ====================

export async function listUsers(): Promise<ApiResponse<UserRecord[]>> {
  return request("/api/users")
}


export async function createUser(
  data: CreateUserInput
): Promise<ApiResponse<UserRecord>> {
  return request("/api/users", jsonOptions("POST", data))
}


export async function saveUserPermissions(
  userId: number,
  permissionKeys: string[]
): Promise<ApiResponse<UserRecord>> {
  return request(
    `/api/users/${userId}/permissions`,
    jsonOptions("PUT", { permission_keys: permissionKeys })
  )
}


export async function resetUserPassword(
  userId: number,
  newPassword: string
): Promise<ApiResponse<null>> {
  return request(
    `/api/users/${userId}/password`,
    jsonOptions("POST", { new_password: newPassword })
  )
}


export async function setUserEnabled(
  userId: number,
  enabled: boolean
): Promise<ApiResponse<UserRecord>> {
  return request(
    `/api/users/${userId}/enabled`,
    jsonOptions("PUT", { enabled })
  )
}
