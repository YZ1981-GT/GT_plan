/**
 * J1 / H4 披露 columns 契约（批 3 / 批 4 收口）
 *
 * J1：3 张表共用 5 列单行表头。`flat: true` 是**必需**的 ——「本期增加」「本期减少」
 * 共享前缀「本期」，后端 `_infer_groups_from_headers` 会反猜出源模板不存在的
 * 「本期」父表头（与 F2 房企 3 表同款缺陷）。
 *
 * H4：推的是 H2 章节（五、23）里的子表，列头必须**复用 H2 的定义**，
 * 两处各造一份必然分叉（附注列头随最后一次同步跳变）。
 *
 * spec: .kiro/specs/disclosure-columns-coverage-rollout/ R1 / R3（Task 7 / Task 8）
 */
import { describe, expect, it } from 'vitest'
import {
  J1_SUB_TABLE_KEYS,
  buildJ1SyncPayload,
  j1MovementColumns,
} from '../j1NoteSectionMap'
import { buildH4ListedSyncPayloads } from '../h4DisclosureSyncPayload'
import { buildH2ListedColumns } from '../h2DisclosureSyncPayload'
import { H2_LISTED_SUBTABLE } from '../h2NoteSectionMap'

const dataKeys = (sub: Record<string, unknown>): string[] =>
  Object.keys(sub).filter((k) => !k.startsWith('_')).sort()

// ─── J1 ──────────────────────────────────────────────────────────────────────

function j1Snapshot() {
  const rows = [
    { label: '工资、奖金、津贴和补贴', begin: 100, increase: 500, decrease: 480, end: 120 },
  ] as never
  return { summary: rows, shortTerm: rows, postEmployment: rows, notes: {} } as never
}

describe('J1 应付职工薪酬披露 columns 契约', () => {
  it('5 列取附注模板口径（「期初余额」而非组件的「上年年末数」）', () => {
    expect(j1MovementColumns().map((c) => c.label)).toEqual([
      '项目', '期初余额', '本期增加', '本期减少', '期末余额',
    ])
  })

  it('🔴 标签列标 flat，抑制凭空「本期」父表头；全表 0 处 group', () => {
    const cols = j1MovementColumns()
    expect(cols.some((c) => c.flat === true), '未声明 flat → 后端会反猜「本期」父表头').toBe(true)
    expect(cols.filter((c) => c.group !== undefined)).toHaveLength(0)
  })

  it('4 个金额列标 format: amount（标签列不标）', () => {
    const cols = j1MovementColumns()
    expect(cols[0].format).toBeUndefined()
    expect(cols.slice(1).map((c) => c.format)).toEqual(['amount', 'amount', 'amount', 'amount'])
  })

  it('Property 2：恰好 1 个 is_label 且居首', () => {
    const cols = j1MovementColumns()
    expect(cols.filter((c) => c.is_label === true)).toHaveLength(1)
    expect(cols[0].is_label).toBe(true)
  })

  it('Property 6：无英文/snake_case 键泄漏为列头', () => {
    for (const c of j1MovementColumns()) {
      expect(c.label.trim()).not.toBe('')
      expect(/^[a-z_]+$/.test(c.label)).toBe(false)
    }
  })

  it.each(['listed', 'soe'] as const)(
    'Property 1（%s）：columns 键 ≡ sub_table_data 数据键（3 张表）',
    (variant) => {
      const { body } = buildJ1SyncPayload({
        variant,
        wpId: 'wp-j1',
        year: 2025,
        snapshot: j1Snapshot(),
        applicableStandards: [variant === 'listed' ? 'listed_standalone' : 'soe_standalone'],
      })
      const p = body as unknown as {
        sub_table_data: Record<string, unknown>
        columns: Record<string, unknown>
      }
      const keys = dataKeys(p.sub_table_data)
      expect(keys).toHaveLength(3)
      expect(Object.keys(p.columns).sort()).toEqual(keys)
      // 三张表用同一份列定义（附注模板 headers 三表相同）
      const expected = Object.values(J1_SUB_TABLE_KEYS[variant]).sort()
      expect(keys).toEqual(expected)
    },
  )
})

// ─── H4 ──────────────────────────────────────────────────────────────────────

const MATERIALS: never[] = [] as never[]

function h4Materials() {
  return [
    { label: '专用材料', endBalance: 300, priorBalance: 200 },
    { label: '减：工程物资减值准备', endBalance: 20, priorBalance: 10, isDeduction: true },
  ] as never
}

describe('H4 工程物资披露 columns 契约', () => {
  it('columns 复用 H2 上市列头，不另造（同一张表两处写）', () => {
    const [p] = buildH4ListedSyncPayloads('wp-h4', ['listed_standalone'], {
      materials: h4Materials(),
    })
    const matKey = H2_LISTED_SUBTABLE.materials
    expect(p.columns?.[matKey]).toBe(buildH2ListedColumns()[matKey])
  })

  it('Property 1：columns 键 ≡ sub_table_data 数据键（仅推工程物资时）', () => {
    const [p] = buildH4ListedSyncPayloads('wp-h4', ['listed_standalone'], {
      materials: h4Materials(),
      noteText: '工程物资系专用材料',
    })
    expect(dataKeys(p.sub_table_data)).toEqual([H2_LISTED_SUBTABLE.materials])
    expect(Object.keys(p.columns ?? {}).sort()).toEqual(dataKeys(p.sub_table_data))
    // `_note_texts` 是元数据键，不参与配对
    expect((p.sub_table_data as Record<string, unknown>)._note_texts).toBeDefined()
  })

  it('Property 1：顺带勾稽 H2 汇总表时，两张表都带列头', () => {
    const [p] = buildH4ListedSyncPayloads(
      'wp-h4',
      ['listed_standalone'],
      { materials: h4Materials() },
      {
        existingSubTableData: {
          [H2_LISTED_SUBTABLE.summary]: [{ label: '工程物资', end_balance: 0, prior_balance: 0 }],
        },
      },
    )
    const keys = dataKeys(p.sub_table_data)
    expect(keys).toEqual([H2_LISTED_SUBTABLE.materials, H2_LISTED_SUBTABLE.summary].sort())
    expect(Object.keys(p.columns ?? {}).sort()).toEqual(keys)
  })

  it('宁缺勿造：未知子表键不臆造列头（由守卫/契约暴露而非静默补一份）', () => {
    const [p] = buildH4ListedSyncPayloads(
      'wp-h4',
      ['listed_standalone'],
      { materials: h4Materials() },
      { existingSubTableData: { 某个未登记的表: [{ label: 'x' }] } },
    )
    expect(Object.keys(p.columns ?? {})).not.toContain('某个未登记的表')
  })

  it('行键与列头 key 对齐（投影器按 row[colDef.key] 取值）', () => {
    const [p] = buildH4ListedSyncPayloads('wp-h4', ['listed_standalone'], {
      materials: h4Materials(),
    })
    const matKey = H2_LISTED_SUBTABLE.materials
    const defs = p.columns![matKey]
    const rows = p.sub_table_data[matKey]
    expect(defs.map((d) => d.key)).toEqual(['label', 'end_balance', 'prior_balance'])
    for (const r of rows) {
      for (const d of defs) expect(Object.prototype.hasOwnProperty.call(r, d.key)).toBe(true)
    }
  })

  it('不适用准则时不产出载荷（也就没有 columns 漂移风险）', () => {
    expect(buildH4ListedSyncPayloads('wp-h4', ['soe_standalone'], { materials: MATERIALS })).toEqual([])
  })
})
