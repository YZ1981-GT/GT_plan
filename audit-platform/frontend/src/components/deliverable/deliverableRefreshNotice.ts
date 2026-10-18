/**
 * 交付件章节增量刷新：确认文案与结果提示（纯函数，供 LineagePanel 使用）
 *
 * Spec: deliverable-trio-generation-accuracy Task 16b（design §7.2）
 *
 * 刷新 = 按最新源数据同口径重新导出，再把目标章节整块换进交付件**已保存的最新版本**，另存为新版本。
 * 后端返回 RefreshResult：version_no（落了新版本才有）/ refreshed / skipped / requires_confirm /
 * pending_confirm_sections / messages（跳过原因、出具章节集合变化，后端已写成中文）。
 * 🔴 原前端不看返回值，跳过、未执行也一律提示「已刷新」。
 */

export interface DeliverableRefreshResult {
  version_no: number | null
  refreshed: string[]
  skipped: string[]
  requires_confirm: boolean
  pending_confirm_sections: string[]
  messages: string[]
}

export interface RefreshNotice {
  /** success / info 用轻提示；warning 逐条列出（跳过原因、提醒） */
  kind: 'success' | 'info' | 'warning'
  title: string
  lines: string[]
}

/** 章节号缩写：最多列 6 个，其余「等 N 节」（与后端 `_head` 同口径） */
export function headCodes(codes: string[], limit = 6): string {
  const shown = codes.slice(0, limit).join('、')
  return codes.length > limit ? `${shown} 等 ${codes.length} 节` : shown
}

const BASE_NOTE = '刷新以已保存的最新版本为底，在线编辑中尚未保存的修改不包含在内。'

/** 「刷新本章节」确认文案 */
export function sectionRefreshPrompt(code: string): string {
  return (
    `将按最新源数据重新生成「${code}」，替换交付件中该节的标题、表格与正文，结果另存为新版本，其余章节保持不变。`
    + `${BASE_NOTE}是否继续？`
  )
}

/** 「刷新所有过期」确认文案；staleCount 未知（章节状态没取到）时不写节数 */
export function staleRefreshPrompt(staleCount: number | null): string {
  const scope = staleCount ? `全部过期章节（共 ${staleCount} 节）` : '全部过期章节'
  return (
    `将按最新源数据重新生成${scope}，替换交付件中对应各节的标题、表格与正文，结果另存为一个新版本，未过期章节保持不变。`
    + `${BASE_NOTE}是否继续？`
  )
}

/** 后端检测到人工修改（requires_confirm）时的二次确认文案 */
export function overwritePrompt(codes: string[]): string {
  const what = codes.length === 1
    ? `「${codes[0]}」在交付件中`
    : `以下 ${codes.length} 节在交付件中（${headCodes(codes)}）`
  return `${what}有手动修改（与上次生成或刷新时的内容不同），刷新会覆盖这些修改。是否仍要刷新？`
}

/** 在线编辑本次会话已有修改时拒绝刷新的说明 */
export const UNSAVED_EDITS_MESSAGE =
  '本次在线编辑有修改尚未保存回交付件（关闭编辑器后才会另存为新版本）。现在刷新会以修改前的版本为底，'
  + '之后保存的编辑又会覆盖刷新结果。请先关闭编辑器，待交付中心出现新版本后再打开刷新。'

/** 刷新结果 → 提示 */
export function summarizeRefresh(res: Partial<DeliverableRefreshResult> | null | undefined): RefreshNotice {
  const refreshed = res?.refreshed ?? []
  const skipped = res?.skipped ?? []
  const messages = res?.messages ?? []
  const versionNo = res?.version_no ?? null

  if (versionNo !== null && refreshed.length > 0) {
    const head = `已刷新 ${refreshed.length} 节（${headCodes(refreshed)}），已另存为第 ${versionNo} 版`
    if (!messages.length) return { kind: 'success', title: '刷新完成', lines: [head] }
    return {
      kind: 'warning',
      title: skipped.length ? '刷新完成，部分章节未刷新' : '刷新完成，请留意以下提醒',
      lines: [head, ...messages],
    }
  }
  if (skipped.length || messages.length) {
    return {
      kind: 'warning',
      title: '未刷新',
      lines: messages.length ? messages : [`${skipped.length} 节未刷新（${headCodes(skipped)}）`],
    }
  }
  return { kind: 'info', title: '无需刷新', lines: ['没有需要刷新的过期章节'] }
}
