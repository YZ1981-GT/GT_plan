<template>
  <div class="gt-cfs-worksheet gt-fade-in">
    <GtPageHeader title="现金流量表" :show-back="false">
      <template #actions>
        <el-button size="small" @click="onGenerate" :loading="genLoading">生成底稿</el-button>
        <el-button size="small" @click="onAutoGenerate" :loading="autoLoading">自动调整项</el-button>
        <el-button size="small" @click="showAdjForm = true">新建调整</el-button>
      </template>
    </GtPageHeader>

    <!-- 平衡状态 -->
    <el-alert v-if="reconciliation" :type="reconciliation.balanced ? 'success' : 'warning'"
      :title="reconciliation.balanced ? '✓ 工作底稿已平衡' : '✗ 工作底稿未平衡'" :closable="false"
      show-icon style="margin-bottom: 12px" />

    <!-- 工作底稿表格 -->
    <el-alert
      v-if="!loading && worksheetRows.length === 0"
      type="info" show-icon :closable="false" style="margin-bottom: 12px"
    >
      <template #title>工作底稿暂无数据</template>
      <div style="font-size: var(--gt-font-size-xs); line-height: 1.6">请先点击"生成工作底稿"按钮，系统将从试算表自动生成现金流量表工作底稿。</div>
    </el-alert>
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
          <el-tag size="small" :type="(categoryTagType(row.cash_flow_category)) || undefined">
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
          :row-class-name="({ row }: any) => row.is_total ? 'total-row' : ''">
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
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { confirmDelete } from '@/utils/confirm'
import {
  generateCFSWorksheet, getCFSWorksheet, getCFSReconciliation,
  createCFSAdjustment, updateCFSAdjustment, deleteCFSAdjustment as apiDeleteAdj,
  autoGenerateCFSAdjustments, getCFSIndirectMethod, getCFSVerify,
  type CFSWorksheetRow, type CFSReconciliation, type CFSIndirectMethod,
} from '@/services/auditPlatformApi'
import { useProjectSelector } from '@/composables/useProjectSelector'
import { useEditMode } from '@/composables/useEditMode'
import { fmtAmount } from '@/utils/formatters'

const route = useRoute()
const router = useRouter()
const year = computed(() => Number(route.query.year) || new Date().getFullYear())

const {
  projectId, selectedProjectId, projectOptions, selectedYear, yearOptions,
  onProjectChange, onYearChange, loadProjectOptions, syncFromRoute,
} = useProjectSelector('cfs-worksheet')

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
const { isEditing, isDirty, enterEdit, exitEdit, markDirty, clearDirty } = useEditMode()
const adjForm = ref({
  description: '', debit_account: '', credit_account: '',
  amount: 0, cash_flow_category: 'operating', cash_flow_line_item: '',
})

const fmtAmt = fmtAmount

function categoryLabel(c: string) {
  const m: Record<string, string> = { operating: '经营', investing: '投资', financing: '筹资', supplementary: '补充' }
  return m[c] || c
}

function categoryTagType(c: string): '' | 'success' | 'warning' | 'info' | 'danger' | 'primary' {
  const m: Record<string, '' | 'success' | 'warning' | 'info' | 'danger' | 'primary'> = { operating: '', investing: 'success', financing: 'warning', supplementary: 'info' }
  return m[c] || 'info'
}

async function fetchAll() {
  loading.value = true
  try {
    const wsData = await getCFSWorksheet(projectId.value, year.value) as any
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
  await confirmDelete('该调整分录')
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

onMounted(() => {
  syncFromRoute()
  loadProjectOptions()
  fetchAll()
})
</script>

<style scoped>
.gt-cfs-worksheet { padding: var(--gt-space-5); }

/* ── 页面横幅 ── */
.gt-cfs-banner {
  display: flex; flex-direction: column; gap: 10px;
  background: var(--gt-gradient-primary);
  border-radius: var(--gt-radius-lg);
  padding: 18px 28px;
  margin-bottom: var(--gt-space-5);
  color: var(--gt-color-text-inverse);
  position: relative; overflow: hidden;
  box-shadow: 0 4px 20px rgba(75, 45, 119, 0.2);
  background-image: var(--gt-gradient-primary), linear-gradient(rgba(255,255,255,0.03) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.03) 1px, transparent 1px);
  background-size: 100% 100%, 20px 20px, 20px 20px;
}
.gt-cfs-banner::before {
  content: '';
  position: absolute; top: -40%; right: -10%;
  width: 45%; height: 180%;
  background: radial-gradient(ellipse, rgba(255,255,255,0.07) 0%, transparent 65%);
  pointer-events: none;
}
.gt-cfs-banner-text h2 { margin: 0 0 2px; font-size: var(--gt-font-size-xl); font-weight: 700; }
.gt-cfs-banner-text p { margin: 0; font-size: var(--gt-font-size-xs); opacity: 0.75; }
.gt-cfs-banner-row1 {
  display: flex; align-items: center; gap: 16px;
  position: relative; z-index: 1;
}
.gt-cfs-title { margin: 0; font-size: var(--gt-font-size-xl); font-weight: 700; white-space: nowrap; }
.gt-cfs-info-bar { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.gt-cfs-info-item { display: flex; align-items: center; gap: 4px; }
.gt-cfs-info-label { font-size: var(--gt-font-size-xs); opacity: 0.8; white-space: nowrap; }
.gt-cfs-info-badge { font-size: var(--gt-font-size-xs); background: rgba(255,255,255,0.18); padding: 2px 10px; border-radius: 10px; white-space: nowrap; }
.gt-cfs-info-sep { width: 1px; height: 16px; background: rgba(255,255,255,0.25); }
.gt-cfs-unit-select, .gt-cfs-year-select { width: 160px; }
.gt-cfs-unit-select :deep(.el-input__wrapper),
.gt-cfs-year-select :deep(.el-input__wrapper) {
  background: rgba(255,255,255,0.15) !important;
  border: 1px solid rgba(255,255,255,0.25) !important;
  box-shadow: none !important;
}
.gt-cfs-unit-select :deep(.el-input__inner),
.gt-cfs-year-select :deep(.el-input__inner) { color: var(--gt-color-text-inverse) !important; font-size: var(--gt-font-size-xs); }
.gt-cfs-unit-select :deep(.el-input__suffix),
.gt-cfs-year-select :deep(.el-input__suffix) { color: rgba(255,255,255,0.7) !important; }
.gt-cfs-banner-row2 {
  display: flex; gap: 8px; align-items: center;
  position: relative; z-index: 1;
}
.gt-cfs-banner-row2 .el-button { background: rgba(255,255,255,0.15); border: 1px solid rgba(255,255,255,0.25); color: #fff; }
.gt-cfs-banner-row2 .el-button:hover { background: rgba(255,255,255,0.25); }
.gt-cfs-banner-actions {
  display: flex; gap: 8px; align-items: center;
  position: relative; z-index: 1;
}
.gt-cfs-banner-actions .el-button { background: rgba(255,255,255,0.15); border: 1px solid rgba(255,255,255,0.25); color: #fff; }
.gt-cfs-banner-actions .el-button:hover { background: rgba(255,255,255,0.25); }
.gt-cfs-actions { display: flex; gap: var(--gt-space-2); }
.gt-cfs-unallocated { color: var(--gt-color-coral); font-weight: 600; }

.gt-cfs-reconciliation-badge {
  margin-top: var(--gt-space-3); font-size: var(--gt-font-size-base); font-weight: 600;
  display: inline-flex; align-items: center; gap: 6px;
  padding: 6px 14px; border-radius: var(--gt-radius-full);
}
.gt-cfs-reconciliation-badge.gt-cfs-pass { color: var(--gt-color-success); background: var(--gt-color-success-light); }
.gt-cfs-reconciliation-badge.gt-cfs-fail { color: var(--gt-color-coral); background: var(--gt-color-coral-light); }

.gt-cfs-verify-panel {
  background: var(--gt-color-bg-white); padding: var(--gt-space-4);
  border-radius: var(--gt-radius-md); box-shadow: var(--gt-shadow-sm);
  border: 1px solid rgba(75, 45, 119, 0.04);
}
.gt-cfs-verify-item {
  padding: 8px 12px; font-size: var(--gt-font-size-base);
  border-radius: var(--gt-radius-sm); margin-bottom: 4px;
  transition: background var(--gt-transition-fast);
}
.gt-cfs-verify-item:hover { background: var(--gt-color-bg); }
.gt-cfs-verify-item.gt-cfs-pass { color: var(--gt-color-success); }
.gt-cfs-verify-item.gt-cfs-fail { color: var(--gt-color-coral); }
.gt-cfs-verify-diff { margin-left: var(--gt-space-2); font-weight: 700; }

:deep(.total-row) {
  background: linear-gradient(90deg, #ece4f5, #e8e0f0) !important;
  font-weight: 700;
}
:deep(.total-row td) { border-bottom: 2px solid var(--gt-color-primary-lighter) !important; }
:deep(.el-tabs__item.is-active) { font-weight: 600; }
</style>
