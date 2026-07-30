<template>
  <div class="n1-seg-table">
  <el-table
    :data="displayRows"
    border
    size="small"
    style="width: 100%"
    :span-method="spanMethod"
    :row-class-name="rowClassName"
  >
    <!-- 标签列（项目名） -->
    <el-table-column :label="labelHeader" min-width="220" fixed>
      <template #default="{ row }">
        <span v-if="row._kind === 'group'" class="n1-seg-group-label">{{ row.item }}</span>
        <span v-else-if="row._kind === 'subtotal'" class="n1-seg-total-label">{{ row.item }}</span>
        <el-input
          v-else-if="!readonly && row._editableLabel"
          :model-value="row.item"
          size="small"
          placeholder="填写项目名称"
          @change="(v: string) => onLabelChange(row, v)"
        />
        <span v-else>{{ row.item }}</span>
      </template>
    </el-table-column>

    <!-- 值列：相邻同 group 的列合并为两级表头（对齐源模板 B10:C10 / D10:E10） -->
    <template v-for="(blk, bi) in headerBlocks" :key="`blk-${bi}`">
      <el-table-column v-if="blk.group" :label="blk.group" align="center">
        <el-table-column
          v-for="col in blk.columns"
          :key="col.key"
          :label="col.label"
          :min-width="col.minWidth || 150"
          align="right"
        >
          <template #default="{ row }">
            <span v-if="row._kind === 'group'">—</span>
            <span v-else-if="row._kind === 'subtotal'" class="n1-seg-formula">
              {{ fmtAmount(row[col.key]) }}
            </span>
            <WpAmountInput
              v-else-if="!readonly"
              :model-value="(row[col.key] as number | null) ?? 0"
              :aria-label="`${row.item} ${col.label}`"
              @change="(v: number) => onValueChange(row, col.key, v)"
            />
            <span v-else>{{ fmtAmount(row[col.key]) }}</span>
          </template>
        </el-table-column>
      </el-table-column>
      <el-table-column
        v-else
        :label="blk.columns[0].label"
        :min-width="blk.columns[0].minWidth || 150"
        :align="blk.columns[0].format === 'text' ? 'left' : 'right'"
      >
        <template #default="{ row }">
          <span v-if="row._kind === 'group'">—</span>
          <template v-else-if="blk.columns[0].format === 'text'">
            <el-input
              v-if="!readonly && row._kind === 'data'"
              :model-value="(row[blk.columns[0].key] as string) ?? ''"
              size="small"
              :placeholder="blk.columns[0].placeholder || ''"
              @change="(v: string) => onTextChange(row, blk.columns[0].key, v)"
            />
            <span v-else>{{ row[blk.columns[0].key] || '—' }}</span>
          </template>
          <span v-else-if="row._kind === 'subtotal'" class="n1-seg-formula">
            {{ fmtAmount(row[blk.columns[0].key]) }}
          </span>
          <WpAmountInput
            v-else-if="!readonly"
            :model-value="(row[blk.columns[0].key] as number | null) ?? 0"
            :aria-label="`${row.item} ${blk.columns[0].label}`"
            @change="(v: number) => onValueChange(row, blk.columns[0].key, v)"
          />
          <span v-else>{{ fmtAmount(row[blk.columns[0].key]) }}</span>
        </template>
      </el-table-column>
    </template>

    <!-- 操作列（仅用户动态新增的行可删；源模板固定行不可删） -->
    <el-table-column v-if="showActionColumn" label="操作" width="72" align="center" fixed="right">
      <template #default="{ row }">
        <el-button
          v-if="row._kind === 'data' && row._editableLabel"
          text
          type="danger"
          size="small"
          @click="onRemoveRow(row)"
        >
          删除
        </el-button>
        <span v-else>—</span>
      </template>
    </el-table-column>
  </el-table>

  <!-- 源模板每段留有空白预留行（上市 R20 / R28），平台改为按需增行 -->
  <div v-if="showActionColumn" class="n1-seg-footer">
    <el-button
      v-for="seg in segments"
      :key="`add-${seg.key}`"
      text
      type="primary"
      size="small"
      @click="onAddRow(seg.key)"
    >
      + 新增{{ seg.label ? seg.label.replace(/[一二、：]/g, '') : '' }}行
    </el-button>
  </div>
  </div>
</template>

<script setup lang="ts">
/**
 * N1DisclosureSegmentTable — 分段（资产段 / 负债段）+ 可选两级表头的披露表
 *
 * 源模板依据：`N1 递延所得税资产.xlsx` 披露 sheet 的表（1）与国企表（2）都是
 * 「整行合并的分组标题 + 明细行 + 段末小计」结构（A12:E12 / A22:E22 为整行合并），
 * 且表（1）带两级表头（B10:C10 期末余额 / D10:E10 上年年末余额）。
 *
 * 本组件把这套结构做成两变体共用：
 * - 列序 / 父表头由 `columns` 驱动（相邻同 `group` 的列自动合并为两级表头）
 * - 分组标题行用 `span-method` 整行合并
 * - 段末小计行为公式行（只读，由父组件按源模板 `=SUM(...)` 计算后传入）
 * - 明细行支持在段末「+ 行」新增（源模板每段留有空白预留行）
 *
 * 🔴 两版子列序相反（上市暂时性差异在前 / 国企资产负债在前）—— 由父组件引用
 * `n1UnoffsetSubOrder(variant)` 产出 `columns`，本组件不做变体判断。
 */
import { computed, inject } from 'vue'
import { useDisplayPrefsStore } from '@/stores/displayPrefs'
import { DisplayPrefs_Key } from '../../composables/displayPrefsKey'
import WpAmountInput from '../../shared/WpAmountInput.vue'
// 🔴 类型必须从 .ts 引入：`<script setup>` 不允许 `export interface`（SFC 编译失败，
// 且 Volar 诊断查不出，只有 Vite transform 报 500）
import type {
  N1SegColumn,
  N1SegRow,
  N1Segment,
} from '../../composables/n1DisclosureSegmentTypes'

const props = withDefaults(
  defineProps<{
    labelHeader: string
    columns: N1SegColumn[]
    segments: N1Segment[]
    readonly?: boolean
    allowAddRow?: boolean
  }>(),
  { readonly: false, allowAddRow: true },
)

/** 金额格式单一真源（千分符 + 2 位小数 + 单位后缀，见 stores/displayPrefs） */
const displayPrefs = inject(DisplayPrefs_Key, null) ?? useDisplayPrefsStore()
function fmtAmount(v: unknown): string {
  if (v === null || v === undefined || v === '') return '—'
  const n = Number(v)
  return Number.isFinite(n) ? displayPrefs.fmtAmount(n) : '—'
}

const emit = defineEmits<{
  (e: 'change-cell', payload: { seg: string; index: number; key: string; value: number | string }): void
  (e: 'add-row', seg: string): void
  (e: 'remove-row', payload: { seg: string; index: number }): void
  (e: 'change-label', payload: { seg: string; index: number; value: string }): void
}>()

/** 相邻同 group 的列合并成一个表头块；无 group 的列各自成块 */
const headerBlocks = computed(() => {
  const blocks: Array<{ group?: string; columns: N1SegColumn[] }> = []
  for (const col of props.columns) {
    const last = blocks[blocks.length - 1]
    if (col.group && last && last.group === col.group) {
      last.columns.push(col)
    } else {
      blocks.push({ group: col.group, columns: [col] })
    }
  }
  return blocks
})

interface DisplayRow extends N1SegRow {
  _kind: 'group' | 'data' | 'subtotal'
  _seg: string
  _index: number
}

const displayRows = computed<DisplayRow[]>(() => {
  const out: DisplayRow[] = []
  for (const seg of props.segments) {
    // 空 label = 单段平表（表 2/3/4/5 无资产/负债分段），不渲染分组标题行
    if (seg.label) out.push({ item: seg.label, _kind: 'group', _seg: seg.key, _index: -1 })
    seg.rows.forEach((r, i) => out.push({ ...r, _kind: 'data', _seg: seg.key, _index: i }))
    if (seg.subtotal) {
      out.push({
        item: seg.subtotalLabel || '小计',
        ...seg.subtotal,
        _kind: 'subtotal',
        _seg: seg.key,
        _index: -1,
      })
    }
  }
  return out
})

const showActionColumn = computed(() => !props.readonly && props.allowAddRow)

/** 分组标题行整行合并（对齐源模板 A12:E12 / A22:E22） */
function spanMethod({ row, columnIndex }: { row: DisplayRow; columnIndex: number }) {
  if (row._kind !== 'group') return
  const totalCols = 1 + props.columns.length + (showActionColumn.value ? 1 : 0)
  return columnIndex === 0 ? { rowspan: 1, colspan: totalCols } : { rowspan: 1, colspan: 0 }
}

function rowClassName({ row }: { row: DisplayRow }): string {
  if (row._kind === 'group') return 'n1-seg-group-row'
  if (row._kind === 'subtotal') return 'n1-seg-subtotal-row'
  return ''
}

function onValueChange(row: DisplayRow, key: string, value: number): void {
  emit('change-cell', { seg: row._seg, index: row._index, key, value })
}

function onTextChange(row: DisplayRow, key: string, value: string): void {
  emit('change-cell', { seg: row._seg, index: row._index, key, value })
}

function onLabelChange(row: DisplayRow, value: string): void {
  emit('change-label', { seg: row._seg, index: row._index, value })
}

function onAddRow(seg: string): void {
  emit('add-row', seg)
}

function onRemoveRow(row: DisplayRow): void {
  emit('remove-row', { seg: row._seg, index: row._index })
}
</script>

<style scoped>
:deep(.el-table) {
  font-size: var(--wp-font-size, 13px);
}
:deep(.n1-seg-group-row) {
  background: #f5f7fa !important;
}
:deep(.n1-seg-subtotal-row) {
  background: #f0f9eb !important;
  font-weight: 600;
}
.n1-seg-group-label {
  font-weight: 700;
  color: #303133;
}
.n1-seg-total-label {
  font-weight: 700;
  color: #303133;
}
.n1-seg-formula {
  color: #409eff;
  font-weight: 500;
}
.n1-seg-footer {
  display: flex;
  gap: 12px;
  padding: 6px 2px 0;
}
:deep(td.is-right .cell) {
  white-space: nowrap;
  font-variant-numeric: tabular-nums;
}
</style>
