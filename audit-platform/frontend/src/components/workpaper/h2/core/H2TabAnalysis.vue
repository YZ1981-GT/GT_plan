<template>
  <div class="h2-tab-analysis">
    <!-- 审计目标 -->
    <el-alert type="info" :closable="false" class="objective-alert"
      title="审计目标：分析在建工程的完工进度、资本化利率与工期偏差的合理性，识别超预算/超期/资本化率异常项目，评估其减值迹象与转固时点。" />

    <!-- 工具栏 -->
    <div class="tab-toolbar">
      <div class="toolbar-right">
        <span class="chip-wrap"><GtIndexChip value="wp:H2-4" :context-project-id="projectId" /></span>
        <el-tag size="small" type="info">共 {{ state.progressRows.value.length }} 项</el-tag>
      </div>
    </div>

    <!-- 方法论上下文 -->
    <div class="methodology-context">
      <p>分析要点：关注完工进度与预算的匹配度、资本化利率的合理性、工期延误的影响。超过阈值的项目需重点关注减值迹象。</p>
    </div>

    <!-- 区域1: 工程进度分析 -->
    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="section-header">
          <span>一、工程进度分析</span>
          <div class="section-header-actions">
            <el-button size="small" circle @click="openReview('H2-4-progress')">💬</el-button>
          </div>
        </div>
      </template>
      <el-table :data="state.progressRows.value" border stripe size="small" class="analysis-table">
        <el-table-column prop="name" label="工程项目" min-width="140" />
        <el-table-column prop="budget" label="预算(元)" min-width="110" align="right">
          <template #default="{ row }"><span class="amt-cell">{{ fmtAmt(row.budget) }}</span></template>
        </el-table-column>
        <el-table-column prop="accumulated" label="累计投入(元)" min-width="110" align="right">
          <template #default="{ row }"><span class="amt-cell">{{ fmtAmt(row.accumulated) }}</span></template>
        </el-table-column>
        <el-table-column label="完工率(%)" min-width="90" align="right">
          <template #default="{ row }">
            <span :class="['formula-cell', { 'warning-value': row.completionRate > 100 }]"
              :title="`=累计投入/预算×100 = ${row.completionRate?.toFixed(1)}%`">
              {{ row.completionRate != null ? row.completionRate.toFixed(1) + '%' : '-' }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="超预算率(%)" min-width="100" align="right">
          <template #default="{ row }">
            <span :class="['formula-cell', { 'error-amount': row.overBudgetRate > 10 }]"
              :title="`=(累计-预算)/预算×100`">
              {{ row.overBudgetRate != null ? row.overBudgetRate.toFixed(1) + '%' : '-' }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="预警" width="80" align="center">
          <template #default="{ row }">
            <el-tag v-if="row.overBudgetRate > 10" type="danger" size="small">超支</el-tag>
            <el-tag v-else-if="row.completionRate > 100" type="warning" size="small">超进度</el-tag>
            <el-tag v-else type="success" size="small">正常</el-tag>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 区域2: 资本化率分析 -->
    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="section-header">
          <span>二、资本化率分析</span>
          <div class="section-header-actions">
            <GtIndexChip value="H2-10" label="→ H2-10利息" />
          </div>
        </div>
      </template>
      <el-table :data="state.capRateRows.value" border stripe size="small" class="analysis-table">
        <el-table-column prop="name" label="工程项目" min-width="140" />
        <el-table-column prop="interestAmount" label="资本化利息(元)" min-width="110" align="right">
          <template #default="{ row }"><span class="amt-cell">{{ fmtAmt(row.interestAmount) }}</span></template>
        </el-table-column>
        <el-table-column prop="cipBalance" label="在建余额(元)" min-width="110" align="right">
          <template #default="{ row }"><span class="amt-cell">{{ fmtAmt(row.cipBalance) }}</span></template>
        </el-table-column>
        <el-table-column label="实际资本化率(%)" min-width="120" align="right">
          <template #default="{ row }">
            <span :class="['formula-cell', { 'warning-value': row.actualCapRate > 8 }]"
              :title="`=利息/余额×100`">
              {{ row.actualCapRate != null ? row.actualCapRate.toFixed(2) + '%' : '-' }}
            </span>
          </template>
        </el-table-column>
        <el-table-column prop="benchmarkRate" label="基准利率(%)" min-width="100" align="right">
          <template #default="{ row }"><span>{{ row.benchmarkRate?.toFixed(2) ?? '-' }}%</span></template>
        </el-table-column>
        <el-table-column label="偏差" width="80" align="center">
          <template #default="{ row }">
            <el-tag v-if="Math.abs((row.actualCapRate ?? 0) - (row.benchmarkRate ?? 0)) > 2" type="warning" size="small">偏高</el-tag>
            <el-tag v-else type="info" size="small">合理</el-tag>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 区域3: 工期分析 -->
    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="section-header">
          <span>三、工期分析</span>
          <div class="section-header-actions">
            <GtIndexChip value="H2-5" label="→ H2-5转固" />
          </div>
        </div>
      </template>
      <el-table :data="state.durationRows.value" border stripe size="small" class="analysis-table">
        <el-table-column prop="name" label="工程项目" min-width="140" />
        <el-table-column prop="startDate" label="开工日期" min-width="100" />
        <el-table-column prop="plannedEnd" label="预计竣工" min-width="100" />
        <el-table-column prop="actualEnd" label="实际竣工" min-width="100" />
        <el-table-column label="超期天数" min-width="90" align="right">
          <template #default="{ row }">
            <span :class="['formula-cell', { 'error-amount': row.overdueDays > 180 }]"
              :title="`=实际-预计`">
              {{ row.overdueDays ?? '-' }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="80" align="center">
          <template #default="{ row }">
            <el-tag v-if="row.overdueDays > 180" type="danger" size="small">严重延期</el-tag>
            <el-tag v-else-if="row.overdueDays > 0" type="warning" size="small">延期</el-tag>
            <el-tag v-else-if="row.actualEnd" type="success" size="small">按期</el-tag>
            <el-tag v-else type="info" size="small">在建</el-tag>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 审计说明 -->
    <el-card shadow="never" class="audit-note-card">
      <template #header>
        <div class="section-header"><span>审计说明</span></div>
      </template>
      <el-input v-model="state.auditNote.value" type="textarea" :autosize="{ minRows: 5 }"
        placeholder="填写审计说明：概述所实施的分析程序（完工进度/资本化率/工期）、数据来源、发现的异常项目及跟进情况。" :disabled="isReadonly"
        @blur="state.saveNote(state.auditNote.value)" />
    </el-card>

    <!-- 审计结论 -->
    <el-card shadow="never" class="audit-note-card">
      <template #header>
        <div class="section-header">
          <span>审计结论（分析结论）</span>
        </div>
      </template>
      <el-input v-model="state.conclusion.value" type="textarea" :autosize="{ minRows: 3, maxRows: 8 }"
        placeholder="请填写分析结论..." :disabled="isReadonly"
        @blur="state.saveConclusion(state.conclusion.value)" />
    </el-card>

    <!-- 编制提示 -->
    <details class="edit-tips">
      <summary>编制提示</summary>
      <ul>
        <li>完工率=累计投入/预算×100%，超过100%表示超支</li>
        <li>超预算率=(累计-预算)/预算×100%，超10%重点关注</li>
        <li>工期超180天严重延期：需关注减值迹象(→H2-15)</li>
        <li>资本化率偏离基准>2%需解释合理性</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * H2TabAnalysis.vue — H2-4 分析表
 * 三区域(进度+资本化率+工期) + 阈值高亮 + GtIndexChip
 * Spec: Task 4.5 | Requirements: 5.1-5.8
 */
import { inject, toRef, computed } from 'vue'
import { MagicStick } from '@element-plus/icons-vue'
import { useH2Analysis } from '../../composables/useH2Analysis'
import GtIndexChip from '../../GtIndexChip.vue'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})
const saveResponse = inject<(id: string, val: any) => void>('saveResponse', () => {})

const state = useH2Analysis({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  allResponses: computed(() => props.allResponses),
  isReadonly: toRef(props, 'isReadonly'),
  onSave: (itemId: string, value: any) => saveResponse(itemId, value),
})


function openReview(id: string) {
  openReviewDialog(id)
}

function fmtAmt(val: number | null | undefined): string {
  if (val == null) return '-'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.h2-tab-analysis { padding: 16px; font-size: var(--wp-font-size, 13px); }
.objective-alert { margin-bottom: 12px; }
.tab-toolbar { display: flex; justify-content: flex-end; align-items: center; margin-bottom: 8px; gap: 8px; flex-wrap: wrap; }
.toolbar-right { display: flex; gap: 6px; align-items: center; }
.chip-wrap { display: inline-flex; align-items: center; }
.methodology-context {
  border-left: 3px solid #f0a020; background: #fdf8e8;
  padding: 12px 16px; margin-bottom: 16px; border-radius: 4px; font-size: var(--wp-font-size, 13px);
}
.block-card { margin-bottom: 16px; }
.section-header { display: flex; align-items: center; justify-content: space-between; }
.section-header-actions { display: flex; gap: 8px; align-items: center; }
.analysis-table { font-size: var(--wp-font-size, 13px); }
.amt-cell { font-variant-numeric: tabular-nums; }
.formula-cell { border-bottom: 1px dashed var(--el-border-color); cursor: help; font-variant-numeric: tabular-nums; }
.warning-value { color: var(--el-color-warning); font-weight: 600; }
.error-amount { color: var(--el-color-danger); font-weight: 600; }
.audit-note-card { margin-bottom: 12px; }
.edit-tips { margin-top: 16px; font-size: 12px; color: var(--el-text-color-secondary); }
.edit-tips summary { cursor: pointer; font-weight: 500; }
.edit-tips ul { padding-left: 20px; margin-top: 8px; }
</style>
