<template>
  <div class="gt-cfs-worksheet gt-fade-in">
    <div class="gt-cfs-header">
      <h2 class="gt-page-title">现金流量表工作底稿</h2>
      <div class="gt-cfs-actions">
        <el-button @click="onGenerate" :loading="genLoading">生成工作底稿</el-button>
        <el-button @click="onAutoGenerate" :loading="autoLoading">自动生成调整项</el-button>
        <el-button @click="showAdjForm = true" type="primary">新建调整分录</el-button>
      </div>
    </div>

    <!-- 平衡状态 -->
    <el-alert v-if="reconciliation" :type="reconciliation.balanced ? 'success' : 'warning'"
      :title="reconciliation.balanced ? '✓ 工作底稿已平衡' : '✗ 工作底稿未平衡'" :closable="false"
      show-icon style="margin-bottom: 12px" />

    <!-- 工作底稿表格 -->
    <h3 class="gt-section-title">工作底稿</h3>
    <el-table :data="worksheetRows" v-loading="loading" border stripe size="small" style="width: 100%; margin-bottom: 20px">
      <el-table-column prop="account_code" label="科目编码" width="110" />
      <el-table-column prop="account_name" label="科目名称" min-width="160" />
      <el-table-column label="期初余额" width="130" align="right">
        <template #default="{ row }">{{ fmtAmt(row.opening_balance) }}</template>
      </el-table-column>
      <el-table-column label="期末余额" width="130" align="right">
        <template #default="{ row }">{{ fmtAmt(row.closing_balance) }}</template>
      </el-table-column>
      <el-table-column label="变动额" width="130" align="right">
        <template #default="{ row }">{{ fmtAmt(row.period_change) }}</template>
      </el-table-column>
      <el-table-column label="已分配" width="130" align="right">
        <template #default="{ row }">{{ fmtAmt(row.allocated_amount) }}</template>
      </el-table-column>
      <el-table-column label="未分配" width="130" align="right">
        <template #default="{ row }">
          <span :class="{ 'gt-cfs-unallocated': parseFloat(row.unallocated_amount) !== 0 }">
            {{ fmtAmt(row.unallocated_amount) }}
          </span>
        </template>
      </el-table-column>
    </el-table>

    <!-- CFS调整分录列表 -->
    <h3 class="gt-section-title">调整分录</h3>
    <el-table :data="adjustments" border stripe size="small" style="width: 100%; margin-bottom: 20px">
      <el-table-column prop="adjustment_no" label="编号" width="100" />
      <el-table-column prop="description" label="描述" min-width="180" show-overflow-tooltip />
      <el-table-column prop="debit_account" label="借方科目" width="130" />
      <el-table-column prop="credit_account" label="贷方科目" width="130" />
      <el-table-column label="金额" width="120" align="right">
        <template #default="{ row }">{{ fmtAmt(row.amount) }}</template>
      </el-table-column>
      <el-table-column label="类别" width="100">
        <template #default="{ row }">
          <el-tag size="small" :type="categoryTagType(row.cash_flow_category)">
            {{ categoryLabel(row.cash_flow_category) }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="自动" width="60" align="center">
        <template #default="{ row }">
          <el-tag v-if="row.is_auto_generated" type="info" size="small">自动</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="120" fixed="right">
        <template #default="{ row }">
          <el-button size="small" @click="editAdj(row)">编辑</el-button>
          <el-button size="small" type="danger" @click="deleteAdj(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 现金流量表预览 + 勾稽校验 -->
    <el-row :gutter="16">
      <el-col :span="12">
        <h3 class="gt-section-title">间接法补充资料</h3>
        <el-table v-if="indirectMethod" :data="indirectMethod.items" border size="small"
          :row-class-name="({ row }) => row.is_total ? 'total-row' : ''">
          <el-table-column prop="label" label="项目" min-width="250" />
          <el-table-column label="金额" width="150" align="right">
            <template #default="{ row }">{{ fmtAmt(row.amount) }}</template>
          </el-table-column>
        </el-table>
        <div v-if="indirectMethod" class="gt-cfs-reconciliation-badge" :class="indirectMethod.reconciliation_passed ? 'gt-cfs-pass' : 'gt-cfs-fail'">
          {{ indirectMethod.reconciliation_passed ? '✓ 间接法勾稽通过' : '✗ 间接法勾稽不通过' }}
        </div>
      </el-col>
      <el-col :span="12">
        <h3 class="gt-section-title">现金勾稽校验</h3>
        <div v-if="verifyResult" class="gt-cfs-verify-panel">
          <div v-for="(item, idx) in verifyResult.checks || []" :key="idx" class="gt-cfs-verify-item"
            :class="item.passed ? 'gt-cfs-pass' : 'gt-cfs-fail'">
            {{ item.passed ? '✓' : '✗' }} {{ item.name }}
            <span v-if="!item.passed" class="gt-cfs-verify-diff">差额: {{ item.diff }}</span>
          </div>
        </div>
        <el-button @click="onVerify" :loading="verifyLoading" style="margin-top: 8px">执行勾稽校验</el-button>
      </el-col>
    </el-row>

    <!-- 新建/编辑调整分录弹窗 -->
    <el-dialog append-to-body v-model="showAdjForm" :title="editingAdj ? '编辑调整分录' : '新建调整分录'" width="550px" destroy-on-close>
      <el-form :model="adjForm" label-width="90px">
        <el-form-item label="描述">
          <el-input v-model="adjForm.description" />
        </el-form-item>
        <el-form-item label="借方科目">
          <el-input v-model="adjForm.debit_account" />
        </el-form-item>
        <el-form-item label="贷方科目">
          <el-input v-model="adjForm.credit_account" />
        </el-form-item>
        <el-form-item label="金额">
          <el-input-number v-model="adjForm.amount" :min="0" :precision="2" :controls="false" style="width: 100%" />
        </el-form-item>
        <el-form-item label="现金流类别">
          <el-select v-model="adjForm.cash_flow_category" style="width: 100%">
            <el-option label="经营活动" value="operating" />
            <el-option label="投资活动" value="investing" />
            <el-option label="筹资活动" value="financing" />
            <el-option label="补充资料" value="supplementary" />
          </el-select>
        </el-form-item>
        <el-form-item label="现金流行项">
          <el-input v-model="adjForm.cash_flow_line_item" placeholder="如：销售商品收到的现金" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showAdjForm = false">取消</el-button>
        <el-button type="primary" @click="submitAdj" :loading="adjSubmitting">
          {{ editingAdj ? '保存' : '创建' }}
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  generateCFSWorksheet, getCFSWorksheet, getCFSReconciliation,
  createCFSAdjustment, updateCFSAdjustment, deleteCFSAdjustment as apiDeleteAdj,
  autoGenerateCFSAdjustments, getCFSIndirectMethod, getCFSVerify,
  type CFSWorksheetRow, type CFSReconciliation, type CFSIndirectMethod,
} from '@/services/auditPlatformApi'

const route = useRoute()
const projectId = computed(() => route.params.projectId as string)
const year = computed(() => Number(route.query.year) || new Date().getFullYear())

const loading = ref(false)
const genLoading = ref(false)
const autoLoading = ref(false)
const verifyLoading = ref(false)
const adjSubmitting = ref(false)

const worksheetRows = ref<CFSWorksheetRow[]>([])
const adjustments = ref<any[]>([])
const reconciliation = ref<CFSReconciliation | null>(null)
const indirectMethod = ref<CFSIndirectMethod | null>(null)
const verifyResult = ref<any>(null)

// Adjustment form
const showAdjForm = ref(false)
const editingAdj = ref<any>(null)
const adjForm = ref({
  description: '', debit_account: '', credit_account: '',
  amount: 0, cash_flow_category: 'operating', cash_flow_line_item: '',
})

function fmtAmt(v: string | number | null | undefined): string {
  if (v === null || v === undefined) return '-'
  const n = typeof v === 'string' ? parseFloat(v) || 0 : v
  if (n === 0) return '-'
  return n.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function categoryLabel(c: string) {
  const m: Record<string, string> = { operating: '经营', investing: '投资', financing: '筹资', supplementary: '补充' }
  return m[c] || c
}

function categoryTagType(c: string) {
  const m: Record<string, string> = { operating: '', investing: 'success', financing: 'warning', supplementary: 'info' }
  return m[c] || 'info'
}

async function fetchAll() {
  loading.value = true
  try {
    const wsData = await getCFSWorksheet(projectId.value, year.value)
    if (Array.isArray(wsData)) {
      worksheetRows.value = wsData
      adjustments.value = []
    } else {
      worksheetRows.value = wsData.worksheet_rows || wsData.rows || []
      adjustments.value = wsData.adjustments || []
    }
  } catch { worksheetRows.value = []; adjustments.value = [] }
  try { reconciliation.value = await getCFSReconciliation(projectId.value, year.value) } catch { /* */ }
  try { indirectMethod.value = await getCFSIndirectMethod(projectId.value, year.value) } catch { /* */ }
  loading.value = false
}

async function onGenerate() {
  genLoading.value = true
  try {
    await generateCFSWorksheet(projectId.value, year.value)
    ElMessage.success('工作底稿生成完成')
    await fetchAll()
  } finally { genLoading.value = false }
}

async function onAutoGenerate() {
  autoLoading.value = true
  try {
    await autoGenerateCFSAdjustments(projectId.value, year.value)
    ElMessage.success('自动调整项生成完成')
    await fetchAll()
  } finally { autoLoading.value = false }
}

async function onVerify() {
  verifyLoading.value = true
  try { verifyResult.value = await getCFSVerify(projectId.value, year.value) }
  finally { verifyLoading.value = false }
}

function editAdj(row: any) {
  editingAdj.value = row
  adjForm.value = {
    description: row.description || '',
    debit_account: row.debit_account,
    credit_account: row.credit_account,
    amount: parseFloat(row.amount) || 0,
    cash_flow_category: row.cash_flow_category,
    cash_flow_line_item: row.cash_flow_line_item || '',
  }
  showAdjForm.value = true
}

async function deleteAdj(row: any) {
  await ElMessageBox.confirm('确定删除该调整分录？', '确认')
  await apiDeleteAdj(row.id)
  ElMessage.success('删除成功')
  await fetchAll()
}

async function submitAdj() {
  adjSubmitting.value = true
  try {
    const body = { ...adjForm.value, project_id: projectId.value, year: year.value }
    if (editingAdj.value) {
      await updateCFSAdjustment(editingAdj.value.id, body)
      ElMessage.success('保存成功')
    } else {
      await createCFSAdjustment(body)
      ElMessage.success('创建成功')
    }
    showAdjForm.value = false
    editingAdj.value = null
    await fetchAll()
  } finally { adjSubmitting.value = false }
}

onMounted(fetchAll)
</script>

<style scoped>
.gt-cfs-worksheet { padding: var(--gt-space-4); }
.gt-cfs-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: var(--gt-space-4); }
.gt-cfs-actions { display: flex; gap: var(--gt-space-2); }
.gt-cfs-unallocated { color: var(--gt-color-coral); font-weight: 600; }
.gt-cfs-reconciliation-badge { margin-top: var(--gt-space-2); font-size: var(--gt-font-size-base); font-weight: 600; }
.gt-cfs-reconciliation-badge.gt-cfs-pass { color: var(--gt-color-success); }
.gt-cfs-reconciliation-badge.gt-cfs-fail { color: var(--gt-color-coral); }
.gt-cfs-verify-panel { background: var(--gt-color-bg-white); padding: var(--gt-space-3); border-radius: var(--gt-radius-sm); box-shadow: var(--gt-shadow-sm); }
.gt-cfs-verify-item { padding: 6px 0; font-size: var(--gt-font-size-base); }
.gt-cfs-verify-item.gt-cfs-pass { color: var(--gt-color-success); }
.gt-cfs-verify-item.gt-cfs-fail { color: var(--gt-color-coral); }
.gt-cfs-verify-diff { margin-left: var(--gt-space-2); font-weight: 600; }
:deep(.total-row) { background-color: #e8e0f0 !important; font-weight: 700; }
</style>
