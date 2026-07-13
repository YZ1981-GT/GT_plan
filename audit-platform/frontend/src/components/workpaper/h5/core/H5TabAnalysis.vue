<template>
  <div class="h5-tab-analysis">
    <!-- 审计目标 -->
    <el-alert type="info" :closable="false" title="审计目标：通过本期与上期油气资产原值/折耗/净值的变动分析，识别异常波动并评价变动合理性。" class="objective-alert" />

    <!-- 工具栏 -->
    <div class="tab-toolbar">
      <div class="toolbar-right">
        <span class="chip-wrap"><GtIndexChip value="wp:H5-6" :context-project-id="projectId" /></span>
        <el-tag size="small" type="info">共 {{ state.rows.value.length }} 行</el-tag>
      </div>
    </div>

    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="section-title">
          <span>H5-6 分析性程序</span>
          <div class="title-actions">
            <el-button size="small" type="default" link @click="handleReview('H5-6')">💬 复核</el-button>
          </div>
        </div>
      </template>

      <!-- 摘要指标 -->
      <div class="summary-row">
        <div class="summary-item"><span class="label">本期原值合计</span><span class="value">{{ fmtAmt(state.totalCurrentCost.value) }}</span></div>
        <div class="summary-item"><span class="label">本期净值合计</span><span class="value">{{ fmtAmt(state.totalCurrentNetValue.value) }}</span></div>
        <div class="summary-item"><span class="label">综合折耗率</span><span class="value">{{ state.overallDepletionRate.value.toFixed(2) }}%</span></div>
      </div>

      <!-- 重大变动预警 -->
      <el-alert v-if="state.significantChanges.value.length > 0" type="warning" :closable="false" show-icon class="warn-alert">
        {{ state.significantChanges.value.length }} 项变动超30%，请关注
      </el-alert>

      <el-table :data="state.rows.value" border stripe size="small" class="analysis-table">
        <el-table-column prop="category" label="资产分类" min-width="100" fixed>
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.category" size="small" @change="state.updateCell(row.rowId, 'category', $event)" />
            <span v-else>{{ row.category }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="priorCost" label="上期原值" min-width="100" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.priorCost" :controls="false" size="small" @change="state.updateCell(row.rowId, 'priorCost', $event ?? 0)" />
            <span v-else class="amount-cell">{{ fmtAmt(row.priorCost) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="currentCost" label="本期原值" min-width="100" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.currentCost" :controls="false" size="small" @change="state.updateCell(row.rowId, 'currentCost', $event ?? 0)" />
            <span v-else class="amount-cell">{{ fmtAmt(row.currentCost) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="原值变动率" min-width="90" align="right">
          <template #default="{ row }">
            <span class="formula-cell" :class="{ abnormal: Math.abs(row.costChangeRate) > 30 }" title="变动率=(本期-上期)/上期×100">
              {{ row.costChangeRate.toFixed(2) }}%
            </span>
          </template>
        </el-table-column>
        <el-table-column prop="currentDepletion" label="本期折耗" min-width="100" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.currentDepletion" :controls="false" size="small" @change="state.updateCell(row.rowId, 'currentDepletion', $event ?? 0)" />
            <span v-else class="amount-cell">{{ fmtAmt(row.currentDepletion) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="折耗率" min-width="80" align="right">
          <template #default="{ row }">
            <span class="formula-cell" title="折耗率=累计折耗/原值×100">{{ row.depletionRate.toFixed(2) }}%</span>
          </template>
        </el-table-column>
        <el-table-column prop="currentNetValue" label="本期净值" min-width="100" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.currentNetValue" :controls="false" size="small" @change="state.updateCell(row.rowId, 'currentNetValue', $event ?? 0)" />
            <span v-else class="amount-cell">{{ fmtAmt(row.currentNetValue) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="explanation" label="变动原因" min-width="140">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.explanation" size="small" @change="state.updateCell(row.rowId, 'explanation', $event)" />
            <span v-else>{{ row.explanation }}</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-card shadow="never" class="note-card">
      <template #header><div class="section-title"><span>审计说明</span></div></template>
      <el-input v-model="state.auditNote.value" type="textarea" :autosize="{ minRows: 5, maxRows: 8 }"
        placeholder="填写分析性程序审计说明..." :disabled="isReadonly" @blur="state.saveNote(state.auditNote.value)" />
    </el-card>

    <el-card shadow="never" class="note-card">
      <template #header><div class="section-title"><span>审计结论</span></div></template>
      <el-input v-model="state.auditConclusion.value" type="textarea" :autosize="{ minRows: 2, maxRows: 6 }"
        placeholder="分析性程序结论..." :disabled="isReadonly" @blur="state.saveConclusion(state.auditConclusion.value)" />
    </el-card>

    <details class="compile-hint">
      <summary>编制提示</summary>
      <ul>
        <li>分析变动率异常项(>30%)需说明原因</li>
        <li>折耗率应符合单位产量法的合理范围</li>
        <li>对比上期数据评价油气资产变动合理性</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
import { computed, inject, toRef } from 'vue'
import { MagicStick } from '@element-plus/icons-vue'
import GtIndexChip from '../../GtIndexChip.vue'
import { useH5Analysis } from '../../composables/useH5Analysis'
import { useH5FormData } from '../../composables/useH5FormData'

const props = defineProps<{ wpId: string; projectId: string; allResponses: Map<string, any>; isReadonly: boolean }>()
const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})
const allResponsesRef = computed(() => props.allResponses)

const formData = useH5FormData({ wpId: toRef(props, 'wpId'), projectId: toRef(props, 'projectId') })

const state = useH5Analysis({
  allResponses: allResponsesRef as any,
  wpId: toRef(props, 'wpId'), projectId: toRef(props, 'projectId'),
  onSave: (itemId: string, value: any) => formData.setResponse(itemId, value),
})

function handleReview(id: string) { openReviewDialog(id) }
function fmtAmt(val: number | null | undefined): string {
  if (val == null) return '-'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.h5-tab-analysis { padding: 16px; font-size: var(--wp-font-size, 13px); }
.objective-alert { margin-bottom: 12px; }
.tab-toolbar { display: flex; justify-content: flex-end; align-items: center; margin-bottom: 8px; }
.toolbar-right { display: flex; gap: 6px; align-items: center; }
.chip-wrap { display: inline-flex; align-items: center; }
.block-card { margin-bottom: 16px; }
.section-title { display: flex; align-items: center; justify-content: space-between; }
.title-actions { display: flex; gap: 8px; }
.summary-row { display: flex; gap: 24px; margin-bottom: 12px; padding: 8px 12px; background: var(--el-fill-color-lighter); border-radius: 6px; }
.summary-item .label { color: var(--el-text-color-secondary); margin-right: 6px; }
.summary-item .value { font-weight: 600; font-variant-numeric: tabular-nums; }
.warn-alert { margin-bottom: 12px; }
.analysis-table { font-size: var(--wp-font-size, 13px); }
.amount-cell { font-variant-numeric: tabular-nums; }
.formula-cell { font-variant-numeric: tabular-nums; border-bottom: 1px dashed var(--el-border-color); cursor: help; }
.formula-cell.abnormal { color: var(--el-color-warning); font-weight: 600; }
.note-card { margin-bottom: 16px; }
.compile-hint { margin-top: 12px; font-size: 12px; color: var(--el-text-color-secondary); }
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ul { padding-left: 20px; margin-top: 8px; }
</style>
