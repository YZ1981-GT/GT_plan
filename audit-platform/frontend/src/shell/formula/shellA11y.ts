/**
 * Shell a11y helpers (formula-toolbar Task 12).
 *
 * Chinese accessible names, Escape, scroll lock, return-focus.
 * Rail and dialog must not form a dual focus trap.
 */

export type ShellFocusable =
  | 'rail-trigger'
  | 'rail-panel'
  | 'formula-outlet'
  | 'formula-dialog'
  | 'review-thread'

export const SHELL_A11Y_NAMES: Record<ShellFocusable, string> = {
  'rail-trigger': '底稿右侧能力入口',
  'rail-panel': '底稿右侧能力面板',
  'formula-outlet': '页面公式能力入口',
  'formula-dialog': '公式管理器',
  'review-thread': '底稿复核线程',
}

let scrollLockCount = 0
let previousOverflow = ''

export function acquireShellScrollLock(target: HTMLElement | Document = document): void {
  scrollLockCount += 1
  if (scrollLockCount !== 1) return
  const el = target === document ? document.body : (target as HTMLElement)
  previousOverflow = el.style.overflow
  el.style.overflow = 'hidden'
}

export function releaseShellScrollLock(target: HTMLElement | Document = document): void {
  if (scrollLockCount === 0) return
  scrollLockCount -= 1
  if (scrollLockCount > 0) return
  const el = target === document ? document.body : (target as HTMLElement)
  el.style.overflow = previousOverflow
  previousOverflow = ''
}

export function resetShellScrollLockForTests(): void {
  scrollLockCount = 0
  previousOverflow = ''
  if (typeof document !== 'undefined') document.body.style.overflow = ''
}

export interface ShellFocusSession {
  returnTarget: HTMLElement | null
  trapId: string
}

const sessions = new Map<string, ShellFocusSession>()

export function beginShellFocusSession(input: {
  trapId: string
  returnTarget: HTMLElement | null
}): void {
  // Dual trap forbidden: replacing an open trap returns focus first.
  for (const [id, session] of [...sessions.entries()]) {
    if (id === input.trapId) continue
    endShellFocusSession(id)
  }
  sessions.set(input.trapId, {
    returnTarget: input.returnTarget,
    trapId: input.trapId,
  })
}

export function endShellFocusSession(trapId: string): void {
  const session = sessions.get(trapId)
  sessions.delete(trapId)
  if (session?.returnTarget && typeof session.returnTarget.focus === 'function') {
    try {
      session.returnTarget.focus()
    } catch {
      // Element may have unmounted.
    }
  }
}

export function activeShellFocusTrapIds(): string[] {
  return [...sessions.keys()]
}

export function resetShellFocusSessionsForTests(): void {
  sessions.clear()
}

/** Escape closes the active trap; returns true when handled. */
export function handleShellEscapeKey(event: KeyboardEvent): boolean {
  if (event.key !== 'Escape') return false
  const ids = activeShellFocusTrapIds()
  if (ids.length === 0) return false
  // Close the most recently registered trap only (no dual-trap cascade).
  const id = ids[ids.length - 1]!
  endShellFocusSession(id)
  event.stopPropagation()
  event.preventDefault()
  return true
}

export function assertChineseAccessibleName(name: string | null | undefined): boolean {
  if (!name || !name.trim()) return false
  // Must contain at least one CJK character for workpaper-route chrome.
  return /[\u4e00-\u9fff]/.test(name)
}
