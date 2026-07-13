<template>
  <div class="h2-tab-stocktake-plan">
    <!-- 审计目标 -->
    <el-alert type="info" :closable="false" class="objective-alert"
      title="审计目标：制定在建工程现场监盘计划，明确踏勘日期/地点/范围与工程选取依据（金额重大/异常/随机），确保监盘程序覆盖充分、执行有序。" />

    <!-- 工具栏 -->
    <div class="tab-toolbar">
      <div class="toolbar-right">
        <span class="chip-wrap"><GtIndexChip value="wp:H2-12" :context-project-id="projectId" /></span>
        <el-tag size="small" type="info">选取 {{ state.plan.value.selectedProjects.length }} 项</el-tag>
      </div>
    </div>

    <!-- 区域1: 基本信息 -->
    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="section-header">
          <span>一、监盘基本信息</span>
          <div class="section-header-actions">
            <el-button size="small" circle @click="openReview('H2-12')">💬</el-button>
          </div>
        </div>
      </template>

      <div class="form-grid">
        <div class="form-item">
          <span class="form-label">踏勘日期：</span>
          <el-date-picker v-if="!isReadonly" v-model="state.plan.value.inspectionDate" type="date"
            size="small" value-format="YYYY-MM-DD" style="width:220px"
            @change="onFieldChange('inspectionDate', $event)" />
          <span v-else>{{ state.plan.value.inspectionDate || '-' }}</span>
        </div>
        <div class="form-item">
          <span class="form-label">工程地点：</span>
          <el-input v-if="!isReadonly" v-model="state.plan.value.location" size="small"
            placeholder="工程所在地点..."
            @change="onFieldChange('location', state.plan.value.location)" />
          <span v-else>{{ state.plan.value.location || '-' }}</span>
        </div>
        <div class="form-item">
          <span class="form-label">参与人员：</span>
          <el-input v-if="!isReadonly" v-model="state.plan.value.participants" size="small"
            placeholder="审计团队人员姓名..."
            @change="onFieldChange('participants', state.plan.value.participants)" />
          <span v-else>{{ state.plan.value.participants || '-' }}</span>
        </div>
        <div class="form-item">
          <span class="form-label">踏勘范围：</span>
          <el-input v-if="!isReadonly" v-model="state.plan.value.scope" type="textarea"
            :autosize="{ minRows: 2, maxRows: 4 }" placeholder="涵盖期末在建工程项目..."
            @blur="onFieldChange('scope', state.plan.value.scope)" />
          <span v-else>{{ state.plan.value.scope || '-' }}</span>
        </div>
      </div>
    </el-card>

    <!-- 区域2: 工程选取 -->
    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="section-header"><span>二、监盘工程选取</span></div>
      </template>

      <el-table :data="state.plan.value.selectedProjects" border stripe size="small" class="plan-table">
        <el-table-column prop="name" label="工程项目" min-width="150">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.name" size="small"
              @change="onProjectChange()" />
            <span v-else>{{ row.name || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="reason" label="选取原因" min-width="150">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" v-model="row.reason" size="small" style="width:100%"
              @change="onProjectChange()">
              <el-option label="金额重大" value="金额重大" />
              <el-option label="进度异常" value="进度异常" />
              <el-option label="工期延迟" value="工期延迟" />
              <el-option label="随机选取" value="随机选取" />
            </el-select>
            <span v-else>{{ row.reason || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="plannedContent" label="计划踏勘内容" min-width="200">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.plannedContent" size="small"
              @change="onProjectChange()" />
            <span v-else>{{ row.plannedContent || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="" width="50" v-if="!isReadonly">
          <template #default="{ row }">
            <el-button size="small" type="danger" link @click="handleRemoveProject(row.rowId)">✕</el-button>
          </template>
        </el-table-column>
      </el-table>
      <div class="add-row-bar" v-if="!isReadonly">
        <el-button size="small" @click="handleAddProject">+ 新增监盘工程</el-button>
      </div>
    </el-card>

    <!-- 区域3: 时间安排 -->
    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="section-header"><span>三、时间安排</span></div>
      </template>
      <div class="form-grid">
        <div class="form-item">
          <span class="form-label">时间安排：</span>
          <el-input v-if="!isReadonly" v-model="state.plan.value.schedule" type="textarea"
            :autosize="{ minRows: 2, maxRows: 4 }" placeholder="监盘时间安排/需准备的资料/安全注意事项..."
            @blur="onFieldChange('schedule', state.plan.value.schedule)" />
          <span v-else>{{ state.plan.value.schedule || '-' }}</span>
        </div>
      </div>
    </el-card>

    <!-- 审计说明 -->
    <el-card shadow="never" class="audit-note-card">
      <template #header>
        <div class="section-header"><span>审计说明</span></div>
      </template>
      <el-input :model-value="auditNote" type="textarea" :autosize="{ minRows: 5 }"
        placeholder="填写审计说明：概述监盘计划的编制依据、工程选取的抽样考虑、人员安排与资料准备。" :disabled="isReadonly"
        @change="saveAuditNote" />
    </el-card>

    <!-- 审计结论 -->
    <el-card shadow="never" class="audit-note-card">
      <template #header>
        <div class="section-header"><span>审计结论</span></div>
      </template>
      <el-input :model-value="auditConclusion" type="textarea" :autosize="{ minRows: 3 }"
        placeholder="填写结论：如监盘计划已充分覆盖重大与异常项目、经项目负责人审批，可据以实施。" :disabled="isReadonly"
        @change="saveAuditConclusion" />
    </el-card>

    <!-- 编制提示 -->
    <details class="edit-tips">
      <summary>编制提示</summary>
      <ul>
        <li>监盘计划应在实施前制定，明确踏勘日期/地点/范围</li>
        <li>工程选取应覆盖金额重大项目+异常项目+随机选取</li>
        <li>时间安排需考虑工程进度和现场条件</li>
        <li>参与人员应包含具有工程经验的审计人员</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * H2TabStocktakePlan.vue — H2-12 监盘计划
 * 3区域(基本信息+工程选取+时间安排)
 * Spec: Task 4.15 | Requirements: 11.1
 */
import { ref, inject, toRef, computed, onMounted } from 'vue'
import { ElMessageBox } from 'element-plus'
import { MagicStick } from '@element-plus/icons-vue'
import { useH2Stocktake } from '../../composables/useH2Stocktake'
import GtIndexChip from '../../GtIndexChip.vue'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})
const saveResponse = inject<(id: string, val: any) => void>('saveResponse', () => {})

const state = useH2Stocktake({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  allResponses: computed(() => props.allResponses),
  isReadonly: toRef(props, 'isReadonly'),
  phase: 'plan',
  onSave: (itemId: string, value: any) => saveResponse(itemId, value),
})

const isReadonly = computed(() => props.isReadonly)

// H2-12 审计说明/结论：本 sheet 独立 item_id（plan/check/summary 共用同一 composable）。
const NOTE_KEY = 'H2-12-audit-note'
const CONCLUSION_KEY = 'H2-12-audit-conclusion'
const auditNote = ref('')
const auditConclusion = ref('')
function saveAuditNote(val: string): void {
  if (props.isReadonly) return
  auditNote.value = val
  props.allResponses.set(NOTE_KEY, { item_id: NOTE_KEY, conclusion: null, remark: val })
  saveResponse(NOTE_KEY, val)
}
function saveAuditConclusion(val: string): void {
  if (props.isReadonly) return
  auditConclusion.value = val
  props.allResponses.set(CONCLUSION_KEY, { item_id: CONCLUSION_KEY, conclusion: null, remark: val })
  saveResponse(CONCLUSION_KEY, val)
}
onMounted(() => {
  const n = props.allResponses.get(NOTE_KEY)
  if (n?.remark) auditNote.value = n.remark
  const c = props.allResponses.get(CONCLUSION_KEY)
  if (c?.remark) auditConclusion.value = c.remark
})

function onFieldChange(field: string, value: any) {
  state.updatePlan(field as any, value)
}

/** 工程选取行内编辑后整体持久化 */
function onProjectChange() {
  state.updatePlan('selectedProjects', state.plan.value.selectedProjects)
}

async function handleAddProject() {
  try {
    const { value } = await ElMessageBox.prompt('请输入工程项目名称', '新增监盘工程', {
      confirmButtonText: '确认', cancelButtonText: '取消',
      inputPattern: /\S+/, inputErrorMessage: '名称不能为空',
    })
    if (value) state.addPlanProject(value)
  } catch { /* cancelled */ }
}

function handleRemoveProject(rowId: string) {
  state.removePlanProject(rowId)
}


function openReview(id: string) {
  openReviewDialog(id)
}
</script>

<style scoped>
.h2-tab-stocktake-plan { padding: 16px; font-size: var(--wp-font-size, 13px); }
.objective-alert { margin-bottom: 12px; }
.tab-toolbar { display: flex; justify-content: flex-end; align-items: center; margin-bottom: 8px; gap: 8px; flex-wrap: wrap; }
.toolbar-right { display: flex; gap: 6px; align-items: center; }
.chip-wrap { display: inline-flex; align-items: center; }
.audit-note-card { margin-bottom: 12px; }
.block-card { margin-bottom: 16px; }
.section-header { display: flex; align-items: center; justify-content: space-between; }
.section-header-actions { display: flex; gap: 8px; align-items: center; }
.form-grid { display: grid; grid-template-columns: 1fr; gap: 16px; }
.form-item { display: flex; flex-direction: column; gap: 6px; }
.form-label { font-weight: 500; color: var(--el-text-color-secondary); }
.plan-table { font-size: var(--wp-font-size, 13px); }
.add-row-bar { margin-top: 12px; }
.edit-tips { margin-top: 16px; font-size: 12px; color: var(--el-text-color-secondary); }
.edit-tips summary { cursor: pointer; font-weight: 500; }
.edit-tips ul { padding-left: 20px; margin-top: 8px; }
</style>
