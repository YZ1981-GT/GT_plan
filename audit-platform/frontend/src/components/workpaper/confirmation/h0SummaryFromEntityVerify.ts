/**
 * h0SummaryFromEntityVerify.ts — H0-1 ← H0-2 带入映射（声明式纯函数）
 *
 * 源模板 `函证结果汇总表H0-1` 的 **七条 VLOOKUP**（逐格实证，`data_only=False`）：
 *
 * | H0-1 列 | 公式（R8 行）                                                  | col_index | H0-2 列 |
 * |---------|----------------------------------------------------------------|-----------|---------|
 * | D       | `VLOOKUP(B8,'核实被函证单位信息H0-2'!A:AL,2,0)`                 | 2         | B 被询证单位全称 |
 * | G       | `VLOOKUP(...,3,0)`                                             | 3         | C 函证方式 |
 * | J       | `VLOOKUP(...,4,0)`                                             | 4         | D 收件地址 |
 * | K       | `VLOOKUP(...,10,0)`                                            | 10        | J 发函地址与企查查地址是否一致 |
 * | M       | `VLOOKUP(...,16,0)`                                            | 16        | P 回函方式 |
 * | Q       | `VLOOKUP(...,19,0)`                                            | 19        | S 回函发出地址（含物流信息中的地址） |
 * | R       | `VLOOKUP(...,22,0)`                                            | 22        | V 发函地址与回函地址是否一致 |
 *
 * `lookup_value` 是 **B 列（询证函索引号）** → 带入匹配键必须用索引号，空索引号行跳过。
 *
 * 改造前平台无此联动（全库 grep 零命中）→ 这 7 列信息要在 H0-1 与 H0-2 各录一遍。
 *
 * 守卫：`backend/tests/test_h0_source_template_facts.py` 以 xlsx 为裁决者
 * 逐条比对 `sourceColumnIndex` 与 H0-2 目标列语义（Property 14）。
 *
 * spec: .kiro/specs/h0-confirmation-source-fidelity-and-linkage/
 *       Requirements 5.1~5.6；Property 14 / 15
 */

import type { ConfirmationRow } from './confirmationTypes'
import type { EntityVerifyRow } from './entityVerify/entityVerifyTypes'

// ─── 声明式映射 ──────────────────────────────────────────────────────────────

export interface H0PullFieldSpec {
  /** H0-1 列 key（`ConfirmationRow` 字段） */
  targetKey: keyof ConfirmationRow & string
  /** 源模板 H0-1 列字母 */
  targetColumn: string
  /** H0-2 字段（`EntityVerifyRow`） */
  sourceField: keyof EntityVerifyRow & string
  /** 源模板 H0-2 列字母 */
  sourceColumn: string
  /** 源模板 VLOOKUP 的 col_index_num（守卫据此与 xlsx 交叉锁死） */
  sourceColumnIndex: number
  /** 列中文名（toast / 未匹配提示用） */
  label: string
}

export const H0_PULL_FROM_ENTITY_VERIFY: readonly H0PullFieldSpec[] = [
  {
    targetKey: 'entity_name',
    targetColumn: 'D',
    sourceField: 'entity_name',
    sourceColumn: 'B',
    sourceColumnIndex: 2,
    label: '被询证单位名称',
  },
  {
    // 🔴 源模板「函证方式」是**发函渠道**，平台对应字段是 `send_channel`
    //    （不是承载积极式/消极式的 `confirmation_method`）
    targetKey: 'send_channel',
    targetColumn: 'G',
    sourceField: 'first_send_method',
    sourceColumn: 'C',
    sourceColumnIndex: 3,
    label: '函证方式',
  },
  {
    targetKey: 'entity_address',
    targetColumn: 'J',
    sourceField: 'entity_address',
    sourceColumn: 'D',
    sourceColumnIndex: 4,
    label: '收件地址',
  },
  {
    targetKey: 'send_addr_match',
    targetColumn: 'K',
    sourceField: 'address_match',
    sourceColumn: 'J',
    sourceColumnIndex: 10,
    label: '地址核查是否一致',
  },
  {
    targetKey: 'reply_method',
    targetColumn: 'M',
    sourceField: 'reply_method',
    sourceColumn: 'P',
    sourceColumnIndex: 16,
    label: '回函方式',
  },
  {
    targetKey: 'reply_from_addr',
    targetColumn: 'Q',
    sourceField: 'reply_from_addr',
    sourceColumn: 'S',
    sourceColumnIndex: 19,
    label: '回函发出地址',
  },
  {
    targetKey: 'send_reply_addr_match',
    targetColumn: 'R',
    sourceField: 'reply_addr_match',
    sourceColumn: 'V',
    sourceColumnIndex: 22,
    label: '发函地址与回函地址是否一致',
  },
]

// ─── 结果结构 ────────────────────────────────────────────────────────────────

export type H0PullMode = 'fill_blank' | 'overwrite'

export interface H0PullResult {
  /** 命中并实际写入的行数 */
  matched: number
  /** 命中但无任何字段被改写的行数（`fill_blank` 下已填满） */
  untouched: number
  /** 索引号为空/空白被跳过的行数 */
  skippedNoIndex: number
  /** 在 H0-2 找不到对应索引号的清单（去重保序） */
  unmatchedIndexes: string[]
  /** 实际被改写的行 id */
  updatedRowIds: string[]
  /** 逐字段写入计数（供 toast 明细） */
  fieldWrites: Record<string, number>
}

// ─── 工具 ────────────────────────────────────────────────────────────────────

function normIndex(v: unknown): string {
  return String(v ?? '').trim()
}

/** 空值判定：`undefined`/`null`/空白字符串视为空；`0`/`false` **不**算空 */
function isBlank(v: unknown): boolean {
  if (v === undefined || v === null) return true
  if (typeof v === 'string') return v.trim() === ''
  return false
}

/** 一致性枚举 → 源模板「是/否」用语（H0-1 的 K/R 列是 是/否，H0-2 是三态枚举） */
function toYesNo(v: unknown): string | undefined {
  if (v === 'consistent') return '是'
  if (v === 'inconsistent') return '否'
  if (v === 'pending') return undefined // 待核实 → 不带入（宁缺勿造）
  if (isBlank(v)) return undefined
  return String(v)
}

/** 取 H0-2 某字段的可带入值（做必要的口径转换；返回 undefined = 不带入） */
export function resolvePullValue(spec: H0PullFieldSpec, row: EntityVerifyRow): string | undefined {
  const raw = (row as Record<string, unknown>)[spec.sourceField]
  if (spec.targetKey === 'send_addr_match' || spec.targetKey === 'send_reply_addr_match') {
    return toYesNo(raw)
  }
  if (isBlank(raw)) return undefined
  return String(raw).trim()
}

/** 建 H0-2 索引号 → 行 的查找表（同索引号取**首条**，与 VLOOKUP 语义一致） */
export function buildEntityIndex(
  entityRows: readonly EntityVerifyRow[],
): Map<string, EntityVerifyRow> {
  const map = new Map<string, EntityVerifyRow>()
  for (const r of entityRows) {
    const key = normIndex(r.confirm_index)
    if (!key) continue
    if (!map.has(key)) map.set(key, r) // VLOOKUP 取首个匹配
  }
  return map
}

// ─── 主函数 ──────────────────────────────────────────────────────────────────

/**
 * 按源模板 VLOOKUP 关系从 H0-2 带入 7 列到 H0-1。
 *
 * 契约（R5.2~5.5 / Property 15）：
 * - 匹配键 = 询证函索引号；空索引号行**跳过且不修改**
 * - `mode='fill_blank'`：只补空值，已填值不被覆盖（手工优先）
 * - `mode='overwrite'`：覆盖全部（但源侧为空仍不写，不会把已有值清空）
 * - **幂等**：连续两次调用结果一致
 * - 就地修改传入的 `summaryRows`（调用方负责持久化）
 */
export function pullH0SummaryFromEntityVerify(input: {
  summaryRows: ConfirmationRow[]
  entityRows: readonly EntityVerifyRow[]
  mode: H0PullMode
}): H0PullResult {
  const { summaryRows, entityRows, mode } = input
  const index = buildEntityIndex(entityRows)

  const result: H0PullResult = {
    matched: 0,
    untouched: 0,
    skippedNoIndex: 0,
    unmatchedIndexes: [],
    updatedRowIds: [],
    fieldWrites: {},
  }
  const seenUnmatched = new Set<string>()

  for (const row of summaryRows) {
    const key = normIndex(row.confirm_index)
    if (!key) {
      result.skippedNoIndex += 1
      continue
    }
    const src = index.get(key)
    if (!src) {
      if (!seenUnmatched.has(key)) {
        seenUnmatched.add(key)
        result.unmatchedIndexes.push(key)
      }
      continue
    }

    let changed = false
    for (const spec of H0_PULL_FROM_ENTITY_VERIFY) {
      const value = resolvePullValue(spec, src)
      if (value === undefined) continue

      const current = (row as Record<string, unknown>)[spec.targetKey]
      if (mode === 'fill_blank' && !isBlank(current)) continue
      if (String(current ?? '') === value) continue

      ;(row as Record<string, unknown>)[spec.targetKey] = value
      result.fieldWrites[spec.label] = (result.fieldWrites[spec.label] ?? 0) + 1
      changed = true
    }

    if (changed) {
      result.matched += 1
      if (row._row_id) result.updatedRowIds.push(row._row_id)
    } else {
      result.untouched += 1
    }
  }

  return result
}

/** 结果摘要文案（toast） */
export function describeH0PullResult(r: H0PullResult): string {
  const parts = [`已带入 ${r.matched} 行`]
  if (r.untouched) parts.push(`无需更新 ${r.untouched} 行`)
  if (r.skippedNoIndex) parts.push(`跳过 ${r.skippedNoIndex} 行（无询证函索引号）`)
  if (r.unmatchedIndexes.length) {
    const head = r.unmatchedIndexes.slice(0, 5).join('、')
    const more = r.unmatchedIndexes.length > 5 ? ` 等 ${r.unmatchedIndexes.length} 个` : ''
    parts.push(`H0-2 未找到：${head}${more}`)
  }
  return parts.join('；')
}
