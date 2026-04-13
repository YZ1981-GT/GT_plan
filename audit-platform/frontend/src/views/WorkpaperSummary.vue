<template>
  <div class="gt-wp-summary">
    <!-- 左侧选择面板 -->
    <aside class="gt-wp-summary__left">
      <!-- 科目选择 -->
      <div class="gt-wp-summary__selector">
        <h4 class="gt-wp-summary__selector-title">选择底稿科目</h4>
        <el-input
          v-model="accountFilter"
          placeholder="搜索科目..."
          size="small"
          clearable
          class="gt-wp-summary__filter"
        />
        <el-tree
          ref="accountTreeRef"
          :data="accountTree"
          :props="{ label: 'label', children: 'children' }"
          show-checkbox
          node-key="id"
          :filter-node-method="filterAccountNode"
          default-expand-all
          class="gt-wp-summary__tree"
          @check-change="onAccountCheck"
        />
      </div>

      <!-- 企业选择 -->
      <div class="gt-wp-summary__selector">
        <h4 class="gt-wp-summary__selector-title">选择企业</h4>
        <el-tree
          ref="companyTreeRef"
          :data="companyTree"
          :props="{ label: 'label', children: 'children' }"
          show-checkbox
          node-key="id"
          default-expand-all
          class="gt-wp-summary__tree"
        />
      </div>
    </aside>

    <!-- 右侧结果区 -->
    <main class="gt-wp-summary__right">
      <div class="gt-wp-summary__toolbar">
        <el-button type="primary" :loading="loading" @click="doGenerate">
          生成汇总
        </el-button>
        <el-button :disabled="!summaryData" @click="doExport">
          导出Excel
        </el-button>
        <el-button text @click="$router.back()">返回</el-button>
      </div>

      <el-table
        v-if="summaryData"
        :data="tableRows"
        border
        stripe
        size="small"
        class="gt-wp-summary__table"
        :summary-method="getSummaries"
        show-summary
      >
        <el-table-column prop="account_code" label="科目编码" width="120" fixed />
        <el-table-column prop="account_name" label="科目名称" width="160" fixed />
        <el-table-column
          v-for="cc in summaryData.companies"
          :key="cc"
          :label="summaryData.company_names[cc] || cc"
          min-width="140"
          align="right"
        >
          <template #default="{ row }">
            {{ fmtAmt(row.values[cc]) }}
          </template>
        </el-table-column>
        <el-table-column label="合计" min-width="140" align="right" fixed="right">
          <template #default="{ row }">
            <span style="font-weight: 600">{{ fmtAmt(row.total) }}</span>
          </template>
        </el-table-column>
      </el-table>

      <el-empty v-else description="请选择科目和企业后点击「生成汇总」" :image-size="120" />
    </main>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { getChildCompanies, generateWorkpaperSummary, exportWorkpaperSummary } from '@/services/auditPlatformApi'

const route = useRoute()
const projectId = route.params.projectId as string

// ── 科目树 ──
const accountFilter = ref('')
const accountTreeRef = ref<any>(null)

interface TreeNode { id: string; label: string; children?: TreeNode[] }

const accountTree = ref<TreeNode[]>([
  {
    id: 'asset', label: '1-资产类', children: [
      { id: '1001', label: '1001 库存现金' },
      { id: '1002', label: '1002 银行存款' },
      { id: '1012', label: '1012 其他货币资金' },
      { id: '1101', label: '1101 交易性金融资产' },
      { id: '1121', label: '1121 应收票据' },
      { id: '1122', label: '1122 应收账款' },
      { id: '1123', label: '1123 预付账款' },
      { id: '1131', label: '1131 应收股利' },
      { id: '1132', label: '1132 应收利息' },
      { id: '1221', label: '1221 其他应收款' },
      { id: '1401', label: '1401 材料采购' },
      { id: '1403', label: '1403 原材料' },
      { id: '1405', label: '1405 库存商品' },
      { id: '1501', label: '1501 持有至到期投资' },
      { id: '1511', label: '1511 长期股权投资' },
      { id: '1601', label: '1601 固定资产' },
      { id: '1602', label: '1602 累计折旧' },
      { id: '1604', label: '1604 在建工程' },
      { id: '1701', label: '1701 无形资产' },
      { id: '1702', label: '1702 累计摊销' },
      { id: '1801', label: '1801 长期待摊费用' },
      { id: '1811', label: '1811 递延所得税资产' },
    ],
  },
  {
    id: 'liability', label: '2-负债类', children: [
      { id: '2001', label: '2001 短期借款' },
      { id: '2201', label: '2201 应付票据' },
      { id: '2202', label: '2202 应付账款' },
      { id: '2203', label: '2203 预收账款' },
      { id: '2211', label: '2211 应付职工薪酬' },
      { id: '2221', label: '2221 应交税费' },
      { id: '2231', label: '2231 应付利息' },
      { id: '2232', label: '2232 应付股利' },
      { id: '2241', label: '2241 其他应付款' },
      { id: '2501', label: '2501 长期借款' },
      { id: '2502', label: '2502 应付债券' },
      { id: '2701', label: '2701 长期应付款' },
      { id: '2801', label: '2801 预计负债' },
      { id: '2901', label: '2901 递延收益' },
    ],
  },
  {
    id: 'equity', label: '3-权益类', children: [
      { id: '3001', label: '3001 实收资本' },
      { id: '3002', label: '3002 资本公积' },
      { id: '3101', label: '3101 盈余公积' },
      { id: '3103', label: '3103 本年利润' },
      { id: '3104', label: '3104 利润分配' },
    ],
  },
  {
    id: 'income_expense', label: '5/6-损益类', children: [
      { id: '5001', label: '5001 生产成本' },
      { id: '5101', label: '5101 制造费用' },
      { id: '6001', label: '6001 主营业务收入' },
      { id: '6051', label: '6051 其他业务收入' },
      { id: '6111', label: '6111 投资收益' },
      { id: '6301', label: '6301 营业外收入' },
      { id: '6401', label: '6401 主营业务成本' },
      { id: '6402', label: '6402 其他业务成本' },
      { id: '6403', label: '6403 营业税金及附加' },
      { id: '6601', label: '6601 销售费用' },
      { id: '6602', label: '6602 管理费用' },
      { id: '6603', label: '6603 财务费用' },
      { id: '6701', label: '6701 资产减值损失' },
      { id: '6711', label: '6711 营业外支出' },
      { id: '6801', label: '6801 所得税费用' },
    ],
  },
])

watch(accountFilter, (val) => {
  accountTreeRef.value?.filter(val)
})

function filterAccountNode(value: string, data: TreeNode) {
  if (!value) return true
  return data.label.toLowerCase().includes(value.toLowerCase())
}

function onAccountCheck() { /* no-op, read from ref on generate */ }

// ── 企业树 ──
const companyTreeRef = ref<any>(null)
const companyTree = ref<TreeNode[]>([])

onMounted(async () => {
  try {
    const companies = await getChildCompanies(projectId)
    companyTree.value = [{
      id: 'all',
      label: '全部企业',
      children: companies.map((c: any) => ({
        id: c.company_code,
        label: `${c.company_name}（${c.company_code}）`,
      })),
    }]
  } catch {
    companyTree.value = []
  }
})

// ── 汇总 ──
const loading = ref(false)
const summaryData = ref<any>(null)
const tableRows = ref<any[]>([])

async function doGenerate() {
  const checkedAccounts = (accountTreeRef.value?.getCheckedKeys(true) || [])
    .filter((k: string) => !['asset', 'liability', 'equity', 'income_expense'].includes(k))
  const checkedCompanies = (companyTreeRef.value?.getCheckedKeys(true) || [])
    .filter((k: string) => k !== 'all')

  if (!checkedAccounts.length) {
    ElMessage.warning('请至少选择一个科目')
    return
  }
  if (!checkedCompanies.length) {
    ElMessage.warning('请至少选择一个企业')
    return
  }

  loading.value = true
  try {
    const year = new Date().getFullYear()
    const result = await generateWorkpaperSummary(projectId, {
      year,
      account_codes: checkedAccounts,
      company_codes: checkedCompanies,
    })
    summaryData.value = result
    tableRows.value = result.rows || []
    if (!tableRows.value.length) {
      ElMessage.info('未查询到匹配数据')
    }
  } catch (e: any) {
    ElMessage.error(e?.message || '生成汇总失败')
  } finally {
    loading.value = false
  }
}

async function doExport() {
  if (!summaryData.value) return
  const checkedAccounts = (accountTreeRef.value?.getCheckedKeys(true) || [])
    .filter((k: string) => !['asset', 'liability', 'equity', 'income_expense'].includes(k))
  const checkedCompanies = (companyTreeRef.value?.getCheckedKeys(true) || [])
    .filter((k: string) => k !== 'all')

  try {
    const blob = await exportWorkpaperSummary(projectId, {
      year: new Date().getFullYear(),
      account_codes: checkedAccounts,
      company_codes: checkedCompanies,
    })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = 'workpaper_summary.xlsx'
    a.click()
    URL.revokeObjectURL(url)
    ElMessage.success('导出成功')
  } catch {
    ElMessage.error('导出失败')
  }
}

function getSummaries({ columns, data }: any) {
  if (!summaryData.value) return []
  const gt = summaryData.value.grand_total
  return columns.map((_: any, idx: number) => {
    if (idx === 0) return '合计'
    if (idx === 1) return ''
    if (idx === columns.length - 1) return fmtAmt(gt.total)
    const cc = summaryData.value.companies[idx - 2]
    return cc ? fmtAmt(gt[cc]) : ''
  })
}

function fmtAmt(v: any): string {
  const n = Number(v)
  if (!n && n !== 0) return '-'
  if (n === 0) return '-'
  return n.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.gt-wp-summary {
  display: flex;
  height: 100%;
  gap: 0;
}

.gt-wp-summary__left {
  width: 300px;
  min-width: 300px;
  border-right: 1px solid var(--gt-color-border-light);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.gt-wp-summary__selector {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  padding: var(--gt-space-3);
  border-bottom: 1px solid var(--gt-color-border-light);
}
.gt-wp-summary__selector:last-child {
  border-bottom: none;
}

.gt-wp-summary__selector-title {
  font-size: var(--gt-font-size-sm);
  font-weight: 600;
  color: var(--gt-color-primary-dark);
  margin: 0 0 var(--gt-space-2) 0;
  padding-bottom: var(--gt-space-1);
  border-bottom: 2px solid var(--gt-color-primary);
}

.gt-wp-summary__filter {
  margin-bottom: var(--gt-space-2);
}

.gt-wp-summary__tree {
  flex: 1;
  overflow-y: auto;
}
.gt-wp-summary__tree :deep(.el-tree-node__content) {
  height: 28px;
  font-size: var(--gt-font-size-xs);
}

.gt-wp-summary__right {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  padding: var(--gt-space-4);
}

.gt-wp-summary__toolbar {
  display: flex;
  gap: var(--gt-space-2);
  margin-bottom: var(--gt-space-4);
  align-items: center;
}

.gt-wp-summary__table {
  flex: 1;
}
.gt-wp-summary__table :deep(.el-table__footer-wrapper td) {
  font-weight: 700;
  background: var(--gt-color-primary-bg) !important;
}
.gt-wp-summary__table :deep(td .cell) {
  font-variant-numeric: tabular-nums;
}
</style>
