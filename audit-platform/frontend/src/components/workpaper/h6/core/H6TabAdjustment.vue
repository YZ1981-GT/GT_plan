<template>
  <div class="h6-tab-adjustment">
    <!-- 审计目标 -->
    <el-alert
      type="info"
      :closable="false"
      show-icon
      class="objective-alert"
      title="审计目标：核实固定资产清理相关审计调整分录（AJE）与重分类调整分录（RJE）借贷平衡、依据充分，确认调整已正确联动 H6-1 审定表 AJE/RJE 列并汇总至 A13 错报，保证清理事项列报恰当。"
    />

    <!-- 方法论上下文 -->
    <div class="methodology-context">
      <p>H6-3调整分录：记录固定资产清理审计过程中发现的审计调整分录(AJE)和重分类调整分录(RJE)。调整分录必须借贷平衡，保存后自动联动H6-1审定表AJE/RJE列，并通过EventBus发布'adjustment:created'供A13错报汇总消费。</p>
    </div>

    <!-- Section Title -->
    <div class="section-header">
      <span>调整分录汇总 H6-3</span>
      <div class="section-header-actions">
        <el-button size="small" circle @click="openReview('H6-3-adjustment')">💬</el-button>
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
      <el-table-column label="类别" width="90" align="center">
        <template #default="{ row }">
          <el-select v-if="!props.isReadonly" v-model="row.entryType" size="small"
            @change="updateCell(row.rowId, 'entryType', $event)">
            <el-option label="AJE" value="AJE" />
            <el-option label="RJE" value="RJE" />
          </el-select>
          <el-tag v-else :type="row.entryType === 'AJE' ? 'danger' : 'warning'" size="small">
            {{ row.entryType }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="科目代码" width="100">
        <template #default="{ row }">
          <el-input v-if="!props.isReadonly" v-model="row.accountCode" size="small"
            @change="updateCell(row.rowId, 'accountCode', $event)" />
          <span v-else>{{ row.accountCode }}</span>
        </template>
      </el-table-column>
      <el-table-column label="科目名称" min-width="110">
        <template #default="{ row }">
          <el-input v-if="!props.isReadonly" v-model="row.accountName" size="small"
            @change="updateCell(row.rowId, 'accountName', $event)" />
          <span v-else>{{ row.accountName }}</span>
        </template>
      </el-table-column>
      <el-table-column label="摘要" min-width="120">
        <template #default="{ row }">
          <el-input v-if="!props.isReadonly" v-model="row.summary" size="small"
            @change="updateCell(row.rowId, 'summary', $event)" />
          <span v-else>{{ row.summary }}</span>
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
          <el-input v-if="!props.isReadonly" v-model="row.refIndex" size="small"
            @change="updateCell(row.rowId, 'refIndex', $event)" />
          <span v-else>{{ row.refIndex }}</span>
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
        <span class="balance-value">{{ fmtAmt(balanceStatus.debitTotal) }}</span>
      </div>
      <div class="balance-row">
        <span class="balance-label">贷方合计：</span>
        <span class="balance-value">{{ fmtAmt(balanceStatus.creditTotal) }}</span>
      </div>
      <div class="balance-status" :class="{ balanced: balanceStatus.isBalanced, unbalanced: !balanceStatus.isBalanced }">
        <span v-if="balanceStatus.isBalanced">✓ 平衡</span>
        <span v-else>✗ 不平衡：差额{{ fmtAmt(balanceStatus.diff) }}</span>
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
            <el-button size="small" circle @click="openReview('H6-3-note')">💬</el-button>
          </div>
        </div>
      </template>
      <el-input v-model="auditNote" type="textarea" :autosize="{ minRows: 5, maxRows: 10 }"
        placeholder="请填写审计说明..." :disabled="props.isReadonly"
        @blur="saveAuditNote" />
    </el-card>

    <!-- 审计结论 -->
    <el-card shadow="never" class="audit-note-card">
      <template #header>
        <div class="section-header" style="margin-bottom:0">
          <span>审计结论</span>
          <div class="section-header-actions">
            <el-button size="small" circle @click="openReview('H6-3-conclusion')">💬</el-button>
          </div>
        </div>
      </template>
      <el-input v-model="auditConclusion" type="textarea" :autosize="{ minRows: 3, maxRows: 8 }"
        placeholder="请填写审计结论..." :disabled="props.isReadonly"
        @blur="saveAuditConclusion" />
    </el-card>

    <!-- 编制提示 -->
    <details class="edit-tips">
      <summary>编制提示</summary>
      <ul>
        <li>AJE=审计调整分录，RJE=重分类调整分录</li>
        <li>借方合计必须等于贷方合计（借贷平衡），不平衡时红色警告</li>
        <li>保存后自动通过EventBus发布'adjustment:created'联动A13错报汇总</li>
        <li>AJE/RJE净额自动同步到H6-1审定表对应列</li>
        <li>科目代码填写1606固定资产清理或相关科目；摘要简要说明调整原因</li>
        <li>过渡科目1606期末应为0，调整应确保清理完毕结转</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * H6TabAdjustment.vue — H6-3 调整分录汇总（10列+借贷平衡+EventBus）
 *
 * 10列: 序号|调整事项说明|类别(AJE/RJE)|科目代码|科目名称|摘要|借方金额|贷方金额|索引|备注
 * 底部: 借贷合计 + 平衡状态(绿"✓平衡"/红"✗不平衡")
 * EventBus: save时publish 'adjustment:created' → A13错报汇总
 * Sync: AJE/RJE净额 → H6-1审定表
 *
 * Spec: .kiro/specs/h6-asset-disposal-clearing/
 * Task: 4.4
 * Requirements: 4.1-4.2
 */
import { ref, computed, inject, toRef, onMounted } from 'vue'
import { useH6Adjustment } from '../../composables/useH6Adjustment'
import { useH6ImportExport } from '../../composables/useH6ImportExport'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})
// 父入口提供的持久化函数（更新共享 Map + 防抖 PUT checklist-responses）。Bug C 修复：此前仅写内存 Map。
const saveResponse = inject<(itemId: string, value: any) => void>('saveResponse', (itemId, value) => {
  const strVal = value != null ? (typeof value === 'string' ? value : JSON.stringify(value)) : null
  props.allResponses.set(itemId, { item_id: itemId, remark: strVal, conclusion: null })
})
const saving = ref(false)

// ─── Composable ──────────────────────────────────────────────────────────────
const allResponsesRef = computed(() => props.allResponses)

const {
  rows, balanceStatus, ajeTotalNet, rjeTotalNet,
  addRow, deleteRow, updateCell, save, publishAndSync,
} = useH6Adjustment({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  allResponses: allResponsesRef as any,
  onSave: (itemId: string, value: any) => saveResponse(itemId, value),
  onPublishEvent: (event: string, payload: any) => {
    window.dispatchEvent(new CustomEvent(event, { detail: payload }))
  },
  onSyncToAdjudication: (ajeNet: number, rjeNet: number) => {
    // 同步AJE/RJE净额到H6-1审定表（通过allResponses共享 + 持久化）
    saveResponse('H6-3-aje-net', String(ajeNet))
    saveResponse('H6-3-rje-net', String(rjeNet))
  },
})

const importExport = useH6ImportExport({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  onImported: () => {
    // 导入完成后重新加载 — composable的watch(allResponses)自动触发
  },
})

// ─── Audit Note ──────────────────────────────────────────────────────────────
const auditNote = ref('')
const auditConclusion = ref('')

onMounted(() => {
  const noteItem = props.allResponses.get('H6-3-note')
  if (noteItem?.remark) auditNote.value = noteItem.remark
  const concItem = props.allResponses.get('H6-3-conclusion')
  if (concItem?.remark) auditConclusion.value = concItem.remark
})

function saveAuditNote() {
  saveResponse('H6-3-note', auditNote.value)
}
function saveAuditConclusion() {
  saveResponse('H6-3-conclusion', auditConclusion.value)
}

// ─── Actions ─────────────────────────────────────────────────────────────────

function handleAddRow() {
  addRow()
}

function handleDeleteRow(rowId: string) {
  deleteRow(rowId)
}

async function handleSave() {
  saving.value = true
  try {
    save()
    publishAndSync()
  } finally {
    saving.value = false
  }
}

function handleImportExport(command: string) {
  if (command === 'export-template') importExport.exportTemplate('H6-3')
  else if (command === 'export-data') importExport.exportData('H6-3')
  else if (command === 'import-data') {
    const input = document.createElement('input')
    input.type = 'file'
    input.accept = '.xlsx,.xls,.csv'
    input.onchange = (e: Event) => {
      const file = (e.target as HTMLInputElement).files?.[0]
      if (file) importExport.importData('H6-3', file)
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
.h6-tab-adjustment { padding: 16px; font-size: var(--wp-font-size, 13px); }

.objective-alert { margin-bottom: 12px; }

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
