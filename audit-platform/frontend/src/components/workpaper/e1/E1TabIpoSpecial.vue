<script setup lang="ts">
/**
 * E1TabIpoSpecial.vue — E1-26~32 IPO组 (sheetCode分发)
 *
 * Spec: .kiro/specs/e1-monetary-fund-refactor/
 * Task: 18.17
 *
 * - Uses useE1IpoSpecial composable
 * - Props: sheetCode detected from sheetName
 * - Renders columns from COLUMN_CONFIG[sheetCode] dynamically
 * - Applicability switch: el-switch at top when isApplicable is false shows "未启用IPO程序"
 * - Dynamic rows
 *
 * Requirements: 11.1-11.9
 */
import { computed, inject, toRef, type Ref } from 'vue'
import {
  useE1IpoSpecial,
  type IpoSheetCode,
  type ColumnDef,
  COLUMN_CONFIG,
} from '../composables/useE1IpoSpecial'
import type { UseE1BaseOptions } from '../composables/useE1Adjudication'
import GtIndexChip from '../GtIndexChip.vue'

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

const displayPrefs = inject<{ fmtAmount: (v: number) => string }>('displayPrefs', {
  fmtAmount: (v: number) =>
    v === 0 ? '-' : v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }),
})

// ─── SheetCode Detection ─────────────────────────────────────────────────────

const sheetCode = computed<IpoSheetCode>(() => {
  const name = props.sheetName || ''
  const match = name.match(/E1-(\d+)/)
  if (match) {
    const code = `E1-${match[1]}` as IpoSheetCode
    if (code in COLUMN_CONFIG) return code
  }
  return 'E1-26'
})

// ─── Composable ──────────────────────────────────────────────────────────────

const options: UseE1BaseOptions & { sheetCode: IpoSheetCode } = {
  wpId: toRef(props, 'wpId') as unknown as Ref<string>,
  projectId: toRef(props, 'projectId') as unknown as Ref<string>,
  allResponses: toRef(props, 'allResponses') as unknown as Ref<Map<string, any>>,
  saveImmediate: props.saveImmediate,
  debouncedSave: props.debouncedSave,
  isReadonly: toRef(props, 'isReadonly') as unknown as Ref<boolean>,
  sheetCode: sheetCode.value,
}

const {
  rows,
  columns,
  isApplicable,
  isLoading,
  addRow,
  removeRow,
  updateCell,
} = useE1IpoSpecial(options)

// ─── Applicability Toggle ────────────────────────────────────────────────────

function toggleApplicability(val: boolean): void {
  if (props.isReadonly) return
  const key = 'E1-ipo-applicable'
  const conclusion = val ? 'Y' : 'N'
  const item = { item_id: key, conclusion, remark: null }
  props.allResponses.set(key, item)
  props.saveImmediate([item]).catch(() => {})
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

function getColWidth(col: ColumnDef): number {
  return col.width || (col.type === 'number' ? 130 : col.type === 'date' ? 130 : 150)
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
  <div class="e1-tab-ipo-special">
    <!-- 编制提示 -->
    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 针对 IPO 及舞弊风险执行更严格的货币资金核查程序（E1-26~32），先确认本程序是否适用。</p>
        <p>2. 全额函证银行账户，核查资金流水的完整性，穿行测试大额资金往来的业务实质。</p>
        <p>3. 重点关注资金体外循环、大额异常资金往来、关联方资金占用与资金归集迹象。</p>
        <p>4. 执行未预先告知的现场监盘与银行流水穿行测试，评估管理层凌驾于控制之上的风险。</p>
      </div>
    </details>

    <!-- 审计目标 -->
    <el-alert
      type="info"
      :closable="false"
      title="审计目标：针对 IPO 及舞弊风险执行专项核查，确认货币资金真实、完整且不存在体外循环。"
      class="objective-alert"
    />

    <!-- 工具栏 -->
    <div class="tab-toolbar">
      <div class="toolbar-left">
        <el-switch
          :model-value="isApplicable"
          :disabled="isReadonly"
          active-text="已启用IPO/舞弊应对程序"
          inactive-text="未启用"
          @change="toggleApplicability"
        />
        <el-button v-if="isApplicable" size="small" type="primary" :disabled="isReadonly" @click="addRow">+ 添加行</el-button>
      </div>
      <div class="toolbar-right">
        <span class="chip-wrap"><GtIndexChip value="wp:E1-1" :context-project-id="projectId" /></span>
        <el-tag v-if="isApplicable" size="small" type="info">共 {{ rows.length }} 行</el-tag>
      </div>
    </div>

    <!-- Not applicable state -->
    <div v-if="!isApplicable" class="not-applicable">
      <el-empty description="未启用IPO程序" :image-size="80" />
    </div>

    <!-- Applicable: show table -->
    <el-skeleton v-else :loading="isLoading" :rows="10" animated>
      <template #default>
        <el-table :data="rows" border stripe size="small" max-height="550" style="width: 100%">
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
.e1-tab-ipo-special {
  padding: 12px 0;
}
.e1-tab-ipo-special :deep(.el-table) {
  --el-table-font-size: 13px;
  font-size: 13px;
}
.e1-tab-ipo-special :deep(.el-table .cell) {
  font-size: 13px !important;
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
  font-size: 13px;
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
  gap: 12px;
  align-items: center;
  flex-wrap: wrap;
}
.toolbar-right {
  display: flex;
  gap: 6px;
  align-items: center;
}
.chip-wrap { display: inline-flex; align-items: center; }

.not-applicable {
  padding: 40px 0;
}

/* 自动计算列灰底 */
:deep(.auto-calc-col) {
  background-color: #f5f7fa !important;
}
.auto-calc-value {
  color: #606266;
}
</style>
