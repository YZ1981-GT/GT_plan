<script setup lang="ts">
/** F3TabRelatedParty — F3-6 关联方检查 | Task 6.4 */
import { toRef, inject, type Ref } from 'vue'
import { useF3RelatedParty } from '../composables/useF3RelatedParty'
import { useF3AiGenerate } from '../composables/useF3AiGenerate'
import F3ImportExportToolbar from './F3ImportExportToolbar.vue'
import GtIndexChip from '../GtIndexChip.vue'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const reloadWorkpaperData = inject<(() => void) | null>('reloadWorkpaperData', null)
const openReviewDialog = inject<((sectionId: string) => void) | null>('openReviewDialog', null)
function onImported() { reloadWorkpaperData?.() }

function fmt(v: number): string {
  return v === 0 ? '-' : v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

const { rows, summary, auditNote, addRow, removeRow, updateCell, rowClassName } = useF3RelatedParty({
  wpId: toRef(props, 'wpId') as Ref<string>,
  projectId: toRef(props, 'projectId') as Ref<string>,
  allResponses: toRef(props, 'allResponses') as Ref<Map<string, any>>,
  isReadonly: toRef(props, 'isReadonly') as Ref<boolean>,
})

const { aiAvailable, loading: aiLoading, generateAndConfirm } = useF3AiGenerate(toRef(props, 'wpId') as Ref<string>)

async function generateAiNote() {
  if (props.isReadonly) return
  const text = await generateAndConfirm(
    'related-evaluation',
    auditNote.value,
    {
      partyCount: rows.value.length,
      totalFace: summary.value.totalFace,
      unfairCount: summary.value.unfairCount,
    },
    'AI 生成 · 关联方评价',
  )
  if (text) auditNote.value = text
}

const fairnessOptions = ['公允', '基本公允', '不公允', '无法判断']
</script>

<template>
  <div class="f3-tab-related">
    <!-- 编制提示 -->
    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 识别关联方开具、承兑或背书的应付票据，评估交易的商业实质与定价公允性。</p>
        <p>2. 单一关联方占比为公式列，占比&gt;30% 橙色高亮，提示集中度风险。</p>
        <p>3. 关注关联方票据是否用于资金占用、变相融资或调节报表，评价定价是否公允。</p>
        <p>4. 关联方应付票据及承兑关系应在附注按 CAS 36 关联方披露充分列示。</p>
      </div>
    </details>

    <!-- 审计目标 -->
    <el-alert
      type="info"
      :closable="false"
      title="审计目标：识别关联方应付票据交易，评价定价公允性与商业实质，确保关联方关系及交易充分披露。"
      class="objective-alert"
    />

    <!-- 工具栏 -->
    <div class="tab-toolbar">
      <div class="toolbar-left">
        <el-button size="small" type="primary" :disabled="isReadonly" @click="addRow">+ 添加行</el-button>
      </div>
      <div class="toolbar-right">
        <F3ImportExportToolbar :wp-id="wpId" :project-id="projectId" sheet="F3-6" :disabled="isReadonly" @imported="onImported" />
        <span class="chip-wrap"><GtIndexChip value="wp:F3-2" :context-project-id="projectId" /></span>
        <el-tag size="small" type="info">共 {{ rows.length }} 行</el-tag>
      </div>
    </div>

    <el-table :data="rows" border size="small" :row-class-name="rowClassName" style="width: 100%">
      <el-table-column prop="seq" label="序号" width="55" />
      <el-table-column label="关联方" min-width="120">
        <template #default="{ row }"><el-input v-if="!isReadonly" :model-value="row.partyName" size="small" @change="(v: string) => updateCell(row.rowId, 'partyName', v)" /><span v-else>{{ row.partyName }}</span></template>
      </el-table-column>
      <el-table-column label="关联关系" width="100">
        <template #default="{ row }"><el-input v-if="!isReadonly" :model-value="row.relationship" size="small" @change="(v: string) => updateCell(row.rowId, 'relationship', v)" /><span v-else>{{ row.relationship }}</span></template>
      </el-table-column>
      <el-table-column label="面值" width="110" align="right">
        <template #default="{ row }"><el-input-number v-if="!isReadonly" :model-value="row.faceValue" :controls="false" size="small" style="width:100%" @change="(v: number) => updateCell(row.rowId, 'faceValue', v ?? 0)" /><span v-else>{{ fmt(row.faceValue) }}</span></template>
      </el-table-column>
      <el-table-column label="占比%" width="90" align="right" class-name="auto-calc-col"><template #default="{ row }"><span class="formula-cell">{{ row.concentration.toFixed(2) }}%</span></template></el-table-column>
      <el-table-column label="定价公允性" width="110">
        <template #default="{ row }">
          <el-select v-if="!isReadonly" :model-value="row.fairness" size="small" @change="(v: string) => updateCell(row.rowId, 'fairness', v)">
            <el-option v-for="o in fairnessOptions" :key="o" :label="o" :value="o" />
          </el-select>
          <span v-else>{{ row.fairness }}</span>
        </template>
      </el-table-column>
      <el-table-column label="审计评价" min-width="120">
        <template #default="{ row }"><el-input v-if="!isReadonly" :model-value="row.auditEvaluation" size="small" @change="(v: string) => updateCell(row.rowId, 'auditEvaluation', v)" /><span v-else>{{ row.auditEvaluation }}</span></template>
      </el-table-column>
      <el-table-column label="操作" width="55"><template #default="{ row }"><el-button link type="danger" size="small" :disabled="isReadonly" @click="removeRow(row.rowId)">删</el-button></template></el-table-column>
    </el-table>

    <div class="summary">关联方票据合计 {{ fmt(summary.totalFace) }} | 不公允 {{ summary.unfairCount }} 笔</div>

    <!-- 审计意见区（卡片式） -->
    <el-card class="opinion-card" shadow="never">
      <template #header>
        <div class="opinion-header">
          <span class="opinion-title">审计说明</span>
          <div class="opinion-actions">
            <el-button size="small" type="primary" plain :disabled="isReadonly || !aiAvailable" :loading="aiLoading" @click="generateAiNote">🤖 AI辅助</el-button>
            <el-button size="small" @click="openReviewDialog?.('F3-6-note')">💬</el-button>
          </div>
        </div>
      </template>
      <el-input v-model="auditNote" type="textarea" :autosize="{ minRows: 3, maxRows: 8 }" :disabled="isReadonly" placeholder="请输入关联方应付票据评价..." />
    </el-card>
  </div>
</template>

<style scoped>
.f3-tab-related {
  padding: 12px;
}
.f3-tab-related :deep(.el-table) {
  --el-table-font-size: 13px;
  font-size: 13px;
}
.f3-tab-related :deep(.el-table .cell) {
  font-size: 13px !important;
}
.guidance-details {
  margin-bottom: 12px;
  border-left: 3px solid #409eff;
  background: #ecf5ff;
  border-radius: 4px;
  padding: 8px 12px;
}
.guidance-details summary {
  cursor: pointer;
  font-weight: 500;
  color: #409eff;
}
.guidance-content {
  margin-top: 8px;
  font-size: 13px;
  color: #606266;
  line-height: 1.6;
}
.guidance-content p {
  margin: 2px 0;
}
.objective-alert {
  margin-bottom: 12px;
}
.tab-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}
.toolbar-left {
  display: flex;
  gap: 8px;
  align-items: center;
}
.toolbar-right {
  display: flex;
  gap: 6px;
  align-items: center;
}
.chip-wrap { display: inline-flex; align-items: center; }
.formula-cell {
  background: #f5f7fa;
  border-bottom: 1px dashed #c0c4cc;
  cursor: help;
}
:deep(.auto-calc-col) {
  background-color: #f5f7fa !important;
}
:deep(.concentration-warn td) {
  background: #fdf6ec !important;
}
.summary {
  margin: 8px 0;
  text-align: right;
  font-weight: 600;
}
.opinion-card {
  margin-top: 16px;
  border-radius: 8px;
}
.opinion-card :deep(.el-card__header) {
  padding: 12px 16px;
  background: #fafafa;
  border-bottom: 1px solid #ebeef5;
}
.opinion-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.opinion-title {
  font-size: 14px;
  font-weight: 600;
  color: #303133;
}
.opinion-actions {
  display: flex;
  gap: 6px;
}
</style>
