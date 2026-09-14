<template>
  <div class="h5-tab-stocktake-summary">
    <!-- 审计目标 -->
    <el-alert type="info" :closable="false" title="审计目标：汇总监盘执行情况与差异分析，形成监盘结论，评价油气资产存在与完整性。" class="objective-alert" />

    <!-- 工具栏 -->
    <div class="tab-toolbar">
      <div class="toolbar-right">
        <span class="chip-wrap"><GtIndexChip value="wp:H5-11" :context-project-id="projectId" /></span>
      </div>
    </div>

    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="section-title">
          <span>H5-11 监盘小结</span>
          <div class="title-actions">
            <el-button size="small" type="default" link @click="handleReview('H5-11')">💬 复核</el-button>
          </div>
        </div>
      </template>

      <!-- 联动数据摘要 -->
      <div class="linked-summary">
        <el-descriptions :column="2" size="small" border>
          <el-descriptions-item label="计划完成率">{{ state.planCompletionRate.value }}%</el-descriptions-item>
          <el-descriptions-item label="异常项数">{{ state.abnormalCheckItems.value.length }}</el-descriptions-item>
          <el-descriptions-item label="差异总额">{{ fmtAmt(state.totalDifference.value) }}</el-descriptions-item>
        </el-descriptions>
      </div>

      <!-- 叙述式小结 -->
      <div class="summary-sections">
        <div class="summary-section">
          <label>一、盘点概况</label>
          <el-input v-model="state.summary.value.overview" type="textarea" :autosize="{ minRows: 3, maxRows: 8 }"
            placeholder="概述监盘时间、地点、参与人员、方式..." :disabled="isReadonly"
            @blur="state.updateSummary('overview', state.summary.value.overview)" />
        </div>
        <div class="summary-section">
          <label>二、盘点范围</label>
          <el-input v-model="state.summary.value.scope" type="textarea" :autosize="{ minRows: 2, maxRows: 6 }"
            placeholder="说明盘点覆盖的油田/区块/资产类别..." :disabled="isReadonly"
            @blur="state.updateSummary('scope', state.summary.value.scope)" />
        </div>
        <div class="summary-section">
          <label>三、差异分析</label>
          <el-input v-model="state.summary.value.diffAnalysis" type="textarea" :autosize="{ minRows: 3, maxRows: 8 }"
            placeholder="分析盘点差异原因及影响程度..." :disabled="isReadonly"
            @blur="state.updateSummary('diffAnalysis', state.summary.value.diffAnalysis)" />
        </div>
        <div class="summary-section">
          <label>四、监盘结论</label>
          <el-input v-model="state.summary.value.conclusion" type="textarea" :autosize="{ minRows: 2, maxRows: 6 }"
            placeholder="总结监盘结论..." :disabled="isReadonly"
            @blur="state.updateSummary('conclusion', state.summary.value.conclusion)" />
        </div>
        <div class="summary-section">
          <label>五、建议</label>
          <el-input v-model="state.summary.value.suggestions" type="textarea" :autosize="{ minRows: 2, maxRows: 6 }"
            placeholder="提出改进建议..." :disabled="isReadonly"
            @blur="state.updateSummary('suggestions', state.summary.value.suggestions)" />
        </div>
      </div>
    </el-card>

    <!-- 审计说明 -->
    <el-card shadow="never" class="audit-note-card">
      <template #header><div class="card-header"><span>审计说明</span></div></template>
      <el-input type="textarea" :model-value="auditNoteText" :autosize="{ minRows: 5 }"
        placeholder="填写监盘小结审计说明..." :disabled="isReadonly" @change="savePolishNote" />
    </el-card>

    <!-- 审计结论 -->
    <el-card shadow="never" class="audit-note-card">
      <template #header><div class="card-header"><span>审计结论</span></div></template>
      <el-input type="textarea" :model-value="auditConclusionText" :autosize="{ minRows: 3 }"
        placeholder="填写监盘小结审计结论..." :disabled="isReadonly" @change="savePolishConclusion" />
    </el-card>

    <details class="compile-hint">
      <summary>编制提示</summary>
      <ul>
        <li>监盘小结为叙述式，总结H5-9计划执行情况及H5-10差异</li>
        <li>可使用AI辅助生成初稿，再根据实际情况修改</li>
        <li>结论应明确说明是否发现重大差异及对审计意见的影响</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, inject, onMounted, toRef } from 'vue'
import { MagicStick } from '@element-plus/icons-vue'
import GtIndexChip from '../../GtIndexChip.vue'
import { useH5Stocktake } from '../../composables/useH5Stocktake'
import { useH5FormData } from '../../composables/useH5FormData'

const props = defineProps<{ wpId: string; projectId: string; allResponses: Map<string, any>; isReadonly: boolean }>()
const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})
const allResponsesRef = computed(() => props.allResponses)
const formData = useH5FormData({ wpId: toRef(props, 'wpId'), projectId: toRef(props, 'projectId') })
const state = useH5Stocktake({ allResponses: allResponsesRef as any, wpId: toRef(props, 'wpId'), projectId: toRef(props, 'projectId'), onSave: (itemId: string, value: any) => formData.setResponse(itemId, value) })

// 审计说明/结论（component-local H5-11，conclusion:null）
const NOTE_KEY = 'H5-11-audit-note'
const CONCLUSION_KEY = 'H5-11-audit-conclusion'
const auditNoteText = ref('')
const auditConclusionText = ref('')
function savePolishNote(val: string): void {
  if (props.isReadonly) return
  auditNoteText.value = val
  props.allResponses.set(NOTE_KEY, { item_id: NOTE_KEY, conclusion: null, remark: val })
  void formData.saveResponse(NOTE_KEY, val)
}
function savePolishConclusion(val: string): void {
  if (props.isReadonly) return
  auditConclusionText.value = val
  props.allResponses.set(CONCLUSION_KEY, { item_id: CONCLUSION_KEY, conclusion: null, remark: val })
  void formData.saveResponse(CONCLUSION_KEY, val)
}
onMounted(() => {
  const n = props.allResponses.get(NOTE_KEY)
  if (n?.remark) auditNoteText.value = n.remark
  const c = props.allResponses.get(CONCLUSION_KEY)
  if (c?.remark) auditConclusionText.value = c.remark
})

function handleReview(id: string) { openReviewDialog(id) }
function fmtAmt(val: number | null | undefined): string { return val == null ? '-' : val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) }
</script>

<style scoped>
.h5-tab-stocktake-summary { padding: 16px; font-size: var(--wp-font-size, 13px); }
.objective-alert { margin-bottom: 12px; }
.tab-toolbar { display: flex; justify-content: flex-end; align-items: center; margin-bottom: 8px; }
.toolbar-right { display: flex; gap: 6px; align-items: center; }
.chip-wrap { display: inline-flex; align-items: center; }
.audit-note-card { margin-top: 16px; }
.audit-note-card .card-header { display: flex; justify-content: space-between; align-items: center; font-weight: 500; }
.block-card { margin-bottom: 16px; }
.section-title { display: flex; align-items: center; justify-content: space-between; }
.title-actions { display: flex; gap: 8px; }
.linked-summary { margin-bottom: 16px; }
.summary-sections { display: flex; flex-direction: column; gap: 16px; }
.summary-section label { display: block; font-weight: 600; margin-bottom: 6px; color: var(--el-text-color-primary); }
.compile-hint { margin-top: 12px; font-size: 12px; color: var(--el-text-color-secondary); }
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ul { padding-left: 20px; margin-top: 8px; }
</style>
