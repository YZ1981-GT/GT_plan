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
    <!-- Applicability Switch -->
    <div class="applicability-bar">
      <el-switch
        :model-value="isApplicable"
        :disabled="isReadonly"
        active-text="已启用IPO/舞弊应对程序"
        inactive-text="未启用"
        @change="toggleApplicability"
      />
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
          >
            <template #default="{ row }">
              <!-- Computed: readonly -->
              <span v-if="col.type === 'computed'" class="computed-cell">
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

        <el-button v-if="!isReadonly" size="small" class="add-btn" @click="addRow">+ 添加行</el-button>
      </template>
    </el-skeleton>
  </div>
</template>

<style scoped>
.e1-tab-ipo-special {
  padding: 12px 0;
}
.applicability-bar {
  margin-bottom: 12px;
  padding: 8px 12px;
  background: #f5f7fa;
  border-radius: 4px;
}
.not-applicable {
  padding: 40px 0;
}
.computed-cell {
  color: #606266;
  font-style: italic;
}
.add-btn {
  margin-top: 8px;
}
</style>
