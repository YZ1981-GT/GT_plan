<template>
<div class="d5-adjustment">
    <!-- 编制提示 -->
    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 审计调整分录（AJE）：用于更正被审计单位错误的会计处理或确认未入账交易。</p>
        <p>2. 重分类调整分录（RJE）：用于调整报表列报分类，不影响利润。</p>
        <p>3. 应收款项融资相关调整科目：1124应收款项融资 / 6101公允价值变动损益 / 其他综合收益。</p>
        <p>4. 借贷必须平衡，每笔分录需注明调整事由和索引号；可选中分录推送至 A13 错报汇总表。</p>
      </div>
    </details>

    <!-- 工具栏 -->
    <div class="tab-toolbar">
      <div class="toolbar-left">
        <el-button size="small" type="primary" :disabled="isReadonly" @click="addRow">+ 新增调整分录</el-button>
        <el-button
          size="small"
          :disabled="isReadonly || selectedRowIds.length === 0"
          @click="handlePushToA13"
        >推送至A13</el-button>
      </div>
      <div class="toolbar-right">
        <el-dropdown size="small" trigger="click" :disabled="isReadonly">
          <el-button size="small">导入导出 ▾</el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item @click="onExportTemplate">导出模板</el-dropdown-item>
              <el-dropdown-item @click="onExportData">导出数据</el-dropdown-item>
              <el-dropdown-item>
                <el-upload :show-file-list="false" accept=".xlsx" :before-upload="onImportFile" :disabled="isReadonly">
                  <span>导入数据</span>
                </el-upload>
              </el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <span class="chip-wrap"><GtIndexChip value="wp:D5-1" :context-project-id="projectId" /></span>
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

      <!-- 调整事项说明 -->
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

      <!-- 类别 -->
      <el-table-column label="类别" width="110">
        <template #default="{ row }">
          <el-select
            v-if="!isReadonly"
            :model-value="row.category"
            size="small"
            placeholder="类别"
            @change="(val: string) => updateCell(row.rowId, 'category', val)"
          >
            <el-option label="账项调整" value="账项调整" />
            <el-option label="报表调整" value="报表调整" />
            <el-option label="其他" value="其他" />
          </el-select>
          <span v-else>{{ row.category }}</span>
        </template>
      </el-table-column>

      <!-- 报表项目 -->
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

      <!-- 科目名称 -->
      <el-table-column label="科目名称" width="130">
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

      <!-- 附注项目 -->
      <el-table-column label="附注项目" width="110">
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

      <!-- 借方金额 -->
      <el-table-column label="借方金额" width="120" align="right">
        <template #default="{ row }">
          <el-input-number
            v-if="!isReadonly"
            :model-value="row.debitAmount"
            :controls="false"
            :min="0"
            size="small"
            style="width:100%"
            @change="(val: number) => updateCell(row.rowId, 'debitAmount', val ?? 0)"
          />
          <span v-else>{{ fmtAmount(row.debitAmount) }}</span>
        </template>
      </el-table-column>

      <!-- 贷方金额 -->
      <el-table-column label="贷方金额" width="120" align="right">
        <template #default="{ row }">
          <el-input-number
            v-if="!isReadonly"
            :model-value="row.creditAmount"
            :controls="false"
            :min="0"
            size="small"
            style="width:100%"
            @change="(val: number) => updateCell(row.rowId, 'creditAmount', val ?? 0)"
          />
          <span v-else>{{ fmtAmount(row.creditAmount) }}</span>
        </template>
      </el-table-column>

      <!-- 索引 -->
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

      <!-- 备注 -->
      <el-table-column label="备注" min-width="100">
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

      <!-- 操作列 -->
      <el-table-column label="操作" width="60" align="center" fixed="right">
        <template #default="{ row }">
          <el-button
            v-if="!isReadonly"
            type="danger"
            text
            size="small"
            @click="removeRow(row.rowId)"
          >
            删除
          </el-button>
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
 * D5TabAdjustment.vue — D5-3 调整分录
 *
 * el-table 10列 + "新增调整分录"按钮
 * 底部借贷合计行 + 平衡指示（绿色✓平衡/红色✗不平衡：差额xxx）
 * "推送至A13"按钮（多选行）
 * 编制提示details折叠（蓝色左边线+浅蓝背景，默认收起）
 *
 * Task: 16.1
 * Requirements: 7.1-7.7
 */
import { ref, computed, toRef, type Ref } from 'vue'
import { useD5Adjustment } from '../composables/useD5Adjustment'
import { useD5TabImportExport } from '../composables/useD5TabImportExport'
import type { ChecklistResponse } from '../composables/useD5FormData'

// @ts-ignore
import GtIndexChip from '../GtIndexChip.vue'

// ─── Props ───────────────────────────────────────────────────────────────────

const props = defineProps<{
  wpId: string
  projectId: string
  isReadonly: boolean
  allResponses: Map<string, ChecklistResponse>
  saveImmediate: (itemId: string, data: Partial<ChecklistResponse>) => Promise<void>
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
}>()

const allResponsesRef = toRef(props, 'allResponses') as unknown as Ref<Map<string, ChecklistResponse>>

// ─── Composable ──────────────────────────────────────────────────────────────

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
} = useD5Adjustment({
  allResponses: allResponsesRef,
  wpId: computed(() => props.wpId) as unknown as Ref<string>,
  projectId: computed(() => props.projectId) as unknown as Ref<string>,
  saveImmediate: props.saveImmediate,
  debouncedSave: props.debouncedSave,
  isReadonly: computed(() => props.isReadonly) as unknown as Ref<boolean>,
})

const wpIdRef = computed(() => props.wpId) as unknown as Ref<string>
const { onExportTemplate, onExportData, onImportFile } = useD5TabImportExport(wpIdRef, 'D5-3')

// ─── Selection ───────────────────────────────────────────────────────────────

const selectedRowIds = ref<string[]>([])

function onSelectionChange(selection: any[]) {
  selectedRowIds.value = selection.map(r => r.rowId)
}

function handlePushToA13() {
  pushToA13(selectedRowIds.value)
}

// ─── Formatting ──────────────────────────────────────────────────────────────

function fmtAmount(val: number | null | undefined): string {
  if (val == null || val === 0) return '-'
  if (val < 0) return `(${Math.abs(val).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })})`
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.d5-adjustment {
  padding: 12px;
}
.d5-adjustment :deep(.el-table) {
  --el-table-font-size: var(--wp-font-size, 13px);
  font-size: var(--wp-font-size, 13px);
}
.d5-adjustment :deep(.el-table .cell) {
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
.guidance-content p {
  margin: 2px 0;
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
.balance-item {
  color: #606266;
}
.balance-item strong {
  color: #303133;
}
</style>
