/**
 * 凭证检查行回写契约（spec voucher-identity-writeback-and-audit-phase 任务 9，需求 4，design §4，
 * ADR-VK-06 / 07 / 08 / 12）
 *
 * 抽凭引擎回填、「从序时账挂入导入」、撤销抽凭都经这里改宿主的凭证检查行：
 *
 * - 行元数据收在一个键 `_gt`：凭证键 vk、分录指纹 lfp、阶段 ph、批次 b、来源 src、配对状态 pr、
 *   展开时的对方科目 cp、存续核对 sv。宿主解析 / 保存时经 `withRowMeta` 透传，不认识也不丢。
 * - 两种回填模式：「追加」按分录指纹去重（已在表里的分录保留原行全部内容，来源记为两者）；
 *   「替换本阶段抽凭行」只删同阶段、来源只有抽凭的行，其中已填内容的行先确认。旧的「合并」按追加。
 * - 没有 `_gt` 的旧行视为来源手工、阶段未标；凭证号 + 日期 + 金额都相同即视为同一分录：不再插入，
 *   并给旧行补写 `_gt`（触碰即迁移）。
 * - 撤销按批次删行：有已填内容的先确认，取消则不撤销；后端撤销失败不删行；提示写实际删了几行。
 * - 年审阶段预审行只读：`rowClass` 给 `gt-row-locked`（点不进编辑控件），`guardPersist` 保存时用读入时的
 *   版本写回（防绕过）。
 *
 * 配对只在后端做（voucher_pairing），这里只按 `pairing` 结果生成待写入项（`prepareSamples`）。
 */
import {
  computed,
  getCurrentInstance,
  hasInjectionContext,
  inject,
  onBeforeUnmount,
  type MaybeRefOrGetter,
  type Ref,
  toValue,
  watch,
} from 'vue'
import Decimal from 'decimal.js'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useProjectAuditPhase, type AuditPhase } from '@/composables/useProjectAuditPhase'
import { WorkpaperRuntimeContextKey } from '../useWorkpaperScaffold'
import {
  notifyVoucherSurvivalRowsChanged,
  registerVoucherSurvivalHost,
  rememberVoucherSurvivalContext,
  type RegisteredSurvivalRow,
  type SurvivalCheckWire,
  type SurvivalRequestRow,
  type SurvivalResultWire,
} from './voucherSurvivalRegistry'
import { amountString, normDate, normText, sideOf, signedAmount } from '@/utils/voucherIdentity'

export const META_KEY = '_gt'
export const MULTI_ACCOUNT = '多科目'

export type RowSource = 'engine' | 'attach' | 'manual'
export type PairingStatus = 'paired' | 'multi' | 'large' | 'unknown_side'
export type FillPolicy = 'expand' | 'join'
export type VoucherFillMode = 'append' | 'replace'

export interface PairingCounterpart {
  account_code: string
  account_name: string
  amount: string
  line_fp: string | null
}

export interface SamplePairing {
  status: PairingStatus
  basis: string | null
  counterparts: PairingCounterpart[]
  counterpart_summary: Array<{ account_code: string; account_name: string; amount: string }>
  summary_omitted?: boolean
}

/** 行元数据（ADR-VK-06） */
export interface VoucherRowMeta {
  vk: string | null
  lfp: string | null
  ph: AuditPhase | null
  b: string | null
  src: RowSource[]
  pr: PairingStatus | null
  /** 同一样本按对方科目展开成多行时，本行的对方科目（区分同一指纹的几行） */
  cp?: string | null
  /** 预审样本存续核对（任务 17）：{ status, datasetId, ackBy?, ackAt? } */
  sv?: Record<string, unknown> | null
}

/**
 * 引擎样本与挂凭回拉样本的共同形状（只列回填要读的字段；宿主自有字段如摘要在映射时自行断言读取）。
 * 不带索引签名：抽凭引擎 / 挂凭回拉的样本类型是 interface，带索引签名就赋不进来。
 */
export interface FillSample {
  voucherKey?: string | null
  lineFp?: string | null
  voucherNo: string
  voucherDate: string
  debitAmount: string | number | null
  creditAmount: string | number | null
  counterpartAccount?: string | null
  counterpartAccountName?: string | null
  pairing?: SamplePairing | null
}

/** 一条待写入项：样本 + 本行的对方科目与金额 + 行元数据；宿主把它映射成自己的行 */
export interface PreparedItem<S extends FillSample = FillSample> {
  sample: S
  meta: VoucherRowMeta
  counterpartAccount: string
  counterpartAccountName: string
  /** 本行金额（两位小数字符串），落在样本自己的借贷栏上；按对方科目展开时是该对方科目对应的那部分 */
  debitAmount: string | null
  creditAmount: string | null
  /** 配不上（multi）或分录超过上限（large）：对方科目写「多科目」，可展开看整张凭证 */
  isMultiAccount: boolean
}

export interface MergeResult<R> {
  rows: R[]
  added: number
  existed: number
  replaced: number
  /** 替换会删掉、但已填了核对内容或附件的行（调用方先确认） */
  needConfirm: R[]
}

/** 预审样本存续核对结果（任务 17，design §7）：未变 / 分录已改 / 疑似重编号 / 凭证已删除 */
export type SurvivalStatus = 'unchanged' | 'modified' | 'renumbered' | 'deleted'
export const SURVIVAL_LABEL: Readonly<Record<SurvivalStatus, string>> = {
  unchanged: '未变', modified: '分录已改', renumbered: '疑似重编号', deleted: '凭证已删除',
}
export const SOURCE_LABEL: Readonly<Record<RowSource, string>> = { engine: '抽凭', attach: '挂凭', manual: '手工' }

const PHASES: ReadonlySet<string> = new Set(['preliminary', 'final'])
const SOURCES: ReadonlySet<string> = new Set(['engine', 'attach', 'manual'])
const STATUSES: ReadonlySet<string> = new Set(['paired', 'multi', 'large', 'unknown_side'])
const SURVIVAL_STATUSES: ReadonlySet<string> = new Set(['unchanged', 'modified', 'renumbered', 'deleted'])

/**
 * 预审行 → 存续核对请求。lfp 是身份真源，科目 / 借贷栏 / 金额从它解析再随请求发出；
 * 解析失败返回 null，由横幅计入「缺身份、无法自动核对」，绝不从分母静默消失。
 */
export function survivalRequestOf(row: unknown): SurvivalRequestRow | null {
  const meta = metaOf(row)
  if (meta?.ph !== 'preliminary' || !meta.lfp || !meta.vk) return null
  try {
    const parts = JSON.parse(meta.lfp)
    const vk = JSON.parse(meta.vk)
    if (!Array.isArray(parts) || parts.length !== 9 || !Array.isArray(vk) || vk.length !== 5) return null
    if (JSON.stringify(parts.slice(0, 5)) !== JSON.stringify(vk)) return null
    const side = parts[6]
    if (side !== 'D' && side !== 'C' && side !== 'X') return null
    const sv = (meta.sv ?? {}) as Record<string, unknown>
    const previousStatus = SURVIVAL_STATUSES.has(String(sv.status)) ? String(sv.status) as SurvivalStatus : null
    return {
      row_key: meta.lfp,
      lfp: meta.lfp,
      vk: meta.vk,
      account_code: String(parts[5] ?? ''),
      side,
      amount: String(parts[7] ?? ''),
      previous_dataset_id: typeof sv.datasetId === 'string' ? sv.datasetId : null,
      previous_status: previousStatus,
      acknowledged: typeof sv.ackAt === 'string' && !!sv.ackAt,
    }
  } catch {
    return null
  }
}

function survivalDetail(result: SurvivalResultWire): string {
  if (result.status === 'unchanged') return '当前账套仍存在同一分录'
  if (result.status === 'modified') {
    const count = Number(result.current_voucher?.line_count ?? 0)
    return `原凭证仍在，但分录内容已变化${count > 0 ? `（当前凭证 ${count} 条分录）` : ''}`
  }
  if (result.status === 'renumbered') {
    const labels = (result.candidates ?? []).map(c => `${c.voucher_date ?? ''} ${c.voucher_type ? `${c.voucher_type}-` : ''}${c.voucher_no ?? ''}`.trim())
    return labels.length ? `同日期、科目、借贷栏及金额的候选凭证：${labels.join('、')}` : '存在疑似改号凭证'
  }
  return '当前账套中未找到原凭证或同金额改号候选'
}

/** 行上的 `_gt`（校验过形状）；没有或不合法返回 null */
export function metaOf(row: unknown): VoucherRowMeta | null {
  const raw = (row as Record<string, unknown> | null)?.[META_KEY] as Record<string, unknown> | undefined
  if (!raw || typeof raw !== 'object') return null
  const src = Array.isArray(raw.src) ? raw.src.filter((s): s is RowSource => SOURCES.has(String(s))) : []
  return {
    vk: typeof raw.vk === 'string' ? raw.vk : null,
    lfp: typeof raw.lfp === 'string' ? raw.lfp : null,
    ph: PHASES.has(String(raw.ph)) ? (raw.ph as AuditPhase) : null,
    b: typeof raw.b === 'string' ? raw.b : null,
    src,
    pr: STATUSES.has(String(raw.pr)) ? (raw.pr as PairingStatus) : null,
    cp: typeof raw.cp === 'string' ? raw.cp : null,
    sv: raw.sv && typeof raw.sv === 'object' ? (raw.sv as Record<string, unknown>) : null,
  }
}

/** 把 source 上的 `_gt` 透传到 target（宿主解析函数与保存函数都用它），返回 target */
export function withRowMeta<T extends object>(target: T, source: unknown): T {
  const meta = metaOf(source)
  if (meta) (target as Record<string, unknown>)[META_KEY] = meta
  return target
}

function pick(row: Record<string, unknown>, ...names: string[]): unknown {
  for (const n of names) if (row[n] !== undefined && row[n] !== null && row[n] !== '') return row[n]
  return undefined
}

/** 旧行（没有指纹）的身份：凭证号 + 日期 + 金额（ADR-VK-12）；凭证号为空返回 null */
export function legacyIdentity(row: unknown): string | null {
  const r = (row ?? {}) as Record<string, unknown>
  const no = normText(pick(r, 'voucherNo', 'voucher_no', 'voucherNumber'))
  if (!no) return null
  const date = normDate(pick(r, 'voucherDate', 'voucher_date', 'date'))
  const debit = pick(r, 'debitAmount', 'debit_amount', 'debit')
  const credit = pick(r, 'creditAmount', 'credit_amount', 'credit')
  let amount: string
  try {
    amount = debit !== undefined || credit !== undefined
      ? amountString(signedAmount(debit ?? 0, credit ?? 0).abs())
      : amountString(pick(r, 'amount') ?? 0)
  } catch {
    // 手工行金额写成「1,234.00」之类解析不了：按原文认，不让一行坏数据挡住整张表的合并
    amount = `${normText(debit ?? pick(r, 'amount'))}/${normText(credit)}`
  }
  return `${no}|${date}|${amount}`
}

function dec(value: unknown): Decimal {
  try {
    return new Decimal(normText(value) || 0)
  } catch {
    return new Decimal(0)
  }
}

function groupByAccount(cps: PairingCounterpart[]): Array<PairingCounterpart & { sum: Decimal }> {
  const out = new Map<string, PairingCounterpart & { sum: Decimal }>()
  for (const c of cps) {
    const prev = out.get(c.account_code)
    if (prev) prev.sum = prev.sum.plus(dec(c.amount))
    else out.set(c.account_code, { ...c, sum: dec(c.amount) })
  }
  return [...out.values()]
}

function rawAmount(value: unknown): string | null {
  return value === null || value === undefined || value === '' ? null : String(value)
}

/** 一栏金额：空的仍为空，有值的写两位小数 */
function sideAmount(value: unknown): string | null {
  return rawAmount(value) === null ? null : amountString(value)
}

function passThrough<S extends FillSample>(
  sample: S, ctx: { phase: AuditPhase | null; source: RowSource; batchId?: string | null },
): PreparedItem<S> {
  return {
    sample,
    meta: {
      vk: sample.voucherKey ?? null, lfp: sample.lineFp ?? null, ph: ctx.phase, b: ctx.batchId ?? null,
      src: [ctx.source], pr: sample.pairing?.status ?? null, cp: null,
    },
    counterpartAccount: normText(sample.counterpartAccount),
    counterpartAccountName: normText(sample.counterpartAccountName),
    debitAmount: rawAmount(sample.debitAmount),
    creditAmount: rawAmount(sample.creditAmount),
    isMultiAccount: sample.counterpartAccount === MULTI_ACCOUNT,
  }
}

/**
 * 分借方 / 贷方两张表（区）的宿主：待写入项按分录自己的借贷栏进表（与分录指纹、配对同口径 `sideOf`）。
 * 只有贷方栏有数进贷方（红字贷方也在贷方，金额带符号照记）、只有借方栏有数进借方；借贷栏不明（两栏都有数或
 * 都为零）进借方。原来各宿主「贷方有正数才进贷方」会把贷方红字写成借方负数，经济方向相反。
 */
export function sideTableOf(item: Pick<PreparedItem, 'debitAmount' | 'creditAmount'>): 'debit' | 'credit' {
  try {
    return sideOf(item.debitAmount, item.creditAmount) === 'C' ? 'credit' : 'debit'
  } catch {
    return 'debit'
  }
}

/** 单列「对方科目」的写法：科目编码 + 名称（名称与编码相同只写一次；配不上为「多科目」） */
export function counterpartText(item: Pick<PreparedItem, 'counterpartAccount' | 'counterpartAccountName'>): string {
  return [item.counterpartAccount, item.counterpartAccountName]
    .filter((v, i, a) => !!v && (i === 0 || v !== a[0])).join(' ')
}

/** 配对结果 → 旧字段 counterpartAccount / counterpartAccountName 的取值（与后端 counterpart_label 同口径） */
export function counterpartLabelOf(pairing: SamplePairing | null | undefined): { code: string; name: string } | null {
  if (!pairing) return null
  if (pairing.status === 'paired' && pairing.counterparts.length > 0) {
    const codes = [...new Set(pairing.counterparts.map(c => c.account_code))]
    if (codes.length === 1) {
      const first = pairing.counterparts.find(c => c.account_code === codes[0])
      return { code: codes[0], name: first?.account_name ?? '' }
    }
    return { code: MULTI_ACCOUNT, name: MULTI_ACCOUNT }
  }
  if (pairing.status === 'multi' || pairing.status === 'large') return { code: MULTI_ACCOUNT, name: MULTI_ACCOUNT }
  return null
}

/**
 * 按后端配对结果生成待写入项（取代 expandMultiAccountVouchers 与宿主内联的拼接）。
 *
 * - `expand`（凭证检查表）：配上的样本按对方科目一行一个，金额 = 该对方科目对应的部分（同科目合并）；
 * - `join`（资产类明细表）：一个样本一行，对方科目用「/」拼接，金额 = 样本金额；
 * - 配不上（multi）/ 超过上限（large）：一行，对方科目「多科目」；借贷栏不明：一行，对方科目沿用源数据；
 * - 没有配对结果的旧样本：沿用样本自带的对方科目（「多科目」照旧标多科目）。
 * 金额一律落在样本自己的借贷栏上，两位小数字符串（不换成浮点数）。
 */
export function prepareSamples<S extends FillSample>(
  samples: S[],
  policy: FillPolicy,
  ctx: { phase: AuditPhase | null; source: RowSource; batchId?: string | null },
): PreparedItem<S>[] {
  const out: PreparedItem<S>[] = []
  for (const sample of samples) {
    let side: ReturnType<typeof sideOf>
    let own: Decimal
    try {
      side = sideOf(sample.debitAmount, sample.creditAmount)
      own = signedAmount(sample.debitAmount, sample.creditAmount, side)
    } catch {
      // 金额解析不了（宿主自填的格式）：原样透传，不猜金额
      out.push(passThrough(sample, ctx))
      continue
    }
    const pairing = sample.pairing ?? null
    const base: VoucherRowMeta = {
      vk: sample.voucherKey ?? null,
      lfp: sample.lineFp ?? null,
      ph: ctx.phase,
      b: ctx.batchId ?? null,
      src: [ctx.source],
      pr: pairing?.status ?? null,
      cp: null,
    }
    const item = (account: string, name: string, amount: Decimal, multi: boolean, cp: string | null): PreparedItem<S> => ({
      sample,
      meta: { ...base, cp },
      counterpartAccount: account,
      counterpartAccountName: name,
      // 借贷栏不明（借贷双填 / 都为零）：两栏照源数据写（空的仍为空），不挑一栏
      debitAmount: side === 'X' ? sideAmount(sample.debitAmount) : side === 'C' ? null : amountString(amount),
      creditAmount: side === 'X' ? sideAmount(sample.creditAmount) : side === 'C' ? amountString(amount) : null,
      isMultiAccount: multi,
    })
    if (pairing?.status === 'paired' && pairing.counterparts.length > 0) {
      const groups = groupByAccount(pairing.counterparts)
      if (policy === 'expand' && groups.length > 1) {
        for (const g of groups) out.push(item(g.account_code, g.account_name, g.sum, false, g.account_code))
      } else {
        out.push(item(groups.map(g => g.account_code).join('/'), groups.map(g => g.account_name).join('/'), own, false,
          groups.length === 1 ? groups[0].account_code : null))
      }
    } else if (pairing?.status === 'multi' || pairing?.status === 'large'
      || (!pairing && sample.counterpartAccount === MULTI_ACCOUNT)) {
      out.push(item(MULTI_ACCOUNT, MULTI_ACCOUNT, own, true, null))
    } else {
      out.push(item(normText(sample.counterpartAccount), normText(sample.counterpartAccountName), own, false, null))
    }
  }
  return out
}

/** 宿主传入了已废弃的 `phase` prop 时提示一次（阶段改取项目当前审计阶段，需求 6.2） */
let deprecatedPhaseWarned = false
export function warnDeprecatedEnginePhase(value: unknown): void {
  if (deprecatedPhaseWarned || value === undefined || !import.meta.env?.DEV) return
  deprecatedPhaseWarned = true
  console.warn(`[GtVoucherSamplingEngine] phase prop 已废弃，已忽略宿主传入的「${String(value)}」：阶段取项目当前审计阶段`)
}

/** 样本 / 行的分录指纹：底稿行在 `_gt.lfp`，引擎与截止抽样的样本在 `lineFp` */
function fingerprintOf(row: unknown): string | null {
  const lfp = metaOf(row)?.lfp
  if (lfp) return lfp
  const fp = (row as Record<string, unknown> | null)?.lineFp
  return typeof fp === 'string' && fp ? fp : null
}

/**
 * incoming 里不在 existing 中的条目（截止抽样等不写 `_gt` 的样本列表用；底稿行合并用 mergeVoucherCheckRows）。
 * 同一分录的认法与 mergeVoucherCheckRows 相同：有指纹按指纹；指纹没对上但旧条目没有指纹、凭证号 + 日期 + 金额相同，
 * 也算同一分录；incoming 自己没有指纹时，凭证号 + 日期 + 金额与任一已有条目相同即算已有（宁可少插一行不重复）。
 */
export function newEntriesOnly<T>(existing: T[], incoming: T[], legacy: (row: T) => string | null = legacyIdentity): T[] {
  const fps = new Set<string>()
  const legacyNoFp = new Set<string>()
  const legacyAll = new Set<string>()
  const remember = (r: T) => {
    const fp = fingerprintOf(r)
    const key = legacy(r)
    if (fp) fps.add(fp)
    if (key) {
      legacyAll.add(key)
      if (!fp) legacyNoFp.add(key)
    }
  }
  existing.forEach(remember)
  const out: T[] = []
  for (const r of incoming) {
    const fp = fingerprintOf(r)
    const key = legacy(r)
    const dup = fp
      ? fps.has(fp) || (!!key && legacyNoFp.has(key))
      : !!key && legacyAll.has(key)
    if (dup) continue
    out.push(r)
    remember(r)
  }
  return out
}

function withSource<R>(row: R, source: RowSource): R {
  const meta = metaOf(row)
  if (!meta || meta.src.includes(source)) return row
  return { ...row, [META_KEY]: { ...meta, src: [...meta.src, source] } }
}

function pushIndex(map: Map<string, number[]>, key: string | null | undefined, i: number): void {
  if (key) map.set(key, [...(map.get(key) ?? []), i])
}

/**
 * 合并一张表的已有行与待写入行（宿主已映射、带 `_gt`）。纯函数，不改入参。
 *
 * - `append`：已有同指纹的行 → 不插入（已存在），已有行来源并入本次来源；没有指纹的旧行按
 *   凭证号 + 日期 + 金额认同一分录 → 不插入，并给旧行补写 `_gt`（阶段未标，来源 = 手工 + 本次）；
 *   待写入行自己没有指纹（预览里手工增补的）时，凭证号 + 日期 + 金额与任一已有行相同即算已有；
 * - `replace`：先删同阶段且来源只有抽凭的行（`needConfirm` 列出其中已填内容的），再按 append 并入。
 */
export function mergeVoucherCheckRows<R>(
  existing: R[],
  incoming: R[],
  opts: {
    mode: VoucherFillMode
    phase: AuditPhase | null
    source: RowSource
    hasUserContent?: (row: R) => boolean
    legacy?: (row: R) => string | null
  },
): MergeResult<R> {
  const legacy = (opts.legacy ?? legacyIdentity) as (r: unknown) => string | null
  const removable = opts.mode === 'replace'
    ? existing.filter((r) => {
      const m = metaOf(r)
      return !!m && m.ph === opts.phase && m.src.length > 0 && m.src.every(s => s === 'engine')
    })
    : []
  const removed = new Set(removable)
  const rows = existing.filter(r => !removed.has(r))
  const byLfp = new Map<string, number[]>()
  const byLegacyNoLfp = new Map<string, number[]>()
  const byLegacyAll = new Map<string, number[]>()
  rows.forEach((r, i) => {
    const lfp = metaOf(r)?.lfp
    const key = legacy(r)
    pushIndex(byLfp, lfp, i)
    pushIndex(byLegacyAll, key, i)
    if (!lfp) pushIndex(byLegacyNoLfp, key, i)
  })
  let added = 0
  let existed = 0
  const fresh: R[] = []
  const freshKeys = new Set<string>()
  for (const row of incoming) {
    const meta = metaOf(row)
    // 同一次写入里重复的分录（同一分录挂了两次、引擎样本重复）只进一行
    const ownKey = rowKey(row, legacy)
    if (ownKey && freshKeys.has(ownKey)) {
      existed += 1
      continue
    }
    const legacyKey = legacy(row)
    const hits = meta?.lfp ? byLfp.get(meta.lfp) : undefined
    const legacyHits = legacyKey ? byLegacyNoLfp.get(legacyKey) : undefined
    const looseHits = !meta?.lfp && legacyKey ? byLegacyAll.get(legacyKey) : undefined
    if (hits?.length || (!legacyHits?.length && looseHits?.length)) {
      existed += 1
      for (const i of (hits?.length ? hits : looseHits) as number[]) rows[i] = withSource(rows[i], opts.source)
      continue
    }
    if (legacyHits?.length && meta) {
      existed += 1
      for (const i of legacyHits) {
        const old = metaOf(rows[i])
        const src = [...new Set<RowSource>([...(old?.src.length ? old.src : ['manual' as RowSource]), opts.source])]
        rows[i] = { ...rows[i], [META_KEY]: { ...meta, ph: old?.ph ?? null, b: old?.b ?? null, src } }
      }
      continue
    }
    fresh.push(row)
    if (ownKey) freshKeys.add(ownKey)
    added += 1
  }
  return {
    rows: [...rows, ...fresh],
    added,
    existed,
    replaced: removable.length,
    needConfirm: opts.hasUserContent ? removable.filter(opts.hasUserContent) : [],
  }
}

/** 引擎回填载荷（GtVoucherSamplingEngine 的 `filled`） */
export interface EngineFilledPayload<S extends FillSample = FillSample> {
  samples: S[]
  /** 引擎按项目阶段抽凭并写进日志的阶段；行按它标阶段（与日志一致） */
  phase?: string | null
  fillMode?: string
  batchId?: string | null
  methodology?: { batchId?: string | null } | null
}
/** 引擎撤销请求（GtVoucherSamplingEngine 的 `undo-request`）：宿主确认后调 performUndo 才真正撤销 */
export interface UndoRequestPayload {
  logId: string
  batchId: string | null
  /** 调后端撤销；失败时由它提示原因并返回 false（宿主不再重复提示） */
  performUndo: () => Promise<boolean>
}
export interface FillOutcome {
  cancelled: boolean
  added: number
  existed: number
  replaced: number
}
export interface VoucherCheckFillOptions<R extends object> {
  projectId: MaybeRefOrGetter<string | null | undefined>
  /** 一张表，或按名分区的多张表（D2 本期 / 期后等） */
  tables: Ref<R[]> | Record<string, Ref<R[]>>
  /**
   * 多张表时每条待写入项进哪张表；返回空则进本次范围（scope.tables）的第一张表
   * （D3 这类由用户在抽凭弹窗里选目标区块的宿主：已在某张表的分录仍进那张表，其余进所选区块）
   */
  tableOf?: (item: PreparedItem) => string | null | undefined
  mapSampleToRow: (item: PreparedItem, tableKey: string) => R
  persist: () => unknown
  /** 行上是否已填核对结果 / 附件等（替换与撤销时决定要不要确认） */
  hasUserContent?: (row: R) => boolean
  policy?: FillPolicy
  /** 改完一张表之后（如重排序号） */
  afterChange?: (tableKey: string, rows: R[]) => void
  legacy?: (row: R) => string | null
  readonly?: MaybeRefOrGetter<boolean>
}
/** 一次回填的范围：多张表的宿主按「本期 / 期后」等分别抽凭时，替换只动本次的目标表 */
export interface FillScope {
  tables?: string[]
}
const SINGLE = 'default'
function rowKey(row: unknown, legacy: (r: unknown) => string | null): string | null {
  const meta = metaOf(row)
  return meta?.lfp ? `${meta.lfp}#${meta.cp ?? ''}` : legacy(row)
}
/** 合并多个 el-table 行样式函数（宿主已有 row-class-name 时与 `rowClass` 合用） */
export function combineRowClass<A>(...fns: Array<((arg: A) => string | undefined | null) | undefined>) {
  return (arg: A): string => fns.map(fn => fn?.(arg) || '').filter(Boolean).join(' ')
}
function validPhase(value: unknown): AuditPhase | null {
  return value === 'preliminary' || value === 'final' ? value : null
}
export function useVoucherCheckFill<R extends object>(opts: VoucherCheckFillOptions<R>) {
  // 阶段按需读（markLoaded / 回填 / 撤销 / ready 时）：组合式函数单测不因构造就发请求
  const auditPhase = useProjectAuditPhase(opts.projectId)
  const phase = computed<AuditPhase>(() => auditPhase.phase.value)
  const legacy = (opts.legacy ?? legacyIdentity) as (r: unknown) => string | null
  const tableMap = (): Record<string, Ref<R[]>> =>
    ('value' in (opts.tables as object) ? { [SINGLE]: opts.tables as Ref<R[]> } : opts.tables as Record<string, Ref<R[]>>)

  // 父级 GtWpRenderer 的横幅与本子组件通过 workpaperId 注册表通信；组合式函数在无组件上下文的单测里不注册。
  const runtime = hasInjectionContext() ? inject(WorkpaperRuntimeContextKey, null) : null
  let unregisterSurvival: () => void = () => undefined

  function collectSurvivalRows(): RegisteredSurvivalRow[] {
    const out: RegisteredSurvivalRow[] = []
    for (const table of Object.values(tableMap())) {
      for (const row of table.value) {
        const meta = metaOf(row)
        if (meta?.ph !== 'preliminary') continue
        const request = survivalRequestOf(row)
        out.push({ request, unsupported: request === null })
      }
    }
    return out
  }

  function applySurvival(result: SurvivalCheckWire): boolean {
    const byFp = new Map(result.results.map(row => [row.lfp, row]))
    let anyChanged = false
    for (const [tableKey, table] of Object.entries(tableMap())) {
      let tableChanged = false
      const next = table.value.map((row) => {
        const meta = metaOf(row)
        const found = meta?.ph === 'preliminary' && meta.lfp ? byFp.get(meta.lfp) : undefined
        if (!meta || !found) return row
        const old = (meta.sv ?? {}) as Record<string, unknown>
        const preserveAck = found.acknowledged
          && old.datasetId === result.dataset_id && old.status === found.status && typeof old.ackAt === 'string'
        const sv: Record<string, unknown> = {
          status: found.status,
          datasetId: result.dataset_id,
          checkId: result.check_id,
          checkedAt: result.checked_at,
          detail: survivalDetail(found),
          candidateVoucherKeys: (found.candidates ?? []).map(c => c.voucher_key).filter(Boolean),
          ...(preserveAck ? { ackBy: old.ackBy, ackAt: old.ackAt } : {}),
        }
        rememberVoucherSurvivalContext(runtime?.wpId.value ?? '', found.lfp, result.check_id, result.dataset_id)
        if (JSON.stringify(old) === JSON.stringify(sv)) return row
        tableChanged = anyChanged = true
        return { ...row, [META_KEY]: { ...meta, sv } }
      })
      if (tableChanged) {
        table.value = next
        opts.afterChange?.(tableKey, next)
      }
    }
    return anyChanged
  }

  function acknowledgeSurvival(lfp: string, ackBy: string, ackAt: string): boolean {
    let anyChanged = false
    for (const [tableKey, table] of Object.entries(tableMap())) {
      let tableChanged = false
      const next = table.value.map((row) => {
        const meta = metaOf(row)
        const sv = meta?.sv as Record<string, unknown> | null | undefined
        if (!meta || meta.lfp !== lfp || !sv || sv.status === 'unchanged' || sv.ackAt) return row
        tableChanged = anyChanged = true
        return { ...row, [META_KEY]: { ...meta, sv: { ...sv, ackBy, ackAt } } }
      })
      if (tableChanged) {
        table.value = next
        opts.afterChange?.(tableKey, next)
      }
    }
    return anyChanged
  }

  if (runtime && getCurrentInstance()) {
    watch(runtime.wpId, (wpId) => {
      unregisterSurvival()
      unregisterSurvival = registerVoucherSurvivalHost(wpId, {
        collect: collectSurvivalRows,
        apply: applySurvival,
        acknowledge: acknowledgeSurvival,
        persist: opts.persist,
      })
    }, { immediate: true })
    onBeforeUnmount(() => unregisterSurvival())
  }
  /**
   * 每张表的预审行读入版本：主键 → 行；有指纹的行按「指纹 + 对方科目」索引，没有指纹的按旧行键索引
   * （旧行键只用来认读入时没有指纹、之后被触碰迁移补了指纹的行；有指纹的行同号同日同金额也是别的分录）
   */
  const locked = new Map<string, { rows: Map<string, R>; byFp: Map<string, string>; byLegacy: Map<string, string> }>()
  function isRowLocked(row: R): boolean {
    return phase.value === 'final' && metaOf(row)?.ph === 'preliminary'
  }
  function rowClass({ row }: { row: R }): string {
    return isRowLocked(row) ? 'gt-row-locked' : ''
  }
  function fpKey(row: unknown): string | null {
    const meta = metaOf(row)
    return meta?.lfp ? `${meta.lfp}#${meta.cp ?? ''}` : null
  }
  function snapshot(tableKey: string, rows: R[]): void {
    const snap = { rows: new Map<string, R>(), byFp: new Map<string, string>(), byLegacy: new Map<string, string>() }
    for (const row of rows) {
      if (metaOf(row)?.ph !== 'preliminary') continue
      const fp = fpKey(row)
      const key = fp ?? legacy(row)
      if (!key || snap.rows.has(key)) continue
      snap.rows.set(key, JSON.parse(JSON.stringify(row)) as R)
      if (fp) snap.byFp.set(fp, key)
      else snap.byLegacy.set(key, key)
    }
    locked.set(tableKey, snap)
  }
  /** 当前行对应读入时的哪一行预审行（主键）；对不上返回 null */
  function lockedKeyOf(snap: { byFp: Map<string, string>; byLegacy: Map<string, string> }, row: R): string | null {
    const fp = fpKey(row)
    const hit = fp ? snap.byFp.get(fp) : undefined
    if (hit) return hit
    const key = legacy(row)
    return key ? snap.byLegacy.get(key) ?? null : null
  }
  /**
   * 宿主读入数据之后调：记下预审行的读入版本，年审阶段保存时据此写回。
   * 项目阶段不在这里读：宿主组件挂载时调 `ready()`（组合式函数单测只构造、不挂载，不发请求）。
   */
  function markLoaded(): void {
    locked.clear()
    for (const [key, table] of Object.entries(tableMap())) snapshot(key, table.value)
    notifyVoucherSurvivalRowsChanged()
  }
  /**
   * 保存前过一遍（需求 6.3「年审阶段预审行不可改、不可删」的兜底）：
   * 年审阶段预审行一律用读入时的版本（被改的改回、被删的补回），行元数据取当前的（来源、存续核对由系统写）；
   * 预审阶段原样返回，并把这次保存的预审行记为新的读入版本（阶段中途切到年审时以最后保存的为准）。
   */
  function guardPersist(rows: R[], tableKey: string = SINGLE): R[] {
    if (phase.value !== 'final') {
      snapshot(tableKey, rows)
      return rows
    }
    const snap = locked.get(tableKey)
    if (!snap?.rows.size) return rows
    const seen = new Set<string>()
    const out = rows.map((row) => {
      const primary = lockedKeyOf(snap, row)
      if (!primary || seen.has(primary)) return row
      seen.add(primary)
      const meta = (row as Record<string, unknown>)[META_KEY]
      const restored = JSON.parse(JSON.stringify(snap.rows.get(primary))) as R
      return meta ? { ...restored, [META_KEY]: meta } : restored
    })
    for (const [k, row] of snap.rows) if (!seen.has(k)) out.push(JSON.parse(JSON.stringify(row)) as R)
    return out
  }
  async function applyItems(
    items: PreparedItem[], mode: VoucherFillMode, source: RowSource, rowPhase: AuditPhase, scope?: FillScope,
  ): Promise<FillOutcome> {
    const outcome: FillOutcome = { cancelled: false, added: 0, existed: 0, replaced: 0 }
    if (toValue(opts.readonly)) return { ...outcome, cancelled: true }
    const tables = tableMap()
    const byTable = new Map<string, R[]>()
    for (const item of items) {
      const key = opts.tableOf?.(item) ?? scope?.tables?.[0] ?? Object.keys(tables)[0]
      const row = opts.mapSampleToRow(item, key)
      ;(row as Record<string, unknown>)[META_KEY] = { ...item.meta }
      byTable.set(key, [...(byTable.get(key) ?? []), row])
    }
    // 替换只动本次范围内的表；范围外的表（tableOf 把已在那张表的分录路由过去）按追加并入
    const replaceKeys = new Set(mode === 'replace' ? (scope?.tables ?? Object.keys(tables)) : [])
    const keys = [...new Set([...replaceKeys, ...byTable.keys()])]
    const merged = keys.map(key => [key, mergeVoucherCheckRows(tables[key]?.value ?? [], byTable.get(key) ?? [], {
      mode: replaceKeys.has(key) ? 'replace' : 'append', phase: rowPhase, source, hasUserContent: opts.hasUserContent, legacy,
    })] as const)
    if (!merged.length) return outcome
    const needConfirm = merged.reduce((n, [, m]) => n + m.needConfirm.length, 0)
    const replaced = merged.reduce((n, [, m]) => n + m.replaced, 0)
    if (needConfirm > 0) {
      try {
        await ElMessageBox.confirm(
          `「替换本阶段抽凭行」会删除 ${replaced} 行，其中 ${needConfirm} 行已填核对内容或附件，确定替换吗？`,
          '替换确认', { type: 'warning', confirmButtonText: '确定替换', cancelButtonText: '取消' },
        )
      } catch {
        ElMessage.info('已取消替换，底稿未改动')
        return { ...outcome, cancelled: true }
      }
    }
    for (const [key, m] of merged) {
      if (!tables[key]) continue
      tables[key].value = m.rows
      opts.afterChange?.(key, m.rows)
      outcome.added += m.added
      outcome.existed += m.existed
      outcome.replaced += m.replaced
    }
    await opts.persist()
    notifyVoucherSurvivalRowsChanged()
    return outcome
  }
  /** 抽凭引擎回填；`scope.tables` 限定替换只动哪几张表（缺省全部） */
  async function onEngineFilled(payload: EngineFilledPayload, scope?: FillScope): Promise<FillOutcome> {
    await auditPhase.load()
    const mode: VoucherFillMode = payload.fillMode === 'replace' ? 'replace' : 'append'
    const batchId = payload.batchId ?? payload.methodology?.batchId ?? null
    const rowPhase = validPhase(payload.phase) ?? phase.value
    const items = prepareSamples(payload.samples ?? [], opts.policy ?? 'expand', {
      phase: rowPhase, source: 'engine', batchId,
    })
    const out = await applyItems(items, mode, 'engine', rowPhase, scope)
    // 底稿实际填入几行只有这里知道（引擎只报「已确认 N 笔样本」）：多科目展开、去重、替换都会让行数与样本数不同
    if (!out.cancelled) {
      const parts = [`填入 ${out.added} 行`]
      if (out.existed) parts.push(`已存在 ${out.existed} 行未重复填入`)
      if (out.replaced) parts.push(`替换本阶段抽凭行 ${out.replaced} 行`)
      if (out.existed > 0 || out.replaced > 0) ElMessage.info(parts.join('，'))
      else ElMessage.success(parts[0])
    }
    return out
  }
  /** 「从序时账挂入导入」：幂等追加，提示已存在几行 */
  async function onAttachImported(samples: FillSample[], scope?: FillScope): Promise<FillOutcome> {
    await auditPhase.load()
    const items = prepareSamples(samples, opts.policy ?? 'expand', { phase: phase.value, source: 'attach' })
    const out = await applyItems(items, 'append', 'attach', phase.value, scope)
    if (!out.cancelled) {
      ElMessage.success(out.existed ? `导入 ${out.added} 行，已存在 ${out.existed} 行` : `导入 ${out.added} 行`)
    }
    return out
  }
  /** 撤销抽凭批次：删本批次填入的行（同时来自挂凭的保留），有已填内容先确认；后端撤销失败不删 */
  async function onUndoRequest(payload: UndoRequestPayload): Promise<boolean> {
    await auditPhase.load()
    const tables = tableMap()
    const batch = payload.batchId
    const inBatch = (r: R) => !!batch && metaOf(r)?.b === batch
    const all = Object.values(tables).flatMap(t => t.value.filter(inBatch))
    if (all.some(isRowLocked)) {
      ElMessage.warning('该批次是预审抽凭，年审阶段预审行只读，不能撤销；确需撤销请先由项目经理把审计阶段改回预审')
      return false
    }
    const kept = all.filter(r => (metaOf(r)?.src ?? []).some(s => s !== 'engine'))
    const toDelete = all.filter(r => !kept.includes(r))
    const withContent = opts.hasUserContent ? toDelete.filter(opts.hasUserContent).length : 0
    if (toDelete.length > 0) {
      try {
        await ElMessageBox.confirm(
          `撤销将删除本批次填入的 ${toDelete.length} 行${withContent ? `，其中 ${withContent} 行已填核对内容或附件` : ''}，确定撤销吗？`,
          '撤销抽凭', { type: 'warning', confirmButtonText: '确定撤销', cancelButtonText: '取消' },
        )
      } catch {
        return false
      }
    }
    if (!(await payload.performUndo())) return false
    const dropped = new Set(toDelete)
    for (const [key, table] of Object.entries(tables)) {
      if (!table.value.some(r => dropped.has(r) || kept.includes(r))) continue
      const next = table.value
        .filter(r => !dropped.has(r))
        .map((r) => {
          if (!kept.includes(r)) return r
          const m = metaOf(r) as VoucherRowMeta
          return { ...r, [META_KEY]: { ...m, b: null, src: m.src.filter(s => s !== 'engine') } }
        })
      table.value = next
      opts.afterChange?.(key, next)
    }
    await opts.persist()
    notifyVoucherSurvivalRowsChanged()
    ElMessage.success(toDelete.length || kept.length
      ? `已撤销本批次，删除 ${toDelete.length} 行${kept.length ? `；${kept.length} 行同时来自挂凭或手工录入，已保留` : ''}`
      : '已撤销本批次（底稿里没有本批次填入的行）')
    return true
  }
  async function ready(): Promise<unknown> {
    const result = await auditPhase.load()
    notifyVoucherSurvivalRowsChanged()
    return result
  }
  return {
    phase,
    phaseText: auditPhase.text,
    /** 等项目阶段读入（宿主要按阶段判只读时先 await）；同时通知底稿级存续横幅重扫行 */
    ready,
    isRowLocked,
    rowClass,
    markLoaded,
    guardPersist,
    onEngineFilled,
    onAttachImported,
    onUndoRequest,
  }
}
