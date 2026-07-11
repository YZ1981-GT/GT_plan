<template>
  <div class="h2-tab-stocktake-plan">
    <!-- 区域1: 基本信息 -->
    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="section-header">
          <span>一、监盘基本信息</span>
          <div class="section-header-actions">
            <el-button size="small" type="primary" link @click="handleAiGenerate('plan-info')">
              <el-icon><MagicStick /></el-icon> AI
            </el-button>
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
import { inject, toRef, computed } from 'vue'
import { ElMessageBox } from 'element-plus'
import { MagicStick } from '@element-plus/icons-vue'
import { useH2Stocktake } from '../../composables/useH2Stocktake'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})

const state = useH2Stocktake({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  allResponses: computed(() => props.allResponses),
  isReadonly: toRef(props, 'isReadonly'),
  phase: 'plan',
})

const isReadonly = computed(() => props.isReadonly)

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

function handleAiGenerate(section: string) {
  console.log('AI generate H2-12:', section)
}

function openReview(id: string) {
  openReviewDialog(id)
}
</script>

<style scoped>
.h2-tab-stocktake-plan { padding: 16px; font-size: 13px; }
.block-card { margin-bottom: 16px; }
.section-header { display: flex; align-items: center; justify-content: space-between; }
.section-header-actions { display: flex; gap: 8px; align-items: center; }
.form-grid { display: grid; grid-template-columns: 1fr; gap: 16px; }
.form-item { display: flex; flex-direction: column; gap: 6px; }
.form-label { font-weight: 500; color: var(--el-text-color-secondary); }
.plan-table { font-size: 13px; }
.add-row-bar { margin-top: 12px; }
.edit-tips { margin-top: 16px; font-size: 12px; color: var(--el-text-color-secondary); }
.edit-tips summary { cursor: pointer; font-weight: 500; }
.edit-tips ul { padding-left: 20px; margin-top: 8px; }
</style>
