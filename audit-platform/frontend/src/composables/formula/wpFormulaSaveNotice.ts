/**
 * 底稿公式保存回执 → 提示文案（spec formula-governance-coverage-closure R6.3 / R5 走查）。
 *
 * 后端 `PUT /api/workpapers/{id}/formulas` 求值有错（取不到数、写法无法识别 …）时只回 `eval_warnings`、
 * 不回 `evaluated_value`，格子留空。提示必须写明原因：只说「公式已保存」或只报告警条数，
 * 用户看不出格子为什么是空的（R5 走查：公式管理中心保存后一律提示「公式已保存」）。
 */

export interface WpFormulaSaveReceipt {
  evaluated_value?: string | number | null
  eval_warnings?: string[] | null
  /** 保存后的公式行（`definition_version` 在这一层，不在回执顶层） */
  saved?: { definition_version?: number | null } | null
}

/**
 * 回执里保存后的定义版本。同一条公式再次保存要用它作 `expected_version`（CAS）：
 * 原先公式管理中心读回执顶层的 `definition_version`（恒取不到），同一行第二次保存必 409「已被他人修改」（R5 走查实测）。
 */
export function savedDefinitionVersion(receipt: WpFormulaSaveReceipt | null | undefined): number | null {
  const v = receipt?.saved?.definition_version
  return typeof v === 'number' ? v : null
}

export interface WpFormulaSaveNotice {
  level: 'success' | 'warning'
  text: string
  /** 求值有错的原因（原样，供调用方汇总） */
  warnings: string[]
}

/** 单条保存的提示；`cell` 为目标单元格（可空）。原因最多列 2 条，其余给条数。 */
export function wpFormulaSaveNotice(
  receipt: WpFormulaSaveReceipt | null | undefined,
  cell = '',
): WpFormulaSaveNotice {
  const warnings = (receipt?.eval_warnings || []).map((w) => String(w || '').trim()).filter(Boolean)
  const at = cell ? ` ${cell} ` : ''
  if (warnings.length) {
    const more = warnings.length > 2 ? `（另有 ${warnings.length - 2} 条）` : ''
    return {
      level: 'warning',
      text: `公式已保存，但${at}没有算出值（已留空）：${warnings.slice(0, 2).join('；')}${more}`,
      warnings,
    }
  }
  const value = receipt?.evaluated_value
  if (value !== null && value !== undefined && String(value) !== '') {
    return { level: 'success', text: `公式已保存，${cell ? `${cell} = ` : '结果 '}${value}`, warnings }
  }
  return { level: 'success', text: '公式已保存', warnings }
}

/** 批量逐条保存后的汇总：有算不出值的公式时列出单元格与第一条原因。 */
export function wpFormulaBatchNotice(
  savedCount: number,
  failures: ReadonlyArray<{ cell: string; warnings: string[] }>,
  suffix = '',
): WpFormulaSaveNotice {
  const all = failures.flatMap((f) => f.warnings)
  if (!failures.length) return { level: 'success', text: `已保存 ${savedCount} 个公式${suffix}`, warnings: [] }
  const shown = failures.slice(0, 2).map((f) => `${f.cell}：${f.warnings[0]}`).join('；')
  const more = failures.length > 2 ? `（另有 ${failures.length - 2} 个）` : ''
  return {
    level: 'warning',
    text: `已保存 ${savedCount} 个公式${suffix}；其中 ${failures.length} 个没有算出值（已留空）：${shown}${more}`,
    warnings: all,
  }
}
