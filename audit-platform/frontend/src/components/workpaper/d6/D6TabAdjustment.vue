<template>
<div class="d6-tab-adjustment">
  <!-- 编制提示 -->
  <details class="guidance-details">
    <summary>📋 编制提示</summary>
    <div class="guidance-content">
      <p>1. 调整分录应按实际调整事项逐笔编制，确保借贷平衡。</p>
      <p>2. 账项调整（AJE）影响审定数，重分类调整（RJE）不影响损益。</p>
      <p>3. 合同资产相关调整科目：1402 合同资产 / 1403 合同资产减值准备。</p>
      <p>4. 借贷必须平衡，每笔分录需注明调整事由和索引号；可选中分录推送至 A13 错报汇总表。</p>
    </div>
  </details>

  <!-- 审计目标 -->
  <el-alert
    type="info"
    :closable="false"
    title="审计目标：验证调整分录的准确性与完整性，确认借贷平衡且调整事由充分合理。"
    class="objective-alert"
  />

  <!-- 工具栏 -->
  <div class="tab-toolbar">
    <div class="toolbar-left">
      <el-button size="small" type="primary" :disabled="isReadonly" @click="addRow">+ 新增调整分录</el-button>
      <el-button
        size="small"
        :disabled="isReadonly || selectedRowIds.length === 0"
        @click="handlePushToA13"
      >推送至A13（{{ selectedRowIds.length }}条）</el-button>
      <GtReviewTrigger section-id="D6-4-header" />
    </div>
    <div class="toolbar-right">
      <span class="chip-wrap"><GtIndexChip value="wp:A13" :context-project-id="projectId" /></span>
      <el-tag size="small" type="info">共 {{ rows.length }} 行</el-tag>
    </div>
  </div>

  <el-table
    :data="rows"
    size="small"
    border
    stripe
    @selection-change="onSelectionChange"
  >
    <el-table-column type="selection" width="40" />

    <el-table-column label="调整事项说明" min-width="160">
      <template #default="{ row }">
        <el-input
          v-if="!isReadonly"
          :model-value="row.description"
          size="small"
          @change="(val: string) => updateCell(row.rowId, 'description', val)"
        />
        <span v-else>{{ row.description }}</span>
      </template>
    </el-table-column>

    <el-table-column label="类别" width="100">
      <template #default="{ row }">
        <el-select
          v-if="!isReadonly"
          :model-value="row.category"
          size="small"
          @change="(val: string) => updateCell(row.rowId, 'category', val)"
        >
          <el-option label="AJE" value="AJE" />
          <el-option label="RJE" value="RJE" />
        </el-select>
        <span v-else>{{ row.category }}</span>
      </template>
    </el-table-column>

    <el-table-column label="报表项目" width="120">
      <template #default="{ row }">
        <el-input
          v-if="!isReadonly"
          :model-value="row.reportItem"
          size="small"
          @change="(val: string) => updateCell(row.rowId, 'reportItem', val)"
        />
        <span v-else>{{ row.reportItem }}</span>
      </template>
    </el-table-column>

    <el-table-column label="科目名称" width="120">
      <template #default="{ row }">
        <el-input
          v-if="!isReadonly"
          :model-value="row.accountName"
          size="small"
          @change="(val: string) => updateCell(row.rowId, 'accountName', val)"
        />
        <span v-else>{{ row.accountName }}</span>
      </template>
    </el-table-column>

    <el-table-column label="附注项目" width="100">
      <template #default="{ row }">
        <el-input
          v-if="!isReadonly"
          :model-value="row.noteItem"
          size="small"
          @change="(val: string) => updateCell(row.rowId, 'noteItem', val)"
        />
        <span v-else>{{ row.noteItem }}</span>
      </template>
    </el-table-column>

    <el-table-column label="预留" width="80">
      <template #default="{ row }">
        <el-input
          v-if="!isReadonly"
          :model-value="row.placeholder"
          size="small"
          @change="(val: string) => updateCell(row.rowId, 'placeholder', val)"
        />
        <span v-else>{{ row.placeholder }}</span>
      </template>
    </el-table-column>

    <el-table-column label="借方金额" width="120" align="right">
      <template #default="{ row }">
        <el-input-number
          v-if="!isReadonly"
          :model-value="row.debitAmount"
          :controls="false"
          size="small"
          style="width:100%"
          @change="(val: number) => updateCell(row.rowId, 'debitAmount', val ?? 0)"
        />
        <span v-else>{{ fmtAmount(row.debitAmount) }}</span>
      </template>
    </el-table-column>

    <el-table-column label="贷方金额" width="120" align="right">
      <template #default="{ row }">
        <el-input-number
          v-if="!isReadonly"
          :model-value="row.creditAmount"
          :controls="false"
          size="small"
          style="width:100%"
          @change="(val: number) => updateCell(row.rowId, 'creditAmount', val ?? 0)"
        />
        <span v-else>{{ fmtAmount(row.creditAmount) }}</span>
      </template>
    </el-table-column>

    <el-table-column label="索引" width="80">
      <template #default="{ row }">
        <el-input
          v-if="!isReadonly"
          :model-value="row.indexRef"
          size="small"
          @change="(val: string) => updateCell(row.rowId, 'indexRef', val)"
        />
        <span v-else>{{ row.indexRef }}</span>
      </template>
    </el-table-column>

    <el-table-column label="备注" min-width="120">
      <template #default="{ row }">
        <el-input
          v-if="!isReadonly"
          :model-value="row.remark"
          size="small"
          @change="(val: string) => updateCell(row.rowId, 'remark', val)"
        />
        <span v-else>{{ row.remark }}</span>
      </template>
    </el-table-column>

    <el-table-column v-if="!isReadonly" label="操作" width="60">
      <template #default="{ row }">
        <el-popconfirm title="确认删除？" @confirm="removeRow(row.rowId)">
          <template #reference>
            <el-button size="small" type="danger" link>删除</el-button>
          </template>
        </el-popconfirm>
      </template>
    </el-table-column>
  </el-table>

  <!-- 底部借贷合计行 + 平衡指示 -->
  <div class="balance-row">
    <span class="balance-item">借方合计：<strong>{{ fmtAmount(debitTotal) }}</strong></span>
    <span class="balance-item">贷方合计：<strong>{{ fmtAmount(creditTotal) }}</strong></span>
    <el-tag v-if="isBalanced" type="success" size="small">借贷平衡</el-tag>
    <el-tag v-else type="danger" size="small">不平衡 差额 {{ fmtAmount(balanceDiff) }}</el-tag>
  </div>
</div>
</template>

<script setup lang="ts">
/**
 * D6TabAdjustment.vue — 调整分录汇总表 D6-4
 */
import { computed, ref, toRef, type Ref } from 'vue'
import { useD6Adjustment } from '../composables/useD6Adjustment'
import type { ChecklistResponse } from '../composables/useD6FormData'
import GtReviewTrigger from '../GtReviewTrigger.vue'

// @ts-ignore
import GtIndexChip from '../GtIndexChip.vue'

const props = defineProps<{
  wpId: string
  projectId: string
  isReadonly: boolean
  allResponses: Map<string, ChecklistResponse>
  saveImmediate: (itemId: string, data: Partial<ChecklistResponse>) => Promise<void>
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
}>()

const allResponsesRef = toRef(props, 'allResponses') as unknown as Ref<Map<string, ChecklistResponse>>

const selectedRowIds = ref<string[]>([])

const {
  rows,
  debitTotal,
  creditTotal,
  isBalanced,
  balanceDiff,
  addRow,
  removeRow,
  updateCell,
  pushToA13,
} = useD6Adjustment({
  allResponses: allResponsesRef,
  wpId: computed(() => props.wpId) as unknown as Ref<string>,
  projectId: computed(() => props.projectId) as unknown as Ref<string>,
  saveImmediate: props.saveImmediate,
  debouncedSave: props.debouncedSave,
})

function onSelectionChange(selection: any[]) {
  selectedRowIds.value = selection.map((r: any) => r.rowId)
}

function handlePushToA13() {
  pushToA13(selectedRowIds.value)
}

function fmtAmount(val: number | null | undefined): string {
  if (val == null || val === 0) return '-'
  if (val < 0) return `(${Math.abs(val).toLocaleString('zh-CN', { maximumFractionDigits: 2 })})`
  return val.toLocaleString('zh-CN', { maximumFractionDigits: 2 })
}
</script>

<style scoped>
.d6-tab-adjustment { padding: 16px; }
.d6-tab-adjustment :deep(.el-table) {
  --el-table-font-size: var(--wp-font-size, 13px);
  font-size: var(--wp-font-size, 13px);
}
.d6-tab-adjustment :deep(.el-table .cell) {
  font-size: var(--wp-font-size, 13px) !important;
}

/* 编制提示 */
.guidance-details {
  margin-bottom: 12px;
  border-left: 3px solid #409eff;
  background: #ecf5ff;
  border-radius: 4px;
  padding: 8px 12px;
}
.guidance-details summary {
  cursor: pointer;
  font-weight: 500;
  color: #409eff;
}
.guidance-content {
  margin-top: 8px;
  font-size: var(--wp-font-size, 13px);
  color: #606266;
  line-height: 1.6;
}
.guidance-content p { margin: 2px 0; }

/* 审计目标 */
.objective-alert {
  margin-bottom: 12px;
}

/* 工具栏 */
.tab-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}
.toolbar-left {
  display: flex;
  gap: 8px;
  align-items: center;
}
.toolbar-right {
  display: flex;
  gap: 6px;
  align-items: center;
}
.chip-wrap { display: inline-flex; align-items: center; }

/* 借贷平衡指示 */
.balance-row {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 10px 12px;
  background: #f5f7fa;
  border-radius: 4px;
  margin-top: 12px;
  font-size: var(--wp-font-size, 13px);
}
.balance-item { color: #606266; }
.balance-item strong { color: #303133; }
</style>
