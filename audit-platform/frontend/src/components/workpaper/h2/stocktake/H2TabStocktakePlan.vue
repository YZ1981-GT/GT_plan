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
          <span class="form-label">监盘目的：</span>
          <el-input v-if="!isReadonly" v-model="state.plan.value.purpose" type="textarea"
            :autosize="{ minRows: 2, maxRows: 4 }" placeholder="核实在建工程的实际存在性和完工状态..."
            @blur="onFieldChange('purpose', state.plan.value.purpose)" />
          <span v-else>{{ state.plan.value.purpose || '-' }}</span>
        </div>
        <div class="form-item">
          <span class="form-label">监盘范围：</span>
          <el-input v-if="!isReadonly" v-model="state.plan.value.scope" type="textarea"
            :autosize="{ minRows: 2, maxRows: 4 }" placeholder="涵盖期末在建工程项目..."
            @blur="onFieldChange('scope', state.plan.value.scope)" />
          <span v-else>{{ state.plan.value.scope || '-' }}</span>
        </div>
        <div class="form-item">
          <span class="form-label">监盘方法：</span>
          <el-select v-if="!isReadonly" v-model="state.plan.value.method" multiple size="small"
            style="width:100%" @change="onFieldChange('method', $event)">
            <el-option label="现场踏勘" value="现场踏勘" />
            <el-option label="查看施工记录" value="查看施工记录" />
            <el-option label="询问项目经理" value="询问项目经理" />
            <el-option label="核对进度报告" value="核对进度报告" />
            <el-option label="拍照存证" value="拍照存证" />
          </el-select>
          <span v-else>{{ (state.plan.value.method || []).join('、') || '-' }}</span>
        </div>
        <div class="form-item">
          <span class="form-label">监盘人员：</span>
          <el-input v-if="!isReadonly" v-model="state.plan.value.personnel" size="small"
            placeholder="审计团队人员姓名..."
            @change="onFieldChange('personnel', $event)" />
          <span v-else>{{ state.plan.value.personnel || '-' }}</span>
        </div>
      </div>
    </el-card>

    <!-- 区域2: 工程选取 -->
    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="section-header"><span>二、监盘工程选取</span></div>
      </template>

      <el-table :data="state.selectedProjects.value" border stripe size="small" class="plan-table">
        <el-table-column prop="name" label="工程项目" min-width="140">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.name" size="small"
              @change="onProjectChange(row.rowId, 'name', $event)" />
            <span v-else>{{ row.name || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="location" label="所在地点" min-width="120">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.location" size="small"
              @change="onProjectChange(row.rowId, 'location', $event)" />
            <span v-else>{{ row.location || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="bookValue" label="账面金额" min-width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.bookValue" :controls="false"
              size="small" class="amt-input" @change="onProjectChange(row.rowId, 'bookValue', $event)" />
            <span v-else class="amt-cell">{{ fmtAmt(row.bookValue) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="selectionReason" label="选取原因" min-width="150">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" v-model="row.selectionReason" size="small" style="width:100%"
              @change="onProjectChange(row.rowId, 'selectionReason', $event)">
              <el-option label="金额重大" value="金额重大" />
              <el-option label="进度异常" value="进度异常" />
              <el-option label="工期延迟" value="工期延迟" />
              <el-option label="随机选取" value="随机选取" />
            </el-select>
            <span v-else>{{ row.selectionReason || '-' }}</span>
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
          <span class="form-label">监盘日期：</span>
          <el-date-picker v-if="!isReadonly" v-model="state.plan.value.planDate" type="daterange"
            size="small" value-format="YYYY-MM-DD" range-separator="至"
            start-placeholder="开始日期" end-placeholder="结束日期"
            @change="onFieldChange('planDate', $event)" />
          <span v-else>{{ (state.plan.value.planDate || []).join(' 至 ') || '-' }}</span>
        </div>
        <div class="form-item">
          <span class="form-label">注意事项：</span>
          <el-input v-if="!isReadonly" v-model="state.plan.value.notes" type="textarea"
            :autosize="{ minRows: 2, maxRows: 4 }" placeholder="安全注意事项/需准备的资料..."
            @blur="onFieldChange('notes', state.plan.value.notes)" />
          <span v-else>{{ state.plan.value.notes || '-' }}</span>
        </div>
      </div>
    </el-card>

    <!-- 编制提示 -->
    <details class="edit-tips">
      <summary>编制提示</summary>
      <ul>
        <li>监盘计划应在实施前制定，明确目的/范围/方法</li>
        <li>工程选取应覆盖金额重大项目+异常项目+随机选取</li>
        <li>时间安排需考虑工程进度和现场条件</li>
        <li>监盘人员应包含具有工程经验的审计人员</li>
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

function onFieldChange(field: string, value: any) {
  state.updatePlanField(field, value)
}

function onProjectChange(rowId: string, field: string, value: any) {
  state.updateProjectCell(rowId, field, value)
}

function handleAddProject() {
  state.addProject()
}

function handleRemoveProject(rowId: string) {
  state.removeProject(rowId)
}

function handleAiGenerate(section: string) {
  console.log('AI generate H2-12:', section)
}

function openReview(id: string) {
  openReviewDialog(id)
}

function fmtAmt(val: number | null | undefined): string {
  if (val == null) return '-'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
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
.amt-cell { font-variant-numeric: tabular-nums; }
.amt-input { width: 100%; }
.add-row-bar { margin-top: 12px; }
.edit-tips { margin-top: 16px; font-size: 12px; color: var(--el-text-color-secondary); }
.edit-tips summary { cursor: pointer; font-weight: 500; }
.edit-tips ul { padding-left: 20px; margin-top: 8px; }
</style>
