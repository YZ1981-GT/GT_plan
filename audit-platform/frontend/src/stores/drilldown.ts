import { defineStore } from 'pinia'
import { ref } from 'vue'
import http from '@/utils/http'

export interface BalanceRow {
  account_code: string
  account_name: string | null
  opening_balance: number | null
  debit_amount: number | null
  credit_amount: number | null
  closing_balance: number | null
  has_aux: boolean
}

export interface LedgerRow {
  id: string
  voucher_date: string
  voucher_no: string
  account_code: string
  account_name: string | null
  debit_amount: number | null
  credit_amount: number | null
  counterpart_account: string | null
  summary: string | null
  preparer: string | null
}

export interface AuxBalanceRow {
  aux_type: string
  aux_code: string | null
  aux_name: string | null
  opening_balance: number | null
  debit_amount: number | null
  credit_amount: number | null
  closing_balance: number | null
}

export interface AuxLedgerRow {
  id: string
  voucher_date: string | null
  voucher_no: string | null
  account_code: string
  aux_type: string | null
  aux_code: string | null
  aux_name: string | null
  debit_amount: number | null
  credit_amount: number | null
  summary: string | null
  preparer: string | null
}

export type DrilldownLevel = 'balance' | 'ledger' | 'aux_balance' | 'aux_ledger'

export interface BreadcrumbItem {
  level: DrilldownLevel
  label: string
  accountCode?: string
  auxType?: string
  auxCode?: string
  auxName?: string
}

export interface BalanceFilter {
  category: string | null
  level: number | null
  keyword: string
  page: number
  pageSize: number
}

export interface LedgerFilter {
  dateFrom: string | null
  dateTo: string | null
  amountMin: number | null
  amountMax: number | null
  voucherNo: string
  summaryKeyword: string
  counterpartAccount: string
  page: number
  pageSize: number
}

export const useDrilldownStore = defineStore('drilldown', () => {
  const projectId = ref<string>('')
  const year = ref<number>(new Date().getFullYear())

  // 当前层级
  const currentLevel = ref<DrilldownLevel>('balance')
  const breadcrumbs = ref<BreadcrumbItem[]>([{ level: 'balance', label: '科目余额表' }])

  // 余额表
  const balanceData = ref<BalanceRow[]>([])
  const balanceTotal = ref(0)
  const balanceFilter = ref<BalanceFilter>({
    category: null, level: null, keyword: '', page: 1, pageSize: 50,
  })
  const balanceScrollTop = ref(0)

  // 序时账
  const ledgerData = ref<LedgerRow[]>([])
  const ledgerTotal = ref(0)
  const ledgerFilter = ref<LedgerFilter>({
    dateFrom: null, dateTo: null, amountMin: null, amountMax: null,
    voucherNo: '', summaryKeyword: '', counterpartAccount: '',
    page: 1, pageSize: 50,
  })
  const selectedAccountCode = ref('')
  const selectedAccountName = ref('')

  // 辅助余额
  const auxBalanceData = ref<AuxBalanceRow[]>([])

  // 辅助明细
  const auxLedgerData = ref<AuxLedgerRow[]>([])
  const auxLedgerTotal = ref(0)
  const auxLedgerPage = ref(1)
  const selectedAuxType = ref('')
  const selectedAuxCode = ref('')
  const selectedAuxName = ref('')

  const loading = ref(false)

  function setProject(pid: string, y: number) {
    projectId.value = pid
    year.value = y
  }

  async function fetchBalance() {
    loading.value = true
    try {
      const f = balanceFilter.value
      const params: Record<string, unknown> = {
        year: year.value, page: f.page, page_size: f.pageSize,
      }
      if (f.category) params.category = f.category
      if (f.level != null) params.level = f.level
      if (f.keyword) params.keyword = f.keyword

      const { data } = await http.get(
        `/api/projects/${projectId.value}/drilldown/balance`, { params },
      )
      const res = data
      balanceData.value = res.items
      balanceTotal.value = res.total
    } finally {
      loading.value = false
    }
  }

  async function drillToLedger(accountCode: string, accountName: string) {
    selectedAccountCode.value = accountCode
    selectedAccountName.value = accountName
    ledgerFilter.value = {
      dateFrom: null, dateTo: null, amountMin: null, amountMax: null,
      voucherNo: '', summaryKeyword: '', counterpartAccount: '',
      page: 1, pageSize: 50,
    }
    currentLevel.value = 'ledger'
    breadcrumbs.value = [
      { level: 'balance', label: '科目余额表' },
      { level: 'ledger', label: `${accountCode} ${accountName || ''}`, accountCode },
    ]
    await fetchLedger()
  }

  async function fetchLedger() {
    loading.value = true
    try {
      const f = ledgerFilter.value
      const params: Record<string, unknown> = {
        year: year.value, page: f.page, page_size: f.pageSize,
      }
      if (f.dateFrom) params.date_from = f.dateFrom
      if (f.dateTo) params.date_to = f.dateTo
      if (f.amountMin != null) params.amount_min = f.amountMin
      if (f.amountMax != null) params.amount_max = f.amountMax
      if (f.voucherNo) params.voucher_no = f.voucherNo
      if (f.summaryKeyword) params.summary_keyword = f.summaryKeyword
      if (f.counterpartAccount) params.counterpart_account = f.counterpartAccount

      const { data } = await http.get(
        `/api/projects/${projectId.value}/drilldown/ledger/${selectedAccountCode.value}`,
        { params },
      )
      const res = data
      ledgerData.value = res.items
      ledgerTotal.value = res.total
    } finally {
      loading.value = false
    }
  }

  async function drillToAuxBalance(accountCode: string, accountName: string) {
    selectedAccountCode.value = accountCode
    selectedAccountName.value = accountName
    currentLevel.value = 'aux_balance'
    breadcrumbs.value = [
      { level: 'balance', label: '科目余额表' },
      { level: 'aux_balance', label: `${accountCode} ${accountName || ''} (辅助)`, accountCode },
    ]
    await fetchAuxBalance()
  }

  async function fetchAuxBalance() {
    loading.value = true
    try {
      const { data } = await http.get(
        `/api/projects/${projectId.value}/drilldown/aux-balance/${selectedAccountCode.value}`,
        { params: { year: year.value } },
      )
      auxBalanceData.value = data
    } finally {
      loading.value = false
    }
  }

  async function drillToAuxLedger(auxType: string, auxCode: string, auxName: string) {
    selectedAuxType.value = auxType
    selectedAuxCode.value = auxCode
    selectedAuxName.value = auxName
    auxLedgerPage.value = 1
    currentLevel.value = 'aux_ledger'
    breadcrumbs.value = [
      { level: 'balance', label: '科目余额表' },
      { level: 'aux_balance', label: `${selectedAccountCode.value} (辅助)`, accountCode: selectedAccountCode.value },
      { level: 'aux_ledger', label: `${auxName || auxCode}`, auxType, auxCode, auxName },
    ]
    await fetchAuxLedger()
  }

  async function fetchAuxLedger() {
    loading.value = true
    try {
      const { data } = await http.get(
        `/api/projects/${projectId.value}/drilldown/aux-ledger/${selectedAccountCode.value}`,
        {
          params: {
            year: year.value,
            aux_type: selectedAuxType.value || undefined,
            aux_code: selectedAuxCode.value || undefined,
            page: auxLedgerPage.value,
            page_size: 50,
          },
        },
      )
      const res = data
      auxLedgerData.value = res.items
      auxLedgerTotal.value = res.total
    } finally {
      loading.value = false
    }
  }

  function navigateTo(level: DrilldownLevel) {
    const idx = breadcrumbs.value.findIndex((b) => b.level === level)
    if (idx >= 0) {
      breadcrumbs.value = breadcrumbs.value.slice(0, idx + 1)
      currentLevel.value = level
    }
  }

  function reset() {
    currentLevel.value = 'balance'
    breadcrumbs.value = [{ level: 'balance', label: '科目余额表' }]
    balanceData.value = []
    ledgerData.value = []
    auxBalanceData.value = []
    auxLedgerData.value = []
  }

  return {
    projectId, year, currentLevel, breadcrumbs, loading,
    balanceData, balanceTotal, balanceFilter, balanceScrollTop,
    ledgerData, ledgerTotal, ledgerFilter,
    selectedAccountCode, selectedAccountName,
    auxBalanceData,
    auxLedgerData, auxLedgerTotal, auxLedgerPage,
    selectedAuxType, selectedAuxCode, selectedAuxName,
    setProject, fetchBalance, drillToLedger, fetchLedger,
    drillToAuxBalance, fetchAuxBalance,
    drillToAuxLedger, fetchAuxLedger,
    navigateTo, reset,
  }
})
