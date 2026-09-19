<template>
  <div class="h8-tab-depreciation-alloc">
    <!-- 审计目标 -->
    <el-alert type="info" :closable="false" show-icon class="obj-alert">
      <template #title>
        审计目标：确认使用权资产本期折旧已按资产类别与用途合理分配至营业成本、制造费用、销售费用、管理费用、研发支出等科目；
        分配合计与 H8-8 折旧测算一致，并与 D5/F2/K8/K9/I6 等对方科目底稿勾稽。
      </template>
    </el-alert>

    <div class="methodology-context">
      <p>
        <strong>编制逻辑（跨科目核对表）：</strong>
        行=使用权资产类别，列=费用科目。横向：各类分配合计须等于 H8-8 该类折旧；
        纵向：各费用列合计供对方底稿取数核对。核对方法：累计折旧贷方本期发生额 ≈ 各费用科目借方折旧之和。
      </p>
    </div>

    <!-- 工具栏 -->
    <div class="tab-toolbar">
      <div class="toolbar-left">
        <el-button size="small" type="primary" :disabled="isReadonly" @click="handleAddRow">+ 新增类别</el-button>
        <el-button size="small" type="warning" plain :disabled="isReadonly || isBalancedWithH88" @click="handleWriteBackH88">
          未配平差额回写 H8-8
        </el-button>
        <el-dropdown :disabled="isReadonly" @command="handleAllocateAll">
          <el-button size="small" :disabled="isReadonly">
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
        <el-button size="small" type="default" link @click="$emit('open-review', 'dep-alloc')">💬 复核</el-button>
        <el-button size="small" type="primary" plain @click="$emit('open-ai', 'dep-alloc')">AI 辅助</el-button>
        <el-dropdown size="small" @command="handleExportCommand">
          <el-button size="small" :loading="ieBusy">导入导出 ▾</el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="export-template">导出模板</el-dropdown-item>
              <el-dropdown-item command="export-data">导出数据</el-dropdown-item>
              <el-dropdown-item command="import-data" :disabled="isReadonly">导入数据</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <input ref="fileInputRef" type="file" accept=".xlsx,.xls" style="display:none" @change="onFileSelected" />
        <el-tag size="small" :type="isBalancedWithH88 ? 'success' : 'danger'">
          {{ isBalancedWithH88 ? '分配合计 = H8-8' : `与H8-8差异 ${fmtAmt(vsH88Diff)}` }}
        </el-tag>
      </div>
      <div class="toolbar-right">
        <GtIndexChip value="wp:H8-9" :context-project-id="projectId" />
        <el-tag size="small" type="info">共 {{ rows.length }} 类</el-tag>
        <el-tag size="small" class="nav-chip" @click="emit('navigate-sheet', 'H8-8')">← H8-8</el-tag>
        <el-tag size="small" class="nav-chip" @click="emit('navigate-sheet', 'H8-10')">H8-10 →</el-tag>
      </div>
    </div>

    <!-- 主矩阵表 -->
    <el-card shadow="never">
      <template #header>
        <div class="section-title">
          <span>H8-9 使用权资产折旧分配分析表</span>
          <span class="h88-hint">
            H8-8 折旧总额：<b class="amount-cell">{{ fmtAmt(h88DepTotal) }}</b>
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

        <el-table-column prop="category" label="使用权资产类别" min-width="130">
          <template #default="{ row }">
            <span v-if="row._isSummary || row._isReconcile" class="summary-text">{{ row.category }}</span>
            <el-select
              v-else-if="!isReadonly"
              v-model="row.category"
              size="small"
              filterable
              allow-create
              @change="onCellChange(row, 'category', row.category)"
            >
              <el-option v-for="c in categoryOptions" :key="c" :label="c" :value="c" />
            </el-select>
            <span v-else>{{ row.category }}</span>
          </template>
        </el-table-column>

        <el-table-column label="折旧总额" width="120" align="right">
          <template #header>
            <el-tooltip content="来自 H8-8 按分类聚合的本期折旧，只读" placement="top">
              <span class="formula-col-header">折旧总额</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <span v-if="row._isReconcile" class="recon-cell">
              <GtIndexChip value="wp:H8-8" :context-project-id="projectId" />
            </span>
            <span v-else class="formula-cell">{{ fmtAmt(row.depTotal) }}</span>
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

        <el-table-column v-if="!isReadonly" label="操作" width="50">
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
        <el-table-column label="对方底稿数" width="140" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!isReadonly && row.field"
              :model-value="row.counterpart"
              :controls="false"
              size="small"
              placeholder="手工录入"
              @change="(v: number | undefined) => onCounterpartChange(row.field, v)"
            />
            <span v-else class="amount-cell">
              {{ row.counterpart == null ? '待拉取' : fmtAmt(row.counterpart) }}
              <el-tag v-if="row.isManual" size="small" type="warning" class="manual-tag">手工</el-tag>
            </span>
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
        <el-table-column label="勾稽状态" min-width="200">
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

    <!-- 上期一致性（Excel 提示第2点） -->
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

    <!-- 审计说明 -->
    <el-card shadow="never" class="note-card">
      <template #header><span>三、审计说明</span></template>
      <el-input
        v-model="auditNoteText"
        type="textarea"
        :autosize="{ minRows: 5 }"
        :disabled="isReadonly"
        placeholder="填写审计说明：分配依据（用途/部门）、与 H8-8 测算及 D5/F2/K8/K9/I6 勾稽情况、分配方法与上期是否一致、重大异常及追加程序。"
        @change="saveAuditNote"
      />
    </el-card>

    <el-card shadow="never" class="note-card">
      <template #header>
        <div class="section-title">
          <span>四、审计结论</span>
          <div class="title-actions">
            <el-button size="small" type="primary" link :disabled="isReadonly" @click="handlePublish">
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
        placeholder="填写审计结论：折旧分配合理、行/列勾稽一致，分配方法与上期一致，未见异常等。"
        @change="saveAllocConclusion"
      />
    </el-card>

    <div class="jump-targets">
      <span class="jump-label">跨底稿联动：</span>
      <GtIndexChip value="wp:H8-8" :context-project-id="projectId" />
      <GtIndexChip value="wp:D5" :context-project-id="projectId" />
      <GtIndexChip value="wp:F2" :context-project-id="projectId" />
      <GtIndexChip value="wp:K8" :context-project-id="projectId" />
      <GtIndexChip value="wp:K9" :context-project-id="projectId" />
      <GtIndexChip value="wp:I6" :context-project-id="projectId" />
    </div>

    <details class="compile-hint">
      <summary>编制提示</summary>
      <ul>
        <li>折旧总额列由 H8-8 按使用权资产类别自动带入（需在 H8-8 填写「资产类别」），不可手改</li>
        <li>横向：各费用列之和必须等于该行折旧总额，否则红色警示</li>
        <li>纵向：营业成本→D5、制造费用→F2、销售费用→K8、管理费用→K9、研发支出→I6</li>
        <li>核对逻辑：累计折旧贷方本期发生额 vs 各费用科目借方「使用权资产折旧」合计</li>
        <li>点「刷新对方底稿数」从对方明细折旧行反向回填；取不到时可在「对方底稿数」列手工覆盖</li>
        <li>「差额一键计入」将各类未分配差额并入选定费用列，便于办公用房等单一用途场景</li>
        <li>勾稽关系行对应 Excel 模板，索引芯片可跳转对方科目底稿</li>
        <li>评估分配方法是否合理且与上期一致；办公用房→管理费用，仓库/厂房→营业成本或制造费用</li>
        <li>发布后发出 h8:depreciation-allocated，供对方底稿取数</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * H8TabDepreciationAlloc.vue — H8-9 折旧分配分析表
 *
 * 对齐 Excel 模板矩阵：类别 × 费用科目 + 合计行 + 勾稽关系行
 * 上游：H8-8 depreciationByCategory；下游：D5/F2/K8/K9/I6
 */
import { ref, computed, toRef, onMounted, watch } from 'vue'
import { ElMessageBox, ElMessage } from 'element-plus'
import {
  useH8DepreciationAlloc,
  H8_EXPENSE_COLS,
  H8_DEFAULT_CATEGORIES,
  type H8AllocRow,
  type H8ExpenseColMeta,
  type H8ExpenseField,
  type H8PriorConsistency,
} from '../../composables/useH8DepreciationAlloc'
import { useH8Depreciation, H8_DEP_ASSET_CATEGORIES } from '../../composables/useH8Depreciation'
import type { H8CounterpartField } from '../../composables/h8DepAllocCounterpartPull'
import { pullH8DepAllocCounterparts } from '../../composables/h8DepAllocCounterpartPull'
import GtIndexChip from '../../GtIndexChip.vue'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const emit = defineEmits<{
  (e: 'save', itemId: string, value: any): void
  (e: 'open-ai', section: string): void
  (e: 'open-review', section: string): void
  (e: 'navigate-sheet', sheetName: string): void
}>()

const allResponsesRef = toRef(props, 'allResponses')

const {
  depTotal: h88DepFromEngine,
  depreciationByCategory,
} = useH8Depreciation({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  allResponses: allResponsesRef,
})

const byCategoryRef = computed(() => depreciationByCategory.value)
const depTotalRef = computed(() => h88DepFromEngine.value)

const conclusion = ref('')
const auditNoteText = ref('')
const NOTE_KEY = 'H8-dep-alloc-audit-note'
const CONCLUSION_KEY = 'H8-dep-alloc-audit-conclusion'

function saveAuditNote() {
  emit('save', NOTE_KEY, auditNoteText.value)
}
function saveAllocConclusion() {
  emit('save', CONCLUSION_KEY, conclusion.value)
}

const expenseCols = H8_EXPENSE_COLS
const categoryOptions = [...H8_DEFAULT_CATEGORIES, ...H8_DEP_ASSET_CATEGORIES]
  .filter((v, i, a) => a.indexOf(v) === i)

const {
  rows,
  displayRows,
  h88DepTotal,
  vsH88Diff,
  isBalancedWithH88,
  categoryDiffs,
  writeBackUnallocatedToH88,
  reconciliationRows,
  counterpartPulledAt,
  applyCounterpartPull,
  setCounterpartManual,
  allocateAllRemaindersTo,
  priorConsistent,
  priorNote,
  savePriorAssessment,
  updateCell,
  addRow,
  removeRow,
  publishAllocated,
  calcRowAllocSum,
  isRowBalanced,
  exportData,
  importData,
} = useH8DepreciationAlloc({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  allResponses: allResponsesRef,
  crossSheetByCategory: byCategoryRef,
  crossSheetDepTotal: depTotalRef,
  onSave(itemId, value) {
    emit('save', itemId, value)
  },
  onPublishEvent(event, payload) {
    console.log('[H8-9] publish', event, payload)
  },
})

const ieBusy = ref(false)
const fileInputRef = ref<HTMLInputElement | null>(null)

async function handleExportCommand(cmd: string) {
  ieBusy.value = true
  try {
    if (cmd === 'export-template') await exportData('template')
    else if (cmd === 'export-data') await exportData('data')
    else if (cmd === 'import-data') fileInputRef.value?.click()
  } finally {
    ieBusy.value = false
  }
}

async function onFileSelected(e: Event) {
  const file = (e.target as HTMLInputElement).files?.[0]
  ;(e.target as HTMLInputElement).value = ''
  if (!file || props.isReadonly) return
  try {
    await ElMessageBox.confirm(
      `即将导入「${file.name}」到 H8-9，已有分配行将被覆盖（折旧总额仍由 H8-8 同步）。确认？`,
      '导入确认',
      { type: 'warning' },
    )
  } catch {
    return
  }
  ieBusy.value = true
  try {
    const r = await importData(file, true)
    ElMessage.success(`已导入 ${r.imported} 类`)
  } catch (err: any) {
    ElMessage.error(err?.message || '导入失败')
  } finally {
    ieBusy.value = false
  }
}

const priorNoteLocal = ref('')
watch(priorNote, (v) => { priorNoteLocal.value = v }, { immediate: true })

const pulling = ref(false)

async function handleRefreshCounterparts() {
  if (!props.projectId || pulling.value) return
  pulling.value = true
  try {
    const pulled = await pullH8DepAllocCounterparts(props.projectId)
    applyCounterpartPull(pulled)
    const okCount = Object.values(pulled).filter((p) => p.status === 'ok').length
    const missCount = Object.values(pulled).length - okCount
    if (okCount === 0) {
      ElMessage.warning('未取到对方折旧行，可在「对方底稿数」列手工录入后勾稽')
    } else if (missCount > 0) {
      ElMessage.success(`已回填 ${okCount} 项；${missCount} 项未命中（可手工覆盖）`)
    } else {
      ElMessage.success(`已回填全部 ${okCount} 项对方底稿数`)
    }
  } catch (e) {
    console.warn('[H8-9] counterpart pull failed', e)
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
  if (!counterpartPulledAt.value && props.projectId) {
    void handleRefreshCounterparts()
  }
})

function onCounterpartChange(field: H8CounterpartField | '' | undefined, v: number | undefined) {
  if (!field) return
  setCounterpartManual(field, v == null || Number.isNaN(Number(v)) ? null : Number(v))
}

function handleAllocateAll(field: H8ExpenseField) {
  const n = allocateAllRemaindersTo(field)
  if (n === 0) ElMessage.info('各行已配平，无需分摊')
  else ElMessage.success(`已将 ${n} 类未分配差额计入「${expenseCols.find((c) => c.field === field)?.label}」`)
}

function onPriorConsistentChange(v: string) {
  const c = (v === 'Y' || v === 'N' ? v : '') as H8PriorConsistency
  savePriorAssessment(c, priorNoteLocal.value)
}

function savePrior() {
  savePriorAssessment(priorConsistent.value, priorNoteLocal.value)
}

function colHeaderTip(col: H8ExpenseColMeta): string {
  if (!col.targetWpCode) return `${col.label}（其他用途，如在建工程资本化等）`
  return `计入${col.label}，对方底稿 ${col.targetWpCode}`
}

function rowBalanceTip(row: H8AllocRow): string {
  if (row._isSummary || isRowBalanced(row)) return ''
  const sum = calcRowAllocSum(row)
  return `分配合计(${fmtAmt(sum)}) ≠ 折旧总额(${fmtAmt(row.depTotal)})，差额: ${fmtAmt(sum - row.depTotal)}`
}

function getRowClassName({ row }: { row: H8AllocRow }): string {
  if (row._isSummary) return 'summary-row'
  if (row._isReconcile) return 'reconcile-row'
  if (!isRowBalanced(row)) return 'error-row'
  return ''
}

async function handleAddRow() {
  try {
    const { value } = await ElMessageBox.prompt('请输入使用权资产类别名称', '新增类别行', {
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

function handleWriteBackH88() {
  writeBackUnallocatedToH88()
  const n = categoryDiffs.value.filter((c) => !c.balanced).length
  ElMessage.success(`已将 ${n} 类未配平差额回写 H8-8 审计结论`)
}

function onCellChange(row: H8AllocRow, field: keyof H8AllocRow, value: any) {
  updateCell(row.rowId, field, value)
}

function handlePublish() {
  publishAllocated()
  ElMessage.success('已发布折旧分配（h8:depreciation-allocated），可供对方底稿取数')
}

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
.h8-tab-depreciation-alloc { padding: 16px; font-size: var(--wp-font-size, 13px); }
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

.tab-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
  flex-wrap: wrap;
}
.toolbar-left, .toolbar-right { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.nav-chip { cursor: pointer; }

.section-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}
.title-actions { display: flex; gap: 8px; align-items: center; }
.h88-hint { font-size: 12px; color: var(--el-text-color-secondary); }
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

.verify-card, .note-card, .prior-card { margin-top: 12px; }
.prior-row {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.prior-note { max-width: 720px; }
.manual-tag { margin-left: 4px; }
.caret { font-size: 10px; margin-left: 2px; }
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
