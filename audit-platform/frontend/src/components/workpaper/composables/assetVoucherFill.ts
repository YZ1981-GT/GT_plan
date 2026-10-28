/**
 * H / I 循环宿主接入共享回填函数的映射小工具（spec voucher-identity-writeback-and-audit-phase 任务 12）
 *
 * 资产类明细表一行一个样本（对方科目按后端配对用「/」拼接，共享回填函数 `policy: 'join'`），金额只有一列（原值 / 账面金额）：
 * 取样本自己那一栏的金额，红字带符号照记 —— 原实现各宿主取绝对值，冲销的增加 / 减少被记成正常发生额。
 * 旧行（没有 `_gt`）原实现回填时取了绝对值，旧行身份按金额绝对值认。
 * 针对性检查表（I2-12 / I3-5 / I4-5 / I5-4 / I6-4）是凭证检查表（借贷两栏 + 对方科目 / 对方明细，`policy: 'expand'`），
 * 映射仍用各自原有的 `mapSampledToI*TargetedRow`，样本换成待写入项（`preparedAsSample`）。
 */
import type { Ref } from 'vue'
import { ElMessage } from 'element-plus'
import type { AuditPhase } from '@/composables/useProjectAuditPhase'
import {
  legacyIdentity, META_KEY, metaOf, newEntriesOnly, prepareSamples, withRowMeta,
  type EngineFilledPayload, type FillOutcome, type FillScope, type PreparedItem,
} from './shared/voucherCheckFill'

/** 抽凭 / 挂凭样本上资产类明细表要读的字段（引擎样本类型的子集） */
export interface AssetSampleFields {
  summary?: string | null
  abnormal?: boolean | null
  selectionReason?: string | null
  remark?: string | null
  isHighValue?: boolean | null
}

export type AssetSample = PreparedItem['sample'] & AssetSampleFields

export function sampleOf(item: PreparedItem): AssetSample {
  return item.sample as AssetSample
}

function num(value: string | null | undefined): number | null {
  if (value === null || value === undefined || value === '') return null
  const n = Number(value)
  return Number.isFinite(n) ? n : null
}

/**
 * 单列金额：样本自己那一栏的金额（带符号）。共享回填函数只在样本那一栏给金额；借贷栏不明（两栏都有数）时
 * 先取 `prefer` 那一栏（增加类表借方、减少类表贷方）
 */
export function assetAmount(item: Pick<PreparedItem, 'debitAmount' | 'creditAmount'>, prefer: 'debit' | 'credit'): number {
  const [first, second] = prefer === 'debit' ? [item.debitAmount, item.creditAmount] : [item.creditAmount, item.debitAmount]
  return num(first) ?? num(second) ?? 0
}

/** 选样说明：引擎给的选样原因、样本备注，高值必选样本标注 */
export function sampleRemark(item: PreparedItem, highValueText = 'MUS高值必选'): string {
  const s = sampleOf(item)
  return String(s.selectionReason || s.remark || (s.isHighValue ? highValueText : ''))
}

/** 旧行（没有 `_gt`）的身份：凭证号 + 日期 + 金额绝对值 */
export function assetLegacyKey(voucherNo: unknown, date: unknown, amount: unknown): string | null {
  const n = Number(amount)
  return legacyIdentity({ voucherNo, voucherDate: date, amount: Number.isFinite(n) ? Math.abs(n) : amount })
}

/**
 * 整表替换导入（Excel 导入）时把已有行的 `_gt` 带给导入的同一行：按旧行身份（同号同日同金额）认，只对上一行才带。
 * 否则年审阶段导入自己导出的表，预审行的导入副本没有 `_gt`，保存时预审行又按读入版本补回 ⇒ 同一笔分录两行；
 * 本阶段抽凭行也丢了指纹，之后只能按凭证号 + 日期 + 金额认。
 */
export function carryRowMeta<R extends object>(next: R[], prev: R[], legacy: (row: R) => string | null): R[] {
  const byKey = new Map<string, R[]>()
  for (const row of prev) {
    const key = metaOf(row) ? legacy(row) : null
    if (key) byKey.set(key, [...(byKey.get(key) ?? []), row])
  }
  const used = new Set<R>()
  return next.map((row) => {
    if (metaOf(row)) return row
    const key = legacy(row)
    const hits = key ? byKey.get(key) : undefined
    if (hits?.length !== 1 || used.has(hits[0])) return row
    used.add(hits[0])
    return withRowMeta({ ...row }, hits[0])
  })
}

/** 年审阶段预审行只读：批量带入 / 挂接之后把预审行换回原样（按行主键） */
export function keepLockedRows<R>(next: R[], prev: R[], isLocked: (row: R) => boolean, idOf: (row: R) => string): R[] {
  const locked = new Map(prev.filter(isLocked).map(r => [idOf(r), r]))
  return locked.size ? next.map(r => locked.get(idOf(r)) ?? r) : next
}

/** 针对性检查表各自映射函数（`mapSampledToI*TargetedRow`）认的样本形状 */
export interface TargetedSample {
  voucherNo: string
  voucherDate: string
  summary: string
  debitAmount: string | null
  creditAmount: string | null
  counterpartAccount: string
  counterpartAccountName: string
  accountName: string
  isHighValue: boolean
  selectionReason: string
  abnormal: boolean
  remark: string
}

/**
 * 待写入项 → 针对性检查表映射函数认的样本：对方科目与金额换成本行的（一行一个对方科目时金额是该对方科目那部分，
 * 落在样本自己的借贷栏、红字带符号；配不上写「多科目」，名称与编码相同时名称留空，「对方明细科目」不重复写「多科目」）。
 * 原实现把整笔样本原样交给映射函数，多科目凭证只有一行、对方科目取样本上推断的那一个
 */
export function preparedAsSample(item: PreparedItem): TargetedSample {
  const s = sampleOf(item) as AssetSample & { accountName?: string | null }
  return {
    voucherNo: String(s.voucherNo ?? ''),
    voucherDate: String(s.voucherDate ?? ''),
    summary: String(s.summary ?? ''),
    debitAmount: item.debitAmount,
    creditAmount: item.creditAmount,
    counterpartAccount: item.counterpartAccount,
    counterpartAccountName: item.counterpartAccountName !== item.counterpartAccount ? item.counterpartAccountName : '',
    accountName: String(s.accountName ?? ''),
    isHighValue: s.isHighValue === true,
    selectionReason: String(s.selectionReason ?? ''),
    abnormal: s.abnormal === true,
    remark: String(s.remark ?? ''),
  }
}

/** 针对性检查表行上用户填的核对内容 */
export interface TargetedCheckContent {
  supportingDocs: string
  check1: string
  check2: string
  check3: string
  check4: string
  check5: string
  indexRef: string
}

/** 行上已填核对内容（替换与撤销抽凭时据此先确认）：支持性文件、核对 1~5、索引号 */
export function hasTargetedCheckContent(r: TargetedCheckContent): boolean {
  return [r.supportingDocs, r.check1, r.check2, r.check3, r.check4, r.check5, r.indexRef]
    .some(v => String(v ?? '').trim() !== '')
}

/** 引擎回填载荷里的抽样方法学（针对性检查表记进抽样说明） */
export interface EngineSamplingNote {
  samplingMethod?: unknown
  sampleSize?: unknown
}

/**
 * 抽凭回填后记进抽样说明（I2-12 / I3-5 / I4-5 / I5-4 原宿主的写法）：抽样方法、样本量取引擎方法学，
 * 抽样过程追加「抽凭引擎回填 N 行（日期）」；N 是底稿实际填入的行数（原实现报的是样本笔数，去重前）
 */
export function noteEngineSampling(
  meta: { sampleMethod: string; sampleSize: number; sampleProcess: string },
  methodology: EngineSamplingNote | null | undefined,
  added: number,
): void {
  if (methodology?.samplingMethod) meta.sampleMethod = String(methodology.samplingMethod)
  if (methodology?.sampleSize) meta.sampleSize = Number(methodology.sampleSize) || meta.sampleSize
  meta.sampleProcess = [meta.sampleProcess, `抽凭引擎回填 ${added} 行（${new Date().toISOString().slice(0, 10)}）`]
    .filter(Boolean).join('；')
}

/** 逐行抽凭要用到的共享回填函数部分（`useVoucherCheckFill` 的返回值满足它） */
export interface RowFillHandle {
  phase: { readonly value: AuditPhase }
  ready: () => Promise<unknown>
  onEngineFilled: (payload: EngineFilledPayload, scope?: FillScope) => Promise<FillOutcome>
}

/**
 * 逐行抽凭（H4-4 / H4-5 的「抽凭」列）：第一笔样本写进所选行，行带上 `_gt`（来源记手工 + 抽凭：撤销该批次时
 * 保留这一行，只去掉抽凭来源），其余样本按引擎所选的方式并入（与整表抽凭同一去重）。
 * - 所选行已关联凭证（有 `_gt`，含年审阶段的预审行）：不改它，本次样本按整表抽凭填入；
 * - 第一笔的分录已在本表别的行：不写所选行（不重复），提示在哪；
 * - 原实现只取第一笔、其余样本静默丢掉（抽凭登记里却记着本底稿抽了这些凭证），也不去重。
 */
export async function fillIntoSelectedRow<R extends object>(opts: {
  fill: RowFillHandle
  rows: Ref<R[]>
  rowId: string
  idOf: (row: R) => string
  payload: EngineFilledPayload
  /** 把待写入项写进所选行（宿主自己的字段映射；已填的名称等按宿主规则保留） */
  apply: (row: R, item: PreparedItem) => void
  persist: () => unknown
  legacy?: (row: R) => string | null
  readonly?: () => boolean
}): Promise<FillOutcome> {
  const none: FillOutcome = { cancelled: false, added: 0, existed: 0, replaced: 0 }
  if (opts.readonly?.()) return { ...none, cancelled: true }
  const samples = opts.payload.samples ?? []
  if (!samples.length) return none
  const target = opts.rows.value.find(r => opts.idOf(r) === opts.rowId)
  if (!target || metaOf(target)) {
    if (target) ElMessage.warning('所选行已关联凭证，本次样本按整表抽凭填入新行')
    return opts.fill.onEngineFilled(opts.payload)
  }
  await opts.fill.ready()
  const ph = opts.payload.phase
  const phase: AuditPhase = ph === 'preliminary' || ph === 'final' ? ph : opts.fill.phase.value
  const batchId = opts.payload.batchId ?? opts.payload.methodology?.batchId ?? null
  const [first] = prepareSamples(samples.slice(0, 1), 'join', { phase, source: 'engine', batchId })
  const candidate = { ...target } as R
  opts.apply(candidate, first)
  ;(candidate as Record<string, unknown>)[META_KEY] = { ...first.meta, src: ['manual', 'engine'] }
  const others = opts.rows.value.filter(r => r !== target)
  const no = String(first.sample.voucherNo ?? '')
  let added = 0
  let existed = 0
  if (newEntriesOnly(others, [candidate], opts.legacy).length) {
    opts.rows.value = opts.rows.value.map(r => (r === target ? candidate : r))
    await opts.persist()
    added = 1
    ElMessage.success(`已填入所选行（凭证 ${no}）`)
  } else {
    existed = 1
    ElMessage.info(`凭证 ${no} 这笔分录已在本表，未写入所选行`)
  }
  const rest = samples.slice(1)
  if (!rest.length) return { ...none, added, existed }
  const out = await opts.fill.onEngineFilled({ ...opts.payload, samples: rest })
  return { ...out, added: out.added + added, existed: out.existed + existed }
}
