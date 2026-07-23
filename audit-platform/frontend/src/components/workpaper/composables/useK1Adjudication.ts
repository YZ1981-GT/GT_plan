/**
 * useK1Adjudication — K1-1 审定表逻辑
 *
 * Spec: .kiro/specs/k1-other-receivables/
 * Task: 3.4
 * Requirements: 2.1-2.10
 *
 * 职责：
 * - 双区块：其他应收款(1221资产类) + 坏账准备(备抵类) + 净值
 * - 89行 × 13列 × 47公式
 * - 三角勾稽 + TB回写 + AJE/RJE 管理
 * - 从 K1-4 回写 1221/1231 账项与报表调整净额（按未审数权重分摊）
 * - EventBus publish 'substantive:adjudicated'
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import {
  calcAuditedAmount,
  calcAssetEndBalance,
  calcContraEndBalance,
  calcNetValue,
  calcTriangleReconciliation,
  calcChangeRate,
  calcSubtotal,
} from './useK1FormulaEngine'
import { readK14AdjustmentNets, type K14AdjustmentNets } from './useK1Adjustment'
import {
  K1_PORTFOLIO_ROW_DEFS,
  K1_AGING_ROW_DEFS,
  K1_NATURE_ROW_DEFS,
  K1_PORTFOLIO_COUNT,
  K1_AGING_COUNT,
  K1_NATURE_COUNT,
} from './k1AdjudicationModel'
import { aggregateK12ForK11, type K1DetailRowLike } from './k1AdjudicationSync'
import {
  computeK11ComboCrossCheck,
  draftVarianceReason,
  K1_VARIANCE_THRESHOLD,
} from './k1AdjudicationCross'
import {
  applyK14NetsToK11,
  type K14WritebackScope,
  type K14WritebackResult,
} from './k1AdjK11Writeback'

export type { K14WritebackScope, K14WritebackResult }
export { applyK14NetsToK11 }

// ─── Types ───────────────────────────────────────────────────────────────────

export interface K1AdjRow {
  rowKey: string
  label: string
  begin: number
  debit: number
  credit: number
  end: number
  priorUnadjusted: number
  priorAje: number
  priorRje: number
  priorAudited: number
  unadjusted: number
  aje: number
  rje: number
  audited: number
  changeAmount: number
  changeRate: number | null
  remark: string
}

export interface K1AdjSection {
  sectionKey: 'receivable' | 'bad-debt' | 'net-value'
  sectionLabel: string
  rows: K1AdjRow[]
  subtotalRow: K1AdjRow
}

export interface K1AdjBlockSection {
  blockKey: string
  blockLabel: string
  grossRows: K1AdjRow[]
  provisionRows: K1AdjRow[]
  netRows: K1AdjRow[]
  grossSubtotal: K1AdjRow
  provisionSubtotal: K1AdjRow
  netSubtotal: K1AdjRow
}

export interface K1ReconciliationResult {
  diff: number
  isBalanced: boolean
}

export interface K1FsReconciliation {
  interestReceivable: number
  dividendReceivable: number
  fsOtherTotal: number
  k11NetAudited: number
  fsDiff: number
  isBalanced: boolean
}

export interface K1VarianceAlert {
  rowKey: string
  label: string
  prefix: string
  changeRate: number
  hasReason: boolean
}

export interface K1TbReconciliation {
  tbReceivable: number
  tbBadDebt: number
  auditedReceivable: number
  auditedBadDebt: number
  receivableDiff: number
  badDebtDiff: number
  isBalanced: boolean
}

/** render 策略注入的 tb_balance 预填（无持久化未审数时） */
export interface K1AdjudicationPrefillBucket {
  opening?: number
  closing?: number
  debit?: number
  credit?: number
}

export interface K1AdjudicationPrefill {
  receivable_total?: K1AdjudicationPrefillBucket
  bad_debt_total?: K1AdjudicationPrefillBucket
  nature?: Record<string, K1AdjudicationPrefillBucket>
  portfolio?: Record<string, K1AdjudicationPrefillBucket>
  portfolio_provision?: Record<string, K1AdjudicationPrefillBucket>
}

export interface UseK1AdjudicationOpts {
  wpId: Ref<string>
  projectId: Ref<string>
  allResponses: Ref<Map<string, any>>
  tbData?: Ref<{ unadjusted1221: number; audited1221: number; unadjustedBadDebt: number; auditedBadDebt: number }>
  onSave?: (itemId: string, value: any) => void
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

function getVal(allResponses: Map<string, any>, itemId: string): string {
  return allResponses.get(itemId)?.remark ?? ''
}

function num(allResponses: Map<string, any>, itemId: string): number {
  const v = getVal(allResponses, itemId)
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

function _round2(n: number): number {
  return Math.round(n * 100) / 100
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useK1Adjudication(opts: UseK1AdjudicationOpts) {
  const { allResponses, onSave, tbData } = opts

  const auditNote = ref('')
  const auditConclusion = ref('')

  // ─── 构建行数据 ────────────────────────────────────────────────────────────

  function buildRow(prefix: string, rowKey: string, label: string, isAssetType: boolean): K1AdjRow {
    const id = `K1-1-${prefix}-${rowKey}`
    const begin = num(allResponses.value, `${id}-begin`)
    const debit = num(allResponses.value, `${id}-debit`)
    const credit = num(allResponses.value, `${id}-credit`)
    const end = isAssetType
      ? calcAssetEndBalance(begin, debit, credit)
      : calcContraEndBalance(begin, credit, debit)
    const priorUnadjusted = num(allResponses.value, `${id}-prior-unadj`) || begin
    const priorAje = num(allResponses.value, `${id}-prior-aje`)
    const priorRje = num(allResponses.value, `${id}-prior-rje`)
    const priorAudited = num(allResponses.value, `${id}-prior-audited`) ||
      calcAuditedAmount(priorUnadjusted, priorAje, priorRje)
    const unadjusted = num(allResponses.value, `${id}-unadj`)
    const aje = num(allResponses.value, `${id}-aje`)
    const rje = num(allResponses.value, `${id}-rje`)
    const audited = calcAuditedAmount(unadjusted, aje, rje)
    const changeAmount = _round2(audited - priorAudited)
    const changeRate = calcChangeRate(audited, priorAudited)
    const remark = getVal(allResponses.value, `${id}-remark`)
    return {
      rowKey, label, begin, debit, credit, end,
      priorUnadjusted, priorAje, priorRje, priorAudited,
      unadjusted, aje, rje, audited, changeAmount, changeRate, remark,
    }
  }

  function buildSubtotal(label: string, rows: K1AdjRow[]): K1AdjRow {
    const sum = (fn: (r: K1AdjRow) => number) => calcSubtotal(rows.map(fn))
    const audited = sum(r => r.audited)
    const priorAudited = sum(r => r.priorAudited)
    return {
      rowKey: 'subtotal', label,
      begin: sum(r => r.begin), debit: sum(r => r.debit), credit: sum(r => r.credit),
      end: sum(r => r.end),
      priorUnadjusted: sum(r => r.priorUnadjusted), priorAje: sum(r => r.priorAje),
      priorRje: sum(r => r.priorRje), priorAudited,
      unadjusted: sum(r => r.unadjusted),
      aje: sum(r => r.aje), rje: sum(r => r.rje), audited,
      changeAmount: _round2(audited - priorAudited),
      changeRate: calcChangeRate(audited, priorAudited), remark: '',
    }
  }

  function buildNetRows(grossRows: K1AdjRow[], provRows: K1AdjRow[]): K1AdjRow[] {
    return grossRows.map((g, i) => {
      const p = provRows[i]
      const priorAudited = calcNetValue(g.priorAudited, p?.priorAudited ?? 0)
      const audited = calcNetValue(g.audited, p?.audited ?? 0)
      return {
        rowKey: `net-${g.rowKey}`,
        label: g.label,
        begin: calcNetValue(g.begin, p?.begin ?? 0),
        debit: 0,
        credit: 0,
        end: calcNetValue(g.end, p?.end ?? 0),
        priorUnadjusted: calcNetValue(g.priorUnadjusted, p?.priorUnadjusted ?? 0),
        priorAje: calcNetValue(g.priorAje, p?.priorAje ?? 0),
        priorRje: calcNetValue(g.priorRje, p?.priorRje ?? 0),
        priorAudited,
        unadjusted: calcNetValue(g.unadjusted, p?.unadjusted ?? 0),
        aje: calcNetValue(g.aje, p?.aje ?? 0),
        rje: calcNetValue(g.rje, p?.rje ?? 0),
        audited,
        changeAmount: _round2(audited - priorAudited),
        changeRate: calcChangeRate(audited, priorAudited),
        remark: '',
      }
    })
  }

  function buildDistributionBlock(
    blockKey: string,
    blockLabel: string,
    defs: typeof K1_AGING_ROW_DEFS,
    grossPrefix: string,
    provPrefix: string,
  ): K1AdjBlockSection {
    const dataDefs = defs.filter((d) => !d.isSubtotal)
    const grossRows = dataDefs.map((d) =>
      buildRow(grossPrefix, d.rowKey, d.label, true),
    )
    const provisionRows = dataDefs.map((d) =>
      buildRow(provPrefix, d.rowKey, d.label, false),
    )
    const netRows = buildNetRows(grossRows, provisionRows)
    return {
      blockKey,
      blockLabel,
      grossRows,
      provisionRows,
      netRows,
      grossSubtotal: buildSubtotal('小计', grossRows),
      provisionSubtotal: buildSubtotal('小计', provisionRows),
      netSubtotal: buildSubtotal('小计', netRows),
    }
  }

  function _writeUnadj(prefix: string, rowKey: string, amount: number): void {
    const itemId = `K1-1-${prefix}-${rowKey}-unadj`
    const val = String(_round2(amount))
    allResponses.value.set(itemId, { item_id: itemId, conclusion: null, remark: val })
    onSave?.(itemId, { remark: val })
  }

  function _writeBegin(prefix: string, rowKey: string, amount: number): void {
    const itemId = `K1-1-${prefix}-${rowKey}-begin`
    const val = String(_round2(amount))
    allResponses.value.set(itemId, { item_id: itemId, conclusion: null, remark: val })
    onSave?.(itemId, { remark: val })
  }

  function _writeDebitCredit(
    prefix: string,
    rowKey: string,
    debit: number,
    credit: number,
  ): void {
    const dId = `K1-1-${prefix}-${rowKey}-debit`
    const cId = `K1-1-${prefix}-${rowKey}-credit`
    allResponses.value.set(dId, { item_id: dId, conclusion: null, remark: String(_round2(debit)) })
    allResponses.value.set(cId, { item_id: cId, conclusion: null, remark: String(_round2(credit)) })
    onSave?.(dId, { remark: String(_round2(debit)) })
    onSave?.(cId, { remark: String(_round2(credit)) })
  }

  /** 是否已有非零未审数（避免覆盖用户已编辑数据） */
  function hasPersistedUnadj(): boolean {
    for (const key of allResponses.value.keys()) {
      if (!/^K1-1-.+-unadj$/.test(key)) continue
      if (Math.abs(num(allResponses.value, key)) >= 0.005) return true
    }
    return false
  }

  function _parseK12Rows(): K1DetailRowLike[] {
    const raw = allResponses.value.get('K1-2-detail-rows')?.remark
    if (!raw) return []
    try {
      const parsed = JSON.parse(raw)
      if (!Array.isArray(parsed)) return []
      return parsed.map((r: any) => ({
        endBalance: Number(r.endBalance) || 0,
        badDebtProvision: Number(r.badDebtProvision) || 0,
        stage: Number(r.stage) || 1,
        nature: String(r.nature || ''),
        agingAudited: r.agingAudited && typeof r.agingAudited === 'object' ? r.agingAudited : {},
      }))
    } catch {
      return []
    }
  }

  function ensurePortfolioLabels(): void {
    const count = num(allResponses.value, 'K1-1-receivable-count')
    if (count <= 0) {
      const cId = 'K1-1-receivable-count'
      allResponses.value.set(cId, { item_id: cId, conclusion: null, remark: String(K1_PORTFOLIO_COUNT) })
      onSave?.(cId, { remark: String(K1_PORTFOLIO_COUNT) })
    }
    K1_PORTFOLIO_ROW_DEFS.forEach((def, i) => {
      const labelId = `K1-1-receivable-r${i}-label`
      if (!getVal(allResponses.value, labelId)) {
        allResponses.value.set(labelId, { item_id: labelId, conclusion: null, remark: def.label })
        onSave?.(labelId, { remark: def.label })
      }
      const bdLabelId = `K1-1-baddebt-r${i}-label`
      if (!getVal(allResponses.value, bdLabelId)) {
        allResponses.value.set(bdLabelId, { item_id: bdLabelId, conclusion: null, remark: def.label })
        onSave?.(bdLabelId, { remark: def.label })
      }
    })
  }

  // ─── Adjudication Sections ─────────────────────────────────────────────────

  const adjudicationSections: ComputedRef<K1AdjSection[]> = computed(() => {
    const recRows: K1AdjRow[] = []
    const recCount = num(allResponses.value, 'K1-1-receivable-count') || K1_PORTFOLIO_COUNT
    for (let i = 0; i < recCount; i++) {
      const def = K1_PORTFOLIO_ROW_DEFS[i]
      const label = getVal(allResponses.value, `K1-1-receivable-r${i}-label`) || def?.label || `项目${i + 1}`
      recRows.push(buildRow('receivable', `r${i}`, label, true))
    }
    const recSubtotal = buildSubtotal('合计', recRows)

    const bdRows: K1AdjRow[] = []
    const bdCount = num(allResponses.value, 'K1-1-baddebt-count') || K1_PORTFOLIO_COUNT
    for (let i = 0; i < bdCount; i++) {
      const def = K1_PORTFOLIO_ROW_DEFS[i]
      const label = getVal(allResponses.value, `K1-1-baddebt-r${i}-label`) || def?.label || `项目${i + 1}`
      bdRows.push(buildRow('baddebt', `r${i}`, label, false))
    }
    const bdSubtotal = buildSubtotal('合计', bdRows)

    const netRows = buildNetRows(recRows, bdRows)
    const netSubtotal = buildSubtotal('合计', netRows)

    return [
      { sectionKey: 'receivable', sectionLabel: '（一）其他应收款原值', rows: recRows, subtotalRow: recSubtotal },
      { sectionKey: 'bad-debt', sectionLabel: '（二）其他应收款坏账准备', rows: bdRows, subtotalRow: bdSubtotal },
      { sectionKey: 'net-value', sectionLabel: '（三）其他应收款净值', rows: netRows, subtotalRow: netSubtotal },
    ] as K1AdjSection[]
  })

  const agingDistribution: ComputedRef<K1AdjBlockSection> = computed(() =>
    buildDistributionBlock('aging', '二、其他应收款账龄分布', K1_AGING_ROW_DEFS, 'aging-gross', 'aging-prov'),
  )

  const natureDistribution: ComputedRef<K1AdjBlockSection> = computed(() =>
    buildDistributionBlock('nature', '三、其他应收款项性质分布', K1_NATURE_ROW_DEFS, 'nature-gross', 'nature-prov'),
  )

  const portfolioRowDefs = K1_PORTFOLIO_ROW_DEFS

  const tbReconciliation: ComputedRef<K1TbReconciliation> = computed(() => {
    const recSec = adjudicationSections.value[0]
    const bdSec = adjudicationSections.value[1]
    const auditedReceivable = recSec?.subtotalRow.audited ?? 0
    const auditedBadDebt = bdSec?.subtotalRow.audited ?? 0
    const tbReceivable = tbData?.value?.audited1221 ?? num(allResponses.value, 'K1-1-tb-receivable')
    const tbBadDebt = tbData?.value?.auditedBadDebt ?? num(allResponses.value, 'K1-1-tb-baddebt')
    const receivableDiff = auditedReceivable - tbReceivable
    const badDebtDiff = auditedBadDebt - tbBadDebt
    return {
      tbReceivable,
      tbBadDebt,
      auditedReceivable,
      auditedBadDebt,
      receivableDiff,
      badDebtDiff,
      isBalanced: Math.abs(receivableDiff) < 0.01 && Math.abs(badDebtDiff) < 0.01,
    }
  })

  const fsReconciliation: ComputedRef<K1FsReconciliation> = computed(() => {
    const netSec = adjudicationSections.value[2]
    const k11NetAudited = netSec?.subtotalRow.audited ?? 0
    const interestReceivable = num(allResponses.value, 'K1-1-fs-interest')
    const dividendReceivable = num(allResponses.value, 'K1-1-fs-dividend')
    const fsOtherTotal = num(allResponses.value, 'K1-1-fs-other-total')
    const fsDiff = k11NetAudited - fsOtherTotal
    return {
      interestReceivable,
      dividendReceivable,
      fsOtherTotal,
      k11NetAudited,
      fsDiff,
      isBalanced: fsOtherTotal <= 0 || Math.abs(fsDiff) < 0.01,
    }
  })

  const comboCrossCheck = computed(() => {
    const labels = adjudicationSections.value[0]?.rows.map((r) => r.label) ?? []
    return computeK11ComboCrossCheck(allResponses.value, labels)
  })

  const varianceAlerts: ComputedRef<K1VarianceAlert[]> = computed(() => {
    const alerts: K1VarianceAlert[] = []
    for (const sec of adjudicationSections.value.slice(0, 2)) {
      const prefix = sec.sectionKey === 'receivable' ? 'receivable' : 'baddebt'
      for (const row of sec.rows) {
        if (row.changeRate != null && Math.abs(row.changeRate) >= K1_VARIANCE_THRESHOLD) {
          alerts.push({
            rowKey: row.rowKey,
            label: row.label,
            prefix,
            changeRate: row.changeRate,
            hasReason: !!row.remark?.trim(),
          })
        }
      }
    }
    return alerts
  })

  const k14AdjustmentSync: ComputedRef<K14AdjustmentNets> = computed(() =>
    readK14AdjustmentNets(allResponses.value),
  )

  // ─── 三角勾稽 ──────────────────────────────────────────────────────────────

  const reconciliation: ComputedRef<K1ReconciliationResult> = computed(() => {
    const sec = adjudicationSections.value[0]
    if (!sec) return { diff: 0, isBalanced: true }
    const row = sec.subtotalRow
    const diff = calcTriangleReconciliation(row.begin, row.debit, row.credit, row.end)
    return { diff, isBalanced: Math.abs(diff) < 0.01 }
  })

  // ─── AJE/RJE 管理 ─────────────────────────────────────────────────────────

  function _writeField(block: 'receivable' | 'baddebt', rowKey: string, field: 'aje' | 'rje', amount: number): void {
    const itemId = `K1-1-${block}-${rowKey}-${field}`
    const val = String(_round2(amount))
    allResponses.value.set(itemId, { item_id: itemId, conclusion: null, remark: val })
    onSave?.(itemId, { remark: val })
  }

  function applyAdjustment(
    block: 'receivable' | 'baddebt',
    rowKey: string,
    type: 'aje' | 'rje',
    amount: number,
  ): void {
    _writeField(block, rowKey, type, amount)
  }

  /** @deprecated 兼容旧签名，默认写入 receivable 区块 */
  function applyAdjustmentLegacy(rowKey: string, type: 'aje' | 'rje', amount: number): void {
    const itemId = `K1-1-receivable-${rowKey}-${type}`
    const existing = num(allResponses.value, itemId)
    _writeField('receivable', rowKey, type, existing + amount)
  }

  /**
   * 从 K1-4 回写 AJE/RJE：1221→组合原值行，1231→组合坏账行（按未审数权重分摊）
   * @param scope all | receivable(1221) | baddebt(1231)
   */
  function syncEndAdjFromK14(
    recAjeNet?: number,
    recRjeNet?: number,
    bdAjeNet?: number,
    bdRjeNet?: number,
    scope: K14WritebackScope = 'all',
  ): K14WritebackResult {
    const netsOverride: Partial<K14AdjustmentNets> = {}
    if (Number.isFinite(Number(recAjeNet))) netsOverride.receivableAjeNet = Number(recAjeNet)
    if (Number.isFinite(Number(recRjeNet))) netsOverride.receivableRjeNet = Number(recRjeNet)
    if (Number.isFinite(Number(bdAjeNet))) netsOverride.badDebtAjeNet = Number(bdAjeNet)
    if (Number.isFinite(Number(bdRjeNet))) netsOverride.badDebtRjeNet = Number(bdRjeNet)

    const hasExplicit =
      Object.keys(netsOverride).length === 4 &&
      [recAjeNet, recRjeNet, bdAjeNet, bdRjeNet].every((n) => Number.isFinite(Number(n)))

    return applyK14NetsToK11(allResponses.value, onSave, {
      scope,
      nets: hasExplicit ? (netsOverride as K14AdjustmentNets) : netsOverride,
    })
  }

  /** 从 K1-2 明细同步未审数至组合/账龄/性质分布 */
  function syncUnadjFromK12(): { applied: boolean; message: string; rowCount: number } {
    const rows = _parseK12Rows()
    if (!rows.length) {
      return { applied: false, message: 'K1-2 明细表暂无数据', rowCount: 0 }
    }
    ensurePortfolioLabels()
    const agg = aggregateK12ForK11(rows)

    K1_PORTFOLIO_ROW_DEFS.forEach((_, i) => {
      _writeUnadj('receivable', `r${i}`, agg.portfolioGross[i] ?? 0)
      _writeUnadj('baddebt', `r${i}`, agg.portfolioProvision[i] ?? 0)
    })

    K1_AGING_ROW_DEFS.filter((d) => !d.isSubtotal).forEach((def, i) => {
      _writeUnadj('aging-gross', def.rowKey, agg.agingGross[i] ?? 0)
      _writeUnadj('aging-prov', def.rowKey, _round2(agg.agingProvision[i] ?? 0))
    })

    K1_NATURE_ROW_DEFS.filter((d) => !d.isSubtotal).forEach((def, i) => {
      _writeUnadj('nature-gross', def.rowKey, agg.natureGross[i] ?? 0)
      _writeUnadj('nature-prov', def.rowKey, agg.natureProvision[i] ?? 0)
    })

    const recTotal = String(_round2(agg.detailSubtotal))
    allResponses.value.set('K1-1-audited-receivable', { item_id: 'K1-1-audited-receivable', conclusion: null, remark: recTotal })
    onSave?.('K1-1-audited-receivable', { remark: recTotal })

    return {
      applied: true,
      message: `已从 K1-2 同步 ${rows.length} 户明细：原值合计 ${recTotal}`,
      rowCount: rows.length,
    }
  }

  function persistAuditedTotals(): void {
    const rec = adjudicationSections.value[0]?.subtotalRow.audited ?? 0
    const bd = adjudicationSections.value[1]?.subtotalRow.audited ?? 0
    const net = adjudicationSections.value[2]?.subtotalRow.audited ?? 0
    const recId = 'K1-1-audited-receivable'
    const bdId = 'K1-1-audited-baddebt'
    allResponses.value.set(recId, { item_id: recId, conclusion: null, remark: String(_round2(rec)) })
    allResponses.value.set(bdId, { item_id: bdId, conclusion: null, remark: String(_round2(bd)) })
    allResponses.value.set('K1-1-audited-net', { item_id: 'K1-1-audited-net', conclusion: null, remark: String(_round2(net)) })
    onSave?.(recId, { remark: String(_round2(rec)) })
    onSave?.(bdId, { remark: String(_round2(bd)) })
    onSave?.('K1-1-audited-net', { remark: String(_round2(net)) })
  }

  /**
   * 从 render adjudication_prefill 写入期初/未审数。
   * 仅在无持久化未审数时生效；性质行按 syncKey 映射，组合默认写入账龄组合。
   */
  function applyAdjudicationPrefill(prefill?: K1AdjudicationPrefill | null): boolean {
    if (!prefill || hasPersistedUnadj()) return false

    ensurePortfolioLabels()
    let wrote = false

    const natureMap = prefill.nature ?? {}
    for (const def of K1_NATURE_ROW_DEFS.filter((d) => !d.isSubtotal)) {
      const bucket = def.syncKey ? natureMap[def.syncKey] : undefined
      if (!bucket) continue
      const opening = Number(bucket.opening) || 0
      const closing = Number(bucket.closing) || 0
      if (Math.abs(opening) < 0.005 && Math.abs(closing) < 0.005) continue
      _writeBegin('nature-gross', def.rowKey, opening)
      _writeUnadj('nature-gross', def.rowKey, closing)
      wrote = true
    }

    const portfolioMap = prefill.portfolio ?? {}
    const portfolioProv = prefill.portfolio_provision ?? {}
    for (const def of K1_PORTFOLIO_ROW_DEFS) {
      const key = def.syncKey || def.rowKey
      const gross = portfolioMap[key]
      const prov = portfolioProv[key]
      if (gross) {
        const opening = Number(gross.opening) || 0
        const closing = Number(gross.closing) || 0
        if (Math.abs(opening) >= 0.005 || Math.abs(closing) >= 0.005) {
          _writeBegin('receivable', def.rowKey, opening)
          _writeUnadj('receivable', def.rowKey, closing)
          const debit = Number(gross.debit) || 0
          const credit = Number(gross.credit) || 0
          if (Math.abs(debit) >= 0.005 || Math.abs(credit) >= 0.005) {
            _writeDebitCredit('receivable', def.rowKey, debit, credit)
          }
          wrote = true
        }
      }
      if (prov) {
        const opening = Number(prov.opening) || 0
        const closing = Number(prov.closing) || 0
        if (Math.abs(opening) >= 0.005 || Math.abs(closing) >= 0.005) {
          _writeBegin('baddebt', def.rowKey, opening)
          _writeUnadj('baddebt', def.rowKey, closing)
          wrote = true
        }
      }
    }

    // 无组合拆分时：总额兜底写入账龄组合 r1
    if (!wrote) {
      const rec = prefill.receivable_total
      const bd = prefill.bad_debt_total
      if (rec && (Math.abs(Number(rec.opening) || 0) >= 0.005 || Math.abs(Number(rec.closing) || 0) >= 0.005)) {
        _writeBegin('receivable', 'r1', Number(rec.opening) || 0)
        _writeUnadj('receivable', 'r1', Number(rec.closing) || 0)
        _writeDebitCredit('receivable', 'r1', Number(rec.debit) || 0, Number(rec.credit) || 0)
        wrote = true
      }
      if (bd && (Math.abs(Number(bd.opening) || 0) >= 0.005 || Math.abs(Number(bd.closing) || 0) >= 0.005)) {
        _writeBegin('baddebt', 'r1', Number(bd.opening) || 0)
        _writeUnadj('baddebt', 'r1', Number(bd.closing) || 0)
        wrote = true
      }
    }

    if (wrote) persistAuditedTotals()
    return wrote
  }

  function writeRemark(prefix: string, rowKey: string, text: string): void {
    const itemId = `K1-1-${prefix}-${rowKey}-remark`
    allResponses.value.set(itemId, { item_id: itemId, conclusion: null, remark: text })
    onSave?.(itemId, { remark: text })
  }

  function writeRowField(prefix: string, rowKey: string, field: string, value: string | number): void {
    const itemId = `K1-1-${prefix}-${rowKey}-${field}`
    const val = String(value)
    allResponses.value.set(itemId, { item_id: itemId, conclusion: null, remark: val })
    onSave?.(itemId, { remark: val })
  }

  function writeFsField(field: 'interest' | 'dividend' | 'other-total', value: number): void {
    const itemId = `K1-1-fs-${field}`
    const val = String(_round2(value))
    allResponses.value.set(itemId, { item_id: itemId, conclusion: null, remark: val })
    onSave?.(itemId, { remark: val })
  }

  function generateVarianceReasonDrafts(): { filled: number; skipped: number } {
    let filled = 0
    let skipped = 0
    for (const sec of adjudicationSections.value.slice(0, 2)) {
      const prefix = sec.sectionKey === 'receivable' ? 'receivable' : 'baddebt'
      for (const row of sec.rows) {
        const draft = draftVarianceReason(row.label, row.changeRate)
        if (!draft) continue
        if (row.remark?.trim()) {
          skipped++
          continue
        }
        writeRemark(prefix, row.rowKey, draft)
        filled++
      }
    }
    return { filled, skipped }
  }

  // ─── Audit Note/Conclusion ─────────────────────────────────────────────────

  watch(() => allResponses.value.get('K1-1-audit-note')?.remark, (v) => {
    auditNote.value = v || ''
  }, { immediate: true })

  watch(() => allResponses.value.get('K1-1-audit-conclusion')?.remark, (v) => {
    auditConclusion.value = v || ''
  }, { immediate: true })

  // ─── Return ────────────────────────────────────────────────────────────────

  return {
    adjudicationSections,
    agingDistribution,
    natureDistribution,
    portfolioRowDefs,
    reconciliation,
    tbReconciliation,
    fsReconciliation,
    comboCrossCheck,
    varianceAlerts,
    auditNote,
    auditConclusion,
    k14AdjustmentSync,
    applyAdjustment,
    applyAdjustmentLegacy,
    syncEndAdjFromK14,
    syncUnadjFromK12,
    applyAdjudicationPrefill,
    hasPersistedUnadj,
    ensurePortfolioLabels,
    persistAuditedTotals,
    writeRemark,
    writeRowField,
    writeFsField,
    generateVarianceReasonDrafts,
  }
}
