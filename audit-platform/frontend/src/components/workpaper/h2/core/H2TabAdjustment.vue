<template>
  <div class="h2-tab-adjustment">
    <!-- 审计目标 -->
    <el-alert type="info" :closable="false" class="objective-alert"
      title="审计目标：登记在建工程相关审计调整（AJE）与重分类调整（RJE）分录，确保借贷平衡，并推送至 A13 汇总以更新 H2-1 审定表的账项调整。" />

    <!-- 工具栏 -->
    <div class="tab-toolbar">
      <div class="toolbar-right">
        <span class="chip-wrap"><GtIndexChip value="wp:H2-3" :context-project-id="projectId" /></span>
        <el-tag size="small" type="info">共 {{ state.rows.value.length }} 条分录</el-tag>
      </div>
    </div>

    <!-- 调整分录表 -->
    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="section-header">
          <span>调整分录（H2-3）</span>
          <div class="section-header-actions">
            <el-tag :type="isBalanced ? 'success' : 'danger'" size="small">
              {{ isBalanced ? '✓ 借贷平衡' : '✗ 借贷不平衡' }}
            </el-tag>
            <el-button size="small" circle @click="openReview('H2-3')">💬</el-button>
          </div>
        </div>
      </template>

      <el-table :data="state.rows.value" border stripe size="small" class="adj-table">
        <el-table-column prop="seq" label="序号" width="50" align="center">
          <template #default="{ $index }">{{ $index + 1 }}</template>
        </el-table-column>
        <el-table-column prop="entryType" label="类型" width="80" align="center">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" v-model="row.entryType" size="small" style="width:70px"
              @change="onCellChange(row.rowId, 'entryType', $event)">
              <el-option label="AJE" value="AJE" />
              <el-option label="RJE" value="RJE" />
            </el-select>
            <span v-else>{{ row.entryType }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="date" label="日期" min-width="110">
          <template #default="{ row }">
            <el-date-picker v-if="!isReadonly" v-model="row.date" type="date" size="small"
              value-format="YYYY-MM-DD" style="width:100%"
              @change="onCellChange(row.rowId, 'date', $event)" />
            <span v-else>{{ row.date || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="summary" label="摘要" min-width="180">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.summary" size="small"
              @change="onCellChange(row.rowId, 'summary', $event)" />
            <span v-else>{{ row.summary || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="accountCode" label="科目编码" min-width="100">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.accountCode" size="small"
              @change="onCellChange(row.rowId, 'accountCode', $event)" />
            <span v-else>{{ row.accountCode || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="accountName" label="科目名称" min-width="120">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.accountName" size="small"
              @change="onCellChange(row.rowId, 'accountName', $event)" />
            <span v-else>{{ row.accountName || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="debit" label="借方金额" min-width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.debit" :controls="false" size="small"
              class="amt-input" @change="onCellChange(row.rowId, 'debit', $event)" />
            <span v-else class="amt-cell">{{ fmtAmt(row.debit) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="credit" label="贷方金额" min-width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.credit" :controls="false" size="small"
              class="amt-input" @change="onCellChange(row.rowId, 'credit', $event)" />
            <span v-else class="amt-cell">{{ fmtAmt(row.credit) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="reason" label="调整原因" min-width="150">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.reason" size="small"
              @change="onCellChange(row.rowId, 'reason', $event)" />
            <span v-else>{{ row.reason || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="" width="50" v-if="!isReadonly">
          <template #default="{ row }">
            <el-button size="small" type="danger" link @click="handleRemove(row.rowId)">✕</el-button>
          </template>
        </el-table-column>
      </el-table>

      <!-- 合计行 -->
      <div class="balance-summary">
        <span>借方合计: <strong>{{ fmtAmt(state.debitTotal.value) }}</strong></span>
        <span style="margin:0 24px">贷方合计: <strong>{{ fmtAmt(state.creditTotal.value) }}</strong></span>
        <span :class="{ 'error-amount': !isBalanced }">
          差额: {{ fmtAmt(state.debitTotal.value - state.creditTotal.value) }}
        </span>
      </div>

      <!-- 新增行 + 推送 -->
      <div class="action-bar" v-if="!isReadonly">
        <el-button size="small" @click="handleAddRow">+ 新增分录</el-button>
        <el-button size="small" type="primary" @click="handlePushA13" :disabled="!isBalanced">
          推送至 A13
        </el-button>
      </div>
    </el-card>

    <!-- 审计说明 -->
    <el-card shadow="never" class="audit-note-card">
      <template #header>
        <div class="section-header"><span>审计说明</span></div>
      </template>
      <el-input v-model="state.auditNote.value" type="textarea" :autosize="{ minRows: 5 }"
        placeholder="填写审计说明：概述各笔调整分录的调整依据、性质（AJE/RJE）与影响科目、金额。" :disabled="isReadonly"
        @blur="state.saveNote(state.auditNote.value)" />
    </el-card>

    <!-- 审计结论 -->
    <el-card shadow="never" class="audit-note-card">
      <template #header>
        <div class="section-header"><span>审计结论</span></div>
      </template>
      <el-input :model-value="auditConclusion" type="textarea" :autosize="{ minRows: 3 }"
        placeholder="填写审计结论：如调整分录已借贷平衡、依据充分并经复核推送 A13，未见异常。" :disabled="isReadonly"
        @change="saveAuditConclusion" />
    </el-card>

    <!-- 编制提示 -->
    <details class="edit-tips">
      <summary>编制提示</summary>
      <ul>
        <li>AJE=审计调整分录，RJE=重分类调整分录</li>
        <li>借贷必须平衡后才能推送至A13汇总</li>
        <li>科目1604在建工程为借方科目(资产类)</li>
        <li>推送A13后，审定表H2-1的账项调整会自动更新</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * H2TabAdjustment.vue — H2-3 调整分录
 * el-table 10列 + 借贷平衡(✓平衡/✗不平衡) + 推送A13
 * Spec: Task 4.4 | Requirements: 4.1-4.8
 */
import { ref, computed, inject, toRef, onMounted } from 'vue'
import { MagicStick } from '@element-plus/icons-vue'
import { useH2Adjustment } from '../../composables/useH2Adjustment'
import GtIndexChip from '../../GtIndexChip.vue'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})
const saveResponse = inject<(id: string, val: any) => void>('saveResponse', () => {})

const state = useH2Adjustment({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  allResponses: computed(() => props.allResponses),
  isReadonly: toRef(props, 'isReadonly'),
  onSave: (itemId: string, value: any) => saveResponse(itemId, value),
})

const isBalanced = computed(() => state.isBalanced.value)

// H2-3 审计结论：composable 仅含审计说明（note），此处补本地审计结论 item_id。
const CONCLUSION_KEY = 'H2-3-audit-conclusion'
const auditConclusion = ref('')
function saveAuditConclusion(val: string): void {
  if (props.isReadonly) return
  auditConclusion.value = val
  props.allResponses.set(CONCLUSION_KEY, { item_id: CONCLUSION_KEY, conclusion: null, remark: val })
  saveResponse(CONCLUSION_KEY, val)
}
onMounted(() => {
  const c = props.allResponses.get(CONCLUSION_KEY)
  if (c?.remark) auditConclusion.value = c.remark
})

function onCellChange(rowId: string, field: string, value: any) {
  state.updateCell(rowId, field, value)
}

function handleAddRow() {
  state.addRow()
}

function handleRemove(rowId: string) {
  state.removeRow(rowId)
}

function handlePushA13() {
  state.pushToA13(state.rows.value.map(r => r.rowId))
}


function openReview(id: string) {
  openReviewDialog(id)
}

function fmtAmt(val: number | null | undefined): string {
  if (val == null) return '-'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.h2-tab-adjustment { padding: 16px; font-size: var(--wp-font-size, 13px); }
.objective-alert { margin-bottom: 12px; }
.tab-toolbar { display: flex; justify-content: flex-end; align-items: center; margin-bottom: 8px; gap: 8px; flex-wrap: wrap; }
.toolbar-right { display: flex; gap: 6px; align-items: center; }
.chip-wrap { display: inline-flex; align-items: center; }
.audit-note-card { margin-bottom: 12px; }
.block-card { margin-bottom: 16px; }
.section-header { display: flex; align-items: center; justify-content: space-between; }
.section-header-actions { display: flex; gap: 8px; align-items: center; }
.adj-table { font-size: var(--wp-font-size, 13px); }
.amt-cell { font-variant-numeric: tabular-nums; }
.amt-input { width: 100%; }
.balance-summary { padding: 12px 0; font-size: var(--wp-font-size, 13px); border-top: 1px solid var(--el-border-color-lighter); margin-top: 12px; }
.error-amount { color: var(--el-color-danger); font-weight: 600; }
.action-bar { margin-top: 12px; display: flex; gap: 8px; }
.edit-tips { margin-top: 16px; font-size: 12px; color: var(--el-text-color-secondary); }
.edit-tips summary { cursor: pointer; font-weight: 500; }
.edit-tips ul { padding-left: 20px; margin-top: 8px; }
</style>
