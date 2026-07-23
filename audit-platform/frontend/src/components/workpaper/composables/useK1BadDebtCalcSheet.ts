/**
 * useK1BadDebtCalcSheet — K1-8 坏账准备测算表
 *
 * 对齐致同源模板 K1-8：
 *   (一) 单项计提
 *   (二) 押金/保证金组合 — 信用期（默认 4 段，可自定义）
 *   (三) 其他组合 — 账龄（3年段 / 5年段 / 自定义，多组合）
 *
 * 公式：应计提③ = 审定余额① × 损失率②；差异⑤ = 应计提③ − 账面准备④
 */
import { ref, computed } from 'vue'
import { ElMessage } from 'element-plus'
import type { AgingPreset } from '@/composables/useAgingConfig'
import { parseNum } from '@/composables/useG5FormulaEngine'
import {
  syncGroupRows,
  resolveAgingSegments,
  G5_CREDIT_TERM_SEGMENTS,
  type G5EclLineRow,
  type G5EclGroup,
  type G5CreditPreset,
} from './useG5ImpairmentCalc'
import { validateCustomAgingLabels } from './g5AgingScheme'

export type K1CalcLineRow = G5EclLineRow
export type K1CalcGroup = G5EclGroup
export type K1AgingPreset = AgingPreset
export type K1CreditPreset = G5CreditPreset

export interface K1BadDebtCalcPayloadV2 {
  version: 2
  singleRows: K1CalcLineRow[]
  creditGroups: K1CalcGroup[]
  agingGroups: K1CalcGroup[]
  agingPreset: K1AgingPreset
  customAgingLabels: string[]
  creditPreset: K1CreditPreset
  customCreditLabels: string[]
  auditNote?: string
  conclusion?: string
  conclusionOption?: string
}

const STORAGE_ITEM_ID = 'K1-8-bad-debt-calc'

function uid(prefix: string): string {
  return `${prefix}-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`
}

function round2(n: number): number {
  return Math.round(parseNum(n) * 100) / 100
}

function calcExpected(balance: number, rate: number): number {
  return round2(parseNum(balance) * parseNum(rate))
}

function calcDiff(expected: number, book: number): number {
  return round2(parseNum(expected) - parseNum(book))
}

function recalcLine(row: K1CalcLineRow): K1CalcLineRow {
  const expectedProvision = calcExpected(row.auditedBalance, row.lossRate)
  return {
    ...row,
    expectedProvision,
    difference: calcDiff(expectedProvision, row.bookProvision),
  }
}

function createLineFromSegment(seg: { key: string; label: string }): K1CalcLineRow {
  return recalcLine({
    rowId: uid('ln'),
    label: seg.label,
    segmentKey: seg.key,
    auditedBalance: 0,
    lossRate: 0,
    expectedProvision: 0,
    bookProvision: 0,
    difference: 0,
    basis: '',
    indexRef: '',
  })
}

function createEmptySingle(debtor = ''): K1CalcLineRow {
  return recalcLine({
    rowId: uid('si'),
    label: debtor,
    segmentKey: '',
    auditedBalance: 0,
    lossRate: 0,
    expectedProvision: 0,
    bookProvision: 0,
    difference: 0,
    basis: '',
    indexRef: '',
  })
}

function createGroup(name: string, segs: Array<{ key: string; label: string }>): K1CalcGroup {
  return {
    groupId: uid('grp'),
    groupName: name,
    rows: segs.map(createLineFromSegment),
  }
}

function resolveCreditSegments(
  preset: K1CreditPreset,
  customLabels: string[] = [],
): Array<{ key: string; label: string }> {
  if (preset === 'CUSTOM' && customLabels.length >= 2) {
    return customLabels
      .map((l) => l.trim())
      .filter(Boolean)
      .slice(0, 10)
      .map((label, i) => ({ key: `custom-${i}`, label, dayFrom: 0, dayTo: null } as any))
  }
  return G5_CREDIT_TERM_SEGMENTS.map((s) => ({ ...s }))
}

function sumLines(rows: K1CalcLineRow[]) {
  const active = rows.filter((r) => !r.archived)
  return {
    balance: round2(active.reduce((s, r) => s + parseNum(r.auditedBalance), 0)),
    expected: round2(active.reduce((s, r) => s + parseNum(r.expectedProvision), 0)),
    book: round2(active.reduce((s, r) => s + parseNum(r.bookProvision), 0)),
    diff: round2(active.reduce((s, r) => s + parseNum(r.difference), 0)),
  }
}

function emptyPayload(): K1BadDebtCalcPayloadV2 {
  const agingSegs = resolveAgingSegments('FIVE_YEAR')
  const creditSegs = resolveCreditSegments('DEFAULT')
  return {
    version: 2,
    singleRows: [],
    creditGroups: [createGroup('押金/保证金', creditSegs)],
    agingGroups: [
      createGroup('组合1', agingSegs),
      createGroup('组合2', agingSegs.map((s) => ({ ...s }))),
    ],
    agingPreset: 'FIVE_YEAR',
    customAgingLabels: [],
    creditPreset: 'DEFAULT',
    customCreditLabels: [],
    auditNote: '',
    conclusion: '',
    conclusionOption: '',
  }
}

function matchSegmentKey(label: string, segs: Array<{ key: string; label: string }>): string {
  const trimmed = String(label || '').trim()
  if (!trimmed) return ''
  const exact = segs.find((s) => s.label === trimmed)
  if (exact) return exact.key
  const partial = segs.find((s) => trimmed.startsWith(s.label.split('/')[0]))
  if (partial) return partial.key
  return ''
}

/** 旧版 useK1AuditRows 结构 → V2 */
function migrateV1Tables(data: Record<string, any>): Partial<K1BadDebtCalcPayloadV2> {
  const agingPreset: K1AgingPreset = 'FIVE_YEAR'
  const agingSegs = resolveAgingSegments(agingPreset)
  const creditSegs = resolveCreditSegments('DEFAULT')

  const mapLegacyRow = (r: Record<string, any>, segs?: Array<{ key: string; label: string }>): K1CalcLineRow => {
    const label = String(r.name || r.label || '').trim()
    const row = recalcLine({
      rowId: r.id || uid('ln'),
      label,
      segmentKey: r.segmentKey || (segs ? matchSegmentKey(label, segs) : ''),
      auditedBalance: parseNum(r.balance ?? r.auditedBalance),
      lossRate: parseNum(r.rate ?? r.lossRate),
      bookProvision: parseNum(r.bookProvision),
      basis: String(r.basis || ''),
      indexRef: String(r.indexNo ?? r.indexRef ?? ''),
    })
    return row
  }

  const singleRows = (data.tables?.single ?? []).map((r: Record<string, any>) => mapLegacyRow(r))
  const depositRows = (data.tables?.deposit ?? []).map((r: Record<string, any>) => mapLegacyRow(r, creditSegs))
  const agingRows = (data.tables?.aging ?? []).map((r: Record<string, any>) => mapLegacyRow(r, agingSegs))

  return {
    singleRows,
    creditGroups: [{
      groupId: uid('grp'),
      groupName: '押金/保证金',
      rows: syncGroupRows(depositRows.length ? depositRows : creditSegs.map(createLineFromSegment), creditSegs),
    }],
    agingGroups: [
      {
        groupId: uid('grp'),
        groupName: '组合1',
        rows: syncGroupRows(agingRows.length ? agingRows : agingSegs.map(createLineFromSegment), agingSegs),
      },
      createGroup('组合2', agingSegs),
    ],
    agingPreset,
    customAgingLabels: [],
    creditPreset: 'DEFAULT',
    customCreditLabels: [],
    auditNote: data.auditNote ?? '',
    conclusion: data.conclusion ?? '',
    conclusionOption: data.conclusionOption ?? '',
  }
}

export function parseK18Payload(raw: unknown): K1BadDebtCalcPayloadV2 {
  const base = emptyPayload()
  if (raw == null || raw === '') return base

  let parsed: any = raw
  if (typeof raw === 'string') {
    try {
      parsed = JSON.parse(raw)
    } catch {
      return base
    }
  }

  if (parsed?.tables && !parsed.version) {
    return { ...base, ...migrateV1Tables(parsed) }
  }

  if (parsed && typeof parsed === 'object' && parsed.version === 2) {
    const p = parsed as Partial<K1BadDebtCalcPayloadV2>
    const agingPreset = (p.agingPreset as K1AgingPreset) || 'FIVE_YEAR'
    const customAging = Array.isArray(p.customAgingLabels) ? p.customAgingLabels.map(String) : []
    const creditPreset = (p.creditPreset as K1CreditPreset) || 'DEFAULT'
    const customCredit = Array.isArray(p.customCreditLabels) ? p.customCreditLabels.map(String) : []
    const agingSegs = resolveAgingSegments(agingPreset, customAging)
    const creditSegs = resolveCreditSegments(creditPreset, customCredit)
    return {
      version: 2,
      singleRows: Array.isArray(p.singleRows)
        ? p.singleRows.map((r) => recalcLine({ ...createEmptySingle(), ...r }))
        : [],
      creditGroups:
        Array.isArray(p.creditGroups) && p.creditGroups.length
          ? p.creditGroups.map((g) => ({
              groupId: g.groupId || uid('grp'),
              groupName: g.groupName || '押金/保证金',
              rows: syncGroupRows(g.rows || [], creditSegs),
            }))
          : [createGroup('押金/保证金', creditSegs)],
      agingGroups:
        Array.isArray(p.agingGroups) && p.agingGroups.length
          ? p.agingGroups.map((g, i) => ({
              groupId: g.groupId || uid('grp'),
              groupName: g.groupName || `组合${i + 1}`,
              rows: syncGroupRows(g.rows || [], agingSegs),
            }))
          : [createGroup('组合1', agingSegs), createGroup('组合2', agingSegs.map((s) => ({ ...s })))],
      agingPreset,
      customAgingLabels: customAging,
      creditPreset,
      customCreditLabels: customCredit,
      auditNote: p.auditNote ?? '',
      conclusion: p.conclusion ?? '',
      conclusionOption: p.conclusionOption ?? '',
    }
  }

  return base
}

export function useK1BadDebtCalcSheet() {
  const payload = ref<K1BadDebtCalcPayloadV2>(emptyPayload())

  const singleRows = computed(() => payload.value.singleRows)
  const creditGroups = computed(() => payload.value.creditGroups)
  const agingGroups = computed(() => payload.value.agingGroups)
  const agingPreset = computed(() => payload.value.agingPreset)
  const creditPreset = computed(() => payload.value.creditPreset)
  const customAgingLabels = computed(() => payload.value.customAgingLabels)
  const customCreditLabels = computed(() => payload.value.customCreditLabels)
  const agingSegments = computed(() =>
    resolveAgingSegments(payload.value.agingPreset, payload.value.customAgingLabels),
  )
  const creditSegments = computed(() =>
    resolveCreditSegments(payload.value.creditPreset, payload.value.customCreditLabels),
  )

  const singleTotal = computed(() => sumLines(payload.value.singleRows))
  const creditTotal = computed(() =>
    sumLines(payload.value.creditGroups.flatMap((g) => g.rows)),
  )
  const agingTotal = computed(() =>
    sumLines(payload.value.agingGroups.flatMap((g) => g.rows)),
  )
  const grandTotal = computed(() => ({
    balance: round2(singleTotal.value.balance + creditTotal.value.balance + agingTotal.value.balance),
    expected: round2(singleTotal.value.expected + creditTotal.value.expected + agingTotal.value.expected),
    book: round2(singleTotal.value.book + creditTotal.value.book + agingTotal.value.book),
    diff: round2(singleTotal.value.diff + creditTotal.value.diff + agingTotal.value.diff),
  }))

  const diffAlert = computed(() => {
    const d = grandTotal.value.diff
    if (Math.abs(d) < 0.01) return ''
    return `测算应计提与账面准备合计差异 ${d.toLocaleString('zh-CN', { minimumFractionDigits: 2 })}，请分析计提是否充分。`
  })

  function touch() {
    payload.value = { ...payload.value }
  }

  function loadFromRaw(raw: string | null | undefined) {
    payload.value = parseK18Payload(raw)
  }

  function serialize(): string {
    return JSON.stringify(payload.value)
  }

  function setAuditMeta(note: string, conclusion: string, conclusionOption: string) {
    payload.value.auditNote = note
    payload.value.conclusion = conclusion
    payload.value.conclusionOption = conclusionOption
    touch()
  }

  function addSingleRow(debtor = '') {
    payload.value.singleRows.push(createEmptySingle(debtor))
    touch()
  }

  function removeSingleRow(rowId: string) {
    payload.value.singleRows = payload.value.singleRows.filter((r) => r.rowId !== rowId)
    touch()
  }

  function updateSingleCell(rowId: string, field: keyof K1CalcLineRow, value: string | number) {
    const row = payload.value.singleRows.find((r) => r.rowId === rowId)
    if (!row) return
    ;(row as any)[field] = value
    Object.assign(row, recalcLine(row))
    touch()
  }

  function setCreditPreset(preset: K1CreditPreset, customLabels?: string[]): boolean {
    if (preset === 'CUSTOM') {
      const labels = (customLabels || []).map((l) => l.trim()).filter(Boolean)
      if (labels.length < 2) {
        ElMessage.warning('自定义信用期至少需要 2 段')
        return false
      }
      if (labels.length > 10) {
        ElMessage.warning('自定义信用期最多 10 段')
        return false
      }
      payload.value.customCreditLabels = labels
    }
    payload.value.creditPreset = preset
    const segs = resolveCreditSegments(preset, payload.value.customCreditLabels)
    payload.value.creditGroups = payload.value.creditGroups.map((g) => ({
      ...g,
      rows: syncGroupRows(g.rows, segs),
    }))
    touch()
    return true
  }

  function updateCreditCell(
    groupId: string,
    rowId: string,
    field: keyof K1CalcLineRow,
    value: string | number,
  ) {
    const g = payload.value.creditGroups.find((x) => x.groupId === groupId)
    const row = g?.rows.find((r) => r.rowId === rowId)
    if (!row) return
    ;(row as any)[field] = value
    Object.assign(row, recalcLine(row))
    touch()
  }

  function removeCreditRow(groupId: string, rowId: string) {
    const g = payload.value.creditGroups.find((x) => x.groupId === groupId)
    if (!g || g.rows.filter((r) => !r.archived).length <= 1) {
      ElMessage.warning('至少保留一段信用期')
      return
    }
    g.rows = g.rows.filter((r) => r.rowId !== rowId)
    touch()
  }

  function setAgingPreset(preset: K1AgingPreset, customLabels?: string[]): boolean {
    if (preset === 'CUSTOM') {
      const labels = (customLabels || []).map((l) => l.trim()).filter(Boolean)
      const err = validateCustomAgingLabels(labels)
      if (err) {
        ElMessage.warning(err)
        return false
      }
      payload.value.customAgingLabels = labels
    }
    payload.value.agingPreset = preset
    const segs = resolveAgingSegments(preset, payload.value.customAgingLabels)
    payload.value.agingGroups = payload.value.agingGroups.map((g) => ({
      ...g,
      rows: syncGroupRows(g.rows, segs),
    }))
    touch()
    return true
  }

  function addAgingGroup() {
    const segs = resolveAgingSegments(payload.value.agingPreset, payload.value.customAgingLabels)
    const n = payload.value.agingGroups.length + 1
    payload.value.agingGroups.push(createGroup(`组合${n}`, segs))
    touch()
  }

  function removeAgingGroup(groupId: string) {
    if (payload.value.agingGroups.length <= 1) {
      ElMessage.warning('至少保留一个账龄组合')
      return
    }
    payload.value.agingGroups = payload.value.agingGroups.filter((g) => g.groupId !== groupId)
    touch()
  }

  function updateGroupName(groupId: string, name: string) {
    const g = payload.value.agingGroups.find((x) => x.groupId === groupId)
    if (g) g.groupName = name
    touch()
  }

  function updateAgingCell(
    groupId: string,
    rowId: string,
    field: keyof K1CalcLineRow,
    value: string | number,
  ) {
    const g = payload.value.agingGroups.find((x) => x.groupId === groupId)
    const row = g?.rows.find((r) => r.rowId === rowId)
    if (!row) return
    ;(row as any)[field] = value
    Object.assign(row, recalcLine(row))
    touch()
  }

  /** 从 K1-2 明细汇总账龄审定余额至第一账龄组合 */
  function pullBalancesFromK1Detail(allResponses: Map<string, any>): { singles: number; agingBands: number } {
    const raw = allResponses.get('K1-2-detail-rows')?.remark
    if (!raw) {
      ElMessage.warning('未找到 K1-2 明细，请先编制余额明细表')
      return { singles: 0, agingBands: 0 }
    }
    let detail: any[] = []
    try {
      const parsed = typeof raw === 'string' ? JSON.parse(raw) : raw
      detail = Array.isArray(parsed) ? parsed : (parsed?.rows ?? [])
    } catch {
      ElMessage.warning('K1-2 明细数据格式异常')
      return { singles: 0, agingBands: 0 }
    }
    if (!detail.length) {
      ElMessage.warning('K1-2 明细为空')
      return { singles: 0, agingBands: 0 }
    }

    let singles = 0
    const agingSum = new Map<string, number>()

    for (const row of detail) {
      const name = String(row.debtorName || row.name || '').trim()
      const bal = parseNum(row.netAmount ?? row.closingBalance ?? row.endBalance)
      if (name && Math.abs(bal) >= 0.005) {
        let line = payload.value.singleRows.find((r) => r.label === name)
        if (!line) {
          line = createEmptySingle(name)
          payload.value.singleRows.push(line)
        }
        line.auditedBalance = round2(bal)
        Object.assign(line, recalcLine(line))
        singles += 1
      }
      const audited = row.agingAudited && typeof row.agingAudited === 'object' ? row.agingAudited : null
      if (audited) {
        for (const [key, val] of Object.entries(audited)) {
          const n = parseNum(val)
          if (Math.abs(n) < 0.005) continue
          agingSum.set(key, round2((agingSum.get(key) || 0) + n))
        }
      }
    }

    let agingBands = 0
    if (agingSum.size && payload.value.agingGroups.length) {
      const g = payload.value.agingGroups[0]
      for (const row of g.rows) {
        if (row.archived || !row.segmentKey) continue
        const hit = agingSum.get(row.segmentKey)
        if (hit != null && Math.abs(hit) >= 0.005) {
          row.auditedBalance = hit
          Object.assign(row, recalcLine(row))
          agingBands += 1
        }
      }
    }

    touch()
    ElMessage.success(`已从 K1-2 导入 ${singles} 户单项、${agingBands} 个账龄段余额`)
    return { singles, agingBands }
  }

  return {
    payload,
    singleRows,
    creditGroups,
    agingGroups,
    agingPreset,
    creditPreset,
    customAgingLabels,
    customCreditLabels,
    agingSegments,
    creditSegments,
    singleTotal,
    creditTotal,
    agingTotal,
    grandTotal,
    diffAlert,
    loadFromRaw,
    serialize,
    setAuditMeta,
    addSingleRow,
    removeSingleRow,
    updateSingleCell,
    setCreditPreset,
    updateCreditCell,
    removeCreditRow,
    setAgingPreset,
    addAgingGroup,
    removeAgingGroup,
    updateGroupName,
    updateAgingCell,
    pullBalancesFromK1Detail,
    STORAGE_ITEM_ID,
  }
}
