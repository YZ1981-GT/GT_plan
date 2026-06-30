<template>
<div class="d5-adjustment">
  <!-- 双模式切换 -->
  <div class="mode-toolbar">
    <el-segmented v-model="viewMode" :options="modeOptions" size="small" />
  </div>

  <template v-if="viewMode === 'structured'">
    <!-- 编制提示折叠 -->
    <details class="guidance-hint">
      <summary>📋 编制提示</summary>
      <div class="hint-content">
        调整分录编制要求：<br/>
        1. 审计调整分录（AJE）：用于更正被审计单位错误的会计处理或确认未入账交易。<br/>
        2. 重分类调整分录（RJE）：用于调整报表列报分类，不影响利润。<br/>
        3. 应收款项融资相关调整科目：1124应收款项融资/6101公允价值变动损益/其他综合收益。<br/>
        4. 借贷必须平衡，每笔分录需注明调整事由和索引号。
      </div>
    </details>

    <!-- 工具栏 -->
    <div class="adj-toolbar">
      <el-button size="small" type="primary" :disabled="isReadonly" @click="addRow">
        新增调整分录
      </el-button>
      <el-button
        size="small"
        :disabled="isReadonly || selectedRowIds.length === 0"
        @click="handlePushToA13"
      >
        推送至A13
      </el-button>
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
      <span>借方合计：{{ fmtAmount(debitTotal) }}</span>
      <span>贷方合计：{{ fmtAmount(creditTotal) }}</span>
      <span :class="isBalanced ? 'balance-ok' : 'balance-err'">
        <template v-if="isBalanced">✓ 平衡</template>
        <template v-else>✗ 不平衡：差额 {{ fmtAmount(balanceDiff) }}</template>
      </span>
    </div>
  </template>

  <!-- OnlyOffice占位 -->
  <div v-else class="onlyoffice-placeholder">
    <el-empty description="在线编辑模式（OnlyOffice）" />
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
import { ref, computed, type Ref } from 'vue'
import { useD5Adjustment } from '../composables/useD5Adjustment'
import type { ChecklistResponse } from '../composables/useD5FormData'

// ─── Props ───────────────────────────────────────────────────────────────────

const props = defineProps<{
  wpId: string
  projectId: string
  isReadonly: boolean
  allResponses: Ref<Map<string, ChecklistResponse>>
  saveImmediate: (itemId: string, data: Partial<ChecklistResponse>) => Promise<void>
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
}>()

// ─── Mode ────────────────────────────────────────────────────────────────────

const viewMode = ref('structured')
const modeOptions = [
  { label: '结构化视图', value: 'structured' },
  { label: '在线编辑', value: 'onlyoffice' },
]

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
  allResponses: props.allResponses,
  wpId: computed(() => props.wpId) as unknown as Ref<string>,
  projectId: computed(() => props.projectId) as unknown as Ref<string>,
  saveImmediate: props.saveImmediate,
  debouncedSave: props.debouncedSave,
  isReadonly: computed(() => props.isReadonly) as unknown as Ref<boolean>,
})

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
  padding: 16px;
}

.mode-toolbar {
  margin-bottom: 12px;
}

.guidance-hint {
  margin-bottom: 12px;
  border-left: 3px solid #409eff;
  background: #ecf5ff;
  border-radius: 4px;
}

.guidance-hint summary {
  padding: 8px 12px;
  cursor: pointer;
  font-size: 13px;
  color: #409eff;
}

.guidance-hint .hint-content {
  padding: 8px 12px 12px;
  font-size: 12px;
  color: #606266;
  line-height: 1.8;
}

.adj-toolbar {
  display: flex;
  gap: 8px;
  margin-bottom: 12px;
}

.balance-row {
  display: flex;
  gap: 24px;
  padding: 10px 12px;
  background: #fafafa;
  border-radius: 4px;
  margin-top: 12px;
  font-size: 13px;
  font-weight: 600;
}

.balance-ok {
  color: #67c23a;
}

.balance-err {
  color: #f56c6c;
}

.onlyoffice-placeholder {
  padding: 40px 0;
}
</style>
