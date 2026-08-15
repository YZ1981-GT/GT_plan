/**
 * I2 附注披露（上市/国企）数据模型
 * 对齐源表：按性质拆分 + 项目滚动 + 重要资本化项目 + 减值准备；联动 I2-2/I2-6/I2-7/I2-15
 */

export const I2_DISC_KEYS = {
  listedNature: 'I2-disc-listed-nature',
  listedMovement: 'I2-disc-listed-movement',
  listedImportant: 'I2-disc-listed-important',
  listedImpairment: 'I2-disc-listed-impairment',
  listedNote: 'I2-disc-listed-note',
  listedNoteCap: 'I2-disc-listed-note-cap',
  listedNoteImpairTest: 'I2-disc-listed-note-impair-test',
  listedNotePurchased: 'I2-disc-listed-note-purchased',
  listedAuditNote: 'I2-disc-listed-audit-note',
  listedAuditConclusion: 'I2-disc-listed-audit-conclusion',
  /** 兼容旧单表 */
  listedLegacyRows: 'I2-disc-listed-rows',

  soeMovement: 'I2-disc-soe-movement',
  soeNote: 'I2-disc-soe-note',
  soeAuditNote: 'I2-disc-soe-audit-note',
  soeAuditConclusion: 'I2-disc-soe-audit-conclusion',
  soeLegacyRows: 'I2-disc-soe-rows',
} as const

/** 上市：研发投入按性质（15号文第二十六条） */
export interface I2NatureRow {
  rowId: string
  name: string
  currentExpensed: number
  currentCapitalized: number
  priorExpensed: number
  priorCapitalized: number
  isTotal?: boolean
}

/** 上市/国企共用：开发支出项目滚动 */
export interface I2MovementRow {
  rowId: string
  name: string
  beginBalance: number
  increaseInternal: number
  increaseOther: number
  decreaseToIntangible: number
  decreaseToExpense: number
  /** 国企多一列「其他减少」 */
  decreaseOther: number
  endBalance: number
  /** 续表：资本化时点/依据/进度（修 #REF!） */
  capStartDate: string
  capBasis: string
  progress: string
  isTotal?: boolean
  isAutoFilled?: boolean
}

export interface I2ImportantCapRow {
  rowId: string
  name: string
  progress: string
  expectedCompletion: string
  economicBenefit: string
  capStartDate: string
  capBasis: string
}

export interface I2ImpairmentRow {
  rowId: string
  name: string
  beginBalance: number
  provision: number
  decrease: number
  endBalance: number
  isTotal?: boolean
}

export const I2_NATURE_DEFAULT_NAMES = [
  '人工费',
  '材料费',
  '水电燃气费',
  '折旧费',
  '无形资产摊销',
  '外购在研项目',
] as const

function _num(v: unknown): number {
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

function _str(v: unknown): string {
  return v == null ? '' : String(v)
}

function _round2(n: number): number {
  return Math.round(n * 100) / 100
}

/** 项目名规范化：去空格/标点/大小写，便于模糊匹配 */
export function normalizeProjectKey(name: string): string {
  return String(name || '')
    .trim()
    .toLowerCase()
    .replace(/[\s\-_/\\（）()【】\[\]·•.,，。:：]+/g, '')
}

/**
 * 在 Map(项目名→源) 中查找：精确 → 规范化相等 → 唯一包含关系。
 * 返回 matchKind 供上层告警。
 */
export function findProjectSource(
  byName: Map<string, any>,
  name: string,
): { src: any; key: string; matchKind: 'exact' | 'normalized' | 'contains' } | null {
  const trimmed = String(name || '').trim()
  if (!trimmed || !byName.size) return null
  if (byName.has(trimmed)) return { src: byName.get(trimmed), key: trimmed, matchKind: 'exact' }

  const key = normalizeProjectKey(trimmed)
  if (!key) return null
  for (const [k, v] of byName) {
    if (normalizeProjectKey(k) === key) return { src: v, key: k, matchKind: 'normalized' }
  }
  const candidates = [...byName.entries()].filter(([k]) => {
    const nk = normalizeProjectKey(k)
    return nk.includes(key) || key.includes(nk)
  })
  if (candidates.length === 1) {
    return { src: candidates[0][1], key: candidates[0][0], matchKind: 'contains' }
  }
  return null
}

function _id(prefix: string): string {
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`
}

export function emptyNatureRow(partial?: Partial<I2NatureRow>): I2NatureRow {
  return {
    rowId: partial?.rowId || _id('nat'),
    name: '',
    currentExpensed: 0,
    currentCapitalized: 0,
    priorExpensed: 0,
    priorCapitalized: 0,
    isTotal: false,
    ...partial,
  }
}

export function defaultNatureRows(): I2NatureRow[] {
  return I2_NATURE_DEFAULT_NAMES.map((name) => emptyNatureRow({ name }))
}

/** 行名归一（去首尾空白 + 折叠内部空白），仅用于撞名比较 */
function _normNatureName(name: unknown): string {
  return String(name ?? '').trim().replace(/\s+/g, '')
}

/** 该行是否源模板固定的 6 类费用性质（`A9:A14`）—— 固定类别不可删 */
export function isI2NatureDefaultRow(row: I2NatureRow): boolean {
  const key = _normNatureName(row?.name)
  if (!key) return false
  return I2_NATURE_DEFAULT_NAMES.some((n) => _normNatureName(n) === key)
}

/**
 * 研发支出按费用性质增行 —— 对齐源模板 `附注披露（上市公司）!A15 = ……` 唯一可扩位。
 *
 * 纯函数（与 `addI1SoeCategory` 同范式）：**命名非法或撞名一律返回 `null`**，
 * 由调用方（组件 `ElMessageBox.prompt`）负责提示，绝不产生无名行。
 * 撞名比较覆盖「源模板 6 个固定类别 + 现存全部行」，归一后比较。
 */
export function addI2NatureRow(
  rows: readonly I2NatureRow[],
  label: string,
): I2NatureRow[] | null {
  const name = String(label ?? '').trim()
  const key = _normNatureName(name)
  if (!key) return null
  const taken = new Set<string>([
    ...I2_NATURE_DEFAULT_NAMES.map(_normNatureName),
    ...rows.map((r) => _normNatureName(r?.name)),
  ])
  if (taken.has(key)) return null
  return [...rows, emptyNatureRow({ name })]
}

/** 删除自定义费用性质行；源模板固定 6 类或找不到 rowId 时返回 `null`（不改数据） */
export function removeI2NatureRow(
  rows: readonly I2NatureRow[],
  rowId: string,
): I2NatureRow[] | null {
  const idx = rows.findIndex((r) => r?.rowId === rowId)
  if (idx < 0) return null
  if (isI2NatureDefaultRow(rows[idx])) return null
  return rows.filter((_, i) => i !== idx)
}

export function emptyMovementRow(partial?: Partial<I2MovementRow>): I2MovementRow {
  const row: I2MovementRow = {
    rowId: partial?.rowId || _id('mov'),
    name: '',
    beginBalance: 0,
    increaseInternal: 0,
    increaseOther: 0,
    decreaseToIntangible: 0,
    decreaseToExpense: 0,
    decreaseOther: 0,
    endBalance: 0,
    capStartDate: '',
    capBasis: '',
    progress: '',
    isTotal: false,
    isAutoFilled: false,
    ...partial,
  }
  recalcMovementEnd(row)
  return row
}

export function recalcMovementEnd(row: I2MovementRow): void {
  row.endBalance = _round2(
    _num(row.beginBalance)
    + _num(row.increaseInternal)
    + _num(row.increaseOther)
    - _num(row.decreaseToIntangible)
    - _num(row.decreaseToExpense)
    - _num(row.decreaseOther),
  )
}

export function emptyImportantRow(partial?: Partial<I2ImportantCapRow>): I2ImportantCapRow {
  return {
    rowId: partial?.rowId || _id('imp'),
    name: '',
    progress: '',
    expectedCompletion: '',
    economicBenefit: '',
    capStartDate: '',
    capBasis: '',
    ...partial,
  }
}

export function emptyImpairmentRow(partial?: Partial<I2ImpairmentRow>): I2ImpairmentRow {
  const row: I2ImpairmentRow = {
    rowId: partial?.rowId || _id('impr'),
    name: '',
    beginBalance: 0,
    provision: 0,
    decrease: 0,
    endBalance: 0,
    isTotal: false,
    ...partial,
  }
  row.endBalance = _round2(_num(row.beginBalance) + _num(row.provision) - _num(row.decrease))
  return row
}

export function normalizeNatureRow(raw: any): I2NatureRow {
  return emptyNatureRow({
    rowId: _str(raw?.rowId) || undefined,
    name: _str(raw?.name),
    currentExpensed: _num(raw?.currentExpensed),
    currentCapitalized: _num(raw?.currentCapitalized),
    priorExpensed: _num(raw?.priorExpensed),
    priorCapitalized: _num(raw?.priorCapitalized),
    isTotal: !!raw?.isTotal,
  })
}

export function normalizeMovementRow(raw: any): I2MovementRow {
  // 兼容旧上市单表：increase/decrease
  const increaseInternal = raw?.increaseInternal != null
    ? _num(raw.increaseInternal)
    : _num(raw?.increase ?? raw?.increaseCapitalized ?? raw?.capIncrease)
  const decreaseToIntangible = raw?.decreaseToIntangible != null
    ? _num(raw.decreaseToIntangible)
    : _num(raw?.decrease ?? raw?.transferToI1 ?? raw?.capDecrease)
  return emptyMovementRow({
    rowId: _str(raw?.rowId) || undefined,
    name: _str(raw?.name || raw?.projectName),
    beginBalance: _num(raw?.beginBalance ?? raw?.capBeginAmount ?? raw?.openingBalance),
    increaseInternal,
    increaseOther: _num(raw?.increaseOther),
    decreaseToIntangible,
    decreaseToExpense: _num(raw?.decreaseToExpense ?? raw?.increaseExpensed),
    decreaseOther: _num(raw?.decreaseOther),
    capStartDate: _str(raw?.capStartDate || raw?.capitalizationStart),
    capBasis: _str(raw?.capBasis),
    progress: _str(raw?.progress ?? (raw?.completionRate != null ? `${raw.completionRate}%` : '')),
    isTotal: !!raw?.isTotal,
    isAutoFilled: !!raw?.isAutoFilled,
  })
}

export function normalizeImportantRow(raw: any): I2ImportantCapRow {
  return emptyImportantRow({
    rowId: _str(raw?.rowId) || undefined,
    name: _str(raw?.name || raw?.projectName),
    progress: _str(raw?.progress),
    expectedCompletion: _str(raw?.expectedCompletion || raw?.endDate),
    economicBenefit: _str(raw?.economicBenefit),
    capStartDate: _str(raw?.capStartDate),
    capBasis: _str(raw?.capBasis),
  })
}

export function normalizeImpairmentRow(raw: any): I2ImpairmentRow {
  return emptyImpairmentRow({
    rowId: _str(raw?.rowId) || undefined,
    name: _str(raw?.name || raw?.projectName),
    beginBalance: _num(raw?.beginBalance),
    provision: _num(raw?.provision ?? raw?.impairment ?? raw?.capImpairment),
    decrease: _num(raw?.decrease),
    isTotal: !!raw?.isTotal,
  })
}

export function summarizeNature(rows: I2NatureRow[]) {
  const data = rows.filter((r) => !r.isTotal)
  return {
    currentExpensed: _round2(data.reduce((s, r) => s + r.currentExpensed, 0)),
    currentCapitalized: _round2(data.reduce((s, r) => s + r.currentCapitalized, 0)),
    priorExpensed: _round2(data.reduce((s, r) => s + r.priorExpensed, 0)),
    priorCapitalized: _round2(data.reduce((s, r) => s + r.priorCapitalized, 0)),
  }
}

export function summarizeMovement(rows: I2MovementRow[]) {
  const data = rows.filter((r) => !r.isTotal)
  data.forEach(recalcMovementEnd)
  return {
    begin: _round2(data.reduce((s, r) => s + r.beginBalance, 0)),
    increaseInternal: _round2(data.reduce((s, r) => s + r.increaseInternal, 0)),
    increaseOther: _round2(data.reduce((s, r) => s + r.increaseOther, 0)),
    decreaseToIntangible: _round2(data.reduce((s, r) => s + r.decreaseToIntangible, 0)),
    decreaseToExpense: _round2(data.reduce((s, r) => s + r.decreaseToExpense, 0)),
    decreaseOther: _round2(data.reduce((s, r) => s + r.decreaseOther, 0)),
    end: _round2(data.reduce((s, r) => s + r.endBalance, 0)),
  }
}

/** 从 I2-2 明细带入项目滚动 */
export function seedMovementFromI22(detailRows: any[]): I2MovementRow[] {
  return detailRows
    .filter((r) => {
      const name = _str(r?.projectName || r?.name).trim()
      return name && name !== '合计'
    })
    .map((r) => normalizeMovementRow({
      name: r.projectName || r.name,
      beginBalance: r.capBeginAmount ?? r.beginBalance,
      increaseInternal: r.capIncrease ?? r.increase,
      decreaseToIntangible: r.transferToI1 ?? r.decreaseToIntangible,
      decreaseToExpense: r.decreaseToExpense,
      capStartDate: r.capStartDate || r.capitalizationStart,
      progress: r.progress != null && r.progress !== ''
        ? (typeof r.progress === 'number' ? `${r.progress}%` : r.progress)
        : (r.completionRate != null ? `${r.completionRate}%` : ''),
      isAutoFilled: true,
    }))
}

/** 用 I2-6 资本化时点/依据/进度补齐滚动行与重要项目（修复源表 #REF!） */
export function enrichFromI26(
  movement: I2MovementRow[],
  important: I2ImportantCapRow[],
  capRows: any[],
): {
  movement: I2MovementRow[]
  important: I2ImportantCapRow[]
  filled: number
  unmatched: string[]
  fuzzyMatched: string[]
} {
  const byName = new Map<string, any>()
  for (const r of capRows) {
    const n = _str(r?.projectName || r?.name).trim()
    if (n) byName.set(n, r)
  }
  let filled = 0
  const unmatched: string[] = []
  const fuzzyMatched: string[] = []

  const nextMov = movement.map((m) => {
    const hit = findProjectSource(byName, m.name)
    if (!hit) {
      if (m.name.trim()) unmatched.push(m.name.trim())
      return m
    }
    if (hit.matchKind !== 'exact') fuzzyMatched.push(`${m.name}→${hit.key}`)
    const src = hit.src
    const next = { ...m }
    if (!next.capStartDate && src.capStartDate) { next.capStartDate = _str(src.capStartDate); filled++ }
    if (!next.capBasis && (src.capBasis || src.basis)) { next.capBasis = _str(src.capBasis || src.basis); filled++ }
    if (!next.progress && src.progress) { next.progress = _str(src.progress); filled++ }
    return next
  })

  let nextImp = [...important]
  if (!nextImp.length) {
    nextImp = [...byName.values()]
      .filter((r) => _str(r.capStartDate) || _num(r.developmentAmount) > 0)
      .map((r) => emptyImportantRow({
        name: _str(r.projectName || r.name),
        progress: _str(r.progress),
        expectedCompletion: _str(r.expectedCompletion || r.endDate),
        capStartDate: _str(r.capStartDate),
        capBasis: _str(r.capBasis || r.basis),
      }))
    filled += nextImp.length
  } else {
    nextImp = nextImp.map((m) => {
      const hit = findProjectSource(byName, m.name)
      if (!hit) {
        if (m.name.trim()) unmatched.push(m.name.trim())
        return m
      }
      if (hit.matchKind !== 'exact') fuzzyMatched.push(`${m.name}→${hit.key}`)
      const src = hit.src
      const next = { ...m }
      if (!next.capStartDate && src.capStartDate) { next.capStartDate = _str(src.capStartDate); filled++ }
      if (!next.capBasis && (src.capBasis || src.basis)) { next.capBasis = _str(src.capBasis || src.basis); filled++ }
      if (!next.progress && src.progress) { next.progress = _str(src.progress); filled++ }
      return next
    })
  }
  return {
    movement: nextMov,
    important: nextImp,
    filled,
    unmatched: [...new Set(unmatched)],
    fuzzyMatched: [...new Set(fuzzyMatched)],
  }
}

/** 从 I2-7 本期增加填性质表资本化列（粗映射） */
export function seedNatureCapitalizedFromI27(projectRows: any[]): Partial<Record<string, number>> {
  let material = 0
  let labor = 0
  let dep = 0
  let energy = 0
  let outsource = 0
  let other = 0
  for (const r of projectRows) {
    if (r?.increase && typeof r.increase === 'object') {
      material += _num(r.increase.material)
      labor += _num(r.increase.labor)
      dep += _num(r.increase.depreciation)
      energy += _num(r.increase.energy)
      outsource += _num(r.increase.outsource)
      other += _num(r.increase.other)
    } else {
      material += _num(r?.materialSubtotal ?? r?.materialDirect)
      labor += _num(r?.laborSubtotal)
      dep += _num(r?.depSubtotal)
      other += _num(r?.otherSubtotal)
    }
  }
  return {
    材料费: _round2(material),
    人工费: _round2(labor),
    折旧费: _round2(dep),
    水电燃气费: _round2(energy),
    外购在研项目: _round2(outsource),
  }
}

export function applyNatureCapitalizedMap(
  rows: I2NatureRow[],
  map: Partial<Record<string, number>>,
): I2NatureRow[] {
  return rows.map((r) => {
    if (r.isTotal) return r
    const v = map[r.name]
    if (v == null) return r
    return { ...r, currentCapitalized: v }
  })
}

export function safeParseArray(raw: unknown): any[] {
  if (Array.isArray(raw)) return raw
  if (typeof raw === 'string' && raw) {
    try {
      const p = JSON.parse(raw)
      return Array.isArray(p) ? p : []
    } catch { return [] }
  }
  if (raw && typeof raw === 'object') {
    const obj = raw as any
    return safeParseArray(obj.remark ?? obj.conclusion)
  }
  return []
}

export function readText(raw: unknown): string {
  if (raw == null) return ''
  if (typeof raw === 'string') return raw
  if (typeof raw === 'object') return String((raw as any).remark ?? (raw as any).conclusion ?? '')
  return ''
}
