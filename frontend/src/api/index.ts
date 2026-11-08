import { auth, clearSession } from "../auth"

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? "").replace(/\/+$/, "")

export interface ApiResponse<T> {
  code: number
  message: string
  data: T | null
}

/** 分段明细：偏移相对"亮光首段起点"，单位秒（v3，2026-11-01） */
export interface FlashSegment {
  seg_index: number
  start_offset: number
  end_offset: number
  /** 与上一段的停顿秒数；第一段为 null */
  gap_before: number | null
  duration: number
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
  /** 按钮上升沿原始时刻；为空表示这炉没有按钮数据（锚点回退到亮光起点） */
  plc_button_time: string | null
  temperature: number | null
  temperature_time: string | null
  spheroidization_wire_entry_start_time: string
  // 进线结束 / 总时长可为空（PLC 采不到时为空），display() 兜底成 —
  spheroidization_wire_entry_end_time: string | null
  spheroidization_wire_entry_total_duration: number | null
  spheroidization_weight: number

  processed: boolean
  processed_at: string | null
  processed_by: string | null
  review_result: string | null

  // 仅详情接口返回。
  spheroidization_image?: string | null
  // 仅详情接口返回；列表接口没有这个键。老记录/单段记录是空数组。
  segments?: FlashSegment[]
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
  // 管理员数据管理页看已删除记录用；不传则后端默认 false
  include_deleted?: boolean
  start_time?: string
  end_time?: string
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
  // 幂等键：两个都传才生效（合并层用），人工补录不传
  device_id?: string | null
  external_id?: string | null
  segments?: FlashSegment[]
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
  // 进线结束 / 总时长可空（PLC 采不到时上游发 null，空着入库不丢炉）
  spheroidization_wire_entry_end_time: string | null
  spheroidization_wire_entry_total_duration: number | null
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
  // 2026-10-31：后端同时给原生字段名（from_standard_record_id）和契约字段名，
  // 这里全部标可选，避免任何一边变动时整页类型报错。
  from_standard_id?: number | null
  to_standard_id?: number
  from_value?: number | null
  to_value?: number
  from_standard_record_id?: number | null
  to_standard_record_id?: number
  operated_by?: string
  /** 后端拼好的整句中文，优先直接显示 */
  summary?: string
  reason: string
  switched_at: string
}

export interface StandardSwitchLogPage {
  items: StandardSwitchLog[]
  page: number
  page_size: number
}

// ====================
// 请求基础
// ====================

function apiUrl(path: string) {
  return `${API_BASE_URL}${path}`
}

// request / jsonOptions 也导给 api/admin.ts 用：统一走这一套请求封装，
// 带 token、统一信封处理，别在别的文件里再造一遍 fetch。
export async function request<T>(
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
      // 轮询刷新必须绕开浏览器缓存，否则可能拿到旧列表
      cache: "no-store",
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

export function jsonOptions(
  method: "POST" | "PUT" | "DELETE",
  body: unknown
): RequestInit {
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
  if (params.include_deleted !== undefined) {
    search.set("include_deleted", String(params.include_deleted))
  }
  if (params.start_time) {
    search.set("start_time", params.start_time)
  }
  if (params.end_time) {
    search.set("end_time", params.end_time)
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
  ApiResponse<StandardSwitchLogPage | StandardSwitchLog[]>
> {
  return request("/api/standards/switch-logs")
}

// 修订检测标准：只传 5 个业务字段，创建信息不接受前端传（后端 extra="forbid"）
export interface UpdateStandardInput {
  standard_spheroidization_time: number
  standard_spheroidization_time_upper: number | null
  standard_spheroidization_time_lower: number | null
  weighing_standard: number
  remark: string
}

export async function updateStandard(
  standardId: number,
  data: UpdateStandardInput
): Promise<ApiResponse<StandardRecord>> {
  return request(`/api/standards/${standardId}`, jsonOptions("PUT", data))
}

// 软删除检测标准：原因必填，删除人由后端按登录态取
export async function deleteStandard(
  standardId: number,
  reason: string
): Promise<ApiResponse<null>> {
  return request(
    `/api/standards/${standardId}`,
    jsonOptions("DELETE", { reason })
  )
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


// 登录页账号下拉：只含用户名，无其他字段
export interface AccountOption {
  username: string
}

export async function getAccounts(): Promise<
  ApiResponse<AccountOption[]>
> {
  return request("/api/users/accounts")
}


export async function changeOwnPassword(
  oldPassword: string,
  newPassword: string
): Promise<ApiResponse<null>> {
  return request(
    "/api/users/me/password",
    jsonOptions("POST", { old_password: oldPassword, new_password: newPassword })
  )
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


// ====================
// 报表（summary 统计 + CSV 导出）
// ====================

export interface ReportDurationStats {
  // 无样本时为 null（不是 0，0 秒是假数据）
  avg: number | null
  median: number | null
  min: number | null
  max: number | null
}

export interface ReportDayRow {
  date: string
  total: number
  abnormal: number
}

/** 班次统计行（白班 08:00~20:00 / 夜班 20:00~次日 08:00） */
export interface ReportShiftRow {
  shift: string
  total: number
  abnormal: number
  normal: number
  // 仅对 actual_spheroidization_time 非空的记录求平均，无样本为 null
  avg_actual_time: number | null
}

/** 标准统计行（按 standard_record_id 分组，JOIN 标准表的创建信息） */
export interface ReportStandardRow {
  standard_record_id: number
  standard_time: number
  standard_created_at: string
  standard_created_by: string
  total: number
  abnormal: number
  avg_actual_time: number | null
}

/** 趋势行（区间逐日，缺天补齐：total=0 / rate=0 / avg=null） */
export interface ReportTrendRow {
  date: string
  total: number
  abnormal: number
  // 0-1，保留 4 位
  abnormal_rate: number
  avg_actual_time: number | null
}

export interface ReportSummary {
  total: number
  // abnormal_type 0..6 各自的数量（NULL 口径归入 0）
  by_type: Record<number, number>
  // 类型 ≠ 0 的记录数（未判定 type=6 也算在内）
  abnormal_count: number
  // 0-1，保留 4 位
  abnormal_rate: number
  unjudged_count: number
  duration: ReportDurationStats
  temperature: {
    covered: number
    total: number
    coverage_rate: number
    by_gun: Record<string, { count: number; avg: number | null }>
  }
  shifts: ReportShiftRow[]
  standards: ReportStandardRow[]
  trend: ReportTrendRow[]
  by_day: ReportDayRow[]
}

export interface ReportRangeQuery {
  start?: string | null
  end?: string | null
  type?: number | null
}

export async function getReportSummary(
  start: string | null,
  end: string | null
): Promise<ApiResponse<ReportSummary>> {
  const search = new URLSearchParams()
  if (start) {
    search.set("start", start)
  }
  if (end) {
    search.set("end", end)
  }
  return request(`/api/reports/summary?${search.toString()}`)
}

function reportExportSearch(query: ReportRangeQuery): string {
  const search = new URLSearchParams()
  if (query.start) {
    search.set("start", query.start)
  }
  if (query.end) {
    search.set("end", query.end)
  }
  if (query.type !== null && query.type !== undefined) {
    search.set("type", String(query.type))
  }
  return search.toString()
}

/** 导出 CSV 的地址（带当前筛选条件） */
export function reportExportUrl(query: ReportRangeQuery = {}) {
  const suffix = reportExportSearch(query)
  return `${apiUrl("/api/reports/export")}${suffix ? `?${suffix}` : ""}`
}

/** 导出 Excel 的地址（参数与 CSV 一致） */
export function reportExportExcelUrl(query: ReportRangeQuery = {}) {
  const suffix = reportExportSearch(query)
  return `${apiUrl("/api/reports/export/excel")}${suffix ? `?${suffix}` : ""}`
}

/**
 * 下载导出文件（CSV / Excel 共用）：fetch 带 Bearer token
 * （直接 <a> 跳转带不了 Authorization），拿到 blob 后触发浏览器下载。
 * 后端 401/403 时走统一 JSON 信封（HTTP 200），
 * 此时解析出 message 抛错，并照旧触发 auth:expired / api:forbidden 事件。
 */
async function downloadReportFile(
  url: string,
  fallbackName: string
): Promise<void> {
  const headers = new Headers()
  const token = auth.value?.token
  if (token) {
    headers.set("Authorization", `Bearer ${token}`)
  }

  const response = await fetch(url, { headers, cache: "no-store" })

  const contentType = response.headers.get("content-type") ?? ""
  if (!response.ok || contentType.includes("application/json")) {
    let message = `导出失败（HTTP ${response.status}）`
    try {
      const body = (await response.json()) as ApiResponse<null>
      if (body.message) {
        message = body.message
      }
      if (body.code === 401) {
        clearSession()
        window.dispatchEvent(new Event("auth:expired"))
      } else if (body.code === 403) {
        window.dispatchEvent(
          new CustomEvent("api:forbidden", { detail: body.message })
        )
      }
    } catch {
      // 非 JSON 响应体，保留默认错误文案
    }
    throw new Error(message)
  }

  const blob = await response.blob()
  const objectUrl = URL.createObjectURL(blob)
  const anchor = document.createElement("a")
  anchor.href = objectUrl
  const disposition = response.headers.get("content-disposition") ?? ""
  const match = disposition.match(/filename="?([^";]+)"?/)
  anchor.download = match ? match[1] : fallbackName
  document.body.appendChild(anchor)
  anchor.click()
  anchor.remove()
  URL.revokeObjectURL(objectUrl)
}

/** 下载导出 CSV */
export async function downloadReportCsv(
  query: ReportRangeQuery = {}
): Promise<void> {
  return downloadReportFile(
    reportExportUrl(query),
    "spheroidization_export.csv"
  )
}

/** 下载导出 Excel */
export async function downloadReportExcel(
  query: ReportRangeQuery = {}
): Promise<void> {
  return downloadReportFile(
    reportExportExcelUrl(query),
    "spheroidization_export.xlsx"
  )
}
