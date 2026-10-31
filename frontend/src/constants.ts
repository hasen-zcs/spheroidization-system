// ====================
// 全局常量
// ====================

// 异常类型中文字典
export const ABNORMAL_TYPE_LABELS: Record<number, string> = {
  1: "进站未球化",
  2: "进线提前中止",
  3: "超标准",
  4: "低于标准",
}

export function abnormalTypeLabel(
  type: number | null | undefined
): string {
  if (type === null || type === undefined) {
    return "未知"
  }
  return ABNORMAL_TYPE_LABELS[type] ?? `未知类型(${type})`
}

// ====================
// 权限点（9 个）
// ====================

export interface PermissionDef {
  key: string
  label: string
}

/** 页面组权限点 */
export const PAGE_PERMISSIONS: PermissionDef[] = [
  { key: "page:records", label: "球化记录" },
  { key: "page:abnormal", label: "异常记录" },
  { key: "page:standard", label: "检测标准" },
  { key: "page:users", label: "用户管理" },
]

/** 功能组权限点 */
export const ACTION_PERMISSIONS: PermissionDef[] = [
  { key: "action:process", label: "标记处理" },
  { key: "action:review", label: "人工复核" },
  { key: "action:create_standard", label: "新增检测标准" },
  { key: "action:switch_standard", label: "切换标准" },
  { key: "action:manage_users", label: "用户管理操作" },
]

/** 权限点中文名映射（key → label） */
export const PERMISSION_LABELS: Record<string, string> = Object.fromEntries(
  [...PAGE_PERMISSIONS, ...ACTION_PERMISSIONS].map(
    (item) => [item.key, item.label]
  )
)

/** 权限分配面板的两组数据 */
export const PERMISSION_GROUPS: Array<{
  key: "page" | "action"
  label: string
  items: PermissionDef[]
}> = [
  { key: "page", label: "页面", items: PAGE_PERMISSIONS },
  { key: "action", label: "功能", items: ACTION_PERMISSIONS },
]
