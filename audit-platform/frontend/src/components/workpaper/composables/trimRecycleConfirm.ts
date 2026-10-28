/**
 * 粗裁保存前确认：已生成的底稿将移入回收站 / 从回收站恢复。
 *
 * spec procedure-trim-generation-delegation-chain 需求 3.2：裁剪预览（`POST /procedure-trim/preview`）回报
 * `recycle_preview`（被裁的已生成底稿、其中有编制内容的、恢复执行要从回收站恢复的）。保存前列出并二次确认；
 * 用户确认过有编制内容的底稿时，apply 带 `confirm_substantive_recycle: true`（否则后端 409、零副作用）。
 */
import { h } from 'vue'
import { ElMessageBox } from 'element-plus'

export interface RecycleSubstantiveItem {
  wp_code: string
  wp_name?: string
  substantive_reasons?: string[]
}

export interface TrimRecyclePreview {
  to_recycle?: string[]
  substantive?: RecycleSubstantiveItem[]
  to_restore?: string[]
  to_reopen_tasks?: number
}

/** `none` = 无需确认；`confirmed` = 用户确认；`cancel` = 用户取消（调用方不得继续 apply） */
export type TrimRecycleDecision = 'none' | 'confirmed' | 'cancel'

export const SUBSTANTIVE_UNCONFIRMED = 'substantive_recycle_unconfirmed'

const MAX_LISTED = 10

function listCodes(codes: string[]): string {
  const shown = codes.slice(0, MAX_LISTED).join('、')
  return codes.length > MAX_LISTED ? `${shown} 等` : shown
}

/** 确认框正文（纯函数，便于测试）。 */
export function recycleSummaryLines(rp: TrimRecyclePreview | null | undefined): string[] {
  const toRecycle = rp?.to_recycle ?? []
  const substantive = rp?.substantive ?? []
  const toRestore = rp?.to_restore ?? []
  const lines: string[] = []
  if (toRecycle.length) {
    lines.push(`${toRecycle.length} 张已生成的底稿将移入回收站（可从回收站恢复）：${listCodes(toRecycle)}`)
  }
  if (substantive.length) {
    lines.push(`其中 ${substantive.length} 张已有编制内容：`)
    for (const item of substantive.slice(0, MAX_LISTED)) {
      const reasons = (item.substantive_reasons ?? []).join('、')
      lines.push(`· ${item.wp_code}${item.wp_name ? ` ${item.wp_name}` : ''}${reasons ? `（${reasons}）` : ''}`)
    }
    if (substantive.length > MAX_LISTED) lines.push(`· 另有 ${substantive.length - MAX_LISTED} 张`)
  }
  if (toRestore.length) {
    lines.push(`${toRestore.length} 张底稿将从回收站恢复：${listCodes(toRestore)}`)
  }
  return lines
}

/**
 * 有底稿要移入回收站时弹确认框。`onlySubstantive`：只在有编制内容时才问（批量智能裁剪用，结果里另行告知）。
 */
export async function confirmTrimRecycle(
  preview: { recycle_preview?: TrimRecyclePreview } | null | undefined,
  opts: { onlySubstantive?: boolean } = {},
): Promise<TrimRecycleDecision> {
  const rp = preview?.recycle_preview
  const toRecycle = rp?.to_recycle ?? []
  const substantive = rp?.substantive ?? []
  if (!toRecycle.length || (opts.onlySubstantive && !substantive.length)) return 'none'
  // h() 在渲染上下文外生成：scoped 样式匹配不到，只用内联样式
  const body = h('div', { style: 'max-height:320px;overflow:auto;line-height:1.7' },
    recycleSummaryLines(rp).map((line) => h('p', { style: 'margin:0 0 4px' }, line)))
  try {
    await ElMessageBox.confirm(body, '已生成的底稿将移入回收站', {
      type: substantive.length ? 'warning' : 'info',
      confirmButtonText: '确认保存',
      cancelButtonText: '取消',
    })
    return 'confirmed'
  } catch {
    return 'cancel'
  }
}

/** apply 回执里的去向（拼在保存成功提示后面；没有则空串）。 */
export function describeRecycleResult(result: { recycled_codes?: string[]; restored_codes?: string[] } | null | undefined): string {
  const parts: string[] = []
  const recycled = result?.recycled_codes ?? []
  const restored = result?.restored_codes ?? []
  if (recycled.length) parts.push(`${recycled.length} 张已生成底稿已移入回收站`)
  if (restored.length) parts.push(`${restored.length} 张底稿已从回收站恢复`)
  return parts.length ? `；${parts.join('；')}` : ''
}

/** apply 409 是「有编制内容未确认」时返回后端说明，否则 null（调用方按版本冲突处理）。 */
export function trimApplyConflictMessage(e: any): string | null {
  const detail = e?.response?.data?.detail ?? e?.response?.data?.data?.detail
  return detail?.error === SUBSTANTIVE_UNCONFIRMED ? String(detail.message || '') || '有底稿已有编制内容，请确认后再保存' : null
}
