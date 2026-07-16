<script setup lang="ts">
/**
 * F2TabCostComparison — F2-20 产成品单位成本年度比较分析表
 */
import { inject, toRef, type Ref } from 'vue'
import { useF2CostComparison } from '../../composables/useF2CostComparison'
import { useF2AiGenerate } from '../../composables/useF2AiGenerate'
import type { ChecklistResponse } from '../../composables/useF2FormData'
import CycleImportExportDropdown from '../../shared/CycleImportExportDropdown.vue'
import F2ReviewChip from '../shared/F2ReviewChip.vue'
import GtIndexChip from '../../GtIndexChip.vue'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, ChecklistResponse>
  isReadonly: boolean
}>()

const reloadWorkpaperData = inject<(() => Promise<void>) | null>('reloadWorkpaperData', null)
async function onImported() { await reloadWorkpaperData?.() }

const cost = useF2CostComparison({
  allResponses: toRef(props, 'allResponses') as Ref<Map<string, ChecklistResponse>>,
  isReadonly: toRef(props, 'isReadonly') as Ref<boolean>,
})

const {
  enrichedRows,
  anomalyCount,
  conclusion,
  auditNote,
  addRow,
  removeRow,
  updateCell,
  aiContext,
} = cost

const { aiAvailable, loading: aiLoading, generateAndConfirm } = useF2AiGenerate(
  toRef(props, 'wpId') as Ref<string>,
)

const YES_NO = [
  { label: '是', value: '是' },
  { label: '否', value: '否' },
  { label: '—', value: '' },
]

function fmt(v: number): string {
  if (!v) return '-'
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 4 })
}
function fmtPct(v: number | null | undefined): string {
  if (v == null || Number.isNaN(v)) return '-'
  return `${v.toFixed(2)}%`
}

function saveNote(v: string) { auditNote.value = v }
function saveConclusion(v: string) { conclusion.value = v }

async function genNote() {
  const text = await generateAndConfirm('f2-20-note', auditNote.value, aiContext(), 'AI 生成 · F2-20 审计说明')
  if (text) auditNote.value = text
}
async function genConclusion() {
  const text = await generateAndConfirm(
    'f2-20-conclusion',
    conclusion.value,
    aiContext(),
    'AI 生成 · 成本比较结论',
  )
  if (text) conclusion.value = text
}
</script>

<template>
  <div class="f2-cost-comparison">
    <details class="guidance-details">
      <summary>编制提示</summary>
      <div class="guidance-content">
        <p>1. 按产品录入本年/上年单位成本构成（直接材料、直接人工、制造费用）；合计与波动比例自动计算。</p>
        <p>2. 单位成本合计波动率默认阈值 20%，超阈值自动提示异常；可手工标记「是否异常」并填写进一步审计底稿索引（如 F2-64 / F2-61）。</p>
        <p>3. 异常波动原因写入审计说明，材料价格等可交叉索引采购测试底稿。</p>
      </div>
    </details>

    <el-alert
      type="info"
      :closable="false"
      show-icon
      class="objective-alert"
      title="审计目标：比较产成品单位成本构成及同比波动，识别异常成本变动，验证成本结转合理性，并为深挖分析提供索引。"
    />

    <div class="tab-toolbar">
      <div class="toolbar-left">
        <el-button size="small" type="primary" :disabled="isReadonly" @click="addRow">+ 新增产品</el-button>
        <el-tag v-if="anomalyCount > 0" type="danger" size="small">异常 {{ anomalyCount }} 项</el-tag>
        <F2ReviewChip section-id="F2-20-cost" />
      </div>
      <div class="toolbar-right">
        <CycleImportExportDropdown
          :wp-id="wpId"
          api-prefix="f2"
          sheet="F2-20"
          :disabled="isReadonly"
          @imported="onImported"
        />
        <span class="chip-wrap"><GtIndexChip value="wp:F2-20" :context-project-id="projectId" :validate="false" /></span>
        <span class="chip-wrap"><GtIndexChip value="wp:F2-64" :context-project-id="projectId" :validate="false" /></span>
      </div>
    </div>

    <el-card shadow="never" class="block-card">
      <template #header><span class="block-title">产成品单位成本年度比较</span></template>
      <div class="table-scroll">
        <el-table :data="enrichedRows" border size="small" :row-class-name="({ row }) => row.isAnomaly ? 'anomaly-row' : ''">
          <el-table-column label="产品名称" width="130" fixed>
            <template #default="{ row }">
              <el-input v-if="!isReadonly" :model-value="row.productName" size="small"
                @change="(v: string) => updateCell(row.rowId, 'productName', v)" />
              <span v-else>{{ row.productName }}</span>
            </template>
          </el-table-column>

          <el-table-column label="本年单位成本" align="center">
            <el-table-column label="直接材料" width="100" align="right">
              <template #default="{ row }">
                <el-input-number v-if="!isReadonly" :model-value="row.currentMaterial" :controls="false" size="small" style="width:100%"
                  @change="(v: number) => updateCell(row.rowId, 'currentMaterial', v ?? 0)" />
                <span v-else>{{ fmt(row.currentMaterial) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="直接人工" width="100" align="right">
              <template #default="{ row }">
                <el-input-number v-if="!isReadonly" :model-value="row.currentLabor" :controls="false" size="small" style="width:100%"
                  @change="(v: number) => updateCell(row.rowId, 'currentLabor', v ?? 0)" />
                <span v-else>{{ fmt(row.currentLabor) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="制造费用" width="100" align="right">
              <template #default="{ row }">
                <el-input-number v-if="!isReadonly" :model-value="row.currentOverhead" :controls="false" size="small" style="width:100%"
                  @change="(v: number) => updateCell(row.rowId, 'currentOverhead', v ?? 0)" />
                <span v-else>{{ fmt(row.currentOverhead) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="合计" width="100" align="right" class-name="auto-calc-col">
              <template #default="{ row }">{{ fmt(row.currentTotal) }}</template>
            </el-table-column>
          </el-table-column>

          <el-table-column label="上年单位成本" align="center">
            <el-table-column label="直接材料" width="100" align="right">
              <template #default="{ row }">
                <el-input-number v-if="!isReadonly" :model-value="row.priorMaterial" :controls="false" size="small" style="width:100%"
                  @change="(v: number) => updateCell(row.rowId, 'priorMaterial', v ?? 0)" />
                <span v-else>{{ fmt(row.priorMaterial) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="直接人工" width="100" align="right">
              <template #default="{ row }">
                <el-input-number v-if="!isReadonly" :model-value="row.priorLabor" :controls="false" size="small" style="width:100%"
                  @change="(v: number) => updateCell(row.rowId, 'priorLabor', v ?? 0)" />
                <span v-else>{{ fmt(row.priorLabor) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="制造费用" width="100" align="right">
              <template #default="{ row }">
                <el-input-number v-if="!isReadonly" :model-value="row.priorOverhead" :controls="false" size="small" style="width:100%"
                  @change="(v: number) => updateCell(row.rowId, 'priorOverhead', v ?? 0)" />
                <span v-else>{{ fmt(row.priorOverhead) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="合计" width="100" align="right" class-name="auto-calc-col">
              <template #default="{ row }">{{ fmt(row.priorTotal) }}</template>
            </el-table-column>
          </el-table-column>

          <el-table-column label="波动比例" align="center">
            <el-table-column label="直接材料" width="90" align="right" class-name="auto-calc-col">
              <template #default="{ row }">
                <span :class="{ abnormal: row.matRate != null && Math.abs(row.matRate) > 20 }">{{ fmtPct(row.matRate) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="直接人工" width="90" align="right" class-name="auto-calc-col">
              <template #default="{ row }">
                <span :class="{ abnormal: row.laborRate != null && Math.abs(row.laborRate) > 20 }">{{ fmtPct(row.laborRate) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="制造费用" width="90" align="right" class-name="auto-calc-col">
              <template #default="{ row }">
                <span :class="{ abnormal: row.ohRate != null && Math.abs(row.ohRate) > 20 }">{{ fmtPct(row.ohRate) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="合计" width="90" align="right" class-name="auto-calc-col">
              <template #default="{ row }">
                <span :class="{ abnormal: row.isAnomaly }">{{ fmtPct(row.totalRate) }}</span>
              </template>
            </el-table-column>
          </el-table-column>

          <el-table-column label="是否异常" width="100" align="center">
            <template #default="{ row }">
              <el-select v-if="!isReadonly" :model-value="row.abnormal" size="small"
                @change="(v: string) => updateCell(row.rowId, 'abnormal', v)">
                <el-option v-for="o in YES_NO" :key="o.value" :label="o.label" :value="o.value" />
              </el-select>
              <el-tag v-else-if="row.isAnomaly" size="small" type="danger">是</el-tag>
              <span v-else>{{ row.abnormal || '—' }}</span>
            </template>
          </el-table-column>
          <el-table-column label="进一步审计底稿索引" width="140">
            <template #default="{ row }">
              <el-input v-if="!isReadonly" :model-value="row.indexRef" size="small" placeholder="如 F2-64"
                @change="(v: string) => updateCell(row.rowId, 'indexRef', v)" />
              <GtIndexChip v-else-if="row.indexRef" :value="row.indexRef.startsWith('wp:') ? row.indexRef : `wp:${row.indexRef}`" :context-project-id="projectId" :validate="false" />
              <span v-else>—</span>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="55" fixed="right">
            <template #default="{ row }">
              <el-button link type="danger" size="small" :disabled="isReadonly" @click="removeRow(row.rowId)">删</el-button>
            </template>
          </el-table-column>
        </el-table>
      </div>
    </el-card>

    <el-card shadow="never" class="audit-note-card">
      <template #header>
        <div class="note-head">
          <span>审计说明</span>
          <el-button size="small" :disabled="isReadonly || !aiAvailable" :loading="aiLoading" @click="genNote">AI辅助</el-button>
        </div>
      </template>
      <el-input
        type="textarea"
        :model-value="auditNote"
        :disabled="isReadonly"
        :autosize="{ minRows: 5 }"
        placeholder="例：1. XX产品单位成本异常波动原因见 F2-64；2. 原材料采购价格进一步分析见 F2-61…"
        @change="saveNote"
      />
    </el-card>

    <el-card class="opinion-card audit-note-card" shadow="never">
      <template #header>
        <div class="opinion-header">
          <span class="opinion-title">审计结论</span>
          <div class="opinion-actions">
            <el-button
              size="small"
              type="primary"
              plain
              :disabled="isReadonly || !aiAvailable"
              :loading="aiLoading"
              @click="genConclusion"
            >AI辅助</el-button>
            <F2ReviewChip section-id="F2-20-conclusion" />
          </div>
        </div>
      </template>
      <el-input
        type="textarea"
        :model-value="conclusion"
        :disabled="isReadonly"
        :autosize="{ minRows: 3 }"
        placeholder="A、未见异常。B、除上述重大不符事项应作为调整事项予以调整外，其余未见异常。C、由于存在以下重大未调整事项（或审计范围受到限制），不可确认。"
        @change="saveConclusion"
      />
    </el-card>
  </div>
</template>

<style scoped>
.f2-cost-comparison { padding: 12px; font-size: 13px; font-size: var(--wp-font-size, 13px); }
.f2-cost-comparison :deep(.el-table) {
  --el-table-font-size: var(--wp-font-size, 13px);
  font-size: var(--wp-font-size, 13px);
}
.f2-cost-comparison :deep(.el-table .cell) { font-size: var(--wp-font-size, 13px) !important; }
.guidance-details {
  margin-bottom: 12px; border-left: 3px solid #409eff; background: #ecf5ff;
  border-radius: 4px; padding: 8px 12px;
}
.guidance-details summary { cursor: pointer; font-weight: 500; color: #409eff; }
.guidance-content { margin-top: 8px; color: #606266; line-height: 1.6; }
.guidance-content p { margin: 2px 0; }
.objective-alert { margin-bottom: 12px; }
.tab-toolbar {
  display: flex; justify-content: space-between; align-items: center;
  margin-bottom: 8px; gap: 8px; flex-wrap: wrap;
}
.toolbar-left, .toolbar-right { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.chip-wrap { display: inline-flex; align-items: center; }
.block-card { margin-bottom: 12px; }
.block-title { font-weight: 600; }
.table-scroll { overflow-x: auto; }
.abnormal { color: #f56c6c; font-weight: 600; }
:deep(.auto-calc-col) { background-color: #f5f7fa !important; }
:deep(.anomaly-row) { background: #fef0f0; }
.note-head {
  display: flex; justify-content: space-between; align-items: center; font-weight: 500;
}
.opinion-card { margin-top: 16px; border-radius: 8px; }
.opinion-card :deep(.el-card__header) { padding: 12px 16px; background: #fafafa; border-bottom: 1px solid #ebeef5; }
.opinion-header { display: flex; align-items: center; justify-content: space-between; }
.opinion-title { font-size: 14px; font-weight: 600; color: #303133; }
.opinion-actions { display: flex; gap: 6px; align-items: center; }
.audit-note-card { margin-top: 16px; }
</style>
