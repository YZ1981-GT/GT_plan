<template>
<div class="d3-adjustment">
  <!-- 工具栏 -->
  <div class="adj-toolbar">
    <el-button size="small" type="primary" :disabled="isReadonly" @click="addRow">+ 新增调整分录</el-button>
    <el-button size="small" :disabled="isReadonly || selectedRowIds.length === 0" @click="pushToA13">
      推送至A13（{{ selectedRowIds.length }}条）
    </el-button>
    <el-button-group size="small" style="margin-left: auto">
      <el-button @click="onExportTemplate">导出模板</el-button>
      <el-button @click="onExportData">导出数据</el-button>
      <el-upload :show-file-list="false" accept=".xlsx" :before-upload="onImportFile">
        <el-button :disabled="isReadonly">导入数据</el-button>
      </el-upload>
    </el-button-group>
    <GtReviewTrigger section-id="D3-aje-header" />
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
  <div class="balance-row">
    <span>借方合计：{{ fmtAmount(debitTotal) }}</span>
    <span>贷方合计：{{ fmtAmount(creditTotal) }}</span>
    <span :class="isBalanced ? 'balanced' : 'unbalanced'">
      {{ isBalanced ? '✓ 借贷平衡' : `✗ 差额：${fmtAmount(balanceDiff)}` }}
    </span>
  </div>

  <!-- 编制提示 -->
  <details class="compile-hint">
    <summary>📋 编制提示</summary>
    <div class="hint-content">
      1. 调整分录应按实际调整事项逐笔编制，确保借贷平衡。<br/>
      2. 账项调整（AJE）影响审定数，重分类调整（RJE）不影响损益。<br/>
      3. 完成后可将分录推送至A13错报汇总表，由业务合伙人最终评估。<br/>
      4. 分录类别选择：账项调整=已确认错报；重分类调整=仅改变列报位置。
    </div>
  </details>
</div>
</template>

<script setup lang="ts">
/**
 * D3TabAdjustment.vue — D3-3 调整分录汇总表
 * 10列表 + 借贷平衡 + 推送A13
 */
import { computed, ref, toRef, type Ref } from 'vue'
import { useD3Adjustment } from '../composables/useD3Adjustment'
import { useD3TabImportExport } from '../composables/useD3TabImportExport'
import type { ChecklistResponse } from '../composables/useD3FormData'
import GtReviewTrigger from '../GtReviewTrigger.vue'

const props = defineProps<{
  allResponses: Map<string, ChecklistResponse>
  wpId: string
  projectId: string
  isReadonly: boolean
  saveImmediate: (itemId: string, data: Partial<ChecklistResponse>) => Promise<void>
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
}>()

// 父级经模板传入的是解包后的普通值（非 ref），此处重新包成 ref 供 composable 使用
const allResponsesRef = toRef(props, 'allResponses') as Ref<Map<string, ChecklistResponse>>
const wpIdRef = toRef(props, 'wpId') as Ref<string>
const projectIdRef = toRef(props, 'projectId') as Ref<string>

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
} = useD3Adjustment({
  allResponses: allResponsesRef,
  wpId: wpIdRef,
  projectId: projectIdRef,
  saveImmediate: props.saveImmediate,
  debouncedSave: props.debouncedSave,
  isReadonly: computed(() => props.isReadonly) as unknown as Ref<boolean>,
})

const { onExportTemplate, onExportData, onImportFile } = useD3TabImportExport(wpIdRef, 'D3-3')

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
.adj-toolbar { display: flex; gap: 8px; margin-bottom: 12px; }
.balance-row { display: flex; gap: 24px; padding: 10px 12px; background: #fafafa; border-radius: 4px; margin-top: 12px; font-size: var(--wp-font-size, 13px); font-weight: 500; }
.balanced { color: #67c23a; }
.unbalanced { color: #f56c6c; font-weight: 600; }
.compile-hint { margin-top: 16px; border-left: 3px solid #409eff; background: #ecf5ff; border-radius: 4px; }
.compile-hint summary { padding: 8px 12px; cursor: pointer; font-size: var(--wp-font-size, 13px); color: #409eff; }
.compile-hint .hint-content { padding: 8px 12px 12px; font-size: 12px; color: #606266; line-height: 1.8; }
</style>
