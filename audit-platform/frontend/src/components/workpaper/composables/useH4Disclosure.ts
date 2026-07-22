/**
 * useH4Disclosure — H4 附注披露（上市 / 国企）共用取数与勾稽
 *
 * 上市：（2）工程物资分类表 ← H4-2 分类 + H4-7 减值
 * 国企：23、在建工程汇总 ← 工程物资行自 H4-1；在建工程行手工/外链
 */
import { computed, type Ref } from 'vue'
import {
  createDefaultH4ListedMaterials,
  h4ListedMaterialsNet,
  num,
  seedH4ListedMaterialsFromDetail,
  type H4ListedMaterialRow,
} from './h4ListedDisclosureModel'
import {
  createDefaultH4SoeSummary,
  seedH4SoeMaterialsFromAdjudication,
  type H4SoeSummaryRow,
} from './h4SoeDisclosureModel'

function safeParseRows<T>(jsonStr: string | null | undefined): T[] {
  if (!jsonStr) return []
  try {
    const parsed = JSON.parse(jsonStr)
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

function getNum(allResponses: Map<string, any>, itemId: string): number {
  const n = Number(allResponses.get(itemId)?.remark)
  return Number.isFinite(n) ? n : 0
}

/** 从 H4-1-rows JSON 汇总原值/减值段 */
export function summarizeH41Sections(allResponses: Map<string, any>): {
  originalEnd: number
  originalBegin: number
  impairEnd: number
  impairBegin: number
  netAudited: number
} {
  const rows = safeParseRows<any>(allResponses.get('H4-1-rows')?.remark)
  let originalEnd = 0
  let originalBegin = 0
  let impairEnd = 0
  let impairBegin = 0
  for (const r of rows) {
    if (r?.isSubtotal || r?.isTotal) continue
    // 新列：beginAudited/endAudited；兼容旧 beginBalance/audited/endBalance
    const begin =
      num(r.beginAudited)
      || num(r.beginUnadjusted) + num(r.beginAdjustment)
      || num(r.beginBalance)
    const end =
      num(r.endAudited)
      || num(r.endUnadjusted) + num(r.endAdjustment)
      || num(r.audited)
      || num(r.endBalance)
      || num(r.unadjusted) + num(r.aje) + num(r.rje)
    if (r.section === 'impairment') {
      impairBegin += begin
      impairEnd += end
    } else if (r.section === 'original') {
      originalBegin += begin
      originalEnd += end
    }
  }
  const provisionBalance = getNum(allResponses, 'H4-7-provision-balance')
  if (provisionBalance && !impairEnd) impairEnd = provisionBalance

  // fallback：H4-1-*-total / adjudicated-total 存的是净值，需加回减值还原账面余额
  if (!rows.length) {
    const netEnd = getNum(allResponses, 'H4-1-adjudicated-total') || getNum(allResponses, 'H4-1-end-total')
    const netBegin = getNum(allResponses, 'H4-1-begin-total')
    originalEnd = netEnd + impairEnd
    originalBegin = netBegin + impairBegin
  }

  const netAudited = getNum(allResponses, 'H4-1-adjudicated-total')
    || (originalEnd - impairEnd)
  return {
    originalEnd: Math.round(originalEnd * 100) / 100,
    originalBegin: Math.round(originalBegin * 100) / 100,
    impairEnd: Math.round(impairEnd * 100) / 100,
    impairBegin: Math.round(impairBegin * 100) / 100,
    netAudited: Math.round(netAudited * 100) / 100,
  }
}

/** 读取 H4-1 重大变动列表（附注键） */
export function readH41SignificantChanges(allResponses: Map<string, any>): Array<{
  name: string
  beginAudited: number
  endAudited: number
  auditedChange: number
  auditedChangeRate: number | null
}> {
  const raw = allResponses.get('H4-1-significant-changes')?.remark
  if (!raw) return []
  try {
    const arr = typeof raw === 'string' ? JSON.parse(raw) : raw
    return Array.isArray(arr) ? arr : []
  } catch {
    return []
  }
}

/** 附注说明草稿：消费重大变动列表 */
export function buildH41SignificantDisclosureNote(allResponses: Map<string, any>): string {
  const items = readH41SignificantChanges(allResponses)
  if (!items.length) return ''
  const parts = items.map((it) => {
    const rate =
      it.auditedChangeRate == null
        ? '-'
        : `${Number(it.auditedChangeRate).toLocaleString('zh-CN', { maximumFractionDigits: 2 })}%`
    return `${it.name}（变动率 ${rate}）`
  })
  return `本期工程物资净值重大变动分类：${parts.join('、')}，详见 H4-1 审计说明(1)。`
}

export function useH4Disclosure(allResponses: Ref<Map<string, any>>) {
  const h41 = computed(() => summarizeH41Sections(allResponses.value))

  const significantChanges = computed(() =>
    readH41SignificantChanges(allResponses.value),
  )

  const significantNoteDraft = computed(() =>
    buildH41SignificantDisclosureNote(allResponses.value),
  )

  const detailRows = computed(() =>
    safeParseRows<any>(allResponses.value.get('H4-2-rows')?.remark),
  )

  function pullListedMaterials(): H4ListedMaterialRow[] {
    const map = allResponses.value
    const provision = getNum(map, 'H4-7-provision-balance')
    const sections = summarizeH41Sections(map)
    return seedH4ListedMaterialsFromDetail(detailRows.value, {
      impairmentEnd: provision || sections.impairEnd,
      impairmentPrior: sections.impairBegin,
    })
  }

  function pullSoeSummary(prev?: H4SoeSummaryRow[]): H4SoeSummaryRow[] {
    const sections = summarizeH41Sections(allResponses.value)
    const mat = seedH4SoeMaterialsFromAdjudication({
      endBook: sections.originalEnd,
      endImpairment: sections.impairEnd,
      beginBook: sections.originalBegin,
      beginImpairment: sections.impairBegin,
    })
    const base = prev?.length ? prev.map((r) => ({ ...r })) : createDefaultH4SoeSummary()
    return base.map((r) => (r.key === 'materials' ? { ...mat } : r))
  }

  /** 上市净值 vs H4-1 审定净值 */
  function listedCrossCheck(rows: H4ListedMaterialRow[]): string[] {
    const warnings: string[] = []
    const net = h4ListedMaterialsNet(rows).endBalance
    const audited = h41.value.netAudited
    if (audited !== 0 && Math.abs(net - audited) >= 0.01) {
      warnings.push(
        `工程物资披露合计期末 ${net.toLocaleString('zh-CN', { minimumFractionDigits: 2 })} 与 H4-1 审定净值 ${audited.toLocaleString('zh-CN', { minimumFractionDigits: 2 })} 差异 ${Math.abs(net - audited).toLocaleString('zh-CN', { minimumFractionDigits: 2 })}，请核对分类汇总与减值。`,
      )
    }
    const sig = significantChanges.value
    if (sig.length) {
      warnings.push(
        `H4-1 识别净值重大变动 ${sig.length} 项（${sig.map((s) => s.name).join('、')}），请在附注说明中披露。`,
      )
    }
    return warnings
  }

  /** 国企工程物资行 vs H4-1 */
  function soeCrossCheck(rows: H4SoeSummaryRow[]): string[] {
    const warnings: string[] = []
    const mat = rows.find((r) => r.key === 'materials')
    if (!mat) return warnings
    const sections = h41.value
    const carrying = num(mat.endBook) - num(mat.endImpairment)
    if (sections.netAudited !== 0 && Math.abs(carrying - sections.netAudited) >= 0.01) {
      warnings.push(
        `工程物资账面价值期末 ${carrying.toLocaleString('zh-CN', { minimumFractionDigits: 2 })} 与 H4-1 审定 ${sections.netAudited.toLocaleString('zh-CN', { minimumFractionDigits: 2 })} 不一致。`,
      )
    }
    if (sections.originalEnd !== 0 && Math.abs(num(mat.endBook) - sections.originalEnd) >= 0.01) {
      warnings.push('工程物资账面余额期末与 H4-1 原值段不一致，建议「从审定取数」。')
    }
    const cip = rows.find((r) => r.key === 'cip')
    if (cip && !num(cip.endBook) && !num(cip.beginBook)) {
      warnings.push('在建工程行尚未填列；合计数披露详见 J2-1，请自 H2-1 审定录入或与报表附注勾稽。')
    }
    const sig = significantChanges.value
    if (sig.length) {
      warnings.push(
        `H4-1 净值重大变动 ${sig.length} 项，建议写入附注披露说明。`,
      )
    }
    return warnings
  }

  return {
    h41,
    significantChanges,
    significantNoteDraft,
    detailRows,
    pullListedMaterials,
    pullSoeSummary,
    listedCrossCheck,
    soeCrossCheck,
    createDefaultH4ListedMaterials,
    createDefaultH4SoeSummary,
  }
}

export default useH4Disclosure
