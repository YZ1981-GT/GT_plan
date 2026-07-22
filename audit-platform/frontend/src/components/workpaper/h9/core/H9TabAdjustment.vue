<template>
  <div class="h9-tab-adjustment">
    <!-- 审计目标 -->
    <el-alert
      type="info"
      :closable="false"
      show-icon
      class="objective-alert"
      title="审计目标：核实租赁负债审计调整分录(AJE)与重分类分录(RJE)记录完整、借贷平衡，确认调整已正确联动 H9-1 审定表的 AJE/RJE 列并反映于报表列报。"
    />

    <!-- 方法论上下文 -->
    <div class="methodology-context">
      <p>H9-4调整分录：记录租赁负债审计过程中发现的审计调整分录(AJE)和重分类调整分录(RJE)。调整分录必须借贷平衡，保存后自动通过EventBus联动H9-1审定表的AJE/RJE列。</p>
    </div>

    <!-- Section Title -->
    <div class="section-header">
      <span>调整分录汇总 H9-4</span>
      <div class="section-header-actions">
        <el-button size="small" circle @click="openReview('H9-4-adjustment')">💬</el-button>
      </div>
    </div>

    <!-- 工具栏 -->
    <div class="tab-toolbar">
      <div class="toolbar-left"></div>
      <div class="toolbar-right">
        <span class="chip-wrap"><GtIndexChip value="wp:H9-4" :context-project-id="props.projectId" /></span>
        <el-tag size="small" type="info">共 {{ rows.length }} 行</el-tag>
      </div>
    </div>

    <!-- 10列表格 -->
    <el-table :data="rows" border stripe size="small" class="adj-table" row-key="rowId">
      <el-table-column prop="seq" label="序号" width="55" align="center" />
      <el-table-column label="调整事项说明" min-width="140">
        <template #default="{ row }">
          <el-input v-if="!props.isReadonly" v-model="row.description" size="small"
            @change="updateCell(row.rowId, 'description', $event)" />
          <span v-else>{{ row.description }}</span>
        </template>
      </el-table-column>
      <el-table-column label="类别" width="120" align="center">
        <template #default="{ row }">
          <el-select v-if="!props.isReadonly" v-model="row.category" size="small"
            @change="updateCell(row.rowId, 'category', $event)">
            <el-option label="账项调整(AJE)" value="AJE" />
            <el-option label="报表调整(RJE)" value="RJE" />
          </el-select>
          <el-tag v-else :type="row.category === 'AJE' ? 'danger' : 'warning'" size="small">
            {{ row.category === 'AJE' ? '账项调整' : '报表调整' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="报表项目" min-width="110">
        <template #default="{ row }">
          <el-input v-if="!props.isReadonly" v-model="row.reportItem" size="small"
            @change="updateCell(row.rowId, 'reportItem', $event)" />
          <span v-else>{{ row.reportItem }}</span>
        </template>
      </el-table-column>
      <el-table-column label="科目名称" min-width="110">
        <template #default="{ row }">
          <el-input v-if="!props.isReadonly" v-model="row.accountName" size="small"
            @change="updateCell(row.rowId, 'accountName', $event)" />
          <span v-else>{{ row.accountName }}</span>
        </template>
      </el-table-column>
      <el-table-column label="附注项目" min-width="100">
        <template #default="{ row }">
          <el-input v-if="!props.isReadonly" v-model="row.noteItem" size="small"
            @change="updateCell(row.rowId, 'noteItem', $event)" />
          <span v-else>{{ row.noteItem }}</span>
        </template>
      </el-table-column>
      <el-table-column label="借方金额" min-width="110" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!props.isReadonly" v-model="row.debitAmount" :controls="false"
            size="small" class="amt-input"
            @change="updateCell(row.rowId, 'debitAmount', $event)" />
          <span v-else class="amt-cell">{{ fmtAmt(row.debitAmount) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="贷方金额" min-width="110" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!props.isReadonly" v-model="row.creditAmount" :controls="false"
            size="small" class="amt-input"
            @change="updateCell(row.rowId, 'creditAmount', $event)" />
          <span v-else class="amt-cell">{{ fmtAmt(row.creditAmount) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="索引" width="80">
        <template #default="{ row }">
          <el-input v-if="!props.isReadonly" v-model="row.indexRef" size="small"
            @change="updateCell(row.rowId, 'indexRef', $event)" />
          <span v-else>{{ row.indexRef }}</span>
        </template>
      </el-table-column>
      <el-table-column label="备注" min-width="100">
        <template #default="{ row }">
          <el-input v-if="!props.isReadonly" v-model="row.remark" size="small"
            @change="updateCell(row.rowId, 'remark', $event)" />
          <span v-else>{{ row.remark }}</span>
        </template>
      </el-table-column>
      <el-table-column label="" width="45" v-if="!props.isReadonly">
        <template #default="{ row }">
          <el-button size="small" type="danger" link @click="handleDeleteRow(row.rowId)">✕</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 借贷合计 + 平衡状态 -->
    <div class="balance-bar">
      <div class="balance-row">
        <span class="balance-label">借方合计：</span>
        <span class="balance-value">{{ fmtAmt(balanceCheck.debitTotal) }}</span>
      </div>
      <div class="balance-row">
        <span class="balance-label">贷方合计：</span>
        <span class="balance-value">{{ fmtAmt(balanceCheck.creditTotal) }}</span>
      </div>
      <div class="balance-status" :class="{ balanced: balanceCheck.isBalanced, unbalanced: !balanceCheck.isBalanced }">
        <span v-if="balanceCheck.isBalanced">✓ 借贷平衡</span>
        <span v-else>✗ {{ balanceCheck.warning }}</span>
      </div>
    </div>

    <!-- 操作栏 -->
    <div class="action-bar" v-if="!props.isReadonly">
      <el-button size="small" @click="handleAddRow">+ 新增调整分录</el-button>
      <el-button size="small" type="primary" @click="handleSave" :loading="saving">保存</el-button>
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
            <el-button size="small" circle @click="openReview('H9-4-note')">💬</el-button>
          </div>
        </div>
      </template>
      <el-input v-model="auditNote" type="textarea" :autosize="{ minRows: 5 }"
        placeholder="请填写调整分录的审计说明..." :disabled="props.isReadonly"
        @blur="saveAuditNote" />
    </el-card>

    <!-- 审计结论 -->
    <el-card shadow="never" class="audit-note-card">
      <template #header>
        <div class="section-header" style="margin-bottom:0">
          <span>审计结论</span>
          <div class="section-header-actions">
            <el-button size="small" circle @click="openReview('H9-4-conclusion')">💬</el-button>
          </div>
        </div>
      </template>
      <el-input v-model="auditConclusion" type="textarea" :autosize="{ minRows: 3 }"
        placeholder="请填写调整分录的审计结论..." :disabled="props.isReadonly"
        @blur="saveAuditConclusion" />
    </el-card>

    <!-- 编制提示 -->
    <details class="edit-tips">
      <summary>编制提示</summary>
      <ul>
        <li>对齐 Excel：类别「账项调整」=AJE、「报表调整」=RJE（一年内到期重分类等）</li>
        <li>借方合计必须等于贷方合计（借贷平衡），不平衡时红色警告</li>
        <li>本表仅列示与本报表项目相关的调整；项目组可按复杂程度选用</li>
        <li>保存后自动通过EventBus发布'adjustment:created'联动H9-1审定表</li>
        <li>科目名称填写「租赁负债」(2205)或「未确认融资费用」等相关科目</li>
        <li>H9为负债类贷方科目：增加记贷方，减少记借方</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * H9TabAdjustment.vue — H9-4 调整分录汇总
 *
 * 10列: 序号|调整事项说明|类别(AJE/RJE)|报表项目|科目名称|附注项目|借方金额|贷方金额|索引|备注
 * 底部: 借贷合计 + 平衡状态(绿"✓平衡"/红"✗不平衡")
 * EventBus: save时publish 'adjustment:created'
 * 新增行: ElMessageBox.prompt输入调整事项名称
 * 导入导出: el-dropdown三级
 *
 * Spec: .kiro/specs/h9-lease-liabilities/ Task 4.5
 * Requirements: 5.1-5.4
 */
import { ref, computed, inject, toRef } from 'vue'
import { ElMessageBox } from 'element-plus'
import { useH9Adjustment } from '../../composables/useH9Adjustment'
import { useH9ImportExport } from '../../composables/useH9ImportExport'
import GtIndexChip from '../../GtIndexChip.vue'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})
// 父入口提供的持久化函数（更新共享 Map + 防抖 PUT checklist-responses）。
// Bug C 修复：此前 onSave 仅写内存 Map，从不落库 → 刷新丢数据。
const saveResponse = inject<(itemId: string, value: any) => void>('saveResponse', (itemId, value) => {
  const strVal = value != null ? (typeof value === 'string' ? value : JSON.stringify(value)) : null
  props.allResponses.set(itemId, { item_id: itemId, remark: strVal, conclusion: null })
})
const saving = ref(false)
const h9ReloadAll = inject<() => Promise<void>>('h9ReloadAll', async () => {})

// ─── Composable ──────────────────────────────────────────────────────────────
const allResponsesRef = computed(() => props.allResponses)

const {
  rows, balanceCheck,
  addRow, deleteRow, updateCell, publishAdjustment, save,
} = useH9Adjustment({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  allResponses: allResponsesRef as any,
  onSave: (itemId: string, value: any) => saveResponse(itemId, value),
  onPublishAdjustment: (_aje: number, _rje: number) => {
    // EventBus已在composable内部通过window.dispatchEvent发布
  },
})

const importExport = useH9ImportExport({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  sheetCode: 'H9-4',
  onImported: async () => { await h9ReloadAll() },
})

// ─── Audit Note / Conclusion ─────────────────────────────────────────────────
const auditNote = ref('')
const auditConclusion = ref('')
// 初始化加载审计说明/结论
const noteData = props.allResponses.get('H9-4-note')
if (noteData) auditNote.value = noteData.remark ?? noteData.conclusion ?? ''
const conclusionData = props.allResponses.get('H9-4-audit-conclusion')
if (conclusionData) auditConclusion.value = conclusionData.remark ?? conclusionData.conclusion ?? ''

function saveAuditNote() {
  saveResponse('H9-4-note', auditNote.value)
}

function saveAuditConclusion() {
  saveResponse('H9-4-audit-conclusion', auditConclusion.value)
}

// ─── Actions ─────────────────────────────────────────────────────────────────

async function handleAddRow() {
  try {
    const { value } = await ElMessageBox.prompt('请输入调整事项名称', '新增调整分录', {
      confirmButtonText: '确认',
      cancelButtonText: '取消',
      inputPlaceholder: '如：租赁负债初始确认差异调整',
    })
    if (value?.trim()) {
      addRow('AJE')
      // 设置新增行的description
      const lastRow = rows.value[rows.value.length - 1]
      if (lastRow) {
        updateCell(lastRow.rowId, 'description', value.trim())
      }
    }
  } catch {
    // 用户取消，不做处理
  }
}

function handleDeleteRow(rowId: string) {
  deleteRow(rowId)
}

async function handleSave() {
  saving.value = true
  try {
    save()
    publishAdjustment()
  } finally {
    saving.value = false
  }
}

function handleImportExport(command: string) {
  if (command === 'export-template') importExport.exportTemplate(['H9-4'])
  else if (command === 'export-data') importExport.exportData(['H9-4'])
  else if (command === 'import-data') {
    const input = document.createElement('input')
    input.type = 'file'
    input.accept = '.xlsx,.xls,.csv'
    input.onchange = (e: Event) => {
      const file = (e.target as HTMLInputElement).files?.[0]
      if (file) importExport.importData(file)
    }
    input.click()
  }
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
.h9-tab-adjustment { padding: 16px; font-size: var(--wp-font-size, 13px); }

.methodology-context {
  border-left: 4px solid #d97706;
  background: #fffbeb;
  padding: 10px 14px;
  margin-bottom: 16px;
  border-radius: 0 6px 6px 0;
  font-size: 12px;
  color: #92400e;
  line-height: 1.6;
}

.section-header {
  display: flex; align-items: center; justify-content: space-between;
  font-size: 14px; font-weight: 600; margin-bottom: 12px;
}
.section-header-actions { display: flex; align-items: center; gap: 4px; }

.objective-alert { margin-bottom: 12px; }
.tab-toolbar {
  display: flex; justify-content: space-between; align-items: center;
  margin-bottom: 12px; flex-wrap: wrap; gap: 8px;
}
.toolbar-left { display: flex; gap: 8px; align-items: center; }
.toolbar-right { display: flex; gap: 6px; align-items: center; }
.chip-wrap { display: inline-flex; align-items: center; }

.adj-table { font-size: var(--wp-font-size, 13px); margin-bottom: 12px; }
.amt-input { width: 100%; }
.amt-cell { display: block; text-align: right; }

.balance-bar {
  display: flex; align-items: center; gap: 24px;
  padding: 10px 14px; margin-bottom: 12px;
  background: var(--el-fill-color-lighter);
  border-radius: 6px;
}
.balance-row { display: flex; align-items: center; gap: 6px; }
.balance-label { color: var(--el-text-color-secondary); font-size: 12px; }
.balance-value { font-weight: 600; font-variant-numeric: tabular-nums; }
.balance-status { font-weight: 600; font-size: var(--wp-font-size, 13px); margin-left: auto; }
.balance-status.balanced { color: #67c23a; }
.balance-status.unbalanced { color: #f56c6c; }

.action-bar { display: flex; align-items: center; margin-bottom: 12px; }
.audit-note-card { margin-bottom: 12px; }
.edit-tips { margin-top: 12px; font-size: 12px; color: var(--el-text-color-secondary); }
.edit-tips summary { cursor: pointer; font-weight: 500; }
.edit-tips ul { padding-left: 20px; margin-top: 8px; }
</style>
