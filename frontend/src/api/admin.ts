// 管理员「数据管理」页（/admin，权限 action:manage_data）的接口。
// 全部走 index.ts 的统一请求封装（带 token、统一信封处理），不另造 fetch。
//
// 列表接口对应后端 TASK-9 的实际实现（app/api/admin.py）：
// - 球化记录   GET /api/spheroidization?include_deleted=   （复用现有接口）
// - 检测标准   GET /api/standards/history?include_deleted= （复用现有接口，不分页）
// - 切换记录   GET /api/admin/switch-logs                  （TASK-9 新增）
// - 复核记录   GET /api/admin/reviews                      （TASK-9 新增）
// 后两者分页结构 {items, total, page, page_size, has_more}，行里带软删三字段。

import {
  jsonOptions,
  querySpheroidization,
  request,
} from "./index"
import type {
  ApiResponse,
  ReviewRecord,
  SpheroidizationRecord,
  StandardRecord,
  StandardSwitchLog,
} from "./index"

// ====================
// 类型
// ====================

/** v6 软删除信息：未删除时三项均为 null */
export interface SoftDeleteInfo {
  deleted_at: string | null
  deleted_by: string | null
  delete_reason: string | null
}

export interface AdminRecordItem
  extends SpheroidizationRecord,
    SoftDeleteInfo {}

export interface AdminStandardItem
  extends StandardRecord,
    SoftDeleteInfo {}

// 原类型里 from_value / to_value 的可空口径不一致（一个可 null 一个不可），
// 管理页统一按"标准被作废后值为 null"收，所以这里 Omit 掉重声明
export interface AdminSwitchLogItem
  extends Omit<StandardSwitchLog, "from_value" | "to_value">,
    SoftDeleteInfo {
  /** 原标准球化时长；标准已作废（软删）时为 null */
  from_value: number | null
  /** 新标准球化时长；标准已作废（软删）时为 null */
  to_value: number | null
}

export interface AdminReviewItem extends ReviewRecord, SoftDeleteInfo {}

export interface AdminPage<T> {
  items: T[]
  total: number
  page: number
  page_size: number
  has_more: boolean
}

export interface AdminListQuery {
  page?: number
  page_size?: number
  include_deleted?: boolean
}

// ====================
// 列表
// ====================

function listSearch(params: AdminListQuery): string {
  const search = new URLSearchParams()
  search.set("page", String(params.page ?? 1))
  search.set("page_size", String(params.page_size ?? 20))
  search.set("include_deleted", String(params.include_deleted ?? false))
  return search.toString()
}

/** 球化记录 tab：复用现有列表接口，带 include_deleted 才能看到已删除行 */
export async function adminQueryRecords(
  params: AdminListQuery = {}
): Promise<ApiResponse<AdminPage<AdminRecordItem>>> {
  const result = await querySpheroidization({
    page: params.page,
    page_size: params.page_size,
    include_deleted: params.include_deleted,
  })
  return result as ApiResponse<AdminPage<AdminRecordItem>>
}

/** 检测标准 tab：历史接口不分页（返回全量数组），分页在前端切 */
export async function adminQueryStandards(
  includeDeleted: boolean
): Promise<ApiResponse<AdminStandardItem[]>> {
  return request(`/api/standards/history?include_deleted=${includeDeleted}`)
}

/** 标准当前生效 id（判断"当前生效标准不能删"用） */
export async function adminGetCurrentStandardId(): Promise<number | null> {
  const result = await request<{ id: number } | null>(
    "/api/standards/current"
  )
  if (result.code !== 200 || result.data === null) {
    return null
  }
  return result.data.id
}

export async function adminQuerySwitchLogs(
  params: AdminListQuery = {}
): Promise<ApiResponse<AdminPage<AdminSwitchLogItem>>> {
  return request(`/api/admin/switch-logs?${listSearch(params)}`)
}

export async function adminQueryReviews(
  params: AdminListQuery = {}
): Promise<ApiResponse<AdminPage<AdminReviewItem>>> {
  return request(`/api/admin/reviews?${listSearch(params)}`)
}

// ====================
// 软删除 / 恢复 / 处理状态
// ====================

// 原因必填；删除人 / 处理人由后端按登录态取，前端不传。

export async function deleteRecord(
  recordId: number,
  reason: string
): Promise<ApiResponse<null>> {
  return request(
    `/api/admin/records/${recordId}/delete`,
    jsonOptions("POST", { reason })
  )
}

// 恢复无需原因：后端不收请求体
export async function restoreRecord(
  recordId: number
): Promise<ApiResponse<null>> {
  return request(`/api/admin/records/${recordId}/restore`, {
    method: "POST",
  })
}

export async function changeProcessed(
  recordId: number,
  processed: 0 | 1,
  reason: string
): Promise<ApiResponse<null>> {
  return request(
    `/api/admin/records/${recordId}/processed`,
    jsonOptions("POST", { processed, reason })
  )
}

export async function deleteStandard(
  recordId: number,
  reason: string
): Promise<ApiResponse<null>> {
  return request(
    `/api/admin/standards/${recordId}/delete`,
    jsonOptions("POST", { reason })
  )
}

export async function restoreStandard(
  recordId: number
): Promise<ApiResponse<null>> {
  return request(`/api/admin/standards/${recordId}/restore`, {
    method: "POST",
  })
}

export async function deleteSwitchLog(
  recordId: number,
  reason: string
): Promise<ApiResponse<null>> {
  return request(
    `/api/admin/switch-logs/${recordId}/delete`,
    jsonOptions("POST", { reason })
  )
}

export async function restoreSwitchLog(
  recordId: number
): Promise<ApiResponse<null>> {
  return request(`/api/admin/switch-logs/${recordId}/restore`, {
    method: "POST",
  })
}

export async function deleteReview(
  recordId: number,
  reason: string
): Promise<ApiResponse<null>> {
  return request(
    `/api/admin/reviews/${recordId}/delete`,
    jsonOptions("POST", { reason })
  )
}

export async function restoreReview(
  recordId: number
): Promise<ApiResponse<null>> {
  return request(`/api/admin/reviews/${recordId}/restore`, {
    method: "POST",
  })
}
