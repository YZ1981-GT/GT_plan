<template>
  <div class="gt-penetration">
    <!-- 账套信息栏 -->
    <div class="gt-ledger-header">
      <div class="gt-ledger-title">
        <span class="gt-ledger-company">{{ currentProject?.client_name || currentProject?.name || '—' }}</span>
        <el-tag size="small" type="info" style="margin-left: 8px">{{ currentProject?.name || '' }}</el-tag>
      </div>
      <div class="gt-ledger-switches">
        <el-select
          v-model="selectedProjectId"
          size="small"
          style="width: 200px"
          placeholder="切换单位"
          @change="onProjectChange"
        >
          <el-option
            v-for="p in projectList"
            :key="p.id"
            :label="`${p.client_name || p.name}`"
            :value="p.id"
          />
        </el-select>
        <el-select
          v-model="selectedYear"
          size="small"
          style="width: 100px"
          placeholder="年度"
          @change="onYearChange"
        >
          <el-option v-for="y in yearOptions" :key="y" :value="y">
            <span>{{ y }}年</span>
            <el-tag v-if="availableYears.includes(y)" size="small" type="success" style="margin-left: 6px; transform: scale(0.85)">有数据</el-tag>
          </el-option>
        </el-select>
        <el-button size="small" @click="goToImport">
          <el-icon style="margin-right: 2px"><Upload /></el-icon> 导入数据
        </el-button>
      </div>
    </div>

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

    <!-- ═══ 第一层：账簿查询 / 辅助余额表 ═══ -->
    <template v-if="currentLevel === 'balance'">
      <!-- Tab 切换 -->
      <div class="gt-balance-tabs">
        <span
          class="gt-balance-tab"
          :class="{ 'gt-balance-tab--active': balanceTab === 'account' }"
          @click="balanceTab = 'account'"
        >科目余额表</span>
        <span
          class="gt-balance-tab"
          :class="{ 'gt-balance-tab--active': balanceTab === 'aux' }"
          @click="balanceTab = 'aux'; loadAllAuxBalance()"
        >辅助余额表</span>
      </div>

      <!-- 账簿查询筛选栏 -->
      <div v-if="balanceTab === 'account'" class="gt-filter-row">
        <el-input
          v-model="searchKeyword"
          placeholder="搜索科目编号或名称..."
          size="small"
          clearable
          :prefix-icon="Search"
          style="width: 200px"
        />
        <el-select v-model="balanceFilter" size="small" style="width: 180px" placeholder="数据筛选">
          <el-option label="全部科目" value="all" />
          <el-option label="期末有数" value="closing" />
          <el-option label="期初有数" value="opening" />
          <el-option label="期初+期末都有数" value="both" />
          <el-option label="全部有数（期初+变动+期末）" value="all_nonzero" />
          <el-option label="本期有变动" value="changed" />
          <el-option label="借方有发生额" value="debit" />
          <el-option label="贷方有发生额" value="credit" />
          <el-option label="仅一级科目" value="level1" />
        </el-select>
        <el-button size="small" :type="treeMode ? 'primary' : ''" @click="treeMode = !treeMode">
          {{ treeMode ? '扁平视图' : '树形视图' }}
        </el-button>
        <el-button v-if="treeMode" size="small" @click="toggleExpandAll">
          {{ allExpanded ? '全部收起' : '全部展开' }}
        </el-button>
        <div class="gt-filter-spacer" />
        <el-tag type="info" size="small">账簿查询</el-tag>
        <el-tag size="small">{{ filteredFlatCount }} / {{ balanceData.length }}</el-tag>
        <el-button size="small" @click="refresh" :loading="loading">刷新</el-button>
      </div>

      <!-- 空状态 -->
      <div v-if="balanceTab === 'account' && !loading && balanceData.length === 0" class="gt-empty-state">
        <p style="font-size: 15px; color: #999">暂无科目余额数据</p>
        <p style="font-size: 13px; color: #bbb">请在项目向导「科目导入」步骤上传包含余额表的 Excel 文件</p>
      </div>

      <!-- 余额表 -->
      <el-table
        v-if="balanceTab === 'account' && balanceData.length > 0"
        ref="balanceTableRef"
        :data="treeMode ? treeBalance : filteredBalance"
        :row-key="treeMode ? 'account_code' : undefined"
        :tree-props="treeMode ? { children: 'children' } : undefined"
        :default-expand-all="false"
        border
        size="small"
        :max-height="tableHeight"
        style="width: 100%"
        highlight-current-row
        @row-dblclick="drillToLedger"
        :row-style="balanceRowStyle"
        :indent="24"
      >
        <el-table-column prop="account_code" label="科目编号" width="200" sortable>
          <template #default="{ row }">
            <span class="gt-link" @click.stop="drillToLedger(row)">{{ row.account_code }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="account_name" label="科目名称" min-width="180" show-overflow-tooltip />
        <el-table-column prop="opening_balance" label="期初余额" width="150" align="right" sortable>
          <template #default="{ row }">{{ fmtAmt(row.opening_balance) }}</template>
        </el-table-column>
        <el-table-column prop="debit_amount" label="借方发生额" width="150" align="right" sortable>
          <template #default="{ row }">{{ fmtAmt(row.debit_amount) }}</template>
        </el-table-column>
        <el-table-column prop="credit_amount" label="贷方发生额" width="150" align="right" sortable>
          <template #default="{ row }">{{ fmtAmt(row.credit_amount) }}</template>
        </el-table-column>
        <el-table-column prop="closing_balance" label="期末余额" width="150" align="right" sortable>
          <template #default="{ row }">
            <span class="gt-link" @click.stop="drillToLedger(row)">{{ fmtAmt(row.closing_balance) }}</span>
          </template>
        </el-table-column>
      </el-table>

      <!-- ═══ 辅助余额表视图 ═══ -->
      <div v-if="balanceTab === 'aux'">
        <div class="gt-filter-row">
          <el-input
            v-model="auxSearchKeyword"
            placeholder="搜索科目、辅助名称或编码..."
            size="small"
            clearable
            :prefix-icon="Search"
            style="width: 220px"
          />
          <el-select v-model="auxFilter" size="small" style="width: 180px" @change="auxPage = 1">
            <el-option label="全部" value="all" />
            <el-option label="期末有数" value="closing" />
            <el-option label="期初有数" value="opening" />
            <el-option label="本期有变动" value="changed" />
            <el-option label="全部有数（期初+变动+期末）" value="all_nonzero" />
          </el-select>
          <div class="gt-filter-spacer" />
          <el-tag size="small">{{ filteredAuxAll.length }} / {{ allAuxBalanceData.length }}</el-tag>
          <el-button size="small" @click="loadAllAuxBalance" :loading="loading">刷新</el-button>
        </div>

        <!-- 空状态 -->
        <div v-if="!loading && allAuxBalanceData.length === 0" class="gt-empty-state">
          <p style="font-size: 15px; color: #999">暂无辅助余额数据</p>
          <p style="font-size: 13px; color: #bbb">请点击右上角「导入数据」重新上传包含辅助账的 Excel 文件</p>
        </div>

        <el-table
          v-else
          :data="pagedAuxAll"
          border
          size="small"
          :max-height="tableHeight"
          style="width: 100%"
          highlight-current-row
          @row-dblclick="drillToAuxLedgerFromBalance"
          :row-style="auxRowStyle"
        >
          <el-table-column prop="account_code" label="科目编号" width="130" sortable />
          <el-table-column prop="account_name" label="科目名称" width="150" show-overflow-tooltip />
          <el-table-column prop="aux_type" label="辅助类型" width="90" />
          <el-table-column prop="aux_code" label="辅助编码" width="100" show-overflow-tooltip />
          <el-table-column prop="aux_name" label="辅助名称" min-width="160" show-overflow-tooltip>
            <template #default="{ row }">
              <span class="gt-link" @click.stop="drillToAuxLedgerFromBalance(row)">{{ row.aux_name }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="opening_balance" label="期初余额" width="130" align="right" sortable>
            <template #default="{ row }">{{ fmtAmt(row.opening_balance) }}</template>
          </el-table-column>
          <el-table-column prop="debit_amount" label="借方发生额" width="130" align="right" sortable>
            <template #default="{ row }">{{ fmtAmt(row.debit_amount) }}</template>
          </el-table-column>
          <el-table-column prop="credit_amount" label="贷方发生额" width="130" align="right" sortable>
            <template #default="{ row }">{{ fmtAmt(row.credit_amount) }}</template>
          </el-table-column>
          <el-table-column prop="closing_balance" label="期末余额" width="130" align="right" sortable>
            <template #default="{ row }">
              <span class="gt-link" @click.stop="drillToAuxLedgerFromBalance(row)">{{ fmtAmt(row.closing_balance) }}</span>
            </template>
          </el-table-column>
        </el-table>
        <div class="gt-pagination" v-if="filteredAuxAll.length > auxPageSize">
          <el-pagination
            v-model:current-page="auxPage"
            :page-size="auxPageSize"
            :total="filteredAuxAll.length"
            layout="prev, pager, next, total"
            size="small"
          />
        </div>
      </div>
    </template>

    <!-- ═══ 第二层：序时账明细 ═══ -->
    <template v-if="currentLevel === 'ledger'">
      <div class="gt-filter-row">
        <el-date-picker
          v-model="dateRange"
          type="daterange"
          size="small"
          start-placeholder="开始日期"
          end-placeholder="结束日期"
          value-format="YYYY-MM-DD"
          style="width: 260px"
          @change="loadLedger"
        />
        <el-button size="small" @click="drillToAuxBalance">辅助余额</el-button>
        <div class="gt-filter-spacer" />
        <el-tag type="info" size="small">{{ currentAccount }} 序时账</el-tag>
        <el-button size="small" @click="loadLedger" :loading="loading">刷新</el-button>
      </div>
      <el-table
        :data="ledgerDisplay"
        border
        size="small"
        :max-height="tableHeight"
        style="width: 100%"
        highlight-current-row
        @row-dblclick="drillToVoucher"
        :row-class-name="ledgerRowClass"
      >
        <el-table-column prop="voucher_date" label="日期" width="100" />
        <el-table-column prop="voucher_no" label="凭证号" width="90">
          <template #default="{ row }">
            <span v-if="row._type === 'normal'" class="gt-link" @click.stop="drillToVoucher(row)">{{ row.voucher_no }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="summary" label="摘要" min-width="200" show-overflow-tooltip />
        <el-table-column prop="debit_amount" label="借方" width="130" align="right">
          <template #default="{ row }">{{ fmtAmt(row.debit_amount) }}</template>
        </el-table-column>
        <el-table-column prop="credit_amount" label="贷方" width="130" align="right">
          <template #default="{ row }">{{ fmtAmt(row.credit_amount) }}</template>
        </el-table-column>
        <el-table-column prop="balance" label="余额" width="140" align="right">
          <template #default="{ row }">
            <span :style="{ fontWeight: row._type !== 'normal' ? '600' : 'normal' }">{{ fmtAmt(row.balance) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="counterpart_account" label="对方科目" width="120" show-overflow-tooltip />
      </el-table>
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

    <!-- ═══ 第三层：凭证分录 ═══ -->
    <template v-if="currentLevel === 'voucher'">
      <div class="gt-filter-row">
        <div class="gt-filter-spacer" />
        <el-tag type="info" size="small">凭证 {{ currentVoucher }}</el-tag>
      </div>
      <el-table :data="voucherItems" border stripe size="small" :max-height="tableHeight" style="width: 100%">
        <el-table-column prop="account_code" label="科目编号" width="120" />
        <el-table-column prop="account_name" label="科目名称" min-width="200" show-overflow-tooltip />
        <el-table-column prop="debit_amount" label="借方" width="140" align="right">
          <template #default="{ row }">{{ fmtAmt(row.debit_amount) }}</template>
        </el-table-column>
        <el-table-column prop="credit_amount" label="贷方" width="140" align="right">
          <template #default="{ row }">{{ fmtAmt(row.credit_amount) }}</template>
        </el-table-column>
        <el-table-column prop="summary" label="摘要" min-width="200" show-overflow-tooltip />
      </el-table>
    </template>

    <!-- ═══ 辅助余额 ═══ -->
    <template v-if="currentLevel === 'aux_balance'">
      <div class="gt-filter-row">
        <div class="gt-filter-spacer" />
        <el-tag type="info" size="small">{{ currentAccount }} 辅助余额</el-tag>
      </div>
      <el-table :data="auxBalanceItems" border stripe size="small" :max-height="tableHeight" style="width: 100%" @row-dblclick="drillToAuxLedger">
        <el-table-column prop="aux_type" label="辅助类型" width="100" />
        <el-table-column prop="aux_code" label="编号" width="120" />
        <el-table-column prop="aux_name" label="名称" min-width="200" show-overflow-tooltip>
          <template #default="{ row }">
            <span class="gt-link">{{ row.aux_name }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="opening_balance" label="期初" width="130" align="right">
          <template #default="{ row }">{{ fmtAmt(row.opening_balance) }}</template>
        </el-table-column>
        <el-table-column prop="debit_amount" label="借方" width="130" align="right">
          <template #default="{ row }">{{ fmtAmt(row.debit_amount) }}</template>
        </el-table-column>
        <el-table-column prop="credit_amount" label="贷方" width="130" align="right">
          <template #default="{ row }">{{ fmtAmt(row.credit_amount) }}</template>
        </el-table-column>
        <el-table-column prop="closing_balance" label="期末" width="130" align="right">
          <template #default="{ row }">{{ fmtAmt(row.closing_balance) }}</template>
        </el-table-column>
      </el-table>
    </template>

    <!-- ═══ 辅助明细 ═══ -->
    <template v-if="currentLevel === 'aux_ledger'">
      <div class="gt-filter-row">
        <div class="gt-filter-spacer" />
        <el-tag type="info" size="small">{{ currentAccount }} / {{ currentAuxCode }} 辅助明细</el-tag>
        <el-button size="small" @click="loadAuxLedger" :loading="loading">刷新</el-button>
      </div>
      <el-table
        :data="auxLedgerDisplay"
        border
        size="small"
        :max-height="tableHeight"
        style="width: 100%"
        highlight-current-row
        @row-dblclick="drillToVoucher"
        :row-class-name="ledgerRowClass"
      >
        <el-table-column prop="voucher_date" label="日期" width="100" />
        <el-table-column prop="voucher_no" label="凭证号" width="90">
          <template #default="{ row }">
            <span v-if="row._type === 'normal'" class="gt-link" @click.stop="drillToVoucher(row)">{{ row.voucher_no }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="aux_name" label="辅助名称" width="150" show-overflow-tooltip />
        <el-table-column prop="summary" label="摘要" min-width="180" show-overflow-tooltip />
        <el-table-column prop="debit_amount" label="借方" width="130" align="right">
          <template #default="{ row }">{{ fmtAmt(row.debit_amount) }}</template>
        </el-table-column>
        <el-table-column prop="credit_amount" label="贷方" width="130" align="right">
          <template #default="{ row }">{{ fmtAmt(row.credit_amount) }}</template>
        </el-table-column>
        <el-table-column prop="balance" label="余额" width="140" align="right">
          <template #default="{ row }">
            <span :style="{ fontWeight: row._type !== 'normal' ? '600' : 'normal' }">{{ fmtAmt(row.balance) }}</span>
          </template>
        </el-table-column>
      </el-table>
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
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Search, Upload } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import http from '@/utils/http'

const route = useRoute()
const router = useRouter()
const projectId = computed(() => route.params.projectId as string)
const year = computed(() => {
  const q = Number(route.query.year)
  if (q && q > 2000) return q
  return new Date().getFullYear() - 1
})

// ── 账套/年度切换 ──
interface ProjectInfo { id: string; name: string; client_name?: string; wizard_state?: any }
const projectList = ref<ProjectInfo[]>([])
const currentProject = ref<ProjectInfo | null>(null)
const selectedProjectId = ref('')
const selectedYear = ref(2025)

const yearOptions = computed(() => {
  const cur = new Date().getFullYear()
  const defaultYears = Array.from({ length: 5 }, (_, i) => cur - i)
  // 合并实际有数据的年度
  const all = new Set([...defaultYears, ...availableYears.value])
  return [...all].sort((a, b) => b - a)
})

const availableYears = ref<number[]>([])

async function loadAvailableYears() {
  if (!projectId.value) return
  try {
    const { data } = await http.get(`/api/projects/${projectId.value}/ledger/years`)
    const result = data?.data ?? data
    availableYears.value = result?.years ?? []
  } catch {
    availableYears.value = []
  }
}

async function loadProjectList() {
  try {
    const { data } = await http.get('/api/projects')
    const list = data?.data ?? data ?? []
    projectList.value = Array.isArray(list) ? list : []
  } catch {
    projectList.value = []
  }
}

async function loadCurrentProject() {
  if (!projectId.value) return
  try {
    const { data } = await http.get(`/api/projects/${projectId.value}/wizard`)
    const ws = data?.data ?? data
    const basicInfo = ws?.steps?.basic_info?.data || {}
    currentProject.value = {
      id: projectId.value,
      name: basicInfo.client_name ? `${basicInfo.client_name}_${basicInfo.audit_year || ''}` : projectId.value,
      client_name: basicInfo.client_name || '',
    }
    selectedYear.value = basicInfo.audit_year || year.value
  } catch {
    // 回退：从项目列表中找
    const found = projectList.value.find(p => p.id === projectId.value)
    if (found) currentProject.value = found
  }
  selectedProjectId.value = projectId.value
}

function onProjectChange(newId: string) {
  if (newId && newId !== projectId.value) {
    router.push({ path: `/projects/${newId}/ledger`, query: { year: String(selectedYear.value) } })
  }
}

function onYearChange(newYear: number) {
  selectedYear.value = newYear
  router.push({ path: `/projects/${projectId.value}/ledger`, query: { year: String(newYear) } })
}

function goToImport() {
  // 跳转到科目导入步骤（步骤2），带上 returnTo 参数以便导入完成后跳回
  router.push({
    path: '/projects/new',
    query: { projectId: projectId.value, returnTo: 'ledger' },
  })
}

// 路由变化时重新加载（不在初始化时触发，由 onMounted 处理）
let _initialized = false
watch([projectId, year], () => {
  if (!_initialized) return
  if (projectId.value) {
    loadCurrentProject()
    loadAvailableYears()
    currentLevel.value = 'balance'
    breadcrumbs.value = [{ label: '账簿查询', level: 'balance' }]
    loadBalance()
  }
})

const loading = ref(false)
const tableHeight = ref(Math.max(400, window.innerHeight - 240))

// ── 导航状态 ──
type Level = 'balance' | 'ledger' | 'voucher' | 'aux_balance' | 'aux_ledger'
const currentLevel = ref<Level>('balance')
const currentAccount = ref('')
const currentAccountOpening = ref(0)  // 穿透时记录期初余额
const currentAuxOpening = ref(0)  // 辅助明细穿透时记录期初余额
const currentVoucher = ref('')
const currentAuxType = ref('')
const currentAuxCode = ref('')
const searchKeyword = ref('')
const balanceFilter = ref('all')
const treeMode = ref(false)
const balanceTab = ref<'account' | 'aux'>('account')
const auxSearchKeyword = ref('')
const auxFilter = ref('all')
const auxPage = ref(1)
const auxPageSize = 100
const dateRange = ref<string[] | null>(null)

interface Crumb { label: string; level: Level; account?: string; voucher?: string }
const breadcrumbs = ref<Crumb[]>([{ label: '账簿查询', level: 'balance' }])

// ── 数据 ──
const balanceData = ref<any[]>([])
const ledgerItems = ref<any[]>([])
const ledgerTotal = ref(0)
const ledgerPage = ref(1)
const ledgerPageSize = 200

/** 序时账增强显示：期初行 + 每笔余额 + 月小计行 */
const ledgerDisplay = computed(() => {
  const items = ledgerItems.value
  if (items.length === 0) return []

  const rows: any[] = []
  let balance = currentAccountOpening.value
  let monthDebit = 0
  let monthCredit = 0
  let lastMonth = ''

  // 期初余额行
  rows.push({
    _type: 'opening',
    voucher_date: '',
    voucher_no: '',
    summary: '期初余额',
    debit_amount: null,
    credit_amount: null,
    balance,
    counterpart_account: '',
    account_code: '',
  })

  for (let i = 0; i < items.length; i++) {
    const item = items[i]
    const d = num(item.debit_amount)
    const c = num(item.credit_amount)
    balance += d - c
    monthDebit += d
    monthCredit += c

    const month = (item.voucher_date || '').substring(0, 7) // "2025-01"
    if (!lastMonth) lastMonth = month

    // 月份变化时插入上月小计
    if (month !== lastMonth && lastMonth) {
      rows.push({
        _type: 'subtotal',
        voucher_date: '',
        voucher_no: '',
        summary: `${lastMonth} 本月合计`,
        debit_amount: monthDebit,
        credit_amount: monthCredit,
        balance,
        counterpart_account: '',
        account_code: '',
      })
      monthDebit = d
      monthCredit = c
      lastMonth = month
    }

    rows.push({ ...item, _type: 'normal', balance })
  }

  // 最后一个月的小计
  if (items.length > 0) {
    rows.push({
      _type: 'subtotal',
      voucher_date: '',
      voucher_no: '',
      summary: `${lastMonth} 本月合计`,
      debit_amount: monthDebit,
      credit_amount: monthCredit,
      balance,
      counterpart_account: '',
      account_code: '',
    })
  }

  return rows
})
const voucherItems = ref<any[]>([])
const auxBalanceItems = ref<any[]>([])
const auxLedgerItems = ref<any[]>([])
const auxLedgerTotal = ref(0)
const auxLedgerPage = ref(1)

/** 辅助明细账增强显示：期初行 + 每笔余额 + 月小计行 */
const auxLedgerDisplay = computed(() => {
  const items = auxLedgerItems.value
  if (items.length === 0) return []

  const rows: any[] = []
  let balance = currentAuxOpening.value
  let monthDebit = 0
  let monthCredit = 0
  let lastMonth = ''

  rows.push({
    _type: 'opening', voucher_date: '', voucher_no: '', aux_name: '',
    summary: '期初余额', debit_amount: null, credit_amount: null,
    balance, account_code: '',
  })

  for (const item of items) {
    const d = num(item.debit_amount)
    const c = num(item.credit_amount)
    balance += d - c
    monthDebit += d
    monthCredit += c

    const month = (item.voucher_date || '').substring(0, 7)
    if (!lastMonth) lastMonth = month

    if (month !== lastMonth && lastMonth) {
      rows.push({
        _type: 'subtotal', voucher_date: '', voucher_no: '', aux_name: '',
        summary: `${lastMonth} 本月合计`, debit_amount: monthDebit,
        credit_amount: monthCredit, balance, account_code: '',
      })
      monthDebit = d
      monthCredit = c
      lastMonth = month
    }

    rows.push({ ...item, _type: 'normal', balance })
  }

  if (items.length > 0) {
    rows.push({
      _type: 'subtotal', voucher_date: '', voucher_no: '', aux_name: '',
      summary: `${lastMonth} 本月合计`, debit_amount: monthDebit,
      credit_amount: monthCredit, balance, account_code: '',
    })
  }

  return rows
})

// ── 余额表筛选 + 树形构建 ──
const balanceTableRef = ref<any>(null)
const allExpanded = ref(false)

function toggleExpandAll() {
  allExpanded.value = !allExpanded.value
  // el-table tree 不支持动态切换 default-expand-all，需要手动操作
  if (balanceTableRef.value) {
    const rows = filteredBalance.value
    for (const row of rows) {
      balanceTableRef.value.toggleRowExpansion(row, allExpanded.value)
    }
  }
}

/** 获取科目级次：优先用后端返回的 level 字段，否则从编码推断 */
function getLevel(row: any): number {
  if (row.level != null && row.level > 0) return row.level
  const code = row.account_code || ''
  if (code.includes('.')) return code.split('.').length
  if (code.length <= 4) return 1
  if (code.length <= 6) return 2
  return 3
}

/** 获取科目的父编码（通用规则）
 * 点号分隔：1002.001 → 1002, 1002.001.01 → 1002.001
 * 纯数字：4位为一级，6位为二级（前4位是父），8位为三级（前6位是父）
 */
function getParentCode(code: string): string | null {
  if (code.includes('.')) {
    const lastDot = code.lastIndexOf('.')
    if (lastDot <= 0) return null
    return code.substring(0, lastDot)
  }
  if (code.length > 6) return code.substring(0, 6)
  if (code.length > 4) return code.substring(0, 4)
  return null
}

const filteredBalance = computed(() => {
  let rows = balanceData.value

  // 关键词搜索时不做树形（直接扁平展示搜索结果）
  if (searchKeyword.value) {
    const kw = searchKeyword.value.toLowerCase()
    rows = rows.filter(r =>
      (r.account_code || '').toLowerCase().includes(kw) ||
      (r.account_name || '').toLowerCase().includes(kw)
    )
  }

  // 数据筛选
  const f = balanceFilter.value
  if (f === 'closing') {
    rows = rows.filter(r => num(r.closing_balance) !== 0)
  } else if (f === 'opening') {
    rows = rows.filter(r => num(r.opening_balance) !== 0)
  } else if (f === 'both') {
    rows = rows.filter(r => num(r.opening_balance) !== 0 && num(r.closing_balance) !== 0)
  } else if (f === 'all_nonzero') {
    rows = rows.filter(r =>
      num(r.opening_balance) !== 0 &&
      (num(r.debit_amount) !== 0 || num(r.credit_amount) !== 0) &&
      num(r.closing_balance) !== 0
    )
  } else if (f === 'changed') {
    rows = rows.filter(r => num(r.debit_amount) !== 0 || num(r.credit_amount) !== 0)
  } else if (f === 'debit') {
    rows = rows.filter(r => num(r.debit_amount) !== 0)
  } else if (f === 'credit') {
    rows = rows.filter(r => num(r.credit_amount) !== 0)
  } else if (f === 'level1') {
    rows = rows.filter(r => getLevel(r) === 1)
  }

  return rows
})

const filteredFlatCount = computed(() => filteredBalance.value.length)

/** 将扁平数据构建为树形结构 */
const treeBalance = computed(() => {
  if (!treeMode.value) return []  // 非树形模式不计算

  const rows = filteredBalance.value
  if (rows.length === 0) return []
  if (balanceFilter.value === 'level1') return rows

  // 简单高效的树构建：只用 account_code 的点号分隔判断父子
  const map = new Map<string, any>()
  const roots: any[] = []

  // 1. 创建所有节点
  for (const row of rows) {
    map.set(row.account_code, { ...row, children: [] })
  }

  // 2. 挂载父子关系
  for (const row of rows) {
    const node = map.get(row.account_code)!
    const pc = getParentCode(row.account_code)
    if (pc && map.has(pc)) {
      map.get(pc)!.children.push(node)
    } else {
      roots.push(node)
    }
  }

  // 3. 清理空 children（不显示展开箭头）
  for (const [, node] of map) {
    if (node.children.length === 0) delete node.children
  }

  return roots.length > 0 ? roots : rows
})

function num(v: any): number { return Number(v) || 0 }

function fmtAmt(v: any): string {
  const n = Number(v)
  if (!n) return '-'
  return n.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function ledgerRowClass({ row }: { row: any }): string {
  if (row._type === 'opening') return 'gt-ledger-opening'
  if (row._type === 'subtotal') return 'gt-ledger-subtotal'
  return ''
}

function balanceRowStyle({ row }: { row: any }) {
  const level = getLevel(row)
  const style: Record<string, string> = {}
  if (level === 1) {
    style.fontWeight = '600'
    style.background = '#f8f5fc'
  }
  // 筛选模式下，补充的祖先节点用浅灰色
  if (row._isAncestor) {
    style.color = '#999'
    style.fontStyle = 'italic'
  }
  return style
}

function auxRowStyle({ row }: { row: any }) {
  // 同一科目的行用相同背景色区分
  return {}
}

// ── 加载数据 ──
async function loadBalance() {
  if (!projectId.value) {
    console.warn('[Ledger] projectId is empty, skip loading')
    return
  }
  loading.value = true
  try {
    const { data } = await http.get(`/api/projects/${projectId.value}/ledger/balance`, {
      params: { year: year.value },
    })
    balanceData.value = data.data ?? data ?? []
    // debug log removed for production
  } catch (e) {
    console.error('[Ledger] loadBalance failed:', e)
    balanceData.value = []
  }
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
      `/api/projects/${projectId.value}/ledger/entries/${encodeURIComponent(currentAccount.value)}`, { params }
    )
    const result = data.data ?? data
    ledgerItems.value = result.items ?? result ?? []
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

// ── 辅助余额表（全量，Tab 视图用） ──
const allAuxBalanceData = ref<any[]>([])

const filteredAuxAll = computed(() => {
  let rows = allAuxBalanceData.value

  // 搜索
  if (auxSearchKeyword.value) {
    const kw = auxSearchKeyword.value.toLowerCase()
    rows = rows.filter(r =>
      (r.account_code || '').toLowerCase().includes(kw) ||
      (r.account_name || '').toLowerCase().includes(kw) ||
      (r.aux_name || '').toLowerCase().includes(kw) ||
      (r.aux_code || '').toLowerCase().includes(kw)
    )
  }

  // 筛选
  const f = auxFilter.value
  if (f === 'closing') {
    rows = rows.filter(r => num(r.closing_balance) !== 0)
  } else if (f === 'opening') {
    rows = rows.filter(r => num(r.opening_balance) !== 0)
  } else if (f === 'changed') {
    rows = rows.filter(r => num(r.debit_amount) !== 0 || num(r.credit_amount) !== 0)
  } else if (f === 'all_nonzero') {
    rows = rows.filter(r =>
      num(r.opening_balance) !== 0 &&
      (num(r.debit_amount) !== 0 || num(r.credit_amount) !== 0) &&
      num(r.closing_balance) !== 0
    )
  }

  return rows
})

const pagedAuxAll = computed(() => {
  const start = (auxPage.value - 1) * auxPageSize
  return filteredAuxAll.value.slice(start, start + auxPageSize)
})

async function loadAllAuxBalance() {
  if (!projectId.value) return
  loading.value = true
  try {
    // 查所有科目的辅助余额（不传 account_code）
    const { data } = await http.get(
      `/api/projects/${projectId.value}/ledger/aux-balance-all`,
      { params: { year: year.value } }
    )
    allAuxBalanceData.value = data.data ?? data ?? []
  } catch { allAuxBalanceData.value = [] }
  finally { loading.value = false }
}

function drillToAuxLedgerFromBalance(row: any) {
  currentAccount.value = row.account_code
  currentAuxType.value = row.aux_type || ''
  currentAuxCode.value = row.aux_code || ''
  currentAuxOpening.value = num(row.opening_balance)
  currentLevel.value = 'aux_ledger'
  auxLedgerPage.value = 1
  breadcrumbs.value = [
    { label: '账簿查询', level: 'balance' },
    { label: `${row.account_code} ${row.aux_name || row.aux_code || ''}`, level: 'aux_ledger' },
  ]
  loadAuxLedger()
}

async function loadAuxLedger() {
  loading.value = true
  try {
    const { data } = await http.get(
      `/api/projects/${projectId.value}/ledger/aux-entries/${currentAccount.value}`,
      { params: { year: year.value, aux_type: currentAuxType.value, aux_code: currentAuxCode.value, page: auxLedgerPage.value, page_size: 100 } }
    )
    const result = data.data ?? data
    auxLedgerItems.value = result.items ?? result ?? []
    auxLedgerTotal.value = result.total ?? 0
  } catch { auxLedgerItems.value = [] }
  finally { loading.value = false }
}

// ── 穿透导航 ──
function drillToLedger(row: any) {
  const code = row.account_code
  // 判断是否有子科目（非末级）：在 balanceData 中查找是否有以该编码为前缀的其他科目
  const hasChildren = balanceData.value.some(r =>
    r.account_code !== code && (r.account_code.startsWith(code + '.') || (r.account_code.startsWith(code) && r.account_code.length > code.length && !code.includes('.')))
  )
  // 非末级科目用前缀查询（查所有子科目的明细账）
  currentAccount.value = hasChildren ? code + '*' : code
  currentAccountOpening.value = num(row.opening_balance)
  currentLevel.value = 'ledger'
  ledgerPage.value = 1
  dateRange.value = null
  const label = hasChildren
    ? `${code} ${row.account_name || ''} (含明细)`
    : `${code} ${row.account_name || ''}`
  breadcrumbs.value = [
    { label: '账簿查询', level: 'balance' },
    { label, level: 'ledger', account: currentAccount.value },
  ]
  loadLedger()
}

function drillToVoucher(row: any) {
  if (!row.voucher_no) return
  currentVoucher.value = row.voucher_no
  currentLevel.value = 'voucher'
  breadcrumbs.value.push({
    label: `凭证 ${row.voucher_no}`, level: 'voucher', voucher: row.voucher_no,
  })
  loadVoucher()
}

function drillToAuxBalance() {
  // 从序时账跳到辅助余额（去掉 * 后缀）
  const code = currentAccount.value.replace('*', '')
  currentAccount.value = code
  currentLevel.value = 'aux_balance'
  breadcrumbs.value.push({
    label: `${code} 辅助余额`, level: 'aux_balance', account: code,
  })
  loadAuxBalance()
}

function drillToAuxLedger(row: any) {
  currentAuxType.value = row.aux_type
  currentAuxCode.value = row.aux_code
  currentAuxOpening.value = num(row.opening_balance)
  currentLevel.value = 'aux_ledger'
  auxLedgerPage.value = 1
  breadcrumbs.value.push({
    label: `${row.aux_name || row.aux_code}`, level: 'aux_ledger',
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

// ── 键盘快捷键：Enter 返回上一级 ──
function onKeyDown(e: KeyboardEvent) {
  if (e.key === 'Enter' && currentLevel.value !== 'balance') {
    e.preventDefault()
    // 返回上一级
    const idx = breadcrumbs.value.length - 2
    if (idx >= 0) navigateTo(idx)
  }
}
onMounted(async () => {
  document.addEventListener('keydown', onKeyDown)
  await loadProjectList()
  await loadCurrentProject()
  await loadAvailableYears()
  await loadBalance()
  _initialized = true
})
onUnmounted(() => {
  document.removeEventListener('keydown', onKeyDown)
})
</script>

<style scoped>
.gt-penetration { padding: var(--gt-space-4); height: 100%; display: flex; flex-direction: column; }

.gt-ledger-header {
  display: flex; align-items: center; justify-content: space-between;
  margin-bottom: var(--gt-space-3); padding: 10px 16px;
  background: linear-gradient(135deg, #f8f5fc 0%, #f0ecf7 100%);
  border-radius: var(--gt-radius-md); border: 1px solid var(--gt-color-primary-lighter, #e0d4f0);
}
.gt-ledger-title { display: flex; align-items: center; }
.gt-ledger-company {
  font-size: 16px; font-weight: 600; color: var(--gt-color-primary-dark);
}
.gt-ledger-switches { display: flex; align-items: center; gap: 8px; }

.gt-balance-tabs {
  display: flex; gap: 0; margin-bottom: var(--gt-space-2);
  border-bottom: 2px solid #e8e8e8;
}
.gt-balance-tab {
  padding: 8px 20px; cursor: pointer; font-size: 14px; font-weight: 500;
  color: #666; border-bottom: 2px solid transparent; margin-bottom: -2px;
  transition: all 0.2s;
}
.gt-balance-tab:hover { color: var(--gt-color-primary); }
.gt-balance-tab--active {
  color: var(--gt-color-primary); border-bottom-color: var(--gt-color-primary);
  font-weight: 600;
}

.gt-breadcrumb {
  display: flex; align-items: center; gap: 2px;
  margin-bottom: var(--gt-space-3); font-size: var(--gt-font-size-sm);
}
.gt-crumb {
  cursor: pointer; color: var(--gt-color-primary); padding: 2px 6px;
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

.gt-empty-state {
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  min-height: 300px; border: 1px dashed #e0e0e0; border-radius: var(--gt-radius-md);
  background: #fafafa;
}

/* 序时账特殊行样式 */
:deep(.gt-ledger-opening) {
  background: #f0ecf7 !important;
  font-weight: 600;
  font-style: italic;
}
:deep(.gt-ledger-subtotal) {
  background: #fef6e6 !important;
  font-weight: 600;
  border-top: 1px solid #e6a23c;
}
</style>
