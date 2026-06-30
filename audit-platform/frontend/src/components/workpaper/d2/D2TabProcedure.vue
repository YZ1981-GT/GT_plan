<script setup lang="ts">
/**
 * D2TabProcedure — 程序表D2A
 * 卡片式: 7个审计步骤, 进度条, 风险等级标签, 总体结论textarea
 */
import { inject, toRef, type Ref } from 'vue'
import { useD2Procedure, type ProcedureStep, type ProcedureStatus, type RiskLevel } from '../composables/useD2Procedure'
import GtIndexChip from '../GtIndexChip.vue'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const displayPrefs = inject<{ fmtAmount: (v: number) => string }>('displayPrefs', {
  fmtAmount: (v: number) => v === 0 ? '-' : v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }),
})

// 复核对话集成 (Task 47.1)
const openReviewDialog = inject<((sectionId: string) => void) | null>('openReviewDialog', null)

const viewMode = defineModel<'structured' | 'online'>('viewMode', { default: 'structured' })

const {
  steps,
  overallConclusion,
  completedCount,
  totalCount,
  allNecessaryDone,
  updateStep,
  updateOverallConclusion,
} = useD2Procedure({
  wpId: toRef(props, 'wpId') as Ref<string>,
  projectId: toRef(props, 'projectId') as Ref<string>,
  allResponses: toRef(props, 'allResponses') as Ref<Map<string, any>>,
  isReadonly: toRef(props, 'isReadonly') as Ref<boolean>,
})

const STATUS_OPTIONS: Array<{ label: string; value: ProcedureStatus }> = [
  { label: '未开始', value: 'not_started' },
  { label: '进行中', value: 'in_progress' },
  { label: '已完成', value: 'completed' },
  { label: '不适用', value: 'not_applicable' },
]

function getRiskTagType(level: RiskLevel): 'danger' | 'warning' | 'success' | 'info' {
  if (level === 'H') return 'danger'
  if (level === 'M') return 'warning'
  if (level === 'L') return 'success'
  return 'info'
}

function getStatusType(status: ProcedureStatus): 'success' | 'warning' | 'info' | 'danger' {
  if (status === 'completed') return 'success'
  if (status === 'in_progress') return 'warning'
  if (status === 'not_applicable') return 'info'
  return 'danger'
}
</script>

<template>
  <div class="d2-tab-procedure">
    <div class="tab-toolbar">
      <div class="toolbar-left">
        <span class="progress-text">进度: {{ completedCount }} / {{ totalCount }}</span>
      </div>
      <div class="toolbar-right">
        <el-segmented v-model="viewMode" :options="[
          { label: '结构化视图', value: 'structured' },
          { label: '在线编辑', value: 'online' },
        ]" size="small" />
      </div>
    </div>

    <!-- 顶部进度条 -->
    <el-progress
      :percentage="totalCount > 0 ? (completedCount / totalCount) * 100 : 0"
      :stroke-width="10"
      :format="() => `${completedCount}/${totalCount}`"
      class="top-progress"
    />

    <!-- 步骤卡片 -->
    <div class="step-cards">
      <el-card
        v-for="step in steps"
        :key="step.stepId"
        shadow="hover"
        class="step-card"
      >
        <template #header>
          <div class="step-header">
            <span class="step-seq">{{ step.seq }}</span>
            <span class="step-desc">{{ step.description }}</span>
            <div class="step-tags">
              <el-tag v-if="step.riskLevel" :type="getRiskTagType(step.riskLevel)" size="small">
                {{ step.riskLevel === 'H' ? '高风险' : step.riskLevel === 'M' ? '中风险' : '低风险' }}
              </el-tag>
              <el-tag :type="getStatusType(step.status)" size="small">
                {{ STATUS_OPTIONS.find(o => o.value === step.status)?.label }}
              </el-tag>
            </div>
          </div>
        </template>

        <div class="step-body">
          <div class="step-row">
            <span class="field-label">分类:</span>
            <span>{{ step.category }}</span>
            <span class="field-label" style="margin-left:16px">目标:</span>
            <span>{{ step.objective }}</span>
          </div>

          <div class="step-row">
            <span class="field-label">状态:</span>
            <el-select
              :model-value="step.status"
              :disabled="isReadonly"
              size="small"
              style="width: 110px"
              @change="(v: string) => updateStep(step.stepId, 'status', v)"
            >
              <el-option v-for="opt in STATUS_OPTIONS" :key="opt.value" :label="opt.label" :value="opt.value" />
            </el-select>
            <span class="field-label" style="margin-left:12px">执行人:</span>
            <el-input
              :model-value="step.executor"
              :disabled="isReadonly"
              size="small"
              style="width: 100px"
              @change="(v: string) => updateStep(step.stepId, 'executor', v)"
            />
            <span class="field-label" style="margin-left:12px">日期:</span>
            <el-date-picker
              :model-value="step.date"
              :disabled="isReadonly"
              type="date"
              value-format="YYYY-MM-DD"
              size="small"
              style="width: 140px"
              @change="(v: string) => updateStep(step.stepId, 'date', v)"
            />
          </div>

          <div class="step-row">
            <span class="field-label">发现:</span>
            <el-input
              :model-value="step.finding"
              :disabled="isReadonly"
              type="textarea"
              :autosize="{ minRows: 1, maxRows: 3 }"
              size="small"
              style="flex:1"
              @change="(v: string) => updateStep(step.stepId, 'finding', v)"
            />
          </div>

          <div class="step-row">
            <span class="field-label">结论:</span>
            <el-input
              :model-value="step.conclusion"
              :disabled="isReadonly"
              size="small"
              style="flex:1"
              @change="(v: string) => updateStep(step.stepId, 'conclusion', v)"
            />
            <span class="field-label" style="margin-left:12px">索引号:</span>
            <span class="index-chip">{{ step.indexRef || '-' }}</span>
          </div>
        </div>
      </el-card>
    </div>

    <!-- 总体结论 -->
    <el-card shadow="never" class="overall-conclusion">
      <template #header>
        <span style="font-weight:600">审计结论</span>
        <el-tag v-if="!allNecessaryDone" type="warning" size="small" style="margin-left:8px">
          需完成全部步骤后方可填写
        </el-tag>
      </template>
      <el-input
        :model-value="overallConclusion"
        type="textarea"
        :rows="4"
        :disabled="isReadonly || !allNecessaryDone"
        placeholder="全部审计程序执行完毕后，请填写审计总体结论..."
        @change="(v: string) => updateOverallConclusion(v)"
      />
    </el-card>
  </div>
</template>

<style scoped>
.d2-tab-procedure { padding: 12px; }
.tab-toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.progress-text { font-size: 13px; font-weight: 600; }
.top-progress { margin-bottom: 16px; }

.step-cards { display: flex; flex-direction: column; gap: 12px; margin-bottom: 16px; }
.step-card { }
.step-header { display: flex; align-items: center; gap: 8px; }
.step-seq {
  display: inline-flex; align-items: center; justify-content: center;
  width: 24px; height: 24px; border-radius: 50%; background: #409eff; color: #fff;
  font-size: 12px; font-weight: 700; flex-shrink: 0;
}
.step-desc { flex: 1; font-size: 13px; font-weight: 500; }
.step-tags { display: flex; gap: 4px; }

.step-body { display: flex; flex-direction: column; gap: 8px; }
.step-row { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; font-size: 13px; }
.field-label { color: #909399; font-size: 12px; white-space: nowrap; }
.index-chip {
  display: inline-block; padding: 2px 6px; background: #ecf5ff; border-radius: 3px;
  font-size: 12px; color: #409eff; font-weight: 500;
}

.overall-conclusion { margin-top: 16px; }
</style>
