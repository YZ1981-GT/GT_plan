<template>
  <div class="misstatements-page">
    <div class="ms-header">
      <h2 class="ms-title">未更正错报汇总</h2>
      <el-button type="primary" @click="openCreateDialog">新增错报</el-button>
    </div>

    <!-- 重要性水平对比卡片 -->
    <div class="materiality-cards" v-if="summary">
      <div class="mat-card">
        <span class="mat-label">累计错报金额</span>
        <span class="mat-value" :class="{ exceeded: summary.exceeds_materiality }">
          {{ fmtAmt(summary.cumulative_amount) }}
        </span>
      </div>
      <div class="mat-card">
        <span class="mat-label">整体重要性</span>
        <span class="mat-value">{{ fmtAmt(summary.overall_materiality) }}</span>
      </div>
      <div class="mat-card">
        <span class="mat-label">实际执行重要性</span>
        <span class="mat-value">{{ fmtAmt(summary.performance_materiality) }}</span>
      </div>
      <div class="mat-card">
        <span class="mat-label">微小错报临界值</span>
        <span class="mat-value">{{ fmtAmt(summary.trivial_threshold) }}</span>
      </div>
      <div class="mat-card">
        <span class="mat-label">评价完整性</span>
        <span class="mat-value" :class="summary.evaluation_complete ? 'complete' : 'incomplete'">
          {{ summary.evaluation_complete ? '✓ 完整' : '✗ 不完整' }}
        </span>
      </div>
    </div>

    <!-- 超限预警横幅 -->
    <el-alert v-if="summary?.exceeds_materiality" type="error" :closable="false"
      class="threshold-warning" show-icon>
      未更正错报累计金额({{ fmtAmt(summary.cumulative_amount) }})已达到或超过整体重要性水平({{ fmtAmt(summary.overall_materiality) }})，可能需要出具保留意见或否定意见
    </el-alert>

    <!-- 按类型分组小计 -->
    <div class="type-summary" v-if="summary?.by_type?.length">
      <el-table :data="summary.by_type" border size="small" style="margin-bottom: 16px">
        <el-table-column label="错报类型" width="150">
          <template #default="{ row }">
            <el-tag :type="typeTagType(row.misstatement_type)" size="small">
              {{ typeLabel(row.misstatement_type) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="count" label="数量" width="80" align="center" />
        <el-table-column label="小计金额" align="right">
          <template #default="{ row }">{{ fmtAmt(row.total_amount) }}</template>
        </el-table-column>
      </el-table>
    </div>

    <!-- 错报列表 -->
    <el-table :data="items" v-loading="loading" border stripe style="width: 100%">
      <el-table-column prop="misstatement_description" label="错报描述" min-width="200" show-overflow-tooltip />
      <el-table-column label="类型" width="100">
        <template #default="{ row }">
          <el-tag :type="typeTagType(row.misstatement_type)" size="small">
            {{ typeLabel(row.misstatement_type) }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="affected_account_code" label="科目编码" width="120" />
      <el-table-column prop="affected_account_name" label="科目名称" width="140" show-overflow-tooltip />
      <el-table-column label="金额" width="130" align="right">
        <template #default="{ row }">{{ fmtAmt(row.misstatement_amount) }}</template>
      </el-table-column>
      <el-table-column label="结转" width="70" align="center">
        <template #default="{ row }">
          <el-tag v-if="row.is_carried_forward" type="info" size="small">结转</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="management_reason" label="管理层原因" min-width="150" show-overflow-tooltip />
      <el-table-column prop="auditor_evaluation" label="审计师评价" min-width="150" show-overflow-tooltip />
      <el-table-column label="操作" width="180" fixed="right">
        <template #default="{ row }">
          <el-button size="small" @click="openEditDialog(row)">编辑</el-button>
          <el-button size="small" type="danger" @click="onDelete(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 新建/编辑弹窗 -->
    <el-dialog v-model="formVisible" :title="isEditing ? '编辑错报' : '新增错报'" width="600px" destroy-on-close>
      <el-form :model="form" label-width="100px">
        <el-form-item label="错报类型">
          <el-select v-model="form.misstatement_type" style="width: 100%">
            <el-option label="事实错报" value="factual" />
            <el-option label="判断错报" value="judgmental" />
            <el-option label="推断错报" value="projected" />
          </el-select>
        </el-form-item>
        <el-form-item label="错报描述">
          <el-input v-model="form.misstatement_description" type="textarea" :rows="2" />
        </el-form-item>
        <el-form-item label="科目编码">
          <el-input v-model="form.affected_account_code" />
        </el-form-item>
        <el-form-item label="科目名称">
          <el-input v-model="form.affected_account_name" />
        </el-form-item>
        <el-form-item label="错报金额">
          <el-input-number v-model="form.misstatement_amount" :precision="2" :controls="false" style="width: 100%" />
        </el-form-item>
        <el-form-item label="管理层原因">
          <el-input v-model="form.management_reason" type="textarea" :rows="2" placeholder="管理层不调整的原因" />
        </el-form-item>
        <el-form-item label="审计师评价">
          <el-input v-model="form.auditor_evaluation" type="textarea" :rows="2" placeholder="审计师对管理层原因的评价" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="formVisible = false">取消</el-button>
        <el-button type="primary" @click="onSubmit" :loading="submitLoading"
          :disabled="!form.misstatement_description || !form.misstatement_amount">
          {{ isEditing ? '保存' : '创建' }}
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
  listMisstatements, createMisstatement, updateMisstatement,
  deleteMisstatement, getMisstatementSummary,
  type MisstatementItem, type MisstatementSummaryData,
} from '@/services/auditPlatformApi'

const route = useRoute()
const projectId = computed(() => route.params.projectId as string)
const year = computed(() => Number(route.query.year) || new Date().getFullYear())

const loading = ref(false)
const submitLoading = ref(false)
const items = ref<MisstatementItem[]>([])
const summary = ref<MisstatementSummaryData | null>(null)

const formVisible = ref(false)
const isEditing = ref(false)
const editingId = ref('')
const form = ref({
  misstatement_type: 'factual',
  misstatement_description: '',
  affected_account_code: '',
  affected_account_name: '',
  misstatement_amount: 0,
  management_reason: '',
  auditor_evaluation: '',
})

function fmtAmt(v: string | number | null | undefined): string {
  if (v === null || v === undefined) return '-'
  const n = typeof v === 'string' ? parseFloat(v) || 0 : v
  if (n === 0) return '-'
  return n.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function typeLabel(t: string) {
  const m: Record<string, string> = { factual: '事实错报', judgmental: '判断错报', projected: '推断错报' }
  return m[t] || t
}

function typeTagType(t: string) {
  const m: Record<string, string> = { factual: 'danger', judgmental: 'warning', projected: 'info' }
  return m[t] || 'info'
}

async function fetchItems() {
  loading.value = true
  try {
    items.value = await listMisstatements(projectId.value, year.value)
  } finally {
    loading.value = false
  }
}

async function fetchSummary() {
  try {
    summary.value = await getMisstatementSummary(projectId.value, year.value)
  } catch { /* ignore */ }
}

function openCreateDialog() {
  isEditing.value = false
  editingId.value = ''
  form.value = {
    misstatement_type: 'factual',
    misstatement_description: '',
    affected_account_code: '',
    affected_account_name: '',
    misstatement_amount: 0,
    management_reason: '',
    auditor_evaluation: '',
  }
  formVisible.value = true
}

function openEditDialog(row: MisstatementItem) {
  isEditing.value = true
  editingId.value = row.id
  form.value = {
    misstatement_type: row.misstatement_type,
    misstatement_description: row.misstatement_description,
    affected_account_code: row.affected_account_code || '',
    affected_account_name: row.affected_account_name || '',
    misstatement_amount: parseFloat(String(row.misstatement_amount)) || 0,
    management_reason: row.management_reason || '',
    auditor_evaluation: row.auditor_evaluation || '',
  }
  formVisible.value = true
}

async function onSubmit() {
  submitLoading.value = true
  try {
    const body = {
      ...form.value,
      misstatement_amount: String(form.value.misstatement_amount),
    }
    if (isEditing.value) {
      await updateMisstatement(projectId.value, editingId.value, body)
      ElMessage.success('保存成功')
    } else {
      await createMisstatement(projectId.value, { ...body, year: year.value })
      ElMessage.success('创建成功')
    }
    formVisible.value = false
    fetchItems()
    fetchSummary()
  } finally {
    submitLoading.value = false
  }
}

async function onDelete(row: MisstatementItem) {
  await ElMessageBox.confirm('确定删除该错报记录？', '确认')
  await deleteMisstatement(projectId.value, row.id)
  ElMessage.success('删除成功')
  fetchItems()
  fetchSummary()
}

onMounted(() => {
  fetchItems()
  fetchSummary()
})
</script>

<style scoped>
.misstatements-page { padding: 16px; }
.ms-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }
.ms-title { margin: 0; color: var(--gt-color-primary); font-size: 20px; }
.materiality-cards { display: flex; gap: 12px; margin-bottom: 16px; flex-wrap: wrap; }
.mat-card {
  background: #fff; border-radius: var(--gt-radius-sm); padding: 12px 16px;
  box-shadow: var(--gt-shadow-sm); min-width: 130px; text-align: center;
}
.mat-label { display: block; font-size: 12px; color: #999; }
.mat-value { display: block; font-size: 18px; font-weight: 600; color: var(--gt-color-primary); }
.mat-value.exceeded { color: var(--gt-color-coral, #e74c3c); }
.mat-value.complete { color: var(--gt-color-success, #27ae60); }
.mat-value.incomplete { color: var(--gt-color-coral, #e74c3c); }
.threshold-warning { margin-bottom: 16px; }
.type-summary { margin-bottom: 8px; }
</style>
