/**
 * G5 上市附注披露行模型 — 对齐致同 Excel「附注披露信息（上市公司）」长期应收款
 *
 * (1) 按性质分类  (2) 坏账准备计提概况 + 单项明细 + 组合账龄块
 * (3) 坏账变动    (4) 未实现融资收益 / 重要核销 / 最低租赁收款
 * 比例类字段用 safeRate，避免模板中的 #DIV/0!
 */

export interface G5PeriodAmt {
  balance: number
  provision: number
}

export type G5NatureKind =
  | 'preset'
  | 'custom'
  | 'subrow'
  | 'subtotal'
  | 'deduction'
  | 'total'

export interface G5NatureRow {
  id: string
  rowKey: string
  label: string
  kind: G5NatureKind
  /** 未实现融资收益等子行挂靠的父 rowKey */
  parentKey?: string
  indent: number
  editable: boolean
  end: G5PeriodAmt
  prior: G5PeriodAmt
  endDiscountRate: string
  priorDiscountRate: string
}

export type G5MethodKind = 'group_header' | 'data' | 'total'

export interface G5MethodRow {
  id: string
  rowKey: string
  label: string
  kind: G5MethodKind
  editable: boolean
  end: G5PeriodAmt
  prior: G5PeriodAmt
}

export interface G5IndividualDetailRow {
  id: string
  name: string
  endBalance: number
  endProvision: number
  endReason: string
  priorBalance: number
  priorProvision: number
  priorReason: string
}

export type G5AgingKind = 'band' | 'total'

export interface G5AgingBandRow {
  id: string
  bandKey: string
  label: string
  kind: G5AgingKind
  endBalance: number
  endProvision: number
  priorBalance: number
  priorProvision: number
}

export interface G5PortfolioBlock {
  id: string
  name: string
  /** 来自会计政策 / G5-3，用于一致性提示 */
  fromPolicy: boolean
  agingRows: G5AgingBandRow[]
}

export type G5MovementKind = 'data' | 'closing'

export interface G5MovementRow {
  rowKey: string
  label: string
  kind: G5MovementKind
  editable: boolean
  gross: number
  provision: number
}

export interface G5WriteoffRow {
  id: string
  name: string
  amount: number
  reason: string
  relatedParty: boolean
}

export interface G5LeaseMlpRow {
  id: string
  periodLabel: string
  endBalance: number
  endProvision: number
  priorBalance: number
  priorProvision: number
  relatedParty: boolean
}

export interface G5ListedDisclosureState {
  version: 1
  natureRows: G5NatureRow[]
  methodRows: G5MethodRow[]
  individualDetails: G5IndividualDetailRow[]
  portfolios: G5PortfolioBlock[]
  movementRows: G5MovementRow[]
  unrealizedNote: string
  writeoffRows: G5WriteoffRow[]
  leaseMlpRows: G5LeaseMlpRow[]
  useThreeStageHintAck: boolean
}

const uid = (prefix: string) =>
  `${prefix}-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`

export function bookValue(amt: G5PeriodAmt): number {
  return round2((Number(amt.balance) || 0) - (Number(amt.provision) || 0))
}

/** 安全比率（%），分母为 0 时返回 null，UI 显示「—」而非 #DIV/0! */
export function safeRate(numerator: number, denominator: number): number | null {
  const d = Number(denominator) || 0
  if (d === 0) return null
  return round2(((Number(numerator) || 0) / d) * 100)
}

export function fmtRate(rate: number | null): string {
  if (rate == null) return '—'
  return `${rate.toFixed(2)}%`
}

export function round2(n: number): number {
  return Math.round((Number(n) || 0) * 100) / 100
}

function emptyAmt(): G5PeriodAmt {
  return { balance: 0, provision: 0 }
}

export const G5_DEFAULT_AGING_BANDS: ReadonlyArray<{ bandKey: string; label: string }> = [
  { bandKey: 'within1', label: '1年以内' },
  { bandKey: 'y1to2', label: '1-2年' },
  { bandKey: 'y2to3', label: '2-3年' },
]

export function createAgingRows(
  bands: ReadonlyArray<{ bandKey: string; label: string }> = G5_DEFAULT_AGING_BANDS,
): G5AgingBandRow[] {
  const rows: G5AgingBandRow[] = bands.map((b) => ({
    id: uid(`age-${b.bandKey}`),
    bandKey: b.bandKey,
    label: b.label,
    kind: 'band' as const,
    endBalance: 0,
    endProvision: 0,
    priorBalance: 0,
    priorProvision: 0,
  }))
  rows.push({
    id: uid('age-total'),
    bandKey: 'total',
    label: '合计',
    kind: 'total',
    endBalance: 0,
    endProvision: 0,
    priorBalance: 0,
    priorProvision: 0,
  })
  return rows
}

export function recomputeAgingTotals(rows: G5AgingBandRow[]): G5AgingBandRow[] {
  const bands = rows.filter((r) => r.kind === 'band')
  const sum = (field: keyof Pick<G5AgingBandRow, 'endBalance' | 'endProvision' | 'priorBalance' | 'priorProvision'>) =>
    round2(bands.reduce((s, r) => s + (Number(r[field]) || 0), 0))
  return rows.map((r) =>
    r.kind === 'total'
      ? {
          ...r,
          endBalance: sum('endBalance'),
          endProvision: sum('endProvision'),
          priorBalance: sum('priorBalance'),
          priorProvision: sum('priorProvision'),
        }
      : r,
  )
}

/** 对应模板「……」动态账龄段：插在合计行前 */
export function insertAgingBand(
  rows: G5AgingBandRow[],
  label = '其他账龄段',
): G5AgingBandRow[] {
  const band: G5AgingBandRow = {
    id: uid('age-extra'),
    bandKey: `custom-${Date.now().toString(36)}`,
    label,
    kind: 'band',
    endBalance: 0,
    endProvision: 0,
    priorBalance: 0,
    priorProvision: 0,
  }
  const totalIdx = rows.findIndex((r) => r.kind === 'total')
  const next = [...rows]
  if (totalIdx >= 0) next.splice(totalIdx, 0, band)
  else next.push(band)
  return recomputeAgingTotals(next)
}

export function removeAgingBand(rows: G5AgingBandRow[], bandId: string): G5AgingBandRow[] {
  const target = rows.find((r) => r.id === bandId)
  if (!target || target.kind !== 'band') return rows
  const bands = rows.filter((r) => r.kind === 'band')
  if (bands.length <= 1) return rows
  return recomputeAgingTotals(rows.filter((r) => r.id !== bandId))
}

export function createEmptyPortfolio(name = ''): G5PortfolioBlock {
  return {
    id: uid('pf'),
    name,
    fromPolicy: false,
    agingRows: createAgingRows(),
  }
}

export function createEmptyIndividualDetail(name = ''): G5IndividualDetailRow {
  return {
    id: uid('ind'),
    name,
    endBalance: 0,
    endProvision: 0,
    endReason: '',
    priorBalance: 0,
    priorProvision: 0,
    priorReason: '',
  }
}

export function createEmptyCustomNature(label = ''): G5NatureRow {
  return {
    id: uid('nat'),
    rowKey: `custom-${uid('k')}`,
    label,
    kind: 'custom',
    indent: 0,
    editable: true,
    end: emptyAmt(),
    prior: emptyAmt(),
    endDiscountRate: '',
    priorDiscountRate: '',
  }
}

export function createEmptyWriteoff(): G5WriteoffRow {
  return {
    id: uid('wo'),
    name: '',
    amount: 0,
    reason: '',
    relatedParty: false,
  }
}

export function createEmptyLeaseMlp(periodLabel = ''): G5LeaseMlpRow {
  return {
    id: uid('mlp'),
    periodLabel,
    endBalance: 0,
    endProvision: 0,
    priorBalance: 0,
    priorProvision: 0,
    relatedParty: false,
  }
}

/** 预置性质分类行（对齐模板，含子行「未实现融资收益」） */
export function buildDefaultNatureRows(): G5NatureRow[] {
  const mk = (
    rowKey: string,
    label: string,
    kind: G5NatureKind,
    opts: { parentKey?: string; indent?: number; editable?: boolean } = {},
  ): G5NatureRow => ({
    id: uid(rowKey),
    rowKey,
    label,
    kind,
    parentKey: opts.parentKey,
    indent: opts.indent ?? (kind === 'subrow' ? 1 : 0),
    editable: opts.editable ?? (kind === 'preset' || kind === 'subrow' || kind === 'deduction'),
    end: emptyAmt(),
    prior: emptyAmt(),
    endDiscountRate: '',
    priorDiscountRate: '',
  })

  return [
    mk('finance-lease', '融资租赁款', 'preset'),
    mk('finance-lease-unrealized', '其中：未实现融资收益', 'subrow', {
      parentKey: 'finance-lease',
    }),
    mk('installment-goods', '分期收款销售商品款', 'preset'),
    mk('installment-goods-unrealized', '其中：未实现融资收益', 'subrow', {
      parentKey: 'installment-goods',
    }),
    mk('installment-services', '分期收款提供劳务款', 'preset'),
    mk('installment-services-unrealized', '其中：未实现融资收益', 'subrow', {
      parentKey: 'installment-services',
    }),
    mk('deposit', '应收保证金', 'preset'),
    mk('related', '应收关联方款项', 'preset'),
    mk('other', '其他', 'preset'),
    mk('subtotal', '小计', 'subtotal', { editable: false }),
    mk('one-year', '减：一年内到期的长期应收款', 'deduction'),
    mk('total', '合计', 'total', { editable: false }),
  ]
}

export function buildDefaultMethodRows(): G5MethodRow[] {
  const mk = (
    rowKey: string,
    label: string,
    kind: G5MethodKind,
    editable: boolean,
  ): G5MethodRow => ({
    id: uid(rowKey),
    rowKey,
    label,
    kind,
    editable,
    end: emptyAmt(),
    prior: emptyAmt(),
  })
  return [
    mk('individual', '按单项计提坏账准备', 'data', true),
    mk('collective', '按组合计提坏账准备', 'data', true),
    mk('total', '合计', 'total', false),
  ]
}

export function buildDefaultMovementRows(): G5MovementRow[] {
  const defs: Array<{ rowKey: string; label: string; kind: G5MovementKind; editable: boolean }> = [
    { rowKey: 'opening', label: '期初余额', kind: 'data', editable: true },
    { rowKey: 'provision', label: '本期计提', kind: 'data', editable: true },
    { rowKey: 'recovery', label: '本期收回或转回', kind: 'data', editable: true },
    { rowKey: 'charge-off', label: '本期转销', kind: 'data', editable: true },
    { rowKey: 'write-off', label: '本期核销', kind: 'data', editable: true },
    { rowKey: 'other', label: '其他变动', kind: 'data', editable: true },
    { rowKey: 'closing', label: '期末余额', kind: 'closing', editable: false },
  ]
  return defs.map((d) => ({ ...d, gross: 0, provision: 0 }))
}

export function buildDefaultLeaseMlpRows(): G5LeaseMlpRow[] {
  return [
    createEmptyLeaseMlp('1年以内'),
    createEmptyLeaseMlp('1-2年'),
    createEmptyLeaseMlp('2-3年'),
    createEmptyLeaseMlp('3年以上'),
  ]
}

export function buildDefaultListedState(): G5ListedDisclosureState {
  return {
    version: 1,
    natureRows: buildDefaultNatureRows(),
    methodRows: buildDefaultMethodRows(),
    individualDetails: [],
    portfolios: [createEmptyPortfolio('组合1')],
    movementRows: buildDefaultMovementRows(),
    unrealizedNote: '',
    writeoffRows: [],
    leaseMlpRows: buildDefaultLeaseMlpRows(),
    useThreeStageHintAck: false,
  }
}

/** 性质表派生：小计/合计（小计不含扣除行；合计=小计−一年内） */
export function recomputeNatureDerived(rows: G5NatureRow[]): G5NatureRow[] {
  const summable = rows.filter(
    (r) => r.kind === 'preset' || r.kind === 'custom',
  )
  const sumEndBal = round2(summable.reduce((s, r) => s + (Number(r.end.balance) || 0), 0))
  const sumEndProv = round2(summable.reduce((s, r) => s + (Number(r.end.provision) || 0), 0))
  const sumPriorBal = round2(summable.reduce((s, r) => s + (Number(r.prior.balance) || 0), 0))
  const sumPriorProv = round2(summable.reduce((s, r) => s + (Number(r.prior.provision) || 0), 0))

  const oneYear = rows.find((r) => r.rowKey === 'one-year')
  const oyEndBal = Number(oneYear?.end.balance) || 0
  const oyEndProv = Number(oneYear?.end.provision) || 0
  const oyPriorBal = Number(oneYear?.prior.balance) || 0
  const oyPriorProv = Number(oneYear?.prior.provision) || 0

  return rows.map((r) => {
    if (r.kind === 'subtotal') {
      return {
        ...r,
        end: { balance: sumEndBal, provision: sumEndProv },
        prior: { balance: sumPriorBal, provision: sumPriorProv },
      }
    }
    if (r.kind === 'total') {
      return {
        ...r,
        end: {
          balance: round2(sumEndBal - oyEndBal),
          provision: round2(sumEndProv - oyEndProv),
        },
        prior: {
          balance: round2(sumPriorBal - oyPriorBal),
          provision: round2(sumPriorProv - oyPriorProv),
        },
      }
    }
    return r
  })
}

export function recomputeMethodTotals(rows: G5MethodRow[]): G5MethodRow[] {
  const data = rows.filter((r) => r.kind === 'data')
  const sumEndBal = round2(data.reduce((s, r) => s + (Number(r.end.balance) || 0), 0))
  const sumEndProv = round2(data.reduce((s, r) => s + (Number(r.end.provision) || 0), 0))
  const sumPriorBal = round2(data.reduce((s, r) => s + (Number(r.prior.balance) || 0), 0))
  const sumPriorProv = round2(data.reduce((s, r) => s + (Number(r.prior.provision) || 0), 0))
  return rows.map((r) =>
    r.kind === 'total'
      ? {
          ...r,
          end: { balance: sumEndBal, provision: sumEndProv },
          prior: { balance: sumPriorBal, provision: sumPriorProv },
        }
      : r,
  )
}

/** 坏账变动：期末 = 期初 + 计提 − 收回转回 − 转销 − 核销 + 其他 */
export function recomputeMovementClosing(rows: G5MovementRow[]): G5MovementRow[] {
  const get = (key: string) => rows.find((r) => r.rowKey === key)
  const calc = (field: 'gross' | 'provision') => {
    const opening = Number(get('opening')?.[field]) || 0
    const provision = Number(get('provision')?.[field]) || 0
    const recovery = Number(get('recovery')?.[field]) || 0
    const chargeOff = Number(get('charge-off')?.[field]) || 0
    const writeOff = Number(get('write-off')?.[field]) || 0
    const other = Number(get('other')?.[field]) || 0
    return round2(opening + provision - recovery - chargeOff - writeOff + other)
  }
  return rows.map((r) =>
    r.kind === 'closing'
      ? { ...r, gross: calc('gross'), provision: calc('provision') }
      : r,
  )
}

export interface G5TieOutResult {
  natureTotalEnd: number
  methodTotalEnd: number
  natureProvEnd: number
  methodProvEnd: number
  balanceDiff: number
  provisionDiff: number
  matched: boolean
}

export function computeNatureMethodTieOut(
  natureRows: G5NatureRow[],
  methodRows: G5MethodRow[],
): G5TieOutResult {
  const nat = recomputeNatureDerived(natureRows).find((r) => r.kind === 'total')
  const meth = recomputeMethodTotals(methodRows).find((r) => r.kind === 'total')
  const natureTotalEnd = Number(nat?.end.balance) || 0
  const methodTotalEnd = Number(meth?.end.balance) || 0
  const natureProvEnd = Number(nat?.end.provision) || 0
  const methodProvEnd = Number(meth?.end.provision) || 0
  const balanceDiff = round2(natureTotalEnd - methodTotalEnd)
  const provisionDiff = round2(natureProvEnd - methodProvEnd)
  return {
    natureTotalEnd,
    methodTotalEnd,
    natureProvEnd,
    methodProvEnd,
    balanceDiff,
    provisionDiff,
    matched: Math.abs(balanceDiff) < 0.01 && Math.abs(provisionDiff) < 0.01,
  }
}

export function serializeListedDisclosure(state: G5ListedDisclosureState): string {
  return JSON.stringify({ ...state, version: 1 })
}

function asAmt(raw: unknown): G5PeriodAmt {
  if (!raw || typeof raw !== 'object') return emptyAmt()
  const o = raw as Record<string, unknown>
  return {
    balance: Number(o.balance) || 0,
    provision: Number(o.provision) || 0,
  }
}

export function parseListedDisclosure(
  raw: string | null | undefined,
): G5ListedDisclosureState | null {
  if (!raw?.trim()) return null
  try {
    const parsed = JSON.parse(raw)
    if (!parsed || typeof parsed !== 'object') return null
    // 兼容旧 stub：纯文本不解析为结构化
    if (typeof parsed === 'string') return null

    const base = buildDefaultListedState()
    const natureRows = Array.isArray(parsed.natureRows)
      ? (parsed.natureRows as G5NatureRow[]).map((r) => ({
          ...createEmptyCustomNature(),
          ...r,
          end: asAmt(r.end),
          prior: asAmt(r.prior),
          endDiscountRate: String(r.endDiscountRate ?? ''),
          priorDiscountRate: String(r.priorDiscountRate ?? ''),
        }))
      : base.natureRows

    const methodRows = Array.isArray(parsed.methodRows)
      ? (parsed.methodRows as G5MethodRow[]).map((r) => ({
          ...buildDefaultMethodRows()[0],
          ...r,
          end: asAmt(r.end),
          prior: asAmt(r.prior),
        }))
      : base.methodRows

    const portfolios = Array.isArray(parsed.portfolios)
      ? (parsed.portfolios as G5PortfolioBlock[]).map((p) => ({
          id: p.id || uid('pf'),
          name: String(p.name ?? ''),
          fromPolicy: !!p.fromPolicy,
          agingRows: recomputeAgingTotals(
            Array.isArray(p.agingRows) && p.agingRows.length
              ? p.agingRows.map((a) => ({
                  id: a.id || uid('age'),
                  bandKey: String(a.bandKey ?? ''),
                  label: String(a.label ?? ''),
                  kind: a.kind === 'total' ? 'total' : 'band',
                  endBalance: Number(a.endBalance) || 0,
                  endProvision: Number(a.endProvision) || 0,
                  priorBalance: Number(a.priorBalance) || 0,
                  priorProvision: Number(a.priorProvision) || 0,
                }))
              : createAgingRows(),
          ),
        }))
      : base.portfolios

    return {
      version: 1,
      natureRows: recomputeNatureDerived(natureRows.length ? natureRows : base.natureRows),
      methodRows: recomputeMethodTotals(methodRows.length ? methodRows : base.methodRows),
      individualDetails: Array.isArray(parsed.individualDetails)
        ? parsed.individualDetails.map((r: G5IndividualDetailRow) => ({
            ...createEmptyIndividualDetail(),
            ...r,
            id: r.id || uid('ind'),
          }))
        : [],
      portfolios,
      movementRows: recomputeMovementClosing(
        Array.isArray(parsed.movementRows) && parsed.movementRows.length
          ? parsed.movementRows.map((r: G5MovementRow) => ({
              ...buildDefaultMovementRows()[0],
              ...r,
            }))
          : base.movementRows,
      ),
      unrealizedNote: String(parsed.unrealizedNote ?? ''),
      writeoffRows: Array.isArray(parsed.writeoffRows)
        ? parsed.writeoffRows.map((r: G5WriteoffRow) => ({
            ...createEmptyWriteoff(),
            ...r,
            id: r.id || uid('wo'),
          }))
        : [],
      leaseMlpRows: Array.isArray(parsed.leaseMlpRows) && parsed.leaseMlpRows.length
        ? parsed.leaseMlpRows.map((r: G5LeaseMlpRow) => ({
            ...createEmptyLeaseMlp(),
            ...r,
            id: r.id || uid('mlp'),
          }))
        : base.leaseMlpRows,
      useThreeStageHintAck: !!parsed.useThreeStageHintAck,
    }
  } catch {
    return null
  }
}

/** 从 G5-1 审定 store 取期初/期末审定数 */
export function extractAdjCell(
  store: Record<string, { openingUnadjusted?: number; openingAJE?: number; openingRJE?: number; closingUnadjusted?: number; closingAJE?: number; closingRJE?: number } | undefined>,
  rowKey: string,
): { opening: number; closing: number } {
  const cell = store[rowKey]
  if (!cell) return { opening: 0, closing: 0 }
  const opening =
    (Number(cell.openingUnadjusted) || 0)
    + (Number(cell.openingAJE) || 0)
    + (Number(cell.openingRJE) || 0)
  const closing =
    (Number(cell.closingUnadjusted) || 0)
    + (Number(cell.closingAJE) || 0)
    + (Number(cell.closingRJE) || 0)
  return { opening: round2(opening), closing: round2(closing) }
}

/**
 * 从 G5-2 明细按业务类型归集到性质行
 * lease→融资租赁；installment→分期商品；其余→其他；关联方单独
 */
export function classifyNatureFromDetail(
  detailRaw: string | null | undefined,
): Partial<Record<string, { end: G5PeriodAmt; prior: G5PeriodAmt; unrealizedEnd: number; unrealizedPrior: number }>> {
  const out: Partial<
    Record<string, { end: G5PeriodAmt; prior: G5PeriodAmt; unrealizedEnd: number; unrealizedPrior: number }>
  > = {}
  if (!detailRaw) return out
  try {
    const parsed = JSON.parse(detailRaw)
    const rows = Array.isArray(parsed) ? parsed : parsed?.rows
    if (!Array.isArray(rows)) return out

    const bump = (
      key: string,
      endBal: number,
      priorBal: number,
      unrealEnd: number,
      unrealPrior: number,
    ) => {
      const cur = out[key] ?? {
        end: emptyAmt(),
        prior: emptyAmt(),
        unrealizedEnd: 0,
        unrealizedPrior: 0,
      }
      cur.end.balance = round2(cur.end.balance + endBal)
      cur.prior.balance = round2(cur.prior.balance + priorBal)
      cur.unrealizedEnd = round2(cur.unrealizedEnd + unrealEnd)
      cur.unrealizedPrior = round2(cur.unrealizedPrior + unrealPrior)
      out[key] = cur
    }

    for (const r of rows) {
      const endBal = Number(r.closingBalance ?? r.netAmount ?? 0) || 0
      const priorBal = Number(r.priorBalance ?? r.openingBalance ?? 0) || 0
      const unrealEnd = Number(r.unrealizedIncome ?? 0) || 0
      const unrealPrior = Number(r.priorUnrealizedIncome ?? 0) || 0
      if (r.isRelatedParty) {
        bump('related', endBal, priorBal, 0, 0)
        continue
      }
      const bt = String(r.businessType || '').toLowerCase()
      if (bt === 'lease' || /租赁|融资租赁/.test(String(r.businessType || ''))) {
        bump('finance-lease', endBal, priorBal, unrealEnd, unrealPrior)
      } else if (bt === 'installment' || /分期/.test(String(r.businessType || ''))) {
        bump('installment-goods', endBal, priorBal, unrealEnd, unrealPrior)
      } else if (/保证|质保|押金|deposit/i.test(String(r.debtorName || '') + String(r.remark || ''))) {
        bump('deposit', endBal, priorBal, 0, 0)
      } else {
        bump('other', endBal, priorBal, unrealEnd, unrealPrior)
      }
    }
  } catch {
    /* ignore */
  }
  return out
}

/** 从 G5-3 提取单项/组合名称与金额（兼容滚动态 + 旧 ECL） */
export function extractBadDebtForDisclosure(badRaw: string | null | undefined): {
  individual: G5IndividualDetailRow[]
  groupNames: string[]
  individualTotals: { end: G5PeriodAmt; prior: G5PeriodAmt }
  groupTotals: { end: G5PeriodAmt; prior: G5PeriodAmt }
} {
  const empty = {
    individual: [] as G5IndividualDetailRow[],
    groupNames: [] as string[],
    individualTotals: { end: emptyAmt(), prior: emptyAmt() },
    groupTotals: { end: emptyAmt(), prior: emptyAmt() },
  }
  if (!badRaw) return empty
  try {
    const parsed = JSON.parse(badRaw)
    const rows = Array.isArray(parsed) ? parsed : parsed?.rows
    if (!Array.isArray(rows)) return empty

    const individual: G5IndividualDetailRow[] = []
    const groupNames: string[] = []
    const indT = { end: emptyAmt(), prior: emptyAmt() }
    const grpT = { end: emptyAmt(), prior: emptyAmt() }

    for (const r of rows) {
      if (r?.kind === 'section_header' || r?.kind === 'subtotal' || r?.kind === 'total') continue
      const name = String(r.item || r.debtorOrGroup || '').trim()
      const openingUnadj = Number(r.openingUnadjusted) || 0
      const openingAdj = Number(r.openingAdjustment) || 0
      const hasMovement =
        'openingUnadjusted' in (r || {})
        || 'provisionIncrease' in (r || {})
        || 'closingAdjustment' in (r || {})
      const openingAudited = Number(r.openingAudited) || round2(openingUnadj + openingAdj)
      const closingFromMovement = hasMovement
        ? round2(
          openingAudited
          + (Number(r.provisionIncrease) || 0)
          + (Number(r.otherIncrease) || 0)
          - (Number(r.reversal) || 0)
          - (Number(r.writeOff) || 0)
          - (Number(r.otherDecrease) || 0)
          + (Number(r.closingAdjustment) || 0),
        )
        : 0
      const endProv = Number(
        r.closingAudited
        ?? r.adjustedProvision
        ?? (hasMovement ? closingFromMovement : undefined)
        ?? r.unadjustedProvision
        ?? 0,
      ) || 0
      const priorProv = Number(
        r.openingAudited
        ?? (hasMovement ? openingAudited : undefined)
        ?? r.priorYearProvision
        ?? 0,
      ) || 0
      const isIndividual =
        r.category === 'individual' || r.provisionMethod === 'individual'
      const endBal = Number(r.adjustedBalance ?? r.closingBalance ?? 0) || 0

      if (isIndividual) {
        individual.push({
          ...createEmptyIndividualDetail(name),
          endBalance: endBal,
          endProvision: endProv,
          endReason: String(r.reason || r.adjustmentDesc || r.remark || ''),
          priorBalance: 0,
          priorProvision: priorProv,
          priorReason: '',
        })
        indT.end.balance = round2(indT.end.balance + endBal)
        indT.end.provision = round2(indT.end.provision + endProv)
        indT.prior.provision = round2(indT.prior.provision + priorProv)
      } else {
        if (name && !groupNames.includes(name)) groupNames.push(name)
        grpT.end.balance = round2(grpT.end.balance + endBal)
        grpT.end.provision = round2(grpT.end.provision + endProv)
        grpT.prior.provision = round2(grpT.prior.provision + priorProv)
      }
    }
    return { individual, groupNames, individualTotals: indT, groupTotals: grpT }
  } catch {
    return empty
  }
}

/** 从 G5-8 section2 检查项提取组合名称候选 */
export function extractPolicyGroupNames(policyRaw: string | null | undefined): string[] {
  if (!policyRaw) return []
  try {
    const parsed = JSON.parse(policyRaw)
    const section2 = parsed?.section2
    if (!Array.isArray(section2)) return []
    return section2
      .map((r: { checkItem?: string; companyPolicy?: string }) =>
        String(r.companyPolicy || r.checkItem || '').trim(),
      )
      .filter(Boolean)
  } catch {
    return []
  }
}

/**
 * 将组合名称列表同步为组合账龄块：保留已有同名块数据，新增缺失名，可选移除多余
 */
export function syncPortfoliosByNames(
  existing: G5PortfolioBlock[],
  names: string[],
  opts: { removeMissing?: boolean; markFromPolicy?: boolean } = {},
): G5PortfolioBlock[] {
  const { removeMissing = false, markFromPolicy = true } = opts
  const map = new Map(existing.map((p) => [p.name.trim(), p]))
  const result: G5PortfolioBlock[] = []
  for (const name of names) {
    const key = name.trim()
    if (!key) continue
    const found = map.get(key)
    if (found) {
      result.push({ ...found, fromPolicy: markFromPolicy || found.fromPolicy })
      map.delete(key)
    } else {
      result.push({ ...createEmptyPortfolio(key), fromPolicy: markFromPolicy })
    }
  }
  if (!removeMissing) {
    for (const left of map.values()) result.push(left)
  }
  return result.length ? result : existing
}
