<template>
  <div class="component-auditor-view">
    <!-- View Mode Toggle -->
    <div class="view-toggle">
      <el-radio-group v-model="viewMode" size="small">
        <el-radio-button label="table">表格视图</el-radio-button>
        <el-radio-button label="panel">三栏面板视图</el-radio-button>
      </el-radio-group>
    </div>

    <!-- Dashboard Cards (always visible) -->
    <el-row :gutter="16" class="dashboard-cards" v-if="store.dashboard || viewMode === 'panel'">
      <el-col :span="6" v-for="s in statusCards" :key="s.status">
        <el-card shadow="hover" class="dash-card">
          <div class="dash-value">{{ s.count }}</div>
          <div class="dash-label">{{ s.label }}</div>
        </el-card>
      </el-col>
    </el-row>

    <!-- ─── Table View (legacy) ─────────────────────────────────────── -->
    <template v-if="viewMode === 'table'">
      <div class="section-header">
        <h3>组成部分审计师</h3>
        <el-button type="primary" size="small" @click="showAuditorDialog()">新增审计师</el-button>
      </div>

      <el-table :data="store.auditors" v-loading="store.loading" border stripe size="small">
        <el-table-column prop="component_name" label="组成部分" width="180" />
        <el-table-column prop="auditor_name" label="审计师姓名" width="120" />
        <el-table-column prop="auditor_email" label="邮箱" min-width="200" />
        <el-table-column prop="scope" label="审计范围" min-width="160" />
        <el-table-column prop="status" label="状态" width="120">
          <template #default="{ row }">
            <el-tag :type="statusType(row.status)" size="small">{{ row.status }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="140" fixed="right">
          <template #default="{ row }">
            <el-button size="small" text @click="showAuditorDialog(row)">编辑</el-button>
            <el-button type="danger" size="small" text @click="onDeleteAuditor(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="section-header" style="margin-top: 24px">
        <h3>审计指令</h3>
        <el-button type="primary" size="small" @click="showInstructionDialog()">新增指令</el-button>
      </div>

      <el-table :data="store.instructions" v-loading="store.loading" border stripe size="small">
        <el-table-column prop="instruction_no" label="编号" width="100" />
        <el-table-column prop="content" label="内容" min-width="300" show-overflow-tooltip />
        <el-table-column prop="issued_date" label="发出日期" width="120" />
        <el-table-column prop="due_date" label="截止日期" width="120" />
        <el-table-column prop="status" label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="statusType(row.status)" size="small">{{ row.status }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="140" fixed="right">
          <template #default="{ row }">
            <el-button size="small" text @click="showInstructionDialog(row)">编辑</el-button>
            <el-button type="danger" size="small" text @click="onDeleteInstruction(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="section-header" style="margin-top: 24px">
        <h3>审计结果</h3>
        <el-button type="primary" size="small" @click="showResultDialog()">新增结果</el-button>
      </div>

      <el-table :data="store.results" v-loading="store.loading" border stripe size="small">
        <el-table-column prop="result_no" label="编号" width="100" />
        <el-table-column prop="summary" label="摘要" min-width="300" show-overflow-tooltip />
        <el-table-column prop="received_date" label="收到日期" width="120" />
        <el-table-column prop="status" label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="statusType(row.status)" size="small">{{ row.status }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="140" fixed="right">
          <template #default="{ row }">
            <el-button size="small" text @click="showResultDialog(row)">编辑</el-button>
            <el-button type="danger" size="small" text @click="onDeleteResult(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </template>

    <!-- ─── Three-Column Panel View (Task 17) ───────────────────────── -->
    <template v-else>
      <ComponentAuditorPanel
        ref="auditorPanelRef"
        :project-id="projectId"
        @auditor-selected="onAuditorSelected"
        @instruction-selected="onInstructionSelected"
        @auditor-add="showAuditorDialog()"
        @auditor-edit="showAuditorDialog"
        @instruction-add="onInstructionAdd"
        @instruction-edit="showInstructionDialog"
        @result-add="onResultAdd"
        @result-edit="showResultDialog"
      />
    </template>

    <!-- 审计师弹窗 -->
    <el-dialog v-model="auditorDialogVisible" :title="editingAuditor ? '编辑审计师' : '新增审计师'" width="520px">
      <el-form :model="auditorForm" label-width="100px">
        <el-form-item label="组成部分"><el-input v-model="auditorForm.component_name" /></el-form-item>
        <el-form-item label="审计师姓名"><el-input v-model="auditorForm.auditor_name" /></el-form-item>
        <el-form-item label="邮箱"><el-input v-model="auditorForm.auditor_email" /></el-form-item>
        <el-form-item label="审计范围"><el-input v-model="auditorForm.scope" /></el-form-item>
        <el-form-item label="状态">
          <el-select v-model="auditorForm.status">
            <el-option label="待开始" value="pending" />
            <el-option label="进行中" value="in_progress" />
            <el-option label="已完成" value="completed" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="auditorDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="onSaveAuditor">保存</el-button>
      </template>
    </el-dialog>

    <!-- 指令弹窗 (legacy inline + InstructionForm component) -->
    <InstructionForm
      v-model:visible="instructionFormVisible"
      :instruction="editingInstruction"
      :component-auditor-id="selectedAuditorId"
      @saved="onInstructionSaved"
    />

    <!-- 结果弹窗 (legacy inline + ComponentResultForm component) -->
    <ComponentResultForm
      v-model:visible="resultFormVisible"
      :result="editingResult"
      :project-id="projectId"
      @saved="onResultSaved"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useConsolidationStore } from '@/stores/consolidation'
import {
  createComponentAuditor, updateComponentAuditor, deleteComponentAuditor,
  createInstruction, updateInstruction, deleteInstruction,
  createResult, updateResult, deleteResult,
} from '@/services/consolidationApi'
import type { ComponentAuditor, Instruction, InstructionResult } from '@/services/consolidationApi'
import ComponentAuditorPanel from '@/components/consolidation/ComponentAuditorPanel.vue'
import InstructionForm from '@/components/consolidation/InstructionForm.vue'
import ComponentResultForm from '@/components/consolidation/ComponentResultForm.vue'

const props = defineProps<{ projectId: string }>()
const store = useConsolidationStore()

// ─── View Mode Toggle ────────────────────────────────────────────────────────
const viewMode = ref<'table' | 'panel'>('panel')
const auditorPanelRef = ref<InstanceType<typeof ComponentAuditorPanel>>()

// ─── Dialogs ─────────────────────────────────────────────────────────────────
const auditorDialogVisible = ref(false)
const instructionFormVisible = ref(false)
const resultFormVisible = ref(false)
const editingAuditor = ref<ComponentAuditor | null>(null)
const editingInstruction = ref<Instruction | null>(null)
const editingResult = ref<InstructionResult | null>(null)
const selectedAuditorId = ref('')

// ─── Legacy Forms ─────────────────────────────────────────────────────────────
const auditorForm = ref({ component_name: '', auditor_name: '', auditor_email: '', scope: '', status: 'pending', component_auditor_id: '' })
const instructionForm = ref({ instruction_no: '', content: '', issued_date: '', due_date: '', status: 'pending', component_auditor_id: '' })
const resultForm = ref({ result_no: '', summary: '', received_date: '', status: 'pending', instruction_id: '', component_auditor_id: '' })

const statusCards = computed(() => [
  { label: '待开始', status: 'pending', count: store.auditorsByStatus.pending.length },
  { label: '进行中', status: 'in_progress', count: store.auditorsByStatus.in_progress.length },
  { label: '已完成', status: 'completed', count: store.auditorsByStatus.completed.length },
  { label: '总计', status: 'total', count: store.auditors.length },
])

function statusType(s: string) {
  const map: Record<string, any> = { pending: 'info', in_progress: 'warning', completed: 'success', issued: '', responded: 'success', submitted: 'warning', reviewed: 'success' }
  return map[s] || ''
}

function showAuditorDialog(row?: ComponentAuditor) {
  editingAuditor.value = row || null
  if (row) {
    auditorForm.value = { component_name: row.component_name, auditor_name: row.auditor_name, auditor_email: row.auditor_email, scope: row.scope, status: row.status, component_auditor_id: row.id }
  } else {
    auditorForm.value = { component_name: '', auditor_name: '', auditor_email: '', scope: '', status: 'pending', component_auditor_id: '' }
  }
  auditorDialogVisible.value = true
}

function showInstructionDialog(row?: Instruction) {
  editingInstruction.value = row || null
  instructionFormVisible.value = true
}

function onInstructionAdd(auditorId: string) {
  editingInstruction.value = null
  selectedAuditorId.value = auditorId
  instructionFormVisible.value = true
}

function onResultAdd(instructionId: string) {
  editingResult.value = null
  resultFormVisible.value = true
}

function showResultDialog(row?: InstructionResult) {
  editingResult.value = row || null
  resultFormVisible.value = true
}

function onAuditorSelected(auditor: ComponentAuditor) {
  selectedAuditorId.value = auditor.id
}

function onInstructionSelected(instruction: Instruction) {
  // no-op for now
}

async function onInstructionSaved(instruction: Instruction) {
  await store.fetchInstructions(props.projectId)
  auditorPanelRef.value?.loadInstructions(instruction.component_auditor_id)
}

async function onResultSaved(result: InstructionResult) {
  await store.fetchResults(props.projectId)
  auditorPanelRef.value?.loadResults(result.instruction_id)
}

async function onSaveAuditor() {
  try {
    if (editingAuditor.value) {
      await updateComponentAuditor(editingAuditor.value.id, props.projectId, auditorForm.value)
      ElMessage.success('更新成功')
    } else {
      await createComponentAuditor(props.projectId, { ...auditorForm.value, project_id: props.projectId })
      ElMessage.success('创建成功')
    }
    auditorDialogVisible.value = false
    await store.fetchAuditors(props.projectId)
    auditorPanelRef.value?.loadAuditors()
  } catch { ElMessage.error('保存失败') }
}

async function onDeleteAuditor(row: ComponentAuditor) {
  await ElMessageBox.confirm('确认删除？', '提示')
  await deleteComponentAuditor(row.id, props.projectId)
  store.auditors = store.auditors.filter(a => a.id !== row.id)
  auditorPanelRef.value?.loadAuditors()
  ElMessage.success('删除成功')
}

async function onDeleteInstruction(row: Instruction) {
  await ElMessageBox.confirm('确认删除？', '提示')
  await deleteInstruction(row.id, props.projectId)
  store.instructions = store.instructions.filter(i => i.id !== row.id)
  auditorPanelRef.value?.loadInstructions(row.component_auditor_id)
  ElMessage.success('删除成功')
}

async function onDeleteResult(row: InstructionResult) {
  await ElMessageBox.confirm('确认删除？', '提示')
  await deleteResult(row.id, props.projectId)
  store.results = store.results.filter(r => r.id !== row.id)
  auditorPanelRef.value?.loadResults(row.instruction_id)
  ElMessage.success('删除成功')
}

onMounted(async () => {
  await Promise.all([
    store.fetchAuditors(props.projectId),
    store.fetchInstructions(props.projectId),
    store.fetchResults(props.projectId),
    store.fetchDashboard(props.projectId),
  ])
})
</script>

<style scoped>
.component-auditor-view { display: flex; flex-direction: column; gap: var(--gt-space-3); }

.view-toggle {
  display: flex;
  align-items: center;
  justify-content: flex-end;
}

.section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: var(--gt-space-2); }
.section-header h3 { margin: 0; font-size: 16px; color: var(--gt-color-primary-dark); }
.dashboard-cards { margin-bottom: var(--gt-space-4); }
.dash-card { text-align: center; }
.dash-value { font-size: 28px; font-weight: bold; color: var(--gt-color-primary); }
.dash-label { font-size: 13px; color: #666; margin-top: 4px; }
</style>
