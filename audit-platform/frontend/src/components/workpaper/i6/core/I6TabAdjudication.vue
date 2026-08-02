<template>
  <div class="i6-adjudication">
    <div class="methodology-context">
      <p><strong>研发费用审定原理：</strong>科目6602（损益类/借方）。取发生额非余额。</p>
      <p>审定数=未审数+AJE+RJE。数据优先自 I6-2 明细引用；TB数据行用于与试算表勾稽。</p>
      <p>I6↔I2联动：费用化(I6)+资本化(I2)=研发总额(VR-I6-01)。变动率超±30%需补充说明。</p>
    </div>

    <el-alert
      type="info"
      :closable="false"
      title="审计目标：核实研发费用（6602）本期发生额的完整性与准确性，验证费用化与资本化划分（VR-I6-01）恰当，为附注披露及加计扣除提供审定依据。"
      class="objective-alert"
    />

    <WpFourTableSourcePanel
      :source-codes="tbSourceCodes"
      :gross-label="sourceConfig.grossLabel"
      :provision-label="sourceConfig.provisionLabel"
      :fallback-row-code="sourceConfig.fallbackRowCode"
      :hints="sourceConfig.hints"
    />

    <el-alert
      v-if="linkagePanel.i2DataReady && !linkagePanel.vrI601Status.isValid"
      type="error"
      :title="`VR-I6-01不平：费用化(${fmtAmount(linkagePanel.expenseI6)}) + 资本化(${fmtAmount(linkagePanel.capitalizedI2)}) ≠ 研发总额，差额 ${fmtAmount(linkagePanel.vrI601Status.difference)}`"
      show-icon
      :closable="false"
      class="adj-warning"
    />

    <el-alert
      v-if="detailCrossValidation"
      type="warning"
      :title="detailCrossValidation"
      show-icon
      :closable="false"
      class="adj-warning"
    />

    <el-alert
      v-if="Math.abs(tbDifference) > 0.01"
      type="warning"
      :title="`TB差异：审定合计 ${fmtAmount(totalRow.本期审定)} − TB未审 ${fmtAmount(tbUnadjusted)} = ${fmtAmount(tbDifference)}`"
      show-icon
      :closable="false"
      class="adj-warning"
    />

    <el-alert
      v-if="adj.needsAuditNoteDraft.value"
      type="warning"
      :closable="false"
      show-icon
      class="adj-warning"
    >
      <template #title>
        变动率超30%的类别共 {{ adj.highChangeRateRows.value.length }} 项，须在审计说明中披露主要原因
      </template>
      <template #default>
        <el-button
          v-if="!isReadonly"
          size="small"
          type="primary"
          plain
          class="draft-btn"
          @click="handleApplyNoteDraft"
        >
          生成变动说明草稿
        </el-button>
      </template>
    </el-alert>

    <div class="table-section">
      <div class="block-header">
        <span class="block-title">研发费用审定表（I6-1）</span>
        <div class="block-actions">
          <el-button size="small" type="primary" plain :loading="adjPull.loading.value" @click="openBringInAdjustment">
            <el-icon><Download /></el-icon>带入调整
          </el-button>
          <el-button size="small" type="primary" plain :disabled="isReadonly" @click="adj.syncFromDetail(false)">
            从 I6-2 取数
          </el-button>
          <el-button size="small" plain :disabled="isReadonly" @click="handleSyncFromI63">
            从 I6-3 同步调整
          </el-button>
          <el-button size="small" :disabled="isReadonly" @click="adj.syncFromDetail(true)">强制覆盖</el-button>
          <el-button size="small" type="success" :disabled="isReadonly" @click="adj.writeback()">
            回写TB(6602)
          </el-button>
          <el-button size="small" type="default" text @click="handleReview">复核</el-button>
        </div>
      </div>

      <div class="tab-toolbar">
        <div class="toolbar-left">
          <GtIndexChip v-if="discVis.listed" value="Note:五、66" :context-project-id="projectId" />
          <GtIndexChip v-if="discVis.soe" value="Note:八、67" :context-project-id="projectId" />
        </div>
        <div class="toolbar-right">
          <span class="chip-wrap"><GtIndexChip value="wp:I6-1" :context-project-id="projectId" /></span>
          <span
            v-if="!linkagePanel.i2DataReady"
            class="linkage-info"
          >
            I2 资本化数据未同步
          </span>
          <span
            v-else-if="!linkagePanel.vrI601Status.isValid"
            class="linkage-warn"
          >
            VR-I6-01 不平衡（差额 {{ fmtAmount(linkagePanel.vrI601Status.difference) }}）
          </span>
          <span
            v-else
            class="linkage-ok"
          >
            ✓ VR-I6-01 已核对
          </span>
          <GtIndexChip value="I2" @click="navigateTo('I2')" />
          <el-tag size="small" type="info">共 {{ displayRows.length }} 行</el-tag>
        </div>
      </div>

      <el-table
        :data="displayRows"
        border
        size="small"
        :row-class-name="getRowClassName"
        class="adjudication-table"
        max-height="560"
        scrollbar-always-on
      >
        <el-table-column prop="类别" label="类别" min-width="140" fixed>
          <template #default="{ row }">
            <span :class="{ 'subtotal-text': row.isTotal, 'control-text': row.isControl }">{{ row.类别 }}</span>
          </template>
        </el-table-column>
        <el-table-column label="上期未审(B)" min-width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="row.isEditable && !isReadonly" :model-value="row.上期未审" size="small" :controls="false" @change="(v: number) => onCellChange(row, '上期未审', v)" />
            <span v-else>{{ fmtAmount(row.上期未审) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="上期AJE(C)" min-width="100" align="right">
          <template #default="{ row }">
            <el-input-number v-if="row.isEditable && !isReadonly" :model-value="row.上期AJE" size="small" :controls="false" @change="(v: number) => onCellChange(row, '上期AJE', v)" />
            <span v-else>{{ fmtAmount(row.上期AJE) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="上期RJE(D)" min-width="100" align="right">
          <template #default="{ row }">
            <el-input-number v-if="row.isEditable && !isReadonly" :model-value="row.上期RJE" size="small" :controls="false" @change="(v: number) => onCellChange(row, '上期RJE', v)" />
            <span v-else>{{ fmtAmount(row.上期RJE) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="上期审定(E)" min-width="110" align="right">
          <template #default="{ row }">
            <span class="formula-value">{{ fmtAmount(row.上期审定) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="本期未审(F)" min-width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="row.isEditable && !isReadonly" :model-value="row.本期未审" size="small" :controls="false" @change="(v: number) => onCellChange(row, '本期未审', v)" />
            <span v-else>{{ fmtAmount(row.本期未审) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="本期AJE(G)" min-width="100" align="right">
          <template #default="{ row }">
            <el-input-number v-if="row.isEditable && !isReadonly" :model-value="row.本期AJE" size="small" :controls="false" @change="(v: number) => onCellChange(row, '本期AJE', v)" />
            <span v-else>{{ fmtAmount(row.本期AJE) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="本期RJE(H)" min-width="100" align="right">
          <template #default="{ row }">
            <el-input-number v-if="row.isEditable && !isReadonly" :model-value="row.本期RJE" size="small" :controls="false" @change="(v: number) => onCellChange(row, '本期RJE', v)" />
            <span v-else>{{ fmtAmount(row.本期RJE) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="本期审定(I)" min-width="110" align="right">
          <template #default="{ row }">
            <span class="formula-value">{{ fmtAmount(row.本期审定) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="变动额(J)" min-width="110" align="right">
          <template #default="{ row }">
            <span class="formula-value">{{ fmtAmount(row.变动额) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="变动率" min-width="90" align="right">
          <template #default="{ row }">
            <span class="formula-value" :class="{ 'rate-warn': row.changeRateHighlight }">
              {{ fmtRate(row.变动率) }}
            </span>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <el-card shadow="never" class="linkage-card">
      <template #header>
        <div class="card-header">
          <span>I6↔I2 联动面板（VR-I6-01）</span>
        </div>
      </template>
      <el-descriptions :column="4" border size="small">
        <el-descriptions-item label="费用化(I6)">{{ fmtAmount(linkagePanel.expenseI6) }}</el-descriptions-item>
        <el-descriptions-item label="资本化(I2)">{{ fmtAmount(linkagePanel.capitalizedI2) }}</el-descriptions-item>
        <el-descriptions-item label="研发总额">{{ fmtAmount(linkagePanel.researchTotal) }}</el-descriptions-item>
        <el-descriptions-item label="VR-I6-01">
          <el-tag :type="linkagePanel.vrI601Status.isValid ? 'success' : 'danger'" size="small">
            {{ linkagePanel.vrI601Status.isValid ? '✓ 平衡' : '✗ 不平衡' }}
          </el-tag>
        </el-descriptions-item>
      </el-descriptions>
      <div class="cross-ref-bar">
        <span class="cross-ref-label">跨底稿联动：</span>
        <GtIndexChip value="I2" @click="navigateTo('I2')" />
        <GtIndexChip value="I6-2" @click="navigateTo('I6-2')" />
        <GtIndexChip value="I6-3" @click="navigateTo('I6-3')" />
        <GtIndexChip v-if="discVis.listed" value="附注上市" @click="navigateTo('附注上市')" />
        <GtIndexChip v-if="discVis.soe" value="附注国企" @click="navigateTo('附注国企')" />
      </div>
    </el-card>

    <el-card class="audit-note-card" shadow="never">
      <template #header><div class="card-header"><span>审计说明</span></div></template>
      <el-input
        :model-value="adj.auditNote.value"
        type="textarea"
        :autosize="{ minRows: 4 }"
        placeholder="说明研发费用增减变动主要原因（变动率超30%须重点说明）、与I2划分一致性等…"
        :disabled="isReadonly"
        @change="adj.saveNote"
      />
      <div v-if="!isReadonly && adj.needsAuditNoteDraft.value" class="note-draft-hint">
        <el-button size="small" type="warning" plain @click="handleApplyNoteDraft">
          一键填入变动率超30%说明草稿
        </el-button>
      </div>
    </el-card>

    <el-card class="audit-note-card" shadow="never">
      <template #header><div class="card-header"><span>审计结论</span></div></template>
      <el-select
        :model-value="adj.auditConclusion.value"
        placeholder="请选择审计结论"
        :disabled="isReadonly"
        class="conclusion-select"
        @change="adj.saveConclusion"
      >
        <el-option value="研发费用发生额列报恰当，费用化与资本化划分正确" label="研发费用发生额列报恰当，费用化与资本化划分正确" />
        <el-option value="经审计调整后，研发费用列报恰当" label="经审计调整后，研发费用列报恰当" />
        <el-option value="需进一步关注" label="需进一步关注" />
      </el-select>
    </el-card>

    <details class="compile-hint" open>
      <summary>编制说明</summary>
      <ol>
        <li>类别行数据引用 I6-2 明细（未审/AJE/RJE/审定），公式：审定=未审+AJE+RJE。</li>
        <li>合计行为各类别加总；TB数据行为试算表6602未审发生额；差异=合计本期审定−TB数据。</li>
        <li>回写TB后发布 <code>substantive:adjudicated</code>，驱动附注披露表自动刷新。</li>
        <li>附注同步目标：上市 §五、66 / 国企 §八、67「研发费用（按费用性质列示）」。</li>
        <li>「带入调整」：从集中登记按科目 6602 拉取调整分录，逐笔分配到各费用类别的本期 AJE/RJE，带入后审定数自动更新并联动附注。</li>
      </ol>
    </details>

    <AdjudicationBringInDialog
      v-model="bringInVisible"
      :matches="adjPull.matches.value"
      :row-options="bringInRowOptions"
      subject-label="6602 研发费用"
      :loading="adjPull.loading.value"
      @apply="onBringInApply"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, inject } from 'vue'
import { ElMessage } from 'element-plus'
import { Download } from '@element-plus/icons-vue'
import GtIndexChip from '../../GtIndexChip.vue'
import { useI6Adjudication, type I6AdjudicationRow } from '../../composables/useI6Adjudication'
import { resolveI6DisclosureVisibility } from '../../composables/i6ApplicableSheets'
import { useAdjudicationBringIn } from '../../composables/useAdjudicationBringIn'
import { useAuditContext } from '@/composables/useAuditContext'
import AdjudicationBringInDialog from '@/components/adjustment/AdjudicationBringInDialog.vue'
import WpFourTableSourcePanel from '../../shared/WpFourTableSourcePanel.vue'
import { getICycleSourceConfig, extractTbSourceCodes } from '../../composables/useICycleFourTableSource'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  tbData: { unadjusted6602: number; audited6602: number }
  isReadonly: boolean
  applicableStandards?: string[]
  htmlData?: Record<string, unknown> | null
}>()

const emit = defineEmits<{
  'navigate-sheet': [sheetName: string]
  'save': [itemId: string, value: any]
}>()

const openReviewDialog = inject<(section?: string) => void>('openReviewDialog', () => {})

const sourceConfig = getICycleSourceConfig('I6')
const tbSourceCodes = computed(() => extractTbSourceCodes(props.htmlData))

const adj = useI6Adjudication({
  allResponses: computed(() => props.allResponses),
  tbData: computed(() => props.tbData),
  projectId: computed(() => props.projectId),
  isReadonly: computed(() => props.isReadonly),
  onSave: (itemId, value) => emit('save', itemId, value),
})

const totalRow = adj.totalRow
const linkagePanel = adj.linkagePanel
const tbUnadjusted = adj.tbUnadjusted
const tbDifference = adj.tbDifference
const detailCrossValidation = adj.detailCrossValidation

// ─── 从集中登记带入调整（6602 研发费用，损益借方；带入本期 AJE/RJE） ───
const bringInRows = computed(() =>
  adj.rows.value.map((r) => ({ rowKey: r.rowId, name: r.类别, aje: r.本期AJE, rje: r.本期RJE })),
)
const {
  adjPull,
  visible: bringInVisible,
  rowOptions: bringInRowOptions,
  open: openBringInAdjustment,
  apply: onBringInApply,
} = useAdjudicationBringIn({
  projectId: computed(() => props.projectId) as any,
  year: useAuditContext().year as any,
  subjectPrefix: '6602',
  direction: 'debit',
  subjectCode: '6602',
  wpCode: 'I6',
  subjectLabel: '研发费用(6602)',
  rows: bringInRows,
  updateCell: (rowKey: string, field: any, value: number) =>
    adj.updateCell(rowKey, field === 'rje' ? '本期RJE' : '本期AJE', value),
  totalAudited: () => totalRow.value.本期审定,
})

const discVis = computed(() => resolveI6DisclosureVisibility(props.applicableStandards))

interface DisplayRow extends I6AdjudicationRow {
  isControl?: boolean
}

const displayRows = computed<DisplayRow[]>(() => {
  const detail = adj.rows.value
  const total = totalRow.value
  const tbRow: DisplayRow = {
    rowId: 'row-tb',
    类别: 'TB数据',
    上期未审: 0, 上期AJE: 0, 上期RJE: 0, 上期审定: 0,
    本期未审: tbUnadjusted.value, 本期AJE: 0, 本期RJE: 0,
    本期审定: tbUnadjusted.value,
    变动额: 0, 变动率: null, 备注: '', changeRateHighlight: false,
    isEditable: false, isTotal: false, isControl: true,
  }
  const diffRow: DisplayRow = {
    rowId: 'row-diff',
    类别: '差异',
    上期未审: 0, 上期AJE: 0, 上期RJE: 0, 上期审定: 0,
    本期未审: 0, 本期AJE: 0, 本期RJE: 0,
    本期审定: tbDifference.value,
    变动额: 0, 变动率: null, 备注: '', changeRateHighlight: Math.abs(tbDifference.value) > 0.01,
    isEditable: false, isTotal: false, isControl: true,
  }
  return [...detail, total, tbRow, diffRow]
})

function onCellChange(row: I6AdjudicationRow, field: keyof I6AdjudicationRow, value: number): void {
  adj.updateCell(row.rowId, field, value)
}

function getRowClassName({ row }: { row: DisplayRow }): string {
  if (row.isTotal) return 'row-subtotal'
  if (row.isControl) return 'row-control'
  return ''
}

function handleReview(): void { openReviewDialog('I6-1 审定表') }
function navigateTo(code: string): void { emit('navigate-sheet', code) }

function handleSyncFromI63(): void {
  adj.syncFromI63()
}

function handleApplyNoteDraft(): void {
  if (adj.applyAuditNoteDraft()) {
    ElMessage.success('已生成变动说明草稿，请补充具体原因后保存')
  } else {
    ElMessage.info('当前无变动率超30%的类别')
  }
}

function fmtAmount(v: number | null | undefined): string {
  if (v == null) return '-'
  if (Math.abs(v) < 0.005) return '-'
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function fmtRate(rate: number | null | undefined): string {
  if (rate == null) return '-'
  return (rate * 100).toFixed(1) + '%'
}
</script>

<style scoped>
.i6-adjudication { font-size: var(--wp-font-size, 13px); padding: 16px; }
.methodology-context { border-left: 4px solid #d97706; background: #fffbeb; padding: 12px 16px; margin-bottom: 16px; border-radius: 4px; font-size: 12px; color: #92400e; line-height: 1.8; }
.methodology-context p { margin: 0; }
.objective-alert, .adj-warning { margin-bottom: 12px; }
.table-section { margin-bottom: 20px; }
.block-header { display: flex; align-items: center; justify-content: space-between; padding: 10px 0; font-weight: 600; font-size: 14px; flex-wrap: wrap; gap: 8px; }
.block-actions { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
.tab-toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.toolbar-left, .toolbar-right { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.linkage-warn { font-size: 12px; color: #e6a23c; font-weight: 500; }
.linkage-info { font-size: 12px; color: var(--el-text-color-secondary); }
.linkage-ok { font-size: 12px; color: #67c23a; font-weight: 500; }
.adjudication-table { font-size: var(--wp-font-size, 13px); }
.formula-value { border-bottom: 1px dashed #c0c4cc; cursor: help; font-weight: 500; }
.adjudication-table :deep(.row-subtotal td) { font-weight: 600; background: #f0f9ff !important; }
.adjudication-table :deep(.row-control td) { font-weight: 600; background: #fefce8 !important; }
.subtotal-text, .control-text { font-weight: 600; }
.rate-warn { color: #d97706; font-weight: 600; background: #fefce8; padding: 1px 4px; border-radius: 2px; }
.linkage-card { margin-bottom: 16px; }
.card-header { display: flex; align-items: center; justify-content: space-between; font-size: 14px; font-weight: 500; }
.cross-ref-bar { display: flex; align-items: center; gap: 8px; padding: 12px 0; flex-wrap: wrap; }
.cross-ref-label { color: #606266; font-size: var(--wp-font-size, 13px); }
.audit-note-card { margin-bottom: 16px; }
.audit-note-card :deep(.el-card__header) { padding: 12px 16px; background: #fafafa; }
.conclusion-select { width: 100%; }
.compile-hint { margin-top: 12px; font-size: 12px; color: var(--el-text-color-secondary); }
.compile-hint summary { cursor: pointer; font-weight: 500; color: var(--el-text-color-primary); }
.compile-hint ol { padding-left: 20px; margin: 8px 0 0; }
.compile-hint li { margin-bottom: 4px; line-height: 1.5; }
.draft-btn { margin-top: 6px; }
.note-draft-hint { margin-top: 8px; }
</style>
