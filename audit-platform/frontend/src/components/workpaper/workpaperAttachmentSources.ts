/**
 * 底稿关联附件 — 统一反查来源标注
 * spec: attachment-workpaper-linkage-convergence Task 3.2
 */

export type AttachmentSourceKey = 'associated' | 'referenced' | 'confirmation' | 'evidence_link' | 'checklist'

export const SOURCE_LABEL: Record<
  AttachmentSourceKey | string,
  { label: string; type: '' | 'success' | 'warning' | 'info' | 'danger' }
> = {
  associated: { label: '关联证据', type: 'success' },
  referenced: { label: '底稿引用', type: 'info' },
  confirmation: { label: '函证回函', type: 'warning' },
  /** 只挂在某一行 / 单元格上的证据（spec attachment-evidence-intake ADR-AEI-02） */
  evidence_link: { label: '行级证据', type: '' },
  checklist: { label: '检查项证据', type: '' },
}

export function resolveSourceKeys(
  row: { source?: string; sources?: string[] } | null | undefined,
): string[] {
  if (!row) return []
  if (Array.isArray(row.sources) && row.sources.length) return row.sources
  if (row.source) return [row.source]
  return []
}

/**
 * 权威链表 / reference / 行级证据链接可解除（解除 = 本底稿的整稿关联与各行链接一并解除）；
 * 纯函证只读链路不提供解除（不改函证编制）。
 */
export function canUnlinkSources(sources: string[]): boolean {
  return sources.includes('associated') || sources.includes('referenced') || sources.includes('evidence_link')
}
