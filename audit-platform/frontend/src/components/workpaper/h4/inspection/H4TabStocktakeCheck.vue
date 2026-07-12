<template>
  <div class="h4-tab-stocktake-check">
    <!-- 方法论上下文 -->
    <div class="methodology-context">
      <p>H4-6盘点检查：逐项核对工程物资实物盘点结果与账面记录。差异数量=盘点数量-账面数量；差异金额=盘点金额-账面金额。差异不为零的行黄色高亮，提示需追查原因。</p>
    </div>

    <!-- Section Title -->
    <div class="section-header">
      <span>盘点检查表 H4-6</span>
      <div class="section-header-actions">
        <el-button size="small" type="primary" link @click="handleAiGenerate">
          <el-icon><MagicStick /></el-icon> AI
        </el-button>
        <el-button size="small" circle @click="openReview('H4-6-stocktake')">💬</el-button>
      </div>
    </div>

    <!-- 12列表格 -->
    <el-table :data="rows" border stripe size="small" class="check-table" row-key="rowId"
      :row-class-name="getRowClassName">
      <el-table-column prop="seq" label="序号" width="50" align="center" />
      <el-table-column label="物资名称" min-width="110">
        <template #default="{ row }">
          <el-input v-if="!props.isReadonly" v-model="row.name" size="small"
            @change="updateCell(row.rowId, 'name', $event)" />
          <span v-else>{{ row.name }}</span>
        </template>
      </el-table-column>
      <el-table-column label="规格" min-width="90">
        <template #default="{ row }">
          <el-input v-if="!props.isReadonly" v-model="row.spec" size="small"
            @change="updateCell(row.rowId, 'spec', $event)" />
          <span v-else>{{ row.spec }}</span>
        </template>
      </el-table-column>
      <el-table-column label="账面数量" width="90" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!props.isReadonly" v-model="row.bookQty" :controls="false"
            size="small" class="amt-input"
            @change="updateCell(row.rowId, 'bookQty', $event)" />
          <span v-else>{{ row.bookQty || '-' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="账面金额" width="100" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!props.isReadonly" v-model="row.bookAmt" :controls="false"
            size="small" class="amt-input"
            @change="updateCell(row.rowId, 'bookAmt', $event)" />
          <span v-else class="amt-cell">{{ fmtAmt(row.bookAmt) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="盘点数量" width="90" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!props.isReadonly" v-model="row.countQty" :controls="false"
            size="small" class="amt-input"
            @change="updateCell(row.rowId, 'countQty', $event)" />
          <span v-else>{{ row.countQty || '-' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="盘点金额" width="100" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!props.isReadonly" v-model="row.countAmt" :controls="false"
            size="small" class="amt-input"
            @change="updateCell(row.rowId, 'countAmt', $event)" />
          <span v-else class="amt-cell">{{ fmtAmt(row.countAmt) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="差异数量" width="90" align="right">
        <template #default="{ row }">
          <span class="formula-cell" :class="{ 'diff-warn': row.hasDiff }"
            title="差异数量 = 盘点数量 - 账面数量">{{ row.diffQty || '-' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="差异金额" width="100" align="right">
        <template #default="{ row }">
          <span class="formula-cell" :class="{ 'diff-warn': row.hasDiff }"
            title="差异金额 = 盘点金额 - 账面金额">{{ fmtAmt(row.diffAmt) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="存放位置" min-width="100">
        <template #default="{ row }">
          <el-input v-if="!props.isReadonly" v-model="row.location" size="small"
            @change="updateCell(row.rowId, 'location', $event)" />
          <span v-else>{{ row.location }}</span>
        </template>
      </el-table-column>
      <el-table-column label="盘点日期" width="100">
        <template #default="{ row }">
          <el-input v-if="!props.isReadonly" v-model="row.countDate" size="small" placeholder="YYYY-MM-DD"
            @change="updateCell(row.rowId, 'countDate', $event)" />
          <span v-else>{{ row.countDate }}</span>
        </template>
      </el-table-column>
      <el-table-column label="备注" min-width="100">
        <template #default="{ row }">
          <el-input v-if="!props.isReadonly" v-model="row.remark" size="small"
            @change="updateCell(row.rowId, 'remark', $event)" />
          <span v-else>{{ row.remark }}</span>
        </template>
      </el-table-column>
      <el-table-column label="" width="40" v-if="!props.isReadonly">
        <template #default="{ row }">
          <el-button size="small" type="danger" link @click="handleDeleteRow(row.rowId)">✕</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 统计摘要 -->
    <div class="stats-bar">
      <span class="stats-item">盘点总笔数 <strong>{{ totalCount }}</strong></span>
      <span class="stats-item" :class="{ 'stats-warn': diffRowCount > 0 }">
        存在差异 <strong>{{ diffRowCount }}</strong> 笔
      </span>
    </div>

    <!-- 操作栏 -->
    <div class="action-bar" v-if="!props.isReadonly">
      <el-button size="small" @click="handleAddRow">+ 添加盘点行</el-button>
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
        <div class="section-header" style="margin-bottom:0">
          <span>审计说明</span>
          <div class="section-header-actions">
            <el-button size="small" type="primary" link @click="handleAiGenerate">
              <el-icon><MagicStick /></el-icon> AI生成
            </el-button>
            <el-button size="small" circle @click="openReview('H4-6-note')">💬</el-button>
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
        <li>逐项核对物资实物盘点数量/金额与账面记录</li>
        <li>差异数量=盘点数量-账面数量；差异金额=盘点金额-账面金额</li>
        <li>差异不为零的行自动黄色高亮，需在备注中说明原因</li>
        <li>盘点日期填写实际盘点日（YYYY-MM-DD格式）</li>
        <li>存放位置记录物资实际存放地点以便复盘</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * H4TabStocktakeCheck.vue — H4-6 盘点检查表
 *
 * 12列: 序号|物资名称|规格|账面数量|账面金额|盘点数量|盘点金额|差异数量|差异金额|存放位置|盘点日期|备注
 * 差异列: auto-calculated, YELLOW highlight when diff != 0 (row-level)
 *
 * Spec: .kiro/specs/h4-engineering-materials/
 * Task: 4.7
 * Requirements: 7.1-7.3
 */
import { ref, computed, inject, toRef } from 'vue'
import { ElMessageBox } from 'element-plus'
import { MagicStick } from '@element-plus/icons-vue'
import { useH4Stocktake, type H4StocktakeRow } from '../../composables/useH4Stocktake'
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
  rows, diffRowCount, totalCount,
  addRow, deleteRow, updateCell, save,
} = useH4Stocktake({
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
})

// ─── Audit Note ──────────────────────────────────────────────────────────────
const auditNote = ref('')
function saveAuditNote() {
  props.allResponses.set('H4-6-note', { item_id: 'H4-6-note', remark: auditNote.value, conclusion: null })
}

// ─── Actions ─────────────────────────────────────────────────────────────────

function getRowClassName({ row }: { row: H4StocktakeRow }) {
  if (row.hasDiff) return 'diff-row'
  return ''
}

async function handleAddRow() {
  try {
    const { value } = await ElMessageBox.prompt('请输入物资名称', '添加盘点行', {
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
  if (command === 'export-template') importExport.exportTemplate('H4-6')
  else if (command === 'export-data') importExport.exportData('H4-6')
  else if (command === 'import-data') {
    const input = document.createElement('input')
    input.type = 'file'
    input.accept = '.xlsx,.xls,.csv'
    input.onchange = (e: Event) => {
      const file = (e.target as HTMLInputElement).files?.[0]
      if (file) importExport.importData('H4-6', file)
    }
    input.click()
  }
}

function handleAiGenerate() {
  console.log('[H4-6] AI generate')
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
.h4-tab-stocktake-check { padding: 16px; font-size: var(--wp-font-size, 13px); }

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

.check-table { font-size: var(--wp-font-size, 13px); margin-bottom: 12px; }
.amt-input { width: 100%; }
.amt-cell { display: block; text-align: right; }

.formula-cell {
  display: inline-block; text-align: right;
  border-bottom: 1px dashed #67c23a;
  cursor: help;
}
.diff-warn { color: #e6a23c; font-weight: 600; border-bottom-color: #e6a23c; }

:deep(.diff-row) { background-color: #fdf6ec !important; }

.stats-bar {
  display: flex; align-items: center; gap: 24px;
  padding: 10px 14px; margin-bottom: 12px;
  background: var(--el-fill-color-lighter);
  border-radius: 6px;
  font-size: var(--wp-font-size, 13px);
}
.stats-item { color: var(--el-text-color-secondary); }
.stats-item strong { color: var(--el-text-color-primary); font-variant-numeric: tabular-nums; }
.stats-warn strong { color: #e6a23c; }

.action-bar { display: flex; align-items: center; margin-bottom: 12px; }
.audit-note-card { margin-bottom: 12px; }
.edit-tips { margin-top: 12px; font-size: 12px; color: var(--el-text-color-secondary); }
.edit-tips summary { cursor: pointer; font-weight: 500; }
.edit-tips ul { padding-left: 20px; margin-top: 8px; }
</style>
