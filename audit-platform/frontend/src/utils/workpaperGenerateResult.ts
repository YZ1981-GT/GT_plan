/**
 * 生成底稿接口回执 → 一条给用户看的提示（模板集生成与按编码生成两个接口共用）。
 *
 * spec formula-fetch-and-wp-generation-defect-closure R4 / R5：
 * - 模板集生成回报 `ignored_codes`（裁剪弹窗里选中、但不在所选模板集里的编码，未生成）；
 * - 按编码生成回报 `blank_codes`（没找到底稿模板、只建了空白底稿的编码）与 `failures`。
 * spec procedure-trim-generation-delegation-chain 需求 2（两个接口都回报）：
 * - `skipped_trimmed_codes`：已在程序裁剪中标为不执行的编码（含跟随科目的子表 / 程序表），未生成；
 * - `in_recycle_codes`：底稿在回收站中的编码（同码只能从回收站恢复），未生成。
 * 按编码生成另回报 `header_failures`：底稿已生成、但表头（编制单位 / 期间等）没填上的编码与原因
 * （原先失败只记服务日志，界面照报「生成完成」）。
 * 有任何一项就用警告提示并写明编码，不再一律报「生成完成」。
 */

export interface WorkpaperGenerateResult {
  created?: number
  count?: number
  ignored_codes?: string[]
  blank_codes?: string[]
  skipped_trimmed_codes?: string[]
  in_recycle_codes?: string[]
  failures?: Array<{ wp_code?: string; error?: string }>
  header_failures?: Array<{ wp_code?: string; reason?: string }>
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

export function summarizeWorkpaperGenerateResult(
  result: WorkpaperGenerateResult | null | undefined,
): WorkpaperGenerateNotice {
  const created = result?.created ?? result?.count ?? 0
  const parts = [`底稿生成完成，共创建 ${created} 份底稿`]
  const ignored = result?.ignored_codes ?? []
  const blank = result?.blank_codes ?? []
  const trimmed = result?.skipped_trimmed_codes ?? []
  const recycled = result?.in_recycle_codes ?? []
  const failed = (result?.failures ?? []).map((f) => f?.wp_code || '?')
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
  const headerFailed = (result?.header_failures ?? []).map((h) =>
    h?.reason ? `${h?.wp_code || '?'}（${h.reason}）` : h?.wp_code || '?',
  )
  if (headerFailed.length) {
    parts.push(`${headerFailed.length} 个底稿表头未填上：${listCodes(headerFailed)}`)
  }
  const warn =
    ignored.length || trimmed.length || recycled.length || blank.length || failed.length || headerFailed.length
  return {
    level: warn ? 'warning' : 'success',
    message: parts.join('；'),
  }
}
