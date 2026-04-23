<template>
  <div class="report-page">
    <el-card class="toolbar-card" shadow="never">
      <div class="toolbar">
        <div class="left">
          <h2>调整分录</h2>
          <el-tag type="primary" effect="plain">RJE 重分类 / AJE 审计调整</el-tag>
        </div>
        <div class="right">
          <el-select v-model="currentYear" placeholder="选择年度" style="width:120px;margin-right:12px;">
            <el-option v-for="y in yearOptions" :key="y" :label="y + '年'" :value="y" />
          </el-select>
          <el-button :icon="RefreshRight" @click="loadData">刷新</el-button>
          <el-button :icon="Document" @click="goToUnadjusted">未审报表</el-button>
          <el-button :icon="DocumentChecked" @click="goToAdjusted">审定报表</el-button>
          <el-button :icon="List" @click="goToTrialBalance">试算平衡表</el-button>
        </div>
      </div>
    </el-card>

    <!-- 筛选与统计 -->
    <el-card shadow="never" style="margin-bottom:16px">
      <el-row :gutter="16">
        <el-col :span="6">
          <el-statistic title="总借方" :value="totalDebit" :precision="2" prefix="¥" />
        </el-col>
        <el-col :span="6">
          <el-statistic title="总贷方" :value="totalCredit" :precision="2" prefix="¥" />
        </el-col>
        <el-col :span="6">
          <el-statistic title="分录组数" :value="entries.length" />
        </el-col>
        <el-col :span="6">
          <el-statistic title="差额" :value="totalDebit - totalCredit" :precision="2" prefix="¥"
            :value-style="{ color: Math.abs(totalDebit - totalCredit) < 0.01 ? '#67c23a' : '#f56c6c' }" />
        </el-col>
      </el-row>
    </el-card>

    <!-- 分录列表 -->
    <el-card shadow="never">
      <el-table
        :data="entries"
        v-loading="loading"
        size="small"
        border
        stripe
        style="width: 100%"
        row-key="entry_group_id"
        default-expand-all
      >
        <el-table-column type="expand">
          <template #default="{ row }">
            <el-table :data="row.line_items" size="small" border :show-header="false" style="width:100%;margin:8px 0">
              <el-table-column prop="line_no" width="60" align="center" />
              <el-table-column prop="standard_account_code" label="科目代码" width="120" />
              <el-table-column prop="account_name" label="科目名称" min-width="180" />
              <el-table-column prop="debit_amount" label="借方" align="right" min-width="140">
                <template #default="{ row: li }">
                  <span v-if="Number(li.debit_amount) > 0" class="debit">{{ formatNumber(li.debit_amount) }}</span>
                  <span v-else>-</span>
                </template>
              </el-table-column>
              <el-table-column prop="credit_amount" label="贷方" align="right" min-width="140">
                <template #default="{ row: li }">
                  <span v-if="Number(li.credit_amount) > 0" class="credit">{{ formatNumber(li.credit_amount) }}</span>
                  <span v-else>-</span>
                </template>
              </el-table-column>
              <el-table-column prop="report_line_code" label="报表行次" width="100" />
            </el-table>
          </template>
        </el-table-column>
        <el-table-column prop="adjustment_no" label="分录编号" width="120" />
        <el-table-column prop="adjustment_type" label="类型" width="100">
          <template #default="{ row }">
            <el-tag :type="row.adjustment_type === 'rje' ? 'warning' : 'danger'" size="small">
              {{ row.adjustment_type === 'rje' ? '重分类' : '审计调整' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="description" label="摘要" min-width="240" />
        <el-table-column prop="review_status" label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="statusType(row.review_status)" size="small">{{ statusLabel(row.review_status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="total_debit" label="借方合计" align="right" min-width="140">
          <template #default="{ row }">
            {{ formatNumber(row.total_debit) }}
          </template>
        </el-table-column>
        <el-table-column prop="total_credit" label="贷方合计" align="right" min-width="140">
          <template #default="{ row }">
            {{ formatNumber(row.total_credit) }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="120" align="center">
          <template #default="{ row }">
            <el-button link type="primary" size="small" @click="viewImpact(row)">查看影响</el-button>
          </template>
        </el-table-column>
      </el-table>

      <el-empty v-if="!loading && entries.length === 0" description="暂无调整分录" />
    </el-card>

    <!-- 影响弹窗：联动试算表 -->
    <el-dialog v-model="impactDialogVisible" title="调整分录影响 — 试算表联动" width="720px">
      <p v-if="selectedEntry" style="margin-bottom:12px">
        分录 <strong>{{ selectedEntry.adjustment_no }}</strong> 影响的科目及金额变动：
      </p>
      <el-table v-if="impactData.length" :data="impactData" size="small" border>
        <el-table-column prop="standard_account_code" label="科目代码" width="120" />
        <el-table-column prop="account_name" label="科目名称" />
        <el-table-column prop="unadjusted_amount" label="调整前未审数" align="right">
          <template #default="{ row }">{{ formatNumber(row.unadjusted_amount) }}</template>
        </el-table-column>
        <el-table-column prop="adjustment_net" label="调整金额" align="right">
          <template #default="{ row }">
            <span :class="{ debit: row.adjustment_net > 0, credit: row.adjustment_net < 0 }">
              {{ formatNumber(row.adjustment_net) }}
            </span>
          </template>
        </el-table-column>
        <el-table-column prop="audited_amount" label="调整后审定数" align="right">
          <template #default="{ row }">{{ formatNumber(row.audited_amount) }}</template>
        </el-table-column>
      </el-table>
      <div style="margin-top:16px;text-align:right">
        <el-button type="primary" @click="impactDialogVisible = false">关闭</el-button>
        <el-button @click="goToTrialBalance">前往试算平衡表</el-button>
      </div>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { RefreshRight, Document, DocumentChecked, List } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { adjustmentEntries, trialBalance } from '@/api/index.js'

const route = useRoute()
const router = useRouter()

const currentProjectId = computed(() => route.query.project_id || localStorage.getItem('current_project_id') || '')
const currentYear = ref(parseInt(route.query.year) || new Date().getFullYear())
const yearOptions = computed(() => {
  const y = new Date().getFullYear()
  return [y, y - 1, y - 2]
})

const entries = ref([])
const loading = ref(false)

const totalDebit = computed(() =>
  entries.value.reduce((s, r) => s + (Number(r.total_debit) || 0), 0)
)
const totalCredit = computed(() =>
  entries.value.reduce((s, r) => s + (Number(r.total_credit) || 0), 0)
)

async function loadData() {
  if (!currentProjectId.value) {
    ElMessage.warning('请先选择项目')
    return
  }
  loading.value = true
  try {
    const result = await adjustmentEntries.list(currentProjectId.value, currentYear.value, { page_size: 500 })
    entries.value = result.items || result.data || result || []
  } catch (err) {
    ElMessage.error(err.message || '加载调整分录失败')
    entries.value = []
  } finally {
    loading.value = false
  }
}

function formatNumber(v) {
  if (v === null || v === undefined || v === '') return '-'
  const n = Number(v)
  if (isNaN(n)) return v
  return n.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function statusLabel(status) {
  const map = { draft: '草稿', pending: '待审', approved: '已审', rejected: '驳回' }
  return map[status] || status
}
function statusType(status) {
  const map = { draft: 'info', pending: 'warning', approved: 'success', rejected: 'danger' }
  return map[status] || 'info'
}

// 联动弹窗
const impactDialogVisible = ref(false)
const selectedEntry = ref(null)
const impactData = ref([])

async function viewImpact(entry) {
  selectedEntry.value = entry
  impactDialogVisible.value = true
  impactData.value = []
  if (!currentProjectId.value) return
  try {
    const tb = await trialBalance.get(currentProjectId.value, currentYear.value)
    const tbMap = {}
    ;(Array.isArray(tb) ? tb : []).forEach(r => {
      tbMap[r.standard_account_code] = r
    })
    impactData.value = (entry.line_items || []).map(li => {
      const tbr = tbMap[li.standard_account_code] || {}
      const adjNet = (Number(li.debit_amount) || 0) - (Number(li.credit_amount) || 0)
      return {
        standard_account_code: li.standard_account_code,
        account_name: li.account_name || tbr.account_name || '-',
        unadjusted_amount: tbr.unadjusted_amount || 0,
        adjustment_net: adjNet,
        audited_amount: (Number(tbr.audited_amount) || 0),
      }
    })
  } catch (err) {
    ElMessage.error('加载试算表联动数据失败')
  }
}

function goToUnadjusted() {
  router.push({
    path: '/reports/unadjusted',
    query: { project_id: currentProjectId.value, year: currentYear.value },
  })
}
function goToAdjusted() {
  router.push({
    path: '/reports/adjusted',
    query: { project_id: currentProjectId.value, year: currentYear.value },
  })
}
function goToTrialBalance() {
  router.push({
    path: '/reports/trial-balance',
    query: { project_id: currentProjectId.value, year: currentYear.value },
  })
}

watch([currentProjectId, currentYear], () => {
  loadData()
}, { immediate: true })
</script>

<style scoped>
.report-page {
  padding: 16px;
  background: #f5f7fa;
  min-height: 100vh;
}
.toolbar-card {
  margin-bottom: 16px;
}
.toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 12px;
}
.toolbar .left {
  display: flex;
  align-items: center;
  gap: 12px;
}
.toolbar .left h2 {
  margin: 0;
  font-size: 20px;
}
.toolbar .right {
  display: flex;
  align-items: center;
  gap: 8px;
}
.debit {
  color: #f56c6c;
}
.credit {
  color: #67c23a;
}
:deep(.el-statistic__content) {
  font-size: 22px;
}
</style>
