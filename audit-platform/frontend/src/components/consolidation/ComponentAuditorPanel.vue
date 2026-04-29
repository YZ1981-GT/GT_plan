<template>
  <div class="auditor-panel">
    <!-- Column 1: Auditor List -->
    <div class="panel-column auditor-column">
      <div class="column-header">
        <span class="column-title">审计师列表</span>
        <el-button size="small" type="primary" @click="handleAddAuditor">新增</el-button>
      </div>
      <div class="auditor-list" v-loading="loadingAuditors">
        <div
          v-for="auditor in auditors"
          :key="auditor.id"
          class="auditor-card"
          :class="{ 'is-selected': selectedAuditor?.id === auditor.id }"
          @click="selectAuditor(auditor)"
        >
          <div class="auditor-card-header">
            <span class="auditor-name">{{ auditor.auditor_name }}</span>
            <el-tag :type="statusTagType(auditor.status)" size="small" class="status-badge">
              {{ statusLabel(auditor.status) }}
            </el-tag>
          </div>
          <div class="auditor-email">{{ auditor.auditor_email }}</div>
          <div class="auditor-component">
            <span class="component-label">组成部分：</span>{{ auditor.component_name }}
          </div>
          <div class="auditor-footer">
            <span
              class="rating-indicator"
              :class="`rating-${qualificationRating(auditor)}`"
              :title="`资质评级：${qualificationLabel(qualificationRating(auditor))}`"
            >
              {{ qualificationLabel(qualificationRating(auditor)) }}
            </span>
            <div class="scope-tags" v-if="auditor.scope">
              <el-tag size="small" type="info" class="scope-tag">{{ auditor.scope }}</el-tag>
            </div>
          </div>
        </div>
        <el-empty v-if="!loadingAuditors && auditors.length === 0" description="暂无审计师" />
      </div>
    </div>

    <!-- Column 2: Instruction Management -->
    <div class="panel-column instruction-column">
      <div class="column-header">
        <span class="column-title">审计指令</span>
        <el-button
          size="small"
          type="primary"
          :disabled="!selectedAuditor"
          @click="handleAddInstruction"
        >
          新增指令
        </el-button>
      </div>
      <div class="instruction-list" v-loading="loadingInstructions">
        <el-table
          :data="instructions"
          size="small"
          border
          stripe
          :max-height="420"
          @row-click="selectInstruction"
          highlight-current-row
          :row-class-name="instructionRowClass"
        >
          <el-table-column prop="instruction_no" label="编号" width="90" />
          <el-table-column prop="issued_date" label="发出日期" width="100" />
          <el-table-column prop="due_date" label="截止日期" width="100" />
          <el-table-column prop="status" label="状态" width="90">
            <template #default="{ row }">
              <el-tag :type="instructionStatusType(row.status)" size="small">
                {{ instructionStatusLabel(row.status) }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="80" fixed="right">
            <template #default="{ row }">
              <el-button size="small" text type="primary" @click.stop="handleEditInstruction(row)">
                编辑
              </el-button>
            </template>
          </el-table-column>
        </el-table>
        <el-empty
          v-if="!loadingInstructions && instructions.length === 0"
          :description="selectedAuditor ? '暂无指令' : '请先选择审计师'"
        />
      </div>
    </div>

    <!-- Column 3: Result Management -->
    <div class="panel-column result-column">
      <div class="column-header">
        <span class="column-title">审计结果</span>
        <el-button
          size="small"
          type="primary"
          :disabled="!selectedInstruction"
          @click="handleAddResult"
        >
          新增结果
        </el-button>
      </div>
      <div class="result-list" v-loading="loadingResults">
        <el-table
          :data="results"
          size="small"
          border
          stripe
          :max-height="420"
        >
          <el-table-column prop="result_no" label="编号" width="80" />
          <el-table-column prop="received_date" label="收到日期" width="100" />
          <el-table-column prop="summary" label="摘要" min-width="140" show-overflow-tooltip />
          <el-table-column prop="status" label="状态" width="80">
            <template #default="{ row }">
              <el-tag :type="resultStatusType(row.status)" size="small">
                {{ resultStatusLabel(row.status) }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="附件" width="60">
            <template #default="{ row }">
              <el-tag v-if="row.attachments && row.attachments.length > 0" type="info" size="small">
                {{ row.attachments.length }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="80" fixed="right">
            <template #default="{ row }">
              <el-button size="small" text type="primary" @click.stop="handleEditResult(row)">
                编辑
              </el-button>
            </template>
          </el-table-column>
        </el-table>
        <el-empty
          v-if="!loadingResults && results.length === 0"
          :description="selectedInstruction ? '暂无结果' : '请先选择指令'"
        />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import {
  getComponentAuditors,
  getInstructions,
  getResults,
} from '@/services/consolidationApi'
import type { ComponentAuditor, Instruction, InstructionResult } from '@/services/consolidationApi'

// ─── Props & Emits ───────────────────────────────────────────────────────────
const props = defineProps<{
  projectId: string
}>()

const emit = defineEmits<{
  'auditor-selected': [auditor: ComponentAuditor]
  'instruction-selected': [instruction: Instruction]
  'auditor-add': []
  'auditor-edit': [auditor: ComponentAuditor]
  'instruction-add': [auditorId: string]
  'instruction-edit': [instruction: Instruction]
  'result-add': [instructionId: string]
  'result-edit': [result: InstructionResult]
}>()

// ─── State ───────────────────────────────────────────────────────────────────
const auditors = ref<ComponentAuditor[]>([])
const selectedAuditor = ref<ComponentAuditor | null>(null)
const selectedInstruction = ref<Instruction | null>(null)
const loadingAuditors = ref(false)
const loadingInstructions = ref(false)
const loadingResults = ref(false)
const instructions = ref<Instruction[]>([])
const results = ref<InstructionResult[]>([])

// ─── Data Loading ────────────────────────────────────────────────────────────
async function loadAuditors() {
  loadingAuditors.value = true
  try {
    auditors.value = await getComponentAuditors(props.projectId)
  } catch {
    ElMessage.error('加载审计师列表失败')
  } finally {
    loadingAuditors.value = false
  }
}

async function loadInstructions(auditorId: string) {
  loadingInstructions.value = true
  try {
    // Filter instructions for the selected auditor
    const all = await getInstructions(props.projectId)
    instructions.value = all.filter(i => i.component_auditor_id === auditorId)
  } catch {
    ElMessage.error('加载审计指令失败')
  } finally {
    loadingInstructions.value = false
  }
}

async function loadResults(instructionId: string) {
  loadingResults.value = true
  try {
    // Filter results for the selected instruction
    const all = await getResults(props.projectId)
    results.value = all.filter(r => r.instruction_id === instructionId)
  } catch {
    ElMessage.error('加载审计结果失败')
  } finally {
    loadingResults.value = false
  }
}

// ─── Auditor Selection ───────────────────────────────────────────────────────
function selectAuditor(auditor: ComponentAuditor) {
  selectedAuditor.value = auditor
  selectedInstruction.value = null
  results.value = []
  loadInstructions(auditor.id)
  emit('auditor-selected', auditor)
}

// ─── Instruction Selection ──────────────────────────────────────────────────
function selectInstruction(row: Instruction) {
  selectedInstruction.value = row
  loadResults(row.id)
  emit('instruction-selected', row)
}

// ─── Qualification Rating Helpers ────────────────────────────────────────────
function qualificationRating(auditor: ComponentAuditor): 'excellent' | 'good' | 'fair' | 'poor' {
  // Derive from auditor scope or default to 'good'
  const scope = auditor.scope?.toLowerCase() || ''
  if (scope.includes('excellent') || scope.includes('优秀')) return 'excellent'
  if (scope.includes('good') || scope.includes('良好')) return 'good'
  if (scope.includes('fair') || scope.includes('一般')) return 'fair'
  return 'poor'
}

function qualificationLabel(rating: string): string {
  const map: Record<string, string> = {
    excellent: '优秀',
    good: '良好',
    fair: '一般',
    poor: '较差',
  }
  return map[rating] || rating
}

// ─── Status Helpers ──────────────────────────────────────────────────────────
function statusTagType(status: string | undefined): '' | 'success' | 'warning' | 'info' | 'danger' {
  const map: Record<string, '' | 'success' | 'warning' | 'info' | 'danger'> = {
    active: 'success',
    inactive: 'info',
    pending: 'warning',
    in_progress: 'warning',
    completed: 'success',
  }
  return map[status || ''] || ''
}

function statusLabel(status: string | undefined): string {
  const map: Record<string, string> = {
    active: '活跃',
    inactive: '非活跃',
    pending: '待开始',
    in_progress: '进行中',
    completed: '已完成',
  }
  return map[status || ''] || status || ''
}

function instructionStatusType(status: string): '' | 'success' | 'warning' | 'info' | 'danger' {
  const map: Record<string, '' | 'success' | 'warning' | 'info' | 'danger'> = {
    draft: 'info',
    sent: 'warning',
    acknowledged: 'success',
    pending: 'info',
    issued: 'warning',
    responded: 'success',
  }
  return map[status] || ''
}

function instructionStatusLabel(status: string): string {
  const map: Record<string, string> = {
    draft: '草稿',
    sent: '已发送',
    acknowledged: '已确认',
    pending: '草稿',
    issued: '已发出',
    responded: '已回复',
  }
  return map[status] || status
}

function resultStatusType(status: string): '' | 'success' | 'warning' | 'info' | 'danger' {
  const map: Record<string, '' | 'success' | 'warning' | 'info' | 'danger'> = {
    pending: 'info',
    received: 'warning',
    reviewed: 'success',
    submitted: 'warning',
    reviewed_result: 'success',
  }
  return map[status] || ''
}

function resultStatusLabel(status: string): string {
  const map: Record<string, string> = {
    pending: '待处理',
    received: '已收到',
    reviewed: '已审核',
    submitted: '已提交',
    reviewed_result: '已复核',
  }
  return map[status] || status
}

function instructionRowClass({ row }: { row: Instruction }): string {
  return selectedInstruction.value?.id === row.id ? 'current-row' : ''
}

// ─── CRUD Handlers ───────────────────────────────────────────────────────────
function handleAddAuditor() {
  emit('auditor-add')
}

function handleAddInstruction() {
  if (!selectedAuditor.value) return
  emit('instruction-add', selectedAuditor.value.id)
}

function handleEditInstruction(instruction: Instruction) {
  emit('instruction-edit', instruction)
}

function handleAddResult() {
  if (!selectedInstruction.value) return
  emit('result-add', selectedInstruction.value.id)
}

function handleEditResult(result: InstructionResult) {
  emit('result-edit', result)
}

// ─── Watchers ───────────────────────────────────────────────────────────────
watch(() => props.projectId, () => {
  loadAuditors()
  selectedAuditor.value = null
  selectedInstruction.value = null
  instructions.value = []
  results.value = []
}, { immediate: true })

// ─── Expose ─────────────────────────────────────────────────────────────────
defineExpose({
  loadAuditors,
  loadInstructions,
  loadResults,
  selectedAuditor,
  selectedInstruction,
  instructions,
  results,
})
</script>

<style scoped>
.auditor-panel {
  display: grid;
  grid-template-columns: 300px 1fr 1fr;
  gap: var(--gt-space-4);
  height: 100%;
  min-height: 500px;
}

.panel-column {
  display: flex;
  flex-direction: column;
  background: #fff;
  border-radius: var(--gt-radius-md);
  border: 1px solid rgba(75, 45, 119, 0.15);
  overflow: hidden;
}

.column-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--gt-space-3) var(--gt-space-4);
  background: var(--gt-color-primary);
  color: #fff;
}

.column-title {
  font-weight: 600;
  font-size: 14px;
}

.auditor-list,
.instruction-list,
.result-list {
  flex: 1;
  overflow-y: auto;
  padding: var(--gt-space-3);
}

/* Auditor Card */
.auditor-card {
  background: #fff;
  border: 1px solid rgba(75, 45, 119, 0.12);
  border-radius: var(--gt-radius-sm);
  padding: var(--gt-space-3);
  margin-bottom: var(--gt-space-3);
  cursor: pointer;
  transition: all 0.2s;
  box-shadow: var(--gt-shadow-sm);
}

.auditor-card:hover {
  border-color: var(--gt-color-primary-light);
  box-shadow: var(--gt-shadow-md);
  transform: translateY(-1px);
}

.auditor-card.is-selected {
  border-color: var(--gt-color-primary);
  background: rgba(75, 45, 119, 0.04);
  box-shadow: 0 0 0 2px rgba(75, 45, 119, 0.15);
}

.auditor-card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: var(--gt-space-1);
}

.auditor-name {
  font-weight: 600;
  color: var(--gt-color-primary-dark);
  font-size: 14px;
}

.status-badge {
  font-size: 11px;
}

.auditor-email {
  font-size: 12px;
  color: #666;
  margin-bottom: var(--gt-space-1);
}

.auditor-component {
  font-size: 12px;
  color: #555;
  margin-bottom: var(--gt-space-2);
}

.component-label {
  color: #888;
}

.auditor-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--gt-space-2);
}

.rating-indicator {
  display: inline-block;
  padding: 1px 8px;
  border-radius: 10px;
  font-size: 11px;
  font-weight: 600;
}

.rating-excellent {
  background: #e6f7ed;
  color: var(--gt-color-success);
}

.rating-good {
  background: #e6f0ff;
  color: var(--gt-color-teal);
}

.rating-fair {
  background: #fff4e5;
  color: #e07b00;
}

.rating-poor {
  background: #ffe6e6;
  color: var(--gt-color-coral);
}

.scope-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.scope-tag {
  font-size: 10px;
}

/* Table current row highlight */
:deep(.current-row) {
  background-color: rgba(75, 45, 119, 0.06) !important;
}
</style>
