/**
 * 试算平衡表改审定数 → 调整分录草稿（spec citar-table-manual-edit R2，用户 2026-11-04 选方案 A）。
 * 纯函数：差额（借正贷负）> 0 借本科目贷对方，< 0 反之；不直接改试算表，草稿批准后才进试算表。
 */

export interface TbAdjustDraftInput {
  code: string
  name: string
  /** 当前审定数（借正贷负） */
  current: number
  /** 目标审定数（借正贷负） */
  target: number
  counterCode: string
  counterName: string
  description: string
}

export interface TbAdjustLine {
  standard_account_code: string
  account_name?: string
  debit_amount: number
  credit_amount: number
}

/** 借正贷负的差额，两位小数（避免浮点尾差生成 0.01 分录） */
export function adjustmentDelta(current: number, target: number): number {
  return Math.round((target - current) * 100) / 100
}

/** 生成调整分录的两行；差额为 0 或对方科目与本科目相同返回错误文案 */
export function buildTbAdjustLines(input: TbAdjustDraftInput): { lines: TbAdjustLine[]; error: string } {
  const delta = adjustmentDelta(input.current, input.target)
  if (Math.abs(delta) < 0.005) return { lines: [], error: '目标金额与当前审定数相同，无需调整' }
  const counter = input.counterCode.trim()
  if (!counter) return { lines: [], error: '请填写对方科目' }
  if (counter === input.code) return { lines: [], error: '对方科目不能与本科目相同' }
  const amount = Math.abs(delta)
  const self: TbAdjustLine = {
    standard_account_code: input.code,
    account_name: input.name || undefined,
    debit_amount: delta > 0 ? amount : 0,
    credit_amount: delta > 0 ? 0 : amount,
  }
  const other: TbAdjustLine = {
    standard_account_code: counter,
    account_name: input.counterName.trim() || undefined,
    debit_amount: delta > 0 ? 0 : amount,
    credit_amount: delta > 0 ? amount : 0,
  }
  return { lines: [self, other], error: '' }
}

/** 方向 + 金额 → 借正贷负 */
export function signedOf(direction: '借' | '贷', amount: number): number {
  return direction === '贷' ? -Math.abs(amount) : Math.abs(amount)
}
