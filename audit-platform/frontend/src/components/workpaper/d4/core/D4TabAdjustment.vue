<script setup lang="ts">
/**
 * D4TabAdjustment — D4-4 调整分录
 *
 * el-table 10列 + "新增调整分录" + 借贷合计+平衡指示
 * "推送至A13"按钮 + 编制提示details折叠
 *
 * Requirements: 5.1-5.7
 */
import { ref, computed, inject, toRef, type Ref } from 'vue'
import { useD4Adjustment, type D4AdjustmentRow } from '../../composables/useD4Adjustment'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const openReviewDialog = inject<((sectionId: string) => void) | null>('openReviewDialog', null)

// ─── 金额格式化 ───────────────────────────────────────────────────────
function fmtAmount(v: number): string {
  if (v === 0) return '-'
  if (v < 0) return `(${Math.abs(v).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })})`
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

// ─── Composable ───────────────────────────────────────────────────────
const {
  rows,
  debitTotal,
  creditTotal,
  isBalanced,
  balanceDiff,
  addRow,
  removeRow,
  updateCell,
  publishAdjustment,
  pushToA13,
} = useD4Adjustment({
  wpId: toRef(props, 'wpId') as Ref<string>,
  projectId: toRef(props, 'projectId') as Ref<string>,
  allResponses: toRef(props, 'allResponses') as Ref<Map<string, any>>,
  isReadonly: toRef(props, 'isReadonly') as Ref<boolean>,
})

// ─── 选中行（用于推送A13） ─────────────────────────────────────────────
const selectedRows = ref<D4AdjustmentRow[]>([])

function handleSelectionChange(selection: D4AdjustmentRow[]) {
  selectedRows.value = selection
}

function handlePushToA13() {
  const ids = selectedRows.value.map(r => r.rowId)
  if (ids.length === 0) return
  pushToA13(ids)
}

// ─── 分类选项 ─────────────────────────────────────────────────────────
const categoryOptions = [
  { label: '账项调整', value: '账项调整' },
  { label: '报表调整', value: '报表调整' },
  { label: '其他', value: '其他' },
]
</script>

<template>
  <div class="d4-tab-adjustment">
    <!-- 编制提示 -->
    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 记录审计过程中发现的需要调整的会计分录。</p>
        <p>2. "账项调整"(AJE)：涉及科目余额的调整；"报表调整"(RJE)：仅影响报表列报的重分类调整。</p>
        <p>3. 借贷合计必须平衡（借方合计=贷方合计），不平衡时无法确认。</p>
        <p>4. 确认后的调整分录将同步更新D4-1审定表的AJE/RJE列。</p>
        <p>5. 可选中分录推送至A13错报汇总表。</p>
      </div>
    </details>

    <!-- 工具栏 -->
    <div class="tab-toolbar">
      <div class="toolbar-left">
        <el-button size="small" type="primary" :disabled="isReadonly" @click="addRow">
          + 新增调整分录
        </el-button>
        <el-button
          size="small"
          :disabled="isReadonly || selectedRows.length === 0"
          @click="handlePushToA13"
        >
          推送至A13
        </el-button>
      </div>
      <div class="toolbar-right">
        <el-button
          size="small"
          type="success"
          :disabled="isReadonly || !isBalanced || rows.length === 0"
          @click="publishAdjustment"
        >
          确认调整
        </el-button>
      </div>
    </div>

    <!-- 借贷平衡指示 -->
    <div class="balance-indicator">
      <span class="balance-item">
        借方合计：<strong>{{ fmtAmount(debitTotal) }}</strong>
      </span>
      <span class="balance-item">
        贷方合计：<strong>{{ fmtAmount(creditTotal) }}</strong>
      </span>
      <el-tag v-if="isBalanced" type="success" size="small">借贷平衡</el-tag>
      <el-tag v-else type="danger" size="small">
        不平衡 差异{{ fmtAmount(balanceDiff) }}
      </el-tag>
    </div>

    <!-- 主表 -->
    <el-table
      :data="rows"
      border
      size="small"
      style="width: 100%; margin-bottom: 12px"
      @selection-change="handleSelectionChange"
    >
      <el-table-column type="selection" width="40" />

      <!-- 1. 摘要 -->
      <el-table-column label="摘要" width="140">
        <template #default="{ row }">
          <el-input
            v-if="!isReadonly"
            :model-value="row.description"
            size="small"
            placeholder="摘要"
            @change="(v: string) => updateCell(row.rowId, 'description', v)"
          />
          <span v-else>{{ row.description || '-' }}</span>
        </template>
      </el-table-column>

      <!-- 2. 分类 -->
      <el-table-column label="分类" width="110">
        <template #default="{ row }">
          <el-select
            v-if="!isReadonly"
            :model-value="row.category"
            size="small"
            @change="(v: string) => updateCell(row.rowId, 'category', v)"
          >
            <el-option
              v-for="opt in categoryOptions"
              :key="opt.value"
              :label="opt.label"
              :value="opt.value"
            />
          </el-select>
          <span v-else>{{ row.category }}</span>
        </template>
      </el-table-column>

      <!-- 3. 报表项目 -->
      <el-table-column label="报表项目" width="120">
        <template #default="{ row }">
          <el-input
            v-if="!isReadonly"
            :model-value="row.reportItem"
            size="small"
            placeholder="报表项目"
            @change="(v: string) => updateCell(row.rowId, 'reportItem', v)"
          />
          <span v-else>{{ row.reportItem || '-' }}</span>
        </template>
      </el-table-column>

      <!-- 4. 会计科目 -->
      <el-table-column label="会计科目" width="130">
        <template #default="{ row }">
          <el-input
            v-if="!isReadonly"
            :model-value="row.accountName"
            size="small"
            placeholder="如 6001-主营业务收入"
            @change="(v: string) => updateCell(row.rowId, 'accountName', v)"
          />
          <span v-else>{{ row.accountName || '-' }}</span>
        </template>
      </el-table-column>

      <!-- 5. 附注项目 -->
      <el-table-column label="附注项目" width="100">
        <template #default="{ row }">
          <el-input
            v-if="!isReadonly"
            :model-value="row.noteItem"
            size="small"
            @change="(v: string) => updateCell(row.rowId, 'noteItem', v)"
          />
          <span v-else>{{ row.noteItem || '-' }}</span>
        </template>
      </el-table-column>

      <!-- 6. 占位符 -->
      <el-table-column label="占位符" width="90">
        <template #default="{ row }">
          <el-input
            v-if="!isReadonly"
            :model-value="row.placeholder"
            size="small"
            @change="(v: string) => updateCell(row.rowId, 'placeholder', v)"
          />
          <span v-else>{{ row.placeholder || '-' }}</span>
        </template>
      </el-table-column>

      <!-- 7. 借方金额 -->
      <el-table-column label="借方" width="120" align="right">
        <template #default="{ row }">
          <el-input
            v-if="!isReadonly"
            :model-value="row.debitAmount"
            size="small"
            type="number"
            @change="(v: string) => updateCell(row.rowId, 'debitAmount', v)"
          />
          <span v-else>{{ fmtAmount(row.debitAmount) }}</span>
        </template>
      </el-table-column>

      <!-- 8. 贷方金额 -->
      <el-table-column label="贷方" width="120" align="right">
        <template #default="{ row }">
          <el-input
            v-if="!isReadonly"
            :model-value="row.creditAmount"
            size="small"
            type="number"
            @change="(v: string) => updateCell(row.rowId, 'creditAmount', v)"
          />
          <span v-else>{{ fmtAmount(row.creditAmount) }}</span>
        </template>
      </el-table-column>

      <!-- 9. 索引号 -->
      <el-table-column label="索引号" width="80">
        <template #default="{ row }">
          <el-input
            v-if="!isReadonly"
            :model-value="row.indexRef"
            size="small"
            @change="(v: string) => updateCell(row.rowId, 'indexRef', v)"
          />
          <span v-else>{{ row.indexRef || '-' }}</span>
        </template>
      </el-table-column>

      <!-- 10. 备注 -->
      <el-table-column label="备注" min-width="100">
        <template #default="{ row }">
          <el-input
            v-if="!isReadonly"
            :model-value="row.remark"
            size="small"
            @change="(v: string) => updateCell(row.rowId, 'remark', v)"
          />
          <span v-else>{{ row.remark || '-' }}</span>
        </template>
      </el-table-column>

      <!-- 操作 -->
      <el-table-column label="" width="50" align="center" fixed="right">
        <template #default="{ row }">
          <el-button
            v-if="!isReadonly"
            type="danger"
            size="small"
            link
            @click="removeRow(row.rowId)"
          >删</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 空状态 -->
    <div v-if="rows.length === 0" class="empty-hint">
      暂无调整分录。点击"新增调整分录"添加。
    </div>
  </div>
</template>

<style scoped>
.d4-tab-adjustment {
  padding: 12px;
}
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
  font-size: 13px;
  color: #606266;
  line-height: 1.6;
}
.guidance-content p {
  margin: 2px 0;
}
.tab-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}
.toolbar-left {
  display: flex;
  gap: 8px;
}
.toolbar-right {
  display: flex;
  gap: 6px;
}
.balance-indicator {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 8px 12px;
  background: #f5f7fa;
  border-radius: 4px;
  margin-bottom: 12px;
  font-size: 13px;
}
.balance-item {
  color: #606266;
}
.balance-item strong {
  color: #303133;
}
.empty-hint {
  text-align: center;
  color: #909399;
  padding: 24px;
  font-size: 13px;
}
</style>
