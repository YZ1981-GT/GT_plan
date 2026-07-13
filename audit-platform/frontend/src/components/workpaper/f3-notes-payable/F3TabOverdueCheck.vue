<script setup lang="ts">
/** F3TabOverdueCheck — F3-5 逾期票据检查 | Task 6.4 */
import { ref, watch, toRef, inject, type Ref } from 'vue'
import { useF3OverdueCheck } from '../composables/useF3OverdueCheck'
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

const { rows, summary, auditConclusion, addRow, removeRow, updateCell, rowClassName } = useF3OverdueCheck({
  wpId: toRef(props, 'wpId') as Ref<string>,
  projectId: toRef(props, 'projectId') as Ref<string>,
  allResponses: toRef(props, 'allResponses') as Ref<Map<string, any>>,
  isReadonly: toRef(props, 'isReadonly') as Ref<boolean>,
})

const { aiAvailable, loading: aiLoading, generateAndConfirm } = useF3AiGenerate(toRef(props, 'wpId') as Ref<string>)

// ─── 审计说明（无匹配 AI section → 纯 textarea；F3 约定持久化） ───
const NOTE_KEY = 'F3-5-note'
const auditNote = ref('')
function saveAuditNote(val: string): void {
  if (props.isReadonly) return
  auditNote.value = val
  const item = { item_id: NOTE_KEY, conclusion: null, remark: val }
  props.allResponses.set(NOTE_KEY, item)
  window.dispatchEvent(new CustomEvent('f3:save-items', { detail: { items: [item] } }))
}
watch(() => props.allResponses.get(NOTE_KEY)?.remark, (v) => { if (typeof v === 'string') auditNote.value = v }, { immediate: true })

async function generateAiConclusion() {
  if (props.isReadonly) return
  const text = await generateAndConfirm(
    'overdue-evaluation',
    auditConclusion.value,
    {
      overdueCount: summary.value.count,
      overdueAmount: summary.value.totalAmount,
      highRiskCount: summary.value.highRisk,
      transferredCount: summary.value.transferred,
    },
    'AI 生成 · 逾期检查评价',
  )
  if (text) auditConclusion.value = text
}

const riskOptions = ['低', '中', '高', '极高']
</script>

<template>
  <div class="f3-tab-overdue">
    <!-- 编制提示 -->
    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 筛查已到期未兑付/临近到期的应付票据，评估兑付风险与后续会计处理。</p>
        <p>2. 逾期天数为公式列（今天 - 到期日）：&gt;90 天建议高风险（红色），&gt;30 天橙色高亮。</p>
        <p>3. 到期未兑付的商业承兑汇票应转入应付账款，银行承兑垫款应关注是否形成短期借款。</p>
        <p>4. 关注逾期票据是否触发违约条款、罚息计提及对信用与持续经营的影响。</p>
      </div>
    </details>

    <!-- 审计目标 -->
    <el-alert
      type="info"
      :closable="false"
      title="审计目标：识别逾期及临期应付票据，评估兑付风险，确认到期未兑付票据的重分类与计量恰当。"
      class="objective-alert"
    />

    <!-- 工具栏 -->
    <div class="tab-toolbar">
      <div class="toolbar-left">
        <el-button size="small" type="primary" :disabled="isReadonly" @click="addRow">+ 添加行</el-button>
      </div>
      <div class="toolbar-right">
        <F3ImportExportToolbar :wp-id="wpId" :project-id="projectId" sheet="F3-5" :disabled="isReadonly" @imported="onImported" />
        <span class="chip-wrap"><GtIndexChip value="wp:F3-2" :context-project-id="projectId" /></span>
        <el-tag size="small" type="info">共 {{ rows.length }} 行</el-tag>
      </div>
    </div>

    <el-table :data="rows" border size="small" :row-class-name="rowClassName" style="width: 100%">
      <el-table-column prop="seq" label="序号" width="55" />
      <el-table-column label="出票人" min-width="100">
        <template #default="{ row }"><el-input v-if="!isReadonly" :model-value="row.drawer" size="small" @change="(v: string) => updateCell(row.rowId, 'drawer', v)" /><span v-else>{{ row.drawer }}</span></template>
      </el-table-column>
      <el-table-column label="到期日" width="110">
        <template #default="{ row }"><el-input v-if="!isReadonly" :model-value="row.dueDate" size="small" @change="(v: string) => updateCell(row.rowId, 'dueDate', v)" /><span v-else>{{ row.dueDate }}</span></template>
      </el-table-column>
      <el-table-column label="面值" width="100" align="right">
        <template #default="{ row }"><el-input-number v-if="!isReadonly" :model-value="row.faceValue" :controls="false" size="small" style="width:100%" @change="(v: number) => updateCell(row.rowId, 'faceValue', v ?? 0)" /><span v-else>{{ fmt(row.faceValue) }}</span></template>
      </el-table-column>
      <el-table-column label="逾期天数" width="90" align="right" class-name="auto-calc-col"><template #default="{ row }"><span class="formula-cell">{{ row.overdueDays }}</span></template></el-table-column>
      <el-table-column label="风险等级" width="100">
        <template #default="{ row }">
          <el-select v-if="!isReadonly" :model-value="row.riskLevel" size="small" @change="(v: string) => updateCell(row.rowId, 'riskLevel', v)">
            <el-option v-for="o in riskOptions" :key="o" :label="o" :value="o" />
          </el-select>
          <span v-else>{{ row.riskLevel }}</span>
        </template>
      </el-table-column>
      <el-table-column label="审计建议" min-width="120">
        <template #default="{ row }"><el-input v-if="!isReadonly" :model-value="row.auditAdvice" size="small" @change="(v: string) => updateCell(row.rowId, 'auditAdvice', v)" /><span v-else>{{ row.auditAdvice }}</span></template>
      </el-table-column>
      <el-table-column label="操作" width="55"><template #default="{ row }"><el-button link type="danger" size="small" :disabled="isReadonly" @click="removeRow(row.rowId)">删</el-button></template></el-table-column>
    </el-table>

    <div class="summary">逾期 {{ summary.count }} 笔 / 金额 {{ fmt(summary.totalAmount) }} / 高风险 {{ summary.highRisk }} 笔 / 已转应付 {{ summary.transferred }} 笔</div>

    <!-- 审计说明 -->
    <el-card class="opinion-card" shadow="never">
      <template #header>
        <div class="opinion-header"><span class="opinion-title">审计说明</span></div>
      </template>
      <el-input
        v-model="auditNote"
        type="textarea"
        :autosize="{ minRows: 5 }"
        :disabled="isReadonly"
        placeholder="填写审计说明：逾期票据筛查情况、兑付风险评估、到期未兑付票据的重分类与后续处理。"
        @change="(v: string) => saveAuditNote(v)"
      />
    </el-card>

    <!-- 审计意见区（卡片式） -->
    <el-card class="opinion-card" shadow="never">
      <template #header>
        <div class="opinion-header">
          <span class="opinion-title">审计结论</span>
          <div class="opinion-actions">
            <el-button size="small" type="primary" plain :disabled="isReadonly || !aiAvailable" :loading="aiLoading" @click="generateAiConclusion">🤖 AI辅助</el-button>
            <el-button size="small" @click="openReviewDialog?.('F3-5-conclusion')">💬</el-button>
          </div>
        </div>
      </template>
      <el-input v-model="auditConclusion" type="textarea" :autosize="{ minRows: 3, maxRows: 8 }" :disabled="isReadonly" placeholder="请输入逾期票据检查评价..." />
    </el-card>
  </div>
</template>

<style scoped>
.f3-tab-overdue {
  padding: 12px;
}
.f3-tab-overdue :deep(.el-table) {
  --el-table-font-size: var(--wp-font-size, 13px);
  font-size: var(--wp-font-size, 13px);
}
.f3-tab-overdue :deep(.el-table .cell) {
  font-size: var(--wp-font-size, 13px) !important;
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
  font-size: var(--wp-font-size, 13px);
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
:deep(.risk-high td) {
  background: #fef0f0 !important;
}
:deep(.risk-medium td) {
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
