<template>
<div class="d3-adjustment">
  <!-- 编制提示 -->
  <details class="guidance-details">
    <summary>📋 编制提示</summary>
    <div class="guidance-content">
      <p>1. 预付账款（科目1123）调整分录应按实际调整事项逐笔编制，确保借贷平衡。</p>
      <p>2. 账项调整（AJE）影响审定数；重分类调整（RJE）仅改变列报位置，不影响损益。</p>
      <p>3. 常见调整：长期挂账转其他应收款/坏账、关联方预付重分类、错误计提冲回等。</p>
      <p>4. 勾选后可推送至 A13 错报汇总表，由业务合伙人最终评估影响。</p>
    </div>
  </details>

  <!-- 工具栏 -->
  <div class="tab-toolbar">
    <div class="toolbar-left">
      <el-button size="small" type="primary" :disabled="isReadonly" @click="addRow">+ 新增调整分录</el-button>
      <el-button size="small" :disabled="isReadonly || selectedRowIds.length === 0" @click="pushToA13">
        推送至A13（{{ selectedRowIds.length }}条）
      </el-button>
    </div>
    <div class="toolbar-right">
      <span class="chip-wrap"><GtIndexChip value="wp:A13" :context-project-id="projectId" /></span>
      <el-tag size="small" type="info">共 {{ rows.length }} 行</el-tag>
    </div>
  </div>

  <!-- 调整分录表 -->
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
        <el-input v-model="row.description" size="small" :disabled="isReadonly"
          @change="(val: string) => updateCell(row.rowId, 'description', val)" />
      </template>
    </el-table-column>
    <el-table-column label="类别" width="120">
      <template #default="{ row }">
        <el-select v-model="row.category" size="small" :disabled="isReadonly"
          @change="(val: string) => updateCell(row.rowId, 'category', val)">
          <el-option value="账项调整" />
          <el-option value="报表调整" />
          <el-option value="重分类调整" />
          <el-option value="其他" />
        </el-select>
      </template>
    </el-table-column>
    <el-table-column label="报表项目" width="120">
      <template #default="{ row }">
        <el-input v-model="row.reportItem" size="small" :disabled="isReadonly"
          @change="(val: string) => updateCell(row.rowId, 'reportItem', val)" />
      </template>
    </el-table-column>
    <el-table-column label="科目名称" width="120">
      <template #default="{ row }">
        <el-input v-model="row.accountName" size="small" :disabled="isReadonly"
          @change="(val: string) => updateCell(row.rowId, 'accountName', val)" />
      </template>
    </el-table-column>
    <el-table-column label="附注项目" width="100">
      <template #default="{ row }">
        <el-input v-model="row.noteItem" size="small" :disabled="isReadonly"
          @change="(val: string) => updateCell(row.rowId, 'noteItem', val)" />
      </template>
    </el-table-column>
    <el-table-column label="借方金额" width="120" align="right">
      <template #default="{ row }">
        <el-input v-model.number="row.debitAmount" size="small" :disabled="isReadonly"
          @change="(val: any) => updateCell(row.rowId, 'debitAmount', val)" />
      </template>
    </el-table-column>
    <el-table-column label="贷方金额" width="120" align="right">
      <template #default="{ row }">
        <el-input v-model.number="row.creditAmount" size="small" :disabled="isReadonly"
          @change="(val: any) => updateCell(row.rowId, 'creditAmount', val)" />
      </template>
    </el-table-column>
    <el-table-column label="索引" width="80">
      <template #default="{ row }">
        <el-input v-model="row.indexRef" size="small" :disabled="isReadonly"
          @change="(val: string) => updateCell(row.rowId, 'indexRef', val)" />
      </template>
    </el-table-column>
    <el-table-column label="备注" min-width="120">
      <template #default="{ row }">
        <el-input v-model="row.remark" size="small" :disabled="isReadonly"
          @change="(val: string) => updateCell(row.rowId, 'remark', val)" />
      </template>
    </el-table-column>
    <el-table-column label="操作" width="60" v-if="!isReadonly">
      <template #default="{ row }">
        <el-popconfirm title="确认删除？" @confirm="removeRow(row.rowId)">
          <template #reference><el-button size="small" type="danger" link>删除</el-button></template>
        </el-popconfirm>
      </template>
    </el-table-column>
  </el-table>

  <!-- 借贷合计 + 平衡指示 -->
  <div class="tb-check-row">
    <span class="tb-label">借方合计 {{ fmtAmount(debitTotal) }} · 贷方合计 {{ fmtAmount(creditTotal) }}</span>
    <el-tag v-if="isBalanced" type="success" size="small">借贷平衡</el-tag>
    <el-tag v-else type="danger" size="small">差额 {{ fmtAmount(balanceDiff) }}</el-tag>
  </div>
</div>
</template>

<script setup lang="ts">
/**
 * F1TabAdjustment.vue — F1-3 调整分录汇总表
 * 10列表 + 借贷平衡 + 推送A13
 */
import { computed, ref, toRef, type Ref } from 'vue'
import { useF1Adjustment } from '../composables/useF1Adjustment'
import type { ChecklistResponse } from '../composables/useF1FormData'

// @ts-ignore - GtIndexChip may not have type declarations
import GtIndexChip from '../GtIndexChip.vue'

const props = defineProps<{
  allResponses: Map<string, ChecklistResponse>
  wpId: string
  projectId: string
  isReadonly: boolean
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
} = useF1Adjustment({
  allResponses: allResponsesRef,
  wpId: toRef(props, 'wpId') as Ref<string>,
  projectId: toRef(props, 'projectId') as Ref<string>,
  saveImmediate: props.saveImmediate,
  debouncedSave: props.debouncedSave,
  isReadonly: computed(() => props.isReadonly) as unknown as Ref<boolean>,
})

function onSelectionChange(selection: any[]) {
  selectedRowIds.value = selection.map((r: any) => r.rowId)
}

function fmtAmount(val: number | null | undefined): string {
  if (val == null || val === 0) return '-'
  if (val < 0) return `(${Math.abs(val).toLocaleString('zh-CN', { maximumFractionDigits: 2 })})`
  return val.toLocaleString('zh-CN', { maximumFractionDigits: 2 })
}
</script>

<style scoped>
.d3-adjustment { padding: 16px; }
.d3-adjustment :deep(.el-table) { --el-table-font-size: 13px; font-size: 13px; }
.d3-adjustment :deep(.el-table .cell) { font-size: 13px !important; }

/* 编制提示 */
.guidance-details { margin-bottom: 12px; border-left: 3px solid #409eff; background: #ecf5ff; border-radius: 4px; padding: 8px 12px; }
.guidance-details summary { cursor: pointer; font-weight: 500; color: #409eff; }
.guidance-content { margin-top: 8px; font-size: 13px; color: #606266; line-height: 1.6; }
.guidance-content p { margin: 2px 0; }

/* 工具栏 */
.tab-toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; flex-wrap: wrap; gap: 8px; }
.toolbar-left { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.toolbar-right { display: flex; gap: 6px; align-items: center; }
.chip-wrap { display: inline-flex; align-items: center; }

/* 平衡核对行 */
.tb-check-row { display: flex; align-items: center; gap: 8px; padding: 10px 12px; background: #f5f7fa; border-radius: 4px; margin-top: 12px; font-size: 13px; }
.tb-label { color: #909399; }
</style>
