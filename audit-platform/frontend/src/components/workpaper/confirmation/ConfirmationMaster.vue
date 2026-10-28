<template>
  <div class="confirmation-master">
    <div v-if="!readonly" class="confirmation-master__toolbar">
      <div class="confirmation-master__toolbar-left">
        <el-button type="primary" size="small" @click="$emit('add')">
          <el-icon><Plus /></el-icon> 新增
        </el-button>
        <el-button type="danger" size="small" :disabled="!selectedIds.length" @click="$emit('delete')">
          删除选中
        </el-button>
        <el-button type="success" size="small" @click="$emit('save')">
          保存
        </el-button>
      </div>
      <div class="confirmation-master__toolbar-right">
        <el-button size="small" type="info" plain @click="$emit('show-formula')">fx 公式</el-button>
        <el-button size="small" @click="$emit('download-template')">↓ 导入模板</el-button>
        <el-button size="small" @click="$emit('import-data')">↑ 导入</el-button>
      </div>
    </div>
    <!-- 列表视图=简表概览（核心列）；完整宽表全列见「完整表格」视图（ConfirmationFullGrid）；
         点击行由下方 ConfirmationDetail 编辑全部字段（含 additive 补列） -->
    <el-table
      :data="rows"
      @selection-change="onSelectionChange"
      @row-click="(row) => $emit('row-click', row)"
      highlight-current-row
      border
      size="small"
      table-layout="auto"
      class="confirmation-master__table"
    >
      <el-table-column v-if="!readonly" type="selection" width="36" align="center" />
      <el-table-column prop="seq" label="序号" min-width="45" align="center" />
      <el-table-column prop="confirm_index" label="索引号" min-width="70" />
      <el-table-column prop="entity_name" label="被询证单位" min-width="130" show-overflow-tooltip />
      <el-table-column prop="account_type" label="科目" min-width="80" />
      <el-table-column prop="amount" label="函证金额" min-width="100" align="right">
        <template #default="{ row }">
          {{ fmtAmount(row.amount) }}
        </template>
      </el-table-column>
      <el-table-column prop="match_status" label="相符情况" min-width="70" align="center">
        <template #default="{ row }">
          <el-tag v-if="row.match_status === '相符'" type="success" size="small">相符</el-tag>
          <el-tag v-else-if="row.match_status === '不符'" type="danger" size="small">不符</el-tag>
          <el-tag v-else-if="row.match_status === '未回函'" type="warning" size="small">未回函</el-tag>
          <span v-else>—</span>
        </template>
      </el-table-column>
      <!-- 三态（需求 1.6）：明细面板写的是 '是' / '否'，'否' 是真值 ⇒ 原先裸判显示成「是」；未填显示 — -->
      <el-table-column prop="is_replied" label="回函" min-width="55" align="center">
        <template #default="{ row }">
          <el-tag v-if="isRepliedTrue(row)" type="success" size="small" data-testid="reply-flag">是</el-tag>
          <el-tag v-else-if="isNotReplied(row)" type="info" size="small" data-testid="reply-flag">否</el-tag>
          <span v-else data-testid="reply-flag">—</span>
        </template>
      </el-table-column>
      <!-- 函证附件（spec attachment-confirmation-evidence-loop 需求 1.1）：只读也显示，点开为只读抽屉 -->
      <el-table-column v-if="attachmentCounts" label="函证附件" min-width="96" align="center">
        <template #default="{ row }">
          <el-button
            v-if="row._hub_confirmation_id"
            link
            type="primary"
            size="small"
            data-testid="hub-attachment-count"
            :aria-label="`${row.entity_name || '本行'}的发函件与回函件`"
            @click.stop="$emit('open-attachments', row)"
          >发 {{ countOf(row).outbound }} · 回 {{ countOf(row).inbound }}</el-button>
          <el-tooltip v-else content="尚未同步到函证中心，同步后可挂发函件 / 回函件" placement="top">
            <span class="confirmation-master__muted">未同步</span>
          </el-tooltip>
        </template>
      </el-table-column>
    </el-table>
  </div>
</template>

<script setup lang="ts">
import { Plus } from '@element-plus/icons-vue'
import type { ConfirmationRow } from './confirmationTypes'
import type { HubAttachmentCount } from './composables/useHubAttachmentCounts'
import { isNotReplied, isRepliedTrue } from './replyStatus'

const props = defineProps<{
  rows: ConfirmationRow[]
  readonly: boolean
  selectedIds: string[]
  /** 函证中心附件计数（按 `_hub_confirmation_id`）；不传则不显示「函证附件」列 */
  attachmentCounts?: Record<string, HubAttachmentCount>
}>()

const emit = defineEmits<{
  (e: 'add'): void
  (e: 'delete'): void
  (e: 'save'): void
  (e: 'download-template'): void
  (e: 'import-data'): void
  (e: 'show-formula'): void
  (e: 'row-click', row: ConfirmationRow): void
  (e: 'update:selectedIds', ids: string[]): void
  (e: 'open-attachments', row: ConfirmationRow): void
}>()

function countOf(row: ConfirmationRow): HubAttachmentCount {
  return props.attachmentCounts?.[row._hub_confirmation_id ?? ''] ?? { outbound: 0, inbound: 0 }
}

function onSelectionChange(selection: ConfirmationRow[]) {
  emit('update:selectedIds', selection.map((r) => r._row_id!))
}

/** 平台金额格式（千分符 + 两位小数），与 FullGrid/Detail 一致 */
function fmtAmount(amount: number | undefined | null): string {
  if (amount == null) return '—'
  return amount.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.confirmation-master__toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 10px;
  flex-wrap: wrap;
  gap: 8px;
}
.confirmation-master__toolbar-left {
  display: flex;
  gap: 6px;
}
.confirmation-master__toolbar-right {
  display: flex;
  gap: 6px;
}

.confirmation-master__table {
  width: 100%;
  font-size: 13px;
}

.confirmation-master__muted {
  font-size: 12px;
  color: var(--gt-color-text-tertiary, #909399);
}

/* 表头折行显示 */
.confirmation-master__table :deep(.el-table__header th .cell) {
  white-space: normal;
  word-break: break-all;
  line-height: 1.3;
  font-size: 12px;
}

/* 勾选列居中 */
.confirmation-master__table :deep(.el-table-column--selection .cell) {
  display: flex;
  justify-content: center;
  align-items: center;
  padding: 0;
}

.confirmation-master__table :deep(.el-table__body td .cell) {
  font-size: 12px;
}

/* 数值列等宽对齐+防折行 */
.confirmation-master__table :deep(td.is-right .cell) {
  white-space: nowrap;
  font-variant-numeric: tabular-nums;
}
</style>
