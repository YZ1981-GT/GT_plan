/**
 * H1-12 折旧测算分支键读写
 * 优先 H1-12-{A|B|C}-rows；A 无分支键时回退 H1-12-rows。
 */
export type H12Branch = 'A' | 'B' | 'C'

type RemarkItem = { remark?: string | null } | undefined

function safeParseArr(remark: unknown): any[] {
  if (!remark) return []
  try {
    const parsed = typeof remark === 'string' ? JSON.parse(remark) : remark
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

export function resolveH12Branch(
  allResponses: Map<string, RemarkItem> | { get: (k: string) => RemarkItem },
): H12Branch {
  const raw = String(allResponses.get('H1-12-branch')?.remark || 'A').trim().toUpperCase()
  return raw === 'B' || raw === 'C' ? raw : 'A'
}

export function h12BranchRowsKey(branch: H12Branch): string {
  return `H1-12-${branch}-rows`
}

/** 读活动分支行；无分支键时 A 回退旧共享键 */
export function readH12BranchRows(
  allResponses: Map<string, RemarkItem> | { get: (k: string) => RemarkItem },
): { branch: H12Branch; itemKey: string; rows: any[] } {
  const branch = resolveH12Branch(allResponses)
  const branchKey = h12BranchRowsKey(branch)
  const branchItem = allResponses.get(branchKey)
  if (branchItem?.remark != null) {
    return { branch, itemKey: branchKey, rows: safeParseArr(branchItem.remark) }
  }
  if (branch === 'A') {
    return {
      branch,
      itemKey: 'H1-12-rows',
      rows: safeParseArr(allResponses.get('H1-12-rows')?.remark),
    }
  }
  return { branch, itemKey: branchKey, rows: [] }
}

/** 写活动分支键，并镜像 H1-12-rows（与 useH1Depreciation._persist 一致） */
export function saveH12BranchRows(
  onSave: ((itemId: string, value: any) => void) | undefined,
  branch: H12Branch,
  rows: any[],
): void {
  if (!onSave) return
  onSave(h12BranchRowsKey(branch), rows)
  onSave('H1-12-rows', rows)
}
