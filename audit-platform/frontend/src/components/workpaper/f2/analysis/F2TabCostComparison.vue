<script setup lang="ts">
/** F2TabCostComparison — F2-20 成本比较 | Task 17.4 */
import { ref, inject, toRef, onMounted, type Ref } from 'vue'
import { useF2CostComparison } from '../../composables/useF2Analysis'
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

// ─── 审计说明 / 审计结论 ───────────────────────────────────────────────────────
const NOTE_KEY = 'F2-cost-comparison-audit-note'
const CONCLUSION_KEY = 'F2-cost-comparison-audit-conclusion'
const auditNote = ref('')
const auditConclusion = ref('')

function persistAudit(key: string, val: string): void {
  const item = { item_id: key, conclusion: null, remark: val }
  props.allResponses.set(key, item)
  window.dispatchEvent(new CustomEvent('f2:save-items', { detail: { items: [item] } }))
}
function saveAuditNote(val: string): void {
  if (props.isReadonly) return
  auditNote.value = val
  persistAudit(NOTE_KEY, val)
}
function saveAuditConclusion(val: string): void {
  if (props.isReadonly) return
  auditConclusion.value = val
  persistAudit(CONCLUSION_KEY, val)
}
onMounted(() => {
  const n = props.allResponses.get(NOTE_KEY)
  if (n?.remark) auditNote.value = n.remark
  const c = props.allResponses.get(CONCLUSION_KEY)
  if (c?.remark) auditConclusion.value = c.remark
})

function fmtRate(r: number | '' | 'N/A'): string {
  if (r === '' || r === 'N/A') return String(r)
  return `${(r * 100).toFixed(1)}%`
}

const { activeSegment, enrichedRows, anomalyCount, conclusion, addRow, removeRow, updateCell } = useF2CostComparison({
  allResponses: toRef(props, 'allResponses') as Ref<Map<string, ChecklistResponse>>,
  isReadonly: toRef(props, 'isReadonly') as Ref<boolean>,
})

const { aiAvailable, loading: aiLoading, generateAndConfirm } = useF2AiGenerate(toRef(props, 'wpId') as Ref<string>)

async function generateCostConclusion() {
  const text = await generateAndConfirm(
    'cost-comparison-conclusion',
    conclusion.value,
    { productCount: enrichedRows.value.length, anomalyCount: anomalyCount.value },
    'AI 生成 · 成本比较结论',
  )
  if (text) conclusion.value = text
}

const segmentOptions = [
  { label: '本期成本', value: 'current' },
  { label: '变动分析', value: 'variance' },
]
</script>

<template>
  <div class="f2-cost-comparison">
    <!-- 编制提示 -->
    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 按产品比较本期/上期单位成本构成（材料 + 人工 + 制造费用），合计为自动计算列。</p>
        <p>2. 单位成本变动率 ＞ 20% 自动红色标记，须填写异常说明并分析成本波动原因。</p>
        <p>3. 依《企业会计准则第 1 号——存货》，存货成本应包含采购成本、加工成本及其他成本，结转应准确。</p>
        <p>4. 关注成本异常与产销量、材料价格、工艺变更的量本关系，防止成本结转错报。</p>
      </div>
    </details>

    <!-- 审计目标 -->
    <el-alert
      type="info"
      :closable="false"
      show-icon
      class="objective-alert"
      title="审计目标：分析各产品单位成本构成的合理性，识别成本异常波动，验证存货成本结转的准确性。"
    />

    <!-- 工具栏 -->
    <div class="tab-toolbar">
      <div class="toolbar-left">
        <el-button size="small" type="primary" :disabled="isReadonly" @click="addRow">+ 新增产品</el-button>
        <el-tag v-if="anomalyCount > 0" type="danger" size="small">{{ anomalyCount }} 项成本异常</el-tag>
      </div>
      <div class="toolbar-right">
        <CycleImportExportDropdown
          :wp-id="wpId"
          api-prefix="f2"
          sheet="F2-20"
          :disabled="isReadonly"
          @imported="onImported"
        />
        <span class="chip-wrap"><GtIndexChip value="wp:F2-1" :context-project-id="projectId" /></span>
        <el-tag size="small" type="info">共 {{ enrichedRows.length }} 行</el-tag>
      </div>
    </div>
    <el-segmented v-model="activeSegment" :options="segmentOptions" size="small" class="segment-bar" />

    <el-table :data="enrichedRows" border size="small" max-height="480">
      <el-table-column label="产品名称" width="140" fixed>
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.productName" size="small" @change="(v: string) => updateCell(row.rowId, 'productName', v)" />
          <span v-else>{{ row.productName }}</span>
        </template>
      </el-table-column>

      <template v-if="activeSegment === 'current'">
        <el-table-column label="产量" width="90">
          <template #default="{ row }">
            <el-input-number :model-value="row.currentQty" size="small" :controls="false" :disabled="isReadonly"
              @change="(v: number) => updateCell(row.rowId, 'currentQty', v ?? 0)" />
          </template>
        </el-table-column>
        <el-table-column label="材料" width="100">
          <template #default="{ row }">
            <el-input-number :model-value="row.currentMaterial" size="small" :controls="false" :disabled="isReadonly"
              @change="(v: number) => updateCell(row.rowId, 'currentMaterial', v ?? 0)" />
          </template>
        </el-table-column>
        <el-table-column label="人工" width="100">
          <template #default="{ row }">
            <el-input-number :model-value="row.currentLabor" size="small" :controls="false" :disabled="isReadonly"
              @change="(v: number) => updateCell(row.rowId, 'currentLabor', v ?? 0)" />
          </template>
        </el-table-column>
        <el-table-column label="制造费用" width="100">
          <template #default="{ row }">
            <el-input-number :model-value="row.currentOverhead" size="small" :controls="false" :disabled="isReadonly"
              @change="(v: number) => updateCell(row.rowId, 'currentOverhead', v ?? 0)" />
          </template>
        </el-table-column>
        <el-table-column label="合计" width="100" align="right" class-name="auto-calc-col">
          <template #default="{ row }">{{ row.currentTotal.toLocaleString() }}</template>
        </el-table-column>
      </template>

      <template v-else>
        <el-table-column label="上期合计" width="110" align="right" class-name="auto-calc-col">
          <template #default="{ row }">{{ row.priorTotal.toLocaleString() }}</template>
        </el-table-column>
        <el-table-column label="变动额" width="110" align="right" class-name="auto-calc-col">
          <template #default="{ row }">{{ row.variance.toLocaleString() }}</template>
        </el-table-column>
        <el-table-column label="变动率" width="90">
          <template #default="{ row }">
            <span :class="{ anomaly: row.isAnomaly }">{{ fmtRate(row.varianceRate) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="异常说明" min-width="140">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.anomalyNote" size="small"
              :class="{ anomaly: row.isAnomaly }"
              @change="(v: string) => updateCell(row.rowId, 'anomalyNote', v)" />
            <span v-else>{{ row.anomalyNote }}</span>
          </template>
        </el-table-column>
      </template>

      <el-table-column label="操作" width="55" fixed="right">
        <template #default="{ row }">
          <el-button link type="danger" size="small" :disabled="isReadonly" @click="removeRow(row.rowId)">删</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 审计意见区（卡片式） -->
    <el-card class="opinion-card" shadow="never">
      <template #header>
        <div class="opinion-header">
          <span class="opinion-title">分析结论</span>
          <div class="opinion-actions">
            <el-button size="small" type="primary" plain :disabled="isReadonly || !aiAvailable" :loading="aiLoading" @click="generateCostConclusion">🤖 AI辅助</el-button>
            <F2ReviewChip section-id="F2-20-conclusion" />
          </div>
        </div>
      </template>
      <el-input v-model="conclusion" type="textarea" :autosize="{ minRows: 3, maxRows: 8 }" :disabled="isReadonly" placeholder="请输入成本比较分析结论..." />
    </el-card>

    <!-- 审计说明 -->
    <el-card shadow="never" class="audit-note-card">
      <template #header><div class="card-header"><span>审计说明</span></div></template>
      <el-input
        type="textarea"
        :model-value="auditNote"
        :disabled="isReadonly"
        :autosize="{ minRows: 5 }"
        placeholder="填写审计说明：概述所执行的成本比较程序、测试情况与结果，以及成本异常波动的核查与拟调整/未调整事项及其影响。"
        @change="saveAuditNote"
      />
    </el-card>

    <!-- 审计结论 -->
    <el-card shadow="never" class="audit-note-card">
      <template #header><div class="card-header"><span>审计结论</span></div></template>
      <el-input
        type="textarea"
        :model-value="auditConclusion"
        :disabled="isReadonly"
        :autosize="{ minRows: 3 }"
        placeholder="填写审计结论：A、未见异常。B、除上述重大不符事项应作为调整事项予以调整外，其余未见异常。C、由于存在以下重大未调整事项（或审计范围受到限制），不可确认。"
        @change="saveAuditConclusion"
      />
    </el-card>
  </div>
</template>

<style scoped>
.f2-cost-comparison { padding: 12px; font-size: var(--wp-font-size, 13px); }
.f2-cost-comparison :deep(.el-table) { --el-table-font-size: var(--wp-font-size, 13px); font-size: var(--wp-font-size, 13px); }
.f2-cost-comparison :deep(.el-table .cell) { font-size: var(--wp-font-size, 13px) !important; }
.guidance-details {
  margin-bottom: 12px;
  border-left: 3px solid #409eff;
  background: #ecf5ff;
  border-radius: 4px;
  padding: 8px 12px;
}
.guidance-details summary { cursor: pointer; font-weight: 500; color: #409eff; }
.guidance-content { margin-top: 8px; font-size: var(--wp-font-size, 13px); color: #606266; line-height: 1.6; }
.guidance-content p { margin: 2px 0; }
.objective-alert { margin-bottom: 12px; }
.tab-toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.toolbar-left { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.toolbar-right { display: flex; gap: 6px; align-items: center; }
.chip-wrap { display: inline-flex; align-items: center; }
.segment-bar { margin-bottom: 12px; }
.anomaly { color: #f56c6c; font-weight: 600; }
:deep(.auto-calc-col) { background-color: #f5f7fa !important; }
.opinion-card { margin-top: 16px; border-radius: 8px; }
.opinion-card :deep(.el-card__header) { padding: 12px 16px; background: #fafafa; border-bottom: 1px solid #ebeef5; }
.opinion-header { display: flex; align-items: center; justify-content: space-between; }
.opinion-title { font-size: 14px; font-weight: 600; color: #303133; }
.opinion-actions { display: flex; gap: 6px; align-items: center; }
.audit-note-card { margin-top: 16px; }
.audit-note-card .card-header { display: flex; justify-content: space-between; align-items: center; font-weight: 500; }
</style>
