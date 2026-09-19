/**
 * K1 四表库取数接线守卫
 *
 * 覆盖三处「只有实测才暴露」的接线缺陷：
 * 1. 账龄段未透传 → K1-1 固定 5 年段，项目配 3 年段时 over3 丢失（Property 5）
 * 2. 坏账兜底请求用宽口径 `1231` → 把应收账款坏账算进 K1（Property 2）
 * 3. `tb_source_codes` 无消费方 → dead output（R1.7）
 *
 * spec: .kiro/specs/k1-four-table-extraction-and-disclosure-alignment/
 */
import { describe, it, expect } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { ref } from 'vue'
import { PRESET_SEGMENTS, type AgingSegment } from '@/composables/useAgingConfig'
import {
  aggregateK12ForK11,
  agingBucketLabels,
  K1_DEFAULT_AGING_SEG_KEYS,
} from '../k1AdjudicationSync'
import {
  buildK1AgingRowDefs,
  k1AgingSegmentKeys,
  K1_AGING_ROW_DEFS,
} from '../k1AdjudicationModel'
import {
  K1_BAD_DEBT_FALLBACK_STANDARD,
  hasK1TbSourceCodes,
  k1CodeListText,
  k1ExtraEntries,
  k1GrossQueryCodes,
  k1ProvisionQueryCodes,
  k1ResolvedFromLabel,
  k1SignedFormulaText,
  sumLongestPrefixOnly,
  type K1TbSourceCodes,
} from '../k1TbSourceCodes'
import { useK1Adjudication } from '../useK1Adjudication'

const THREE = PRESET_SEGMENTS.THREE_YEAR as AgingSegment[]
const FIVE = PRESET_SEGMENTS.FIVE_YEAR as AgingSegment[]

const CUSTOM: AgingSegment[] = [
  { key: 'custom-0', label: '半年以内', dayFrom: 0, dayTo: 180 },
  { key: 'custom-1', label: '半年至两年', dayFrom: 181, dayTo: 730 },
  { key: 'custom-2', label: '两年以上', dayFrom: 731, dayTo: null },
]

function detail(aging: Record<string, number>, end: number, prov = 0) {
  return { endBalance: end, badDebtProvision: prov, stage: 1, nature: '保证金', agingAudited: aging }
}

// ─── Property 5：账龄段贯通 ──────────────────────────────────────────────────

describe('K1-1 账龄行跟随项目账龄配置（R5 / Property 5）', () => {
  it('5 年段 → 6 个数据行 + 小计；3 年段 → 4 个数据行 + 小计', () => {
    const five = buildK1AgingRowDefs(FIVE)
    const three = buildK1AgingRowDefs(THREE)
    expect(five.filter((r) => !r.isSubtotal)).toHaveLength(6)
    expect(three.filter((r) => !r.isSubtotal)).toHaveLength(4)
    expect(five.at(-1)?.isSubtotal).toBe(true)
    expect(three.at(-1)?.isSubtotal).toBe(true)
  })

  it('syncKey 就是段 key（不是下标），rowKey 保持历史 a{index} 形态', () => {
    const defs = buildK1AgingRowDefs(THREE)
    expect(defs.filter((d) => !d.isSubtotal).map((d) => d.syncKey)).toEqual([
      'within1', 'y1to2', 'y2to3', 'over3',
    ])
    expect(defs.filter((d) => !d.isSubtotal).map((d) => d.rowKey)).toEqual([
      'a0', 'a1', 'a2', 'a3',
    ])
  })

  it('自定义段用自定义 label 与 key', () => {
    const defs = buildK1AgingRowDefs(CUSTOM).filter((d) => !d.isSubtotal)
    expect(defs.map((d) => d.label)).toEqual(['半年以内', '半年至两年', '两年以上'])
    expect(defs.map((d) => d.syncKey)).toEqual(['custom-0', 'custom-1', 'custom-2'])
  })

  it('空/未传段 → 回退 K1 默认 5 年段（与改动前逐字等价）', () => {
    expect(buildK1AgingRowDefs(null)).toEqual(K1_AGING_ROW_DEFS)
    expect(buildK1AgingRowDefs([])).toEqual(K1_AGING_ROW_DEFS)
    expect(k1AgingSegmentKeys()).toEqual([...K1_DEFAULT_AGING_SEG_KEYS])
  })

  it('🔴 3 年段的 over3 不再丢失（旧实现硬编码 5 年段 key）', () => {
    const rows = [detail({ within1: 100, y1to2: 50, y2to3: 20, over3: 30 }, 200)]
    const agg = aggregateK12ForK11(rows, THREE)
    expect(agg.agingSegmentKeys).toEqual(['within1', 'y1to2', 'y2to3', 'over3'])
    expect(agg.agingGross).toEqual([100, 50, 20, 30])
    // 反向自检：用默认 5 年段聚合时 over3 确实读不到（证明本断言不空转）
    const wrong = aggregateK12ForK11(rows)
    expect(wrong.agingGross.reduce((a, b) => a + b, 0)).toBe(170)
    expect(agg.agingGross.reduce((a, b) => a + b, 0)).toBe(200)
  })

  it('自定义段长度与聚合结果长度一致（Property 5）', () => {
    for (const segs of [THREE, FIVE, CUSTOM]) {
      const agg = aggregateK12ForK11([detail({ within1: 1 }, 1)], segs)
      expect(agg.agingGross).toHaveLength(segs.length)
      expect(agg.agingProvision).toHaveLength(segs.length)
    }
  })

  it('账龄细分之和不超过明细期末合计', () => {
    const rows = [
      detail({ within1: 60, y1to2: 40 }, 100, 10),
      detail({ within1: 30 }, 50, 5),
    ]
    const agg = aggregateK12ForK11(rows, FIVE)
    const sum = agg.agingGross.reduce((a, b) => a + b, 0)
    expect(sum).toBeLessThanOrEqual(agg.detailSubtotal + 1e-9)
  })

  it('坏账按账龄占比分摊，合计等于明细坏账合计', () => {
    const agg = aggregateK12ForK11([detail({ within1: 60, y1to2: 40 }, 100, 10)], FIVE)
    expect(agg.agingProvision[0]).toBeCloseTo(6, 6)
    expect(agg.agingProvision[1]).toBeCloseTo(4, 6)
    expect(agg.agingProvision.reduce((a, b) => a + b, 0)).toBeCloseTo(10, 6)
  })

  it('agingBucketLabels 跟随段配置', () => {
    expect(agingBucketLabels(THREE)).toEqual(['1年以内', '1-2年', '2-3年', '3年以上'])
    expect(agingBucketLabels()).toHaveLength(6)
  })
})

// ─── Property 2 / R4：坏账兜底口径 ───────────────────────────────────────────

describe('坏账兜底口径不得是宽前缀 1231（R4 / Property 2）', () => {
  it('兜底标准码是 1231-03，不是 1231', () => {
    expect(K1_BAD_DEBT_FALLBACK_STANDARD).toBe('1231-03')
    expect(k1ProvisionQueryCodes(null)).toEqual(['1231-03'])
    expect(k1GrossQueryCodes(null)).toEqual(['1221'])
  })

  it('溯源存在时用溯源口径', () => {
    const src: K1TbSourceCodes = {
      gross_standard: ['1221'],
      provision_standard: ['1231-03'],
    }
    expect(k1ProvisionQueryCodes(src)).toEqual(['1231-03'])
    expect(k1GrossQueryCodes(src)).toEqual(['1221'])
  })

  it('🔴 父子并存时只累加最长前缀（消除双计）', () => {
    // 实证：trial_balance 里 1231 与 1231-01..05 并存
    const rows = [
      { code: '1231', unadjusted: 1756301.88, audited: 1756301.88 },
      { code: '1231-01', unadjusted: 2324576.06, audited: 2324576.06 },
      { code: '1231-02', unadjusted: 240670353.68, audited: 240670353.68 },
      { code: '1231-03', unadjusted: 9544930.32, audited: 9544930.32 },
    ]
    // 只要 1231-03 → 只拿它
    expect(sumLongestPrefixOnly(rows, ['1231-03']).unadjusted).toBe(9544930.32)
    // 若误用宽口径 1231 → 父级 1231 被剔除（因存在更长子码），但仍会含应收账款
    const wide = sumLongestPrefixOnly(rows, ['1231']).unadjusted
    expect(wide).toBeCloseTo(2324576.06 + 240670353.68 + 9544930.32, 2)
    // 反向自检：宽口径与正确口径确实不同
    expect(wide).not.toBeCloseTo(9544930.32, 2)
  })

  it('无子码时父级自身参与求和', () => {
    const rows = [{ code: '1221', unadjusted: 100, audited: 200 }]
    expect(sumLongestPrefixOnly(rows, ['1221'])).toEqual({ unadjusted: 100, audited: 200 })
  })

  it('空输入安全', () => {
    expect(sumLongestPrefixOnly([], ['1231-03'])).toEqual({ unadjusted: 0, audited: 0 })
    expect(sumLongestPrefixOnly([{ code: '1221', unadjusted: 1, audited: 1 }], [])).toEqual({
      unadjusted: 0,
      audited: 0,
    })
  })
})

// ─── R1.7：tb_source_codes 有真实消费方 ─────────────────────────────────────

describe('tb_source_codes 不是 dead output（R1.7）', () => {
  const ROOT = resolve(__dirname, '../..')

  function read(rel: string): string {
    return readFileSync(resolve(ROOT, rel), 'utf-8')
  }

  it('宿主读 render 下发字段并透传给审定表 Tab', () => {
    const host = read('GtK1OtherReceivables.vue')
    expect(host).toMatch(/htmlData\?\.tb_source_codes/)
    expect(host).toMatch(/:tb-source-codes="tbSourceCodes"/)
  })

  it('审定表 Tab 声明 prop 并渲染溯源面板', () => {
    const tab = read('k1/core/K1TabAdjudication.vue')
    expect(tab).toMatch(/tbSourceCodes\?:\s*K1TbSourceCodes/)
    expect(tab).toMatch(/<K1FourTableSourcePanel/)
  })

  it('审定表 Tab 透传项目账龄段（否则 K1-1 固定 5 年段）', () => {
    const tab = read('k1/core/K1TabAdjudication.vue')
    expect(tab).toMatch(/agingSegments:\s*agingConfig\.segments/)
    // setup 作用域 composable 必须在 setup 顶层调用
    expect(tab).toMatch(/const\s+agingConfig\s*=\s*useAgingConfig\(/)
  })

  it('宿主坏账兜底请求不得残留宽口径字面量 1231', () => {
    const host = read('GtK1OtherReceivables.vue')
    // 反向自检：文件里确实有兜底请求代码
    expect(host).toMatch(/k1ProvisionQueryCodes/)
    expect(host).not.toMatch(/account_prefix:\s*'1231'/)
    expect(host).not.toMatch(/account_prefix:\s*'1221'/)
  })

  it('面板展示辅助函数中文化且能处理空值', () => {
    expect(k1ResolvedFromLabel('report_config')).toBe('报表规则映射')
    expect(k1ResolvedFromLabel('fallback')).toBe('兜底科目')
    expect(k1ResolvedFromLabel(undefined)).toBe('兜底科目')
    expect(k1CodeListText([])).toBe('—')
    expect(k1CodeListText(['1221', '1131'])).toBe('1221、1131')
    expect(hasK1TbSourceCodes(null)).toBe(false)
    expect(hasK1TbSourceCodes({ gross: ['1221'] })).toBe(true)
  })

  it('附加科目条目中文化（1131 应收股利 / 1132 应收利息）', () => {
    const entries = k1ExtraEntries({ extra: { '1131': ['1131'], '1132': ['1132'] } })
    expect(entries.map((e) => e.label)).toEqual(['应收股利', '应收利息'])
  })

  it('公式符号可读串按 +/− 渲染', () => {
    const txt = k1SignedFormulaText({
      signed_codes: [['1221', 1], ['1231-03', -1], ['1131', 1]],
    })
    expect(txt).toBe('+ 1221　− 1231-03　+ 1131')
    expect(k1SignedFormulaText(null)).toBe('')
  })
})

// ─── R3.3：FS 三行四表预填 ──────────────────────────────────────────────────

describe('「与经审计的财务报表核对」区三行四表预填（R3.3 / Property 4）', () => {
  it('三行都从 fs_reconciliation 写入', () => {
    const map = ref(new Map<string, any>())
    const { applyAdjudicationPrefill } = useK1Adjudication({
      wpId: ref('wp1'),
      projectId: ref('p1'),
      allResponses: map as any,
    })
    const ok = applyAdjudicationPrefill({
      fs_reconciliation: { interest: 0, dividend: 21000000, report_total: 289985715.67 },
    })
    expect(ok).toBe(true)
    expect(Number(map.value.get('K1-1-fs-dividend')?.remark)).toBe(21000000)
    expect(Number(map.value.get('K1-1-fs-other-total')?.remark)).toBe(289985715.67)
    // 金额为 0 的项不写占位
    expect(map.value.get('K1-1-fs-interest')).toBeUndefined()
  })

  it('逐项手工优先：已有非零值不覆盖', () => {
    const map = ref(new Map<string, any>())
    map.value.set('K1-1-fs-dividend', { remark: '123' })
    const { applyFsReconciliationPrefill } = useK1Adjudication({
      wpId: ref('wp1'),
      projectId: ref('p1'),
      allResponses: map as any,
    })
    const ok = applyFsReconciliationPrefill({ dividend: 999, report_total: 5 })
    expect(ok).toBe(true)
    expect(Number(map.value.get('K1-1-fs-dividend')?.remark)).toBe(123)
    expect(Number(map.value.get('K1-1-fs-other-total')?.remark)).toBe(5)
  })

  it('未审数已录时 FS 三行仍可独立补齐（旧实现整体早返回）', () => {
    const map = ref(new Map<string, any>())
    map.value.set('K1-1-receivable-r0-unadj', { remark: '999' })
    const { applyAdjudicationPrefill } = useK1Adjudication({
      wpId: ref('wp1'),
      projectId: ref('p1'),
      allResponses: map as any,
    })
    const ok = applyAdjudicationPrefill({
      portfolio: { aging: { opening: 1, closing: 2 } },
      fs_reconciliation: { dividend: 7 },
    })
    expect(ok).toBe(true)
    expect(Number(map.value.get('K1-1-fs-dividend')?.remark)).toBe(7)
    // 未审数仍不被覆盖
    expect(map.value.get('K1-1-receivable-r1-unadj')).toBeUndefined()
  })

  it('无 fs_reconciliation 时行为与改动前一致（返回 false）', () => {
    const map = ref(new Map<string, any>())
    map.value.set('K1-1-receivable-r0-unadj', { remark: '999' })
    const { applyAdjudicationPrefill } = useK1Adjudication({
      wpId: ref('wp1'),
      projectId: ref('p1'),
      allResponses: map as any,
    })
    expect(applyAdjudicationPrefill({ portfolio: { aging: { opening: 1, closing: 2 } } })).toBe(false)
  })
})
