/**
 * useH4Impairment — H4-7 工程物资减值测算 composable
 *
 * 对齐源模板「工程物资减值测算表」列结构：
 *   A类别 B名称 C是否存在迹象 D①迹象描述 E②账面价值
 *   F③公允净额 G④现值 H⑤=MAX(③,④) I⑥=MAX(②−⑤,0) J⑦已提 K⑧=⑥−⑦ L索引 M备注
 *
 * 编制路径：CAS8迹象 → 从H4-2/H4-1带入②/⑦ → 填③/④（或H4-8回写）→ 推送补提AJE至H4-3
 */
import { ref, computed, type Ref, type ComputedRef } from 'vue'
import {
  calcSubtotal,
  calcRecoverableAmount,
  calcRequiredProvision,
  calcPeriodImpairmentAdjustment,
} from './useH4FormulaEngine'
import { ITEM_H47_STOCKTAKE_CONCERNS } from './h4StocktakeCheckModel'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface H4ImpairmentSignRow {
  rowId: string
  indicator: string
  exists: '是' | '否' | '不适用' | ''
  evidence: string
}

/**
 * H4-7 测算行（对齐 Excel）
 * ⑤=MAX(③,④)  ⑥=MAX(②−⑤,0)  ⑧=⑥−⑦
 */
export interface H4ImpairmentCalcRow {
  rowId: string
  /** A 工程物资类别 */
  category: string
  /** B 工程物资名称 */
  name: string
  /** C 是否存在减值迹象 */
  hasSign: '是' | '否' | ''
  /** ① 减值迹象描述 */
  signDesc: string
  /** ② 账面价值 */
  bookValue: number
  /** ③ 公允价值减去处置费用后的净额 */
  fairValueNet: number
  /** ④ 预计未来现金流量现值 */
  pvCashFlows: number
  /** ⑤ 可收回金额 */
  recoverableAmount: number
  /** ⑥ 期末应计提减值准备 */
  requiredProvision: number
  /** ⑦ 期末账面已计提减值准备 */
  bookedProvision: number
  /** ⑧ 本期应补提（CAS8 不得转回，⑧＜0 预警） */
  periodAdjustment: number
  /** 工作底稿索引号 */
  wpIndex: string
  remark: string
  /** 上游明细行 id（自 H4-2 带入时保留） */
  sourceDetailRowId?: string
}

export const H4_MATERIAL_CATEGORIES = [
  '专用材料',
  '设备',
  '工器具',
  '其他',
] as const

export const H47_AJE_MARKER = 'H4-7-aje-auto'

export interface H41ImpairmentReconcileLine {
  category: string
  h47Required: number
  h41End: number
  diff: number
}

// ─── Constants ───────────────────────────────────────────────────────────────

const SIGNS_KEY = 'H4-7-impairment-signs'
const CALC_KEY = 'H4-7-calc-rows'
const NOTE_KEY = 'H4-7-note'
const CONCLUSION_KEY = 'H4-7-conclusion'
/** 附注/摘要消费的汇总值 */
const SUMMARY_BOOK_KEY = 'H4-7-book-value'
const SUMMARY_REC_KEY = 'H4-7-recoverable-amount'
const SUMMARY_LOSS_KEY = 'H4-7-impairment-loss'
const SUMMARY_PROV_KEY = 'H4-7-provision-balance'
const H42_ROWS_KEY = 'H4-2-rows'
const H41_ROWS_KEY = 'H4-1-rows'
const H43_ROWS_KEY = 'H4-3-rows'

/** CAS8 六项 — 措辞贴合工程物资场景 */
const DEFAULT_SIGN_INDICATORS: string[] = [
  '物资市价当期大幅度下跌，跌幅明显高于因时间推移或正常使用而预计的下跌',
  '企业经营所处的经济、技术或法律环境以及物资所处市场发生重大不利变化（如工程停缓建、规格淘汰）',
  '市场利率或其他市场投资报酬率上升，影响工程物资可收回金额的折现率',
  '有证据表明物资已经陈旧过时或实体损坏（锈蚀、变质、毁损、盘亏）',
  '物资已经或将被闲置、终止使用或计划提前处置（长期积压、报废处置）',
  '企业内部报告证据表明物资的经济绩效已经低于或将低于预期（呆滞、周转极低）',
]

// ─── Pure helpers（导出供单测） ──────────────────────────────────────────────

export function recalcH4ImpairmentCalcRow(row: H4ImpairmentCalcRow): void {
  // 无迹象：不做减值测试，维持已提现状（⑧=0）
  if (row.hasSign === '否') {
    row.recoverableAmount = Number(row.bookValue) || 0
    row.requiredProvision = Math.max(Number(row.bookedProvision) || 0, 0)
    row.periodAdjustment = 0
    return
  }
  const hasSplit = (Number(row.fairValueNet) || 0) > 0 || (Number(row.pvCashFlows) || 0) > 0
  if (hasSplit) {
    row.recoverableAmount = calcRecoverableAmount(row.fairValueNet, row.pvCashFlows)
  }
  row.requiredProvision = calcRequiredProvision(row.bookValue, row.recoverableAmount)
  row.periodAdjustment = calcPeriodImpairmentAdjustment(row.requiredProvision, row.bookedProvision)
}

export function buildH47ImpairmentAjePair(opts: {
  materialName: string
  amount: number
  seqStart: number
}): Array<Record<string, any>> {
  const amt = Math.round((Number(opts.amount) || 0) * 100) / 100
  const name = (opts.materialName || '工程物资').trim() || '工程物资'
  const desc = `补提工程物资减值准备-${name}`
  const baseId = `h47-aje-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 6)}`
  return [
    {
      rowId: `${baseId}-dr`,
      seq: opts.seqStart,
      description: desc,
      category: '账项调整',
      entryType: 'AJE',
      reportItem: '资产减值损失',
      accountCode: '6701',
      accountName: '资产减值损失',
      noteItem: '',
      summary: desc,
      debitAmount: amt,
      creditAmount: 0,
      indexRef: 'H4-7',
      refIndex: 'H4-7',
      remark: H47_AJE_MARKER,
    },
    {
      rowId: `${baseId}-cr`,
      seq: opts.seqStart + 1,
      description: desc,
      category: '账项调整',
      entryType: 'AJE',
      reportItem: '工程物资',
      accountCode: '1605',
      accountName: '工程物资减值准备',
      noteItem: '',
      summary: desc,
      debitAmount: 0,
      creditAmount: amt,
      indexRef: 'H4-7',
      refIndex: 'H4-7',
      remark: H47_AJE_MARKER,
    },
  ]
}

export function buildH47ConclusionDraft(input: {
  signYesCount: number
  calcCount: number
  totalRequired: number
  totalBooked: number
  totalAdjustment: number
  reversalCount: number
}): string {
  const fmt = (n: number) => n.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
  if (input.signYesCount === 0 && input.calcCount === 0) {
    return '经按 CAS8 六项迹象检查，未发现工程物资减值迹象，本期无需进行减值测算，减值准备计提充分。'
  }
  let text = `经检查，主体层面识别减值迹象 ${input.signYesCount} 项，对 ${input.calcCount} 项工程物资测算可收回金额。`
  text += `期末应提减值准备合计 ${fmt(input.totalRequired)}，账面已提 ${fmt(input.totalBooked)}，本期应补提 ${fmt(input.totalAdjustment)}。`
  if (input.reversalCount > 0) {
    text += `另有 ${input.reversalCount} 项测算结果低于账面已提，按 CAS8 长期资产减值不得转回，已提示关注，未建议冲回。`
  }
  text += '综上，除上述关注事项外，工程物资减值准备计提在所有重大方面公允。'
  return text
}

function _num(v: any): number {
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

function _newId(prefix: string): string {
  return `${prefix}-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 6)}`
}

function _parseJson(item: any): any {
  if (!item) return null
  const raw = item.remark ?? item.conclusion
  if (raw == null || raw === '') return null
  if (typeof raw === 'object') return raw
  try { return JSON.parse(String(raw)) } catch { return raw }
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useH4Impairment(options: {
  wpId: Ref<string>
  projectId: Ref<string>
  allResponses: Ref<Map<string, any>>
  isReadonly: Ref<boolean>
  /** @deprecated 兼容旧调用，仅 H4-7 使用 */
  section?: 'impairment' | 'recoverable'
  onSave?: (itemId: string, value: any) => void
}) {
  const signRows = ref<H4ImpairmentSignRow[]>([])
  const calcRows = ref<H4ImpairmentCalcRow[]>([])
  const auditNote = ref('')
  const conclusion = ref('')

  function _emptyCalcRow(partial: Partial<H4ImpairmentCalcRow> = {}): H4ImpairmentCalcRow {
    const row: H4ImpairmentCalcRow = {
      rowId: partial.rowId ?? _newId('h47'),
      category: partial.category ?? '',
      name: partial.name ?? '',
      hasSign: partial.hasSign === '是' || partial.hasSign === '否' ? partial.hasSign : '',
      signDesc: partial.signDesc ?? '',
      bookValue: _num(partial.bookValue),
      fairValueNet: _num(partial.fairValueNet),
      pvCashFlows: _num(partial.pvCashFlows),
      recoverableAmount: _num(partial.recoverableAmount),
      requiredProvision: 0,
      bookedProvision: _num(partial.bookedProvision),
      periodAdjustment: 0,
      wpIndex: partial.wpIndex ?? '',
      remark: partial.remark ?? '',
      sourceDetailRowId: partial.sourceDetailRowId,
    }
    recalcH4ImpairmentCalcRow(row)
    return row
  }

  function _mapCalcRow(raw: any): H4ImpairmentCalcRow {
    return _emptyCalcRow({
      rowId: raw.rowId,
      category: raw.category ?? '',
      name: raw.name ?? raw.assetName ?? '',
      hasSign: raw.hasSign === '是' || raw.hasSign === '否'
        ? raw.hasSign
        : (raw.hasIndication === 'Y' ? '是' : raw.hasIndication === 'N' ? '否' : ''),
      signDesc: raw.signDesc ?? raw.indicationDesc ?? '',
      bookValue: raw.bookValue,
      fairValueNet: raw.fairValueNet ?? raw.fairValueLessDisposal,
      pvCashFlows: raw.pvCashFlows ?? raw.dcfValue,
      recoverableAmount: raw.recoverableAmount,
      bookedProvision: raw.bookedProvision ?? raw.alreadyProvided,
      wpIndex: raw.wpIndex ?? raw.indexRef ?? '',
      remark: raw.remark ?? '',
      sourceDetailRowId: raw.sourceDetailRowId,
    })
  }

  function _defaultSigns(): H4ImpairmentSignRow[] {
    return DEFAULT_SIGN_INDICATORS.map((indicator, i) => ({
      rowId: `sign-${i + 1}`,
      indicator,
      exists: '' as const,
      evidence: '',
    }))
  }

  function _getJson(itemId: string): any {
    return _parseJson(options.allResponses.value.get(itemId))
  }

  function _getString(itemId: string): string {
    const item = options.allResponses.value.get(itemId)
    return String(item?.remark ?? item?.conclusion ?? '')
  }

  function _persistSigns(): void {
    options.onSave?.(SIGNS_KEY, signRows.value.map(r => ({
      rowId: r.rowId,
      indicator: r.indicator,
      exists: r.exists,
      evidence: r.evidence,
    })))
  }

  function _persistCalc(): void {
    const payload = calcRows.value.map(r => ({
      rowId: r.rowId,
      category: r.category,
      name: r.name,
      hasSign: r.hasSign,
      signDesc: r.signDesc,
      bookValue: r.bookValue,
      fairValueNet: r.fairValueNet,
      pvCashFlows: r.pvCashFlows,
      recoverableAmount: r.recoverableAmount,
      requiredProvision: r.requiredProvision,
      bookedProvision: r.bookedProvision,
      periodAdjustment: r.periodAdjustment,
      wpIndex: r.wpIndex,
      remark: r.remark,
      sourceDetailRowId: r.sourceDetailRowId,
    }))
    options.onSave?.(CALC_KEY, payload)

    // 同步摘要键（附注披露消费）
    // impairment-loss = 本期补提⑧>0（附注「本期计提」）
    // provision-balance = 期末应提⑥（附注「减值准备」余额）
    const book = calcSubtotal(calcRows.value.map(r => r.bookValue))
    const rec = calcSubtotal(calcRows.value.map(r => r.recoverableAmount))
    const periodLoss = calcSubtotal(calcRows.value.map(r => Math.max(r.periodAdjustment, 0)))
    const endingProv = calcSubtotal(calcRows.value.map(r => r.requiredProvision))
    options.onSave?.(SUMMARY_BOOK_KEY, book)
    options.onSave?.(SUMMARY_REC_KEY, rec)
    options.onSave?.(SUMMARY_LOSS_KEY, periodLoss)
    options.onSave?.(SUMMARY_PROV_KEY, endingProv)
  }

  function load(): void {
    const signsRaw = _getJson(SIGNS_KEY)
    if (Array.isArray(signsRaw) && signsRaw.length > 0) {
      signRows.value = signsRaw.map((r: any, i: number) => ({
        rowId: r.rowId ?? `sign-${i + 1}`,
        indicator: r.indicator ?? DEFAULT_SIGN_INDICATORS[i] ?? '',
        exists: (r.exists === '是' || r.exists === '否' || r.exists === '不适用') ? r.exists : '',
        evidence: String(r.evidence ?? ''),
      }))
      // 补齐缺失的默认迹象行
      if (signRows.value.length < DEFAULT_SIGN_INDICATORS.length) {
        for (let i = signRows.value.length; i < DEFAULT_SIGN_INDICATORS.length; i++) {
          signRows.value.push({
            rowId: `sign-${i + 1}`,
            indicator: DEFAULT_SIGN_INDICATORS[i],
            exists: '',
            evidence: '',
          })
        }
      }
    } else {
      signRows.value = _defaultSigns()
    }

    const calcRaw = _getJson(CALC_KEY)
    calcRows.value = Array.isArray(calcRaw) ? calcRaw.map(_mapCalcRow) : []

    auditNote.value = _getString(NOTE_KEY)
    conclusion.value = _getString(CONCLUSION_KEY)
  }

  // ─── Computed ──────────────────────────────────────────────────────────────

  const signYesCount: ComputedRef<number> = computed(() =>
    signRows.value.filter(r => r.exists === '是').length,
  )

  const hasImpairmentSign: ComputedRef<boolean> = computed(() =>
    signYesCount.value > 0 || calcRows.value.some(r => r.hasSign === '是'),
  )

  const totalBookValue = computed(() => calcSubtotal(calcRows.value.map(r => r.bookValue)))
  const totalRecoverable = computed(() => calcSubtotal(calcRows.value.map(r => r.recoverableAmount)))
  const totalRequiredProvision = computed(() => calcSubtotal(calcRows.value.map(r => r.requiredProvision)))
  const totalBookedProvision = computed(() => calcSubtotal(calcRows.value.map(r => r.bookedProvision)))
  const totalPeriodAdjustment = computed(() => calcSubtotal(calcRows.value.map(r => r.periodAdjustment)))

  const cas8ReversalRows = computed(() =>
    calcRows.value.filter(r => r.periodAdjustment < -0.005),
  )

  const missingRecoverableRows = computed(() =>
    calcRows.value.filter(r =>
      r.hasSign === '是'
      && r.bookValue > 0
      && r.fairValueNet <= 0
      && r.pvCashFlows <= 0
      && r.recoverableAmount <= 0,
    ),
  )

  const supplementRows = computed(() =>
    calcRows.value.filter(r => r.periodAdjustment > 0.005),
  )

  const totalSupplement = computed(() =>
    supplementRows.value.reduce((s, r) => s + r.periodAdjustment, 0),
  )

  // ─── Actions ───────────────────────────────────────────────────────────────

  function updateSignCell(rowId: string, field: 'exists' | 'evidence', value: any): void {
    if (options.isReadonly.value) return
    const row = signRows.value.find(r => r.rowId === rowId)
    if (!row) return
    if (field === 'exists') {
      row.exists = (value === '是' || value === '否' || value === '不适用') ? value : ''
    } else {
      row.evidence = String(value ?? '')
    }
    _persistSigns()
  }

  function updateCalcCell(rowId: string, field: keyof H4ImpairmentCalcRow, value: any): void {
    if (options.isReadonly.value) return
    const row = calcRows.value.find(r => r.rowId === rowId)
    if (!row) return
    const formulaFields: Array<keyof H4ImpairmentCalcRow> = [
      'recoverableAmount', 'requiredProvision', 'periodAdjustment',
    ]
    if (formulaFields.includes(field)) return

    if (field === 'hasSign') {
      row.hasSign = (value === '是' || value === '否') ? value : ''
    } else if (['bookValue', 'fairValueNet', 'pvCashFlows', 'bookedProvision'].includes(field)) {
      ;(row as any)[field] = _num(value)
    } else if (field === 'sourceDetailRowId') {
      row.sourceDetailRowId = value ? String(value) : undefined
    } else {
      ;(row as any)[field] = String(value ?? '')
    }
    recalcH4ImpairmentCalcRow(row)
    _persistCalc()
  }

  /** 批量更新（UI 便捷 API） */
  function updateCalcRow(rowId: string, patch: Partial<H4ImpairmentCalcRow>): void {
    if (options.isReadonly.value) return
    const row = calcRows.value.find(r => r.rowId === rowId)
    if (!row) return
    const formulaFields = new Set(['recoverableAmount', 'requiredProvision', 'periodAdjustment'])
    for (const [field, value] of Object.entries(patch)) {
      if (formulaFields.has(field)) continue
      if (field === 'hasSign') {
        row.hasSign = (value === '是' || value === '否') ? value : ''
      } else if (['bookValue', 'fairValueNet', 'pvCashFlows', 'bookedProvision'].includes(field)) {
        ;(row as any)[field] = _num(value)
      } else if (field === 'sourceDetailRowId') {
        row.sourceDetailRowId = value ? String(value) : undefined
      } else if (field in row) {
        ;(row as any)[field] = String(value ?? '')
      }
    }
    recalcH4ImpairmentCalcRow(row)
    _persistCalc()
  }

  function addCalcRow(name = ''): void {
    if (options.isReadonly.value) return
    calcRows.value.push(_emptyCalcRow({ name, hasSign: '是' }))
    _persistCalc()
  }

  function removeCalcRow(rowId: string): void {
    if (options.isReadonly.value) return
    const idx = calcRows.value.findIndex(r => r.rowId === rowId)
    if (idx < 0) return
    calcRows.value.splice(idx, 1)
    _persistCalc()
  }

  /** 从 H4-2 明细带入类别/名称/期末账面价值 */
  function importFromH42(): { ok: boolean; added: number; updated: number; message: string } {
    if (options.isReadonly.value) return { ok: false, added: 0, updated: 0, message: '只读模式' }
    const raw = _getJson(H42_ROWS_KEY)
    if (!Array.isArray(raw) || raw.length === 0) {
      return { ok: false, added: 0, updated: 0, message: 'H4-2 暂无明细行数据' }
    }

    let added = 0
    let updated = 0
    for (const d of raw) {
      const name = String(d.name ?? '').trim()
      if (!name) continue
      const endAmt = _num(d.bookValueEnd ?? d.endAmount)
      const category = String(d.category ?? '')
      const detailId = String(d.rowId ?? '')
      const existing = calcRows.value.find(r =>
        (detailId && r.sourceDetailRowId === detailId)
        || (r.name === name && r.category === category),
      )
      if (existing) {
        existing.bookValue = endAmt
        existing.category = category || existing.category
        if (detailId) existing.sourceDetailRowId = detailId
        recalcH4ImpairmentCalcRow(existing)
        updated++
      } else {
        calcRows.value.push(_emptyCalcRow({
          name,
          category,
          bookValue: endAmt,
          hasSign: '',
          sourceDetailRowId: detailId || undefined,
        }))
        added++
      }
    }
    _persistCalc()
    return {
      ok: true,
      added,
      updated,
      message: `已从 H4-2 带入：新增 ${added}、更新账面 ${updated}`,
    }
  }

  /** 自 H4-6 推送的减值关注一键落成测算行 */
  function importFromStocktakeConcerns(): { added: number; refreshed: number; message: string } {
    if (options.isReadonly.value) {
      return { added: 0, refreshed: 0, message: '只读模式' }
    }
    const payload = _getJson(ITEM_H47_STOCKTAKE_CONCERNS)
    const items: any[] = Array.isArray(payload?.items) ? payload.items : []
    if (!items.length) {
      return { added: 0, refreshed: 0, message: 'H4-6 暂无减值关注，请先在盘点检查表执行「推送减值关注」' }
    }

    // 主体迹象：实体损坏 / 闲置积压 — 标为「是」
    const damageSign = signRows.value.find(r => /毁损|损坏|盘亏|陈旧/.test(r.indicator))
    const idleSign = signRows.value.find(r => /闲置|积压|提前处置/.test(r.indicator))
    const hasDamage = items.some((c: any) =>
      (c.reasons || []).some((x: string) => /毁损|待报废|盘亏/.test(x)) || c.result === '盘亏',
    )
    const hasIdle = items.some((c: any) =>
      (c.reasons || []).some((x: string) => /闲置|积压/.test(x)),
    )
    if (damageSign && hasDamage && damageSign.exists !== '是') {
      damageSign.exists = '是'
      damageSign.evidence = damageSign.evidence || `H4-6 推送 ${items.length} 项关注（含毁损/盘亏）`
    }
    if (idleSign && hasIdle && idleSign.exists !== '是') {
      idleSign.exists = '是'
      idleSign.evidence = idleSign.evidence || `H4-6 推送 ${items.length} 项关注（含闲置/积压）`
    }
    _persistSigns()

    let added = 0
    let refreshed = 0
    for (const c of items) {
      const name = String(c.name ?? '').trim()
      if (!name) continue
      const sourceId = String(c.sourceRowId ?? '')
      const reasons = Array.isArray(c.reasons) ? c.reasons.join('、') : String(c.qualityStatus || c.result || '盘点关注')
      const existing = calcRows.value.find(r =>
        (sourceId && r.sourceDetailRowId === `h46:${sourceId}`)
        || r.name === name
        || r.remark.includes(`来源H4-6/${sourceId}`),
      )
      if (!existing) {
        calcRows.value.push(_emptyCalcRow({
          name,
          hasSign: '是',
          signDesc: reasons,
          bookValue: _num(c.bookAmount),
          wpIndex: 'H4-6',
          remark: `来源H4-6/${sourceId || name}`,
          sourceDetailRowId: sourceId ? `h46:${sourceId}` : undefined,
        }))
        added++
      } else {
        existing.hasSign = '是'
        if (!existing.signDesc) existing.signDesc = reasons
        if (_num(c.bookAmount) > 0 && !existing.bookValue) existing.bookValue = _num(c.bookAmount)
        if (!existing.wpIndex) existing.wpIndex = 'H4-6'
        existing.remark = existing.remark || `来源H4-6/${sourceId || name}`
        recalcH4ImpairmentCalcRow(existing)
        refreshed++
      }
    }
    _persistCalc()
    return {
      added,
      refreshed,
      message: `自 H4-6 引入：新增 ${added}、刷新 ${refreshed}，共 ${items.length} 项`,
    }
  }

  /** 读取已推送关注条数（供 UI） */
  function stocktakeConcernCount(): number {
    const payload = _getJson(ITEM_H47_STOCKTAKE_CONCERNS)
    return Array.isArray(payload?.items) ? payload.items.length : 0
  }

  /** 按类别匹配 H4-1 减值段期末余额，写入⑦账面已提 */
  function importBookedFromH41(): { ok: boolean; matched: number; message: string } {
    if (options.isReadonly.value) return { ok: false, matched: 0, message: '只读模式' }
    const raw = _getJson(H41_ROWS_KEY)
    if (!Array.isArray(raw) || raw.length === 0) {
      return { ok: false, matched: 0, message: 'H4-1 暂无审定表数据' }
    }
    const impairByName = new Map<string, number>()
    for (const r of raw) {
      if (r.section !== 'impairment' || r.isSubtotal || r.isTotal) continue
      const name = String(r.name ?? '').trim()
      if (!name) continue
      // 新字段 endAudited；兼容旧 endBalance/audited/unadjusted
      const endAud =
        r.endAudited != null
          ? _num(r.endAudited)
          : _num(r.endBalance ?? r.audited ?? (
            _num(r.endUnadjusted ?? r.unadjusted) + _num(r.endAdjustment ?? r.aje) + _num(r.rje)
          ))
      impairByName.set(name, endAud)
    }
    if (impairByName.size === 0) {
      return { ok: false, matched: 0, message: 'H4-1 减值段无分类行' }
    }

    let matched = 0
    for (const row of calcRows.value) {
      const key = (row.category || '').trim()
      if (key && impairByName.has(key)) {
        row.bookedProvision = impairByName.get(key)!
        recalcH4ImpairmentCalcRow(row)
        matched++
      }
    }
    // 若按类别未匹配且测算表为空分类、H4-1仅一行减值，则均摊/整额写入合计逻辑：整额写入首行
    if (matched === 0 && calcRows.value.length > 0 && impairByName.size === 1) {
      const only = [...impairByName.values()][0]
      for (const row of calcRows.value) {
        row.bookedProvision = only
        recalcH4ImpairmentCalcRow(row)
        matched++
      }
    }
    _persistCalc()
    return {
      ok: matched > 0,
      matched,
      message: matched > 0
        ? `已从 H4-1 减值段写入⑦：匹配 ${matched} 行`
        : '未能按类别匹配 H4-1 减值段，请手工填写⑦',
    }
  }

  /** 推送⑧>0 补提 AJE 草稿至 H4-3（CAS8 负值跳过） */
  function pushAjeDraftToH43(): {
    ok: boolean
    added: number
    skippedReversal: number
    amount: number
    message: string
  } {
    if (options.isReadonly.value) {
      return { ok: false, added: 0, skippedReversal: 0, amount: 0, message: '只读模式' }
    }
    const toPush = supplementRows.value
    const skippedReversal = cas8ReversalRows.value.length
    if (toPush.length === 0) {
      return {
        ok: false,
        added: 0,
        skippedReversal,
        amount: 0,
        message: skippedReversal > 0
          ? `无补提项；有 ${skippedReversal} 项⑧为负（CAS8不得转回），未生成冲回分录`
          : '本期⑧均为0，无需生成调整分录',
      }
    }

    let existing: any[] = []
    const raw = _getJson(H43_ROWS_KEY)
    if (Array.isArray(raw)) existing = raw
    existing = existing.filter((r: any) => r?.remark !== H47_AJE_MARKER)

    let seq = existing.reduce((m: number, r: any) => Math.max(m, _num(r.seq)), 0) + 1
    const newRows: any[] = []
    for (const calc of toPush) {
      const pair = buildH47ImpairmentAjePair({
        materialName: calc.name,
        amount: calc.periodAdjustment,
        seqStart: seq,
      })
      newRows.push(...pair)
      seq += pair.length
    }

    const merged = [...existing, ...newRows].map((r, i) => ({ ...r, seq: i + 1 }))
    options.onSave?.(H43_ROWS_KEY, merged)

    const amount = toPush.reduce((s, r) => s + r.periodAdjustment, 0)
    let message = `已向 H4-3 推送 ${newRows.length} 条 AJE 草稿（补提合计 ${amount.toLocaleString('zh-CN', { maximumFractionDigits: 2 })}）`
    if (skippedReversal > 0) {
      message += `；另有 ${skippedReversal} 项拟冲回已跳过（CAS8）`
    }
    return { ok: true, added: newRows.length, skippedReversal, amount, message }
  }

  /** 核对 H4-7 ⑥应提（按类别）与 H4-1 减值段期末 */
  function reconcileWithH41(): {
    ok: boolean
    isMatch: boolean
    totalDiff: number
    lines: H41ImpairmentReconcileLine[]
    message: string
  } {
    const raw = _getJson(H41_ROWS_KEY)
    const h41ByCat = new Map<string, number>()
    if (Array.isArray(raw)) {
      for (const r of raw) {
        if (r.section !== 'impairment' || r.isSubtotal || r.isTotal) continue
        const name = String(r.name ?? '').trim()
        if (!name) continue
        const endAud =
          r.endAudited != null
            ? _num(r.endAudited)
            : _num(r.endBalance ?? r.audited ?? (
              _num(r.endUnadjusted ?? r.unadjusted)
              + _num(r.endAdjustment ?? r.aje)
              + _num(r.rje)
            ))
        h41ByCat.set(name, endAud)
      }
    }

    const h47ByCat = new Map<string, number>()
    for (const row of calcRows.value) {
      const key = (row.category || row.name || '未分类').trim()
      h47ByCat.set(key, (h47ByCat.get(key) || 0) + row.requiredProvision)
    }

    const cats = new Set([...h47ByCat.keys(), ...h41ByCat.keys()])
    const lines: H41ImpairmentReconcileLine[] = []
    let totalDiff = 0
    for (const category of cats) {
      const h47Required = h47ByCat.get(category) || 0
      const h41End = h41ByCat.get(category) || 0
      const diff = Math.round((h47Required - h41End) * 100) / 100
      totalDiff += diff
      lines.push({ category, h47Required, h41End, diff })
    }
    totalDiff = Math.round(totalDiff * 100) / 100
    const isMatch = Math.abs(totalDiff) < 0.01 && lines.every(l => Math.abs(l.diff) < 0.01)
    const hasH41 = h41ByCat.size > 0
    const hasH47 = calcRows.value.length > 0
    if (!hasH47) {
      return { ok: false, isMatch: false, totalDiff: 0, lines, message: 'H4-7 尚无测算行' }
    }
    if (!hasH41) {
      return { ok: false, isMatch: false, totalDiff, lines, message: 'H4-1 减值段无分类行，请先在审定表建减值分类' }
    }
    return {
      ok: true,
      isMatch,
      totalDiff,
      lines,
      message: isMatch
        ? `H4-7 应提与 H4-1 减值段一致（差额 ${totalDiff.toFixed(2)}）`
        : `H4-7 应提与 H4-1 减值段差额 ${totalDiff.toLocaleString('zh-CN', { maximumFractionDigits: 2 })}，可回写 H4-1`,
    }
  }

  /**
   * 将 H4-7 ⑥应提按类别回写 H4-1 减值段：
   * - 匹配已有分类行：写入期末未审=应提，期末账项调整清零（审定=应提）
   * - 无匹配时新建减值分类行（对齐 H4-1 新列结构）
   */
  function applyRequiredToH41(): {
    ok: boolean
    updated: number
    created: number
    message: string
  } {
    if (options.isReadonly.value) {
      return { ok: false, updated: 0, created: 0, message: '只读模式' }
    }
    if (calcRows.value.length === 0) {
      return { ok: false, updated: 0, created: 0, message: 'H4-7 尚无测算行' }
    }

    const h47ByCat = new Map<string, number>()
    for (const row of calcRows.value) {
      const key = (row.category || '其他').trim() || '其他'
      h47ByCat.set(key, (h47ByCat.get(key) || 0) + row.requiredProvision)
    }

    let existing: any[] = []
    const raw = _getJson(H41_ROWS_KEY)
    if (Array.isArray(raw)) existing = raw.map((r: any) => ({ ...r }))

    let updated = 0
    let created = 0
    for (const [category, required] of h47ByCat) {
      const idx = existing.findIndex(
        (r: any) => r.section === 'impairment' && !r.isSubtotal && !r.isTotal
          && String(r.name ?? '').trim() === category,
      )
      if (idx >= 0) {
        const beginUnadj = _num(existing[idx].beginUnadjusted ?? existing[idx].beginBalance)
        const beginAdj = _num(existing[idx].beginAdjustment)
        existing[idx] = {
          ...existing[idx],
          section: 'impairment',
          name: category,
          beginUnadjusted: beginUnadj,
          beginAdjustment: beginAdj,
          beginAudited: beginUnadj + beginAdj,
          endUnadjusted: required,
          endAdjustment: 0,
          endAudited: required,
          // 清除旧字段，避免二次加载歧义
          beginBalance: undefined,
          debitAmount: undefined,
          creditAmount: undefined,
          endBalance: undefined,
          unadjusted: undefined,
          aje: undefined,
          rje: undefined,
          audited: undefined,
        }
        updated++
      } else {
        existing.push({
          rowId: _newId('h41-imp'),
          name: category,
          section: 'impairment',
          beginUnadjusted: 0,
          beginAdjustment: 0,
          beginAudited: 0,
          endUnadjusted: required,
          endAdjustment: 0,
          endAudited: required,
        })
        created++
      }
    }

    options.onSave?.(H41_ROWS_KEY, existing)
    options.onSave?.(SUMMARY_PROV_KEY, totalRequiredProvision.value)
    options.onSave?.(SUMMARY_LOSS_KEY, totalSupplement.value)

    return {
      ok: true,
      updated,
      created,
      message: `已回写 H4-1 减值段：更新 ${updated}、新建 ${created}（按⑥应提）`,
    }
  }

  function saveNote(note: string): void {
    if (options.isReadonly.value) return
    auditNote.value = note
    options.onSave?.(NOTE_KEY, note)
  }

  function saveConclusion(text: string): { ok: boolean; message?: string } {
    if (options.isReadonly.value) return { ok: false, message: '只读模式' }
    conclusion.value = text
    options.onSave?.(CONCLUSION_KEY, text)
    return { ok: true }
  }

  function fillConclusionDraft(): string {
    const text = buildH47ConclusionDraft({
      signYesCount: signYesCount.value,
      calcCount: calcRows.value.length,
      totalRequired: totalRequiredProvision.value,
      totalBooked: totalBookedProvision.value,
      totalAdjustment: Math.max(totalPeriodAdjustment.value, 0),
      reversalCount: cas8ReversalRows.value.length,
    })
    saveConclusion(text)
    return text
  }

  // 初始加载
  load()

  return {
    signRows,
    calcRows,
    auditNote,
    conclusion,
    signYesCount,
    hasImpairmentSign,
    totalBookValue,
    totalRecoverable,
    totalRequiredProvision,
    totalBookedProvision,
    totalPeriodAdjustment,
    cas8ReversalRows,
    missingRecoverableRows,
    supplementRows,
    totalSupplement,
    updateSignCell,
    updateCalcCell,
    updateCalcRow,
    addCalcRow,
    removeCalcRow,
    importFromH42,
    importFromStocktakeConcerns,
    stocktakeConcernCount,
    importBookedFromH41,
    pushAjeDraftToH43,
    reconcileWithH41,
    applyRequiredToH41,
    saveNote,
    saveConclusion,
    fillConclusionDraft,
    load,
  }
}

export default useH4Impairment
