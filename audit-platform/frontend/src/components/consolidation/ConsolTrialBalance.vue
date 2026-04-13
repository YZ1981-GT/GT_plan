<template>
  <div class="gt-consol-trial-balance">
    <!-- 工具栏 -->
    <div class="toolbar">
      <div class="toolbar-left">
        <el-select
          v-model="filterCompany"
          placeholder="筛选公司"
          clearable
          multiple
          collapse-tags
          collapse-tags-tooltip
          style="width: 200px"
          @change="handleFilterChange"
        >
          <el-option
            v-for="c in companyOptions"
            :key="c.code"
            :label="c.name"
            :value="c.code"
          />
        </el-select>
        <el-select
          v-model="filterCategory"
          placeholder="筛选类别"
          clearable
          style="width: 140px"
          @change="handleFilterChange"
        >
          <el-option label="资产类" value="asset" />
          <el-option label="负债类" value="liability" />
          <el-option label="权益类" value="equity" />
          <el-option label="损益类" value="pl" />
        </el-select>
      </div>
      <div class="toolbar-right">
        <el-button :loading="loading" @click="onRefresh" plain>
          <el-icon><Refresh /></el-icon> 刷新
        </el-button>
        <el-button :loading="exportLoading" @click="onExportExcel" plain>
          <el-icon><Download /></el-icon> 导出 Excel
        </el-button>
        <el-button @click="onCheckBalance" plain>
          <el-icon><Check /></el-icon> 借贷平衡校验
        </el-button>
      </div>
    </div>

    <!-- 借贷平衡警告 -->
    <el-alert
      v-if="balanceError"
      type="error"
      :title="balanceError"
      show-icon
      :closable="false"
      style="margin-bottom: 8px"
    />
    <el-alert
      v-else-if="balanceChecked && !balanceError"
      type="success"
      title="借贷平衡校验通过"
      show-icon
      :closable="false"
      style="margin-bottom: 8px"
    />

    <!-- 合并试算表 -->
    <el-table
      :data="displayRows"
      v-loading="loading"
      border
      stripe
      size="small"
      :max-height="tableMaxHeight"
      row-key="id"
      :expand-row-keys="expandedRows"
      @expand-change="onExpandChange"
      :header-cell-style="{ background: 'var(--gt-color-primary)', color: '#fff', fontWeight: '600' }"
      class="consol-table"
    >
      <!-- 固定列：科目编码 & 科目名称 -->
      <el-table-column type="expand" width="40" />
      <el-table-column prop="account_code" label="科目编码" width="120" fixed />
      <el-table-column prop="account_name" label="科目名称" min-width="180" fixed />

      <!-- 各公司审定数列（动态渲染，可展开查看明细） -->
      <el-table-column
        v-for="company in displayCompanies"
        :key="company.code"
        :label="company.name"
        align="center"
        width="160"
      >
        <template #default="{ row }">
          <div
            class="company-amount"
            :class="{ clickable: row.company_amounts?.[company.code] }"
            @click="row.company_amounts?.[company.code] && toggleDetail(row, company.code)"
          >
            <template v-if="row.company_amounts?.[company.code]">
              <span class="debit" v-if="(row.company_amounts[company.code].debit ?? 0) > 0">
                {{ formatNum(row.company_amounts[company.code].debit) }}
              </span>
              <span class="credit" v-if="(row.company_amounts[company.code].credit ?? 0) > 0">
                {{ formatNum(row.company_amounts[company.code].credit) }}
              </span>
            </template>
            <span v-else class="zero">—</span>
          </div>
        </template>
      </el-table-column>

      <!-- 汇总数列 -->
      <el-table-column label="汇总数" align="center" width="140">
        <template #default="{ row }">
          <span class="debit" v-if="row.individual_sum > 0">{{ formatNum(row.individual_sum) }}</span>
          <span class="credit" v-else-if="row.individual_sum < 0">{{ formatNum(Math.abs(row.individual_sum)) }}</span>
          <span v-else class="zero">—</span>
        </template>
      </el-table-column>

      <!-- 合并调整列 -->
      <el-table-column label="合并调整" align="center" width="140">
        <template #default="{ row }">
          <span class="debit" v-if="row.consol_adjustment > 0">{{ formatNum(row.consol_adjustment) }}</span>
          <span class="credit" v-else-if="row.consol_adjustment < 0">{{ formatNum(Math.abs(row.consol_adjustment)) }}</span>
          <span v-else class="zero">—</span>
        </template>
      </el-table-column>

      <!-- 合并抵消列（可点击查看明细） -->
      <el-table-column label="合并抵消" align="center" width="140">
        <template #default="{ row }">
          <span
            class="elimination-cell clickable"
            :class="{ zero: row.consol_elimination === 0 }"
            @click="onEliminationClick(row)"
          >
            <span class="debit" v-if="row.consol_elimination > 0">{{ formatNum(row.consol_elimination) }}</span>
            <span class="credit" v-else-if="row.consol_elimination < 0">{{ formatNum(Math.abs(row.consol_elimination)) }}</span>
            <span v-else class="zero">—</span>
          </span>
        </template>
      </el-table-column>

      <!-- 合并数列 -->
      <el-table-column label="合并数" align="center" width="140">
        <template #default="{ row }">
          <span class="bold debit" v-if="row.consol_amount > 0">{{ formatNum(row.consol_amount) }}</span>
          <span class="bold credit" v-else-if="row.consol_amount < 0">{{ formatNum(Math.abs(row.consol_amount)) }}</span>
          <span v-else class="zero">—</span>
        </template>
      </el-table-column>

      <!-- 展开行：抵消分录明细 -->
      <template #expanded-row="{ row }">
        <div class="expanded-detail">
          <div class="detail-title">抵消分录明细 - {{ row.account_code }} {{ row.account_name }}</div>
          <el-table
            v-if="row.elimination_details?.length"
            :data="row.elimination_details"
            border
            size="small"
            max-height="200"
          >
            <el-table-column prop="entry_no" label="分录编号" width="120" />
            <el-table-column prop="entry_type" label="类型" width="120">
              <template #default="{ row: d }">
                {{ entryTypeLabel(d.entry_type) }}
              </template>
            </el-table-column>
            <el-table-column label="借方" align="right" width="140">
              <template #default="{ row: d }">
                <span class="debit" v-if="d.debit">{{ formatNum(d.debit) }}</span>
                <span v-else class="zero">—</span>
              </template>
            </el-table-column>
            <el-table-column label="贷方" align="right" width="140">
              <template #default="{ row: d }">
                <span class="credit" v-if="d.credit">{{ formatNum(d.credit) }}</span>
                <span v-else class="zero">—</span>
              </template>
            </el-table-column>
          </el-table>
          <div v-else class="no-detail">暂无抵消分录明细</div>
        </div>
      </template>
    </el-table>

    <!-- 合计行 -->
    <div class="total-row" v-if="displayRows.length">
      <span class="total-label">合计</span>
      <span
        v-for="company in displayCompanies"
        :key="company.code"
        class="total-company"
        :class="{ zero: totalCompanyAmount(company.code) === 0 }"
      >
        <span class="debit" v-if="totalCompanyAmount(company.code) > 0">
          {{ formatNum(totalCompanyAmount(company.code)) }}
        </span>
        <span class="credit" v-else-if="totalCompanyAmount(company.code) < 0">
          {{ formatNum(Math.abs(totalCompanyAmount(company.code))) }}
        </span>
        <span v-else class="zero">—</span>
      </span>
      <span class="total-cell">
        <span class="debit bold" v-if="totalIndividualSum > 0">{{ formatNum(totalIndividualSum) }}</span>
        <span class="credit bold" v-else-if="totalIndividualSum < 0">{{ formatNum(Math.abs(totalIndividualSum)) }}</span>
        <span v-else class="zero">—</span>
      </span>
      <span class="total-cell">
        <span class="debit bold" v-if="totalAdjustment > 0">{{ formatNum(totalAdjustment) }}</span>
        <span class="credit bold" v-else-if="totalAdjustment < 0">{{ formatNum(Math.abs(totalAdjustment)) }}</span>
        <span v-else class="zero">—</span>
      </span>
      <span class="total-cell">
        <span class="debit bold" v-if="totalElimination > 0">{{ formatNum(totalElimination) }}</span>
        <span class="credit bold" v-else-if="totalElimination < 0">{{ formatNum(Math.abs(totalElimination)) }}</span>
        <span v-else class="zero">—</span>
      </span>
      <span class="total-cell">
        <span class="debit bold" v-if="totalConsolAmount > 0">{{ formatNum(totalConsolAmount) }}</span>
        <span class="credit bold" v-else-if="totalConsolAmount < 0">{{ formatNum(Math.abs(totalConsolAmount)) }}</span>
        <span v-else class="zero">—</span>
      </span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Refresh, Download, Check } from '@element-plus/icons-vue'
import {
  getConsolTrialBalanceFull,
  exportConsolTrialExcel,
  type ConsolTrialBalanceEntry,
  type ConsolTrialBalanceFilter,
  type EliminationEntryType,
} from '@/services/consolidationApi'

// ─── Props & Emits ─────────────────────────────────────────────────────────
const props = defineProps<{
  projectId: string
  period: number
}>()

const emit = defineEmits<{
  'entry-click': [entry: ConsolTrialBalanceEntry]
}>()

// ─── State ───────────────────────────────────────────────────────────────────
const loading = ref(false)
const exportLoading = ref(false)
const balanceChecked = ref(false)

const allRows = ref<ConsolTrialBalanceEntry[]>([])
const expandedRows = ref<string[]>([])
const expandedDetailRows = ref<Set<string>>(new Set())

const filterCompany = ref<string[]>([])
const filterCategory = ref<string>('')

// ─── Computed ────────────────────────────────────────────────────────────────
const tableMaxHeight = computed(() => {
  const vh = window.innerHeight
  return Math.max(400, vh - 320)
})

// 所有公司列表（从数据中提取）
const companyOptions = computed(() => {
  const codeSet = new Set<string>()
  const nameMap: Record<string, string> = {}
  allRows.value.forEach(row => {
    Object.keys(row.company_amounts || {}).forEach(code => {
      codeSet.add(code)
      nameMap[code] = nameMap[code] || code
    })
  })
  return Array.from(codeSet).map(code => ({ code, name: nameMap[code] || code }))
})

const displayCompanies = computed(() => {
  if (!filterCompany.value.length) return companyOptions.value
  return companyOptions.value.filter(c => filterCompany.value.includes(c.code))
})

const displayRows = computed(() => {
  let rows = allRows.value
  if (filterCategory.value) {
    rows = rows.filter(r => r.account_category === filterCategory.value)
  }
  return rows
})

// 分组汇总
const groupTotals = computed(() => {
  const groups: Record<string, { debit: number; credit: number }> = {}
  displayRows.value.forEach(row => {
    const cat = row.account_category || 'other'
    if (!groups[cat]) groups[cat] = { debit: 0, credit: 0 }
    if (row.consol_amount > 0) groups[cat].debit += row.consol_amount
    else if (row.consol_amount < 0) groups[cat].credit += Math.abs(row.consol_amount)
  })
  return groups
})

// 合计行
const totalIndividualSum = computed(() =>
  displayRows.value.reduce((sum, r) => sum + r.individual_sum, 0)
)
const totalAdjustment = computed(() =>
  displayRows.value.reduce((sum, r) => sum + r.consol_adjustment, 0)
)
const totalElimination = computed(() =>
  displayRows.value.reduce((sum, r) => sum + r.consol_elimination, 0)
)
const totalConsolAmount = computed(() =>
  displayRows.value.reduce((sum, r) => sum + r.consol_amount, 0)
)

function totalCompanyAmount(companyCode: string) {
  return displayRows.value.reduce((sum, r) => {
    const amt = r.company_amounts?.[companyCode]
    if (!amt) return sum
    return sum + (amt.debit ?? 0) - (amt.credit ?? 0)
  }, 0)
}

const balanceError = computed(() => {
  const debitTotal = totalConsolAmount.value > 0 ? totalConsolAmount.value : 0
  const creditTotal = totalConsolAmount.value < 0 ? Math.abs(totalConsolAmount.value) : 0
  const diff = Math.abs(debitTotal - creditTotal)
  if (diff > 0.01) {
    return `借贷不平衡！借方合计: ${formatNum(debitTotal)}，贷方合计: ${formatNum(creditTotal)}，差额: ${formatNum(diff)}`
  }
  return null
})

// ─── Methods ─────────────────────────────────────────────────────────────────
function formatNum(v: number) {
  if (!v && v !== 0) return '—'
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function entryTypeLabel(type: string) {
  const map: Record<string, string> = {
    investment: '投资类',
    ar_ap: '往来类',
    transaction: '交易类',
    internal_income: '内部收入类',
    other: '其他',
  }
  return map[type] || type
}

function toggleDetail(row: ConsolTrialBalanceEntry, companyCode: string) {
  const key = `${row.id}-${companyCode}`
  if (expandedDetailRows.value.has(key)) {
    expandedDetailRows.value.delete(key)
  } else {
    expandedDetailRows.value.add(key)
  }
}

function onExpandChange(row: ConsolTrialBalanceEntry) {
  // handled by el-table expand
}

async function loadData() {
  loading.value = true
  balanceChecked.value = false
  try {
    const filter: ConsolTrialBalanceFilter = { year: props.period }
    if (filterCategory.value) filter.account_category = filterCategory.value
    if (filterCompany.value.length) filter.company_codes = filterCompany.value
    allRows.value = await getConsolTrialBalanceFull(props.projectId, filter)
  } catch (e) {
    ElMessage.error('加载合并试算表失败')
    console.error(e)
  } finally {
    loading.value = false
  }
}

function onRefresh() {
  loadData()
}

async function onExportExcel() {
  exportLoading.value = true
  try {
    const url = await exportConsolTrialExcel(props.projectId, props.period)
    if (url) {
      const a = document.createElement('a')
      a.href = url
      a.download = `合并试算表_${props.period}.xlsx`
      a.click()
      ElMessage.success('导出成功')
    }
  } catch (e) {
    ElMessage.error('导出失败')
    console.error(e)
  } finally {
    exportLoading.value = false
  }
}

function onCheckBalance() {
  balanceChecked.value = true
  if (balanceError.value) {
    ElMessageBox.alert(balanceError.value, '借贷不平衡', { type: 'error' })
  } else {
    ElMessage.success('借贷平衡校验通过')
  }
}

function onEliminationClick(row: ConsolTrialBalanceEntry) {
  emit('entry-click', row)
}

function handleFilterChange() {
  loadData()
}

onMounted(() => loadData())
</script>

<style scoped>
.gt-consol-trial-balance {
  display: flex;
  flex-direction: column;
  gap: var(--gt-space-3);
}

.toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: var(--gt-space-2);
}

.toolbar-left,
.toolbar-right {
  display: flex;
  align-items: center;
  gap: var(--gt-space-2);
}

/* 金额颜色 */
.debit { color: var(--gt-color-coral, #FF5149); }
.credit { color: var(--gt-color-teal, #0094B3); }
.zero { color: #999; }
.bold { font-weight: 700; }
.clickable { cursor: pointer; }
.clickable:hover { text-decoration: underline; }

.company-amount {
  display: flex;
  flex-direction: column;
  gap: 2px;
  font-size: 12px;
  line-height: 1.4;
}

/* 抵消列可点击样式 */
.elimination-cell {
  display: flex;
  justify-content: center;
  cursor: pointer;
}
.elimination-cell:hover {
  text-decoration: underline;
  color: var(--gt-color-primary, #4b2d77);
}

/* 展开行样式 */
.expanded-detail {
  padding: var(--gt-space-3);
  background: #f8f7fc;
}
.detail-title {
  font-size: 13px;
  color: var(--gt-color-primary, #4b2d77);
  font-weight: 600;
  margin-bottom: var(--gt-space-2);
}
.no-detail {
  color: #999;
  font-size: 13px;
  padding: var(--gt-space-2);
  text-align: center;
}

/* 合计行 */
.total-row {
  display: flex;
  align-items: center;
  background: var(--gt-color-primary, #4b2d77);
  color: #fff;
  font-size: 13px;
  font-weight: 600;
  padding: 8px 0;
  border-radius: var(--gt-radius-sm);
}
.total-label {
  width: 300px;
  padding-left: var(--gt-space-4);
  flex-shrink: 0;
}
.total-company {
  width: 160px;
  text-align: center;
  flex-shrink: 0;
}
.total-cell {
  width: 140px;
  text-align: center;
  flex-shrink: 0;
}

/* 表格样式 */
.consol-table :deep(.el-table__expanded-cell) {
  padding: 0;
}
.consol-table :deep(.el-table__row--striped) {
  background: #fafafa;
}
</style>
