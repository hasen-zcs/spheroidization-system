// ====================
// 全局常量
// ====================

// 异常类型中文字典
export const ABNORMAL_TYPE_LABELS: Record<number, string> = {
  // vpmin 正常判定给的就是 0，不是 null；null 才代表"没判"
  0: "正常",
  1: "进站未球化",
  2: "进线中断",
  3: "超标准",
  4: "低于标准",
  5: "分段多次球化",
  6: "未判定",
}

/** 机器检测结果的三态：true 异常 / false 正常 / null 未知。
 *
 * 2026-11-01 起"未判定（类型 6）"归入异常（abnormal=true，原因写"未判定"），
 * pending 只留给"上游压根没给判定"的老数据——页面不能把它显示成"正常"，
 * 质量系统里这等于替机器下结论。
 */
export type AbnormalTone = "abnormal" | "normal" | "pending"

export function abnormalTone(
  value: boolean | number | null | undefined
): AbnormalTone {
  if (value === null || value === undefined) {
    return "pending"
  }
  return value ? "abnormal" : "normal"
}

export function abnormalResultLabel(
  value: boolean | number | null | undefined
): string {
  const tone = abnormalTone(value)
  if (tone === "pending") {
    return "未判定"
  }
  return tone === "abnormal" ? "异常" : "正常"
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
// 权限点（10 个）
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
  { key: "action:create_standard", label: "检测标准管理" },
  { key: "action:switch_standard", label: "切换标准" },
  { key: "action:manage_data", label: "数据管理" },
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

// 下拉条预设选项（2026-11-06 三需求 R2，用户视角=车间/工艺员）
export const SWITCH_REASON_OPTIONS: string[] = [
  "标准值更新（工艺优化）",
  "异常炉次后重新标定",
  "新材料试浇",
  "设备仪表标定后",
  "季节温变调整",
  "纠正前期误操作",
]

export const REVIEW_REMARK_OPTIONS: string[] = [
  "机器误判，纠正为正常",
  "机器漏判，纠正为异常",
  "取样验证与机器一致",
  "取样验证与机器不符",
  "设备故障后复测",
  "样品缺失无法复核",
]

export const STANDARD_REMARK_OPTIONS: string[] = [
  "工艺参数优化",
  "异常炉次后重新标定",
  "新材料新牌号试浇",
  "设备变更或标定",
  "季节温变调整",
]
