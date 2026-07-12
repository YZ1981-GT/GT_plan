/**
 * useK1VoucherCheck.ts — K1-12 其他应收款检查表（凭证级测试）状态与计算
 *
 * 忠实反映致同源模板 K1-12 结构：
 *   一、审计目标（存在/权利义务/计价分摊 三认定）
 *   二、样本选取标准与规模（测试总体/特定样本/抽样总体/样本量/抽样方法/抽样过程）
 *   三、测试（1.本期发生额检查 2.期后收款检查，凭证级明细）
 *   四、审计说明（检查比例表：本期借方/本期贷方/期末余额 → 账面/检查/比例）
 *   五、审计结论
 *
 * 纯函数 + ref 状态，持久化由组件层 emit('save') 负责。
 * 数据打包为单一 JSON 存 checklist_responses（item_id: K1-12-voucher-check）。
 */
import { ref, computed, type Ref } from 'vue'

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
}

export interface K1CheckRatioRow {
  direction: string     // 方向
  bookAmount: number    // 账面金额
  checkedAmount: number // 检查金额
  ratio: number | null  // 检查比例
}

const CHECK_LABELS = ['凭证与原始单据相符', '业务内容真实合理', '会计科目正确', '金额计算准确', '截止期间正确']

function emptyRow(seq: number): K1VoucherRow {
  return {
    id: `k1vc-${Date.now()}-${seq}-${Math.random().toString(36).slice(2, 6)}`,
    debtorName: '', date: '', voucherNo: '', businessContent: '',
    offsetAccount: '', offsetSubAccount: '', debitAmount: 0, creditAmount: 0,
    supportingDoc: '', checks: [false, false, false, false, false],
    indexNo: '', abnormal: false, remark: '',
  }
}

function emptyCriteria(): K1SampleCriteria {
  return {
    populationDebitCount: 0, populationDebitAmount: 0,
    populationCreditCount: 0, populationCreditAmount: 0,
    specificSample: '', samplingPopulationCount: 0, samplingPopulationAmount: 0,
    sampleSize: 0, samplingMethod: '货币单元抽样', samplingProcess: '', endBalance: 0,
  }
}

export function useK1VoucherCheck(opts: {
  allResponses: Ref<Map<string, any>>
  itemId?: string
}) {
  const itemId = opts.itemId ?? 'K1-12-voucher-check'

  // ─── 状态 ───────────────────────────────────────────────────────────────────
  const criteria = ref<K1SampleCriteria>(emptyCriteria())
  const occurrenceRows = ref<K1VoucherRow[]>([])   // 本期发生额检查
  const postCollectionRows = ref<K1VoucherRow[]>([]) // 期后收款检查
  const auditNote = ref('')
  const conclusion = ref('')
  const conclusionOption = ref('')

  const checkLabels = CHECK_LABELS

  // ─── 加载 ────────────────────────────────────────────────────────────────────
  function load(): void {
    const stored = opts.allResponses.value.get(itemId)
    const raw = stored?.remark ?? stored?.value
    if (!raw) return
    try {
      const data = typeof raw === 'string' ? JSON.parse(raw) : raw
      if (data.criteria) criteria.value = { ...emptyCriteria(), ...data.criteria }
      if (Array.isArray(data.occurrenceRows)) occurrenceRows.value = data.occurrenceRows.map(normalizeRow)
      if (Array.isArray(data.postCollectionRows)) postCollectionRows.value = data.postCollectionRows.map(normalizeRow)
      auditNote.value = data.auditNote ?? ''
      conclusion.value = data.conclusion ?? ''
      conclusionOption.value = data.conclusionOption ?? ''
    } catch {
      // 忽略损坏数据
    }
  }

  function normalizeRow(r: any): K1VoucherRow {
    const base = emptyRow(0)
    return {
      ...base,
      ...r,
      checks: Array.isArray(r?.checks) && r.checks.length === 5
        ? r.checks.map((x: any) => !!x)
        : [false, false, false, false, false],
      debitAmount: Number(r?.debitAmount ?? 0),
      creditAmount: Number(r?.creditAmount ?? 0),
    }
  }

  // ─── 行操作 ──────────────────────────────────────────────────────────────────
  function addOccurrenceRow(): void { occurrenceRows.value.push(emptyRow(occurrenceRows.value.length)) }
  function addPostCollectionRow(): void { postCollectionRows.value.push(emptyRow(postCollectionRows.value.length)) }
  function removeOccurrenceRow(id: string): void { occurrenceRows.value = occurrenceRows.value.filter(r => r.id !== id) }
  function removePostCollectionRow(id: string): void { postCollectionRows.value = postCollectionRows.value.filter(r => r.id !== id) }

  /** 抽凭引擎回填：把样本映射为凭证检查行 */
  function fillFromSamples(target: 'occurrence' | 'post', samples: any[]): void {
    const mapped: K1VoucherRow[] = samples.map((s, i) => ({
      ...emptyRow(i),
      debtorName: s.counterpartName ?? s.debtorName ?? '',
      date: s.voucherDate ?? '',
      voucherNo: s.voucherNo ?? '',
      businessContent: s.summary ?? '',
      offsetAccount: s.counterpartAccount ?? '',
      debitAmount: Number(s.debitAmount ?? 0),
      creditAmount: Number(s.creditAmount ?? 0),
      abnormal: !!s.abnormal,
      remark: s.selectionReason ?? '',
    }))
    if (target === 'occurrence') {
      const existing = new Set(occurrenceRows.value.map(r => r.voucherNo).filter(Boolean))
      occurrenceRows.value.push(...mapped.filter(r => !r.voucherNo || !existing.has(r.voucherNo)))
    } else {
      const existing = new Set(postCollectionRows.value.map(r => r.voucherNo).filter(Boolean))
      postCollectionRows.value.push(...mapped.filter(r => !r.voucherNo || !existing.has(r.voucherNo)))
    }
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
      mk('本期借方', criteria.value.populationDebitAmount, occurrenceDebitChecked.value),
      mk('本期贷方', criteria.value.populationCreditAmount, occurrenceCreditChecked.value),
      mk('期末余额', criteria.value.endBalance, postCollectionChecked.value),
    ]
  })

  /** 检查比例是否偏低（<某阈值需扩样或说明）*/
  const lowRatioWarnings = computed(() =>
    checkRatios.value.filter(r => r.ratio != null && r.ratio < 0.3 && r.bookAmount > 0)
  )

  /** 异常凭证汇总 */
  const abnormalRows = computed(() => [
    ...occurrenceRows.value.filter(r => r.abnormal),
    ...postCollectionRows.value.filter(r => r.abnormal),
  ])

  // ─── 序列化（持久化用）─────────────────────────────────────────────────────────
  function serialize(): string {
    return JSON.stringify({
      criteria: criteria.value,
      occurrenceRows: occurrenceRows.value,
      postCollectionRows: postCollectionRows.value,
      auditNote: auditNote.value,
      conclusion: conclusion.value,
      conclusionOption: conclusionOption.value,
    })
  }

  return {
    itemId, checkLabels,
    criteria, occurrenceRows, postCollectionRows, auditNote, conclusion, conclusionOption,
    checkRatios, lowRatioWarnings, abnormalRows,
    occurrenceDebitChecked, occurrenceCreditChecked, postCollectionChecked,
    load, addOccurrenceRow, addPostCollectionRow, removeOccurrenceRow, removePostCollectionRow,
    fillFromSamples, serialize,
  }
}
