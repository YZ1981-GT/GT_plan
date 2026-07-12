<template>
  <div class="h5-tab-adjustment">
    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="section-title">
          <span>H5-3 调整分录</span>
          <div class="title-actions">
            <el-button size="small" type="primary" link @click="handleAiGenerate">
              <el-icon><MagicStick /></el-icon> AI说明
            </el-button>
            <el-button size="small" type="default" link @click="handleReview('H5-3')">
              💬 复核
            </el-button>
          </div>
        </div>
      </template>

      <!-- 借贷平衡状态 -->
      <div class="balance-bar">
        <span>借方合计: <b>{{ fmtAmt(state.totalDebit.value) }}</b></span>
        <span>贷方合计: <b>{{ fmtAmt(state.totalCredit.value) }}</b></span>
        <el-tag :type="state.isBalanced.value ? 'success' : 'danger'" size="small">
          {{ state.isBalanced.value ? '借贷平衡 ✓' : `差额 ${fmtAmt(state.balanceDiff.value)}` }}
        </el-tag>
      </div>

      <el-table :data="state.entries.value" border stripe size="small" class="adj-table">
        <el-table-column prop="entryNo" label="编号" width="70" align="center">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.entryNo" size="small"
              @change="state.updateEntry(row.rowId, 'entryNo', $event)" />
            <span v-else>{{ row.entryNo }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="type" label="类型" width="80" align="center">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" v-model="row.type" size="small"
              @change="state.updateEntry(row.rowId, 'type', $event)">
              <el-option label="AJE" value="AJE" />
              <el-option label="RJE" value="RJE" />
            </el-select>
            <el-tag v-else :type="row.type === 'AJE' ? 'danger' : 'warning'" size="small">{{ row.type }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="accountCode" label="科目代码" min-width="90">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.accountCode" size="small"
              @change="state.updateEntry(row.rowId, 'accountCode', $event)" />
            <span v-else>{{ row.accountCode }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="accountName" label="科目名称" min-width="110">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.accountName" size="small"
              @change="state.updateEntry(row.rowId, 'accountName', $event)" />
            <span v-else>{{ row.accountName }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="description" label="摘要" min-width="130">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.description" size="small"
              @change="state.updateEntry(row.rowId, 'description', $event)" />
            <span v-else>{{ row.description }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="debitAmount" label="借方金额" min-width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.debitAmount" :controls="false" size="small"
              @change="state.updateEntry(row.rowId, 'debitAmount', $event ?? 0)" />
            <span v-else class="amount-cell">{{ fmtAmt(row.debitAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="creditAmount" label="贷方金额" min-width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.creditAmount" :controls="false" size="small"
              @change="state.updateEntry(row.rowId, 'creditAmount', $event ?? 0)" />
            <span v-else class="amount-cell">{{ fmtAmt(row.creditAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="preparedBy" label="编制人" width="80">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.preparedBy" size="small"
              @change="state.updateEntry(row.rowId, 'preparedBy', $event)" />
            <span v-else>{{ row.preparedBy }}</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="60" align="center" v-if="!isReadonly">
          <template #default="{ row }">
            <el-button type="danger" link size="small" @click="state.removeEntry(row.rowId)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 操作 -->
    <div class="action-bar" v-if="!isReadonly">
      <el-button size="small" @click="state.addEntry('AJE')">+ AJE</el-button>
      <el-button size="small" @click="state.addEntry('RJE')">+ RJE</el-button>
      <el-button type="primary" size="small" :disabled="!state.isBalanced.value" @click="state.publishAdjustment()">
        发布到A13
      </el-button>
    </div>

    <!-- 审计说明 -->
    <el-card shadow="never" class="note-card">
      <template #header>
        <div class="section-title"><span>审计说明</span></div>
      </template>
      <el-input v-model="state.auditNote.value" type="textarea" :autosize="{ minRows: 2, maxRows: 6 }"
        placeholder="请填写调整分录说明..." :disabled="isReadonly" @blur="state.saveNote(state.auditNote.value)" />
    </el-card>

    <details class="compile-hint">
      <summary>编制提示</summary>
      <ul>
        <li>调整分录必须借贷平衡后才能发布到A13错报汇总</li>
        <li>AJE=审计调整分录，RJE=重分类调整分录</li>
        <li>发布后触发EventBus事件 adjustment:created → A13自动接收</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
import { computed, inject, toRef } from 'vue'
import { MagicStick } from '@element-plus/icons-vue'
import { useH5Adjustment } from '../../composables/useH5Adjustment'
import { useH5FormData } from '../../composables/useH5FormData'
import { eventBus } from '@/utils/eventBus'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})
const allResponsesRef = computed(() => props.allResponses)

const formData = useH5FormData({ wpId: toRef(props, 'wpId'), projectId: toRef(props, 'projectId') })

const state = useH5Adjustment({
  allResponses: allResponsesRef as any,
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  onSave: (itemId: string, value: any) => formData.setResponse(itemId, value),
  onPublishEvent: (event: string, payload: any) => {
    // Emit adjustment:created → A13 via real EventBus
    eventBus.emit(event as any, { ...payload, timestamp: Date.now() })
  },
})

function handleAiGenerate() { /* AI */ }
function handleReview(id: string) { openReviewDialog(id) }
function fmtAmt(val: number | null | undefined): string {
  if (val == null) return '-'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.h5-tab-adjustment { padding: 16px; font-size: var(--wp-font-size, 13px); }
.block-card { margin-bottom: 16px; }
.section-title { display: flex; align-items: center; justify-content: space-between; }
.title-actions { display: flex; gap: 8px; }
.balance-bar { display: flex; align-items: center; gap: 16px; margin-bottom: 12px; font-size: var(--wp-font-size, 13px); }
.adj-table { font-size: var(--wp-font-size, 13px); }
.amount-cell { font-variant-numeric: tabular-nums; }
.action-bar { margin: 12px 0; display: flex; gap: 8px; }
.note-card { margin-bottom: 16px; }
.compile-hint { margin-top: 12px; font-size: 12px; color: var(--el-text-color-secondary); }
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ul { padding-left: 20px; margin-top: 8px; }
</style>
