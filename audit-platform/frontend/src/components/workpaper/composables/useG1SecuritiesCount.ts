/**
 * useG1SecuritiesCount — G1-11 有价证券监盘表
 *
 * 对齐致同纸质底稿：
 * - 盘点信息头（单位/日期/地点/人员）→ 自动生成监盘叙述
 * - 盘点明细：证券名称|面值|数量|总计(公式)|票面利率|到期日
 * - 审计扩展：代码|类型|账面数量|差异|差异原因|保管机构（支撑账实核对与 G1-4/G1-12）
 */
import { ref, computed, watch, type Ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { parseNum, calcCountDiff, calcSubtotal } from './useG1TraFinFormulaEngine'
import type { ChecklistResponse } from './useF1FormData'

// ── Types ──────────────────────────────────────────────────────────────────

export interface G1SecuritiesCountHeader {
  company: string
  countDate: string
  location: string
  accountingSupervisor: string
  cashier: string
  observer: string
  counter: string
  reviewer: string
  participantCount: string
  /** 监盘叙述（可由头信息生成，可手改） */
  narrative: string
}

/** G1-11 监盘行 */
export interface G1SecuritiesCountRow {
  id: string
  seq: number
  securityName: string
  securityCode: string
  securityType: string
  /** 面值（纸质列） */
  faceValue: number
  /** 盘点数量 */
  countedQuantity: number
  /** 总计 = 面值 × 数量（公式） */
  total: number
  /** 票面利率（%） */
  couponRate: number
  maturityDate: string
  bookedQuantity: number
  countDiff: number
  diffReason: string
  custodian: string
  countDate: string
  /** 盘点地点（多地点同时盘点） */
  location: string
}

export interface G1SecuritiesCountColumn {
  prop: keyof G1SecuritiesCountRow
  label: string
  width: number
  formula?: boolean
  type?: 'text' | 'number' | 'date'
  group?: 'count' | 'recon'
}

export const G1_SECURITIES_COUNT_COLUMNS: G1SecuritiesCountColumn[] = [
  { prop: 'seq', label: '序号', width: 52, type: 'number' },
  { prop: 'location', label: '盘点地点', width: 110, type: 'text', group: 'count' },
  { prop: 'securityName', label: '证券名称', width: 140, type: 'text', group: 'count' },
  { prop: 'faceValue', label: '面值', width: 100, type: 'number', group: 'count' },
  { prop: 'countedQuantity', label: '数量', width: 90, type: 'number', group: 'count' },
  { prop: 'total', label: '总计', width: 110, type: 'number', formula: true, group: 'count' },
  { prop: 'couponRate', label: '票面利率(%)', width: 100, type: 'number', group: 'count' },
  { prop: 'maturityDate', label: '到期日', width: 120, type: 'date', group: 'count' },
  { prop: 'securityCode', label: '代码', width: 100, type: 'text', group: 'recon' },
  { prop: 'securityType', label: '类型', width: 90, type: 'text', group: 'recon' },
  { prop: 'bookedQuantity', label: '账面数量', width: 100, type: 'number', group: 'recon' },
  { prop: 'countDiff', label: '差异', width: 90, type: 'number', formula: true, group: 'recon' },
  { prop: 'diffReason', label: '差异原因', width: 130, type: 'text', group: 'recon' },
  { prop: 'custodian', label: '保管机构', width: 120, type: 'text', group: 'recon' },
  { prop: 'countDate', label: '监盘日期', width: 120, type: 'date', group: 'recon' },
]

const DATA_KEY = 'G1-11-rows'
const HEADER_KEY = 'G1-11-header'
const CONCLUSION_KEY = 'G1-11-conclusion'
const DETAIL_KEY = 'G1-2-rows'
const RECON_KEY = 'G1-12-rows'

export function emptyHeader(): G1SecuritiesCountHeader {
  return {
    company: '',
    countDate: '',
    location: '',
    accountingSupervisor: '',
    cashier: '',
    observer: '',
    counter: '',
    reviewer: '',
    participantCount: '',
    narrative: '',
  }
}

/** 由盘点头生成监盘叙述（对齐纸质红字占位句式） */
export function buildCountNarrative(h: G1SecuritiesCountHeader): string {
  const people = h.participantCount?.trim() || '—'
  const date = h.countDate?.trim() || '—年—月—日'
  const loc = h.location?.trim() || '—'
  const parts = [
    `${people}人于${date}，在${loc}对有价证券进行盘点。`,
  ]
  const roles: string[] = []
  if (h.observer?.trim()) roles.push(`监盘人：${h.observer.trim()}`)
  if (h.counter?.trim()) roles.push(`盘点人：${h.counter.trim()}`)
  if (h.accountingSupervisor?.trim()) roles.push(`会计主管：${h.accountingSupervisor.trim()}`)
  if (h.cashier?.trim()) roles.push(`出纳：${h.cashier.trim()}`)
  if (h.reviewer?.trim()) roles.push(`复核人：${h.reviewer.trim()}`)
  if (roles.length) parts.push(roles.join('；') + '。')
  if (h.company?.trim()) parts.push(`盘点单位：${h.company.trim()}。`)
  return parts.join('')
}

export function calcCountTotal(faceValue: number, quantity: number): number {
  return Math.round(parseNum(faceValue) * parseNum(quantity) * 100) / 100
}

function emptyRow(id: string, seq: number): G1SecuritiesCountRow {
  return {
    id,
    seq,
    securityName: '',
    securityCode: '',
    securityType: '',
    faceValue: 0,
    countedQuantity: 0,
    total: 0,
    couponRate: 0,
    maturityDate: '',
    bookedQuantity: 0,
    countDiff: 0,
    diffReason: '',
    custodian: '',
    countDate: '',
    location: '',
  }
}

function enrich(r: G1SecuritiesCountRow): G1SecuritiesCountRow {
  const total = calcCountTotal(r.faceValue, r.countedQuantity)
  const countDiff = calcCountDiff(parseNum(r.countedQuantity), parseNum(r.bookedQuantity))
  return { ...r, total, countDiff }
}

export function migrateCountRow(raw: Record<string, unknown>, seq: number): G1SecuritiesCountRow {
  return enrich({
    ...emptyRow(String(raw.id ?? `row-${seq}`), seq),
    securityName: String(raw.securityName ?? ''),
    securityCode: String(raw.securityCode ?? ''),
    securityType: String(raw.securityType ?? ''),
    faceValue: parseNum(raw.faceValue),
    countedQuantity: parseNum(raw.countedQuantity ?? raw.quantity),
    couponRate: parseNum(raw.couponRate),
    maturityDate: String(raw.maturityDate ?? ''),
    bookedQuantity: parseNum(raw.bookedQuantity),
    diffReason: String(raw.diffReason ?? ''),
    custodian: String(raw.custodian ?? ''),
    countDate: String(raw.countDate ?? ''),
    location: String(raw.location ?? ''),
  })
}

/** |差异|>0 且未填差异原因 */
export function checkDiffReasonGaps(list: G1SecuritiesCountRow[]): G1SecuritiesCountRow[] {
  return list.filter(
    (r) => Math.abs(parseNum(r.countDiff)) > 0 && !String(r.diffReason ?? '').trim(),
  )
}

/** 按盘点地点分组（空地点归「未指定地点」） */
export function groupCountRowsByLocation(
  list: G1SecuritiesCountRow[],
): { location: string; rows: G1SecuritiesCountRow[] }[] {
  const map = new Map<string, G1SecuritiesCountRow[]>()
  for (const r of list) {
    const loc = String(r.location || '').trim() || '未指定地点'
    if (!map.has(loc)) map.set(loc, [])
    map.get(loc)!.push(r)
  }
  return Array.from(map.entries()).map(([location, rows]) => ({ location, rows }))
}

function loadRows(map: Map<string, ChecklistResponse>): G1SecuritiesCountRow[] {
  const raw = map.get(DATA_KEY)?.conclusion ?? map.get(DATA_KEY)?.remark
  if (!raw) return [enrich(emptyRow('1', 1))]
  try {
    const parsed = JSON.parse(raw) as Record<string, unknown>[]
    if (!Array.isArray(parsed) || parsed.length === 0) return [enrich(emptyRow('1', 1))]
    return parsed.map((p, i) => migrateCountRow(p, i + 1))
  } catch {
    return [enrich(emptyRow('1', 1))]
  }
}

function loadHeader(map: Map<string, ChecklistResponse>): G1SecuritiesCountHeader {
  const raw = map.get(HEADER_KEY)?.conclusion ?? map.get(HEADER_KEY)?.remark
  if (!raw) return emptyHeader()
  try {
    const parsed = JSON.parse(raw) as Partial<G1SecuritiesCountHeader>
    return { ...emptyHeader(), ...parsed }
  } catch {
    return emptyHeader()
  }
}

export function headerCompleteness(h: G1SecuritiesCountHeader): { filled: number; total: number; missing: string[] } {
  const fields: { key: keyof G1SecuritiesCountHeader; label: string }[] = [
    { key: 'company', label: '盘点单位' },
    { key: 'countDate', label: '盘点日期' },
    { key: 'location', label: '盘点地点' },
    { key: 'observer', label: '监盘人' },
    { key: 'counter', label: '盘点人' },
  ]
  const missing = fields.filter((f) => !String(h[f.key] ?? '').trim()).map((f) => f.label)
  return { filled: fields.length - missing.length, total: fields.length, missing }
}

// ── Composable ─────────────────────────────────────────────────────────────

export function useG1SecuritiesCount(opts: {
  allResponses: Ref<Map<string, ChecklistResponse>>
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
  isReadonly: Ref<boolean>
}) {
  const rows = ref<G1SecuritiesCountRow[]>(loadRows(opts.allResponses.value))
  const header = ref<G1SecuritiesCountHeader>(loadHeader(opts.allResponses.value))
  const auditConclusion = ref(opts.allResponses.value.get(CONCLUSION_KEY)?.conclusion ?? '')

  function loadAll() {
    rows.value = loadRows(opts.allResponses.value)
    header.value = loadHeader(opts.allResponses.value)
    auditConclusion.value = opts.allResponses.value.get(CONCLUSION_KEY)?.conclusion ?? ''
  }

  watch(
    () => opts.allResponses.value.get(DATA_KEY)?.conclusion
      ?? opts.allResponses.value.get(DATA_KEY)?.remark,
    (raw) => {
      if (raw) rows.value = loadRows(opts.allResponses.value)
    },
  )

  const diffCount = computed(() => rows.value.filter((r) => Math.abs(parseNum(r.countDiff)) > 0).length)
  const diffReasonGaps = computed(() => checkDiffReasonGaps(rows.value))
  const gateReady = computed(() => diffReasonGaps.value.length === 0)
  const headerStatus = computed(() => headerCompleteness(header.value))
  const locationOptions = computed(() => {
    const set = new Set<string>()
    if (header.value.location?.trim()) set.add(header.value.location.trim())
    for (const r of rows.value) {
      if (r.location?.trim()) set.add(r.location.trim())
    }
    return Array.from(set)
  })
  const groupedByLocation = computed(() => groupCountRowsByLocation(rows.value))
  const grandTotal = computed(() => ({
    countedQuantity: calcSubtotal(rows.value.map((r) => parseNum(r.countedQuantity))),
    total: calcSubtotal(rows.value.map((r) => parseNum(r.total))),
    bookedQuantity: calcSubtotal(rows.value.map((r) => parseNum(r.bookedQuantity))),
  }))

  function isDiffAbnormal(row: G1SecuritiesCountRow): boolean {
    return Math.abs(parseNum(row.countDiff)) > 0
  }

  function needsDiffReason(row: G1SecuritiesCountRow): boolean {
    return Math.abs(parseNum(row.countDiff)) > 0 && !String(row.diffReason ?? '').trim()
  }

  function persistRows() {
    if (!opts.isReadonly.value) {
      opts.debouncedSave(DATA_KEY, { conclusion: JSON.stringify(rows.value) })
    }
  }

  function persistHeader() {
    if (!opts.isReadonly.value) {
      opts.debouncedSave(HEADER_KEY, { conclusion: JSON.stringify(header.value) })
    }
  }

  watch(auditConclusion, (v) => {
    if (!opts.isReadonly.value) opts.debouncedSave(CONCLUSION_KEY, { conclusion: v })
  })

  function updateHeader(patch: Partial<G1SecuritiesCountHeader>, regenNarrative = false) {
    if (opts.isReadonly.value) return
    const next = { ...header.value, ...patch }
    if (regenNarrative || !next.narrative?.trim()) {
      next.narrative = buildCountNarrative(next)
    }
    header.value = next
    persistHeader()
  }

  function regenerateNarrative() {
    if (opts.isReadonly.value) return
    header.value = { ...header.value, narrative: buildCountNarrative(header.value) }
    persistHeader()
  }

  function updateRow(id: string, patch: Partial<G1SecuritiesCountRow>) {
    if (opts.isReadonly.value) return
    rows.value = rows.value.map((r) => (r.id === id ? enrich({ ...r, ...patch }) : r))
    persistRows()
  }

  async function addRow() {
    if (opts.isReadonly.value) return
    try {
      const { value } = await ElMessageBox.prompt('请输入证券名称', '新增监盘行', {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        inputPattern: /\S+/,
        inputErrorMessage: '证券名称不能为空',
      })
      const seq = rows.value.length + 1
      rows.value = [
        ...rows.value,
        enrich({
          ...emptyRow(`row-${Date.now()}`, seq),
          securityName: value,
          countDate: header.value.countDate || '',
          location: header.value.location || '',
        }),
      ]
      persistRows()
    } catch {
      /* cancelled */
    }
  }

  function removeRow(id: string) {
    if (opts.isReadonly.value || rows.value.length <= 1) return
    rows.value = rows.value.filter((r) => r.id !== id).map((r, i) => ({ ...r, seq: i + 1 }))
    persistRows()
  }

  /** 从 G1-2 带入证券名称、代码、类型、账面期末数量 */
  function pullFromDetail() {
    if (opts.isReadonly.value) return
    const raw = opts.allResponses.value.get(DETAIL_KEY)?.conclusion
    if (!raw) {
      ElMessage.warning('未找到 G1-2 明细表数据')
      return
    }
    try {
      const list = JSON.parse(raw) as Array<Record<string, unknown>>
      if (!Array.isArray(list) || !list.length) {
        ElMessage.info('G1-2 无明细行')
        return
      }
      const byName = new Map(rows.value.map((r) => [r.securityName.trim(), r]))
      let added = 0
      let updated = 0
      let seq = rows.value.length
      for (const src of list) {
        const name = String(src.securityName ?? '').trim()
        if (!name) continue
        const booked = parseNum(src.closingQuantity)
        const existing = byName.get(name)
        if (existing) {
          byName.set(
            name,
            enrich({
              ...existing,
              securityCode: existing.securityCode || String(src.securityCode ?? ''),
              securityType: existing.securityType || String(src.investType ?? ''),
              bookedQuantity: booked || existing.bookedQuantity,
              countDate: existing.countDate || header.value.countDate,
            }),
          )
          updated += 1
        } else {
          seq += 1
          const row = enrich({
            ...emptyRow(src.id ? `d2-${src.id}` : `row-${Date.now()}-${seq}`, seq),
            securityName: name,
            securityCode: String(src.securityCode ?? ''),
            securityType: String(src.investType ?? ''),
            bookedQuantity: booked,
            countedQuantity: booked,
            countDate: header.value.countDate || '',
            location: header.value.location || '',
          })
          byName.set(name, row)
          added += 1
        }
      }
      rows.value = Array.from(byName.values()).map((r, i) => ({ ...r, seq: i + 1 }))
      persistRows()
      ElMessage.success(`已从 G1-2 更新 ${updated} 行、新增 ${added} 行`)
    } catch {
      ElMessage.error('解析 G1-2 数据失败')
    }
  }

  function mapTypeToCategory(t: string): string {
    const s = t.trim().toLowerCase()
    if (!s) return ''
    if (/债|bond|debt|票据|理财/.test(s)) return 'debt'
    if (/股|权益|equity|stock|fund|基金/.test(s)) return 'equity'
    if (/衍生|derivative|期权|期货|互换|远期/.test(s)) return 'derivative'
    return 'other'
  }

  /**
   * 将本表监盘结果推送到 G1-12 倒轧表（写入监盘日实存与账面数量）
   * @param force 为 true 时覆盖已有增减以外的盘点日字段
   */
  function pushToReconciliation(force = false): number {
    if (opts.isReadonly.value) return 0
    const sources = rows.value.filter((r) => r.securityName.trim())
    if (!sources.length) {
      ElMessage.warning('本表无有效监盘行可推送')
      return 0
    }

    let existing: Array<Record<string, unknown>> = []
    const raw = opts.allResponses.value.get(RECON_KEY)?.conclusion
      ?? opts.allResponses.value.get(RECON_KEY)?.remark
    if (raw) {
      try {
        const parsed = JSON.parse(raw)
        if (Array.isArray(parsed)) existing = parsed
      } catch {
        /* ignore */
      }
    }

    const byCountId = new Map(
      existing.filter((r) => r.countRowId).map((r) => [String(r.countRowId), r]),
    )
    const byName = new Map(
      existing
        .filter((r) => String(r.securityName ?? '').trim())
        .map((r) => [String(r.securityName).trim(), r]),
    )

    const next: Record<string, unknown>[] = []
    let added = 0
    let updated = 0

    for (const src of sources) {
      const name = src.securityName.trim()
      const matched = (src.id && byCountId.get(src.id)) || byName.get(name)
      const cat = mapTypeToCategory(src.securityType)
      const basePatch = {
        securityName: name,
        countQuantity: src.countedQuantity,
        countFaceValue: src.faceValue,
        countCouponRate: src.couponRate,
        countMaturityDate: src.maturityDate,
        bookQuantity: src.bookedQuantity,
        countRowId: src.id,
        category: cat || (matched?.category ?? ''),
        reportFaceValue: src.faceValue || parseNum(matched?.reportFaceValue),
        reportCouponRate: src.couponRate || parseNum(matched?.reportCouponRate),
        reportMaturityDate: src.maturityDate || String(matched?.reportMaturityDate ?? ''),
      }

      if (matched && !force) {
        next.push({
          ...matched,
          ...basePatch,
          category: matched.category || cat,
          countFaceValue: src.faceValue || parseNum(matched.countFaceValue),
          countCouponRate: src.couponRate || parseNum(matched.countCouponRate),
          countMaturityDate: src.maturityDate || String(matched.countMaturityDate ?? ''),
          bookQuantity: src.bookedQuantity || parseNum(matched.bookQuantity),
          // 保留增减与备注
          increaseQuantity: matched.increaseQuantity,
          increaseFaceTotal: matched.increaseFaceTotal,
          decreaseQuantity: matched.decreaseQuantity,
          decreaseFaceTotal: matched.decreaseFaceTotal,
          remark: matched.remark,
          id: matched.id,
        })
        updated += 1
      } else if (matched && force) {
        next.push({
          ...matched,
          ...basePatch,
          id: matched.id,
          increaseQuantity: matched.increaseQuantity,
          increaseFaceTotal: matched.increaseFaceTotal,
          decreaseQuantity: matched.decreaseQuantity,
          decreaseFaceTotal: matched.decreaseFaceTotal,
          remark: matched.remark,
        })
        updated += 1
      } else {
        next.push({
          id: `from-g111-${src.id}`,
          seq: next.length + 1,
          ...basePatch,
          increaseQuantity: 0,
          increaseFaceTotal: 0,
          decreaseQuantity: 0,
          decreaseFaceTotal: 0,
          bookFaceValue: src.faceValue,
          bookTotal: 0,
          remark: src.location ? `监盘地点：${src.location}` : '',
        })
        added += 1
      }
    }

    // 保留倒轧表中监盘未覆盖的行
    const syncedIds = new Set(next.map((r) => String(r.id)))
    const syncedNames = new Set(next.map((r) => String(r.securityName ?? '').trim()))
    const syncedCountIds = new Set(next.map((r) => String(r.countRowId ?? '')).filter(Boolean))
    for (const r of existing) {
      const id = String(r.id ?? '')
      const name = String(r.securityName ?? '').trim()
      const cid = String(r.countRowId ?? '')
      if (syncedIds.has(id)) continue
      if (cid && syncedCountIds.has(cid)) continue
      if (name && syncedNames.has(name)) continue
      if (name || parseNum(r.countQuantity) || parseNum(r.bookQuantity)) next.push(r)
    }

    const payload = next.map((r, i) => ({ ...r, seq: i + 1 }))
    opts.debouncedSave(RECON_KEY, { conclusion: JSON.stringify(payload) })
    ElMessage.success(`已推送至 G1-12：新增 ${added}、更新 ${updated}（请打开倒轧表核对增减）`)
    return added + updated
  }

  return {
    columns: G1_SECURITIES_COUNT_COLUMNS,
    rows,
    header,
    auditConclusion,
    diffCount,
    diffReasonGaps,
    gateReady,
    headerStatus,
    locationOptions,
    groupedByLocation,
    grandTotal,
    isDiffAbnormal,
    needsDiffReason,
    loadAll,
    persistRows,
    persistHeader,
    updateHeader,
    regenerateNarrative,
    updateRow,
    addRow,
    removeRow,
    pullFromDetail,
    pushToReconciliation,
  }
}

export default useG1SecuritiesCount
