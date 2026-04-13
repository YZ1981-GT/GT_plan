<template>
  <div class="gt-penetration">
    <!-- 面包屑导航 -->
    <div class="gt-breadcrumb">
      <span
        v-for="(crumb, i) in breadcrumbs"
        :key="i"
        class="gt-crumb"
        :class="{ 'gt-crumb--active': i === breadcrumbs.length - 1 }"
        @click="navigateTo(i)"
      >
        {{ crumb.label }}
        <span v-if="i < breadcrumbs.length - 1" class="gt-crumb-sep">/</span>
      </span>
    </div>

    <!-- 筛选栏 -->
    <div class="gt-filter-row">
      <el-input
        v-if="currentLevel === 'balance'"
        v-model="searchKeyword"
        placeholder="搜索科目编号或名称..."
        size="small"
        clearable
        :prefix-icon="Search"
        style="width: 200px"
      />
      <el-date-picker
        v-if="currentLevel === 'ledger'"
        v-model="dateRange"
        type="daterange"
        size="small"
        start-placeholder="开始日期"
        end-placeholder="结束日期"
        value-format="YYYY-MM-DD"
        style="width: 260px"
        @change="loadLedger"
      />
      <div class="gt-filter-spacer" />
      <el-tag type="info" size="small">{{ levelLabel }}</el-tag>
      <el-button size="small" @click="refresh" :loading="loading">刷新</el-button>
    </div>

    <!-- 第一层：科目余额表 -->
    <template v-if="currentLevel === 'balance'">
      <VirtualScrollTable
        :data="filteredBalance"
        :columns="balanceCols"
        :height="tableHeight"
        @row-click="drillToLedger"
      >
        <template #account_code="{ row }">
          <span class="gt-link">{{ row.account_code }}</span>
        </template>
        <template #closing_balance="{ row }">
          <span class="gt-link">{{ fmtAmt(row.closing_balance) }}</span>
        </template>
      </VirtualScrollTable>
    </template>

    <!-- 第二层：序时账明细 -->
    <template v-if="currentLevel === 'ledger'">
      <VirtualScrollTable
        :data="ledgerItems"
        :columns="ledgerCols"
        :height="tableHeight"
        @row-click="drillToVoucher"
      >
        <template #voucher_no="{ row }">
          <span class="gt-link">{{ row.voucher_no }}</span>
        </template>
      </VirtualScrollTable>
      <div class="gt-pagination" v-if="ledgerTotal > ledgerPageSize">
        <el-pagination
          v-model:current-page="ledgerPage"
          :page-size="ledgerPageSize"
          :total="ledgerTotal"
          layout="prev, pager, next, total"
          size="small"
          @current-change="loadLedger"
        />
      </div>
    </template>

    <!-- 第三层：凭证分录 -->
    <template v-if="currentLevel === 'voucher'">
      <VirtualScrollTable
        :data="voucherItems"
        :columns="voucherCols"
        :height="tableHeight"
      />
    </template>

    <!-- 辅助余额 -->
    <template v-if="currentLevel === 'aux_balance'">
      <VirtualScrollTable
        :data="auxBalanceItems"
        :columns="auxBalanceCols"
        :height="tableHeight"
        @row-click="drillToAuxLedger"
      >
        <template #aux_name="{ row }">
          <span class="gt-link">{{ row.aux_name }}</span>
        </template>
      </VirtualScrollTable>
    </template>

    <!-- 辅助明细 -->
    <template v-if="currentLevel === 'aux_ledger'">
      <VirtualScrollTable
        :data="auxLedgerItems"
        :columns="auxLedgerCols"
        :height="tableHeight"
      />
      <div class="gt-pagination" v-if="auxLedgerTotal > 100">
        <el-pagination
          v-model:current-page="auxLedgerPage"
          :page-size="100"
          :total="auxLedgerTotal"
          layout="prev, pager, next, total"
          size="small"
          @current-change="loadAuxLedger"
        />
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { Search } from '@element-plus/icons-vue'
import VirtualScrollTable from '@/components/common/VirtualScrollTable.vue'
import type { VTColumn } from '@/components/common/VirtualScrollTable.vue'
import http from '@/utils/http'

const route = useRoute()
const projectId = computed(() => route.params.projectId as string)
const year = computed(() => Number(route.query.year) || new Date().getFullYear())

const loading = ref(false)
const tableHeight = ref(Math.max(400, window.innerHeight - 220))

// ── 导航状态 ──
type Level = 'balance' | 'ledger' | 'voucher' | 'aux_balance' | 'aux_ledger'
const currentLevel = ref<Level>('balance')
const currentAccount = ref('')
const currentVoucher = ref('')
const currentAuxType = ref('')
const currentAuxCode = ref('')
const searchKeyword = ref('')
const dateRange = ref<string[] | null>(null)

interface Crumb { label: string; level: Level; account?: string; voucher?: string; auxType?: string; auxCode?: string }
const breadcrumbs = ref<Crumb[]>([{ label: '科目余额表', level: 'balance' }])

const levelLabel = computed(() => {
  const m: Record<Level, string> = {
    balance: '科目余额表', ledger: '序时账', voucher: '凭证分录',
    aux_balance: '辅助余额', aux_ledger: '辅助明细',
  }
  return m[currentLevel.value]
})

// ── 数据 ──
const balanceData = ref<any[]>([])
const ledgerItems = ref<any[]>([])
const ledgerTotal = ref(0)
const ledgerPage = ref(1)
const ledgerPageSize = 200
const voucherItems = ref<any[]>([])
const auxBalanceItems = ref<any[]>([])
const auxLedgerItems = ref<any[]>([])
const auxLedgerTotal = ref(0)
const auxLedgerPage = ref(1)

const filteredBalance = computed(() => {
  if (!searchKeyword.value) return balanceData.value
  const kw = searchKeyword.value.toLowerCase()
  return balanceData.value.filter(r =>
    (r.account_code || '').toLowerCase().includes(kw) ||
    (r.account_name || '').toLowerCase().includes(kw)
  )
})

// ── 列定义 ──
const balanceCols: VTColumn[] = [
  { key: 'account_code', label: '科目编号', width: '120px' },
  { key: 'account_name', label: '科目名称', width: '200px' },
  { key: 'opening_balance', label: '期初余额', width: '140px', align: 'right' },
  { key: 'debit_amount', label: '借方发生额', width: '140px', align: 'right' },
  { key: 'credit_amount', label: '贷方发生额', width: '140px', align: 'right' },
  { key: 'closing_balance', label: '期末余额', width: '140px', align: 'right' },
]

const ledgerCols: VTColumn[] = [
  { key: 'voucher_date', label: '日期', width: '100px' },
  { key: 'voucher_no', label: '凭证号', width: '120px' },
  { key: 'summary', label: '摘要' },
  { key: 'debit_amount', label: '借方', width: '130px', align: 'right' },
  { key: 'credit_amount', label: '贷方', width: '130px', align: 'right' },
  { key: 'counterpart_account', label: '对方科目', width: '120px' },
]

const voucherCols: VTColumn[] = [
  { key: 'account_code', label: '科目编号', width: '120px' },
  { key: 'account_name', label: '科目名称', width: '200px' },
  { key: 'debit_amount', label: '借方', width: '140px', align: 'right' },
  { key: 'credit_amount', label: '贷方', width: '140px', align: 'right' },
  { key: 'summary', label: '摘要' },
]

const auxBalanceCols: VTColumn[] = [
  { key: 'aux_type', label: '辅助类型', width: '100px' },
  { key: 'aux_code', label: '编号', width: '120px' },
  { key: 'aux_name', label: '名称', width: '200px' },
  { key: 'opening_balance', label: '期初', width: '130px', align: 'right' },
  { key: 'debit_amount', label: '借方', width: '130px', align: 'right' },
  { key: 'credit_amount', label: '贷方', width: '130px', align: 'right' },
  { key: 'closing_balance', label: '期末', width: '130px', align: 'right' },
]

const auxLedgerCols: VTColumn[] = [
  { key: 'voucher_date', label: '日期', width: '100px' },
  { key: 'voucher_no', label: '凭证号', width: '120px' },
  { key: 'aux_name', label: '辅助名称', width: '160px' },
  { key: 'debit_amount', label: '借方', width: '130px', align: 'right' },
  { key: 'credit_amount', label: '贷方', width: '130px', align: 'right' },
  { key: 'summary', label: '摘要' },
]

// ── 加载数据 ──
async function loadBalance() {
  loading.value = true
  try {
    const { data } = await http.get(`/api/projects/${projectId.value}/ledger/balance`, {
      params: { year: year.value },
    })
    balanceData.value = data.data ?? data ?? []
  } catch { balanceData.value = [] }
  finally { loading.value = false }
}

async function loadLedger() {
  loading.value = true
  try {
    const params: any = { year: year.value, page: ledgerPage.value, page_size: ledgerPageSize }
    if (dateRange.value?.length === 2) {
      params.date_from = dateRange.value[0]
      params.date_to = dateRange.value[1]
    }
    const { data } = await http.get(
      `/api/projects/${projectId.value}/ledger/entries/${currentAccount.value}`, { params }
    )
    const result = data.data ?? data
    ledgerItems.value = result.items ?? []
    ledgerTotal.value = result.total ?? 0
  } catch { ledgerItems.value = [] }
  finally { loading.value = false }
}

async function loadVoucher() {
  loading.value = true
  try {
    const { data } = await http.get(
      `/api/projects/${projectId.value}/ledger/voucher/${encodeURIComponent(currentVoucher.value)}`,
      { params: { year: year.value } }
    )
    voucherItems.value = data.data ?? data ?? []
  } catch { voucherItems.value = [] }
  finally { loading.value = false }
}

async function loadAuxBalance() {
  loading.value = true
  try {
    const { data } = await http.get(
      `/api/projects/${projectId.value}/ledger/aux-balance/${currentAccount.value}`,
      { params: { year: year.value } }
    )
    auxBalanceItems.value = data.data ?? data ?? []
  } catch { auxBalanceItems.value = [] }
  finally { loading.value = false }
}

async function loadAuxLedger() {
  loading.value = true
  try {
    const { data } = await http.get(
      `/api/projects/${projectId.value}/ledger/aux-entries/${currentAccount.value}`,
      { params: { year: year.value, aux_type: currentAuxType.value, aux_code: currentAuxCode.value, page: auxLedgerPage.value, page_size: 100 } }
    )
    const result = data.data ?? data
    auxLedgerItems.value = result.items ?? []
    auxLedgerTotal.value = result.total ?? 0
  } catch { auxLedgerItems.value = [] }
  finally { loading.value = false }
}

// ── 穿透导航 ──
function drillToLedger(row: any) {
  currentAccount.value = row.account_code
  currentLevel.value = 'ledger'
  ledgerPage.value = 1
  dateRange.value = null
  breadcrumbs.value = [
    { label: '科目余额表', level: 'balance' },
    { label: `${row.account_code} ${row.account_name || ''}`, level: 'ledger', account: row.account_code },
  ]
  loadLedger()
}

function drillToVoucher(row: any) {
  currentVoucher.value = row.voucher_no
  currentLevel.value = 'voucher'
  breadcrumbs.value.push({
    label: `凭证 ${row.voucher_no}`, level: 'voucher', voucher: row.voucher_no,
  })
  loadVoucher()
}

function drillToAuxBalance(accountCode: string) {
  currentAccount.value = accountCode
  currentLevel.value = 'aux_balance'
  breadcrumbs.value = [
    { label: '科目余额表', level: 'balance' },
    { label: `${accountCode} 辅助余额`, level: 'aux_balance', account: accountCode },
  ]
  loadAuxBalance()
}

function drillToAuxLedger(row: any) {
  currentAuxType.value = row.aux_type
  currentAuxCode.value = row.aux_code
  currentLevel.value = 'aux_ledger'
  auxLedgerPage.value = 1
  breadcrumbs.value.push({
    label: `${row.aux_name || row.aux_code}`, level: 'aux_ledger',
    auxType: row.aux_type, auxCode: row.aux_code,
  })
  loadAuxLedger()
}

function navigateTo(index: number) {
  const crumb = breadcrumbs.value[index]
  breadcrumbs.value = breadcrumbs.value.slice(0, index + 1)
  currentLevel.value = crumb.level
  if (crumb.level === 'balance') loadBalance()
  else if (crumb.level === 'ledger') { currentAccount.value = crumb.account || ''; loadLedger() }
  else if (crumb.level === 'aux_balance') { currentAccount.value = crumb.account || ''; loadAuxBalance() }
}

function refresh() {
  if (currentLevel.value === 'balance') loadBalance()
  else if (currentLevel.value === 'ledger') loadLedger()
  else if (currentLevel.value === 'voucher') loadVoucher()
  else if (currentLevel.value === 'aux_balance') loadAuxBalance()
  else if (currentLevel.value === 'aux_ledger') loadAuxLedger()
}

function fmtAmt(v: any): string {
  const n = Number(v)
  if (!n) return '-'
  return n.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

onMounted(loadBalance)
</script>

<style scoped>
.gt-penetration { padding: var(--gt-space-4); height: 100%; display: flex; flex-direction: column; }

.gt-breadcrumb {
  display: flex; align-items: center; gap: 2px;
  margin-bottom: var(--gt-space-3); font-size: var(--gt-font-size-sm);
}
.gt-crumb {
  cursor: pointer; color: var(--gt-color-primary); padding: 2px 4px;
  border-radius: var(--gt-radius-sm); transition: background var(--gt-transition-fast);
}
.gt-crumb:hover { background: var(--gt-color-primary-bg); }
.gt-crumb--active { color: var(--gt-color-text); font-weight: 600; cursor: default; }
.gt-crumb--active:hover { background: transparent; }
.gt-crumb-sep { color: var(--gt-color-text-tertiary); margin: 0 2px; }

.gt-filter-row {
  display: flex; align-items: center; gap: var(--gt-space-2);
  margin-bottom: var(--gt-space-3); flex-shrink: 0;
}
.gt-filter-spacer { flex: 1; }

.gt-link { color: var(--gt-color-primary); cursor: pointer; }
.gt-link:hover { text-decoration: underline; }

.gt-pagination { margin-top: var(--gt-space-3); display: flex; justify-content: flex-end; }
</style>
