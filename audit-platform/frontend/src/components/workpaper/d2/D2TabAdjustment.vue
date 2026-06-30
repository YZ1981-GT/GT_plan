<script setup lang="ts">
/**
 * D2TabAdjustment — 调整分录D2-4
 * 10列, 新增/删除, 借贷平衡检查, 推送至A13
 */
import { ref, inject, toRef, type Ref } from 'vue'
import { useD2Adjustment, type AdjustmentEntry } from '../composables/useD2Adjustment'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const emit = defineEmits<{
  (e: 'export-template'): void
  (e: 'export-data'): void
  (e: 'import-data'): void
}>()

const displayPrefs = inject<{ fmtAmount: (v: number) => string }>('displayPrefs', {
  fmtAmount: (v: number) => v === 0 ? '-' : v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }),
})

// 复核对话集成 (Task 47.1)
const openReviewDialog = inject<((sectionId: string) => void) | null>('openReviewDialog', null)

function handleCellContextMenu(row: any, column: any, event: MouseEvent): void {
  if (!openReviewDialog) return
  event.preventDefault()
  const field = column?.property || 'unknown'
  const rowKey = row?.index || 'unknown'
  openReviewDialog(`D2-adjustment-${rowKey}-${field}`)
}

const viewMode = defineModel<'structured' | 'online'>('viewMode', { default: 'structured' })
const selectedRows = ref<string[]>([])

const {
  entries,
  debitTotal,
  creditTotal,
  isBalanced,
  balanceDiff,
  addEntry,
  removeEntry,
  updateEntry,
  pushToA13,
} = useD2Adjustment({
  wpId: toRef(props, 'wpId') as Ref<string>,
  projectId: toRef(props, 'projectId') as Ref<string>,
  allResponses: toRef(props, 'allResponses') as Ref<Map<string, any>>,
  isReadonly: toRef(props, 'isReadonly') as Ref<boolean>,
})

function handleSelection(selection: AdjustmentEntry[]) {
  selectedRows.value = selection.map(e => e.rowId)
}

function handlePushToA13() {
  pushToA13(selectedRows.value)
}
</script>

<template>
  <div class="d2-tab-adjustment">
    <div class="tab-toolbar">
      <div class="toolbar-left">
        <el-button size="small" @click="emit('export-template')">导出模板</el-button>
        <el-button size="small" @click="emit('export-data')">导出数据</el-button>
        <el-button size="small" @click="emit('import-data')">导入数据</el-button>
        <el-button size="small" type="primary" :disabled="isReadonly" @click="addEntry">
          新增调整分录
        </el-button>
        <el-button
          size="small"
          type="warning"
          :disabled="selectedRows.length === 0"
          @click="handlePushToA13"
        >推送至A13</el-button>
      </div>
      <div class="toolbar-right">
        <el-segmented v-model="viewMode" :options="[
          { label: '结构化视图', value: 'structured' },
          { label: '在线编辑', value: 'online' },
        ]" size="small" />
      </div>
    </div>

    <el-table
      :data="entries"
      border
      size="small"
      style="width: 100%"
      @selection-change="handleSelection"
    >
      <el-table-column type="selection" width="40" />
      <el-table-column label="调整事项" min-width="160">
        <template #default="{ row }">
          <el-input
            v-if="!isReadonly"
            :model-value="row.description"
            size="small"
            @change="(v: string) => updateEntry(row.rowId, 'description', v)"
          />
          <span v-else>{{ row.description || '-' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="类别" width="90">
        <template #default="{ row }">
          <el-select
            v-if="!isReadonly"
            :model-value="row.entryType"
            size="small"
            @change="(v: string) => updateEntry(row.rowId, 'entryType', v)"
          >
            <el-option label="AJE" value="AJE" />
            <el-option label="RJE" value="RJE" />
          </el-select>
          <el-tag v-else :type="row.entryType === 'AJE' ? 'primary' : 'warning'" size="small">{{ row.entryType }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="报表项目" width="120">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.reportItem" size="small" @change="(v: string) => updateEntry(row.rowId, 'reportItem', v)" />
          <span v-else>{{ row.reportItem || '-' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="科目名称" width="120">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.accountName" size="small" @change="(v: string) => updateEntry(row.rowId, 'accountName', v)" />
          <span v-else>{{ row.accountName || '-' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="附注项目" width="100">
        <template #default="{ row }">{{ row.noteItem || '-' }}</template>
      </el-table-column>
      <el-table-column label="借方金额" width="120" align="right">
        <template #default="{ row }">
          <el-input-number
            v-if="!isReadonly"
            :model-value="row.debitAmount"
            size="small"
            :controls="false"
            :precision="2"
            @change="(v: number) => updateEntry(row.rowId, 'debitAmount', v)"
          />
          <span v-else>{{ displayPrefs.fmtAmount(row.debitAmount) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="贷方金额" width="120" align="right">
        <template #default="{ row }">
          <el-input-number
            v-if="!isReadonly"
            :model-value="row.creditAmount"
            size="small"
            :controls="false"
            :precision="2"
            @change="(v: number) => updateEntry(row.rowId, 'creditAmount', v)"
          />
          <span v-else>{{ displayPrefs.fmtAmount(row.creditAmount) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="索引" width="80">
        <template #default="{ row }">{{ row.indexRef || '-' }}</template>
      </el-table-column>
      <el-table-column label="操作" width="60" v-if="!isReadonly">
        <template #default="{ row }">
          <el-button type="danger" link size="small" @click="removeEntry(row.rowId)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 平衡行 -->
    <div class="balance-bar" :class="{ balanced: isBalanced, unbalanced: !isBalanced }">
      <span>借方合计: {{ displayPrefs.fmtAmount(debitTotal) }}</span>
      <span>贷方合计: {{ displayPrefs.fmtAmount(creditTotal) }}</span>
      <span v-if="isBalanced" class="balance-status">✓ 平衡</span>
      <span v-else class="balance-status">✗ 不平衡：差额{{ displayPrefs.fmtAmount(balanceDiff) }}</span>
    </div>
  </div>
</template>

<style scoped>
.d2-tab-adjustment { padding: 12px; }
.tab-toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.toolbar-left { display: flex; gap: 8px; }
.balance-bar {
  display: flex; gap: 24px; align-items: center;
  padding: 10px 12px; margin-top: 10px;
  border-radius: 4px; font-size: 13px; font-weight: 600;
}
.balance-bar.balanced { background: #f0f9eb; border: 1px solid #e1f3d8; }
.balance-bar.unbalanced { background: #fef0f0; border: 1px solid #fde2e2; }
.balance-status { margin-left: auto; }
.balanced .balance-status { color: #67c23a; }
.unbalanced .balance-status { color: #f56c6c; }
</style>
