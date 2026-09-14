/**
 * useJ1Adjudication — 审定表变动列口径 + 持久化 回归测试
 *
 * 锁定 2026-07-26 修复的两个 P0：
 *  1. 模板读 unadjVsPriorDiff/Rate 与 auditedVsPriorDiff/Rate，而 composable 只算
 *     changeDiff/changeRate → 四列恒 undefined（现按「上期审定数 = 期初审定数」口径派生）
 *  2. 审定表编辑无任何持久化 → 刷新即丢（现写 J1-1-rows + 跨表合计键）
 */
import { describe, it, expect, vi } from 'vitest'
import { ref } from 'vue'
import {
  useJ1Adjudication,
  recalcAdjudicationRow,
  J1_ADJ_ROWS_KEY,
  J1_ADJ_END_TOTAL_KEY,
  J1_ADJ_BEGIN_TOTAL_KEY,
  J1_DETAIL_SECTION_KEYS,
  normalizeJ1Label,
  buildAdjudicationRowsFromDetail,
  type AdjudicationRow,
  type ChecklistItem,
} from '../useJ1Adjudication'

function makeRow(partial: Partial<AdjudicationRow> = {}): AdjudicationRow {
  return recalcAdjudicationRow({
    id: 'r1', label: '工资', category: 'short_term',
    beginUnadj: 0, beginAje: 0, beginAudited: 0,
    endUnadj: 0, endAje: 0, endAudited: 0,
    unadjVsPriorDiff: 0, unadjVsPriorRate: 0,
    auditedVsPriorDiff: 0, auditedVsPriorRate: 0,
    changeDiff: 0, changeRate: 0,
    analysis: '',
    ...partial,
  })
}

const PREFILL = {
  adjudication_rows: [
    { id: 'tb-2211.01', label: '短期薪酬', category: 'short_term', begin_unadj: 100, begin_aje: 0, end_unadj: 150, end_aje: 10 },
    { id: 'tb-2211.02', label: '养老保险', category: 'post_employment', begin_unadj: 50, begin_aje: 0, end_unadj: 40, end_aje: 0 },
  ],
}

describe('recalcAdjudicationRow — 变动列口径（上期审定数=期初审定数）', () => {
  it('审定数 = 未审 + 调整', () => {
    const r = makeRow({ beginUnadj: 100, beginAje: 5, endUnadj: 200, endAje: -10 })
    expect(r.beginAudited).toBe(105)
    expect(r.endAudited).toBe(190)
  })

  it('未审 vs 上期审定 / 审定 vs 上期审定 均以期初审定为基数', () => {
    const r = makeRow({ beginUnadj: 100, beginAje: 0, endUnadj: 150, endAje: 10 })
    expect(r.unadjVsPriorDiff).toBe(50)
    expect(r.unadjVsPriorRate).toBe(50)
    expect(r.auditedVsPriorDiff).toBe(60)
    expect(r.auditedVsPriorRate).toBe(60)
  })

  it('deprecated changeDiff/changeRate 与 auditedVsPrior* 保持同值（向后兼容）', () => {
    const r = makeRow({ beginUnadj: 100, endUnadj: 130 })
    expect(r.changeDiff).toBe(r.auditedVsPriorDiff)
    expect(r.changeRate).toBe(r.auditedVsPriorRate)
  })

  it('变动列不再是 undefined（历史 bug：模板读不到 → 30% 标红从不触发）', () => {
    const r = makeRow({ beginUnadj: 100, endUnadj: 200 })
    for (const k of ['unadjVsPriorDiff', 'unadjVsPriorRate', 'auditedVsPriorDiff', 'auditedVsPriorRate'] as const) {
      expect(r[k]).not.toBeUndefined()
    }
    expect(Math.abs(r.auditedVsPriorRate) > 30).toBe(true)
  })
})

describe('useJ1Adjudication — hydrate 优先级', () => {
  it('无持久化时用 htmlData（后端 tb_balance 预填），snake_case 字段可解析', () => {
    const { rows, init, grandTotal } = useJ1Adjudication(ref(PREFILL as any))
    init(PREFILL as any)
    expect(rows.value).toHaveLength(2)
    expect(rows.value[0].beginUnadj).toBe(100)
    expect(rows.value[0].endAudited).toBe(160)
    expect(grandTotal.value.endAudited).toBe(200)
  })

  it('有持久化行时优先 J1-1-rows（不再被 tb_balance 预填覆盖）', () => {
    const map = ref(new Map<string, ChecklistItem>([
      [J1_ADJ_ROWS_KEY, {
        item_id: J1_ADJ_ROWS_KEY, conclusion: null,
        remark: JSON.stringify([
          { id: 'x1', label: '手工行', category: 'severance', beginUnadj: 7, beginAje: 0, endUnadj: 9, endAje: 0, analysis: '裁员' },
        ]),
      }],
    ]))
    const { rows, init } = useJ1Adjudication(ref(PREFILL as any), { allResponses: map })
    init(PREFILL as any)
    expect(rows.value).toHaveLength(1)
    expect(rows.value[0].label).toBe('手工行')
    expect(rows.value[0].endAudited).toBe(9)
  })

  it('持久化数据损坏时回退 htmlData（不崩）', () => {
    const map = ref(new Map<string, ChecklistItem>([
      [J1_ADJ_ROWS_KEY, { item_id: J1_ADJ_ROWS_KEY, conclusion: null, remark: '{不是JSON' }],
    ]))
    const { rows, init } = useJ1Adjudication(ref(PREFILL as any), { allResponses: map })
    init(PREFILL as any)
    expect(rows.value).toHaveLength(2)
  })
})

describe('useJ1Adjudication — 持久化', () => {
  it('updateRow 落库行 JSON + 期末/期初审定合计跨表键', async () => {
    const map = ref(new Map<string, ChecklistItem>())
    const saveImmediate = vi.fn().mockResolvedValue(undefined)
    const { init, updateRow } = useJ1Adjudication(ref(PREFILL as any), { allResponses: map, saveImmediate })
    init(PREFILL as any)

    updateRow('tb-2211.01', 'endAje', 40)

    expect(saveImmediate).toHaveBeenCalledTimes(1)
    const items: ChecklistItem[] = saveImmediate.mock.calls[0][0]
    const byId = Object.fromEntries(items.map(i => [i.item_id, i.remark]))
    expect(Object.keys(byId).sort()).toEqual(
      [J1_ADJ_BEGIN_TOTAL_KEY, J1_ADJ_END_TOTAL_KEY, J1_ADJ_ROWS_KEY].sort(),
    )
    // 150+40 + 40 = 230
    expect(byId[J1_ADJ_END_TOTAL_KEY]).toBe('230')
    expect(byId[J1_ADJ_BEGIN_TOTAL_KEY]).toBe('150')
    const stored = JSON.parse(byId[J1_ADJ_ROWS_KEY] as string)
    expect(stored[0].endAje).toBe(40)
    // 只存基础字段（派生列 hydrate 时重算，避免陈旧值）
    expect(stored[0]).not.toHaveProperty('endAudited')
    // 内存 Map 同步写回（切 sheet 不丢）
    expect(map.value.get(J1_ADJ_ROWS_KEY)).toBeTruthy()
  })

  it('commitRows 在增删行后重算并落库', () => {
    const map = ref(new Map<string, ChecklistItem>())
    const saveImmediate = vi.fn().mockResolvedValue(undefined)
    const { rows, init, commitRows } = useJ1Adjudication(ref(PREFILL as any), { allResponses: map, saveImmediate })
    init(PREFILL as any)
    rows.value.push(makeRow({ id: 'new', label: '辞退福利', category: 'severance', endUnadj: 30 }))
    commitRows()
    const items: ChecklistItem[] = saveImmediate.mock.calls[0][0]
    const endTotal = items.find(i => i.item_id === J1_ADJ_END_TOTAL_KEY)?.remark
    expect(endTotal).toBe('230') // 160 + 40 + 30
  })

  it('未提供 saveImmediate 时不抛错（只写内存）', () => {
    const map = ref(new Map<string, ChecklistItem>())
    const { init, updateRow } = useJ1Adjudication(ref(PREFILL as any), { allResponses: map })
    init(PREFILL as any)
    expect(() => updateRow('tb-2211.01', 'endUnadj', 500)).not.toThrow()
    // (500 未审 + 10 调整) + (40 + 0) = 550
    expect(map.value.get(J1_ADJ_END_TOTAL_KEY)?.remark).toBe('550')
  })
})

describe('useJ1Adjudication — 分组小计', () => {
  it('小计变动率按小计口径重算（非逐行求和）', () => {
    const { groups, init } = useJ1Adjudication(ref(PREFILL as any))
    init(PREFILL as any)
    const shortTerm = groups.value.find(g => g.category === 'short_term')!
    expect(shortTerm.subtotal.beginAudited).toBe(100)
    expect(shortTerm.subtotal.endAudited).toBe(160)
    expect(shortTerm.subtotal.auditedVsPriorRate).toBe(60)
  })

  it('四个分类分组恒存在（含空分组）', () => {
    const { groups, init } = useJ1Adjudication(ref({} as any))
    init({})
    expect(groups.value.map(g => g.category)).toEqual([
      'short_term', 'post_employment', 'severance', 'other_long_term',
    ])
  })
})

// ─── P1：从 J1-2 明细带入未审数 ────────────────────────────────────────────

describe('normalizeJ1Label — 项目名归一化', () => {
  it('去空白/「其中：」前缀/序号前缀/不适用尾注', () => {
    expect(normalizeJ1Label('其中：1.工资')).toBe('工资')
    expect(normalizeJ1Label(' 职工 福利费 ')).toBe('职工福利费')
    expect(normalizeJ1Label('2、奖金')).toBe('奖金')
    expect(normalizeJ1Label('其他长期职工福利（不适用的删除）')).toBe('其他长期职工福利')
    expect(normalizeJ1Label(null)).toBe('')
  })
})

describe('buildAdjudicationRowsFromDetail — 明细→审定表带入', () => {
  const sections = {
    shortTerm: [
      { label: '工资、奖金、津贴和补贴', unadjBegin: 100, unadjIncrease: 900, unadjDecrease: 800 },
      { label: '其中：1.工资', indent: 1, unadjBegin: 80, unadjIncrease: 700, unadjDecrease: 620 },
    ],
    postEmployment: [
      { label: '离职后福利', unadjBegin: 20, unadjIncrease: 100, unadjDecrease: 90 },
      { label: '其他长期职工福利', unadjBegin: 5, unadjIncrease: 10, unadjDecrease: 3 },
      { label: '其中：1.xxx', indent: 1, unadjBegin: 5, unadjIncrease: 10, unadjDecrease: 3 },
    ],
    severance: [
      { label: '', unadjBegin: 0, unadjIncrease: 0, unadjDecrease: 0 },
      { label: '车间裁员补偿', unadjBegin: 0, unadjIncrease: 50, unadjDecrease: 20 },
    ],
  }

  it('期末未审 = 期初 + 增加 − 减少（负债贷方口径）', () => {
    const { rows } = buildAdjudicationRowsFromDetail(sections as any, [])
    const wage = rows.find(r => r.label === '工资、奖金、津贴和补贴')!
    expect(wage.beginUnadj).toBe(100)
    expect(wage.endUnadj).toBe(200)
    expect(wage.category).toBe('short_term')
  })

  it('postEmployment 分区自「其他长期职工福利」起归入 other_long_term', () => {
    const { rows } = buildAdjudicationRowsFromDetail(sections as any, [])
    expect(rows.find(r => r.label === '离职后福利')!.category).toBe('post_employment')
    expect(rows.find(r => r.label === '其他长期职工福利')!.category).toBe('other_long_term')
    expect(rows.find(r => r.label === '其中：1.xxx')!.category).toBe('other_long_term')
  })

  it('空名且全零行跳过（辞退福利默认空行）', () => {
    const { rows } = buildAdjudicationRowsFromDetail(sections as any, [])
    expect(rows.filter(r => r.category === 'severance').map(r => r.label)).toEqual(['车间裁员补偿'])
  })

  it('同名行保留既有调整/原因分析与行 id', () => {
    const existing = [makeRow({ id: 'keep-1', label: '其中：工资', beginAje: 3, endAje: 7, analysis: '已核' })]
    const { rows, matched } = buildAdjudicationRowsFromDetail(sections as any, existing)
    expect(matched).toBe(1)
    const wage = rows.find(r => r.label === '其中：1.工资')!
    expect(wage.id).toBe('keep-1')
    expect(wage.endAje).toBe(7)
    expect(wage.analysis).toBe('已核')
    // 审定 = 未审 + 调整（80+3 / 160+7）
    expect(wage.beginAudited).toBe(83)
    expect(wage.endUnadj).toBe(160)
    expect(wage.endAudited).toBe(167)
  })

  it('pullFromDetail 读 J1-2 分区键并落库；明细未编制时返回 0 不动现有行', () => {
    const map = ref(new Map<string, ChecklistItem>())
    const saveImmediate = vi.fn().mockResolvedValue(undefined)
    const { rows, init, pullFromDetail } = useJ1Adjudication(ref(PREFILL as any), { allResponses: map, saveImmediate })
    init(PREFILL as any)

    // 明细表未编制 → no-op
    expect(pullFromDetail()).toEqual({ rowCount: 0, matched: 0 })
    expect(rows.value).toHaveLength(2)

    map.value.set(J1_DETAIL_SECTION_KEYS.shortTerm, {
      item_id: J1_DETAIL_SECTION_KEYS.shortTerm, conclusion: null,
      remark: JSON.stringify(sections.shortTerm),
    })
    const res = pullFromDetail()
    expect(res.rowCount).toBe(2)
    expect(rows.value.map(r => r.label)).toEqual(['工资、奖金、津贴和补贴', '其中：1.工资'])
    expect(saveImmediate).toHaveBeenCalled()
  })
})
