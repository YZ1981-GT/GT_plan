/**
 * 生成底稿接口回执 → 一条给用户看的提示（模板集生成、按编码生成、链路编排「生成底稿」步、B60 自动补附件共用）。
 *
 * 字段与后端统一回执一致（backend/app/services/wp_generation_receipt.py，spec procedure-chain-hardening-and-java-contracts R11）：
 * - `ignored_codes`：裁剪弹窗里选中、但不在所选模板集里的编码，未生成；
 * - `skipped_trimmed_codes`：已在程序裁剪中标为不执行的编码（含跟随科目的子表 / 程序表），未生成；
 * - `in_recycle_codes`：底稿在回收站中的编码（同码只能从回收站恢复），未生成；
 * - `blank_codes`：没找到底稿模板、只建了空白底稿的编码；`failures`：建行 / 落文件失败的编码（不计入新建）；
 * - `header_failures`：底稿已生成、但表头（编制单位 / 期间等）没填上的编码与原因；
 * - `existing_codes`：已有底稿、未重复生成；`header_unfilled`：请求内不填表头的入口新建的工作簿份数。
 * 前五类有任何一项就用警告提示并写明编码；后两类只是说明，不改变提示级别。
 */

export interface WorkpaperGenerateResult {
  operation_id?: string
  status?: 'succeeded' | 'partial_failed' | 'failed' | 'stale'
  created?: number
  count?: number
  ignored_codes?: string[]
  blank_codes?: string[]
  skipped_trimmed_codes?: string[]
  in_recycle_codes?: string[]
  existing_codes?: string[]
  failures?: Array<{ wp_code?: string; error?: string }>
  header_failures?: Array<{ wp_code?: string; reason?: string }>
  header_unfilled?: number
}

export interface WorkpaperGenerateNotice {
  level: 'success' | 'warning'
  message: string
}

const MAX_LISTED = 10

function listCodes(codes: string[]): string {
  const shown = codes.slice(0, MAX_LISTED).join('、')
  return codes.length > MAX_LISTED ? `${shown} 等` : shown
}

function withReason(code: string | undefined, reason: string | undefined): string {
  return reason ? `${code || '?'}（${reason}）` : code || '?'
}

export function summarizeWorkpaperGenerateResult(
  result: WorkpaperGenerateResult | null | undefined,
): WorkpaperGenerateNotice {
  const created = result?.created ?? result?.count ?? 0
  const terminalStatus = result?.status
  const parts = [terminalStatus === 'stale'
    ? '程序裁剪结果已变化，本次未发布底稿，请刷新生成计划后重试'
    : terminalStatus === 'failed'
      ? '底稿生成失败，本次未发布底稿'
      : `底稿生成完成，共创建 ${created} 份底稿`]
  const ignored = result?.ignored_codes ?? []
  const blank = result?.blank_codes ?? []
  const trimmed = result?.skipped_trimmed_codes ?? []
  const recycled = result?.in_recycle_codes ?? []
  const existing = result?.existing_codes ?? []
  const failed = (result?.failures ?? []).map((f) => withReason(f?.wp_code, f?.error))
  const headerFailed = (result?.header_failures ?? []).map((h) => withReason(h?.wp_code, h?.reason))
  const headerUnfilled = result?.header_unfilled ?? 0
  if (existing.length) {
    parts.push(`${existing.length} 个编码已有底稿，未重复生成：${listCodes(existing)}`)
  }
  if (ignored.length) {
    parts.push(`${ignored.length} 个选中的编码不在所选模板集里，未生成：${listCodes(ignored)}`)
  }
  if (trimmed.length) {
    parts.push(`${trimmed.length} 个编码已在程序裁剪中标为不执行，未生成：${listCodes(trimmed)}`)
  }
  if (recycled.length) {
    parts.push(`${recycled.length} 个编码的底稿在回收站中，请从回收站恢复：${listCodes(recycled)}`)
  }
  if (blank.length) {
    parts.push(`${blank.length} 个编码没有找到底稿模板，已建空白底稿：${listCodes(blank)}`)
  }
  if (failed.length) {
    parts.push(`${failed.length} 个编码生成失败：${listCodes(failed)}`)
  }
  if (headerFailed.length) {
    parts.push(`${headerFailed.length} 个底稿表头未填上：${listCodes(headerFailed)}`)
  }
  if (headerUnfilled > 0) {
    parts.push(`${headerUnfilled} 份底稿生成时未写入表头（编制单位、审计期间等），需在底稿文件中另行填写`)
  }
  const warn = terminalStatus === 'stale' || terminalStatus === 'failed' ||
    ignored.length || trimmed.length || recycled.length || blank.length || failed.length || headerFailed.length
  return {
    level: warn ? 'warning' : 'success',
    message: parts.join('；'),
  }
}
