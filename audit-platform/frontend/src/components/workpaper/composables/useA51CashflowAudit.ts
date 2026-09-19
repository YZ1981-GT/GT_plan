/**
 * useA51CashflowAudit — A5-1 现金流量表审计 数据管理 + 计算 + 持久化
 *
 * Spec: .kiro/specs/a5-1-cashflow-audit/
 * Tasks: 2.1, 2.2, 2.3
 *
 * 职责：
 * - 静态常量定义（PROGRAM_STEPS, AUDIT_ROWS, RECONCILE_GROUPS, etc.）
 * - loadData / refreshData: 自加载 render-config?force_component_type=a5-1-cashflow-audit
 * - getField / setField: 字段读写
 * - debouncedSave: 2s debounce → PUT checklist-responses 批量
 * - 全部自动计算函数（审定数、合计、差异等）
 * - programProgress: {filled, total:21}
 */
import { ref, computed, type Ref, type ComputedRef } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '@/services/apiProxy'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface ProgramStep {
  id: string
  title: string
  level: number
}

export interface AuditRow {
  id: string
  name: string
  type: 'editable' | 'auto'
  sign: '+' | '-' | ''
}

export interface ReconcileItem {
  id: string
  name: string
}

export interface ReconcileGroup {
  id: string
  title: string
  items: ReconcileItem[]
}

export interface CheckSection {
  id: string
  title: string
  rows: { id: string; name: string; type: 'editable' | 'auto' }[]
}

export interface CheckRow {
  id: string
  name: string
  type: 'editable' | 'auto'
}

export interface OtherCFGroup {
  id: string
  title: string
  receive: { id: string; name: string }[]
  pay: { id: string; name: string }[]
}

export interface TipSection {
  title: string
  content: string[]
}

// ─── Static Constants (Task 2.1) ─────────────────────────────────────────────

export const AUDIT_OBJECTIVES: string[] = [
  '现金流量表的内容、性质和数额是否正确、合理、完整',
  '现金流量有关项目数额与其他报表及附注的勾稽关系是否正确',
  '现金流量表各项目的披露是否恰当',
]

export const PROGRAM_STEPS: ProgramStep[] = [
  { id: 'step-1', title: '获取编制现金流量表的基础资料', level: 0 },
  { id: 'step-1-1', title: '复核加计是否正确', level: 1 },
  { id: 'step-1-2', title: '与相关账户余额及发生额核对一致', level: 1 },
  { id: 'step-2', title: '核对现金及现金等价物', level: 0 },
  { id: 'step-2-1', title: '确认货币资金余额与审定数一致', level: 1 },
  { id: 'step-2-2', title: '确认受限存款已适当扣除', level: 1 },
  { id: 'step-2-3', title: '确认现金等价物范围适当', level: 1 },
  { id: 'step-3', title: '经营活动现金流量核查', level: 0 },
  { id: 'step-3-1', title: '勾稽核对：销售商品收到的现金', level: 1 },
  { id: 'step-3-2', title: '勾稽核对：购买商品支付的现金', level: 1 },
  { id: 'step-3-3', title: '勾稽核对：支付职工薪酬', level: 1 },
  { id: 'step-3-4', title: '勾稽核对：支付各项税金', level: 1 },
  { id: 'step-4', title: '投资活动现金流量核查', level: 0 },
  { id: 'step-4-1', title: '核查取得/处置子公司现金流量', level: 1 },
  { id: 'step-4-2', title: '核查固定资产等长期资产购建/处置', level: 1 },
  { id: 'step-5', title: '筹资活动现金流量核查', level: 0 },
  { id: 'step-5-1', title: '核查借款收到/偿还的现金', level: 1 },
  { id: 'step-5-2', title: '核查分配股利/偿付利息', level: 1 },
  { id: 'step-6', title: '编制现金流量表补充资料', level: 0 },
  { id: 'step-6-1', title: '核对间接法调整项目', level: 1 },
  { id: 'step-6-2', title: '核对现金及现金等价物净变动额与直接法一致', level: 1 },
]

export const AUDIT_ROWS: AuditRow[] = [
  { id: '1', name: '年12月31日货币资金', type: 'editable', sign: '+' },
  { id: '2', name: '减：使用受到限制的存款', type: 'editable', sign: '-' },
  { id: '3', name: '减：其他扣减项', type: 'editable', sign: '-' },
  { id: '4', name: '加：持有期限不超过三个月的国债投资', type: 'editable', sign: '+' },
  { id: '5', name: '加：其他加项', type: 'editable', sign: '+' },
  { id: '6', name: '现金及现金等价物余额', type: 'auto', sign: '' },
  { id: '7', name: '减：上年12月31日现金及现金等价物余额', type: 'editable', sign: '-' },
  { id: '8', name: '现金及现金等价物净增加/(减少)额', type: 'auto', sign: '' },
]

export const RECONCILE_GROUPS: ReconcileGroup[] = [
  {
    id: '1',
    title: '销售商品、提供劳务收到的现金',
    items: [
      { id: '1', name: '营业收入' },
      { id: '2', name: '加：应收账款减少额' },
      { id: '3', name: '加：应收票据减少额' },
      { id: '4', name: '加：预收款项增加额' },
      { id: '5', name: '加：销项税额' },
      { id: '6', name: '减：应收账款坏账准备减少额' },
      { id: '7', name: '加：特殊调整项1' },
      { id: '8', name: '加：特殊调整项2' },
      { id: '9', name: '加：特殊调整项3' },
      { id: '10', name: '加：其他' },
    ],
  },
  {
    id: '2',
    title: '购买商品、接受劳务支付的现金',
    items: [
      { id: '1', name: '营业成本(不含折旧摊销)' },
      { id: '2', name: '加：存货增加额' },
      { id: '3', name: '加：应付账款减少额' },
      { id: '4', name: '加：应付票据减少额' },
      { id: '5', name: '加：预付款项增加额' },
      { id: '6', name: '加：进项税额' },
      { id: '7', name: '减：应付账款坏账准备减少额' },
      { id: '8', name: '加：特殊调整项1' },
      { id: '9', name: '加：特殊调整项2' },
      { id: '10', name: '加：其他' },
    ],
  },
  {
    id: '3',
    title: '支付给职工以及为职工支付的现金',
    items: [
      { id: '1', name: '应付职工薪酬本期借方发生额' },
      { id: '2', name: '加：在建工程中的薪酬支出' },
      { id: '3', name: '加：研发费用中的薪酬支出' },
    ],
  },
  {
    id: '4',
    title: '支付的各项税金',
    items: [
      { id: '1', name: '所得税费用(扣除递延)' },
      { id: '2', name: '加：税金及附加' },
      { id: '3', name: '加：增值税已交税金' },
    ],
  },
]

export const CHECK4_SECTIONS: CheckSection[] = [
  {
    id: 'acquire',
    title: '一、取得子公司及其他营业单位',
    rows: [
      { id: '1', name: '支付的现金对价', type: 'editable' },
      { id: '2', name: '加：支付的直接费用', type: 'editable' },
      { id: '3', name: '支付现金总额', type: 'editable' },
      { id: '4', name: '减：子公司持有的现金', type: 'editable' },
      { id: '5', name: '支付净额', type: 'auto' },
      { id: '6', name: '非现金对价', type: 'editable' },
      { id: '7', name: '取得的净资产', type: 'editable' },
      { id: '8', name: '商誉/(负商誉)', type: 'editable' },
      { id: '9', name: '少数股东权益', type: 'editable' },
      { id: '10', name: '其他调整', type: 'editable' },
    ],
  },
  {
    id: 'dispose',
    title: '二、处置子公司及其他营业单位',
    rows: [
      { id: '1', name: '收到的现金对价', type: 'editable' },
      { id: '2', name: '加：收到的其他款项', type: 'editable' },
      { id: '3', name: '收到现金总额', type: 'editable' },
      { id: '4', name: '减：子公司持有的现金', type: 'editable' },
      { id: '5', name: '收到净额', type: 'auto' },
      { id: '6', name: '处置的净资产', type: 'editable' },
      { id: '7', name: '处置损益', type: 'editable' },
      { id: '8', name: '少数股东权益变动', type: 'editable' },
      { id: '9', name: '非现金对价', type: 'editable' },
      { id: '10', name: '其他调整', type: 'editable' },
    ],
  },
]

export const CHECK5_ROWS: CheckRow[] = [
  { id: '1', name: '库存现金', type: 'editable' },
  { id: '2', name: '银行存款', type: 'editable' },
  { id: '3', name: '其他货币资金', type: 'editable' },
  { id: '4', name: '存放中央银行款项', type: 'editable' },
  { id: '5', name: '存放同业款项', type: 'editable' },
  { id: '6', name: '拆放同业', type: 'editable' },
  { id: '7', name: '现金等价物(短期债券投资)', type: 'editable' },
  { id: '8', name: '期末余额', type: 'auto' },
  { id: '9', name: '减：受限部分', type: 'editable' },
  { id: '10', name: '期末现金及现金等价物余额', type: 'auto' },
]

export const OTHER_CF_GROUPS: OtherCFGroup[] = [
  {
    id: '1',
    title: '经营活动',
    receive: Array.from({ length: 10 }, (_, i) => ({ id: String(i + 1), name: i === 0 ? '收到的保证金/押金' : '' })),
    pay: Array.from({ length: 10 }, (_, i) => ({ id: String(i + 1), name: i === 0 ? '支付的保证金/押金' : '' })),
  },
  {
    id: '2',
    title: '投资活动',
    receive: Array.from({ length: 10 }, (_, i) => ({ id: String(i + 1), name: i === 0 ? '收到的政府补助' : '' })),
    pay: Array.from({ length: 10 }, (_, i) => ({ id: String(i + 1), name: i === 0 ? '支付的并购咨询费' : '' })),
  },
  {
    id: '3',
    title: '筹资活动',
    receive: Array.from({ length: 10 }, (_, i) => ({ id: String(i + 1), name: i === 0 ? '收到的借款保证金' : '' })),
    pay: Array.from({ length: 10 }, (_, i) => ({ id: String(i + 1), name: i === 0 ? '支付的融资手续费' : '' })),
  },
]

export const ACCOUNTING_TIPS: TipSection[] = [
  {
    title: '一、现金流量表编制实务问题',
    content: [
      '1. 现金流量表的编制应以实际收支为基础，而非权责发生制下的收入费用。编制时需特别注意增值税的影响——销售商品收到的现金应包含代收的增值税销项税额，购买商品支付的现金应包含进项税额。',
      '2. 同一笔交易涉及多个现金流量类别时，应按其经济实质分别归类。例如偿还银行借款本息，本金部分列为筹资活动，利息部分列为筹资活动"分配股利、利润或偿付利息"项。',
    ],
  },
  {
    title: '二、现金及现金等价物范围',
    content: [
      '可以作为现金等价物的：持有期限不超过三个月的债券投资、货币市场基金（T+0赎回且金额可确定）。',
      '不可作为现金等价物的：权益性投资（股票）、持有期限超过三个月的定期存款（除非可提前支取且不受重大损失）、受限的银行存款、信用证保证金。',
    ],
  },
  {
    title: '三、受限存款及利息收入列报',
    content: [
      '各类存款保证金→"支付其他与经营活动有关的现金"',
      '信用证保证金→"支付其他与经营活动有关的现金"',
      '银行承兑汇票保证金→"支付其他与经营活动有关的现金"',
      '履约保证金→"支付其他与经营活动有关的现金"',
      '投标保证金→"支付其他与经营活动有关的现金"',
      '住房公积金专户→不纳入现金等价物',
      '法院冻结款项→不纳入现金等价物',
      '央行准备金→视性质归入"存放中央银行款项"',
      '协定存款→作为银行存款，不受限部分纳入现金',
      '结构性存款→持有期>3月不作现金等价物',
      '定期存款(≤3月)→作为现金等价物',
      '定期存款(>3月)→受限，不作现金等价物',
      '通知存款→视可随时支取性判断是否受限',
      '外汇保证金→"支付其他与经营活动有关的现金"',
      '期货保证金→"支付其他与投资活动有关的现金"',
      '质押定期存款→受限存款，不纳入现金等价物',
      '理财产品(>3月)→"支付其他与投资活动有关的现金"',
      '理财产品(≤3月可赎回)→视同现金等价物（需满足流动性条件）',
    ],
  },
  {
    title: '四、政府补助及固定资产进项税',
    content: [
      '与日常活动相关的政府补助(计入其他收益)：收到时列为"收到其他与经营活动有关的现金"。',
      '与日常活动无关的政府补助(计入营业外收入)：收到时列为"收到其他与经营活动有关的现金"（注：CAS 16要求统一列入经营活动）。',
      '购建固定资产的进项税额：列为"购建固定资产、无形资产和其他长期资产支付的现金"的组成部分，不单独列为经营活动。',
      '留抵退税：收到时列为"收到的税费返还"（经营活动）。',
    ],
  },
]

// ─── Composable Interface ────────────────────────────────────────────────────

export interface UseA51Options {
  wpId: Ref<string>
}

export interface UseA51Return {
  // State
  responses: Ref<Record<string, string>>
  loading: Ref<boolean>
  lastSavedAt: Ref<Date | null>
  saveError: Ref<boolean>
  // Data loading
  loadData: (wpId: string) => Promise<void>
  refreshData: (wpId: string) => Promise<void>
  // Field access
  getField: (itemId: string) => string
  setField: (itemId: string, value: string) => void
  // Calculations (Task 2.3)
  getAuditedAmount: (rowId: string) => number
  getAuditRow6Amount: () => number
  getAuditRow8Amount: () => number
  getReconcileTotal: (groupId: string) => number
  getReconcileDiff: (groupId: string) => number
  getCheckDiff: (tab: string, rowIdx: string) => number
  getCheck5Balance: () => number
  getOtherCFTotal: (groupId: string, side: 'receive' | 'pay') => number
  programProgress: ComputedRef<{ filled: number; total: number }>
  // Lifecycle
  flushPendingSave: () => Promise<void>
}

// ─── Helper ──────────────────────────────────────────────────────────────────

/** parseFloat with NaN→0 fallback */
function safeFloat(val: string | undefined | null): number {
  if (!val) return 0
  const n = parseFloat(val)
  return isNaN(n) ? 0 : n
}

// ─── Composable (Tasks 2.2 + 2.3) ───────────────────────────────────────────

export function useA51CashflowAudit(opts: UseA51Options): UseA51Return {
  const { wpId } = opts

  const responses = ref<Record<string, string>>({})
  const loading = ref(false)
  const lastSavedAt = ref<Date | null>(null)
  const saveError = ref(false)

  // ─── Pending saves ───
  const pendingItems = new Map<string, { item_id: string; conclusion: string | null; remark: string | null }>()
  let saveTimer: ReturnType<typeof setTimeout> | null = null

  // ─── Data Loading (Task 2.2) ───

  async function loadData(targetId: string): Promise<void> {
    loading.value = true
    try {
      const res = await api.get<any>(
        `/api/workpapers/${targetId}/render-config?force_component_type=a5-1-cashflow-audit`,
        { _silent: true } as any,
      )
      // render-config 返回 {sheets: [{html_data: {responses: {...}}}]}
      const htmlData = res?.sheets?.[0]?.html_data
      if (htmlData?.responses && typeof htmlData.responses === 'object') {
        const newResponses: Record<string, string> = {}
        for (const [key, val] of Object.entries(htmlData.responses)) {
          newResponses[key] = typeof val === 'string' ? val : String(val ?? '')
        }
        responses.value = newResponses
      }
    } catch {
      // 不阻塞渲染——步骤是静态定义的，responses 为空时仍可正常填写
    } finally {
      loading.value = false
    }
  }

  async function refreshData(targetId: string): Promise<void> {
    await loadData(targetId)
  }

  // ─── Field Read/Write (Task 2.2) ───

  function getField(itemId: string): string {
    return responses.value[itemId] ?? ''
  }

  function setField(itemId: string, value: string): void {
    responses.value[itemId] = value
    // Queue for save
    pendingItems.set(itemId, { item_id: itemId, conclusion: null, remark: value })
    scheduleSave()
  }

  // ─── Debounce Save (Task 2.2) ───

  function scheduleSave() {
    saveError.value = false
    if (saveTimer) clearTimeout(saveTimer)
    saveTimer = setTimeout(() => { saveTimer = null; doSave() }, 2000)
  }

  async function doSave(retryCount = 0): Promise<void> {
    if (pendingItems.size === 0) return
    const items = [...pendingItems.values()]
    pendingItems.clear()

    try {
      await api.put(`/api/workpapers/${wpId.value}/checklist-responses`, { items })
      lastSavedAt.value = new Date()
      saveError.value = false
    } catch {
      if (retryCount < 3) {
        // Re-queue items and retry with exponential backoff
        for (const item of items) pendingItems.set(item.item_id, item)
        const delay = Math.pow(2, retryCount) * 1000 // 1s, 2s, 4s
        setTimeout(() => doSave(retryCount + 1), delay)
        return
      }
      saveError.value = true
      ElMessage.warning('保存失败，请检查网络后重试')
    }
  }

  async function flushPendingSave(): Promise<void> {
    if (saveTimer) {
      clearTimeout(saveTimer)
      saveTimer = null
    }
    await doSave()
  }

  // ─── Calculations (Task 2.3) ───

  function getAuditedAmount(rowId: string): number {
    const unadjusted = safeFloat(getField(`a51-audit-${rowId}.unadjusted`))
    const adjustment = safeFloat(getField(`a51-audit-${rowId}.adjustment`))
    return unadjusted + adjustment
  }

  function getAuditRow6Amount(): number {
    // row6 = row1 - row2 - row3 + row4 + row5
    return getAuditedAmount('1')
      - getAuditedAmount('2')
      - getAuditedAmount('3')
      + getAuditedAmount('4')
      + getAuditedAmount('5')
  }

  function getAuditRow8Amount(): number {
    // row8 = row6 - row7
    return getAuditRow6Amount() - getAuditedAmount('7')
  }

  function getReconcileTotal(groupId: string): number {
    const group = RECONCILE_GROUPS.find(g => g.id === groupId)
    if (!group) return 0
    return group.items.reduce((sum, item) => {
      return sum + safeFloat(getField(`a51-reconcile-${groupId}-${item.id}.amount`))
    }, 0)
  }

  function getReconcileDiff(groupId: string): number {
    const total = getReconcileTotal(groupId)
    const reportAmount = safeFloat(getField(`a51-reconcile-${groupId}.report_amount`))
    return total - reportAmount
  }

  function getCheckDiff(tab: string, rowIdx: string): number {
    const estimated = safeFloat(getField(`a51-${tab}-${rowIdx}.estimated`))
    const reported = safeFloat(getField(`a51-${tab}-${rowIdx}.reported`))
    return estimated - reported
  }

  function getCheck5Balance(): number {
    // SUM(行1~7的测算数) - 受限部分(行9)的测算数
    let sum = 0
    for (let i = 1; i <= 7; i++) {
      sum += safeFloat(getField(`a51-check5-${i}.estimated`))
    }
    const restricted = safeFloat(getField(`a51-check5-9.estimated`))
    return sum - restricted
  }

  function getOtherCFTotal(groupId: string, side: 'receive' | 'pay'): number {
    let sum = 0
    for (let i = 1; i <= 10; i++) {
      sum += safeFloat(getField(`a51-other-${groupId}-${side}-${i}.amount`))
    }
    return sum
  }

  const programProgress = computed<{ filled: number; total: number }>(() => {
    let filled = 0
    for (const step of PROGRAM_STEPS) {
      const conclusion = getField(`a51-program-${step.id}.conclusion`)
      if (conclusion === 'Y' || conclusion === 'N' || conclusion === 'NA') {
        filled++
      }
    }
    return { filled, total: 21 }
  })

  return {
    responses,
    loading,
    lastSavedAt,
    saveError,
    loadData,
    refreshData,
    getField,
    setField,
    getAuditedAmount,
    getAuditRow6Amount,
    getAuditRow8Amount,
    getReconcileTotal,
    getReconcileDiff,
    getCheckDiff,
    getCheck5Balance,
    getOtherCFTotal,
    programProgress,
    flushPendingSave,
  }
}
