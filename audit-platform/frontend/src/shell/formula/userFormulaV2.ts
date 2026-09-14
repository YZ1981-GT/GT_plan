/**
 * Frontend mirror of user formula v2 command shapes (Task 8).
 */

export const USER_FORMULA_V2_COMMAND_VERSION = '2.0' as const

export type UserFormulaV2Action = 'create' | 'update' | 'delete' | 'restore'

export interface UserFormulaV2Command {
  commandVersion: typeof USER_FORMULA_V2_COMMAND_VERSION
  clientItemId: string
  operationId?: string
  action: UserFormulaV2Action
  formulaId: string | null
  location: unknown
  target: {
    addrId: string | null
    fieldKey: string | null
    rowKey: string | null
    columnKey: string | null
    a1: string | null
  }
  formulaFunction: string | null
  ruleCategory: string
  expression: string | null
  refs: string[]
  baseVersion: string | null
  reason: string
}

export interface UserFormulaV2BatchResult {
  overallStatus: 'success' | 'partial' | 'failed'
  operationId: string
  items: Array<{
    clientItemId: string
    status: 'success' | 'conflict' | 'forbidden' | 'invalid' | 'error'
    formulaId: string | null
    serverVersion: string | null
    fieldConflicts: Array<{
      field: string
      base: unknown
      current: unknown
      incoming: unknown
    }>
    errorCode: string | null
    draftRetained?: boolean
  }>
  committed?: boolean
}

/** Guard: formulaFunction and ruleCategory must remain separate. */
export function assertFunctionCategorySplit(cmd: {
  formulaFunction: string | null
  ruleCategory: string
  formula_type?: unknown
}): { ok: true } | { ok: false; reasonCode: string } {
  if ('formula_type' in cmd && cmd.formula_type !== undefined) {
    return { ok: false, reasonCode: 'formula_type_dual_sense_forbidden' }
  }
  if (
    cmd.formulaFunction &&
    cmd.formulaFunction === cmd.ruleCategory &&
    ['auto_calc', 'logic_check', 'reasonability'].includes(cmd.formulaFunction)
  ) {
    return { ok: false, reasonCode: 'function_category_collapsed' }
  }
  return { ok: true }
}
