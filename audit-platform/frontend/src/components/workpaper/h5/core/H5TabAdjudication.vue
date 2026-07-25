<template>
  <div class="h5-tab-adjudication">
    <!-- 审计目标 -->
    <el-alert type="info" :closable="false" title="审计目标：汇总油气资产（1631）、累计折耗（1632）及减值准备的审定结果，验证三角勾稽平衡并回写试算表。" class="objective-alert" />

    <!-- 工具栏 -->
    <div class="tab-toolbar">
      <div class="toolbar-right">
        <el-button v-if="!isReadonly" size="small" type="primary" plain :loading="adjPullCost.loading.value" @click="openBringInCost">
          <el-icon><Download /></el-icon>带入调整(原值)
        </el-button>
        <el-button v-if="!isReadonly" size="small" type="primary" plain :loading="adjPullDepletion.loading.value" @click="openBringInDepletion">
          <el-icon><Download /></el-icon>带入调整(累计折耗)
        </el-button>
        <span class="chip-wrap"><GtIndexChip value="wp:H5-1" :context-project-id="projectId" /></span>
      </div>
    </div>

    <!-- 一、油气资产原值 -->
    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="section-title">
          <span>一、油气资产原值（科目1631）</span>
          <div class="title-actions">
            <el-button size="small" type="default" link @click="handleReview('H5-1-cost')">
              💬 复核
            </el-button>
          </div>
        </div>
      </template>
      <el-table :data="costDisplayRows" border stripe size="small" class="adj-table">
        <el-table-column prop="category" label="项目" min-width="130" fixed />
        <el-table-column prop="beginBalance" label="期初余额" min-width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="row.isEditable && !isReadonly" v-model="row.beginBalance" :controls="false" size="small" class="amount-input"
              @change="onCellChange('cost', row.rowId, 'beginBalance', $event)" />
            <span v-else class="amount-cell">{{ fmtAmt(row.beginBalance) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="debit" label="本期借方" min-width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="row.isEditable && !isReadonly" v-model="row.debit" :controls="false" size="small" class="amount-input"
              @change="onCellChange('cost', row.rowId, 'debit', $event)" />
            <span v-else class="amount-cell">{{ fmtAmt(row.debit) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="credit" label="本期贷方" min-width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="row.isEditable && !isReadonly" v-model="row.credit" :controls="false" size="small" class="amount-input"
              @change="onCellChange('cost', row.rowId, 'credit', $event)" />
            <span v-else class="amount-cell">{{ fmtAmt(row.credit) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期末余额" min-width="110" align="right">
          <template #default="{ row }">
            <span class="formula-cell" title="期末=期初+借方-贷方">{{ fmtAmt(row.endBalance) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="unadjusted" label="未审数" min-width="110" align="right">
          <template #default="{ row }">
            <span class="amount-cell tb-auto">{{ fmtAmt(row.unadjusted) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="aje" label="AJE" min-width="100" align="right">
          <template #default="{ row }">
            <el-input-number v-if="row.isEditable && !isReadonly" v-model="row.aje" :controls="false" size="small" class="amount-input"
              @change="onCellChange('cost', row.rowId, 'aje', $event)" />
            <span v-else class="amount-cell">{{ fmtAmt(row.aje) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="rje" label="RJE" min-width="100" align="right">
          <template #default="{ row }">
            <el-input-number v-if="row.isEditable && !isReadonly" v-model="row.rje" :controls="false" size="small" class="amount-input"
              @change="onCellChange('cost', row.rowId, 'rje', $event)" />
            <span v-else class="amount-cell">{{ fmtAmt(row.rje) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="审定数" min-width="110" align="right">
          <template #default="{ row }">
            <span class="formula-cell" title="审定=未审+AJE+RJE">{{ fmtAmt(row.audited) }}</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 二、累计折耗 -->
    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="section-title">
          <span>二、累计折耗（科目1632·备抵）</span>
          <div class="title-actions">
            <el-button size="small" type="default" link @click="handleReview('H5-1-depletion')">
              💬 复核
            </el-button>
          </div>
        </div>
      </template>
      <el-table :data="depletionDisplayRows" border stripe size="small" class="adj-table">
        <el-table-column prop="category" label="项目" min-width="130" fixed />
        <el-table-column prop="beginBalance" label="期初余额" min-width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="row.isEditable && !isReadonly" v-model="row.beginBalance" :controls="false" size="small" class="amount-input"
              @change="onCellChange('depletion', row.rowId, 'beginBalance', $event)" />
            <span v-else class="amount-cell">{{ fmtAmt(row.beginBalance) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="debit" label="本期借方(减少)" min-width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="row.isEditable && !isReadonly" v-model="row.debit" :controls="false" size="small" class="amount-input"
              @change="onCellChange('depletion', row.rowId, 'debit', $event)" />
            <span v-else class="amount-cell">{{ fmtAmt(row.debit) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="credit" label="本期贷方(增加)" min-width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="row.isEditable && !isReadonly" v-model="row.credit" :controls="false" size="small" class="amount-input"
              @change="onCellChange('depletion', row.rowId, 'credit', $event)" />
            <span v-else class="amount-cell">{{ fmtAmt(row.credit) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期末余额" min-width="110" align="right">
          <template #default="{ row }">
            <span class="formula-cell" title="备抵期末=期初+贷方-借方">{{ fmtAmt(row.endBalance) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="unadjusted" label="未审数" min-width="110" align="right">
          <template #default="{ row }">
            <span class="amount-cell tb-auto">{{ fmtAmt(row.unadjusted) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="aje" label="AJE" min-width="100" align="right">
          <template #default="{ row }">
            <el-input-number v-if="row.isEditable && !isReadonly" v-model="row.aje" :controls="false" size="small" class="amount-input"
              @change="onCellChange('depletion', row.rowId, 'aje', $event)" />
            <span v-else class="amount-cell">{{ fmtAmt(row.aje) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="rje" label="RJE" min-width="100" align="right">
          <template #default="{ row }">
            <el-input-number v-if="row.isEditable && !isReadonly" v-model="row.rje" :controls="false" size="small" class="amount-input"
              @change="onCellChange('depletion', row.rowId, 'rje', $event)" />
            <span v-else class="amount-cell">{{ fmtAmt(row.rje) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="审定数" min-width="110" align="right">
          <template #default="{ row }">
            <span class="formula-cell" title="审定=未审+AJE+RJE">{{ fmtAmt(row.audited) }}</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 三、减值准备 -->
    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="section-title">
          <span>三、减值准备</span>
          <div class="title-actions">
            <el-button size="small" type="default" link @click="handleReview('H5-1-impairment')">
              💬 复核
            </el-button>
          </div>
        </div>
      </template>
      <el-table :data="impairmentDisplayRows" border stripe size="small" class="adj-table">
        <el-table-column prop="category" label="项目" min-width="130" fixed />
        <el-table-column prop="beginBalance" label="期初余额" min-width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="row.isEditable && !isReadonly" v-model="row.beginBalance" :controls="false" size="small" class="amount-input"
              @change="onCellChange('impairment', row.rowId, 'beginBalance', $event)" />
            <span v-else class="amount-cell">{{ fmtAmt(row.beginBalance) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="debit" label="本期借方(转回)" min-width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="row.isEditable && !isReadonly" v-model="row.debit" :controls="false" size="small" class="amount-input"
              @change="onCellChange('impairment', row.rowId, 'debit', $event)" />
            <span v-else class="amount-cell">{{ fmtAmt(row.debit) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="credit" label="本期贷方(计提)" min-width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="row.isEditable && !isReadonly" v-model="row.credit" :controls="false" size="small" class="amount-input"
              @change="onCellChange('impairment', row.rowId, 'credit', $event)" />
            <span v-else class="amount-cell">{{ fmtAmt(row.credit) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期末余额" min-width="110" align="right">
          <template #default="{ row }">
            <span class="formula-cell" title="备抵期末=期初+贷方-借方">{{ fmtAmt(row.endBalance) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="unadjusted" label="未审数" min-width="110" align="right">
          <template #default="{ row }">
            <span class="amount-cell tb-auto">{{ fmtAmt(row.unadjusted) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="aje" label="AJE" min-width="100" align="right">
          <template #default="{ row }">
            <el-input-number v-if="row.isEditable && !isReadonly" v-model="row.aje" :controls="false" size="small" class="amount-input"
              @change="onCellChange('impairment', row.rowId, 'aje', $event)" />
            <span v-else class="amount-cell">{{ fmtAmt(row.aje) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="rje" label="RJE" min-width="100" align="right">
          <template #default="{ row }">
            <el-input-number v-if="row.isEditable && !isReadonly" v-model="row.rje" :controls="false" size="small" class="amount-input"
              @change="onCellChange('impairment', row.rowId, 'rje', $event)" />
            <span v-else class="amount-cell">{{ fmtAmt(row.rje) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="审定数" min-width="110" align="right">
          <template #default="{ row }">
            <span class="formula-cell" title="审定=未审+AJE+RJE">{{ fmtAmt(row.audited) }}</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 四、油气资产净值 + 三角勾稽 -->
    <el-card shadow="never" class="reconciliation-card">
      <template #header>
        <div class="section-title">
          <span>四、油气资产净值与三角勾稽校验</span>
        </div>
      </template>
      <div class="net-value-row">
        <span>油气资产净值 = 原值审定 - 累计折耗审定 - 减值准备审定 = </span>
        <span class="formula-cell" title="净值=原值-折耗-减值">{{ fmtAmt(state.netValueAudited.value) }}</span>
      </div>
      <el-divider />
      <el-table :data="state.reconciliationResults.value" size="small" border>
        <el-table-column prop="layer" label="校验层" width="160" />
        <el-table-column label="差额" width="150" align="right">
          <template #default="{ row }">
            <span :class="['amount-cell', { 'error-amount': !row.isBalanced }]">
              {{ fmtAmt(row.difference) }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="100" align="center">
          <template #default="{ row }">
            <span v-if="row.isBalanced" class="reconcile-ok">✓</span>
            <span v-else class="reconcile-warn">⚠</span>
          </template>
        </el-table-column>
      </el-table>

      <!-- 交叉验证H5-2 -->
      <div v-if="state.crossValidation.value.hasCostWarning || state.crossValidation.value.hasDepWarning" class="cross-warning">
        <el-alert type="warning" :closable="false" show-icon>
          <template #title>
            交叉验证异常（H5-2明细表）：
            <span v-if="state.crossValidation.value.hasCostWarning">原值差异 {{ fmtAmt(state.crossValidation.value.costDiff) }}</span>
            <span v-if="state.crossValidation.value.hasDepWarning"> 折耗差异 {{ fmtAmt(state.crossValidation.value.depDiff) }}</span>
          </template>
        </el-alert>
      </div>
    </el-card>

    <!-- 审计说明 -->
    <el-card shadow="never" class="note-card">
      <template #header>
        <div class="section-title">
          <span>审计说明</span>
        </div>
      </template>
      <el-input v-model="state.auditNote.value" type="textarea" :autosize="{ minRows: 3, maxRows: 8 }" placeholder="请填写审计说明..."
        :disabled="isReadonly" @blur="state.saveNote(state.auditNote.value)" />
    </el-card>

    <!-- 审计结论 -->
    <el-card shadow="never" class="note-card">
      <template #header>
        <div class="section-title"><span>审计结论</span></div>
      </template>
      <el-input v-model="state.auditConclusion.value" type="textarea" :autosize="{ minRows: 3, maxRows: 6 }"
        placeholder="填写审计结论：A、未见异常。B、除上述重大不符事项应作调整外，其余未见异常。C、存在重大未调整事项/审计范围受限，不可确认。"
        :disabled="isReadonly" @blur="state.saveConclusion(state.auditConclusion.value)" />
    </el-card>

    <!-- 操作按钮 -->
    <div class="action-bar" v-if="!isReadonly">
      <el-button type="primary" @click="handlePublish" :loading="publishing">
        确认审定 → 回写TB
      </el-button>
    </div>

    <!-- 编制提示 -->
    <details class="compile-hint">
      <summary>编制提示</summary>
      <ul>
        <li>一.原值(1631)：资产类，期末=期初+借方-贷方</li>
        <li>二.累计折耗(1632)：备抵类，期末=期初+贷方-借方</li>
        <li>三.减值准备：备抵类，期末=期初+贷方-借方</li>
        <li>四.净值=原值-累计折耗-减值准备</li>
        <li>三角勾稽：各区块期末=期初+增加-减少，三层均须平衡</li>
        <li>审定数=未审数+AJE+RJE，未审数从TB自动取入(只读)</li>
        <li>"确认审定"将回写trial_balance并发布EventBus事件</li>
        <li>折耗核心方法：单位产量法（产量÷预计可采储量×可折耗金额）</li>
        <li>「带入调整(原值/累计折耗)」：从集中登记按科目 1631/1632 拉取调整分录，逐笔分配到各分类的 AJE/RJE（原值借方净额、折耗贷方净额），带入后审定数自动更新并联动附注</li>
      </ul>
    </details>

    <AdjudicationBringInDialog
      v-model="bringInCostVisible"
      :matches="adjPullCost.matches.value"
      :row-options="bringInCostRowOptions"
      subject-label="1631 油气资产原值"
      :loading="adjPullCost.loading.value"
      @apply="onBringInCostApply"
    />
    <AdjudicationBringInDialog
      v-model="bringInDepletionVisible"
      :matches="adjPullDepletion.matches.value"
      :row-options="bringInDepletionRowOptions"
      subject-label="1632 累计折耗"
      :loading="adjPullDepletion.loading.value"
      @apply="onBringInDepletionApply"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, inject, toRef } from 'vue'
import { MagicStick, Download } from '@element-plus/icons-vue'
import GtIndexChip from '../../GtIndexChip.vue'
import { useH5Adjudication } from '../../composables/useH5Adjudication'
import { useH5FormData } from '../../composables/useH5FormData'
import { useAuditContext } from '@/composables/useAuditContext'
import { useAdjudicationBringIn } from '../../composables/useAdjudicationBringIn'
import AdjudicationBringInDialog from '@/components/adjustment/AdjudicationBringInDialog.vue'
import { eventBus } from '@/utils/eventBus'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})

const allResponsesRef = computed(() => props.allResponses)
const publishing = ref(false)

// FormData composable for save + TB writeback
const formData = useH5FormData({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
})

const state = useH5Adjudication({
  allResponses: allResponsesRef as any,
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  onSave: (itemId: string, value: any) => formData.setResponse(itemId, value),
  onWritebackTB: async (auditedCost: number, auditedDepletion: number) => {
    await formData.writebackTB('1631', auditedCost)
    await formData.writebackTB('1632', auditedDepletion)
  },
  onPublishEvent: (event: string, payload: any) => {
    eventBus.emit(event as any, { ...payload, timestamp: Date.now() })
  },
})

const costDisplayRows = computed(() => {
  const rows = [...state.costRows.value]
  rows.push({ ...state.costSubtotal.value })
  return rows
})

const depletionDisplayRows = computed(() => {
  const rows = [...state.depletionRows.value]
  rows.push({ ...state.depletionSubtotal.value })
  return rows
})

const impairmentDisplayRows = computed(() => {
  const rows = [...state.impairmentRows.value]
  rows.push({ ...state.impairmentSubtotal.value })
  return rows
})

// ─── 从集中登记带入调整（双科目：1631原值[资产借]/1632累计折耗[备抵贷]；减值准备无独立科目码不接） ───
const bringInCostRows = computed(() =>
  state.costRows.value
    .filter((r) => !r.isSubtotal)
    .map((r) => ({ rowKey: r.rowId, name: r.category, aje: r.aje, rje: r.rje })),
)
const {
  adjPull: adjPullCost,
  visible: bringInCostVisible,
  rowOptions: bringInCostRowOptions,
  open: openBringInCost,
  apply: onBringInCostApply,
} = useAdjudicationBringIn({
  projectId: toRef(props, 'projectId') as any,
  year: useAuditContext().year as any,
  subjectPrefix: '1631',
  direction: 'debit',
  subjectCode: '1631',
  wpCode: 'H5',
  subjectLabel: '油气资产原值(1631)',
  rows: bringInCostRows,
  updateCell: (rowKey: string, field: any, value: number) => state.updateCell('cost', rowKey, field, value),
  totalAudited: () => state.costSubtotal.value.audited,
})

const bringInDepletionRows = computed(() =>
  state.depletionRows.value
    .filter((r) => !r.isSubtotal)
    .map((r) => ({ rowKey: r.rowId, name: r.category, aje: r.aje, rje: r.rje })),
)
const {
  adjPull: adjPullDepletion,
  visible: bringInDepletionVisible,
  rowOptions: bringInDepletionRowOptions,
  open: openBringInDepletion,
  apply: onBringInDepletionApply,
} = useAdjudicationBringIn({
  projectId: toRef(props, 'projectId') as any,
  year: useAuditContext().year as any,
  subjectPrefix: '1632',
  direction: 'credit',
  subjectCode: '1632',
  wpCode: 'H5',
  subjectLabel: '累计折耗(1632)',
  rows: bringInDepletionRows,
  updateCell: (rowKey: string, field: any, value: number) => state.updateCell('depletion', rowKey, field, value),
  totalAudited: () => state.depletionSubtotal.value.audited,
})

type BlockType = 'cost' | 'depletion' | 'impairment'

function onCellChange(block: BlockType, rowId: string, field: string, value: number) {
  state.updateCell(block, rowId, field as any, value ?? 0)
}

async function handlePublish() {
  publishing.value = true
  try {
    await state.publishAdjudicated()
  } finally {
    publishing.value = false
  }
}


function handleReview(id: string) {
  openReviewDialog(id)
}

function fmtAmt(val: number | null | undefined): string {
  if (val == null) return '-'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.h5-tab-adjudication { padding: 16px; font-size: var(--wp-font-size, 13px); }
.objective-alert { margin-bottom: 12px; }
.tab-toolbar { display: flex; justify-content: flex-end; align-items: center; margin-bottom: 8px; }
.toolbar-right { display: flex; gap: 6px; align-items: center; }
.chip-wrap { display: inline-flex; align-items: center; }
.block-card { margin-bottom: 16px; }
.section-title { display: flex; align-items: center; justify-content: space-between; }
.title-actions { display: flex; gap: 8px; }
.adj-table { font-size: var(--wp-font-size, 13px); }
.amount-input { width: 100%; }
.amount-cell { font-variant-numeric: tabular-nums; }
.tb-auto { color: var(--el-text-color-secondary); font-style: italic; }
.formula-cell {
  font-variant-numeric: tabular-nums;
  border-bottom: 1px dashed var(--el-border-color);
  cursor: help;
}
.net-value-row { font-size: 14px; font-weight: 500; padding: 8px 0; }
.reconciliation-card { margin-bottom: 16px; }
.reconcile-ok { color: var(--el-color-success); font-size: 16px; font-weight: 700; }
.reconcile-warn { color: var(--el-color-warning); font-size: 16px; font-weight: 700; }
.error-amount { color: var(--el-color-danger); font-weight: 600; }
.cross-warning { margin-top: 12px; }
.note-card { margin-bottom: 16px; }
.action-bar { margin: 16px 0; display: flex; gap: 12px; }
.compile-hint { margin-top: 12px; font-size: 12px; color: var(--el-text-color-secondary); }
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ul { padding-left: 20px; margin-top: 8px; }
</style>
