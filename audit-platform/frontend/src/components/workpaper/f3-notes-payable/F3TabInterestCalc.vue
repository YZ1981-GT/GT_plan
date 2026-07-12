<script setup lang="ts">
/** F3TabInterestCalc — F3-4 带息票据利息测算 | Task 6.3, 9.3 */
import { ref, toRef, inject, type Ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import http from '@/utils/http'
import { useF3InterestCalc, type F3NoteOcrFields } from '../composables/useF3InterestCalc'
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

const { rows, totals, auditConclusion, addRow, removeRow, updateCell, rowClassName, mergeOcrFields } = useF3InterestCalc({
  wpId: toRef(props, 'wpId') as Ref<string>,
  projectId: toRef(props, 'projectId') as Ref<string>,
  allResponses: toRef(props, 'allResponses') as Ref<Map<string, any>>,
  isReadonly: toRef(props, 'isReadonly') as Ref<boolean>,
})

const { aiAvailable, loading: aiLoading, generateAndConfirm } = useF3AiGenerate(toRef(props, 'wpId') as Ref<string>)

async function generateAiConclusion() {
  if (props.isReadonly) return
  const text = await generateAndConfirm(
    'interest-conclusion',
    auditConclusion.value,
    {
      rowCount: rows.value.length,
      totalFaceValue: totals.value.faceValue,
      totalPayableInterest: totals.value.payableInterest,
      totalVariance: totals.value.variance,
    },
    'AI 生成 · 利息测算结论',
  )
  if (text) auditConclusion.value = text
}

const ocrLoadingId = ref<string | null>(null)

async function handleNoteOcr(rowId: string, file: File) {
  if (props.isReadonly) return
  ocrLoadingId.value = rowId
  const formData = new FormData()
  formData.append('file', file)

  try {
    const res = await http.post(
      `/api/workpapers/${props.wpId}/f3/contract-ocr`,
      formData,
      { headers: { 'Content-Type': 'multipart/form-data' }, _silent: true } as any,
    )
    const data = res.data?.data ?? res.data
    const { extracted_fields: fields, confidence } = data

    const fieldSummary = Object.entries(fields || {})
      .filter(([, v]) => v != null && v !== '' && v !== 0)
      .map(([k, v]) => `${k}: ${v}`)
      .join('\n')

    await ElMessageBox.confirm(
      `OCR识别完成（置信度: ${((confidence || 0) * 100).toFixed(0)}%）\n\n提取字段：\n${fieldSummary || '（未提取到有效信息）'}\n\n是否将提取结果填入当前行？`,
      '票据OCR提取结果',
      { confirmButtonText: '填入（覆盖空字段）', cancelButtonText: '取消', type: 'info' },
    )
    mergeOcrFields(rowId, fields as F3NoteOcrFields, false)
    ElMessage.success('OCR结果已填入')
  } catch (err: any) {
    if (err !== 'cancel' && err?.message !== 'cancel') {
      ElMessage.warning('OCR识别失败，请手动填写')
    }
  } finally {
    ocrLoadingId.value = null
  }
}
</script>

<template>
  <div class="f3-tab-interest">
    <!-- 编制提示 -->
    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 针对带息应付票据独立测算应付利息：应付利息 = 面值 × 票面利率 / 100 × 应计天数 / 360。</p>
        <p>2. 灰底虚线列（应计天数、应付利息、差异）为公式列，不可手工编辑；测算数与企业账面计提数比较。</p>
        <p>3. 差异&gt;100 元橙色高亮，重大差异应提请调整（补提或冲回应付利息）。</p>
        <p>4. 📎 列可上传票据/合同影像进行 OCR 识别，自动填充出票人、面值、利率、计息区间等字段。</p>
      </div>
    </details>

    <!-- 审计目标 -->
    <el-alert
      type="info"
      :closable="false"
      title="审计目标：独立测算带息应付票据应付利息，验证利息费用与应付利息计提的准确性与完整性。"
      class="objective-alert"
    />

    <!-- 工具栏 -->
    <div class="tab-toolbar">
      <div class="toolbar-left">
        <el-button size="small" type="primary" :disabled="isReadonly" @click="addRow">+ 添加行</el-button>
      </div>
      <div class="toolbar-right">
        <F3ImportExportToolbar :wp-id="wpId" :project-id="projectId" sheet="F3-4" :disabled="isReadonly" @imported="onImported" />
        <span class="chip-wrap"><GtIndexChip value="wp:F3-2" :context-project-id="projectId" /></span>
        <el-tag size="small" type="info">共 {{ rows.length }} 行</el-tag>
      </div>
    </div>

    <el-table :data="rows" border size="small" :row-class-name="rowClassName" style="width: 100%">
      <el-table-column prop="seq" label="序号" width="55" />
      <el-table-column label="📎" width="45" align="center">
        <template #default="{ row }">
          <el-upload :show-file-list="false" :auto-upload="false" :disabled="isReadonly || ocrLoadingId === row.rowId"
            @change="(f: any) => handleNoteOcr(row.rowId, f.raw || f)">
            <el-button link size="small" :loading="ocrLoadingId === row.rowId">📎</el-button>
          </el-upload>
        </template>
      </el-table-column>
      <el-table-column label="出票人" min-width="100">
        <template #default="{ row }"><el-input v-if="!isReadonly" :model-value="row.drawer" size="small" @change="(v: string) => updateCell(row.rowId, 'drawer', v)" /><span v-else>{{ row.drawer }}</span></template>
      </el-table-column>
      <el-table-column label="面值" width="110" align="right">
        <template #default="{ row }"><el-input-number v-if="!isReadonly" :model-value="row.faceValue" :controls="false" size="small" style="width:100%" @change="(v: number) => updateCell(row.rowId, 'faceValue', v ?? 0)" /><span v-else>{{ fmt(row.faceValue) }}</span></template>
      </el-table-column>
      <el-table-column label="利率%" width="80" align="right">
        <template #default="{ row }"><el-input-number v-if="!isReadonly" :model-value="row.interestRate" :controls="false" size="small" style="width:100%" @change="(v: number) => updateCell(row.rowId, 'interestRate', v ?? 0)" /><span v-else>{{ row.interestRate }}</span></template>
      </el-table-column>
      <el-table-column label="计息起始" width="110">
        <template #default="{ row }"><el-input v-if="!isReadonly" :model-value="row.interestStart" size="small" @change="(v: string) => updateCell(row.rowId, 'interestStart', v)" /><span v-else>{{ row.interestStart }}</span></template>
      </el-table-column>
      <el-table-column label="计息截止" width="110">
        <template #default="{ row }"><el-input v-if="!isReadonly" :model-value="row.interestEnd" size="small" @change="(v: string) => updateCell(row.rowId, 'interestEnd', v)" /><span v-else>{{ row.interestEnd }}</span></template>
      </el-table-column>
      <el-table-column label="应计天数" width="90" align="right" class-name="auto-calc-col">
        <template #default="{ row }"><span class="formula-cell">{{ row.accruedDays }}</span></template>
      </el-table-column>
      <el-table-column label="应付利息" width="110" align="right" class-name="auto-calc-col">
        <template #default="{ row }"><span class="formula-cell">{{ fmt(row.payableInterest) }}</span></template>
      </el-table-column>
      <el-table-column label="企业计提" width="110" align="right">
        <template #default="{ row }"><el-input-number v-if="!isReadonly" :model-value="row.bookInterest" :controls="false" size="small" style="width:100%" @change="(v: number) => updateCell(row.rowId, 'bookInterest', v ?? 0)" /><span v-else>{{ fmt(row.bookInterest) }}</span></template>
      </el-table-column>
      <el-table-column label="差异" width="100" align="right" class-name="auto-calc-col">
        <template #default="{ row }"><span class="formula-cell">{{ fmt(row.variance) }}</span></template>
      </el-table-column>
      <el-table-column label="操作" width="55"><template #default="{ row }"><el-button link type="danger" size="small" :disabled="isReadonly" @click="removeRow(row.rowId)">删</el-button></template></el-table-column>
    </el-table>

    <div class="subtotal">合计 — 面值 {{ fmt(totals.faceValue) }} | 应付利息 {{ fmt(totals.payableInterest) }} | 计提 {{ fmt(totals.bookInterest) }} | 差异 {{ fmt(totals.variance) }}</div>

    <!-- 审计意见区（卡片式） -->
    <el-card class="opinion-card" shadow="never">
      <template #header>
        <div class="opinion-header">
          <span class="opinion-title">审计结论</span>
          <div class="opinion-actions">
            <el-button size="small" type="primary" plain :disabled="isReadonly || !aiAvailable" :loading="aiLoading" @click="generateAiConclusion">🤖 AI辅助</el-button>
            <el-button size="small" @click="openReviewDialog?.('F3-4-conclusion')">💬</el-button>
          </div>
        </div>
      </template>
      <el-input v-model="auditConclusion" type="textarea" :autosize="{ minRows: 3, maxRows: 8 }" :disabled="isReadonly" placeholder="请输入利息测算审计结论..." />
    </el-card>
  </div>
</template>

<style scoped>
.f3-tab-interest {
  padding: 12px;
}
.f3-tab-interest :deep(.el-table) {
  --el-table-font-size: var(--wp-font-size, 13px);
  font-size: var(--wp-font-size, 13px);
}
.f3-tab-interest :deep(.el-table .cell) {
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
:deep(.variance-warn td) {
  background: #fdf6ec !important;
}
.subtotal {
  margin-top: 8px;
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
