<template>
  <div class="h2-tab-transfer-check">
    <!-- 方法论上下文区域 -->
    <div class="methodology-context">
      <p><strong>CAS4转固五条件（均须满足）：</strong></p>
      <ol>
        <li>该固定资产的购建已经达到预定可使用状态</li>
        <li>与该固定资产的购建相关的经济利益很可能流入企业</li>
        <li>该固定资产的成本能够可靠计量</li>
        <li>归属于该固定资产达到预定可使用状态前所发生的必要支出已能确定</li>
        <li>安装或建造过程中的试运转等结果表明资产能够正常运行</li>
      </ol>
    </div>

    <!-- 转固检查表 -->
    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="section-header">
          <span>转固时点检查表（H2-5）</span>
          <div class="section-header-actions">
            <GtIndexChip value="H1-1" label="→ H1固定资产" />
            <el-button size="small" type="primary" link @click="handleAiGenerate">
              <el-icon><MagicStick /></el-icon> AI
            </el-button>
            <el-button size="small" circle @click="openReview('H2-5')">💬</el-button>
          </div>
        </div>
      </template>

      <el-table :data="state.rows.value" border stripe size="small" class="transfer-table"
        :row-class-name="transferRowClass">
        <el-table-column prop="name" label="工程项目" min-width="130" fixed />
        <el-table-column prop="transferDate" label="转固日期" min-width="100">
          <template #default="{ row }">
            <el-date-picker v-if="!isReadonly" v-model="row.transferDate" type="date" size="small"
              value-format="YYYY-MM-DD" style="width:100%"
              @change="onCellChange(row.rowId, 'transferDate', $event)" />
            <span v-else>{{ row.transferDate || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="conditionsMetDate" label="达到可用状态日" min-width="110">
          <template #default="{ row }">
            <el-date-picker v-if="!isReadonly" v-model="row.conditionsMetDate" type="date" size="small"
              value-format="YYYY-MM-DD" style="width:100%"
              @change="onCellChange(row.rowId, 'conditionsMetDate', $event)" />
            <span v-else>{{ row.conditionsMetDate || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="延迟天数" min-width="80" align="right">
          <template #default="{ row }">
            <span :class="['formula-cell', { 'error-amount': row.delayDays > 180, 'warning-value': row.delayDays > 30 }]"
              :title="`=转固日期-达到可用状态日`">
              {{ row.delayDays ?? '-' }}
            </span>
          </template>
        </el-table-column>
        <el-table-column prop="transferAmount" label="转固金额" min-width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.transferAmount" :controls="false"
              size="small" class="amt-input" @change="onCellChange(row.rowId, 'transferAmount', $event)" />
            <span v-else class="amt-cell">{{ fmtAmt(row.transferAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="assetCategory" label="转入资产类别" min-width="110">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.assetCategory" size="small"
              @change="onCellChange(row.rowId, 'assetCategory', $event)" />
            <span v-else>{{ row.assetCategory || '-' }}</span>
          </template>
        </el-table-column>
        <!-- CAS4五条件 -->
        <el-table-column label="条件①" width="60" align="center">
          <template #default="{ row }">
            <el-checkbox v-model="row.condition1" :disabled="isReadonly"
              @change="onCellChange(row.rowId, 'condition1', $event)" />
          </template>
        </el-table-column>
        <el-table-column label="条件②" width="60" align="center">
          <template #default="{ row }">
            <el-checkbox v-model="row.condition2" :disabled="isReadonly"
              @change="onCellChange(row.rowId, 'condition2', $event)" />
          </template>
        </el-table-column>
        <el-table-column label="条件③" width="60" align="center">
          <template #default="{ row }">
            <el-checkbox v-model="row.condition3" :disabled="isReadonly"
              @change="onCellChange(row.rowId, 'condition3', $event)" />
          </template>
        </el-table-column>
        <el-table-column label="条件④" width="60" align="center">
          <template #default="{ row }">
            <el-checkbox v-model="row.condition4" :disabled="isReadonly"
              @change="onCellChange(row.rowId, 'condition4', $event)" />
          </template>
        </el-table-column>
        <el-table-column label="条件⑤" width="60" align="center">
          <template #default="{ row }">
            <el-checkbox v-model="row.condition5" :disabled="isReadonly"
              @change="onCellChange(row.rowId, 'condition5', $event)" />
          </template>
        </el-table-column>
        <el-table-column label="判定" width="80" align="center">
          <template #default="{ row }">
            <el-tag :type="row.allConditionsMet ? 'success' : 'danger'" size="small">
              {{ row.allConditionsMet ? '满足' : '不满足' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="remark" label="备注说明" min-width="150">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.remark" size="small"
              @change="onCellChange(row.rowId, 'remark', $event)" />
            <span v-else>{{ row.remark || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="" width="50" v-if="!isReadonly">
          <template #default="{ row }">
            <el-button size="small" type="danger" link @click="handleRemove(row.rowId)">✕</el-button>
          </template>
        </el-table-column>
      </el-table>

      <!-- 合计 + 新增 -->
      <div class="summary-line">
        转固合计: <strong>{{ fmtAmt(state.totalTransfer.value) }}</strong>
        <span style="margin-left:24px">满足条件: {{ state.metCount.value }}/{{ state.rows.value.length }}</span>
      </div>
      <div class="add-row-bar" v-if="!isReadonly">
        <el-button size="small" @click="handleAddRow">+ 新增工程</el-button>
        <el-button size="small" type="primary" @click="handlePublishToH1">
          联动 → H1固定资产
        </el-button>
      </div>
    </el-card>

    <!-- 审计说明 -->
    <el-card shadow="never" class="audit-note-card">
      <template #header>
        <div class="section-header">
          <span>审计说明</span>
          <el-button size="small" type="primary" link @click="handleAiGenerate">
            <el-icon><MagicStick /></el-icon> AI生成
          </el-button>
        </div>
      </template>
      <el-input v-model="state.auditNote.value" type="textarea" :autosize="{ minRows: 3, maxRows: 8 }"
        placeholder="请填写审计说明..." :disabled="isReadonly"
        @blur="state.saveNote(state.auditNote.value)" />
    </el-card>

    <!-- 编制提示 -->
    <details class="edit-tips">
      <summary>编制提示</summary>
      <ul>
        <li>CAS4五条件须全部勾选才判定为"满足转固条件"</li>
        <li>延迟>180天为严重延迟（红色高亮），需关注减值</li>
        <li>转固合计应与H2-2明细表的转固列合计一致</li>
        <li>"联动H1"将通过EventBus通知固定资产底稿增加对应资产</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * H2TabTransferCheck.vue — H2-5 转固时点检查
 * el-table 15列 + CAS4五条件判定 + 延迟高亮 + GtIndexChip→H1
 * Spec: Task 4.7 | Requirements: 6.1-6.10
 */
import { inject, toRef, computed } from 'vue'
import { ElMessageBox } from 'element-plus'
import { MagicStick } from '@element-plus/icons-vue'
import { useH2TransferCheck } from '../../composables/useH2TransferCheck'
import GtIndexChip from '../../GtIndexChip.vue'
import http from '@/utils/http'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})

const state = useH2TransferCheck({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  allResponses: computed(() => props.allResponses),
  isReadonly: toRef(props, 'isReadonly'),
  onPublishEvent(event: string, payload: any) {
    // Task 6.6 — publish 'h2:transfer-to-h1' 转固联动H1
    console.log('[H2-5] publish', event, payload)
    // EventBus dispatch via backend SSE broadcast
    http.post(`/api/projects/${props.projectId}/events/publish`, {
      event_type: event,
      payload,
    }, { _silent: true } as any).catch(() => { /* best effort retry */ })
  },
})

function transferRowClass({ row }: any) {
  if (row.delayDays > 180) return 'severe-delay-row'
  if (row.delayDays > 30) return 'delay-row'
  return ''
}

function onCellChange(rowId: string, field: string, value: any) {
  state.updateCell(rowId, field, value)
}

async function handleAddRow() {
  try {
    const { value } = await ElMessageBox.prompt('请输入工程项目名称', '新增转固工程', {
      confirmButtonText: '确认', cancelButtonText: '取消',
      inputPattern: /\S+/, inputErrorMessage: '名称不能为空',
    })
    if (value) state.addRow(value)
  } catch { /* cancelled */ }
}

function handleRemove(rowId: string) {
  state.removeRow(rowId)
}

function handlePublishToH1() {
  state.publishTransferToH1()
}

function handleAiGenerate() {
  console.log('AI generate H2-5')
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
.h2-tab-transfer-check { padding: 16px; font-size: var(--wp-font-size, 13px); }
.methodology-context {
  border-left: 3px solid #f0a020; background: #fdf8e8;
  padding: 12px 16px; margin-bottom: 16px; border-radius: 4px; font-size: var(--wp-font-size, 13px);
}
.methodology-context ol { padding-left: 20px; margin: 8px 0 0; }
.block-card { margin-bottom: 16px; }
.section-header { display: flex; align-items: center; justify-content: space-between; }
.section-header-actions { display: flex; gap: 8px; align-items: center; }
.transfer-table { font-size: var(--wp-font-size, 13px); }
.amt-cell { font-variant-numeric: tabular-nums; }
.amt-input { width: 100%; }
.formula-cell { border-bottom: 1px dashed var(--el-border-color); cursor: help; font-variant-numeric: tabular-nums; }
.warning-value { color: var(--el-color-warning); font-weight: 600; }
.error-amount { color: var(--el-color-danger); font-weight: 600; }
.summary-line { padding: 12px 0; font-size: var(--wp-font-size, 13px); border-top: 1px solid var(--el-border-color-lighter); margin-top: 12px; }
.add-row-bar { margin-top: 12px; display: flex; gap: 8px; }
.audit-note-card { margin-bottom: 12px; }
.edit-tips { margin-top: 16px; font-size: 12px; color: var(--el-text-color-secondary); }
.edit-tips summary { cursor: pointer; font-weight: 500; }
.edit-tips ul { padding-left: 20px; margin-top: 8px; }
:deep(.severe-delay-row) { background-color: #fef0f0 !important; }
:deep(.delay-row) { background-color: #fdf6ec !important; }
</style>
