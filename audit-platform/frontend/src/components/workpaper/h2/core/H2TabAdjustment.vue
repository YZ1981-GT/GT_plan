<template>
  <div class="h2-tab-adjustment">
    <!-- 调整分录表 -->
    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="section-header">
          <span>调整分录（H2-3）</span>
          <div class="section-header-actions">
            <el-tag :type="isBalanced ? 'success' : 'danger'" size="small">
              {{ isBalanced ? '✓ 借贷平衡' : '✗ 借贷不平衡' }}
            </el-tag>
            <el-button size="small" type="primary" link @click="handleAiGenerate">
              <el-icon><MagicStick /></el-icon> AI
            </el-button>
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
import { computed, inject, toRef } from 'vue'
import { MagicStick } from '@element-plus/icons-vue'
import { useH2Adjustment } from '../../composables/useH2Adjustment'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})

const state = useH2Adjustment({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  allResponses: computed(() => props.allResponses),
  isReadonly: toRef(props, 'isReadonly'),
})

const isBalanced = computed(() => state.isBalanced.value)

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

function handleAiGenerate() {
  console.log('AI generate H2-3')
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
.h2-tab-adjustment { padding: 16px; font-size: 13px; }
.block-card { margin-bottom: 16px; }
.section-header { display: flex; align-items: center; justify-content: space-between; }
.section-header-actions { display: flex; gap: 8px; align-items: center; }
.adj-table { font-size: 13px; }
.amt-cell { font-variant-numeric: tabular-nums; }
.amt-input { width: 100%; }
.balance-summary { padding: 12px 0; font-size: 13px; border-top: 1px solid var(--el-border-color-lighter); margin-top: 12px; }
.error-amount { color: var(--el-color-danger); font-weight: 600; }
.action-bar { margin-top: 12px; display: flex; gap: 8px; }
.edit-tips { margin-top: 16px; font-size: 12px; color: var(--el-text-color-secondary); }
.edit-tips summary { cursor: pointer; font-weight: 500; }
.edit-tips ul { padding-left: 20px; margin-top: 8px; }
</style>
