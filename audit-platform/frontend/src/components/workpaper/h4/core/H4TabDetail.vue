<template>
  <div class="h4-tab-detail">
    <!-- 方法论上下文 -->
    <div class="methodology-context">
      <p>H4-2明细表：按物资分类逐项登记工程物资的期初、入库、出库及期末余额。67列拆分为3区段Tab展示，保持可操作性。核心公式：入库小计=本期采购+其他增加；期末余额=期初+入库小计-出库合计。</p>
    </div>

    <!-- Section Title: 明细表 -->
    <div class="section-header">
      <span>工程物资明细表 H4-2</span>
      <div class="section-header-actions">
        <el-button size="small" type="primary" link @click="handleAiGenerate">
          <el-icon><MagicStick /></el-icon> AI
        </el-button>
        <el-button size="small" circle @click="openReview('H4-2-detail')">💬</el-button>
      </div>
    </div>

    <!-- 3区段Tab -->
    <el-tabs v-model="activeTab" type="border-card" class="detail-tabs" @tab-change="onTabChange">
      <!-- Tab 1: 基础信息 -->
      <el-tab-pane label="基础信息" name="basic">
        <el-table :data="rows" border stripe size="small" class="detail-table"
          highlight-current-row :current-row-key="selectedRowId"
          @current-change="onCurrentRowChange" row-key="rowId">
          <el-table-column type="index" label="序号" width="55" align="center" />
          <el-table-column prop="category" label="物资分类" min-width="110">
            <template #default="{ row }">
              <el-input v-if="!props.isReadonly" v-model="row.category" size="small"
                @change="updateCell(row.rowId, 'category', $event)" />
              <span v-else>{{ row.category }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="name" label="物资名称" min-width="120">
            <template #default="{ row }">
              <el-input v-if="!props.isReadonly" v-model="row.name" size="small"
                @change="updateCell(row.rowId, 'name', $event)" />
              <span v-else>{{ row.name }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="spec" label="规格型号" min-width="100">
            <template #default="{ row }">
              <el-input v-if="!props.isReadonly" v-model="row.spec" size="small"
                @change="updateCell(row.rowId, 'spec', $event)" />
              <span v-else>{{ row.spec }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="quantity" label="数量" width="80" align="right">
            <template #default="{ row }">
              <el-input-number v-if="!props.isReadonly" v-model="row.quantity" :controls="false"
                size="small" class="amt-input"
                @change="updateCell(row.rowId, 'quantity', $event)" />
              <span v-else>{{ row.quantity || '-' }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="unit" label="单位" width="70">
            <template #default="{ row }">
              <el-input v-if="!props.isReadonly" v-model="row.unit" size="small"
                @change="updateCell(row.rowId, 'unit', $event)" />
              <span v-else>{{ row.unit }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="supplier" label="供应商" min-width="120">
            <template #default="{ row }">
              <el-input v-if="!props.isReadonly" v-model="row.supplier" size="small"
                @change="updateCell(row.rowId, 'supplier', $event)" />
              <span v-else>{{ row.supplier }}</span>
            </template>
          </el-table-column>
          <el-table-column label="" width="45" v-if="!props.isReadonly">
            <template #default="{ row }">
              <el-button size="small" type="danger" link @click="handleDeleteRow(row.rowId)">✕</el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>

      <!-- Tab 2: 入库 -->
      <el-tab-pane label="入库" name="inbound">
        <el-table :data="rows" border stripe size="small" class="detail-table"
          highlight-current-row :current-row-key="selectedRowId"
          @current-change="onCurrentRowChange" row-key="rowId">
          <el-table-column type="index" label="序号" width="55" align="center" />
          <el-table-column prop="name" label="物资名称" min-width="110" />
          <el-table-column label="期初金额" min-width="110" align="right">
            <template #default="{ row }">
              <el-input-number v-if="!props.isReadonly" v-model="row.beginAmount" :controls="false"
                size="small" class="amt-input"
                @change="updateCell(row.rowId, 'beginAmount', $event)" />
              <span v-else class="amt-cell">{{ fmtAmt(row.beginAmount) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="本期采购" min-width="110" align="right">
            <template #default="{ row }">
              <el-input-number v-if="!props.isReadonly" v-model="row.purchaseAmount" :controls="false"
                size="small" class="amt-input"
                @change="updateCell(row.rowId, 'purchaseAmount', $event)" />
              <span v-else class="amt-cell">{{ fmtAmt(row.purchaseAmount) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="其他增加" min-width="110" align="right">
            <template #default="{ row }">
              <el-input-number v-if="!props.isReadonly" v-model="row.otherIncrease" :controls="false"
                size="small" class="amt-input"
                @change="updateCell(row.rowId, 'otherIncrease', $event)" />
              <span v-else class="amt-cell">{{ fmtAmt(row.otherIncrease) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="入库小计" min-width="110" align="right">
            <template #default="{ row }">
              <span class="formula-cell" title="入库小计 = 本期采购 + 其他增加">{{ fmtAmt(row.increaseSubtotal) }}</span>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>

      <!-- Tab 3: 出库 -->
      <el-tab-pane label="出库" name="outbound">
        <el-table :data="rows" border stripe size="small" class="detail-table"
          highlight-current-row :current-row-key="selectedRowId"
          @current-change="onCurrentRowChange" row-key="rowId">
          <el-table-column type="index" label="序号" width="55" align="center" />
          <el-table-column prop="name" label="物资名称" min-width="100" />
          <el-table-column label="领用出库" min-width="100" align="right">
            <template #default="{ row }">
              <el-input-number v-if="!props.isReadonly" v-model="row.usageAmount" :controls="false"
                size="small" class="amt-input"
                @change="updateCell(row.rowId, 'usageAmount', $event)" />
              <span v-else class="amt-cell">{{ fmtAmt(row.usageAmount) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="退货" min-width="100" align="right">
            <template #default="{ row }">
              <el-input-number v-if="!props.isReadonly" v-model="row.returnAmount" :controls="false"
                size="small" class="amt-input"
                @change="updateCell(row.rowId, 'returnAmount', $event)" />
              <span v-else class="amt-cell">{{ fmtAmt(row.returnAmount) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="报废" min-width="100" align="right">
            <template #default="{ row }">
              <el-input-number v-if="!props.isReadonly" v-model="row.scrapAmount" :controls="false"
                size="small" class="amt-input"
                @change="updateCell(row.rowId, 'scrapAmount', $event)" />
              <span v-else class="amt-cell">{{ fmtAmt(row.scrapAmount) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="其他减少" min-width="100" align="right">
            <template #default="{ row }">
              <el-input-number v-if="!props.isReadonly" v-model="row.otherDecrease" :controls="false"
                size="small" class="amt-input"
                @change="updateCell(row.rowId, 'otherDecrease', $event)" />
              <span v-else class="amt-cell">{{ fmtAmt(row.otherDecrease) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="期末余额" min-width="110" align="right">
            <template #default="{ row }">
              <span class="formula-cell" title="期末 = 期初 + 入库小计 - 出库合计">{{ fmtAmt(row.endAmount) }}</span>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>
    </el-tabs>

    <!-- 合计行 -->
    <el-card shadow="never" class="subtotal-card">
      <div class="subtotal-grid">
        <div class="subtotal-item"><span class="st-label">期初合计：</span><span class="st-value">{{ fmtAmt(subtotalRow.beginAmount) }}</span></div>
        <div class="subtotal-item"><span class="st-label">入库小计合计：</span><span class="st-value">{{ fmtAmt(subtotalRow.increaseSubtotal) }}</span></div>
        <div class="subtotal-item"><span class="st-label">出库合计：</span><span class="st-value">{{ fmtAmt(subtotalRow.usageAmount + subtotalRow.returnAmount + subtotalRow.scrapAmount + subtotalRow.otherDecrease) }}</span></div>
        <div class="subtotal-item"><span class="st-label">期末合计：</span><span class="st-value formula-cell" title="期末合计 = Σ期初 + Σ入库 - Σ出库">{{ fmtAmt(subtotalRow.endAmount) }}</span></div>
      </div>
    </el-card>

    <!-- 操作栏 -->
    <div class="action-bar" v-if="!props.isReadonly">
      <el-button size="small" @click="handleAddRow">+ 添加物资行</el-button>
      <el-dropdown trigger="click" @command="handleImportExport" style="margin-left: 8px">
        <el-button size="small">导入导出 ▾</el-button>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item command="export-template">导出模板</el-dropdown-item>
            <el-dropdown-item command="export-data">导出数据</el-dropdown-item>
            <el-dropdown-item command="import-data">导入数据</el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
    </div>

    <!-- 审计说明 -->
    <el-card shadow="never" class="audit-note-card">
      <template #header>
        <div class="section-header">
          <span>审计说明</span>
          <div class="section-header-actions">
            <el-button size="small" type="primary" link @click="handleAiGenerate">
              <el-icon><MagicStick /></el-icon> AI生成
            </el-button>
            <el-button size="small" circle @click="openReview('H4-2-note')">💬</el-button>
          </div>
        </div>
      </template>
      <el-input v-model="auditNote" type="textarea" :autosize="{ minRows: 3, maxRows: 8 }"
        placeholder="请填写审计说明..." :disabled="props.isReadonly"
        @blur="saveAuditNote" />
    </el-card>

    <!-- 编制提示 -->
    <details class="edit-tips">
      <summary>编制提示</summary>
      <ul>
        <li>67列宽表拆分为3区段Tab（基础/入库/出库），切换Tab时行选中保持同步</li>
        <li>核心公式：入库小计=采购+其他增加；期末=期初+入库小计-出库合计</li>
        <li>合计行自动汇总所有物资行，不可编辑</li>
        <li>金额列：右对齐+千分位+负数红色括号+零值显示"-"</li>
        <li>公式列：绿色虚线下划线+鼠标悬停显示公式来源</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * H4TabDetail.vue — H4-2 明细表（67列3区段Tab）
 *
 * 3区段Tab: basic(物资分类/名称/规格/数量/单位/供应商) | inbound(期初/采购/其他增加/入库小计)
 *           | outbound(领用/退货/报废/其他减少/期末余额)
 * 公式: 入库小计=采购+其他增加; 期末=期初+入库-出库合计
 *
 * Spec: .kiro/specs/h4-engineering-materials/
 * Task: 4.3
 * Requirements: 3.1-3.9
 */
import { ref, computed, inject, toRef } from 'vue'
import { ElMessageBox } from 'element-plus'
import { MagicStick } from '@element-plus/icons-vue'
import { useH4Detail, type H4DetailTab } from '../../composables/useH4Detail'
import { useH4ImportExport } from '../../composables/useH4ImportExport'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})

// ─── Composable ──────────────────────────────────────────────────────────────
const allResponsesRef = computed(() => props.allResponses)

const {
  rows, activeTab, selectedRowId, subtotalRow,
  addRow, deleteRow, updateCell, setActiveTab, selectRow, save,
} = useH4Detail({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  allResponses: allResponsesRef as any,
  onSave: (itemId: string, value: any) => {
    const strVal = value != null ? (typeof value === 'string' ? value : JSON.stringify(value)) : null
    props.allResponses.set(itemId, { item_id: itemId, remark: strVal, conclusion: null })
  },
})

const importExport = useH4ImportExport({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  onImported: () => {
    // Reload data from allResponses after import
  },
})

// ─── Audit Note ──────────────────────────────────────────────────────────────
const auditNote = ref('')
function saveAuditNote() {
  props.allResponses.set('H4-2-note', { item_id: 'H4-2-note', remark: auditNote.value, conclusion: null })
}

// ─── Actions ─────────────────────────────────────────────────────────────────

function onTabChange(tab: string | number) {
  setActiveTab(tab as H4DetailTab)
}

function onCurrentRowChange(row: any) {
  selectRow(row?.rowId ?? null)
}

async function handleAddRow() {
  try {
    const { value } = await ElMessageBox.prompt('请输入物资名称', '添加物资行', {
      confirmButtonText: '确认',
      cancelButtonText: '取消',
      inputPattern: /\S+/,
      inputErrorMessage: '名称不能为空',
    })
    if (value) addRow(value)
  } catch { /* cancelled */ }
}

function handleDeleteRow(rowId: string) {
  deleteRow(rowId)
}

function handleImportExport(command: string) {
  if (command === 'export-template') importExport.exportTemplate('H4-2')
  else if (command === 'export-data') importExport.exportData('H4-2')
  else if (command === 'import-data') {
    const input = document.createElement('input')
    input.type = 'file'
    input.accept = '.xlsx,.xls,.csv'
    input.onchange = (e: Event) => {
      const file = (e.target as HTMLInputElement).files?.[0]
      if (file) importExport.importData('H4-2', file)
    }
    input.click()
  }
}

function handleAiGenerate() {
  console.log('[H4-2] AI generate')
}

function openReview(id: string) {
  openReviewDialog(id)
}

// ─── 金额格式化 ──────────────────────────────────────────────────────────────
function fmtAmt(val: number | null | undefined): string {
  if (val == null) return '-'
  if (val === 0) return '-'
  if (val < 0) {
    return `(${Math.abs(val).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })})`
  }
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.h4-tab-detail { padding: 16px; font-size: var(--wp-font-size, 13px); }

.methodology-context {
  border-left: 4px solid #d97706;
  background: #fffbeb;
  padding: 10px 14px;
  margin-bottom: 16px;
  border-radius: 4px;
  font-size: 12px;
  color: #92400e;
  line-height: 1.6;
}

.section-header {
  display: flex; align-items: center; justify-content: space-between;
  font-size: 14px; font-weight: 600; margin-bottom: 12px;
}
.section-header-actions { display: flex; align-items: center; gap: 4px; }

.detail-tabs { margin-bottom: 12px; }
.detail-table { font-size: var(--wp-font-size, 13px); }
.amt-input { width: 100%; }
.amt-cell { display: block; text-align: right; }

.formula-cell {
  display: inline-block; text-align: right;
  border-bottom: 1px dashed #67c23a;
  cursor: help;
  color: var(--el-text-color-primary);
}

.subtotal-card { margin-bottom: 12px; }
.subtotal-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 12px; }
.subtotal-item { display: flex; align-items: center; gap: 6px; }
.st-label { color: var(--el-text-color-secondary); font-size: 12px; }
.st-value { font-weight: 600; font-variant-numeric: tabular-nums; }

.action-bar { display: flex; align-items: center; margin-bottom: 12px; }
.audit-note-card { margin-bottom: 12px; }
.edit-tips { margin-top: 12px; font-size: 12px; color: var(--el-text-color-secondary); }
.edit-tips summary { cursor: pointer; font-weight: 500; }
.edit-tips ul { padding-left: 20px; margin-top: 8px; }
</style>
