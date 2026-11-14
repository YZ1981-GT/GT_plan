const SENSITIVE_WORKPAPER_DRAFT_PREFIXES = [
  'strict-cas-draft:',
  'g8-draft:',
  'g9-draft:',
  'g10-draft:',
  'g11-draft:',
  'g12-draft:',
  'g7-main-draft:',
  'g7-sub-draft:',
  'g7-equity-method-draft:',
  'h10-draft:',
  'gt:stocktake-draft:',
  'gt:h-stocktake-draft:',
  // 当前无生产调用方，但载荷可含底稿正文；登出一并清，未来接入前仍需身份化。
  'gt_wp_offline_',
] as const

const SENSITIVE_WORKPAPER_DRAFT_KEYS = new Set(['gt_wp_offline_index'])

function checklistDraftOwner(): string | null {
  if (typeof sessionStorage === 'undefined') return null
  try {
    const stored = sessionStorage.getItem('user')
    const user = stored ? JSON.parse(stored) : null
    return typeof user?.id === 'string' && user.id ? encodeURIComponent(user.id) : null
  } catch {
    return null
  }
}

/** 任意敏感底稿草稿都以登录用户为第一维；scope 每段编码，不能让分隔符混淆身份。 */
export function userScopedWorkpaperDraftPrefix(namespace: string, scope: readonly string[]): string | null {
  const owner = checklistDraftOwner()
  const normalized = scope.filter(Boolean).map((part) => encodeURIComponent(part))
  return owner && normalized.length > 0 ? `${namespace}:${owner}:${normalized.join(':')}:` : null
}

export function userScopedWorkpaperDraftKey(namespace: string, scope: readonly string[]): string | null {
  const prefix = userScopedWorkpaperDraftPrefix(namespace, scope.slice(0, -1))
  // 不用 `scope.at(-1)`：本仓部分 tsconfig（`tsconfig.pac-t21.json` 等）lib 低于
  // ES2022，`Array.prototype.at` 不在类型里 ⇒ TS2339 打红。索引取值等价且各处都能编。
  const item = scope.length > 0 ? scope[scope.length - 1] : undefined
  return prefix && item ? `${prefix}${encodeURIComponent(item)}` : null
}

/** 草稿键必须包含登录身份；没有身份时 fail-closed，不写共享 localStorage。 */
export function checklistDraftPrefix(namespace: string, wpId: string): string | null {
  return userScopedWorkpaperDraftPrefix(namespace, [wpId])
}

export function checklistDraftKey(namespace: string, wpId: string, itemId: string): string | null {
  return userScopedWorkpaperDraftKey(namespace, [wpId, itemId])
}

/** 登出是身份边界：清掉新旧两种 key 形态，避免共享浏览器留下未提交审计内容。 */
export function clearChecklistDraftsOnLogout(): void {
  if (typeof localStorage === 'undefined') return
  try {
    for (let index = localStorage.length - 1; index >= 0; index -= 1) {
      const key = localStorage.key(index)
      if (key && (
        SENSITIVE_WORKPAPER_DRAFT_KEYS.has(key)
        || SENSITIVE_WORKPAPER_DRAFT_PREFIXES.some((prefix) => key.startsWith(prefix))
      )) {
        localStorage.removeItem(key)
      }
    }
  } catch {
    // 存储不可用时没有可清理的浏览器侧草稿。
  }
}