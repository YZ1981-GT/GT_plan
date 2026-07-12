<script setup lang="ts">
/**
 * E1TabLargeCheck.vue — E1-23 收支检查
 *
 * Spec: .kiro/specs/e1-monetary-fund-refactor/
 * Task: 18.16
 *
 * - Uses useE1IpoSpecial with sheetCode='E1-23'
 * - Generic table driven by COLUMN_CONFIG['E1-23']
 * - Dynamic rows
 *
 * Requirements: 10.6
 */
import { inject, toRef, type Ref } from 'vue'
import {
  useE1IpoSpecial,
  type IpoSheetCode,
  type ColumnDef,
} from '../composables/useE1IpoSpecial'
import type { UseE1BaseOptions } from '../composables/useE1Adjudication'
import GtIndexChip from '../GtIndexChip.vue'
import { DisplayPrefs_Key } from '../composables/displayPrefsKey'
import { useDisplayPrefsStore } from '@/stores/displayPrefs'

// ─── Props ───────────────────────────────────────────────────────────────────

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  saveImmediate: (items: any[]) => Promise<void>
  debouncedSave: (items: any[]) => Promise<void>
  isReadonly: boolean
  sheetName?: string
}>()

// ─── Inject ──────────────────────────────────────────────────────────────────

const displayPrefs = inject(DisplayPrefs_Key, null) ?? useDisplayPrefsStore()

// ─── Composable ──────────────────────────────────────────────────────────────

const sheetCode: IpoSheetCode = 'E1-23'

const options: UseE1BaseOptions & { sheetCode: IpoSheetCode } = {
  wpId: toRef(props, 'wpId') as unknown as Ref<string>,
  projectId: toRef(props, 'projectId') as unknown as Ref<string>,
  allResponses: toRef(props, 'allResponses') as unknown as Ref<Map<string, any>>,
  saveImmediate: props.saveImmediate,
  debouncedSave: props.debouncedSave,
  isReadonly: toRef(props, 'isReadonly') as unknown as Ref<boolean>,
  sheetCode,
}

const {
  rows,
  columns,
  isLoading,
  addRow,
  removeRow,
  updateCell,
} = useE1IpoSpecial(options)

// ─── Helpers ─────────────────────────────────────────────────────────────────

function getColWidth(col: ColumnDef): number {
  return col.width || (col.type === 'number' ? 130 : 150)
}

function formatCellValue(row: any, col: ColumnDef): string {
  const val = row[col.key]
  if (col.type === 'number' || col.type === 'computed') {
    return displayPrefs.fmtAmount(Number(val) || 0)
  }
  if (col.type === 'boolean') return val ? '是' : '否'
  return String(val || '')
}
</script>

<template>
  <div class="e1-tab-large-check">
    <!-- 编制提示 -->
    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 检查大额及异常现金/银行收支的真实性、合规性与业务实质。</p>
        <p>2. 关注大额现金交易、频繁整数收支、无正常商业理由的资金往来及资金体外循环迹象。</p>
        <p>3. 核对收支凭证、合同、审批手续是否齐全，金额、对方账户是否与业务匹配。</p>
        <p>4. 重点关注与关联方、疑似虚构交易对手的大额资金往来，识别舞弊风险。</p>
      </div>
    </details>

    <!-- 审计目标 -->
    <el-alert
      type="info"
      :closable="false"
      title="审计目标：检查大额及异常收支的真实性与合规性，识别资金舞弊及体外循环迹象。"
      class="objective-alert"
    />

    <!-- 工具栏 -->
    <div class="tab-toolbar">
      <div class="toolbar-left">
        <el-tag size="small" type="success">收支检查 (E1-23)</el-tag>
        <el-button size="small" type="primary" :disabled="isReadonly" @click="addRow">+ 添加行</el-button>
      </div>
      <div class="toolbar-right">
        <span class="chip-wrap"><GtIndexChip value="wp:E1-1" :context-project-id="projectId" /></span>
        <el-tag size="small" type="info">共 {{ rows.length }} 行</el-tag>
      </div>
    </div>

    <el-skeleton :loading="isLoading" :rows="8" animated>
      <template #default>
        <el-table :data="rows" border stripe size="small" max-height="500" style="width: 100%">
          <el-table-column
            v-for="col in columns"
            :key="col.key"
            :label="col.label"
            :width="getColWidth(col)"
            :align="col.type === 'number' || col.type === 'computed' ? 'right' : 'left'"
            :class-name="col.type === 'computed' ? 'auto-calc-col' : ''"
          >
            <template #default="{ row }">
              <!-- Computed: readonly -->
              <span v-if="col.type === 'computed'" class="auto-calc-value">
                {{ formatCellValue(row, col) }}
              </span>
              <!-- Number -->
              <el-input-number
                v-else-if="col.type === 'number'"
                :model-value="row[col.key]"
                :disabled="isReadonly"
                :controls="false"
                size="small"
                @change="(val: number) => updateCell(row.id, col.key, val ?? 0)"
              />
              <!-- Boolean -->
              <el-checkbox
                v-else-if="col.type === 'boolean'"
                :model-value="!!row[col.key]"
                :disabled="isReadonly"
                @change="(val: boolean) => updateCell(row.id, col.key, val)"
              />
              <!-- Date -->
              <el-date-picker
                v-else-if="col.type === 'date'"
                :model-value="row[col.key]"
                :disabled="isReadonly"
                type="date"
                value-format="YYYY-MM-DD"
                size="small"
                style="width: 100%"
                @update:model-value="(val: string) => updateCell(row.id, col.key, val || '')"
              />
              <!-- Text (default) -->
              <el-input
                v-else
                :model-value="row[col.key]"
                :disabled="isReadonly"
                size="small"
                @change="(val: string) => updateCell(row.id, col.key, val)"
              />
            </template>
          </el-table-column>

          <el-table-column label="操作" width="70" align="center" fixed="right">
            <template #default="{ row }">
              <el-button v-if="!isReadonly" type="danger" text size="small"
                @click="removeRow(row.id)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
      </template>
    </el-skeleton>
  </div>
</template>

<style scoped>
.e1-tab-large-check {
  padding: 12px 0;
}
.e1-tab-large-check :deep(.el-table) {
  --el-table-font-size: var(--wp-font-size, 13px);
  font-size: var(--wp-font-size, 13px);
}
.e1-tab-large-check :deep(.el-table .cell) {
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
.objective-alert {
  margin-bottom: 12px;
}

/* 工具栏 */
.tab-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
  flex-wrap: wrap;
  gap: 8px;
}
.toolbar-left {
  display: flex;
  gap: 8px;
  align-items: center;
  flex-wrap: wrap;
}
.toolbar-right {
  display: flex;
  gap: 6px;
  align-items: center;
}
.chip-wrap { display: inline-flex; align-items: center; }

/* 自动计算列灰底 */
:deep(.auto-calc-col) {
  background-color: #f5f7fa !important;
}
.auto-calc-value {
  color: #606266;
}
</style>
