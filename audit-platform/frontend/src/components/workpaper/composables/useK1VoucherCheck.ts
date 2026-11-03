/**
 * useK1VoucherCheck.ts — K1-12 其他应收款检查表（凭证级测试）状态与计算
 *
 * 忠实反映致同源模板 K1-12 结构：
 *   一、审计目标（存在/权利义务/计价分摊 三认定）
 *   二、样本选取标准与规模（测试总体/特定样本/抽样总体/样本量/抽样方法/抽样过程）
 *   三、测试（1.本期发生额检查 2.期后收款检查，凭证级明细 + 五项核对）
 *   四、审计说明（检查比例表：本期借方/本期贷方/期末余额 → 账面/检查/比例）
 *   五、审计结论
 *
 * 纯函数 + ref 状态，持久化由组件层 emit('save') 负责。
 * 数据打包为单一 JSON 存 checklist_responses（item_id: K1-12-voucher-check）。
 *
 * J1-8、K2-6、K3-7、K4-4、K5-7、K7-5、K8-8、K9-8、M1-6、M2-5、N2 的凭证检查表也用它。抽凭回填 / 挂凭导入 / 撤销 /
 * 年审阶段预审行只读走共享回填函数 `useVoucherCheckFill`：本期发生额、期后两张表（加宿主自管的表，如 J1 期后支付），
 * 回填进哪张由宿主自己选（不再借引擎的 phase 传「本期 / 期后」），一个对方科目一行（后端配对），按分录指纹去重，
 * 行元数据 `_gt` 随行 JSON 落库（spec voucher-identity-writeback-and-audit-phase 任务 13）。
 */
import { ref, computed, toValue, type MaybeRefOrGetter, type Ref } from 'vue'
import { isK1RelatedPartyMarked } from './useK1RelatedParty'
import { partyNameForColumn } from './shared/samplingPartyTarget'
import {
  metaOf, useVoucherCheckFill, withRowMeta,
  type EngineFilledPayload, type FillSample, type PreparedItem,
} from './shared/voucherCheckFill'

// ─── 源模板五项核对（对齐 K1-12 Excel R13 测试内容说明）────────────────────────
export const K1_VOUCHER_CHECK_LABELS = [
  '原始凭证内容完整',
  '账务记录与原始凭证相符',
  '会计处理正确',
  '会计期间正确',
  '债务人与交易对手核对一致',
] as const

// ─── 凭证检查行 ───────────────────────────────────────────────────────────────
export interface K1VoucherRow {
  id: string
  debtorName: string        // 债务人名称
  date: string              // 日期
  voucherNo: string         // 凭证编号
  businessContent: string   // 业务内容
  offsetAccount: string     // 对方科目
  offsetSubAccount: string  // 对方明细科目
  debitAmount: number       // 借方金额
  creditAmount: number       // 贷方金额
  supportingDoc: string     // 支持性文件
  checks: boolean[]         // 核对内容 1-5
  indexNo: string           // 索引号
  abnormal: boolean         // 是否异常
  remark: string            // 备注说明
  /** OCR 附件文件名（可选） */
  ocrAttachment?: string
}

// ─── 样本选取标准与规模 ───────────────────────────────────────────────────────
export interface K1SampleCriteria {
  populationDebitCount: number    // 借方发生额凭证笔数
  populationDebitAmount: number   // 借方发生额金额
  populationCreditCount: number   // 贷方发生额凭证笔数
  populationCreditAmount: number  // 贷方发生额金额
  specificSample: string          // 特定样本说明（大额/关联方/异常）
  samplingPopulationCount: number // 抽样总体笔数
  samplingPopulationAmount: number// 抽样总体金额
  sampleSize: number              // 确定的抽样样本量
  samplingMethod: string          // 抽样方法
  samplingProcess: string         // 抽样过程
  endBalance: number              // 期末余额（用于检查比例）
  /** 特定样本笔数（用于计算抽样总体） */
  specificSampleCount: number
  /** 特定样本金额（用于计算抽样总体） */
  specificSampleAmount: number
  /** 账面本期借方（检查比例分母，可勾 K1-1/K1-2） */
  bookDebitOccurrence: number
  /** 账面本期贷方（检查比例分母，可勾 K1-1/K1-2） */
  bookCreditOccurrence: number
}

export interface K1CheckRatioRow {
  direction: string     // 方向
  bookAmount: number    // 账面金额
  checkedAmount: number // 检查金额
  ratio: number | null  // 检查比例
}

export interface K1SampleSizeDeviation {
  planned: number
  actual: number
  diff: number
  needsExpansion: boolean
}

export interface K1LargeAmountSpecifics {
  counterparties: Array<{ name: string; amount: number; proportion: number | null }>
  totalAmount: number
  count: number
}

export interface K1AbnormalAdjDraft {
  summary: string
  accountCode: string
  accountName: string
  debitAmount: number
  creditAmount: number
  indexRef: string
  remark: string
}

/** K1-12 → K1-4 推送标记，用于去重 */
export const K1_VOUCHER_PUSH_MARK = '【K1-12推送】'

const CHECK_LABELS = [...K1_VOUCHER_CHECK_LABELS]

function emptyRow(seq: number): K1VoucherRow {
  return {
    id: `k1vc-${Date.now()}-${seq}-${Math.random().toString(36).slice(2, 6)}`,
    debtorName: '', date: '', voucherNo: '', businessContent: '',
    offsetAccount: '', offsetSubAccount: '', debitAmount: 0, creditAmount: 0,
    supportingDoc: '', checks: [false, false, false, false, false],
    indexNo: '', abnormal: false, remark: '',
  }
}

/**
 * 共享回填函数的待写入项 → 凭证检查行：一个对方科目一行（后端配对），金额在样本自己的借贷栏，对方科目 = 编码、
 * 对方明细 = 名称（配不上写「多科目」）。原实现经 expandMultiAccountVouchers 展开（把对方分录的金额写进样本行）、
 * 按凭证号去重（同号的另一条分录被丢掉），已删除。
 */
export function mapPreparedToK1VoucherRow(item: PreparedItem): K1VoucherRow {
  const s = item.sample as PreparedItem['sample'] & {
    summary?: string | null; selectionReason?: string | null; remark?: string | null
    abnormal?: boolean | null; supportingDoc?: string | null; debtorName?: string | null
  }
  const code = item.counterpartAccount
  const name = item.counterpartAccountName
  return {
    ...emptyRow(0),
    debtorName: partyNameForColumn(s, 'debtor') || s.debtorName || '',
    date: s.voucherDate || '',
    voucherNo: s.voucherNo || '',
    businessContent: s.summary || '',
    offsetAccount: code,
    offsetSubAccount: name && name !== code ? name : '',
    debitAmount: Number(item.debitAmount ?? 0) || 0,
    creditAmount: Number(item.creditAmount ?? 0) || 0,
    supportingDoc: s.supportingDoc || '',
    abnormal: !!s.abnormal,
    remark: s.selectionReason || s.remark || '',
  }
}

function hasFilledLeaf(v: unknown): boolean {
  if (v == null) return false
  if (typeof v === 'object') return Object.values(v as Record<string, unknown>).some(hasFilledLeaf)
  if (typeof v === 'number') return v !== 0
  return String(v).trim() !== ''
}

/**
 * 行上已勾核对项，或已填支持性文件、索引号、OCR 附件、证据（J1 卡片的三类单据）——替换与撤销抽凭时据此先确认；
 * 备注缺省是选样原因，不算
 */
export function hasK1VoucherContent(r: K1VoucherRow): boolean {
  const ext = r as K1VoucherRow & { attachments?: Record<string, unknown> | null; evidence?: unknown }
  return r.checks.some(Boolean)
    || [r.supportingDoc, r.indexNo, r.ocrAttachment].some(v => String(v ?? '').trim() !== '')
    || Object.keys(ext.attachments ?? {}).length > 0
    || hasFilledLeaf(ext.evidence)
}

function emptyCriteria(): K1SampleCriteria {
  return {
    populationDebitCount: 0, populationDebitAmount: 0,
    populationCreditCount: 0, populationCreditAmount: 0,
    specificSample: '大额（XX金额以上）、关联方/关联交易形成的款项、异常款项全部测试',
    samplingPopulationCount: 0, samplingPopulationAmount: 0,
    sampleSize: 0, samplingMethod: '货币单元抽样', samplingProcess: '', endBalance: 0,
    specificSampleCount: 0, specificSampleAmount: 0,
    bookDebitOccurrence: 0, bookCreditOccurrence: 0,
  }
}

function getNumFromMap(map: Map<string, any>, key: string): number {
  const raw = map.get(key)?.remark ?? map.get(key)?.conclusion
  const n = Number(raw)
  return Number.isFinite(n) ? n : 0
}

/** 从 K1-1 审定表其他应收款区块汇总借/贷发生额，期末余额优先取 K1-2 合计 */
export function pullK1BookAmounts(map: Map<string, any>): {
  debit: number
  credit: number
  endBalance: number
  relatedParties: string[]
} {
  let debit = 0
  let credit = 0
  const count = getNumFromMap(map, 'K1-1-receivable-count') || 5
  for (let i = 0; i < count; i++) {
    debit += getNumFromMap(map, `K1-1-receivable-r${i}-debit`)
    credit += getNumFromMap(map, `K1-1-receivable-r${i}-credit`)
  }
  const endBalance = getNumFromMap(map, 'K1-2-end-subtotal')
    || getNumFromMap(map, 'K1-1-audited-receivable')

  const relatedParties: string[] = []
  try {
    const raw = map.get('K1-2-detail-rows')?.remark
    if (raw) {
      const rows = typeof raw === 'string' ? JSON.parse(raw) : raw
      if (Array.isArray(rows)) {
        for (const r of rows) {
          if (isK1RelatedPartyMarked(r?.relatedParty) && r?.counterparty) {
            relatedParties.push(String(r.counterparty))
          }
        }
      }
    }
  } catch { /* ignore */ }

  return { debit, credit, endBalance, relatedParties }
}

/** 抽样总体 = 测试总体 − 特定样本（对齐 Excel 二、样本选取逻辑） */
export function computeK1SamplingPopulation(criteria: Pick<
  K1SampleCriteria,
  | 'populationDebitCount' | 'populationCreditCount'
  | 'populationDebitAmount' | 'populationCreditAmount'
  | 'specificSampleCount' | 'specificSampleAmount'
>): { count: number; amount: number } {
  const totalCount = (criteria.populationDebitCount || 0) + (criteria.populationCreditCount || 0)
  const totalAmount = (criteria.populationDebitAmount || 0) + (criteria.populationCreditAmount || 0)
  return {
    count: Math.max(0, totalCount - (criteria.specificSampleCount || 0)),
    amount: Math.max(0, totalAmount - (criteria.specificSampleAmount || 0)),
  }
}

/** 从 K1-5 大额分析读取特定样本候选（默认占比 ≥10%） */
export function pullK1LargeAmountSpecifics(
  map: Map<string, any>,
  threshold = 0.1,
): K1LargeAmountSpecifics {
  const empty: K1LargeAmountSpecifics = { counterparties: [], totalAmount: 0, count: 0 }
  try {
    const raw = map.get('K1-5-large-rows')?.remark
    if (!raw) return empty
    const rows = typeof raw === 'string' ? JSON.parse(raw) : raw
    if (!Array.isArray(rows) || !rows.length) return empty

    const total = rows.reduce((s: number, r: any) => s + (Number(r?.endBalance) || 0), 0)
    const selected = rows.filter((r: any) => {
      const prop = Number(r?.proportion ?? (total > 0 ? (Number(r?.endBalance) || 0) / total : 0))
      return prop >= threshold || rows.length <= 5
    })
    const counterparties = selected
      .map((r: any) => ({
        name: String(r?.counterparty || ''),
        amount: Number(r?.endBalance) || 0,
        proportion: r?.proportion != null ? Number(r.proportion) : null,
      }))
      .filter(c => c.name)

    return {
      counterparties,
      totalAmount: counterparties.reduce((s, c) => s + c.amount, 0),
      count: counterparties.length,
    }
  } catch {
    return empty
  }
}

export function isK1VoucherRowChecksComplete(row: K1VoucherRow): boolean {
  return row.checks.length === 5 && row.checks.every(Boolean)
}

export type K1VoucherCheckStatus = 'ok' | 'missing' | 'pending' | 'warn'

export interface K1VoucherCheckItem {
  key: string
  label: string
  status: K1VoucherCheckStatus
  detail: string
}

/**
 * K1-12 逐笔核对实时状态（五项核对 + 关键字段完备性）。
 * 与表格勾选同源：checks[i]===true → ok。
 */
export function evaluateK1VoucherChecks(row: K1VoucherRow): K1VoucherCheckItem[] {
  const items: K1VoucherCheckItem[] = K1_VOUCHER_CHECK_LABELS.map((label, i) => {
    const checked = !!row.checks?.[i]
    return {
      key: `check-${i}`,
      label: `${i + 1}. ${label}`,
      status: checked ? 'ok' : 'pending',
      detail: checked ? '已勾选' : '待核对',
    }
  })

  if (!row.voucherNo?.trim() && !row.debitAmount && !row.creditAmount) {
    items.push({
      key: 'voucher-meta',
      label: '凭证要素',
      status: 'missing',
      detail: '缺凭证号与金额',
    })
  } else if (!row.supportingDoc?.trim()) {
    items.push({
      key: 'supporting',
      label: '支持性文件',
      status: 'warn',
      detail: '未填支持性文件说明',
    })
  } else {
    items.push({
      key: 'supporting',
      label: '支持性文件',
      status: 'ok',
      detail: row.supportingDoc.slice(0, 40),
    })
  }

  return items
}

/** 卡片状态签：完成 / 待核对 / 异常 */
export function k1VoucherCardStatus(row: K1VoucherRow): {
  label: string
  type: 'success' | 'warning' | 'danger' | 'info'
} {
  if (row.abnormal) return { label: '异常', type: 'danger' }
  if (isK1VoucherRowChecksComplete(row)) return { label: '核对通过', type: 'success' }
  const done = (row.checks || []).filter(Boolean).length
  if (done > 0) return { label: `待核对 ${5 - done}`, type: 'warning' }
  return { label: '未开始', type: 'info' }
}

export function useK1VoucherCheck(opts: {
  allResponses: Ref<Map<string, any>>
  itemId?: string
  /** 可选：覆盖 5 项核对标签（如 K9 管理费用第⑤项应为「费用分类正确」而非 K1 的「债务人核对」） */
  checkLabels?: readonly string[]
  /** 项目 id（抽凭回填按项目当前审计阶段标行阶段，年审阶段预审行只读） */
  projectId?: MaybeRefOrGetter<string | null | undefined>
  readonly?: MaybeRefOrGetter<boolean | undefined>
  /** 回填 / 撤销改完行之后保存（宿主的 persist） */
  persist?: () => unknown
  /** 审计期末日（YYYY-MM-DD）：有期后表的宿主传，挂凭导入凭证日期在其后的进期后表；不传则一律进本期发生额 */
  periodEnd?: MaybeRefOrGetter<string | null | undefined>
  /** 宿主自管的其他表（J1 期后支付）：与本期 / 期后两张表一起去重、撤销、年审阶段只读 */
  extraTables?: Record<string, Ref<K1VoucherRow[]>>
  /** 挂凭导入的分表规则（缺省按 periodEnd 分本期 / 期后；J1 按借贷栏与日期分三区） */
  attachTableOf?: (item: PreparedItem) => string
}) {
  const itemId = opts.itemId ?? 'K1-12-voucher-check'

  // ─── 状态 ───────────────────────────────────────────────────────────────────
  const criteria = ref<K1SampleCriteria>(emptyCriteria())
  const occurrenceRows = ref<K1VoucherRow[]>([])   // 本期发生额检查
  const postCollectionRows = ref<K1VoucherRow[]>([]) // 期后收款检查
  const auditNote = ref('')
  const lowRatioExplanation = ref('')
  const conclusion = ref('')
  const conclusionOption = ref('')

  // 允许调用方覆盖核对标签（仅显示用；checks 数组仍固定 5 项）
  const checkLabels = (opts.checkLabels && opts.checkLabels.length === 5)
    ? [...opts.checkLabels]
    : CHECK_LABELS

  // 抽凭回填 / 挂凭导入 / 撤销 / 年审阶段预审行只读：共享回填函数（本期发生额、期后两张表，加宿主自管的表）
  const voucherTables: Record<string, Ref<K1VoucherRow[]>> = {
    occurrence: occurrenceRows, post: postCollectionRows, ...(opts.extraTables ?? {}),
  }
  /** 已在某张表的分录（按指纹）：再次回填 / 挂凭导入仍进那张表 */
  function tableHolding(lfp: string | null): string | null {
    if (!lfp) return null
    for (const [key, rows] of Object.entries(voucherTables)) {
      if (rows.value.some(r => metaOf(r)?.lfp === lfp)) return key
    }
    return null
  }
  const voucherFill = useVoucherCheckFill<K1VoucherRow>({
    projectId: opts.projectId ?? null,
    tables: voucherTables,
    tableOf: (item) => {
      const held = tableHolding(item.meta.lfp)
      if (held || !item.meta.src.includes('attach')) return held
      if (opts.attachTableOf) return opts.attachTableOf(item)
      // 挂凭导入没有所选的表：有期后表的宿主按凭证日期分（期末之后进期后），其余进本期发生额
      const end = toValue(opts.periodEnd) || ''
      return end && String(item.sample.voucherDate ?? '') > end ? 'post' : 'occurrence'
    },
    mapSampleToRow: (item) => mapPreparedToK1VoucherRow(item),
    persist: () => opts.persist?.(),
    hasUserContent: hasK1VoucherContent,
    readonly: () => Boolean(toValue(opts.readonly)),
  })

  // ─── 加载 ────────────────────────────────────────────────────────────────────
  function load(): void {
    try {
      loadStored()
    } finally {
      // 记下预审行的读入版本（年审阶段保存时据此写回）；宿主自管的表须在 load 之前读好
      voucherFill.markLoaded()
    }
  }
  function loadStored(): void {
    const stored = opts.allResponses.value.get(itemId)
    const raw = stored?.remark ?? stored?.value
    if (!raw) return
    try {
      const data = typeof raw === 'string' ? JSON.parse(raw) : raw
      if (data.criteria) criteria.value = { ...emptyCriteria(), ...data.criteria }
      if (Array.isArray(data.occurrenceRows)) occurrenceRows.value = data.occurrenceRows.map(normalizeRow)
      if (Array.isArray(data.postCollectionRows)) postCollectionRows.value = data.postCollectionRows.map(normalizeRow)
      auditNote.value = data.auditNote ?? ''
      lowRatioExplanation.value = data.lowRatioExplanation ?? ''
      conclusion.value = data.conclusion ?? ''
      conclusionOption.value = data.conclusionOption ?? ''
    } catch {
      // 忽略损坏数据
    }
  }

  function normalizeRow(r: any): K1VoucherRow {
    const base = emptyRow(0)
    return withRowMeta({
      ...base,
      ...r,
      checks: Array.isArray(r?.checks) && r.checks.length === 5
        ? r.checks.map((x: any) => !!x)
        : [false, false, false, false, false],
      debitAmount: Number(r?.debitAmount ?? 0),
      creditAmount: Number(r?.creditAmount ?? 0),
    }, r)
  }

  // ─── 行操作 ──────────────────────────────────────────────────────────────────
  function addOccurrenceRow(): void { occurrenceRows.value.push(emptyRow(occurrenceRows.value.length)) }
  function addPostCollectionRow(): void { postCollectionRows.value.push(emptyRow(postCollectionRows.value.length)) }
  /** 删行：年审阶段的预审行不删 */
  function removeOccurrenceRow(id: string): void {
    occurrenceRows.value = occurrenceRows.value.filter(r => r.id !== id || voucherFill.isRowLocked(r))
  }
  function removePostCollectionRow(id: string): void {
    postCollectionRows.value = postCollectionRows.value.filter(r => r.id !== id || voucherFill.isRowLocked(r))
  }

  /** 弹窗/卡片回写：按 id 合并 patch（年审阶段的预审行不改） */
  function updateVoucherRow(
    target: 'occurrence' | 'post',
    id: string,
    patch: Partial<K1VoucherRow>,
  ): boolean {
    const list = target === 'occurrence' ? occurrenceRows : postCollectionRows
    const idx = list.value.findIndex((r) => r.id === id)
    if (idx < 0) return false
    const prev = list.value[idx]
    if (voucherFill.isRowLocked(prev)) return false
    const next: K1VoucherRow = {
      ...prev,
      ...patch,
      id: prev.id,
      checks: Array.isArray(patch.checks) && patch.checks.length === 5
        ? patch.checks.map(Boolean)
        : prev.checks,
    }
    list.value.splice(idx, 1, next)
    return true
  }

  /**
   * 抽凭引擎回填进宿主所选的表（本期发生额 `occurrence` / 期后 `post` / 宿主自管的表）：一个对方科目一行，
   * 按分录指纹去重，「替换本阶段抽凭行」只动所选的表；填完由共享函数保存并提示填入几行。
   */
  function onEngineFilled(payload: EngineFilledPayload, target: string = 'occurrence') {
    return voucherFill.onEngineFilled(payload, { tables: [target] })
  }

  /** 从序时账挂入导入：幂等追加（已在某张表的分录留在原处，其余按 periodEnd / attachTableOf 分表） */
  function onAttachImported(samples: FillSample[]) {
    return voucherFill.onAttachImported(samples)
  }

  /** 从 K1-1/K1-2 带入账面发生额与期末余额（对齐 Excel E61–E63 公式） */
  function applyFromK1Sheets(): { debit: number; credit: number; endBalance: number; filled: boolean } {
    const { debit, credit, endBalance, relatedParties } = pullK1BookAmounts(opts.allResponses.value)
    const filled = debit > 0 || credit > 0 || endBalance > 0
    if (filled) {
      criteria.value.bookDebitOccurrence = debit
      criteria.value.bookCreditOccurrence = credit
      if (!criteria.value.populationDebitAmount) criteria.value.populationDebitAmount = debit
      if (!criteria.value.populationCreditAmount) criteria.value.populationCreditAmount = credit
      if (!criteria.value.endBalance) criteria.value.endBalance = endBalance
      recalcSamplingPopulation()
    }
    if (relatedParties.length) {
      const hint = `关联方全部测试：${relatedParties.slice(0, 8).join('、')}${relatedParties.length > 8 ? '等' : ''}，共${relatedParties.length}户`
      if (!criteria.value.specificSample || criteria.value.specificSample.includes('XX')) {
        criteria.value.specificSample = hint
      }
      if (!criteria.value.specificSampleCount) {
        criteria.value.specificSampleCount = relatedParties.length
      }
    }
    return { debit, credit, endBalance, filled }
  }

  /** 从 K1-5 大额分析带入特定样本说明与数量/金额 */
  function applyFromK1LargeAmount(threshold = 0.1): K1LargeAmountSpecifics & { filled: boolean } {
    const data = pullK1LargeAmountSpecifics(opts.allResponses.value, threshold)
    if (data.count > 0) {
      const fmtWan = (n: number) => (n / 10000).toLocaleString('zh-CN', { maximumFractionDigits: 0 })
      const parts = data.counterparties.slice(0, 8).map(c => `${c.name}(${fmtWan(c.amount)}万)`)
      criteria.value.specificSample = `大额全部测试（K1-5）：${parts.join('、')}${data.count > 8 ? '等' : ''}，共${data.count}户，合计${data.totalAmount.toLocaleString()}元`
      criteria.value.specificSampleCount = data.count
      criteria.value.specificSampleAmount = data.totalAmount
      recalcSamplingPopulation()
    }
    return { ...data, filled: data.count > 0 }
  }

  /** 重算抽样总体（测试总体 − 特定样本） */
  function recalcSamplingPopulation(): { count: number; amount: number } {
    const derived = computeK1SamplingPopulation(criteria.value)
    criteria.value.samplingPopulationCount = derived.count
    criteria.value.samplingPopulationAmount = derived.amount
    return derived
  }

  /** 异常凭证 → K1-4 调整备忘草稿（金额待补） */
  function buildAbnormalAdjDrafts(): K1AbnormalAdjDraft[] {
    return abnormalRows.value.map((r) => {
      const amt = Math.abs(Number(r.debitAmount || r.creditAmount || 0))
      const debtor = r.debtorName ? `${r.debtorName} ` : ''
      return {
        summary: `${K1_VOUCHER_PUSH_MARK}${debtor}凭证异常：${r.voucherNo || '无号'} ${r.businessContent || ''}`.trim(),
        accountCode: '1221',
        accountName: '其他应收款',
        debitAmount: 0,
        creditAmount: 0,
        indexRef: r.indexNo || 'K1-12',
        remark: `来自K1-12凭证检查；${r.remark || '金额待追查补录'}${amt ? `；检查涉及金额约${amt}` : ''}`,
      }
    })
  }

  // ─── 检查比例表（四、审计说明）────────────────────────────────────────────────
  const occurrenceDebitChecked = computed(() => occurrenceRows.value.reduce((s, r) => s + (r.debitAmount || 0), 0))
  const occurrenceCreditChecked = computed(() => occurrenceRows.value.reduce((s, r) => s + (r.creditAmount || 0), 0))
  const postCollectionChecked = computed(() => postCollectionRows.value.reduce((s, r) => s + (r.creditAmount || 0), 0))

  const checkRatios = computed<K1CheckRatioRow[]>(() => {
    const mk = (direction: string, book: number, checked: number): K1CheckRatioRow => ({
      direction, bookAmount: book, checkedAmount: checked,
      ratio: book > 0 ? checked / book : null,
    })
    return [
      mk('本期借方', criteria.value.bookDebitOccurrence || criteria.value.populationDebitAmount, occurrenceDebitChecked.value),
      mk('本期贷方', criteria.value.bookCreditOccurrence || criteria.value.populationCreditAmount, occurrenceCreditChecked.value),
      mk('期末余额', criteria.value.endBalance, postCollectionChecked.value),
    ]
  })

  /** 检查比例是否偏低（<30% 需扩样或说明）*/
  const lowRatioWarnings = computed(() =>
    checkRatios.value.filter(r => r.ratio != null && r.ratio < 0.3 && r.bookAmount > 0),
  )

  /** 计划样本量 vs 实际检查笔数 */
  const sampleSizeDeviation = computed<K1SampleSizeDeviation | null>(() => {
    const planned = criteria.value.sampleSize
    if (!planned) return null
    const actual = occurrenceRows.value.length
    return { planned, actual, diff: actual - planned, needsExpansion: actual < planned }
  })

  /** 有数据但五项核对未勾满的凭证 */
  const incompleteCheckRows = computed(() => {
    const hasData = (r: K1VoucherRow) => !!(r.voucherNo || r.debitAmount || r.creditAmount)
    return [
      ...occurrenceRows.value.filter(r => hasData(r) && !isK1VoucherRowChecksComplete(r)),
      ...postCollectionRows.value.filter(r => hasData(r) && !isK1VoucherRowChecksComplete(r)),
    ]
  })

  /** 抽样总体演算值（只读预览，与 criteria 中字段一致） */
  const derivedSamplingPopulation = computed(() => computeK1SamplingPopulation(criteria.value))

  /** 异常凭证汇总 */
  const abnormalRows = computed(() => [
    ...occurrenceRows.value.filter(r => r.abnormal),
    ...postCollectionRows.value.filter(r => r.abnormal),
  ])

  // ─── 序列化（持久化用）─────────────────────────────────────────────────────────
  function serialize(): string {
    return JSON.stringify({
      criteria: criteria.value,
      occurrenceRows: voucherFill.guardPersist(occurrenceRows.value, 'occurrence'),
      postCollectionRows: voucherFill.guardPersist(postCollectionRows.value, 'post'),
      auditNote: auditNote.value,
      lowRatioExplanation: lowRatioExplanation.value,
      conclusion: conclusion.value,
      conclusionOption: conclusionOption.value,
    })
  }

  return {
    itemId, checkLabels,
    criteria, occurrenceRows, postCollectionRows, auditNote, lowRatioExplanation,
    conclusion, conclusionOption,
    checkRatios, lowRatioWarnings, sampleSizeDeviation, incompleteCheckRows, derivedSamplingPopulation, abnormalRows,
    occurrenceDebitChecked, occurrenceCreditChecked, postCollectionChecked,
    load, addOccurrenceRow, addPostCollectionRow, removeOccurrenceRow, removePostCollectionRow,
    updateVoucherRow,
    applyFromK1Sheets, applyFromK1LargeAmount, recalcSamplingPopulation,
    buildAbnormalAdjDrafts, serialize,
    // 抽凭回填 / 挂凭导入 / 撤销 / 年审阶段预审行只读（共享回填函数）
    onEngineFilled,
    onAttachImported,
    onUndoRequest: voucherFill.onUndoRequest,
    voucherRowClass: voucherFill.rowClass,
    isVoucherRowLocked: voucherFill.isRowLocked,
    voucherFillReady: voucherFill.ready,
    /** 宿主自管的表保存前过一遍（年审阶段预审行按读入版本写回） */
    guardPersist: voucherFill.guardPersist,
  }
}
