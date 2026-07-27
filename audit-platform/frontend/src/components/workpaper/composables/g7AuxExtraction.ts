/**
 * G7-2 明细表 ← 四表（辅助余额）取数：前端合并纯函数（Task 3.2）。
 *
 * 后端 `/g7/import-aux-balance` 返回成本法候选行（Partial<G7CostRow>[]）；本模块把它们
 * 按被投资单位名称归并进当前编辑态 G7DetailState 的 costRows：
 * - Persist_First：`overwrite=false` 时只填空值，已填字段逐字不变（Property 2）；
 * - overwrite=true：按名覆盖金额字段；
 * - 幂等：同一取数结果重复应用不新增行、不改已填值（Property 4）；
 * - 名称规范化（去空白/全角空格/全角括号）匹配，防重名重复行。
 *
 * 只处理 costRows；equityRows / impairmentRows 原样保留（aux 无控制类型，不臆造 relationship）。
 */
import {
  type G7CostRow,
  type G7DetailState,
  createG7CostRow,
  recalcG7CostRow,
  resequenceG7DetailState,
  syncG7ImpairmentRows,
} from './g7DetailModel'

export interface G7AuxMergeResult {
  state: G7DetailState
  added: number
  filled: number
  skipped: number
}

/** 名称规范化：去空白/全角空格/全角括号，用于去重匹配 */
export function normalizeInvesteeName(name: unknown): string {
  return String(name ?? '')
    .trim()
    .replace(/\s+/g, '')
    .replace(/　/g, '')
    .replace(/（/g, '(')
    .replace(/）/g, ')')
}

const NUM_FIELDS: Array<keyof G7CostRow> = ['openingAmount', 'increaseAmount', 'decreaseAmount']

function num(v: unknown): number {
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

/**
 * 把 aux 成本法候选行并入 detail state 的 costRows。
 *
 * @param state 当前编辑态（会被就地更新并返回同一引用）
 * @param incoming 后端返回的成本法候选行
 * @param opts.overwrite 是否覆盖已填金额字段
 */
export function mergeAuxRowsIntoDetail(
  state: G7DetailState,
  incoming: Array<Partial<G7CostRow>>,
  opts: { overwrite: boolean },
): G7AuxMergeResult {
  let added = 0
  let filled = 0
  let skipped = 0

  const byName = new Map<string, G7CostRow>()
  for (const row of state.costRows) {
    byName.set(normalizeInvesteeName(row.investeeName), row)
  }

  for (const inc of incoming) {
    const key = normalizeInvesteeName(inc.investeeName)
    if (!key) continue
    const existing = byName.get(key)
    if (existing) {
      let touched = false
      for (const f of NUM_FIELDS) {
        const incVal = num(inc[f])
        if (opts.overwrite) {
          if (num(existing[f]) !== incVal && Math.abs(incVal) > 1e-9) {
            ;(existing as any)[f] = incVal
            touched = true
          }
        } else if (num(existing[f]) === 0 && Math.abs(incVal) > 1e-9) {
          // Persist_First：仅填空值
          ;(existing as any)[f] = incVal
          touched = true
        }
      }
      // 仅补空来源串
      if (!existing.remark && inc.remark) {
        existing.remark = inc.remark
        touched = true
      }
      if (touched) {
        recalcG7CostRow(existing)
        filled++
      } else {
        skipped++
      }
    } else {
      const row = createG7CostRow(state.costRows.length + 1, String(inc.investeeName ?? ''))
      Object.assign(row, inc)
      row.section = 'cost'
      row.investeeName = String(inc.investeeName ?? '')
      recalcG7CostRow(row)
      state.costRows.push(row)
      byName.set(key, row)
      added++
    }
  }

  resequenceG7DetailState(state)
  syncG7ImpairmentRows(state)
  return { state, added, filled, skipped }
}
