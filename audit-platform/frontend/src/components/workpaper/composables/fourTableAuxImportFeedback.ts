/**
 * fourTableAuxImportFeedback — 四表库「从余额表导入」端点响应的**单一真源**解析 + reason 码提示映射.
 *
 * 背景（spec four-table-extraction-entry-completion / Task 3 + Task 7）：
 * 迁移后的 aux 取数端点（K1 / D2~D7）统一走共享件 `aggregate_aux_by_name_ex`，
 * 响应经 `ResponseWrapperMiddleware` 包装后前端从 `response.data` 读业务载荷，携带：
 *   - `reason`：ok / no_prefixes / no_aux_type / no_rows / no_active_dataset / error
 *   - `imported_count`：本次新增行数（merge 语义，已有业务键不重复导入）
 *   - `message`：后端产出的自然语言提示（可选，作兜底）
 *   - `selected_aux_type`：命中的单一 aux_type（可选，供追溯）
 *
 * 🔴 禁止各循环各写一份 reason→文案映射（否则口径漂移）：所有宿主的
 * 「从余额表导入」结果提示都从这里取，reason 码是唯一真源。
 *
 * Requirements: 4.4（0 行按 reason 码给可辨别中文提示）/ 5.2（reason 码分辨"接线错误"与"真无数据"）
 */

/** 后端 aux 取数端点返回的 reason 枚举（与 `AuxAggregationResult.reason` 对齐）。 */
export type AuxImportReason =
  | 'ok'
  | 'no_prefixes'
  | 'no_aux_type'
  | 'no_rows'
  | 'no_active_dataset'
  | 'error'

/** 从端点响应解析出的规范化结果。 */
export interface AuxImportOutcome {
  /** 本次新增行数（merge 后追加的行）。 */
  importedCount: number
  /** reason 码；后端未返回时为 undefined（旧端点兼容）。 */
  reason?: AuxImportReason
  /** 命中的单一 aux_type（可选）。 */
  selectedAuxType?: string
  /** 后端 message（可选，作提示兜底）。 */
  message?: string
  /** 总行数（merge 后，可选）。 */
  totalRows?: number
}

/** 提示级别，供 UI 决定用 success / info / warning / error。 */
export type AuxImportPromptLevel = 'success' | 'info' | 'warning' | 'error'

export interface AuxImportPrompt {
  level: AuxImportPromptLevel
  text: string
}

/**
 * reason → 0 行时的可辨别中文提示（Requirement 4.4）。
 * 仅在 `imported_count === 0` 时按 reason 分支；`error` 为 warning 级（区分"接线错误"与"真无数据"）。
 */
const ZERO_ROW_PROMPT: Record<AuxImportReason, AuxImportPrompt> = {
  ok: { level: 'info', text: '辅助余额已是最新，无新增往来单位' },
  no_prefixes: { level: 'warning', text: '无该科目辅助余额（未能从报表映射解析出取数科目）' },
  no_rows: { level: 'info', text: '无该科目辅助余额' },
  no_aux_type: { level: 'warning', text: '该科目未按维度挂账，无法按往来单位归集' },
  no_active_dataset: { level: 'warning', text: '数据集未激活，请先在数据集管理中激活当前年度数据' },
  error: { level: 'error', text: '取数异常，请稍后重试或联系管理员（后台已记录）' },
}

/**
 * 从 http 响应体规范化出 `AuxImportOutcome`。
 *
 * 统一读 `ResponseWrapperMiddleware` 后的 `response.data`（业务载荷可能再嵌一层 `data`），
 * 禁止各循环自行猜测包装层级（design Error Handling）。兼容旧端点（无 reason 时字段缺省）。
 */
export function parseAuxImportResponse(res: any): AuxImportOutcome {
  const data = res?.data?.data ?? res?.data ?? res ?? {}
  const reasonRaw = data?.reason
  const reason = isAuxImportReason(reasonRaw) ? reasonRaw : undefined
  return {
    importedCount: Number(data?.imported_count ?? 0) || 0,
    reason,
    selectedAuxType: data?.selected_aux_type ?? data?.aux_type ?? undefined,
    message: typeof data?.message === 'string' ? data.message : undefined,
    totalRows: data?.total_rows != null ? Number(data.total_rows) : undefined,
  }
}

function isAuxImportReason(v: unknown): v is AuxImportReason {
  return (
    v === 'ok' ||
    v === 'no_prefixes' ||
    v === 'no_aux_type' ||
    v === 'no_rows' ||
    v === 'no_active_dataset' ||
    v === 'error'
  )
}

/**
 * 由 `AuxImportOutcome` 决定要给用户的提示（success / info / warning / error）。
 *
 * 优先级：
 *  1) 导入 > 0 → success（带新增行数，若有 message 用 message 更精确）
 *  2) 导入 = 0 且有 reason → 按 reason 给可辨别提示（Requirement 4.4）
 *  3) 导入 = 0 且无 reason（旧端点）→ 用 message 兜底，再兜底通用文案
 */
export function auxImportPrompt(outcome: AuxImportOutcome): AuxImportPrompt {
  if (outcome.importedCount > 0) {
    return {
      level: 'success',
      text: outcome.message || `成功从余额表导入 ${outcome.importedCount} 行`,
    }
  }
  if (outcome.reason && outcome.reason !== 'ok') {
    // reason 提示优先；若后端同时给了更精确的 message，附带在括号里（不覆盖 reason 的可辨别性）
    const base = ZERO_ROW_PROMPT[outcome.reason]
    return base
  }
  if (outcome.reason === 'ok') {
    return ZERO_ROW_PROMPT.ok
  }
  // 旧端点无 reason：用后端 message 兜底
  return { level: 'info', text: outcome.message || '未从余额表导入新数据' }
}

/** 网络/异常兜底提示（catch 分支用，与 reason='error' 同义但用于请求本身失败）。 */
export const AUX_IMPORT_NETWORK_ERROR_PROMPT: AuxImportPrompt = {
  level: 'error',
  text: '从余额表导入失败，请稍后重试',
}
