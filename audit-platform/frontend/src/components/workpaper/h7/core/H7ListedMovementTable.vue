<template>
  <el-table :data="displayRows" border size="small" class="h7-movement-table">
    <el-table-column prop="label" label="项目" min-width="190" fixed="left">
      <template #default="{ row }">
        <span :class="`indent-${row.indent}`" :style="{ fontWeight: row.kind === 'section' ? 600 : 400 }">
          {{ row.label }}
        </span>
      </template>
    </el-table-column>

    <!-- 两级表头：产业（父）→ 类别（叶子），与源模板 B9:C9 … 合并区同构 -->
    <el-table-column
      v-for="grp in groups"
      :key="grp.industry"
      :label="grp.label"
      align="center"
    >
      <el-table-column
        v-for="cat in grp.categories"
        :key="cat.key"
        :label="cat.label"
        min-width="140"
        align="right"
      >
        <template #header>
          <span class="cat-head">
            <span class="cat-name" :title="`类别列「${cat.label}」（${grp.label}）`">{{ cat.label }}</span>
            <el-button
              v-if="!isReadonly"
              size="small"
              link
              :aria-label="`重命名类别列 ${cat.label}`"
              @click.stop="emit('rename', cat.key)"
            >✎</el-button>
            <el-button
              v-if="!isReadonly"
              size="small"
              link
              :aria-label="`删除类别列 ${cat.label}`"
              @click.stop="emit('remove', cat.key)"
            >✕</el-button>
          </span>
        </template>
        <template #default="{ row }">
          <span v-if="row.kind === 'section'" class="na-cell">—</span>
          <WpAmountInput
            v-else-if="row.editable"
            :model-value="cellOf(row.key, cat.key)"
            :disabled="isReadonly"
            :aria-label="`${row.label} ${cat.label}`"
            @change="(v: number) => emit('cell-change', row.key, cat.key, v)"
          />
          <span v-else class="formula-cell" :title="row.formula">{{ fmtAmount(cellOf(row.key, cat.key)) }}</span>
        </template>
      </el-table-column>
    </el-table-column>

    <el-table-column label="合计" min-width="150" align="right" class-name="auto-calc-col">
      <template #default="{ row }">
        <span v-if="row.kind === 'section'" class="na-cell">—</span>
        <span v-else class="formula-cell" title="合计 = 各类别列之和">{{ fmtAmount(row.total) }}</span>
      </template>
    </el-table-column>
  </el-table>
</template>

<script setup lang="ts">
/**
 * H7ListedMovementTable — H7 上市披露的「产业 × 类别」两级表头变动表（成本 / 公允价值共用）
 *
 * 源模板合并区 `A9:A10`（项目 rowspan2）/ `B9:C9` 种植业 / … / `J9:J10`（合计 rowspan2）。
 * 派生行读时推导、只读并带公式 tooltip；可录入格用 `WpAmountInput`（千分符）。
 *
 * spec: h7-biological-assets-disclosure-rebuild (Task 6)
 */
import { computed } from 'vue'
import WpAmountInput from '../../shared/WpAmountInput.vue'
// 🔴 `fmtAmount` 是 store **成员**（`useDisplayPrefsStore().fmtAmount`），不是模块命名导出。
// 写成 `import { fmtAmount } from '@/stores/displayPrefs'` 会在**运行时**抛
// `does not provide an export named 'fmtAmount'`（Vite transform 200、vitest 与
// get_diagnostics 全绿，只有浏览器挂载时才暴露 —— 本 spec 实测踩中）。
import { useDisplayPrefsStore } from '@/stores/displayPrefs'
import {
  H7_INDUSTRIES,
  h7CellValue,
  h7RowFormula,
  h7TotalCellValue,
  isH7EditableRow,
  orderH7Categories,
  type H7ListedCategory,
  type H7MovementRowDef,
  type MovementCellMap,
} from '../../composables/h7ListedDisclosureModel'

const props = defineProps<{
  rows: readonly H7MovementRowDef[]
  categories: readonly H7ListedCategory[]
  map: MovementCellMap
  isReadonly: boolean
  tableKey: string
}>()

const emit = defineEmits<{
  (e: 'cell-change', rowKey: string, colKey: string, value: number): void
  (e: 'rename', catKey: string): void
  (e: 'remove', catKey: string): void
}>()

const prefs = useDisplayPrefsStore()
/** 走平台金额格式单一真源（千分符 + 单位偏好 + showZero 偏好） */
const fmtAmount = (v: number | null | undefined): string => prefs.fmtAmount(v)

const ordered = computed(() => orderH7Categories(props.categories))

/** 只输出「有类别列」的产业分组（源模板四类固定，但删空后不渲染空分组） */
const groups = computed(() =>
  H7_INDUSTRIES
    .map((ind) => ({
      industry: ind.key,
      label: ind.label,
      categories: ordered.value.filter((c) => c.industry === ind.key),
    }))
    .filter((g) => g.categories.length > 0),
)

const displayRows = computed(() =>
  props.rows.map((def) => ({
    key: def.key,
    label: def.label,
    indent: def.indent,
    kind: def.kind,
    editable: isH7EditableRow(def),
    formula: h7RowFormula(def),
    total: h7TotalCellValue(props.map, def, ordered.value, props.rows),
  })),
)

function cellOf(rowKey: string, colKey: string): number {
  const def = props.rows.find((r) => r.key === rowKey)
  if (!def) return 0
  return h7CellValue(props.map, def, colKey, props.rows)
}
</script>

<style scoped>
.h7-movement-table { font-size: var(--wp-font-size, 13px); }
.h7-movement-table :deep(.auto-calc-col) { background: var(--el-fill-color-lighter); }
.indent-1 { padding-left: 14px; }
.indent-2 { padding-left: 28px; }
.formula-cell {
  font-variant-numeric: tabular-nums;
  border-bottom: 1px dashed var(--el-border-color);
  cursor: help;
}
.na-cell { color: var(--el-text-color-placeholder); }
.cat-head { display: inline-flex; align-items: center; gap: 2px; }
.cat-name { font-weight: 500; }
</style>
