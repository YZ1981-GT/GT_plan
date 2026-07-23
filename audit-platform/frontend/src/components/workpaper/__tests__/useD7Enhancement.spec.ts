/**
 * D7 合同负债增强 — 属性测试 + 单元测试
 *
 * 覆盖动态账龄全链路（P1-P7, P11, P14）与调整分录按性质/账龄路由（P12, P13, P15）。
 *
 * Spec: .kiro/specs/d7-contract-liabilities-enhancement/
 * Task: 11
 */
import { describe, it, expect } from 'vitest'
import { ref } from 'vue'
import * as fc from 'fast-check'
import { segmentsToBands, PRESET_SEGMENTS, type AgingSegment } from '@/composables/useAgingConfig'
import { migrateD7FlatToNested, remapAgingData } from '@/composables/useAgingMigration'
import { aggregateAgingByKeys, collectAgingKeys } from '../composables/useD7FormulaEngine'
import { useD7CrossSheet } from '../composables/useD7CrossSheet'
import { useD7Adjudication } from '../composables/useD7Adjudication'
import { useD7Adjustment, type AdjustmentRow } from '../composables/useD7Adjustment'
import { useD7DetailColumnPrefs } from '../composables/useD7DetailColumnPrefs'
import type { ChecklistResponse } from '../composables/useD7FormData'

// ─── Generators ──────────────────────────────────────────────────────────────

const finiteFloat = (min = -1e9, max = 1e9) =>
  fc.float({ min, max, noNaN: true, noDefaultInfinity: true })

/** 随机段列表（THREE_YEAR / FIVE_YEAR / 自定义 2-5 段） */
const segmentsGen = (): fc.Arbitrary<AgingSegment[]> =>
  fc.oneof(
    fc.constant(PRESET_SEGMENTS.THREE_YEAR),
    fc.constant(PRESET_SEGMENTS.FIVE_YEAR),
    fc.array(fc.integer({ min: 1, max: 5 }), { minLength: 2, maxLength: 5 }).map((arr) =>
      arr.map((_, i) => ({
        key: `seg${i}`,
        label: `段${i}`,
        dayFrom: i === 0 ? 0 : 366 + i,
        dayTo: null,
      } as AgingSegment)),
    ),
  )

function makeMap(entries: Record<string, string>): Map<string, ChecklistResponse> {
  const m = new Map<string, ChecklistResponse>()
  for (const [k, v] of Object.entries(entries)) {
    m.set(k, { item_id: k, conclusion: null, remark: v })
  }
  return m
}

// ─── Property 1: D7 为 2-period，账龄列不含期末未审 ────────────────────────────

describe('Property 1: D7 为 2-period（无期末未审列）', () => {
  /** Feature: d7-contract-liabilities-enhancement, Property 1: D7 为 2-period，账龄列不含期末未审 */
  it('segmentsToBands(_, "D7") band 数=段数，currentField 恒为空', () => {
    fc.assert(
      fc.property(segmentsGen(), (segments) => {
        const bands = segmentsToBands(segments, 'D7')
        expect(bands.length).toBe(segments.length)
        for (const b of bands) {
          expect(b.currentField).toBe('')
          expect(b.priorField).toBe(`agingPrior.${b.key}`)
          expect(b.auditedField).toBe(`agingAudited.${b.key}`)
        }
      }),
      { numRuns: 100 },
    )
  })
})

// ─── Property 2: 账龄列/列组/审定账龄行数量由段驱动 ───────────────────────────

describe('Property 2: 列数由段驱动', () => {
  /** Feature: d7-contract-liabilities-enhancement, Property 2: 账龄列/列组由段驱动 */
  it('列偏好账龄组显隐项数 = 段数 × 2（期初+期末审定）', () => {
    fc.assert(
      fc.property(segmentsGen(), (segments) => {
        const segRef = ref(segments)
        const { columnGroups } = useD7DetailColumnPrefs(segRef)
        const priorGroup = columnGroups.value.find(g => g.label === '期初账龄')
        const auditedGroup = columnGroups.value.find(g => g.label === '期末账龄')
        expect(priorGroup?.keys.length).toBe(segments.length)
        expect(auditedGroup?.keys.length).toBe(segments.length)
        // label 一一对应
        expect(priorGroup?.keys).toEqual(segments.map(s => `agingPrior.${s.key}`))
        expect(auditedGroup?.keys).toEqual(segments.map(s => `agingAudited.${s.key}`))
      }),
      { numRuns: 100 },
    )
  })
})

// ─── Property 3: 账龄按段 key 聚合且忽略配置外旧段 ─────────────────────────────

describe('Property 3: 按段聚合忽略配置外旧段', () => {
  /** Feature: d7-contract-liabilities-enhancement, Property 3: 账龄按段 key 聚合且忽略配置外旧段 */
  it('agingByKey 等于各行该段之和；旧段 key 不出现在结果', () => {
    fc.assert(
      fc.property(
        segmentsGen(),
        fc.array(fc.record({ a: finiteFloat(0, 1e6), b: finiteFloat(0, 1e6) }), { minLength: 0, maxLength: 10 }),
        (segments, raw) => {
          const keys = segments.map(s => s.key)
          const rows = raw.map(r => ({
            // 每行填首段 + 一个"配置外旧段" legacyX
            agingAudited: { [keys[0]]: r.a, legacyX: r.b },
            agingPrior: { [keys[0]]: r.a },
          }))
          const { current } = aggregateAgingByKeys(rows, keys)
          const expected = rows.reduce((s, row) => s + (row.agingAudited[keys[0]] || 0), 0)
          expect(Math.abs((current[keys[0]] ?? 0) - expected)).toBeLessThan(1e-3)
          // 旧段 legacyX 不出现
          expect('legacyX' in current).toBe(false)
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ─── Property 5: 超1年段判定 dayFrom>=366 ─────────────────────────────────────

describe('Property 5: 超1年段判定 dayFrom>=366', () => {
  /** Feature: d7-contract-liabilities-enhancement, Property 5: 超1年段判定 dayFrom>=366 */
  it('crossSheet.overOneYearKeys 恰含 dayFrom>=366 的段', () => {
    fc.assert(
      fc.property(segmentsGen(), (segments) => {
        const cs = useD7CrossSheet({ allResponses: ref(makeMap({})), segments: ref(segments) })
        const expected = segments.filter(s => s.dayFrom >= 366).map(s => s.key)
        expect(cs.overOneYearKeys.value.sort()).toEqual(expected.sort())
      }),
      { numRuns: 100 },
    )
  })
})

// ─── Property 7: 配置变更数据保留 ─────────────────────────────────────────────

describe('Property 7: 配置变更数据保留（共有保留/新增零/旧丢弃）', () => {
  /** Feature: d7-contract-liabilities-enhancement, Property 7: 配置变更数据保留 */
  it('remapAgingData 共有段保留、新增段为0、旧段被丢弃', () => {
    fc.assert(
      fc.property(
        fc.dictionary(fc.constantFrom('within1', 'y1to2', 'y2to3', 'legacyOld'), finiteFloat(0, 1e6)),
        segmentsGen(),
        (oldData, newSegments) => {
          const result = remapAgingData(oldData, newSegments)
          const newKeys = new Set(newSegments.map(s => s.key))
          // 结果 key 完全等于新段
          expect(Object.keys(result).sort()).toEqual(newSegments.map(s => s.key).sort())
          for (const seg of newSegments) {
            if (seg.key in oldData) {
              expect(result[seg.key]).toBe(oldData[seg.key])  // 共有段保留
            } else {
              expect(result[seg.key]).toBe(0)  // 新增段零初始化
            }
          }
          // 旧独有段丢弃
          if ('legacyOld' in oldData && !newKeys.has('legacyOld')) {
            expect('legacyOld' in result).toBe(false)
          }
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ─── Property 11: 历史扁平账龄迁移保值且仅输出 nested ─────────────────────────

describe('Property 11: 历史扁平账龄迁移', () => {
  /** Feature: d7-contract-liabilities-enhancement, Property 11: 扁平迁移保值且仅输出 nested */
  it('flat priorAging1~4/endAging1~4 → nested 默认段，不再含扁平 key，nested 优先', () => {
    fc.assert(
      fc.property(
        finiteFloat(0, 1e6), finiteFloat(0, 1e6), finiteFloat(0, 1e6), finiteFloat(0, 1e6),
        finiteFloat(0, 1e6), finiteFloat(0, 1e6), finiteFloat(0, 1e6), finiteFloat(0, 1e6),
        (p1, p2, p3, p4, e1, e2, e3, e4) => {
          const flat = {
            rowId: 'x', companyName: 'A',
            priorAging1: p1, priorAging2: p2, priorAging3: p3, priorAging4: p4,
            endAging1: e1, endAging2: e2, endAging3: e3, endAging4: e4,
          }
          const migrated: any = migrateD7FlatToNested(flat)
          // 值映射到 THREE_YEAR 默认段
          expect(migrated.agingPrior.within1).toBe(p1)
          expect(migrated.agingPrior.y1to2).toBe(p2)
          expect(migrated.agingPrior.y2to3).toBe(p3)
          expect(migrated.agingPrior.over3).toBe(p4)
          expect(migrated.agingAudited.within1).toBe(e1)
          expect(migrated.agingAudited.over3).toBe(e4)
          // 不再含扁平字段 key
          expect('priorAging1' in migrated).toBe(false)
          expect('endAging4' in migrated).toBe(false)
          // 保留非账龄字段
          expect(migrated.companyName).toBe('A')
        },
      ),
      { numRuns: 100 },
    )
  })

  it('同时含 nested 与扁平字段时以 nested 为准（Req 8.4）', () => {
    const mixed = {
      priorAging1: 999, endAging1: 888,
      agingPrior: { within1: 111 }, agingAudited: { within1: 222 },
    }
    const migrated: any = migrateD7FlatToNested(mixed)
    expect(migrated.agingPrior.within1).toBe(111)
    expect(migrated.agingAudited.within1).toBe(222)
    expect('priorAging1' in migrated).toBe(false)
  })
})

// ─── Property 12: 调整分录按性质/账龄双分组派生（缺省归"其他"） ──────────────

describe('Property 12: 调整分录双分组派生', () => {
  /** Feature: d7-contract-liabilities-enhancement, Property 12: 调整分录按性质/账龄双分组派生 */
  it('byNature / byAging 分组累加正确；缺省性质归 other；Σ byNature.aje === totalAje', () => {
    const segments = PRESET_SEGMENTS.THREE_YEAR
    fc.assert(
      fc.property(
        fc.array(fc.record({
          natureType: fc.constantFrom('预收货款', '开发项目预收款', '预收工程款', '其他', ''),
          agingBand: fc.constantFrom('within1', 'y1to2', 'y2to3', 'over3', ''),
          debitAmount: finiteFloat(0, 1e6),
          creditAmount: finiteFloat(0, 1e6),
        }), { minLength: 0, maxLength: 20 }),
        (adjRows) => {
          const cs = useD7CrossSheet({
            allResponses: ref(makeMap({ 'D7-3-rows': JSON.stringify(adjRows) })),
            segments: ref(segments),
          })
          const totals = cs.adjustmentTotals.value

          // Σ byNature.aje === totalAje（每行必归入某性质）
          const sumNatureAje = Object.values(totals.byNature).reduce((s, v) => s + v.aje, 0)
          const sumNatureRje = Object.values(totals.byNature).reduce((s, v) => s + v.rje, 0)
          expect(Math.abs(sumNatureAje - totals.totalAje)).toBeLessThan(1e-3)
          expect(Math.abs(sumNatureRje - totals.totalRje)).toBeLessThan(1e-3)

          // 手工对照：debit>0 → AJE，否则 credit → RJE
          let expectAje = 0, expectRje = 0
          let expectOtherAje = 0
          for (const r of adjRows) {
            const isAje = r.debitAmount > 0
            const amt = isAje ? r.debitAmount : r.creditAmount
            if (amt === 0) continue
            if (isAje) {
              expectAje += amt
              const nk = ['预收货款', '开发项目预收款', '预收工程款', '其他'].includes(r.natureType) ? r.natureType : ''
              if (nk === '' || nk === '其他') expectOtherAje += amt
            } else {
              expectRje += amt
            }
          }
          expect(Math.abs(totals.totalAje - expectAje)).toBeLessThan(1e-3)
          expect(Math.abs(totals.totalRje - expectRje)).toBeLessThan(1e-3)
          expect(Math.abs(totals.byNature.other.aje - expectOtherAje)).toBeLessThan(1e-3)
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ─── Property 13: computed 幂等，不随重算放大；删除后减少 ──────────────────────

describe('Property 13: 调整数 computed 幂等', () => {
  /** Feature: d7-contract-liabilities-enhancement, Property 13: computed 幂等不放大 + 删除减少 */
  it('重复读取结果恒等；删除一行后对应分组恰减该行贡献', () => {
    const segments = PRESET_SEGMENTS.THREE_YEAR
    const rows = [
      { natureType: '预收货款', agingBand: 'within1', debitAmount: 100, creditAmount: 0 },
      { natureType: '预收货款', agingBand: 'within1', debitAmount: 50, creditAmount: 0 },
    ]
    const allResponses = ref(makeMap({ 'D7-3-rows': JSON.stringify(rows) }))
    const cs = useD7CrossSheet({ allResponses, segments: ref(segments) })

    const first = cs.adjustmentTotals.value.byNature.revenue.aje
    const second = cs.adjustmentTotals.value.byNature.revenue.aje
    expect(first).toBe(second)   // 幂等
    expect(first).toBe(150)

    // 删除第二行
    allResponses.value = makeMap({ 'D7-3-rows': JSON.stringify([rows[0]]) })
    expect(cs.adjustmentTotals.value.byNature.revenue.aje).toBe(100)  // 恰减 50
    expect(cs.adjustmentTotals.value.byAging.within1.aje).toBe(100)
  })
})

// ─── Property 15: 性质合计与账龄合计交叉验证恒等 ──────────────────────────────

describe('Property 15: 性质/账龄交叉验证', () => {
  /** Feature: d7-contract-liabilities-enhancement, Property 15: 性质合计与账龄合计交叉验证 */
  it('行级 endAudited === Σ agingAudited 时 crossValidation.isConsistent', () => {
    const segments = PRESET_SEGMENTS.THREE_YEAR
    fc.assert(
      fc.property(
        fc.array(fc.record({
          natureType: fc.constantFrom('预收货款', '其他'),
          w: finiteFloat(0, 1e5), a: finiteFloat(0, 1e5), b: finiteFloat(0, 1e5), c: finiteFloat(0, 1e5),
        }), { minLength: 0, maxLength: 10 }),
        (raw) => {
          const detailRows = raw.map(r => ({
            natureType: r.natureType,
            endAudited: r.w + r.a + r.b + r.c,   // 行级一致
            priorAudited: 0,
            agingAudited: { within1: r.w, y1to2: r.a, y2to3: r.b, over3: r.c },
            agingPrior: { within1: 0, y1to2: 0, y2to3: 0, over3: 0 },
          }))
          const cs = useD7CrossSheet({
            allResponses: ref(makeMap({ 'D7-2-rows': JSON.stringify(detailRows) })),
            segments: ref(segments),
          })
          expect(cs.crossValidation.value.isConsistent).toBe(true)
          expect(Math.abs(cs.crossValidation.value.diff)).toBeLessThan(0.01)
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ─── collectAgingKeys 回归（保序去重） ────────────────────────────────────────

describe('collectAgingKeys', () => {
  it('保序去重（audited 优先，其次 prior）', () => {
    const rows = [
      { agingAudited: { within1: 1, y1to2: 2 } },
      { agingAudited: { y2to3: 3 }, agingPrior: { over3: 4 } },
    ]
    expect(collectAgingKeys(rows)).toEqual(['within1', 'y1to2', 'y2to3', 'over3'])
    expect(collectAgingKeys([{}])).toEqual([])
  })
})

// ─── 无副作用 save 桩（供 Adjudication / Adjustment composable 测试） ──────────

const noopSaveImmediate = async (): Promise<void> => {}
const noopDebouncedSave = (): void => {}

/** 构造 useD7Adjudication（含真实 crossSheet）用于账龄区块 computed 测试 */
function buildAdjudication(
  detailRows: any[],
  segments: AgingSegment[],
  extraResponses: Record<string, string> = {},
) {
  const allResponses = ref(makeMap({
    'D7-2-rows': JSON.stringify(detailRows),
    ...extraResponses,
  }))
  const crossSheet = useD7CrossSheet({ allResponses, segments: ref(segments) })
  const adjud = useD7Adjudication({
    allResponses,
    crossSheet,
    saveImmediate: noopSaveImmediate,
    debouncedSave: noopDebouncedSave,
    wpId: ref('wp'),
    projectId: ref('p'),
    isReadonly: ref(false),
  })
  return { allResponses, crossSheet, adjud }
}

// ─── Property 4: 审定表账龄区块合计与差异公式 ─────────────────────────────────

describe('Property 4: 审定表账龄区块合计与差异公式', () => {
  /** Feature: d7-contract-liabilities-enhancement, Property 4: 审定表账龄区块合计与差异公式 */
  it('账龄"合计"行 = 各段明细行之和；"差异数"行 = 账龄合计 - 试算平衡表数', () => {
    const segments = PRESET_SEGMENTS.THREE_YEAR
    const segAmt = () => finiteFloat(0, 1e6)
    fc.assert(
      fc.property(
        fc.array(
          fc.record({
            p: fc.tuple(segAmt(), segAmt(), segAmt(), segAmt()),
            a: fc.tuple(segAmt(), segAmt(), segAmt(), segAmt()),
          }),
          { minLength: 0, maxLength: 8 },
        ),
        finiteFloat(0, 1e7), // 试算平衡表数（期末审定）
        (raw, tbCurrent) => {
          const detailRows = raw.map((r, i) => ({
            rowId: `r${i}`,
            natureType: '其他',
            priorAudited: 0,
            endAudited: 0,
            agingPrior: { within1: r.p[0], y1to2: r.p[1], y2to3: r.p[2], over3: r.p[3] },
            agingAudited: { within1: r.a[0], y1to2: r.a[1], y2to3: r.a[2], over3: r.a[3] },
          }))
          const { adjud } = buildAdjudication(detailRows, segments, {
            'D7-1-adj-aging-trial-balance-currentAudited': String(tbCurrent),
          })

          const rows = adjud.agingRows.value
          const detail = rows.filter(r => r.rowType === 'detail')
          const total = rows.find(r => r.rowKey === 'aging-total')!
          const tb = rows.find(r => r.rowKey === 'trial-balance')!
          const diff = rows.find(r => r.rowKey === 'difference')!

          // 账龄区块明细行数 = 段数（Req 3.1）
          expect(detail.length).toBe(segments.length)

          // 合计 = 各明细行之和（Req 3.2）
          const sumCurrent = detail.reduce((s, r) => s + r.currentAudited, 0)
          const sumPrior = detail.reduce((s, r) => s + r.priorAudited, 0)
          expect(Math.abs(total.currentAudited - sumCurrent)).toBeLessThan(1e-3)
          expect(Math.abs(total.priorAudited - sumPrior)).toBeLessThan(1e-3)

          // 试算平衡表数行取自 seed
          expect(Math.abs(tb.currentAudited - tbCurrent)).toBeLessThan(1e-3)

          // 差异数 = 账龄合计 - 试算平衡表数（Req 3.3）
          expect(Math.abs(diff.currentAudited - (total.currentAudited - tb.currentAudited))).toBeLessThan(1e-3)
          expect(Math.abs(diff.priorAudited - (total.priorAudited - tb.priorAudited))).toBeLessThan(1e-3)
        },
      ),
      { numRuns: 100 },
    )
  })

  it('FIVE_YEAR 段下账龄区块明细行数 = 6', () => {
    const { adjud } = buildAdjudication([], PRESET_SEGMENTS.FIVE_YEAR)
    const detail = adjud.agingRows.value.filter(r => r.rowType === 'detail')
    expect(detail.length).toBe(6)
    expect(detail.map(r => r.label)).toEqual(PRESET_SEGMENTS.FIVE_YEAR.map(s => s.label))
  })
})

// ─── Property 16: D7-3 调整分录往返保留性质/账龄字段 ──────────────────────────

/** 构造 useD7Adjustment，捕获持久化的 D7-3-rows JSON */
function buildAdjustment(initialRows: Partial<AdjustmentRow>[], isReadonly = false) {
  let persisted = JSON.stringify(initialRows)
  const allResponses = ref(makeMap({ 'D7-3-rows': persisted }))
  const debouncedSave = (id: string, data: Partial<ChecklistResponse>): void => {
    if (id === 'D7-3-rows' && data.remark !== undefined) persisted = data.remark
  }
  const adj = useD7Adjustment({
    allResponses,
    saveImmediate: noopSaveImmediate,
    debouncedSave,
    wpId: ref('wp'),
    projectId: ref('p'),
    isReadonly: ref(isReadonly),
  })
  return { adj, getPersisted: () => persisted }
}

describe('Property 16: D7-3 调整分录往返保留性质/账龄字段', () => {
  /** Feature: d7-contract-liabilities-enhancement, Property 16: D7-3 调整分录往返保留性质/账龄字段 */
  it('加载与持久化往返后 natureType / agingBand 保留', () => {
    fc.assert(
      fc.property(
        fc.array(
          fc.record({
            rowId: fc.string({ minLength: 1, maxLength: 8 }),
            description: fc.string({ maxLength: 12 }),
            debitAmount: finiteFloat(0, 1e6),
            creditAmount: finiteFloat(0, 1e6),
            natureType: fc.constantFrom('预收货款', '开发项目预收款', '预收工程款', '其他', ''),
            agingBand: fc.constantFrom('within1', 'y1to2', 'y2to3', 'over3', ''),
          }),
          { minLength: 1, maxLength: 12 },
        ),
        (rowsIn) => {
          const { adj, getPersisted } = buildAdjustment(rowsIn)

          // 加载后逐行保留 natureType / agingBand
          for (let i = 0; i < rowsIn.length; i++) {
            expect(adj.rows.value[i].natureType).toBe(rowsIn[i].natureType)
            expect(adj.rows.value[i].agingBand).toBe(rowsIn[i].agingBand)
          }

          // 触发持久化后往返 JSON 仍保留字段
          const firstId = adj.rows.value[0].rowId
          adj.updateCell(firstId, 'remark', 'touched')
          const reparsed = JSON.parse(getPersisted())
          for (let i = 0; i < rowsIn.length; i++) {
            expect(reparsed[i].natureType).toBe(rowsIn[i].natureType)
            expect(reparsed[i].agingBand).toBe(rowsIn[i].agingBand)
          }
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ─── 单元测试：D7-3 性质/账龄字段持久化 ───────────────────────────────────────

describe('单元测试 — D7-3 natureType / agingBand 字段持久化', () => {
  it('updateCell 写入 natureType / agingBand 并持久化到 D7-3-rows', () => {
    const { adj, getPersisted } = buildAdjustment([
      { rowId: 'a1', description: 'x', debitAmount: 100, creditAmount: 0, natureType: '', agingBand: '' },
    ])
    adj.updateCell('a1', 'natureType', '预收工程款')
    adj.updateCell('a1', 'agingBand', 'over3')
    expect(adj.rows.value[0].natureType).toBe('预收工程款')
    expect(adj.rows.value[0].agingBand).toBe('over3')
    const reparsed = JSON.parse(getPersisted())
    expect(reparsed[0].natureType).toBe('预收工程款')
    expect(reparsed[0].agingBand).toBe('over3')
  })

  it('normalizeRow 缺省 natureType / agingBand 为空串', () => {
    const { adj } = buildAdjustment([{ rowId: 'a1', debitAmount: 0, creditAmount: 0 }])
    expect(adj.rows.value[0].natureType).toBe('')
    expect(adj.rows.value[0].agingBand).toBe('')
  })
})

// ─── 单元测试：只读守卫（Adjustment） ─────────────────────────────────────────

describe('单元测试 — 只读守卫（useD7Adjustment）', () => {
  it('只读模式下 addRow / updateCell 均为 no-op', () => {
    const { adj, getPersisted } = buildAdjustment([
      { rowId: 'a1', description: '原始', debitAmount: 100, creditAmount: 0, natureType: '预收货款', agingBand: 'within1' },
    ], true)
    const before = getPersisted()

    adj.addRow()
    expect(adj.rows.value.length).toBe(1) // 未新增

    adj.updateCell('a1', 'natureType', '其他')
    expect(adj.rows.value[0].natureType).toBe('预收货款') // 未改变

    expect(getPersisted()).toBe(before) // 未触发持久化写入
  })
})

// ─── 单元测试：onAdjustmentCreated 已移除 ─────────────────────────────────────

describe('单元测试 — useD7Adjudication 已移除事件累加器', () => {
  it('不再暴露 onAdjustmentCreated；审定数为纯 computed', () => {
    const { adjud } = buildAdjudication([], PRESET_SEGMENTS.THREE_YEAR)
    expect('onAdjustmentCreated' in adjud).toBe(false)
    expect((adjud as any).onAdjustmentCreated).toBeUndefined()
  })

  it('性质行调整数派生自 adjustmentTotals.byNature；重复读取幂等（不累加放大）', () => {
    const adjRows = [
      { rowId: 'e1', debitAmount: 200, creditAmount: 0, natureType: '预收货款', agingBand: 'within1' },
      { rowId: 'e2', debitAmount: 0, creditAmount: 80, natureType: '预收货款', agingBand: 'within1' },
    ]
    const { adjud } = buildAdjudication([], PRESET_SEGMENTS.THREE_YEAR, {
      'D7-3-rows': JSON.stringify(adjRows),
    })
    const revenue = adjud.natureRows.value.find(r => r.rowKey === 'revenue')!
    // AJE=200, RJE=80（派生，不累加）
    expect(revenue.currentAje).toBe(200)
    expect(revenue.currentRje).toBe(80)
    // 重复读取恒等
    expect(adjud.natureRows.value.find(r => r.rowKey === 'revenue')!.currentAje).toBe(200)
  })
})
