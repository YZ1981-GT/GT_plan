/**
 * useCNoteInheritance.spec.ts — C 类附注「子表↔主表合计联动校验」composable 单元测试
 *
 * spec: gt-c-note-table-shrink Task 3
 *
 * 验证（≥5 用例）：
 * 1. ok（绿✓）       —— source 合计 = target → status='ok' + diff=0 + label '勾稽一致'
 * 2. mismatch（红✗） —— source ≠ target + on_mismatch='error' → status='mismatch' + diff + label '差异'
 * 3. warning（黄）   —— source ≠ target + on_mismatch='warning' → status='warning'
 * 4. na             —— 规则关联外部数据源（缺 source/target sub_table）→ status='na' + label '外部勾稽'
 * 5. applicable_when.standard 过滤 —— 仅当前准则匹配的规则参与校验
 * 6. less_than_or_equal 上限校验 + 超限
 * 7. ruleStatusForSubTable 按子表过滤 + 响应式重算
 */
import { describe, it, expect } from 'vitest'
import { ref } from 'vue'
import { useCNoteInheritance } from './useCNoteInheritance'
import type {
  CNoteTableSchema,
  InheritanceRule,
  RowData,
  SubClass,
} from '../../GtCNoteTable.types'

// ─── Helpers ──────────────────────────────────────────────────────────────────

/**
 * 构造一个含两张子表的 schema：
 *  - single_provision（dynamic_rows）：单项计提明细，book_balance
 *  - by_category（static_rows）：按种类汇总，static_row id=cat_single，列 B→book_balance
 * inheritance_rule 可由各用例自行注入。
 */
function makeSchema(rules: InheritanceRule[] = []): CNoteTableSchema {
  return {
    component_type: 'c-note-table',
    sub_tables: [
      {
        id: 'single_provision',
        title: '单项计提',
        type: 'dynamic_rows',
        columns: {
          B: { field: 'book_balance', label: '账面余额', type: 'number', render: 'amount' },
        },
      },
      {
        id: 'by_category',
        title: '按种类汇总',
        type: 'static_rows',
        columns: {
          B: { field: 'book_balance', label: '账面余额', type: 'number', render: 'amount' },
        },
        static_rows: [{ id: 'cat_single', label: '一、单项计提', is_subtotal: true }],
      },
    ],
    inheritance_rules: rules,
  }
}

/** source = single_provision sum(book_balance) ↔ target = by_category.cat_single.B */
function sumRule(overrides: Partial<InheritanceRule> = {}): InheritanceRule {
  return {
    id: 'single_to_category',
    source: { sub_table: 'single_provision', sum_field: 'book_balance' },
    target: { sub_table: 'by_category', row: 'cat_single', column: 'B' },
    formula: 'SUM',
    validation: 'equal',
    on_mismatch: 'error',
    description: '单项子表余额合计 = 按种类"单项"行',
    ...overrides,
  }
}

function makeData(singleRows: RowData[], categoryBalance: number): Record<string, RowData[]> {
  return {
    single_provision: singleRows,
    by_category: [{ id: 'cat_single', book_balance: categoryBalance }],
  }
}

// ─── Tests ──────────────────────────────────────────────────────────────────

describe('useCNoteInheritance', () => {
  it('case 1: ok（绿✓）— source 合计 = target → status=ok + diff=0', () => {
    const schema = ref<CNoteTableSchema>(makeSchema([sumRule()]))
    // 60000 + 40000 = 100000 == category 100000
    const subTableData = ref(makeData([{ book_balance: 60000 }, { book_balance: 40000 }], 100000))
    const sub = ref<SubClass>('listed')

    const { ruleStatuses } = useCNoteInheritance(schema, subTableData, sub)

    expect(ruleStatuses.value.length).toBe(1)
    const rs = ruleStatuses.value[0]
    expect(rs.ruleId).toBe('single_to_category')
    expect(rs.subTableId).toBe('single_provision')
    expect(rs.status).toBe('ok')
    expect(rs.diff).toBe(0)
    expect(rs.label).toBe('勾稽一致')
  })

  it('case 2: mismatch（红✗）— source ≠ target + on_mismatch=error → status=mismatch + diff', () => {
    const schema = ref<CNoteTableSchema>(makeSchema([sumRule()]))
    // 60000 + 40000 = 100000 vs category 90000 → diff = 10000
    const subTableData = ref(makeData([{ book_balance: 60000 }, { book_balance: 40000 }], 90000))
    const sub = ref<SubClass>('listed')

    const { ruleStatuses } = useCNoteInheritance(schema, subTableData, sub)

    const rs = ruleStatuses.value[0]
    expect(rs.status).toBe('mismatch')
    expect(rs.diff).toBe(10000)
    expect(rs.label).toContain('差异')
    expect(rs.tooltip).toContain('源值')
    expect(rs.tooltip).toContain('目标值')
  })

  it('case 3: warning（黄）— source ≠ target + on_mismatch=warning → status=warning', () => {
    const schema = ref<CNoteTableSchema>(makeSchema([sumRule({ on_mismatch: 'warning' })]))
    const subTableData = ref(makeData([{ book_balance: 60000 }, { book_balance: 40000 }], 90000))
    const sub = ref<SubClass>('listed')

    const { ruleStatuses } = useCNoteInheritance(schema, subTableData, sub)

    const rs = ruleStatuses.value[0]
    expect(rs.status).toBe('warning')
    expect(rs.diff).toBe(10000)
  })

  it('case 4: na — 规则缺 source/target sub_table（外部数据源）→ status=na + label 外部勾稽', () => {
    const externalRule: InheritanceRule = {
      id: 'external_check',
      source: { external: 'trial_balance', query: { account: '1122' } },
      target: { sub_table: 'by_category', row: 'cat_single', column: 'B' },
      validation: 'equal',
      on_mismatch: 'error',
      description: '与试算表 1122 科目勾稽',
    }
    const schema = ref<CNoteTableSchema>(makeSchema([externalRule]))
    const subTableData = ref(makeData([{ book_balance: 60000 }], 60000))
    const sub = ref<SubClass>('listed')

    const { ruleStatuses } = useCNoteInheritance(schema, subTableData, sub)

    const rs = ruleStatuses.value[0]
    expect(rs.status).toBe('na')
    expect(rs.label).toBe('外部勾稽')
    // source 无 sub_table → subTableId 落到 target.sub_table
    expect(rs.subTableId).toBe('by_category')
    expect(rs.tooltip).toBe('与试算表 1122 科目勾稽')
  })

  it('case 5: applicable_when.standard 过滤 — 仅当前准则匹配的规则参与校验', () => {
    // soe 专属规则
    const soeOnlyRule = sumRule({
      id: 'soe_only',
      applicable_when: { standard: 'soe' },
    })
    const schema = ref<CNoteTableSchema>(makeSchema([soeOnlyRule]))
    const subTableData = ref(makeData([{ book_balance: 100000 }], 100000))
    const sub = ref<SubClass>('listed')

    const { ruleStatuses } = useCNoteInheritance(schema, subTableData, sub)

    // listed 下 soe 专属规则被过滤掉
    expect(ruleStatuses.value.length).toBe(0)

    // 切到 soe → 规则生效
    sub.value = 'soe'
    expect(ruleStatuses.value.length).toBe(1)
    expect(ruleStatuses.value[0].ruleId).toBe('soe_only')
    expect(ruleStatuses.value[0].status).toBe('ok')
  })

  it('case 6: less_than_or_equal — 上限通过 vs 超限', () => {
    const leRule = sumRule({
      id: 'le_rule',
      validation: 'less_than_or_equal',
    })

    // 上限通过：source 90000 ≤ target 100000
    const schemaOk = ref<CNoteTableSchema>(makeSchema([leRule]))
    const okData = ref(makeData([{ book_balance: 90000 }], 100000))
    const subOk = ref<SubClass>('listed')
    const { ruleStatuses: okStatuses } = useCNoteInheritance(schemaOk, okData, subOk)
    expect(okStatuses.value[0].status).toBe('ok')
    expect(okStatuses.value[0].label).toBe('上限通过')

    // 超限：source 120000 > target 100000 → mismatch（on_mismatch=error）
    const schemaOver = ref<CNoteTableSchema>(makeSchema([leRule]))
    const overData = ref(makeData([{ book_balance: 120000 }], 100000))
    const subOver = ref<SubClass>('listed')
    const { ruleStatuses: overStatuses } = useCNoteInheritance(schemaOver, overData, subOver)
    expect(overStatuses.value[0].status).toBe('mismatch')
    expect(overStatuses.value[0].label).toContain('超限')
    expect(overStatuses.value[0].diff).toBe(20000)
  })

  it('case 7: ruleStatusForSubTable 按子表过滤 + 响应式重算', () => {
    const schema = ref<CNoteTableSchema>(makeSchema([sumRule()]))
    const subTableData = ref(makeData([{ book_balance: 60000 }, { book_balance: 40000 }], 100000))
    const sub = ref<SubClass>('listed')

    const { ruleStatusForSubTable } = useCNoteInheritance(schema, subTableData, sub)

    // 规则挂在 single_provision 子表上
    expect(ruleStatusForSubTable('single_provision').length).toBe(1)
    expect(ruleStatusForSubTable('single_provision')[0].status).toBe('ok')
    // 其它子表无规则
    expect(ruleStatusForSubTable('by_category').length).toBe(0)

    // 响应式：修改动态行使合计变化 → 重新计算为 mismatch
    subTableData.value.single_provision[0].book_balance = 70000 // 70000+40000=110000 ≠ 100000
    const after = ruleStatusForSubTable('single_provision')
    expect(after[0].status).toBe('mismatch')
    expect(after[0].diff).toBe(10000)
  })
})
