<template>
  <div class="h8-tab-adjustment">
    <!-- 审计目标 -->
    <el-alert type="info" :closable="false" show-icon class="objective-alert"
      title="审计目标：确认使用权资产相关审计调整(AJE)与重分类(RJE)分录借贷平衡、依据充分，并已正确同步至 H8-1 审定表及 A13。" />

    <!-- 方法论上下文 -->
    <div class="methodology-context">
      <p>H8-3调整分录汇总：记录审计调整(AJE)和重分类(RJE)分录。借贷必须平衡，调整结果双向同步H8-1审定表。</p>
    </div>

    <!-- 索引 + 行数 -->
    <div class="h8-tab-toolbar">
      <GtIndexChip value="wp:H8-3" />
      <el-tag size="small" type="info">共 {{ rows.length }} 行</el-tag>
    </div>

    <!-- 标题行 -->
    <div class="section-header">
      <span class="section-title-text">调整分录汇总表</span>
      <div class="title-actions">
        <el-button v-if="!isReadonly" size="small" @click="handleAddAJE">+ AJE</el-button>
        <el-button v-if="!isReadonly" size="small" @click="handleAddRJE">+ RJE</el-button>
        <el-button size="small" type="primary" plain @click="$emit('open-ai', 'adjustment')">AI 辅助</el-button>
        <el-button size="small" @click="$emit('open-review', 'adjustment')">复核</el-button>
      </div>
    </div>

    <!-- 借贷平衡指示 -->
    <div class="balance-indicator" :class="balanceCheck.isBalanced ? 'balanced' : 'unbalanced'">
      <span v-if="balanceCheck.isBalanced">✓ 借贷平衡</span>
      <span v-else>⚠ {{ balanceCheck.warning }}</span>
      <span class="balance-amounts">
        借方合计：{{ fmtAmt(debitTotal) }} | 贷方合计：{{ fmtAmt(creditTotal) }}
      </span>
    </div>

    <!-- 调整分录表 -->
    <el-table :data="rows" border size="small" class="adj-table" show-summary :summary-method="getSummary">
      <el-table-column prop="seq" label="序号" width="50" align="center" />
      <el-table-column prop="summary" label="摘要" min-width="150">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" v-model="row.summary" size="small" @change="onCell(row.rowId, 'summary', row.summary)" />
          <span v-else>{{ row.summary }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="accountCode" label="科目编码" width="100">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" v-model="row.accountCode" size="small" @change="onCell(row.rowId, 'accountCode', row.accountCode)" />
          <span v-else>{{ row.accountCode }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="accountName" label="科目名称" width="130">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" v-model="row.accountName" size="small" @change="onCell(row.rowId, 'accountName', row.accountName)" />
          <span v-else>{{ row.accountName }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="debitAmount" label="借方金额" width="120" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly" v-model="row.debitAmount" :controls="false" size="small"
            @change="(v: number | undefined) => onCell(row.rowId, 'debitAmount', v)" />
          <span v-else>{{ fmtAmt(row.debitAmount) }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="creditAmount" label="贷方金额" width="120" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly" v-model="row.creditAmount" :controls="false" size="small"
            @change="(v: number | undefined) => onCell(row.rowId, 'creditAmount', v)" />
          <span v-else>{{ fmtAmt(row.creditAmount) }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="adjustType" label="类型" width="80" align="center">
        <template #default="{ row }">
          <el-tag :type="row.adjustType === 'AJE' ? 'primary' : 'warning'" size="small">
            {{ row.adjustType }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="counterAccount" label="对方科目" width="120">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" v-model="row.counterAccount" size="small" @change="onCell(row.rowId, 'counterAccount', row.counterAccount)" />
          <span v-else>{{ row.counterAccount }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="remark" label="备注" min-width="120">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" v-model="row.remark" size="small" @change="onCell(row.rowId, 'remark', row.remark)" />
          <span v-else>{{ row.remark }}</span>
        </template>
      </el-table-column>
      <el-table-column v-if="!isReadonly" label="" width="50" align="center">
        <template #default="{ row }">
          <el-button type="danger" link size="small" @click="handleDelete(row.rowId)">✕</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 发布同步 -->
    <div v-if="!isReadonly" class="publish-area">
      <el-button type="primary" size="small" @click="handlePublish" :disabled="!balanceCheck.isBalanced">
        同步至H8-1审定表 + 推送A13
      </el-button>
      <span v-if="!balanceCheck.isBalanced" class="publish-hint">借贷不平衡时不可同步</span>
    </div>

    <!-- 审计说明 -->
    <el-card shadow="never" class="audit-note-card">
      <template #header><span class="card-title">审计说明</span></template>
      <el-input type="textarea" :model-value="auditNote" :disabled="isReadonly"
        :autosize="{ minRows: 5 }" placeholder="请输入审计说明..." @change="saveAuditNote" />
    </el-card>

    <!-- 审计结论 -->
    <el-card shadow="never" class="audit-conclusion-card">
      <template #header><span class="card-title">审计结论</span></template>
      <el-input type="textarea" :model-value="auditConclusion" :disabled="isReadonly"
        :autosize="{ minRows: 3 }" placeholder="请输入审计结论..." @change="saveAuditConclusion" />
    </el-card>

    <!-- 编制提示 -->
    <details class="compile-hint">
      <summary>编制提示</summary>
      <ul>
        <li>AJE=审计调整分录，RJE=重分类调整分录，分别标注类型</li>
        <li>每笔分录借贷必须平衡，借方合计=贷方合计方可同步</li>
        <li>同步后调整结果双向影响 H8-1 审定表审定数（未审+AJE+RJE）</li>
        <li>使用权资产相关科目：1901使用权资产、累计折旧、租赁负债、使用权资产减值准备</li>
        <li>借贷不平衡时"同步"按钮禁用，须先修正后再推送 A13</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * H8TabAdjustment.vue — H8-3 调整分录（10列+借贷平衡+EventBus）
 * Spec: Task 4.3 | Requirements: 3.4
 */
import { ref, toRef, watch } from 'vue'
import { useH8Adjustment } from '../../composables/useH8Adjustment'
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
}>()

const {
  rows, debitTotal, creditTotal, balanceCheck, ajeNet, rjeNet,
  addRow, deleteRow, updateCell, publishAdjustment,
} = useH8Adjustment({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  allResponses: toRef(props, 'allResponses'),
  onSave: (itemId, value) => emit('save', itemId, value),
  onPublishAdjustment: (aje, rje) => {
    // EventBus已在composable内发布
  },
})

// ── 审计说明 / 审计结论（持久化 checklist_responses，conclusion:null）──
const AUDIT_NOTE_KEY = 'H8-adjustment-audit-note'
const AUDIT_CONCLUSION_KEY = 'H8-adjustment-audit-conclusion'
const auditNote = ref('')
const auditConclusion = ref('')
function _hydrateAudit() {
  const n = props.allResponses.get(AUDIT_NOTE_KEY)
  if (n?.remark != null) auditNote.value = n.remark
  const c = props.allResponses.get(AUDIT_CONCLUSION_KEY)
  if (c?.remark != null) auditConclusion.value = c.remark
}
_hydrateAudit()
watch(() => props.allResponses, _hydrateAudit)
function saveAuditNote(val: string) {
  if (props.isReadonly) return
  auditNote.value = val
  emit('save', AUDIT_NOTE_KEY, val)
}
function saveAuditConclusion(val: string) {
  if (props.isReadonly) return
  auditConclusion.value = val
  emit('save', AUDIT_CONCLUSION_KEY, val)
}

function fmtAmt(v: number): string {
  if (v === 0) return '-'
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function onCell(rowId: string, field: string, value: any) {
  updateCell(rowId, field, value)
}

function handleAddAJE() { addRow('AJE') }
function handleAddRJE() { addRow('RJE') }
function handleDelete(rowId: string) { deleteRow(rowId) }
function handlePublish() { publishAdjustment() }

function getSummary({ columns }: any) {
  return columns.map((_: any, idx: number) => {
    if (idx === 0) return '合计'
    if (idx === 4) return fmtAmt(debitTotal.value)
    if (idx === 5) return fmtAmt(creditTotal.value)
    return ''
  })
}
</script>

<style scoped>
.h8-tab-adjustment { padding: 16px; font-size: var(--wp-font-size, 13px); }

.objective-alert { margin-bottom: 12px; }
.audit-note-card, .audit-conclusion-card { margin-bottom: 16px; }
.card-title { font-weight: 600; }

.methodology-context {
  background: #fffbeb; border-left: 4px solid #f59e0b; padding: 10px 14px;
  border-radius: 0 6px 6px 0; margin-bottom: 16px; font-size: 12px; color: #92400e;
}

.h8-tab-toolbar { display: flex; align-items: center; gap: 8px; margin-bottom: 12px; }

.compile-hint { margin-top: 12px; font-size: 12px; color: var(--el-text-color-secondary); }
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ul { padding-left: 20px; margin-top: 8px; }

.section-header {
  display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px;
}
.section-title-text { font-weight: 600; font-size: 14px; }
.title-actions { display: flex; gap: 6px; }

.balance-indicator {
  display: flex; align-items: center; justify-content: space-between;
  padding: 8px 14px; border-radius: 6px; margin-bottom: 12px; font-size: var(--wp-font-size, 13px);
}
.balance-indicator.balanced { background: #f0f9eb; color: #67c23a; border: 1px solid #c2e7b0; }
.balance-indicator.unbalanced { background: #fef0f0; color: #f56c6c; border: 1px solid #fbc4c4; }
.balance-amounts { font-size: 12px; opacity: 0.8; }

.adj-table { font-size: var(--wp-font-size, 13px); margin-bottom: 12px; }

.publish-area { display: flex; align-items: center; gap: 12px; margin-top: 12px; }
.publish-hint { font-size: 12px; color: var(--el-text-color-secondary); }
</style>
