import { ref } from "vue"

// ====================
// 登录态（token + 用户信息）的本地存取
// ====================

export interface AuthUser {
  username: string
  is_admin: boolean
  permission_keys: string[]
}

export interface AuthSession {
  token: string
  user: AuthUser
}

const STORAGE_KEY = "spheroidization.auth.session"

function loadStoredSession(): AuthSession | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) {
      return null
    }

    const parsed = JSON.parse(raw) as Partial<AuthSession> | null

    if (
      !parsed ||
      typeof parsed.token !== "string" ||
      parsed.token.length === 0 ||
      !parsed.user ||
      typeof parsed.user.username !== "string"
    ) {
      return null
    }

    return parsed as AuthSession
  } catch {
    return null
  }
}

/** 全局登录态（响应式），整个应用共享 */
export const auth = ref<AuthSession | null>(loadStoredSession())

export function isLoggedIn(): boolean {
  return auth.value !== null
}

export function currentUser(): AuthUser | null {
  return auth.value?.user ?? null
}

/**
 * 权限判断：
 * - 未登录 → false
 * - 管理员 → true（拥有全部权限）
 * - 普通用户 → 查登录态里的权限集合
 */
export function can(permissionKey: string): boolean {
  const session = auth.value
  if (!session) {
    return false
  }
  if (session.user.is_admin) {
    return true
  }
  return session.user.permission_keys.includes(permissionKey)
}

export function applySession(session: AuthSession): void {
  auth.value = session
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(session))
  } catch {
    // localStorage 不可用（如隐私模式）时只保留内存态
  }
}

export function clearSession(): void {
  auth.value = null
  try {
    localStorage.removeItem(STORAGE_KEY)
  } catch {
    // 忽略
  }
}
