<template>
  <div class="gt-drilldown gt-fade-in">
    <!-- 面包屑导航 -->
    <el-breadcrumb separator=">" class="gt-drilldown-breadcrumb">
      <el-breadcrumb-item
        v-for="(crumb, idx) in store.breadcrumbs"
        :key="crumb.level"
      >
        <span
          :class="{ 'gt-drilldown-crumb-link': idx < store.breadcrumbs.length - 1 }"
          @click="idx < store.breadcrumbs.length - 1 && store.navigateTo(crumb.level)"
        >
          {{ crumb.label }}
        </span>
      </el-breadcrumb-item>
    </el-breadcrumb>

    <!-- 余额表视图 -->
    <div v-if="store.currentLevel === 'balance'" class="gt-drilldown-balance-view">
      <div class="gt-drilldown-filter-bar">
        <el-select
          v-model="store.balanceFilter.category"
          placeholder="科目类别"
          clearable
          style="width: 140px"
          @change="onBalanceFilterChange"
        >
          <el-option label="资产" value="asset" />
          <el-option label="负债" value="liability" />
          <el-option label="权益" value="equity" />
          <el-option label="收入" value="revenue" />
          <el-option label="成本" value="cost" />
          <el-option label="费用" value="expense" />
        </el-select>
        <el-input
          v-model="store.balanceFilter.keyword"
          placeholder="搜索科目编码或名称"
          clearable
          style="width: 220px"
          @clear="onBalanceFilterChange"
          @keyup.enter="onBalanceFilterChange"
        />
        <el-button type="primary" @click="onBalanceFilterChange">查询</el-button>
      </div>

      <el-table
        :data="store.balanceData"
        v-loading="store.loading"
        stripe
        border
        style="width: 100%"
      >
        <el-table-column prop="account_code" label="科目编码" width="140" />
        <el-table-column prop="account_name" label="科目名称" min-width="180">
          <template #default="{ row }">
            <span
              class="gt-drilldown-account-link"
              @click="onAccountClick(row)"
            >
              {{ row.account_name }}
              <el-tag v-if="row.has_aux" size="small" type="info" style="margin-left: 4px">辅</el-tag>
            </span>
          </template>
        </el-table-column>
        <el-table-column prop="opening_balance" label="期初余额" width="140" align="right">
          <template #default="{ row }">{{ fmt(row.opening_balance) }}</template>
        </el-table-column>
        <el-table-column prop="debit_amount" label="借方发生额" width="140" align="right">
          <template #default="{ row }">{{ fmt(row.debit_amount) }}</template>
        </el-table-column>
        <el-table-column prop="credit_amount" label="贷方发生额" width="140" align="right">
          <template #default="{ row }">{{ fmt(row.credit_amount) }}</template>
        </el-table-column>
        <el-table-column prop="closing_balance" label="期末余额" width="140" align="right">
          <template #default="{ row }">{{ fmt(row.closing_balance) }}</template>
        </el-table-column>
      </el-table>

      <el-pagination
        v-if="store.balanceTotal > store.balanceFilter.pageSize"
        :current-page="store.balanceFilter.page"
        :page-size="store.balanceFilter.pageSize"
        :total="store.balanceTotal"
        layout="total, prev, pager, next"
        @current-change="onBalancePageChange"
        style="margin-top: 12px; justify-content: flex-end"
      />
    </div>

    <!-- 序时账视图 -->
    <div v-if="store.currentLevel === 'ledger'" class="gt-drilldown-ledger-view">
      <div class="gt-drilldown-filter-bar">
        <el-date-picker
          v-model="ledgerDateRange"
          type="daterange"
          range-separator="至"
          start-placeholder="开始日期"
          end-placeholder="结束日期"
          value-format="YYYY-MM-DD"
          style="width: 260px"
        />
        <el-input
          v-model="store.ledgerFilter.voucherNo"
          placeholder="凭证号"
          clearable
          style="width: 120px"
        />
        <el-input
          v-model="store.ledgerFilter.summaryKeyword"
          placeholder="摘要关键词"
          clearable
          style="width: 160px"
        />
        <el-input
          v-model="store.ledgerFilter.counterpartAccount"
          placeholder="对方科目"
          clearable
          style="width: 120px"
        />
        <el-input-number
          v-model="store.ledgerFilter.amountMin"
          placeholder="最小金额"
          :controls="false"
          style="width: 120px"
        />
        <el-input-number
          v-model="store.ledgerFilter.amountMax"
          placeholder="最大金额"
          :controls="false"
          style="width: 120px"
        />
        <el-button type="primary" @click="onLedgerSearch">查询</el-button>
        <el-button @click="onLedgerReset">重置</el-button>
      </div>

      <el-table
        :data="store.ledgerData"
        v-loading="store.loading"
        stripe
        border
        style="width: 100%"
      >
        <el-table-column prop="voucher_date" label="凭证日期" width="110" />
        <el-table-column prop="voucher_no" label="凭证号" width="100" />
        <el-table-column prop="account_name" label="科目名称" width="160" />
        <el-table-column prop="debit_amount" label="借方金额" width="130" align="right">
          <template #default="{ row }">{{ fmt(row.debit_amount) }}</template>
        </el-table-column>
        <el-table-column prop="credit_amount" label="贷方金额" width="130" align="right">
          <template #default="{ row }">{{ fmt(row.credit_amount) }}</template>
        </el-table-column>
        <el-table-column prop="counterpart_account" label="对方科目" width="120" />
        <el-table-column prop="summary" label="摘要" min-width="200" />
        <el-table-column prop="preparer" label="制单人" width="80" />
      </el-table>

      <el-pagination
        v-if="store.ledgerTotal > store.ledgerFilter.pageSize"
        :current-page="store.ledgerFilter.page"
        :page-size="store.ledgerFilter.pageSize"
        :total="store.ledgerTotal"
        layout="total, prev, pager, next"
        @current-change="onLedgerPageChange"
        style="margin-top: 12px; justify-content: flex-end"
      />
    </div>

    <!-- 辅助余额表视图 -->
    <div v-if="store.currentLevel === 'aux_balance'" class="gt-drilldown-aux-balance-view">
      <el-table
        :data="store.auxBalanceData"
        v-loading="store.loading"
        stripe
        border
        style="width: 100%"
      >
        <el-table-column prop="aux_type" label="辅助类型" width="100" />
        <el-table-column prop="aux_code" label="辅助编码" width="120" />
        <el-table-column prop="aux_name" label="辅助名称" min-width="180">
          <template #default="{ row }">
            <span class="gt-drilldown-account-link" @click="onAuxBalanceClick(row)">
              {{ row.aux_name }}
            </span>
          </template>
        </el-table-column>
        <el-table-column prop="opening_balance" label="期初余额" width="140" align="right">
          <template #default="{ row }">{{ fmt(row.opening_balance) }}</template>
        </el-table-column>
        <el-table-column prop="debit_amount" label="借方发生额" width="140" align="right">
          <template #default="{ row }">{{ fmt(row.debit_amount) }}</template>
        </el-table-column>
        <el-table-column prop="credit_amount" label="贷方发生额" width="140" align="right">
          <template #default="{ row }">{{ fmt(row.credit_amount) }}</template>
        </el-table-column>
        <el-table-column prop="closing_balance" label="期末余额" width="140" align="right">
          <template #default="{ row }">{{ fmt(row.closing_balance) }}</template>
        </el-table-column>
      </el-table>
    </div>

    <!-- 辅助明细账视图 -->
    <div v-if="store.currentLevel === 'aux_ledger'" class="gt-drilldown-aux-ledger-view">
      <el-table
        :data="store.auxLedgerData"
        v-loading="store.loading"
        stripe
        border
        style="width: 100%"
      >
        <el-table-column prop="voucher_date" label="凭证日期" width="110" />
        <el-table-column prop="voucher_no" label="凭证号" width="100" />
        <el-table-column prop="aux_name" label="辅助名称" width="160" />
        <el-table-column prop="debit_amount" label="借方金额" width="130" align="right">
          <template #default="{ row }">{{ fmt(row.debit_amount) }}</template>
        </el-table-column>
        <el-table-column prop="credit_amount" label="贷方金额" width="130" align="right">
          <template #default="{ row }">{{ fmt(row.credit_amount) }}</template>
        </el-table-column>
        <el-table-column prop="summary" label="摘要" min-width="200" />
        <el-table-column prop="preparer" label="制单人" width="80" />
      </el-table>

      <el-pagination
        v-if="store.auxLedgerTotal > 50"
        :current-page="store.auxLedgerPage"
        :page-size="50"
        :total="store.auxLedgerTotal"
        layout="total, prev, pager, next"
        @current-change="onAuxLedgerPageChange"
        style="margin-top: 12px; justify-content: flex-end"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, watch } from 'vue'
import { useRoute } from 'vue-router'
import { useDrilldownStore } from '@/stores/drilldown'
import type { BalanceRow, AuxBalanceRow } from '@/stores/drilldown'

const route = useRoute()
const store = useDrilldownStore()

const ledgerDateRange = ref<[string, string] | null>(null)

watch(ledgerDateRange, (val) => {
  if (val) {
    store.ledgerFilter.dateFrom = val[0]
    store.ledgerFilter.dateTo = val[1]
  } else {
    store.ledgerFilter.dateFrom = null
    store.ledgerFilter.dateTo = null
  }
})

onMounted(() => {
  const pid = route.params.projectId as string
  const y = Number(route.query.year) || new Date().getFullYear()
  store.setProject(pid, y)
  store.reset()
  store.fetchBalance()
})

function fmt(val: number | null | undefined): string {
  if (val == null) return '-'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function onBalanceFilterChange() {
  store.balanceFilter.page = 1
  store.fetchBalance()
}

function onBalancePageChange(page: number) {
  store.balanceFilter.page = page
  store.fetchBalance()
}

function onAccountClick(row: BalanceRow) {
  if (row.has_aux) {
    store.drillToAuxBalance(row.account_code, row.account_name || '')
  } else {
    store.drillToLedger(row.account_code, row.account_name || '')
  }
}

function onLedgerSearch() {
  store.ledgerFilter.page = 1
  store.fetchLedger()
}

function onLedgerReset() {
  store.ledgerFilter = {
    dateFrom: null, dateTo: null, amountMin: null, amountMax: null,
    voucherNo: '', summaryKeyword: '', counterpartAccount: '',
    page: 1, pageSize: 50,
  }
  ledgerDateRange.value = null
  store.fetchLedger()
}

function onLedgerPageChange(page: number) {
  store.ledgerFilter.page = page
  store.fetchLedger()
}

function onAuxBalanceClick(row: AuxBalanceRow) {
  store.drillToAuxLedger(row.aux_type, row.aux_code || '', row.aux_name || '')
}

function onAuxLedgerPageChange(page: number) {
  store.auxLedgerPage = page
  store.fetchAuxLedger()
}
</script>

<style scoped>
.gt-drilldown {
  padding: var(--gt-space-5);
}
.gt-drilldown-breadcrumb {
  margin-bottom: var(--gt-space-4);
  padding: 12px 18px;
  background: var(--gt-color-bg-white);
  border-radius: var(--gt-radius-md);
  box-shadow: var(--gt-shadow-xs);
  border: 1px solid rgba(75, 45, 119, 0.04);
}
.gt-drilldown-crumb-link {
  cursor: pointer;
  color: var(--gt-color-primary);
  font-weight: 500;
  transition: color var(--gt-transition-fast);
}
.gt-drilldown-crumb-link:hover {
  color: var(--gt-color-primary-light);
}
.gt-drilldown-filter-bar {
  display: flex;
  gap: var(--gt-space-2);
  margin-bottom: var(--gt-space-4);
  flex-wrap: wrap;
  align-items: center;
  padding: 10px 16px;
  background: linear-gradient(135deg, #faf9fd, #f4f0fa);
  border-radius: var(--gt-radius-md);
  border: 1px solid rgba(75, 45, 119, 0.06);
}
.gt-drilldown-account-link {
  cursor: pointer;
  color: var(--gt-color-primary);
  font-weight: 500;
  transition: all var(--gt-transition-fast);
  padding: 1px 4px;
  border-radius: var(--gt-radius-sm);
}
.gt-drilldown-account-link:hover {
  background: var(--gt-color-primary-bg);
  color: var(--gt-color-primary-light);
}
</style>
