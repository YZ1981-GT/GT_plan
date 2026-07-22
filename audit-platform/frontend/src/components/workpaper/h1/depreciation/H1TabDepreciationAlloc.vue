<template>
  <div class="h1-tab-dep-alloc">
    <!-- 审计目标 -->
    <el-alert type="info" :closable="false" show-icon class="obj-alert">
      <template #title>
        审计目标：确认固定资产折旧已按资产类别与用途合理分配至生产成本、制造费用、销售费用、管理费用、研发费用等科目；
        分配合计与 H1-12 折旧测算一致，并与 F5/F2/K8/K9/I6 等对方科目底稿勾稽。
      </template>
    </el-alert>

    <div class="methodology-context">
      <p>
        <strong>编制逻辑（跨科目核对表）：</strong>
        行=固定资产类别，列=费用科目。横向：各类分配合计须等于 H1-12 该类折旧；
        纵向：各费用列合计供对方底稿 <code>=WP('H1','折旧分配分析表H1-13','××折旧')</code> 取数核对。
      </p>
    </div>

    <!-- 工具栏 -->
    <div class="tab-toolbar">
      <div class="toolbar-left">
        <el-button size="small" type="primary" :disabled="isReadonly" @click="handleAddRow">+ 新增类别</el-button>
        <el-button size="small" type="warning" plain :disabled="isReadonly || isBalancedWithH12" @click="handleWriteBackH12">
          未配平差额回写 H1-12
        </el-button>
        <el-button size="small" type="default" link @click="handleReview('H1-13')">💬 复核</el-button>
        <el-tag size="small" :type="isBalancedWithH12 ? 'success' : 'danger'">
          {{ isBalancedWithH12 ? '分配合计 = H1-12' : `与H1-12差异 ${fmtAmt(vsH12Diff)}` }}
        </el-tag>
      </div>
      <div class="toolbar-right">
        <GtIndexChip value="wp:H1-13" :context-project-id="projectId" />
        <el-tag size="small" type="info">共 {{ rows.length }} 类</el-tag>
      </div>
    </div>

    <!-- 主矩阵表 -->
    <el-card shadow="never">
      <template #header>
        <div class="section-title">
          <span>H1-13 固定资产折旧分配分析表</span>
          <span class="h12-hint">
            H1-12 折旧总额：<b class="amount-cell">{{ fmtAmt(h12DepTotal) }}</b>
          </span>
        </div>
      </template>

      <el-table
        :data="displayRows"
        border
        stripe
        size="small"
        class="alloc-table"
        :row-class-name="getRowClassName"
      >
        <el-table-column type="index" width="44" label="序号" />

        <el-table-column prop="category" label="固定资产类别" min-width="130">
          <template #default="{ row }">
            <span v-if="row._isSummary || row._isReconcile" class="summary-text">{{ row.category }}</span>
            <el-input
              v-else-if="!isReadonly"
              v-model="row.category"
              size="small"
              @change="onCellChange(row, 'category', row.category)"
            />
            <span v-else>{{ row.category }}</span>
          </template>
        </el-table-column>

        <el-table-column label="折旧总额" width="120" align="right">
          <template #header>
            <el-tooltip content="来自 H1-12 按分类聚合的本期折旧，只读" placement="top">
              <span class="formula-col-header">折旧总额</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <span v-if="row._isReconcile" class="recon-cell">
              <GtIndexChip value="wp:H1-12" :context-project-id="projectId" />
            </span>
            <span v-else class="formula-cell">{{ fmtAmt(row.depTotal) }}</span>
          </template>
        </el-table-column>

        <!-- 费用科目列 -->
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
            <span v-if="row._isReconcile" class="recon-cell">
              <template v-if="col.targetWpCode">
                <span class="recon-text">勾稽一致，详见</span>
                <GtIndexChip :value="`wp:${col.targetWpCode}`" :context-project-id="projectId" />
              </template>
              <span v-else class="recon-text">—</span>
            </span>
            <el-input-number
              v-else-if="!row._isSummary && !isReadonly"
              v-model="(row as any)[col.field]"
              :controls="false"
              size="small"
              @change="onCellChange(row, col.field, (row as any)[col.field])"
            />
            <span v-else class="amount-cell">{{ fmtAmt((row as any)[col.field]) }}</span>
          </template>
        </el-table-column>

        <el-table-column label="合计" width="120" align="right">
          <template #header>
            <el-tooltip content="合计 = 各费用列之和，须等于该行折旧总额" placement="top">
              <span class="formula-col-header">合计</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <span v-if="row._isReconcile" class="recon-text">—</span>
            <el-tooltip
              v-else
              :content="rowBalanceTip(row)"
              :disabled="row._isSummary || isRowBalanced(row)"
              placement="top"
            >
              <span :class="['formula-cell', { 'error-amount': !row._isSummary && !isRowBalanced(row) }]">
                {{ fmtAmt(calcRowAllocSum(row)) }}
              </span>
            </el-tooltip>
          </template>
        </el-table-column>

        <el-table-column prop="remark" label="备注" min-width="100">
          <template #default="{ row }">
            <span v-if="row._isSummary || row._isReconcile">—</span>
            <el-input
              v-else-if="!isReadonly"
              v-model="row.remark"
              size="small"
              @change="onCellChange(row, 'remark', row.remark)"
            />
            <span v-else>{{ row.remark }}</span>
          </template>
        </el-table-column>

        <el-table-column label="操作" width="50" v-if="!isReadonly">
          <template #default="{ row }">
            <el-button
              v-if="!row._isSummary && !row._isReconcile"
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
          <div class="title-actions">
            <span class="verify-hint">
              {{ counterpartPulledAt ? `上次拉取：${fmtTime(counterpartPulledAt)}` : '尚未拉取对方底稿数' }}
            </span>
            <el-button
              size="small"
              type="primary"
              plain
              :loading="pulling"
              :disabled="isReadonly"
              @click="handleRefreshCounterparts"
            >
              刷新对方底稿数
            </el-button>
            <el-button
              size="small"
              type="warning"
              plain
              :disabled="isReadonly || !counterpartPulledAt"
              @click="handleWriteCounterpartDiff"
            >
              差异写入审计说明
            </el-button>
          </div>
        </div>
      </template>
      <el-table :data="reconciliationRows" size="small" border>
        <el-table-column prop="label" label="核对项" min-width="160" />
        <el-table-column label="本表分配数" width="130" align="right">
          <template #default="{ row }">
            <span class="amount-cell">{{ fmtAmt(row.calculated) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="对方底稿数" width="130" align="right">
          <template #default="{ row }">
            <span class="amount-cell">{{ row.counterpart == null ? '待拉取' : fmtAmt(row.counterpart) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="差异" width="110" align="right">
          <template #default="{ row }">
            <span
              v-if="row.difference != null"
              :class="['amount-cell', { 'error-amount': Math.abs(row.difference) > 0.01 }]"
            >{{ fmtAmt(row.difference) }}</span>
            <span v-else class="muted">—</span>
          </template>
        </el-table-column>
        <el-table-column label="勾稽状态" min-width="180">
          <template #default="{ row }">
            <span :class="{ 'error-amount': row.difference != null && Math.abs(row.difference) > 0.01 }">
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

    <!-- 审计说明 -->
    <el-card shadow="never" class="note-card">
      <template #header><span>审计说明</span></template>
      <el-input
        v-model="auditNoteText"
        type="textarea"
        :autosize="{ minRows: 5 }"
        :disabled="isReadonly"
        placeholder="填写审计说明：分配依据（用途/部门）、与 H1-12 测算及 F5/F2/K8/K9/I6 勾稽情况、重大异常及追加程序。"
        @change="saveAuditNote"
      />
    </el-card>

    <el-card shadow="never" class="note-card">
      <template #header>
        <div class="section-title">
          <span>审计结论</span>
          <div class="title-actions">
            <el-button size="small" type="primary" link :disabled="isReadonly" @click="publishAllocated">
              📤 发布折旧分配
            </el-button>
          </div>
        </div>
      </template>
      <el-input
        v-model="conclusion"
        type="textarea"
        :autosize="{ minRows: 3 }"
        :disabled="isReadonly"
        placeholder="填写审计结论：折旧分配合理、行/列勾稽一致，未见异常等。"
        @change="saveAllocConclusion"
      />
    </el-card>

    <div class="jump-targets">
      <span class="jump-label">跨底稿联动：</span>
      <GtIndexChip value="wp:H1-12" :context-project-id="projectId" />
      <GtIndexChip value="wp:F5" :context-project-id="projectId" />
      <GtIndexChip value="wp:F2" :context-project-id="projectId" />
      <GtIndexChip value="wp:K8" :context-project-id="projectId" />
      <GtIndexChip value="wp:K9" :context-project-id="projectId" />
      <GtIndexChip value="wp:I6" :context-project-id="projectId" />
    </div>

    <details class="compile-hint">
      <summary>编制提示</summary>
      <ul>
        <li>折旧总额列由 H1-12 按固定资产类别自动带入，不可手改</li>
        <li>横向：各费用列之和必须等于该行折旧总额，否则红色警示</li>
        <li>纵向：生产成本→F5、制造费用→F2、销售费用→K8、管理费用→K9、研发费用→I6</li>
        <li>点「刷新对方底稿数」从对方明细折旧行反向回填，差异=本表分配−对方数</li>
        <li>勾稽关系行对应 Excel 模板第 14 行，索引芯片可跳转对方科目底稿</li>
        <li>发布后供对方底稿 =WP('H1','折旧分配分析表H1-13','销售费用折旧') 等取数</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * H1TabDepreciationAlloc.vue — H1-13 固定资产折旧分配分析表
 *
 * 对齐 Excel 模板矩阵：类别 × 费用科目 + 合计行 + 勾稽关系行
 * 上游：H1-12 depreciationForAlloc；下游：F5/D5/K8/K9/I6
 */
import { ref, computed, inject, toRef, onMounted } from 'vue'
import { ElMessageBox, ElMessage } from 'element-plus'
import {
  useH1DepreciationAlloc,
  EXPENSE_COLS,
  type AllocRow,
  type ExpenseColMeta,
} from '../../composables/useH1DepreciationAlloc'
import { pullH1DepAllocCounterparts } from '../../composables/h1DepAllocCounterpartPull'
import GtIndexChip from '../../GtIndexChip.vue'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
  /** H1-12 按分类折旧额 */
  depreciationByCategory?: Record<string, number>
  /** H1-12 折旧合计 */
  depreciationTotal?: number
}>()

const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})
const saveResponse = inject<(id: string, val: any) => void>('saveResponse', () => {})

const allResponsesRef = computed(() => props.allResponses)
const byCategoryRef = computed(() => props.depreciationByCategory ?? {})
const depTotalRef = computed(() => props.depreciationTotal ?? 0)

const conclusion = ref('')
const auditNoteText = ref('')
const NOTE_KEY = 'H1-13-audit-note'
const CONCLUSION_KEY = 'H1-13-audit-conclusion'

function saveAuditNote() { saveResponse(NOTE_KEY, auditNoteText.value) }
function saveAllocConclusion() { saveResponse(CONCLUSION_KEY, conclusion.value) }

const expenseCols = EXPENSE_COLS

const {
  rows,
  displayRows,
  h12DepTotal,
  vsH12Diff,
  isBalancedWithH12,
  categoryDiffs,
  writeBackUnallocatedToH12,
  buildCounterpartDiffNote,
  reconciliationRows,
  counterpartPulledAt,
  applyCounterpartPull,
  updateCell,
  addRow,
  removeRow,
  publishAllocated,
  calcRowAllocSum,
  isRowBalanced,
} = useH1DepreciationAlloc(toRef(props, 'wpId'), toRef(props, 'projectId'), allResponsesRef as any, {
  crossSheetByCategory: byCategoryRef as any,
  crossSheetDepTotal: depTotalRef as any,
  onSave(itemId, value) {
    saveResponse(itemId, value)
  },
  onPublishEvent(event: string, payload: any) {
    console.log('[H1-13] publish', event, payload)
  },
})

const pulling = ref(false)

async function handleRefreshCounterparts() {
  if (!props.projectId || pulling.value) return
  pulling.value = true
  try {
    const pulled = await pullH1DepAllocCounterparts(props.projectId)
    applyCounterpartPull(pulled)
    const okCount = Object.values(pulled).filter((p) => p.status === 'ok').length
    const missCount = Object.values(pulled).length - okCount
    if (okCount === 0) {
      ElMessage.warning('未取到对方折旧行，请确认 F5/F2/K8/K9/I6 已编制明细')
    } else if (missCount > 0) {
      ElMessage.success(`已回填 ${okCount} 项；${missCount} 项未命中（可点勾稽状态查看）`)
    } else {
      ElMessage.success(`已回填全部 ${okCount} 项对方底稿数`)
    }
  } catch (e) {
    console.warn('[H1-13] counterpart pull failed', e)
    ElMessage.error('拉取对方底稿数失败')
  } finally {
    pulling.value = false
  }
}

onMounted(() => {
  const n = props.allResponses.get(NOTE_KEY)
  if (n?.remark) auditNoteText.value = n.remark
  const c = props.allResponses.get(CONCLUSION_KEY)
  if (c?.remark) conclusion.value = c.remark
  // 无快照时自动拉一次
  if (!counterpartPulledAt.value && props.projectId) {
    void handleRefreshCounterparts()
  }
})

function colHeaderTip(col: ExpenseColMeta): string {
  if (!col.targetWpCode) return `${col.label}（其他用途，如在建工程资本化等）`
  return `计入${col.label}，对方底稿 ${col.targetWpCode}（${col.wpLabel}）`
}

function rowBalanceTip(row: AllocRow): string {
  if (row._isSummary || isRowBalanced(row)) return ''
  const sum = calcRowAllocSum(row)
  return `分配合计(${fmtAmt(sum)}) ≠ 折旧总额(${fmtAmt(row.depTotal)})，差额: ${fmtAmt(sum - row.depTotal)}`
}

function getRowClassName({ row }: { row: AllocRow }): string {
  if (row._isSummary) return 'summary-row'
  if (row._isReconcile) return 'reconcile-row'
  if (!isRowBalanced(row)) return 'error-row'
  return ''
}

async function handleAddRow() {
  try {
    const { value } = await ElMessageBox.prompt('请输入固定资产类别名称', '新增类别行', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      inputPattern: /\S+/,
      inputErrorMessage: '类别不能为空',
    })
    if (!value) return
    addRow(value)
    ElMessage.success(`已新增：${value}`)
  } catch { /* cancelled */ }
}

function handleWriteCounterpartDiff() {
  const text = buildCounterpartDiffNote()
  auditNoteText.value = auditNoteText.value?.trim()
    ? `${auditNoteText.value.trim()}\n\n${text}`
    : text
  saveAuditNote()
  ElMessage.success('已将跨科目勾稽差异写入审计说明')
}

function handleWriteBackH12() {
  const text = writeBackUnallocatedToH12()
  const n = categoryDiffs.value.filter((c) => !c.balanced).length
  ElMessage.success(`已将 ${n} 类未配平差额回写 H1-12 审计结论`)
  console.log('[H1-13→H1-12]', text)
}

function onCellChange(row: AllocRow, field: keyof AllocRow, value: any) {
  updateCell(row.rowId, field, value)
}

function handleReview(id: string) { openReviewDialog(id) }

function fmtAmt(val: number | null | undefined): string {
  if (val == null) return '—'
  if (Math.abs(val) < 0.005) return '—'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function fmtTime(iso: string): string {
  try {
    const d = new Date(iso)
    if (Number.isNaN(d.getTime())) return iso
    return d.toLocaleString('zh-CN', { hour12: false })
  } catch {
    return iso
  }
}
</script>

<style scoped>
.h1-tab-dep-alloc { padding: 16px; font-size: var(--wp-font-size, 13px); }
.obj-alert { margin-bottom: 12px; }
.methodology-context {
  border-left: 3px solid var(--el-color-warning);
  background: #fffbe6;
  padding: 10px 14px;
  margin-bottom: 12px;
  border-radius: 4px;
  font-size: 12px;
  line-height: 1.7;
}
.methodology-context p { margin: 0; }
.methodology-context code {
  font-size: 11px;
  background: #f5f5f5;
  padding: 1px 4px;
  border-radius: 2px;
}

.tab-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
  flex-wrap: wrap;
}
.toolbar-left, .toolbar-right { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }

.section-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}
.title-actions { display: flex; gap: 8px; }
.h12-hint { font-size: 12px; color: var(--el-text-color-secondary); }
.verify-hint { font-size: 12px; color: var(--el-text-color-secondary); font-weight: 400; }

.alloc-table { font-size: var(--wp-font-size, 13px); }
.alloc-table :deep(.el-input-number) { width: 100%; }
.alloc-table :deep(.el-input-number .el-input__inner) { text-align: right; }

.amount-cell, .formula-cell {
  text-align: right;
  font-variant-numeric: tabular-nums;
}
.formula-cell {
  border-bottom: 1px dashed var(--el-border-color);
  cursor: help;
}
.formula-col-header {
  border-bottom: 1px dashed var(--el-border-color);
  cursor: help;
  padding-bottom: 2px;
}
.error-amount { color: var(--el-color-danger); font-weight: 600; }
.muted { color: var(--el-text-color-secondary); }
.summary-text { font-weight: 700; }

.recon-cell {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  flex-wrap: wrap;
  justify-content: flex-end;
}
.recon-text {
  font-size: 11px;
  color: var(--el-color-danger);
  white-space: nowrap;
}

:deep(.summary-row) { background: #f0fdf4 !important; font-weight: 600; }
:deep(.summary-row td) { background: #f0fdf4 !important; }
:deep(.reconcile-row) { background: #fff7ed !important; }
:deep(.reconcile-row td) { background: #fff7ed !important; }
:deep(.error-row) { background: #fef2f2 !important; }
:deep(.error-row td) { background: #fef2f2 !important; }

.verify-card, .note-card { margin-top: 12px; }
.jump-targets {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 12px;
  flex-wrap: wrap;
}
.jump-label { font-size: 12px; color: var(--el-text-color-secondary); }

.compile-hint {
  margin-top: 12px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ul { padding-left: 20px; margin-top: 8px; line-height: 1.8; }
</style>
