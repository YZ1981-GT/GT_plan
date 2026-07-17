<script setup lang="ts">
/**
 * F2TabCostComparison — F2-20 产成品单位成本年度比较分析表
 * 功能参照 F2-18：期间标签、阈值、表+说明/异常原因、总体结论、AI
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
  pack,
  yearLabels,
  enrichedRows,
  totals,
  anomalyCount,
  notes,
  conclusion,
  updateYearLabel,
  updateThreshold,
  updateNotes,
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
  { label: '自动', value: '' },
]

function fmt(v: number): string {
  if (!v) return '-'
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 4 })
}
function fmtPct(v: number | null | undefined): string {
  if (v == null || Number.isNaN(v)) return '-'
  return `${v.toFixed(2)}%`
}

async function genSection(
  section: 'f2-20-note' | 'f2-20-abnormal' | 'f2-20-conclusion',
  existing: string,
  title: string,
  apply: (text: string) => void,
) {
  const text = await generateAndConfirm(section, existing, aiContext(), title)
  if (text) apply(text)
}

function saveConclusion(v: string) {
  conclusion.value = v
}

function thresholdPctModel(): number {
  return Math.round((pack.value.anomalyThreshold || 0.2) * 1000) / 10
}
function setThresholdPct(v: number) {
  updateThreshold((v ?? 20) / 100)
}
</script>

<template>
  <div class="f2-cost-comparison">
    <details class="guidance-details">
      <summary>编制提示</summary>
      <div class="guidance-content">
        <p>1. 按产品录入本年/上年单位成本构成（直接材料、直接人工、制造费用）；合计与波动比例自动计算。</p>
        <p>2. 单位成本合计波动超阈值时自动提示异常；可手工标记「是否异常」并填写进一步审计底稿索引（如 F2-64 / F2-61）。</p>
        <p>3. 异常波动原因写入「异常原因」，程序概述写入「审计说明」；材料价格等可交叉索引采购测试底稿。</p>
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
        <el-tag v-if="anomalyCount > 0" type="danger" size="small">异常标记 {{ anomalyCount }} 项</el-tag>
        <span class="thr-label">异常阈值</span>
        <el-input-number
          size="small"
          :model-value="thresholdPctModel()"
          :min="1"
          :max="100"
          :step="1"
          :controls="false"
          style="width: 72px"
          :disabled="isReadonly"
          @change="(v: number) => setThresholdPct(v ?? 20)"
        />
        <span class="thr-unit">%</span>
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
        <span class="chip-wrap"><GtIndexChip value="wp:F2-61" :context-project-id="projectId" :validate="false" /></span>
      </div>
    </div>

    <div class="year-labels">
      <span>期间标签：</span>
      <el-input
        size="small"
        style="width: 120px"
        :model-value="yearLabels[0]"
        :disabled="isReadonly"
        @change="(v: string) => updateYearLabel(0, v)"
      />
      <el-input
        size="small"
        style="width: 120px"
        :model-value="yearLabels[1]"
        :disabled="isReadonly"
        @change="(v: string) => updateYearLabel(1, v)"
      />
    </div>

    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="card-header-flex">
          <span class="block-title">一、产成品单位成本年度比较</span>
          <el-button size="small" type="primary" :disabled="isReadonly" @click="addRow">+ 新增产品</el-button>
        </div>
      </template>
      <div class="table-scroll">
        <el-table
          :data="enrichedRows"
          border
          size="small"
          :row-class-name="({ row }) => row.isAnomaly ? 'anomaly-row' : ''"
        >
          <el-table-column label="产品名称" width="130" fixed>
            <template #default="{ row }">
              <el-input
                v-if="!isReadonly"
                :model-value="row.productName"
                size="small"
                @change="(v: string) => updateCell(row.rowId, 'productName', v)"
              />
              <span v-else>{{ row.productName }}</span>
            </template>
          </el-table-column>

          <el-table-column :label="yearLabels[0] + '单位成本'" align="center">
            <el-table-column label="直接材料" width="100" align="right">
              <template #default="{ row }">
                <el-input-number
                  v-if="!isReadonly"
                  :model-value="row.currentMaterial"
                  :controls="false"
                  size="small"
                  style="width: 100%"
                  @change="(v: number) => updateCell(row.rowId, 'currentMaterial', v ?? 0)"
                />
                <span v-else>{{ fmt(row.currentMaterial) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="直接人工" width="100" align="right">
              <template #default="{ row }">
                <el-input-number
                  v-if="!isReadonly"
                  :model-value="row.currentLabor"
                  :controls="false"
                  size="small"
                  style="width: 100%"
                  @change="(v: number) => updateCell(row.rowId, 'currentLabor', v ?? 0)"
                />
                <span v-else>{{ fmt(row.currentLabor) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="制造费用" width="100" align="right">
              <template #default="{ row }">
                <el-input-number
                  v-if="!isReadonly"
                  :model-value="row.currentOverhead"
                  :controls="false"
                  size="small"
                  style="width: 100%"
                  @change="(v: number) => updateCell(row.rowId, 'currentOverhead', v ?? 0)"
                />
                <span v-else>{{ fmt(row.currentOverhead) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="合计" width="100" align="right" class-name="auto-calc-col">
              <template #default="{ row }">{{ fmt(row.currentTotal) }}</template>
            </el-table-column>
          </el-table-column>

          <el-table-column :label="yearLabels[1] + '单位成本'" align="center">
            <el-table-column label="直接材料" width="100" align="right">
              <template #default="{ row }">
                <el-input-number
                  v-if="!isReadonly"
                  :model-value="row.priorMaterial"
                  :controls="false"
                  size="small"
                  style="width: 100%"
                  @change="(v: number) => updateCell(row.rowId, 'priorMaterial', v ?? 0)"
                />
                <span v-else>{{ fmt(row.priorMaterial) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="直接人工" width="100" align="right">
              <template #default="{ row }">
                <el-input-number
                  v-if="!isReadonly"
                  :model-value="row.priorLabor"
                  :controls="false"
                  size="small"
                  style="width: 100%"
                  @change="(v: number) => updateCell(row.rowId, 'priorLabor', v ?? 0)"
                />
                <span v-else>{{ fmt(row.priorLabor) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="制造费用" width="100" align="right">
              <template #default="{ row }">
                <el-input-number
                  v-if="!isReadonly"
                  :model-value="row.priorOverhead"
                  :controls="false"
                  size="small"
                  style="width: 100%"
                  @change="(v: number) => updateCell(row.rowId, 'priorOverhead', v ?? 0)"
                />
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
                <span :class="{ abnormal: row.matHot }">{{ fmtPct(row.matRate) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="直接人工" width="90" align="right" class-name="auto-calc-col">
              <template #default="{ row }">
                <span :class="{ abnormal: row.laborHot }">{{ fmtPct(row.laborRate) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="制造费用" width="90" align="right" class-name="auto-calc-col">
              <template #default="{ row }">
                <span :class="{ abnormal: row.ohHot }">{{ fmtPct(row.ohRate) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="合计" width="90" align="right" class-name="auto-calc-col">
              <template #default="{ row }">
                <span :class="{ abnormal: row.isAnomaly }">{{ fmtPct(row.totalRate) }}</span>
              </template>
            </el-table-column>
          </el-table-column>

          <el-table-column label="是否异常" width="110" align="center">
            <template #default="{ row }">
              <el-select
                v-if="!isReadonly"
                :model-value="row.abnormal"
                size="small"
                @change="(v: string) => updateCell(row.rowId, 'abnormal', v)"
              >
                <el-option v-for="o in YES_NO" :key="o.value" :label="o.label" :value="o.value" />
              </el-select>
              <template v-else>
                <el-tag v-if="row.isAnomaly" size="small" type="danger">是</el-tag>
                <span v-else>{{ row.abnormal || '—' }}</span>
              </template>
              <div v-if="!isReadonly && row.abnormal === '' && row.autoAnomaly" class="auto-hint">自动·超阈值</div>
            </template>
          </el-table-column>
          <el-table-column label="进一步审验底稿索引" width="150">
            <template #default="{ row }">
              <el-input
                v-if="!isReadonly"
                :model-value="row.indexRef"
                size="small"
                placeholder="如 F2-64"
                @change="(v: string) => updateCell(row.rowId, 'indexRef', v)"
              />
              <GtIndexChip
                v-else-if="row.indexRef"
                :value="row.indexRef.startsWith('wp:') ? row.indexRef : `wp:${row.indexRef}`"
                :context-project-id="projectId"
                :validate="false"
              />
              <span v-else>—</span>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="55" fixed="right" align="center">
            <template #default="{ row }">
              <el-button link type="danger" size="small" :disabled="isReadonly" @click="removeRow(row.rowId)">删</el-button>
            </template>
          </el-table-column>
        </el-table>
      </div>

      <div class="total-bar">
        合计（各产品单位成本加总，仅汇总展示）：
        {{ yearLabels[0] }} {{ fmt(totals.currentTotal) }}
        | {{ yearLabels[1] }} {{ fmt(totals.priorTotal) }}
      </div>

      <div class="section-notes">
        <div class="note-head">
          <span>审计说明</span>
          <el-button
            size="small"
            :disabled="isReadonly || !aiAvailable"
            :loading="aiLoading"
            @click="genSection('f2-20-note', notes.note, 'AI · F2-20 审计说明', (t) => updateNotes('note', t))"
          >AI辅助</el-button>
        </div>
        <el-input
          type="textarea"
          :model-value="notes.note"
          :disabled="isReadonly"
          :autosize="{ minRows: 3 }"
          placeholder="概述本表比较程序、关注的产品及交叉索引情况…"
          @change="(v: string) => updateNotes('note', v)"
        />
        <div class="note-head" style="margin-top: 8px">
          <span>异常原因</span>
          <el-button
            size="small"
            :disabled="isReadonly || !aiAvailable"
            :loading="aiLoading"
            @click="genSection('f2-20-abnormal', notes.abnormalReason, 'AI · F2-20 异常原因', (t) => updateNotes('abnormalReason', t))"
          >AI辅助</el-button>
        </div>
        <el-input
          type="textarea"
          :model-value="notes.abnormalReason"
          :disabled="isReadonly"
          :autosize="{ minRows: 2 }"
          placeholder="例：1. XX产品单位成本异常波动原因见 F2-64；2. 原材料采购价格进一步分析见 F2-61…"
          @change="(v: string) => updateNotes('abnormalReason', v)"
        />
      </div>
    </el-card>

    <el-card class="opinion-card audit-note-card" shadow="never">
      <template #header>
        <div class="opinion-header">
          <span class="opinion-title">二、审计结论</span>
          <div class="opinion-actions">
            <el-button
              size="small"
              type="primary"
              plain
              :disabled="isReadonly || !aiAvailable"
              :loading="aiLoading"
              @click="genSection('f2-20-conclusion', conclusion, 'AI 生成 · 成本比较结论', saveConclusion)"
            >AI辅助</el-button>
            <F2ReviewChip section-id="F2-20-conclusion" />
          </div>
        </div>
      </template>
      <el-input
        type="textarea"
        :model-value="conclusion"
        :disabled="isReadonly"
        :autosize="{ minRows: 3, maxRows: 10 }"
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
.thr-label { font-size: 12px; color: #606266; }
.thr-unit { font-size: 12px; color: #909399; margin-right: 4px; }
.chip-wrap { display: inline-flex; align-items: center; }
.year-labels { display: flex; gap: 8px; align-items: center; margin-bottom: 10px; flex-wrap: wrap; }
.block-card { margin-bottom: 12px; }
.block-title { font-weight: 600; }
.card-header-flex { display: flex; justify-content: space-between; align-items: center; gap: 8px; }
.table-scroll { overflow-x: auto; }
.total-bar { margin-top: 8px; text-align: right; font-weight: 600; color: #606266; }
.section-notes { margin-top: 12px; }
.note-head {
  display: flex; justify-content: space-between; align-items: center;
  margin-bottom: 6px; font-weight: 500;
}
.abnormal { color: #f56c6c; font-weight: 600; }
.auto-hint { font-size: 11px; color: #e6a23c; line-height: 1.2; margin-top: 2px; }
:deep(.auto-calc-col) { background-color: #f5f7fa !important; }
:deep(.anomaly-row) { background: #fef0f0; }
.opinion-card { margin-top: 16px; border-radius: 8px; }
.opinion-card :deep(.el-card__header) { padding: 12px 16px; background: #fafafa; border-bottom: 1px solid #ebeef5; }
.opinion-header { display: flex; align-items: center; justify-content: space-between; }
.opinion-title { font-size: 14px; font-weight: 600; color: #303133; }
.opinion-actions { display: flex; gap: 6px; align-items: center; }
.audit-note-card { margin-top: 16px; }
</style>
