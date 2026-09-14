/**
 * useI1UsefulLifeCheck — I1-7 无形资产使用寿命检查
 *
 * 对齐致同 Excel「使用寿命检查表I1-7」编制逻辑：
 * 1. 三路径判定：合同/法定权利 → 到期续约 → 无法定年限估计
 * 2. 使用寿命不确定：记录管理层判断依据，并做管理层询问
 * 3. 询问：是否识别出有限寿命因素、是否按原定用途继续使用
 *
 * 数字化增强（Req 8）：
 * - 剩余年限公式、本期变更（CAS28）、行结论
 * - 从 I1-2 带入名称/寿命/净值；不确定项联动 I1-12
 *
 * Spec: .kiro/specs/i1-intangible-assets/ | Requirements: 8.1-8.3
 */
import { ref, computed, watch, type Ref } from 'vue'

export const I1_USEFUL_LIFE_ROWS_KEY = 'I1-7-rows'
export const I1_USEFUL_LIFE_INQUIRY_KEY = 'I1-7-inquiry-rows'
export const I1_USEFUL_LIFE_NOTE_KEY = 'I1-7-audit-note'
export const I1_USEFUL_LIFE_CONCLUSION_KEY = 'I1-7-conclusion'
export const I1_USEFUL_LIFE_PUBLISH_KEY = 'I1-7-indefinite-list'
const ITEM_ID_DETAIL = 'I1-2-rows'

export type Yn = 'Y' | 'N' | ''

export interface I1UsefulLifeRow {
  rowId: string
  name: string
  /** 账面确定的使用寿命（月）；0 = 不确定/不摊销 */
  usefulLifeMonths: number
  /** 已用年限（年） */
  usedYears: number
  /** 账面净值（自 I1-2，供询问表） */
  netBookValue: number
  /** 合同性权利或其他法定权利 — 是否适用 */
  legalApplicable: Yn
  /** 规定年限（年） */
  legalPrescribedYears: number | null
  /** 已确定的使用寿命（法定路径，年或文字） */
  legalDeterminedLife: string
  /** 权利到期后续约 — 是否适用 */
  renewalApplicable: Yn
  /** 续约期计入使用寿命的年限 */
  renewalYearsInLife: number | null
  /** 已确定的使用寿命（续约路径） */
  renewalDeterminedLife: string
  /** 没有法定使用年限 — 是否估计使用寿命 */
  noLegalEstimate: Yn
  /** 估计是否合理 */
  noLegalReasonable: Yn
  /** 是否属于使用寿命不确定 */
  isIndefinite: Yn
  /** 管理层对“使用寿命不确定”的判断依据 */
  indefiniteJudgmentBasis: string
  /** 相关文件索引号 */
  docIndex: string
  remark: string
  /** 寿命依据摘要（数字化增强） */
  lifeBasis: string
  /** 本期是否变更 */
  isChanged: string
  changeReason: string
  conclusion: string
  sourceDetailRowId?: string
}

export interface I1UsefulLifeInquiryRow {
  rowId: string
  name: string
  netBookValue: number
  /** 是否识别出任何潜在因素导致该项资产拥有有限的使用寿命 */
  identifiedFiniteFactors: Yn
  /** 是否按照原定用途继续使用该资产 */
  continuedOriginalUse: Yn
  findings: string
}

function _genId(prefix: string): string {
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
}

function _getNum(v: unknown): number {
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

function _getYn(v: unknown): Yn {
  const s = String(v ?? '').trim().toUpperCase()
  if (s === 'Y' || s === '是' || s === 'TRUE' || s === '1') return 'Y'
  if (s === 'N' || s === '否' || s === 'FALSE' || s === '0') return 'N'
  return ''
}

export function blankUsefulLifeRow(name = ''): I1UsefulLifeRow {
  return {
    rowId: _genId('ul'),
    name,
    usefulLifeMonths: 120,
    usedYears: 0,
    netBookValue: 0,
    legalApplicable: '',
    legalPrescribedYears: null,
    legalDeterminedLife: '',
    renewalApplicable: '',
    renewalYearsInLife: null,
    renewalDeterminedLife: '',
    noLegalEstimate: '',
    noLegalReasonable: '',
    isIndefinite: 'N',
    indefiniteJudgmentBasis: '',
    docIndex: '',
    remark: '',
    lifeBasis: '',
    isChanged: '否',
    changeReason: '',
    conclusion: '',
  }
}

export function blankInquiryRow(name = '', netBookValue = 0): I1UsefulLifeInquiryRow {
  return {
    rowId: _genId('inq'),
    name,
    netBookValue,
    identifiedFiniteFactors: '',
    continuedOriginalUse: '',
    findings: '',
  }
}

/** 剩余年限（年）= 原始寿命月/12 − 已用年限；不确定返回 null */
export function calcRemainingYears(row: I1UsefulLifeRow): number | null {
  if (isIndefiniteRow(row)) return null
  return row.usefulLifeMonths / 12 - (row.usedYears || 0)
}

export function isIndefiniteRow(row: I1UsefulLifeRow): boolean {
  return row.isIndefinite === 'Y' || row.usefulLifeMonths === 0
}

function _normalizeRow(raw: any): I1UsefulLifeRow {
  const months = _getNum(raw.usefulLifeMonths)
  let isIndefinite = _getYn(raw.isIndefinite)
  if (!isIndefinite && months === 0) isIndefinite = 'Y'
  if (!isIndefinite) isIndefinite = 'N'

  return {
    rowId: raw.rowId || _genId('ul'),
    name: raw.name || '',
    usefulLifeMonths: months,
    usedYears: _getNum(raw.usedYears),
    netBookValue: _getNum(raw.netBookValue ?? raw.netValue),
    legalApplicable: _getYn(raw.legalApplicable),
    legalPrescribedYears: raw.legalPrescribedYears == null || raw.legalPrescribedYears === ''
      ? null
      : _getNum(raw.legalPrescribedYears),
    legalDeterminedLife: raw.legalDeterminedLife ?? '',
    renewalApplicable: _getYn(raw.renewalApplicable),
    renewalYearsInLife: raw.renewalYearsInLife == null || raw.renewalYearsInLife === ''
      ? null
      : _getNum(raw.renewalYearsInLife),
    renewalDeterminedLife: raw.renewalDeterminedLife ?? '',
    noLegalEstimate: _getYn(raw.noLegalEstimate),
    noLegalReasonable: _getYn(raw.noLegalReasonable),
    isIndefinite,
    indefiniteJudgmentBasis: raw.indefiniteJudgmentBasis ?? '',
    docIndex: raw.docIndex ?? '',
    remark: raw.remark ?? '',
    lifeBasis: raw.lifeBasis ?? '',
    isChanged: raw.isChanged === '是' || raw.isChanged === 'Y' ? '是' : (raw.isChanged === '否' || raw.isChanged === 'N' ? '否' : (raw.isChanged || '否')),
    changeReason: raw.changeReason ?? '',
    conclusion: raw.conclusion ?? '',
    sourceDetailRowId: raw.sourceDetailRowId,
  }
}

function _normalizeInquiry(raw: any): I1UsefulLifeInquiryRow {
  return {
    rowId: raw.rowId || _genId('inq'),
    name: raw.name || '',
    netBookValue: _getNum(raw.netBookValue),
    identifiedFiniteFactors: _getYn(raw.identifiedFiniteFactors),
    continuedOriginalUse: _getYn(raw.continuedOriginalUse),
    findings: raw.findings ?? '',
  }
}

function _readJson(allResponses: Map<string, any>, key: string): any {
  const item = allResponses.get(key)
  if (!item) return null
  const raw = item.remark ?? item.conclusion ?? item.value ?? item
  if (raw == null || raw === '') return null
  if (typeof raw !== 'string') return raw
  try {
    return JSON.parse(raw)
  } catch {
    return raw
  }
}

function _parseDetailRows(allResponses: Map<string, any>): any[] {
  const parsed = _readJson(allResponses, ITEM_ID_DETAIL)
  return Array.isArray(parsed) ? parsed : []
}

export function useI1UsefulLifeCheck(params: {
  allResponses: Ref<Map<string, any>>
  onSave?: (itemId: string, value: any) => void
}) {
  const { allResponses, onSave } = params

  const rows = ref<I1UsefulLifeRow[]>([])
  const inquiryRows = ref<I1UsefulLifeInquiryRow[]>([])
  const auditNote = ref('')
  const auditConclusion = ref('')

  function load(): void {
    const rawRows = _readJson(allResponses.value, I1_USEFUL_LIFE_ROWS_KEY)
    rows.value = Array.isArray(rawRows) ? rawRows.map(_normalizeRow) : []

    const rawInq = _readJson(allResponses.value, I1_USEFUL_LIFE_INQUIRY_KEY)
    inquiryRows.value = Array.isArray(rawInq) ? rawInq.map(_normalizeInquiry) : []

    const note = allResponses.value.get(I1_USEFUL_LIFE_NOTE_KEY)
    auditNote.value = String(note?.remark ?? note?.conclusion ?? note?.value ?? '')
    const conc = allResponses.value.get(I1_USEFUL_LIFE_CONCLUSION_KEY)
    auditConclusion.value = String(conc?.remark ?? conc?.conclusion ?? conc?.value ?? '')
  }

  watch(() => allResponses.value, () => load(), { immediate: true })

  // ─── Stats ─────────────────────────────────────────────────────────────────

  const indefiniteCount = computed(() => rows.value.filter(isIndefiniteRow).length)
  const changedCount = computed(() => rows.value.filter((r) => r.isChanged === '是').length)
  const conclusionStats = computed(() => {
    const stats = { reasonable: 0, attention: 0, unreasonable: 0, blank: 0 }
    for (const r of rows.value) {
      if (r.conclusion === '合理') stats.reasonable++
      else if (r.conclusion === '需关注') stats.attention++
      else if (r.conclusion === '不合理') stats.unreasonable++
      else stats.blank++
    }
    return stats
  })

  /** 编制校验：不确定项须有判断依据；变更=是须有原因；询问表覆盖全部不确定项 */
  const prepValidation = computed(() => {
    const messages: string[] = []
    for (const r of rows.value) {
      if (!r.name?.trim()) messages.push('存在未填写资产名称的行')
      if (isIndefiniteRow(r) && !r.indefiniteJudgmentBasis?.trim()) {
        messages.push(`「${r.name || '未命名'}」为寿命不确定，须填写管理层判断依据`)
      }
      if (r.isChanged === '是' && !r.changeReason?.trim()) {
        messages.push(`「${r.name || '未命名'}」本期变更须说明原因（CAS28）`)
      }
      if (r.legalApplicable === 'Y' && r.legalPrescribedYears == null && !r.legalDeterminedLife) {
        messages.push(`「${r.name || '未命名'}」适用法定权利，请填写规定年限或已确定寿命`)
      }
    }
    const indefiniteNames = new Set(rows.value.filter(isIndefiniteRow).map((r) => r.name))
    for (const name of indefiniteNames) {
      if (!inquiryRows.value.some((q) => q.name === name)) {
        messages.push(`不确定寿命资产「${name}」尚未列入管理层询问表`)
      }
    }
    for (const q of inquiryRows.value) {
      if (q.identifiedFiniteFactors === '' || q.continuedOriginalUse === '') {
        messages.push(`询问表「${q.name || '未命名'}」须完成两项询问结论`)
      }
    }
    // 去重
    const uniq = [...new Set(messages)]
    return { ok: uniq.length === 0, messages: uniq }
  })

  // ─── Persist ───────────────────────────────────────────────────────────────

  function persistRows(): void {
    onSave?.(I1_USEFUL_LIFE_ROWS_KEY, rows.value)
  }

  function persistInquiry(): void {
    onSave?.(I1_USEFUL_LIFE_INQUIRY_KEY, inquiryRows.value)
  }

  function saveNote(val: string): void {
    auditNote.value = val
    onSave?.(I1_USEFUL_LIFE_NOTE_KEY, val)
  }

  function saveConclusion(val: string): void {
    auditConclusion.value = val
    onSave?.(I1_USEFUL_LIFE_CONCLUSION_KEY, val)
  }

  function updateField(rowId: string, field: keyof I1UsefulLifeRow, value: unknown): void {
    const row = rows.value.find((r) => r.rowId === rowId)
    if (!row) return
    ;(row as any)[field] = value

    // 寿命月数 ↔ 不确定 双向联动
    if (field === 'usefulLifeMonths') {
      const m = _getNum(value)
      if (m === 0) row.isIndefinite = 'Y'
      else if (row.isIndefinite === 'Y' && m > 0) row.isIndefinite = 'N'
    }
    if (field === 'isIndefinite' && value === 'Y') {
      row.usefulLifeMonths = 0
    }
    if (field === 'isChanged' && value !== '是') {
      row.changeReason = ''
    }

    persistRows()
    syncInquiryFromIndefinite()
  }

  function updateInquiryField(rowId: string, field: keyof I1UsefulLifeInquiryRow, value: unknown): void {
    const row = inquiryRows.value.find((r) => r.rowId === rowId)
    if (!row) return
    ;(row as any)[field] = value
    persistInquiry()
  }

  function addRow(name: string): I1UsefulLifeRow {
    const row = blankUsefulLifeRow(name)
    rows.value.push(row)
    persistRows()
    return row
  }

  function removeRow(rowId: string): void {
    const idx = rows.value.findIndex((r) => r.rowId === rowId)
    if (idx < 0) return
    const name = rows.value[idx]!.name
    rows.value.splice(idx, 1)
    persistRows()
    // 清理询问表同名行（仅当主表不再有该不确定资产）
    if (!rows.value.some((r) => r.name === name && isIndefiniteRow(r))) {
      inquiryRows.value = inquiryRows.value.filter((q) => q.name !== name)
      persistInquiry()
    }
  }

  /** 不确定项自动进入询问表（保留已填询问答案） */
  function syncInquiryFromIndefinite(): void {
    const indefinite = rows.value.filter(isIndefiniteRow)
    const byName = new Map(inquiryRows.value.map((q) => [q.name, q]))
    const next: I1UsefulLifeInquiryRow[] = []
    for (const r of indefinite) {
      const existing = byName.get(r.name)
      if (existing) {
        existing.netBookValue = r.netBookValue || existing.netBookValue
        next.push(existing)
      } else {
        next.push(blankInquiryRow(r.name, r.netBookValue))
      }
    }
    // 保留用户手工加的、主表已删但想留痕的？按 Excel 仅保留不确定项
    inquiryRows.value = next
    persistInquiry()
  }

  /** 从 I1-2 带入名称 / 使用寿命月 / 净值 */
  function seedFromDetail(): { ok: boolean; message: string; count: number } {
    const detail = _parseDetailRows(allResponses.value)
    if (!detail.length) {
      return { ok: false, message: 'I1-2 明细表暂无数据，请先编制明细表', count: 0 }
    }

    const existingByName = new Map(rows.value.map((r) => [r.name, r]))
    let added = 0
    let updated = 0

    for (const d of detail) {
      const name = String(d.name || '').trim()
      if (!name) continue
      const life = _getNum(d.usefulLifeMonths)
      const net = _getNum(d.netValue ?? (
        _getNum(d.costEnd) - _getNum(d.accAmortEnd) - _getNum(d.impairmentEnd)
      ))
      const existing = existingByName.get(name)
      if (existing) {
        existing.usefulLifeMonths = life
        existing.netBookValue = net
        existing.sourceDetailRowId = d.rowId
        if (life === 0) existing.isIndefinite = 'Y'
        updated++
      } else {
        const row = blankUsefulLifeRow(name)
        row.usefulLifeMonths = life
        row.netBookValue = net
        row.sourceDetailRowId = d.rowId
        row.isIndefinite = life === 0 ? 'Y' : 'N'
        if (d.amortizationMethod) row.lifeBasis = String(d.amortizationMethod)
        rows.value.push(row)
        existingByName.set(name, row)
        added++
      }
    }

    persistRows()
    syncInquiryFromIndefinite()
    return {
      ok: true,
      message: `已从 I1-2 同步：新增 ${added}、更新 ${updated}`,
      count: added + updated,
    }
  }

  /** 发布不确定寿命清单，供 I1-12 减值测试取数 */
  function publishIndefiniteList(): void {
    const list = rows.value.filter(isIndefiniteRow).map((r) => ({
      name: r.name,
      netBookValue: r.netBookValue,
      judgmentBasis: r.indefiniteJudgmentBasis,
      docIndex: r.docIndex,
    }))
    onSave?.(I1_USEFUL_LIFE_PUBLISH_KEY, {
      at: new Date().toISOString(),
      count: list.length,
      assets: list,
      // 同步寿命参数摘要，供 I1-10/11 参考
      lifeParams: rows.value.map((r) => ({
        name: r.name,
        usefulLifeMonths: r.usefulLifeMonths,
        isIndefinite: isIndefiniteRow(r),
        isChanged: r.isChanged === '是',
      })),
    })
  }

  function draftConclusion(): string {
    const parts: string[] = []
    parts.push(
      `共检查无形资产 ${rows.value.length} 项，其中使用寿命不确定（不摊销） ${indefiniteCount.value} 项，本期寿命估计变更 ${changedCount.value} 项。`,
    )
    const { reasonable, attention, unreasonable, blank } = conclusionStats.value
    parts.push(`行结论：合理 ${reasonable}、需关注 ${attention}、不合理 ${unreasonable}${blank ? `、待填 ${blank}` : ''}。`)
    if (indefiniteCount.value > 0) {
      parts.push('对使用寿命不确定的无形资产，已询问管理层是否识别出有限寿命因素及是否按原定用途继续使用，并链接 I1-12 执行年度减值测试。')
    }
    if (!prepValidation.value.ok) {
      parts.push(`编制尚待完善：${prepValidation.value.messages.slice(0, 2).join('；')}`)
    } else {
      parts.push('经检查，被审计单位确定无形资产使用寿命的依据总体合理，未见重大异常。')
    }
    return parts.join('')
  }

  return {
    rows,
    inquiryRows,
    auditNote,
    auditConclusion,
    indefiniteCount,
    changedCount,
    conclusionStats,
    prepValidation,
    updateField,
    updateInquiryField,
    addRow,
    removeRow,
    seedFromDetail,
    syncInquiryFromIndefinite,
    persistRows,
    persistInquiry,
    saveNote,
    saveConclusion,
    publishIndefiniteList,
    draftConclusion,
    calcRemainingYears,
    isIndefiniteRow,
  }
}

export default useI1UsefulLifeCheck
