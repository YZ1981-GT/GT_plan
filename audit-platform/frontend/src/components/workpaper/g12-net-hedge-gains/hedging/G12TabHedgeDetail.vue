<template>
  <div class="g12-hedge" data-testid="g12-hedge-detail">
    <div class="toolbar">
      <div class="title-block">
        <h3>G12-2 净敞口套期收益明细</h3>
        <p class="sheet-sub">项目 × 净头寸 × 套期工具 → FV 拆分校验 → 净敞口套期损益</p>
      </div>
      <div class="head-actions">
        <el-button size="small" type="primary" :disabled="isReadonly" @click="hd.addRow('fv_allocation')">+ FV 分配行</el-button>
        <el-button size="small" :disabled="isReadonly" @click="hd.addRow('amortization')">+ 摊销行</el-button>
        <el-button size="small" :disabled="isReadonly" @click="importFromG12_5">从 G12-5 带入</el-button>
        <el-button size="small" :disabled="isReadonly" @click="syncNetPositionFromG12_5">同步 G12-5 净头寸</el-button>
        <el-button size="small" :disabled="isReadonly" @click="importAmortization">从 G12-4/G12-6 带入摊销</el-button>
        <CycleImportExportDropdown :wp-id="wpId" api-prefix="g12" sheet="G12-2" :disabled="isReadonly" @imported="emit('imported')" />
        <GtReviewTrigger section-id="G12-2-hedge-detail" />
      </div>
    </div>

    <GCycleGuideStrip
      label="主闭环"
      :steps="[...G12_CORE_WORKFLOW_STEPS]"
      :active-index="wf.activeIndex.value"
      :completed-indices="wf.completedIndices.value"
    />
    <G12CoreWorkflowChecklist :readiness="wf.readiness.value" compact />

    <details class="guidance-details" open>
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p><strong>本页在主闭环中的位置：第 1 步</strong> — {{ G12_CORE_WORKFLOW_HINT }}</p>
        <p v-for="(line, i) in guidanceLines" :key="i">{{ line }}</p>
      </div>
    </details>

    <el-alert
      type="info"
      :closable="false"
      show-icon
      class="audit-objective"
      title="审计目标"
      :description="auditObjective"
    />

    <el-alert v-if="crossMismatches.length" type="warning" :closable="false" class="cross-alert" data-testid="g12-hedge-fv-cross-bar">
      <template #title>G12-4 交叉验证差异（{{ crossMismatches.length }} 处）</template>
      <div v-for="m in crossMismatches.slice(0, 3)" :key="`${m.hedgeRelationId}-${m.field}`" class="cross-line">
        {{ m.hedgeRelationId }} · {{ m.field === 'instrumentFVChange' ? '工具FV变动' : '项目FV变动' }}：
        G12-2={{ m.hedgeValue.toFixed(2) }} vs G12-4={{ m.fvTestValue.toFixed(2) }}（差 {{ m.variance.toFixed(2) }}）
      </div>
      <span v-if="crossMismatches.length > 3">…另有 {{ crossMismatches.length - 3 }} 处</span>
      <GtIndexChip v-if="jumpToSection" label="G12-4" :prevent-navigate="true" :validate="false" class="warn-chip"
        @click="jumpToSection(resolveG12SheetLabel('G12-4'))" />
    </el-alert>
    <el-alert v-else-if="hasFvTestData" type="success" :closable="false" class="cross-alert cross-ok" data-testid="g12-hedge-fv-cross-ok">
      G12-2 与 G12-4 公允价值测试一致
      <GtIndexChip v-if="jumpToSection" label="G12-4" :prevent-navigate="true" :validate="false" class="ok-chip"
        @click="jumpToSection(resolveG12SheetLabel('G12-4'))" />
    </el-alert>

    <el-alert v-if="hd.totals.value.fvCheckFailCount" type="error" :closable="false" class="cross-alert">
      {{ hd.totals.value.fvCheckFailCount }} 行 FV 拆分校验未通过（销售 + 采购 ≠ 累计 FV 变动）
    </el-alert>

    <div class="tab-toolbar">
      <div class="toolbar-left">
        <span class="chip-wrap"><GtIndexChip value="wp:G12-2" /></span>
        <GtIndexChip v-if="jumpToSection" label="G12-5" :prevent-navigate="true" :validate="false"
          @click="jumpToSection(resolveG12SheetLabel('G12-5'))" />
      </div>
      <el-tag size="small" type="info">共 {{ hd.rows.value.length }} 行</el-tag>
    </div>

    <el-table :data="tableRows" border size="small" style="font-size:13px;margin-top:8px" max-height="520"
      :row-class-name="rowClassName">
      <el-table-column label="#" prop="seq" width="44" fixed />
      <el-table-column label="项目" min-width="140" fixed>
        <template #default="{ row }">
          <el-input v-if="!isReadonly" v-model="row.item" size="small"
            @change="(v: string) => hd.updateCell(row.rowId, 'item', v)" />
          <span v-else>{{ row.item || '—' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="净头寸" width="120">
        <template #default="{ row }">
          <el-input v-if="row.rowKind === 'fv_allocation' && !isReadonly" v-model="row.netPosition" size="small"
            placeholder="支付200万美元"
            @change="(v: string) => hd.updateCell(row.rowId, 'netPosition', v)" />
          <span v-else-if="row.rowKind === 'fv_allocation'">{{ row.netPosition || '—' }}</span>
          <span v-else class="muted">—</span>
        </template>
      </el-table-column>
      <el-table-column label="套期工具" min-width="130">
        <template #default="{ row }">
          <el-input v-if="row.rowKind === 'fv_allocation' && !isReadonly" v-model="row.hedgingInstrument" size="small"
            @change="(v: string) => hd.updateCell(row.rowId, 'hedgingInstrument', v)" />
          <span v-else-if="row.rowKind === 'fv_allocation'">{{ row.hedgingInstrument || '—' }}</span>
          <span v-else class="muted">—</span>
        </template>
      </el-table-column>

      <el-table-column label="套期工具公允价值" align="center">
        <el-table-column label="累计FV变动" width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="row.rowKind === 'fv_allocation' && !isReadonly" v-model="row.instrumentFvCumulative"
              size="small" :controls="false" style="width:100%"
              @change="(v: number) => hd.updateCell(row.rowId, 'instrumentFvCumulative', v)" />
            <span v-else-if="row.rowKind === 'fv_allocation'">{{ fmt(row.instrumentFvCumulative) }}</span>
            <span v-else class="muted">—</span>
          </template>
        </el-table-column>
        <el-table-column label="销售部分" width="100" align="right">
          <template #default="{ row }">
            <el-input-number v-if="row.rowKind === 'fv_allocation' && !isReadonly" v-model="row.salesPortion"
              size="small" :controls="false" style="width:100%"
              @change="(v: number) => hd.updateCell(row.rowId, 'salesPortion', v)" />
            <span v-else-if="row.rowKind === 'fv_allocation'">{{ fmt(row.salesPortion) }}</span>
            <span v-else class="muted">—</span>
          </template>
        </el-table-column>
        <el-table-column label="采购部分" width="100" align="right">
          <template #default="{ row }">
            <el-input-number v-if="row.rowKind === 'fv_allocation' && !isReadonly" v-model="row.purchasePortion"
              size="small" :controls="false" style="width:100%"
              @change="(v: number) => hd.updateCell(row.rowId, 'purchasePortion', v)" />
            <span v-else-if="row.rowKind === 'fv_allocation'">{{ fmt(row.purchasePortion) }}</span>
            <span v-else class="muted">—</span>
          </template>
        </el-table-column>
        <el-table-column label="校验" width="64" align="center">
          <template #default="{ row }">
            <el-tag v-if="row.rowKind === 'fv_allocation'" size="small"
              :type="rowCalcMap.get(row.rowId)?.fvCheckOk ? 'success' : 'danger'">
              {{ rowCalcMap.get(row.rowId)?.fvCheckOk ? 'TRUE' : 'FALSE' }}
            </el-tag>
            <span v-else class="muted">—</span>
          </template>
        </el-table-column>
      </el-table-column>

      <el-table-column label="套期调整摊销" width="110" align="right">
        <template #default="{ row }">
          <el-input-number v-if="row.rowKind === 'amortization' && !isReadonly" v-model="row.hedgeAdjAmortization"
            size="small" :controls="false" style="width:100%"
            @change="(v: number) => hd.updateCell(row.rowId, 'hedgeAdjAmortization', v)" />
          <span v-else-if="row.rowKind === 'amortization'">{{ fmt(row.hedgeAdjAmortization) }}</span>
          <span v-else class="muted">—</span>
        </template>
      </el-table-column>

      <el-table-column label="净敞口套期损益" width="120" align="right">
        <template #default="{ row }">
          <span class="formula" title="FV 行=销售部分；摊销行=摊销金额">
            {{ fmt(rowCalcMap.get(row.rowId)?.netHedgePnl ?? 0) }}
          </span>
        </template>
      </el-table-column>

      <el-table-column label="索引号" width="100">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" v-model="row.indexRef" size="small"
            @change="(v: string) => hd.updateCell(row.rowId, 'indexRef', v)" />
          <GtIndexChip v-else-if="row.indexRef" :value="row.indexRef" />
          <span v-else>—</span>
        </template>
      </el-table-column>

      <el-table-column v-if="!isReadonly" label="操作" width="56" fixed="right">
        <template #default="{ row }">
          <el-button link type="danger" size="small" @click="hd.removeRow(row.rowId)">删</el-button>
        </template>
      </el-table-column>
    </el-table>

    <div class="totals">
      <span>累计FV：{{ fmt(hd.totals.value.instrumentFvCumulative) }}</span>
      <span>销售部分：{{ fmt(hd.totals.value.salesPortion) }}</span>
      <span>采购部分：{{ fmt(hd.totals.value.purchasePortion) }}</span>
      <span>摊销：{{ fmt(hd.totals.value.hedgeAdjAmortization) }}</span>
      <span class="total-pnl">净敞口套期损益合计：{{ fmt(hd.totals.value.netHedgePnl) }}</span>
    </div>

    <el-card shadow="never" class="audit-note-card">
      <template #header><div class="card-header"><span>三、审计说明</span></div></template>
      <el-input :model-value="auditNote" type="textarea" :autosize="{ minRows: 4 }" :disabled="isReadonly"
        placeholder="列示测试程序、调整事项及未调整影响。"
        @change="saveAuditNote" />
    </el-card>
    <el-card shadow="never" class="audit-note-card">
      <template #header><div class="card-header"><span>四、审计结论</span></div></template>
      <el-input :model-value="auditConclusion" type="textarea" :autosize="{ minRows: 3 }" :disabled="isReadonly"
        placeholder="A、未见异常。B、除上述调整事项外，其余未见异常。C、存在重大未调整事项，不可确认。"
        @change="saveAuditConclusion" />
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, toRef, inject, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { useG12HedgeDetail, mapG12HedgeDetailForFvCross } from '../../composables/useG12HedgeDetail'
import { useG12NetExposure } from '../../composables/useG12NetExposure'
import {
  G12_NET_HEDGE_DETAIL_OBJECTIVE,
  G12_NET_HEDGE_DETAIL_GUIDANCE,
} from '../../composables/g12NetHedgeDetailSeed'
import { G12_CORE_WORKFLOW_HINT, G12_CORE_WORKFLOW_STEPS } from '../../composables/g12Constants'
import { useG12CoreWorkflow } from '../../composables/useG12CoreWorkflow'
import { findG12FvCrossMismatches, hasG12FvTestData } from '../../composables/useG12CrossValidate'
import { resolveG12SheetLabel } from '../../composables/g12SheetLabels'
import type { ChecklistResponse } from '../../composables/useF1FormData'
import CycleImportExportDropdown from '../../shared/CycleImportExportDropdown.vue'
import GtReviewTrigger from '../../GtReviewTrigger.vue'
import GtIndexChip from '../../GtIndexChip.vue'
import GCycleGuideStrip from '../../shared/GCycleGuideStrip.vue'
import G12CoreWorkflowChecklist from '../shared/G12CoreWorkflowChecklist.vue'

const props = defineProps<{
  allResponses: Map<string, ChecklistResponse>
  wpId: string
  isReadonly: boolean
  debouncedSave: (id: string, d: Partial<ChecklistResponse>) => void
}>()
const emit = defineEmits<{ imported: [] }>()
const jumpToSection = inject<((sheetName: string) => void) | null>('jumpToSection', null)

const hd = useG12HedgeDetail({
  allResponses: toRef(props, 'allResponses'),
  isReadonly: toRef(props, 'isReadonly'),
  debouncedSave: props.debouncedSave,
})

const ne = useG12NetExposure({
  allResponses: toRef(props, 'allResponses'),
  isReadonly: toRef(props, 'isReadonly'),
  debouncedSave: props.debouncedSave,
})

const wf = useG12CoreWorkflow({ allResponses: toRef(props, 'allResponses'), pageCode: 'G12-2' })

const auditObjective = G12_NET_HEDGE_DETAIL_OBJECTIVE
const guidanceLines = G12_NET_HEDGE_DETAIL_GUIDANCE

const NOTE_KEY = 'G12-hedge-detail-audit-note'
const CONCLUSION_KEY = 'G12-hedge-detail-audit-conclusion'
const auditNote = ref('')
const auditConclusion = ref('')

function saveAuditNote(val: string): void {
  if (props.isReadonly) return
  auditNote.value = val
  props.debouncedSave(NOTE_KEY, { conclusion: null, remark: val })
}
function saveAuditConclusion(val: string): void {
  if (props.isReadonly) return
  auditConclusion.value = val
  props.debouncedSave(CONCLUSION_KEY, { conclusion: null, remark: val })
}

onMounted(() => {
  auditNote.value = props.allResponses.get(NOTE_KEY)?.remark ?? ''
  auditConclusion.value = props.allResponses.get(CONCLUSION_KEY)?.remark ?? ''
})

const tableRows = computed(() => hd.rows.value)
const rowCalcMap = computed(() => new Map(hd.rowCalcs.value.map((c) => [c.rowId, c])))

const crossMismatches = computed(() =>
  findG12FvCrossMismatches(mapG12HedgeDetailForFvCross(hd.rows.value), props.allResponses),
)
const hasFvTestData = computed(() => hasG12FvTestData(props.allResponses))

function fmt(val: number): string {
  if (val === 0) return '0.00'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function rowClassName({ row }: { row: { rowId: string; rowKind: string } }): string {
  const classes: string[] = []
  const calc = rowCalcMap.value.get(row.rowId)
  if (row.rowKind === 'fv_allocation' && calc && !calc.fvCheckOk) classes.push('g12-fv-check-fail')
  if (crossMismatches.value.some((m) => m.hedgeRelationId === row.rowId)) classes.push('g12-cross-warn')
  return classes.join(' ')
}

function importFromG12_5() {
  const added = hd.importFromNetExposure(
    ne.rows.value.map((r) => ({
      item: r.item,
      netPosition: r.netPosition,
      hedgingInstrument: r.hedgingInstrument,
      indexRef: r.indexRef,
    })),
  )
  if (added) ElMessage.success(`已从 G12-5 新增 ${added} 行`)
  else ElMessage.info('G12-5 无新增项目（可能已全部存在）')
}

function syncNetPositionFromG12_5() {
  const n = hd.syncNetPositionFromG12_5(ne.rows.value)
  if (n) ElMessage.success(`已同步 ${n} 行净头寸`)
  else ElMessage.info('无可同步的净头寸（请先匹配项目/套期工具）')
}

function importAmortization() {
  const n = hd.importAmortizationFromResponses(props.allResponses)
  if (n) ElMessage.success(`已带入 ${n} 条摊销行`)
  else ElMessage.info('G12-4/G12-6 中未发现可带入的摊销/6103 分录')
}
</script>

<style scoped>
.g12-hedge { padding: 12px; font-size: var(--wp-font-size, 13px); }
.toolbar { display: flex; justify-content: space-between; align-items: flex-start; flex-wrap: wrap; gap: 8px; margin-bottom: 8px; }
.title-block h3 { margin: 0; }
.sheet-sub { margin: 4px 0 0; color: #909399; font-size: 12px; }
.head-actions { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.guidance-details { margin-bottom: 8px; padding: 8px 12px; border-left: 3px solid #409eff; background: #ecf5ff; border-radius: 0 4px 4px 0; font-size: 12px; color: #606266; }
.guidance-details summary { cursor: pointer; font-weight: 500; color: #409eff; }
.guidance-content p { margin: 4px 0; }
.tab-toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; flex-wrap: wrap; gap: 8px; }
.toolbar-left { display: flex; gap: 6px; align-items: center; }
.chip-wrap { display: inline-flex; align-items: center; }
.audit-note-card { margin-top: 16px; }
.audit-note-card .card-header { font-weight: 500; }
.audit-objective { margin-bottom: 8px; }
.cross-alert { margin-bottom: 8px; }
.cross-ok :deep(.el-alert__content) { display: flex; align-items: center; flex-wrap: wrap; gap: 4px; }
.warn-chip, .ok-chip { margin-left: 8px; }
.cross-line { font-size: 12px; }
.formula { border-bottom: 1px dashed #909399; background: #fafafa; cursor: help; display: inline-block; width: 100%; }
.totals { display: flex; gap: 16px; flex-wrap: wrap; margin-top: 10px; padding: 8px 12px; background: #fafafa; border-radius: 4px; font-size: 12px; font-weight: 500; }
.total-pnl { color: #303133; font-weight: 600; }
.muted { color: #c0c4cc; }
:deep(.g12-cross-warn) { background: #fdf6ec !important; }
:deep(.g12-fv-check-fail) { background: #fef0f0 !important; }
</style>
