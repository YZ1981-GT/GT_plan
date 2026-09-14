/** I5-1 ↔ I5-3 跨表导航高亮（sessionStorage，单次消费） */
const KEY_PROJECT = 'i5-highlight-project'
const KEY_FROM = 'i5-nav-from'

export function setI5NavHighlight(projectName: string, from: 'I5-1' | 'I5-3'): void {
  if (!projectName?.trim()) return
  sessionStorage.setItem(KEY_PROJECT, projectName.trim())
  sessionStorage.setItem(KEY_FROM, from)
}

export function peekI5NavHighlight(): { projectName: string; from: string } | null {
  const projectName = sessionStorage.getItem(KEY_PROJECT)
  if (!projectName) return null
  return { projectName, from: sessionStorage.getItem(KEY_FROM) || '' }
}

export function consumeI5NavHighlight(): { projectName: string; from: string } | null {
  const peeked = peekI5NavHighlight()
  sessionStorage.removeItem(KEY_PROJECT)
  sessionStorage.removeItem(KEY_FROM)
  return peeked
}
