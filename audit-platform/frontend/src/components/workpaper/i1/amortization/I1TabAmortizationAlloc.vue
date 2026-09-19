<template>
  <div class="i1-tab-amort-alloc">
    <!-- 审计目标（对齐 Excel 一、审计目标） -->
    <el-alert type="info" :closable="false" show-icon class="objective-alert">
      <template #title>
        审计目标：检查无形资产本期摊销费用分配是否合理；核实累计摊销贷方发生额与各成本/费用科目借方摊销是否勾稽一致。
      </template>
    </el-alert>

    <div class="methodology-context">
      <p>
        <strong>编制逻辑（跨科目核对表）：</strong>
        行=无形资产（自 I1-10/11 带入），列=费用科目（对齐 Excel：生产成本/制造费用/销售费用/管理费用/研发费用/其他）。
        横向：各行分配合计须等于该资产本期摊销总额；纵向：列合计供 D5/K8/K9/I6 对方底稿取数核对。
      </p>
      <p>
        核对方法：累计摊销(1702)贷方本期发生额 ≈ 生产成本+制造费用+销售费用+管理费用+研发费用等借方「无形资产摊销」之和。
      </p>
    </div>

    <!-- 审计过程（对齐 Excel 二、审计过程） -->
    <details class="procedure-details" open>
      <summary>二、审计过程</summary>
      <ol>
        <li>
          检查摊销费用的分配：将累计摊销科目的本期贷方发生额与相应的成本费用明细账的借方发生额进行比较，
          查明计入本期产品成本或费用的摊销额是否正确、完整。
        </li>
        <li>判断摊销费用的分配是否合理，是否与上期一致。</li>
      </ol>
    </details>

    <!-- 工具栏 -->
    <div class="tab-toolbar">
      <div class="toolbar-left">
        <el-segmented
          v-model="matrixView"
          size="small"
          :options="[
            { label: '按资产', value: 'asset' },
            { label: '按类别汇总', value: 'category' },
          ]"
        />
        <el-button size="small" type="primary" :disabled="isReadonly || matrixView !== 'asset'" @click="handleAddRow">
          + 新增资产行
        </el-button>
        <el-dropdown :disabled="isReadonly || matrixView !== 'asset'" @command="handleAllocateAll">
          <el-button size="small" :disabled="isReadonly || matrixView !== 'asset'">
            差额一键计入 <span class="caret">▾</span>
          </el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item v-for="col in expenseCols" :key="col.field" :command="col.field">
                {{ col.label }}
              </el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <el-dropdown trigger="click" @command="handleImportExport">
          <el-button size="small" :loading="ieBusy">导入导出 ▾</el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="exportTemplate">导出模板</el-dropdown-item>
              <el-dropdown-item command="exportData">导出数据</el-dropdown-item>
              <el-dropdown-item command="importData" :disabled="isReadonly">导入数据</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <input ref="fileInputRef" type="file" accept=".xlsx,.xls" style="display:none" @change="onFileSelected" />
        <el-tag size="small" :type="isBalancedWithSource ? 'success' : 'danger'">
          {{
            isBalancedWithSource
              ? `分配合计 = ${sourceSheetLabel || 'I1-10/11'}`
              : `与${sourceSheetLabel || 'I1-10/11'}差异 ${fmtAmt(vsSourceDiff)}`
          }}
        </el-tag>
        <el-tag v-if="unbalancedCount > 0" size="small" type="warning">
          {{ unbalancedCount }} 行未配平
        </el-tag>
      </div>
      <div class="toolbar-right">
        <span class="chip-wrap"><GtIndexChip value="wp:I1-9" :context-project-id="projectId" /></span>
        <el-tag size="small" type="info">共 {{ rows.length }} 行</el-tag>
        <el-tag size="small" class="nav-chip" @click="navigateTo(sourceSheetLabel || 'I1-10')">
          ← {{ sourceSheetLabel || 'I1-10' }}
        </el-tag>
      </div>
    </div>

    <!-- 主矩阵表 -->
    <el-card shadow="never">
      <template #header>
        <div class="section-title">
          <span>{{ matrixView === 'category' ? '按类别汇总（只读）' : '无形资产摊销费用分配分析' }}</span>
          <span class="source-hint">
            {{ sourceSheetLabel || 'I1-10/11' }} 摊销总额：
            <b class="formula-value">{{ fmtAmt(sourceAmortTotal) }}</b>
          </span>
        </div>
      </template>

      <!-- 类别汇总视图 -->
      <el-table
        v-if="matrixView === 'category'"
        :data="categorySummaryRows"
        border
        stripe
        size="small"
        class="alloc-table"
      >
        <el-table-column prop="category" label="资产类别" min-width="140" fixed />
        <el-table-column prop="assetCount" label="资产数" width="80" align="center" />
        <el-table-column label="摊销总额" min-width="110" align="right" fixed>
          <template #default="{ row }">
            <span class="formula-value">{{ fmtAmt(row.totalAmort) }}</span>
          </template>
        </el-table-column>
        <el-table-column
          v-for="col in expenseCols"
          :key="col.field"
          :label="col.label"
          min-width="110"
          align="right"
        >
          <template #default="{ row }">
            <span class="formula-value">{{ fmtAmt((row as any)[col.field]) }}</span>
          </template>
        </el-table-column>
      </el-table>

      <el-table
        v-else
        :data="displayRows"
        border
        stripe
        size="small"
        class="alloc-table"
        :row-class-name="getRowClassName"
      >
        <el-table-column type="index" width="44" label="序号" fixed />

        <el-table-column prop="name" label="无形资产名称" min-width="140" fixed>
          <template #default="{ row }">
            <span v-if="row._isSummary" class="summary-text">合计</span>
            <span v-else>{{ row.name || '—' }}</span>
          </template>
        </el-table-column>

        <el-table-column label="摊销总额" min-width="110" align="right" fixed>
          <template #header>
            <el-tooltip :content="`来自摊销测算表(${sourceSheetLabel || 'I1-10/I1-11'})，只读`" placement="top">
              <span class="formula-col-header">摊销总额</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <span class="formula-value">{{ fmtAmt(row.totalAmort) }}</span>
          </template>
        </el-table-column>

        <el-table-column
          v-for="col in expenseCols"
          :key="col.field"
          :label="col.label"
          min-width="110"
          align="right"
        >
          <template #header>
            <el-tooltip :content="colHeaderTip(col)" placement="top">
              <span class="formula-col-header">{{ col.label }}</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <el-input-number
              v-if="!row._isSummary && !isReadonly"
              v-model="(row as any)[col.field]"
              :controls="false"
              size="small"
              @change="onCellChange(row, col.field, (row as any)[col.field])"
            />
            <span v-else class="formula-value">{{ fmtAmt((row as any)[col.field]) }}</span>
          </template>
        </el-table-column>

        <el-table-column label="合计" min-width="110" align="right" fixed="right">
          <template #header>
            <el-tooltip content="合计 = 各费用列之和，须等于该行摊销总额" placement="top">
              <span class="formula-col-header">合计</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <el-tooltip
              :content="getRowBalanceTooltip(row)"
              :disabled="row._isSummary || isRowBalanced(row)"
              placement="top"
            >
              <span :class="['formula-value', { 'alloc-error': !row._isSummary && !isRowBalanced(row) }]">
                {{ fmtAmt(calcRowAllocSum(row)) }}
              </span>
            </el-tooltip>
          </template>
        </el-table-column>

        <el-table-column label="未分配" min-width="100" align="right" fixed="right">
          <template #header>
            <el-tooltip content="未分配 = 摊销总额 − 合计（须为 0）" placement="top">
              <span class="formula-col-header">未分配</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <span
              v-if="row._isSummary"
              :class="['formula-value', { 'alloc-error': Math.abs(vsSourceDiff) >= 0.01 }]"
            >
              {{ fmtAmt(vsSourceDiff) }}
            </span>
            <span
              v-else
              :class="['formula-value', { 'alloc-error': Math.abs(calcRowRemainder(row)) >= 0.01 }]"
            >
              {{ fmtAmt(calcRowRemainder(row)) }}
            </span>
          </template>
        </el-table-column>

        <el-table-column label="分配比例" min-width="90" align="right">
          <template #header>
            <el-tooltip content="分配比例 = 该行合计 ÷ 摊销总额合计 × 100%" placement="top">
              <span class="formula-col-header">分配比例</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <span class="formula-value">{{ fmtPercent(row) }}</span>
          </template>
        </el-table-column>

        <el-table-column prop="remark" label="备注" min-width="100">
          <template #default="{ row }">
            <span v-if="row._isSummary">—</span>
            <el-input
              v-else-if="!isReadonly"
              v-model="row.remark"
              size="small"
              placeholder="用途/部门"
              @change="onCellChange(row, 'remark', row.remark)"
            />
            <span v-else>{{ row.remark || '—' }}</span>
          </template>
        </el-table-column>

        <el-table-column v-if="!isReadonly" label="操作" width="50" fixed="right">
          <template #default="{ row }">
            <el-button
              v-if="!row._isSummary"
              size="small"
              type="danger"
              link
              @click="removeRow(row.rowId)"
            >删</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 跨科目勾稽核对 -->
    <el-card shadow="never" class="verify-card">
      <template #header>
        <div class="section-title">
          <span>跨科目勾稽核对</span>
          <span class="verify-hint">
            {{ counterpartPulledAt ? `上次拉取：${fmtTime(counterpartPulledAt)}` : '尚未拉取对方底稿数' }}
          </span>
          <div class="verify-actions">
            <el-button
              size="small"
              type="primary"
              plain
              :loading="pullingCounterpart"
              :disabled="!projectId"
              data-testid="i1-9-refresh-counterpart"
              @click="handleRefreshCounterpart"
            >
              刷新对方底稿数
            </el-button>
            <el-button
              size="small"
              type="warning"
              plain
              :loading="pushingExpense"
              :disabled="isReadonly || !projectId"
              data-testid="i1-9-push-expense"
              @click="handlePushToExpense"
            >
              回写 D5/K8/K9/I6
            </el-button>
          </div>
        </div>
      </template>
      <el-table :data="reconciliationRows" size="small" border>
        <el-table-column prop="label" label="核对项" min-width="180" />
        <el-table-column label="本表分配数" width="130" align="right">
          <template #default="{ row }">
            <span class="formula-value">{{ fmtAmt(row.calculated) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="对方底稿数" width="140" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!isReadonly && row.field"
              :model-value="row.counterpart ?? undefined"
              :controls="false"
              size="small"
              placeholder="手工录入"
              @change="(v: number | undefined) => onCounterpartChange(row.field, v)"
            />
            <span v-else class="formula-value">
              {{ row.counterpart == null ? '—' : fmtAmt(row.counterpart) }}
              <el-tag v-if="row.isManual" size="small" type="warning" class="manual-tag">手工</el-tag>
            </span>
          </template>
        </el-table-column>
        <el-table-column label="差异" width="110" align="right">
          <template #default="{ row }">
            <span
              v-if="row.difference != null"
              :class="['formula-value', { 'alloc-error': Math.abs(row.difference) > 0.01 }]"
            >{{ fmtAmt(row.difference) }}</span>
            <span v-else class="muted">—</span>
          </template>
        </el-table-column>
        <el-table-column label="勾稽状态" min-width="200">
          <template #default="{ row }">
            <span :class="{ 'alloc-error': row.difference != null && Math.abs(row.difference) > 0.01 }">
              {{ row.statusText }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="跳转" width="90" align="center">
          <template #default="{ row }">
            <GtIndexChip
              v-if="row.targetWpCode"
              :value="`wp:${row.targetWpCode}`"
              :context-project-id="projectId"
            />
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 上期一致性（Excel 审计过程第2点） -->
    <el-card shadow="never" class="prior-card">
      <template #header><span>分配方法与上期一致性</span></template>
      <div class="prior-row">
        <el-radio-group
          :model-value="priorConsistent"
          :disabled="isReadonly"
          @change="(v: string | number | boolean | undefined) => onPriorConsistentChange(String(v ?? ''))"
        >
          <el-radio value="Y">与上期一致</el-radio>
          <el-radio value="N">与上期不一致</el-radio>
        </el-radio-group>
        <el-input
          v-model="priorNoteLocal"
          class="prior-note"
          size="small"
          :disabled="isReadonly"
          placeholder="说明分配政策/用途依据；若不一致请说明原因及合理性"
          @change="savePrior"
        />
      </div>
    </el-card>

    <!-- 审计说明 / 结论 -->
    <el-card shadow="never" class="audit-note-card">
      <template #header><div class="card-header"><span>三、审计说明</span></div></template>
      <el-input
        type="textarea"
        :model-value="auditNote"
        :disabled="isReadonly"
        :autosize="{ minRows: 5 }"
        placeholder="填写审计说明：摊销费用分配依据（用途/部门）、与 I1-10/11 测算及 D5/K8/K9/I6 勾稽情况、分配方法与上期是否一致、重大异常及追加程序。"
        @change="saveAuditNote"
      />
    </el-card>

    <el-card shadow="never" class="audit-note-card">
      <template #header>
        <div class="card-header">
          <span>四、审计结论</span>
          <el-button size="small" type="primary" link :disabled="isReadonly" @click="handlePublish">
            📤 发布摊销分配
          </el-button>
        </div>
      </template>
      <el-input
        type="textarea"
        :model-value="auditConclusion"
        :disabled="isReadonly"
        :autosize="{ minRows: 3 }"
        placeholder="填写审计结论：摊销费用分配合理、行/列勾稽一致，分配方法与上期一致，未见异常等。"
        @change="saveAuditConclusion"
      />
    </el-card>

    <div class="jump-targets">
      <span class="jump-label">跨底稿联动：</span>
      <GtIndexChip :value="`wp:${sourceSheetLabel || 'I1-10'}`" :context-project-id="projectId" />
      <GtIndexChip value="wp:D5" :context-project-id="projectId" />
      <GtIndexChip value="wp:K8" :context-project-id="projectId" />
      <GtIndexChip value="wp:K9" :context-project-id="projectId" />
      <GtIndexChip value="wp:I6" :context-project-id="projectId" />
    </div>

    <!-- Excel 脚注 -->
    <div class="excel-footnotes">
      <p>注1：通过非同一控制下企业合并的购买日公允价值（PPA）形成的无形资产，亦须按规定摊销。</p>
      <p>注2：自行研发形成的无形资产，其摊销通常计入研发费用；请核对用途与费用归属是否一致。</p>
    </div>

    <details class="compile-hint">
      <summary>编制提示</summary>
      <ul>
        <li>摊销总额列来自 I1-10/I1-11 本期摊销合计，按资产名称自动同步，不可手改</li>
        <li>横向：各费用列之和必须等于该行摊销总额，否则红色警示；可用「差额一键计入」快速配平</li>
        <li>纵向：生产成本/制造费用→D5、销售费用→K8、管理费用→K9、研发费用→I6</li>
        <li>点「刷新对方底稿数」从对方明细「无形资产摊销」行反向回填；取不到时可手工覆盖</li>
        <li>点「回写 D5/K8/K9/I6」或「发布摊销分配」时，将列合计写入对方底稿明细（checklist 持久化；EventBus 仅作在线即时通知）</li>
        <li>评估分配方法是否合理且与上期一致；办公软件→管理费用，生产相关专利→生产成本/制造费用，自研→研发费用</li>
        <li>发布后写出 I1-9-alloc-totals，供对方底稿 =WP('I1','摊销分配分析表I1-9','销售费用摊销') 等取数</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * I1TabAmortizationAlloc.vue — I1-9 摊销分配分析表
 *
 * 对齐 Excel 模板：目标 → 过程 → 费用分配矩阵 → 说明/结论 + PPA/自研脚注
 * 上游：I1-10/I1-11；下游：D5/K8/K9/I6
 *
 * Spec: .kiro/specs/i1-intangible-assets/ | Requirements: 10.1-10.4
 */
import { ref, computed, toRef, watch, onMounted } from 'vue'
import { ElMessageBox, ElMessage } from 'element-plus'
import GtIndexChip from '../../GtIndexChip.vue'
import {
  useI1AmortizationAlloc,
  I1_EXPENSE_COLS,
  I1_ALLOC_NOTE_KEY,
  I1_ALLOC_CONCLUSION_KEY,
  type I1AllocRow,
  type I1ExpenseColMeta,
  type I1ExpenseField,
  type I1PriorConsistency,
} from '../../composables/useI1AmortizationAlloc'
import { useI1ImportExport } from '../../composables/useI1ImportExport'
import {
  pullI1AmortAllocCounterparts,
  pushI1AmortToExpenseWps,
} from '../../composables/i1AmortAllocCounterpartPull'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
  /** Record<assetName, periodAmortTotal>；缺省时 composable 自 allResponses 解析 */
  amortizationByAsset?: Record<string, number>
}>()

const emit = defineEmits<{
  'navigate-sheet': [sheetName: string]
  'save': [itemId: string, value: any]
}>()

const allResponsesRef = toRef(props, 'allResponses')
const amortByAssetRef = computed(() => props.amortizationByAsset)

const auditNote = ref('')
const auditConclusion = ref('')
const priorNoteLocal = ref('')
const matrixView = ref<'asset' | 'category'>('asset')
const pullingCounterpart = ref(false)
const pushingExpense = ref(false)

function loadAuditText(): void {
  const n = props.allResponses.get(I1_ALLOC_NOTE_KEY)
  if (n) auditNote.value = (n.remark ?? n.conclusion ?? '') as string
  const c = props.allResponses.get(I1_ALLOC_CONCLUSION_KEY)
  if (c) auditConclusion.value = (c.remark ?? c.conclusion ?? '') as string
}

watch(() => props.allResponses, () => loadAuditText(), { immediate: true })

const {
  rows,
  displayRows,
  sourceAmortTotal,
  sourceSheetLabel,
  vsSourceDiff,
  isBalancedWithSource,
  unbalancedCount,
  reconciliationRows,
  counterpartPulledAt,
  setCounterpartManual,
  applyCounterpartPull,
  categorySummaryRows,
  priorConsistent,
  priorNote,
  savePriorAssessment,
  updateCell,
  addRow,
  removeRow,
  allocateAllRemaindersTo,
  publishAllocated,
  colTotals,
  calcRowAllocSum,
  isRowBalanced,
  calcRowRemainder,
  fmtPercent,
  expenseCols,
} = useI1AmortizationAlloc({
  allResponses: allResponsesRef,
  amortizationByAsset: amortByAssetRef,
  onSave(itemId, value) {
    emit('save', itemId, value)
  },
  onPublishEvent(event, payload) {
    try {
      window.dispatchEvent(new CustomEvent(event, { detail: payload }))
    } catch {
      // ignore
    }
  },
})

watch(priorNote, (v) => { priorNoteLocal.value = v }, { immediate: true })

const { exportTemplate, exportData, importData, exporting, importing } = useI1ImportExport({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
})
const ieBusy = computed(() => exporting.value || importing.value)
const fileInputRef = ref<HTMLInputElement | null>(null)

function colHeaderTip(col: I1ExpenseColMeta): string {
  if (col.targetWpCode) return `计入${col.label}（${col.targetWpCode}）的摊销额`
  return `计入${col.label}的摊销额`
}

function getRowBalanceTooltip(row: I1AllocRow): string {
  if (row._isSummary || isRowBalanced(row)) return ''
  const sum = calcRowAllocSum(row)
  const diff = sum - row.totalAmort
  return `分配合计(${fmtAmt(sum)}) ≠ 摊销总额(${fmtAmt(row.totalAmort)})，差额: ${fmtAmt(diff)}`
}

function getRowClassName({ row }: { row: I1AllocRow }): string {
  if (row._isSummary) return 'summary-row'
  if (!isRowBalanced(row)) return 'error-row'
  return ''
}

function onCellChange(row: I1AllocRow, field: string, value: unknown): void {
  updateCell(row, field as keyof I1AllocRow, value)
}

function onCounterpartChange(field: string | undefined, v: number | undefined): void {
  if (!field) return
  setCounterpartManual(field as I1ExpenseField, v == null ? null : Number(v))
}

function onPriorConsistentChange(v: string): void {
  const consistent = (v === 'Y' || v === 'N' ? v : '') as I1PriorConsistency
  savePriorAssessment(consistent, priorNoteLocal.value)
}

function savePrior(): void {
  savePriorAssessment(priorConsistent.value, priorNoteLocal.value)
}

function saveAuditNote(val: string): void {
  if (props.isReadonly) return
  auditNote.value = val
  emit('save', I1_ALLOC_NOTE_KEY, val)
}

function saveAuditConclusion(val: string): void {
  if (props.isReadonly) return
  auditConclusion.value = val
  emit('save', I1_ALLOC_CONCLUSION_KEY, val)
}

async function handleAddRow(): Promise<void> {
  try {
    const { value: name } = await ElMessageBox.prompt(
      '请输入资产名称（建议与 I1-10/I1-11 摊销测算表资产名一致）',
      '新增资产行',
      {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        inputPattern: /\S+/,
        inputErrorMessage: '资产名称不能为空',
      },
    )
    if (!name) return
    addRow(name)
    ElMessage.success(`已新增资产行: ${name}`)
  } catch {
    // cancelled
  }
}

function handleAllocateAll(field: I1ExpenseField): void {
  const n = allocateAllRemaindersTo(field)
  if (!n) ElMessage.info('各行已配平，无需计入')
  else ElMessage.success(`已将 ${n} 行未分配差额计入「${I1_EXPENSE_COLS.find((c) => c.field === field)?.label}」`)
}

function handlePublish(): void {
  publishAllocated()
  void handlePushToExpense(true)
  ElMessage.success('已发布摊销分配（I1-9-alloc-totals + i1:amortization-allocated）')
}

async function handleRefreshCounterpart(): Promise<void> {
  if (!props.projectId) return
  pullingCounterpart.value = true
  try {
    const pulled = await pullI1AmortAllocCounterparts(props.projectId)
    applyCounterpartPull(pulled)
    const ok = Object.values(pulled).filter((p) => p.status === 'ok').length
    ElMessage.success(`已刷新对方底稿数（成功 ${ok}/${Object.keys(pulled).length}）`)
  } catch {
    ElMessage.error('拉取对方底稿数失败')
  } finally {
    pullingCounterpart.value = false
  }
}

async function handlePushToExpense(silent = false): Promise<void> {
  if (!props.projectId || props.isReadonly) return
  pushingExpense.value = true
  try {
    const t = colTotals.value
    const result = await pushI1AmortToExpenseWps(props.projectId, {
      productionManufacturing: t.productionCost + t.manufacturingCost,
      selling: t.sellingExpense,
      management: t.managementExpense,
      rd: t.rdExpense,
    })
    if (!silent) {
      if (result.ok > 0) ElMessage.success(`已回写 ${result.ok} 个对方底稿`)
      else ElMessage.warning(result.messages.slice(0, 2).join('；') || '未回写任何底稿')
    }
  } catch {
    if (!silent) ElMessage.error('回写对方底稿失败')
  } finally {
    pushingExpense.value = false
  }
}

onMounted(() => {
  if (!counterpartPulledAt.value && props.projectId) {
    void handleRefreshCounterpart()
  }
})

async function handleImportExport(command: string): Promise<void> {
  try {
    if (command === 'exportTemplate') await exportTemplate('I1-9')
    else if (command === 'exportData') await exportData('I1-9')
    else if (command === 'importData') fileInputRef.value?.click()
  } catch {
    // errors surfaced by composable
  }
}

async function onFileSelected(ev: Event): Promise<void> {
  const input = ev.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) return
  await importData('I1-9', file)
}

function navigateTo(wpCode: string): void {
  emit('navigate-sheet', wpCode)
}

function fmtAmt(val: number | null | undefined): string {
  if (val == null) return '—'
  if (Math.abs(val) < 0.005) return '—'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function fmtTime(iso: string): string {
  try {
    return new Date(iso).toLocaleString('zh-CN')
  } catch {
    return iso
  }
}
</script>

<style scoped>
.i1-tab-amort-alloc {
  padding: 16px;
  font-size: var(--wp-font-size, 13px);
}

.methodology-context {
  border-left: 4px solid #d97706;
  background: #fffbeb;
  padding: 12px 16px;
  margin-bottom: 12px;
  border-radius: 4px;
  font-size: 12px;
  color: #92400e;
  line-height: 1.8;
}
.methodology-context p { margin: 0; }
.methodology-context strong { color: #78350f; }

.objective-alert { margin-bottom: 12px; }

.procedure-details {
  margin-bottom: 12px;
  font-size: 12px;
  color: var(--el-text-color-regular);
  background: #f8fafc;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 4px;
  padding: 8px 12px;
}
.procedure-details summary {
  cursor: pointer;
  font-weight: 600;
  margin-bottom: 4px;
}
.procedure-details ol {
  margin: 6px 0 0;
  padding-left: 20px;
  line-height: 1.8;
}

.tab-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 12px;
  flex-wrap: wrap;
}
.toolbar-left,
.toolbar-right {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.chip-wrap { display: inline-flex; align-items: center; }
.caret { font-size: 10px; margin-left: 2px; }
.nav-chip { cursor: pointer; }

.section-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  font-weight: 500;
}
.source-hint,
.verify-hint {
  font-size: 12px;
  font-weight: 400;
  color: var(--el-text-color-secondary);
}
.verify-actions { display: flex; gap: 8px; flex-wrap: wrap; }

.audit-note-card,
.verify-card,
.prior-card { margin-top: 16px; }
.audit-note-card .card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-weight: 500;
}

.prior-row {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}
.prior-note { flex: 1; min-width: 220px; }

.alloc-table {
  font-size: var(--wp-font-size, 13px);
}
.alloc-table :deep(.el-table__header th) {
  font-size: 12px;
  font-weight: 600;
  background: #f8fafc;
}
.alloc-table :deep(.el-input-number) { width: 100%; }
.alloc-table :deep(.el-input-number .el-input__inner) { text-align: right; }

.formula-col-header {
  border-bottom: 1px dashed var(--el-border-color);
  cursor: help;
  padding-bottom: 2px;
}
.formula-value { font-variant-numeric: tabular-nums; }

.summary-text { font-weight: 700; }
:deep(.summary-row),
:deep(.summary-row td) {
  background: #f0fdf4 !important;
  font-weight: 600;
}

.alloc-error {
  color: var(--el-color-danger);
  font-weight: 700;
}
:deep(.error-row),
:deep(.error-row td) {
  background: #fef2f2 !important;
}

.jump-targets {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 12px;
  flex-wrap: wrap;
}
.jump-label {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.excel-footnotes {
  margin-top: 12px;
  font-size: 12px;
  color: #1d4ed8;
  line-height: 1.7;
}
.excel-footnotes p { margin: 0; }

.compile-hint {
  margin-top: 12px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  border-top: 1px solid var(--el-border-color-lighter);
  padding-top: 12px;
}
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ul {
  padding-left: 20px;
  margin-top: 8px;
  line-height: 1.8;
}

.muted { color: var(--el-text-color-secondary); }
.manual-tag { margin-left: 4px; }
</style>
