<template>
  <div class="f2-val-sheet f2-loss-contract f2-soft-matrix">
    <header class="sheet-header">
      <div>
        <h3>亏损合同预计损失测算表</h3>
        <span class="code">F2-58</span>
      </div>
      <div class="stat-row">
        <span class="stat">预计损失合计 {{ fmt(loss.columnTotals.value.contractEstimatedLoss) }}</span>
        <span class="stat sub">本期应确认 {{ fmt(loss.columnTotals.value.currentPeriodLoss) }}</span>
        <span class="stat sub">差异 {{ fmtSigned(loss.columnTotals.value.difference) }}</span>
        <el-tag v-if="loss.lossCount.value" type="danger" size="small">
          亏损合同 {{ loss.lossCount.value }} 项
        </el-tag>
        <el-tag v-if="loss.adjustCount.value" type="warning" size="small">
          差异 {{ loss.adjustCount.value }} 项
        </el-tag>
      </div>
    </header>

    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p v-for="(tip, i) in tips" :key="i">{{ i + 1 }}. {{ tip }}</p>
      </div>
    </details>

    <el-alert type="info" :closable="false" :title="objectiveText" class="objective-alert" />

    <div class="tab-toolbar">
      <div class="toolbar-left">
        <el-button size="small" type="primary" :disabled="isReadonly" @click="loss.addProject()">+ 项目</el-button>
      </div>
      <div class="toolbar-right">
        <F2SheetToolbar
          :wp-id="wpId"
          api-prefix="f2-spe"
          sheet="F2-58"
          :disabled="isReadonly"
          review-section="F2-58-loss"
        />
        <GtIndexChip value="wp:F2-58" :context-project-id="projectId" />
        <el-tag size="small" type="info">{{ filledCount }} 个项目</el-tag>
      </div>
    </div>

    <div v-if="projectId && wpId" class="evidence-panel">
      <h4>亏损合同测算附件</h4>
      <p>上传合同、预计收入成本测算、履行成本依据等支持性资料。</p>
      <ItemAttachment
        :project-id="projectId"
        :wp-id="wpId"
        sheet-key="F2-58"
        :item-index="1"
        accept=".pdf,.png,.jpg,.jpeg,.doc,.docx,.xls,.xlsx"
      />
    </div>

    <div class="table-scroll">
      <table class="matrix-table">
        <thead>
          <tr>
            <th rowspan="2" class="sticky col-code">项目编码</th>
            <th rowspan="2" class="sticky col-name">项目名称</th>
            <th rowspan="2">①<br>完工进度</th>
            <th rowspan="2">②<br>预计总收入</th>
            <th rowspan="2">③<br>预计总成本</th>
            <th rowspan="2" class="calc-col">④=③−②<br>合同预计损失</th>
            <th rowspan="2" class="calc-col">⑤<br>已在损益<br>反映亏损</th>
            <th rowspan="2" class="calc-col">⑥=④−⑤<br>本期应确认</th>
            <th rowspan="2">⑦<br>账面已确认</th>
            <th rowspan="2" class="calc-col">⑧=⑥−⑦<br>差异</th>
            <th rowspan="2" class="col-remark">备注</th>
            <th rowspan="2" class="col-act" />
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="row in loss.enrichedProjects.value"
            :key="row.id"
            :class="{ 'row-warn': row.isLoss === '是', 'row-error': row.hasDifference }"
          >
            <td class="sticky col-code">
              <el-input v-if="!isReadonly" :model-value="row.projectCode" size="small"
                @update:model-value="(v: string) => loss.updateProject(row.id, { projectCode: v })" />
              <span v-else>{{ row.projectCode || '—' }}</span>
            </td>
            <td class="sticky col-name">
              <el-input v-if="!isReadonly" :model-value="row.projectName" size="small"
                @update:model-value="(v: string) => loss.updateProject(row.id, { projectName: v })" />
              <span v-else>{{ row.projectName || '—' }}</span>
            </td>
            <td>
              <el-input-number v-if="!isReadonly" :model-value="row.effectiveCompletionRate * 100"
                size="small" :controls="false" :precision="1" class="compact-num"
                @change="(v: number | undefined) => loss.updateProject(row.id, {
                  completionRate: (v ?? 0) / 100,
                  recognizedRevenue: 0,
                })" />
              <span v-else class="auto">{{ fmtPct(row.effectiveCompletionRate) }}</span>
            </td>
            <td>
              <el-input-number v-if="!isReadonly" :model-value="row.estimatedTotalRevenue" size="small"
                :controls="false" class="compact-num wide"
                @change="(v: number | undefined) => loss.updateProject(row.id, { estimatedTotalRevenue: v ?? 0 })" />
              <span v-else class="auto">{{ fmt(row.estimatedTotalRevenue) }}</span>
            </td>
            <td>
              <el-input-number v-if="!isReadonly" :model-value="row.estimatedTotalCost" size="small"
                :controls="false" class="compact-num wide"
                @change="(v: number | undefined) => loss.updateProject(row.id, { estimatedTotalCost: v ?? 0 })" />
              <span v-else class="auto">{{ fmt(row.estimatedTotalCost) }}</span>
            </td>
            <td class="auto calc calc-col" :class="{ 'loss-yes': row.isLoss === '是' }">
              {{ fmt(row.contractEstimatedLoss) }}
            </td>
            <td>
              <el-input-number v-if="!isReadonly" :model-value="row.priorRecognizedLoss" size="small"
                :controls="false" class="compact-num wide"
                :placeholder="fmt(row.contractEstimatedLoss * row.effectiveCompletionRate)"
                @change="(v: number | undefined) => loss.updateProject(row.id, { priorRecognizedLoss: v ?? 0 })" />
              <span v-else class="auto calc">{{ fmt(row.recognizedLossInPl) }}</span>
            </td>
            <td class="auto calc calc-col">{{ fmt(row.currentPeriodLoss) }}</td>
            <td>
              <el-input-number v-if="!isReadonly" :model-value="row.bookRecognizedLoss" size="small"
                :controls="false" class="compact-num wide"
                @change="(v: number | undefined) => loss.updateProject(row.id, { bookRecognizedLoss: v ?? 0 })" />
              <span v-else class="auto">{{ fmt(row.bookRecognizedLoss) }}</span>
            </td>
            <td class="auto calc calc-col" :class="{ 'diff-warn': row.hasDifference }">
              {{ fmtSigned(row.difference) }}
            </td>
            <td class="col-remark">
              <el-input v-if="!isReadonly" :model-value="row.remark" size="small"
                @update:model-value="(v: string) => loss.updateProject(row.id, { remark: v })" />
              <span v-else class="remark-text">{{ row.remark || '—' }}</span>
            </td>
            <td class="col-act">
              <el-button v-if="!isReadonly" link type="danger" size="small" @click="loss.removeProject(row.id)">删</el-button>
            </td>
          </tr>

          <tr class="row-total">
            <td colspan="2" class="sticky col-name">合计</td>
            <td />
            <td class="auto">{{ fmt(loss.columnTotals.value.estimatedTotalRevenue) }}</td>
            <td class="auto">{{ fmt(loss.columnTotals.value.estimatedTotalCost) }}</td>
            <td class="auto calc">{{ fmt(loss.columnTotals.value.contractEstimatedLoss) }}</td>
            <td class="auto calc">{{ fmt(loss.columnTotals.value.recognizedLossInPl) }}</td>
            <td class="auto calc">{{ fmt(loss.columnTotals.value.currentPeriodLoss) }}</td>
            <td class="auto">{{ fmt(loss.columnTotals.value.bookRecognizedLoss) }}</td>
            <td class="auto calc" :class="{ 'diff-warn': Math.abs(loss.columnTotals.value.difference) > 0.01 }">
              {{ fmtSigned(loss.columnTotals.value.difference) }}
            </td>
            <td colspan="2" />
          </tr>
        </tbody>
      </table>
    </div>

    <el-card class="opinion-card" shadow="never">
      <template #header>
        <div class="opinion-header">
          <span class="opinion-title">1、审计说明</span>
          <el-button size="small" type="primary" plain
            :disabled="isReadonly || !aiAvailable" :loading="aiLoading"
            @click="runAi('loss-contract-note')">AI 填写审计说明</el-button>
        </div>
      </template>
      <el-input v-model="loss.auditNote.value" type="textarea" :autosize="{ minRows: 3, maxRows: 8 }"
        placeholder="说明亏损合同识别、预计损失测算及差异处理…" :disabled="isReadonly" />
    </el-card>

    <el-card class="opinion-card" shadow="never">
      <template #header>
        <div class="opinion-header">
          <span class="opinion-title">2、审计结论</span>
          <el-button size="small" type="primary" plain
            :disabled="isReadonly || !aiAvailable" :loading="aiLoading"
            @click="runAi('loss-contract-conclusion')">AI 生成结论</el-button>
        </div>
      </template>
      <el-input :model-value="auditConclusion" type="textarea" :autosize="{ minRows: 3, maxRows: 8 }"
        placeholder="A、未见异常。B、除上述应调整事项外，其余未见异常。C、不可确认。"
        :disabled="isReadonly" @update:model-value="saveAuditConclusion" />
    </el-card>

    <div class="tips-box">
      <div class="tips-title">提示</div>
      <ol>
        <li v-for="(tip, i) in tips" :key="i">{{ tip }}</li>
      </ol>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, toRef, type Ref } from 'vue'
import { useF2LossContract } from '../../composables/useF2LossContract'
import {
  F2_58_OBJECTIVE,
  F2_58_TIPS,
  isBlankLossContractProject,
} from '../../composables/useF2LossContractFormulas'
import {
  useF2SpecialAiGenerate,
  type F2SpeAiSection,
} from '../../composables/useF2SpecialAiGenerate'
import type { ChecklistResponse } from '../../composables/useF2SpecialFormData'
import F2SheetToolbar from '../../f2/shared/F2SheetToolbar.vue'
import GtIndexChip from '../../GtIndexChip.vue'
import ItemAttachment from '../../ItemAttachment.vue'

const props = defineProps<{
  wpId?: string
  projectId?: string
  allResponses: Map<string, ChecklistResponse>
  isReadonly: boolean
}>()

const loss = useF2LossContract({
  allResponses: toRef(props, 'allResponses'),
  isReadonly: toRef(props, 'isReadonly'),
})

const objectiveText = F2_58_OBJECTIVE
const tips = F2_58_TIPS
const wpIdRef = toRef(() => props.wpId || '') as Ref<string>
const {
  aiAvailable,
  loading: aiLoading,
  generateAndConfirm,
} = useF2SpecialAiGenerate(wpIdRef)
const filledCount = computed(() =>
  loss.sheet.value.projects.filter((row) => !isBlankLossContractProject(row)).length,
)

const CONCLUSION_KEY = 'F2-58-conclusion'
const auditConclusion = ref('')
function saveAuditConclusion(val: string): void {
  if (props.isReadonly) return
  auditConclusion.value = val
  const item = { item_id: CONCLUSION_KEY, conclusion: null, remark: val }
  props.allResponses.set(CONCLUSION_KEY, item)
  window.dispatchEvent(new CustomEvent('f2-spe:save-items', { detail: { items: [item] } }))
}
onMounted(() => {
  const c = props.allResponses.get(CONCLUSION_KEY)
  if (c?.remark) auditConclusion.value = c.remark
})

function aiContext(): Record<string, unknown> {
  return {
    sheet: 'F2-58',
    projectCount: filledCount.value,
    estimatedTotalRevenue: loss.columnTotals.value.estimatedTotalRevenue,
    estimatedTotalCost: loss.columnTotals.value.estimatedTotalCost,
    contractEstimatedLoss: loss.columnTotals.value.contractEstimatedLoss,
    recognizedLossInPl: loss.columnTotals.value.recognizedLossInPl,
    currentPeriodLoss: loss.columnTotals.value.currentPeriodLoss,
    bookRecognizedLoss: loss.columnTotals.value.bookRecognizedLoss,
    differenceTotal: loss.columnTotals.value.difference,
    lossCount: loss.lossCount.value,
    differenceCount: loss.adjustCount.value,
    projects: loss.enrichedProjects.value
      .filter((row) => !isBlankLossContractProject(row))
      .slice(0, 30)
      .map((row) => ({
        projectCode: row.projectCode,
        projectName: row.projectName,
        completionRate: row.effectiveCompletionRate,
        estimatedTotalRevenue: row.estimatedTotalRevenue,
        estimatedTotalCost: row.estimatedTotalCost,
        contractEstimatedLoss: row.contractEstimatedLoss,
        recognizedLossInPl: row.recognizedLossInPl,
        currentPeriodLoss: row.currentPeriodLoss,
        bookRecognizedLoss: row.bookRecognizedLoss,
        difference: row.difference,
        remark: row.remark,
      })),
  }
}

async function runAi(section: F2SpeAiSection): Promise<void> {
  const isNote = section === 'loss-contract-note'
  const existing = isNote ? loss.auditNote.value : auditConclusion.value
  const title = isNote
    ? 'AI 生成 · 亏损合同审计说明'
    : 'AI 生成 · 亏损合同审计结论'
  const text = await generateAndConfirm(section, existing || '', aiContext(), title)
  if (!text) return
  if (isNote) loss.auditNote.value = text
  else saveAuditConclusion(text)
}

function fmt(v: number): string {
  if (!Number.isFinite(v) || v === 0) return '—'
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function fmtSigned(v: number): string {
  if (!Number.isFinite(v) || v === 0) return '—'
  const s = v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
  return v > 0 ? s : `(${s.replace('-', '')})`
}

function fmtPct(v: number): string {
  if (!Number.isFinite(v) || v === 0) return '—'
  return `${(v * 100).toFixed(1)}%`
}
</script>

<style scoped src="../../f2/valuation/f2ValSheetStyles.css"></style>
<style scoped src="./f2SoftMatrixStyles.css"></style>
<style scoped>
.f2-loss-contract { --gt-purple: #4b2d77; --gt-purple-soft: #f3eef8; }
.opinion-header { display: flex; align-items: center; justify-content: space-between; }

.table-scroll { overflow-x: auto; margin-bottom: 12px; }
.matrix-table {
  width: 100%;
  border-collapse: separate;
  border-spacing: 0;
  font-size: 11px;
  min-width: 1180px;
}
.matrix-table th,
.matrix-table td {
  border: 1px solid #d4c8e0;
  padding: 4px 4px;
  text-align: center;
  vertical-align: middle;
  background: #fff;
}
.matrix-table thead th {
  background: var(--gt-purple);
  color: #fff;
  font-weight: 600;
  position: sticky;
  top: 0;
  z-index: 2;
  white-space: nowrap;
  font-size: 10px;
  line-height: 1.3;
}
.matrix-table th.calc-col { background: #6b4d8f; }

.sticky { position: sticky; z-index: 3; background: #faf8fc !important; }
.matrix-table thead th.sticky { background: var(--gt-purple) !important; color: #fff; z-index: 4; }
.col-code { left: 0; min-width: 72px; }
.col-name {
  left: 72px;
  min-width: 100px;
  text-align: left !important;
  padding-left: 4px !important;
  box-shadow: 2px 0 4px rgba(75, 45, 119, 0.08);
}
.col-remark { min-width: 80px; }
.col-act { width: 36px; position: sticky; right: 0; z-index: 3; background: #fff !important; }

.row-total td { background: #f0ebf5 !important; font-weight: 600; }
.row-warn td { background: #fdf6ec !important; }
.row-error td { background: #fef0f0 !important; }
.auto { text-align: right; padding-right: 2px; white-space: nowrap; color: #606266; }
span.auto { display: block; }
.calc { color: #4b2d77; font-weight: 500; background: #faf8fc !important; }
.loss-yes { color: #c45656; font-weight: 600; }
.diff-warn { color: #c45656; font-weight: 600; }
.remark-text { font-size: 10px; color: #909399; }

.tips-box {
  margin-top: 16px;
  padding: 12px 16px;
  background: #ecf5ff;
  border-left: 3px solid #409eff;
  border-radius: 4px;
  font-size: 13px;
  line-height: 1.7;
}
.tips-title { font-weight: 600; color: #409eff; margin-bottom: 6px; }
.tips-box ol { margin: 0; padding-left: 1.4em; }

:deep(.compact-num) { width: 72px; }
:deep(.compact-num.wide) { width: 96px; }
:deep(.compact-num .el-input__inner) { text-align: right; padding: 0 4px; font-size: 11px; }
</style>
