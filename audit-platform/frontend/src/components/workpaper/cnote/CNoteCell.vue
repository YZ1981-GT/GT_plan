<!--
  CNoteCell.vue — C 类附注披露嵌套表单元格渲染器

  从 GtCNoteTable.vue 原 577-731 行内联 defineComponent 抽出为独立 SFC。
  按 design D5：保持 render function（h）形态，零行为差异。

  8 渲染分支：
  1. readonly / label → 只读 span（含 _indent 缩进 class）
  2. amount_formula → 只读 gt-amt + formatAmount(computedValue)
  3. percent_formula → 只读 + formatPercent(computedValue)
  4. boolean → ElCheckbox
  5. number → ElInputNumber（amount 时 precision=2 + gt-amt + controlsPosition right）
  6. enum → ElSelect 单选 clearable
  7. multi_enum → ElSelect multiple collapseTags
  8. date → ElDatePicker（YYYY-MM-DD）/ textarea → ElInput textarea / 默认 → ElInput text

  spec: gt-c-note-table-shrink Task 5
-->
<script lang="ts">
import { defineComponent, h } from 'vue'
import {
  ElInput,
  ElInputNumber,
  ElSelect,
  ElOption,
  ElCheckbox,
  ElDatePicker,
} from 'element-plus'
import { formatAmount } from '@/utils/formatAmount'
import { isLabelField, formatPercent } from './cnoteHelpers'
import type { ColumnDefWithKey, RowData } from '../GtCNoteTable.types'

export default defineComponent({
  name: 'CNoteCell',
  props: {
    row: { type: Object, required: true },
    col: { type: Object, required: true },
    readonly: { type: Boolean, default: false },
    computedValue: { type: [Number, String, Object] as any, default: null },
  },
  emits: ['change'],
  setup(p, { emit: emitInner }) {
    const onUpdate = (v: any) => {
      p.row[p.col.field] = v
      emitInner('change', v)
    }

    return () => {
      const col = p.col as ColumnDefWithKey
      const row = p.row as RowData

      // Read-only label / readonly columns (e.g. category_label)
      if (col.readonly || isLabelField(col.field)) {
        const indent = (row._indent ?? 0) as number
        const text = String(row[col.field] ?? row._label ?? '')
        return h(
          'span',
          {
            class: ['gt-cnt__cell-readonly', indent > 0 ? `gt-cnt__indent-${indent}` : ''].filter(Boolean).join(' '),
          },
          text,
        )
      }

      // amount_formula / percent_formula → readonly computed display
      if (col.render === 'amount_formula') {
        return h(
          'span',
          { class: 'gt-cnt__cell-readonly gt-amt' },
          formatAmount(p.computedValue as number | null),
        )
      }
      if (col.render === 'percent_formula') {
        return h(
          'span',
          { class: 'gt-cnt__cell-readonly' },
          formatPercent(p.computedValue as number | null),
        )
      }

      // checkmark display when boolean readonly
      if (col.type === 'boolean') {
        return h(ElCheckbox, {
          modelValue: !!row[col.field],
          'onUpdate:modelValue': onUpdate,
          disabled: p.readonly,
        })
      }

      if (col.type === 'number') {
        const isAmount = col.render === 'amount' || col.render === 'amount_formula'
        return h(ElInputNumber, {
          modelValue: (row[col.field] ?? null) as number | null,
          'onUpdate:modelValue': onUpdate,
          disabled: p.readonly,
          precision: isAmount ? 2 : undefined,
          controlsPosition: 'right',
          size: 'small',
          class: isAmount ? 'gt-amt gt-cnt__amount-input' : undefined,
          min: col.min,
          max: col.max,
        })
      }

      if (col.type === 'enum') {
        return h(
          ElSelect,
          {
            modelValue: row[col.field],
            'onUpdate:modelValue': onUpdate,
            disabled: p.readonly,
            size: 'small',
            clearable: true,
            placeholder: col.label,
          },
          {
            default: () =>
              (col.enum || []).map(opt =>
                h(ElOption, { key: opt, label: opt, value: opt }),
              ),
          },
        )
      }

      if (col.type === 'multi_enum') {
        return h(
          ElSelect,
          {
            modelValue: row[col.field] ?? [],
            'onUpdate:modelValue': onUpdate,
            disabled: p.readonly,
            size: 'small',
            multiple: true,
            collapseTags: true,
            collapseTagsTooltip: true,
            placeholder: col.label,
          },
          {
            default: () =>
              (col.enum || []).map(opt =>
                h(ElOption, { key: opt, label: opt, value: opt }),
              ),
          },
        )
      }

      if (col.type === 'date') {
        return h(ElDatePicker, {
          modelValue: row[col.field],
          'onUpdate:modelValue': onUpdate,
          disabled: p.readonly,
          size: 'small',
          type: 'date',
          format: 'YYYY-MM-DD',
          valueFormat: 'YYYY-MM-DD',
          placeholder: col.label,
        })
      }

      if (col.type === 'textarea') {
        return h(ElInput, {
          modelValue: row[col.field],
          'onUpdate:modelValue': onUpdate,
          disabled: p.readonly,
          size: 'small',
          type: 'textarea',
          rows: 2,
          maxlength: col.max_length,
          showWordLimit: !!col.max_length,
          placeholder: col.label,
        })
      }

      // Default: text
      return h(ElInput, {
        modelValue: row[col.field],
        'onUpdate:modelValue': onUpdate,
        disabled: p.readonly,
        size: 'small',
        maxlength: col.max_length,
        placeholder: col.label,
      })
    }
  },
})
</script>

<style scoped>
.gt-cnt__cell-readonly {
  display: inline-block;
  width: 100%;
  padding: 0 4px;
  color: var(--el-text-color-regular);
  font-variant-numeric: tabular-nums;
}
.gt-cnt__indent-1 { padding-left: 16px; }
.gt-cnt__indent-2 { padding-left: 32px; }
.gt-cnt__amount-input :deep(.el-input__inner) {
  font-family: 'Arial Narrow', Arial, sans-serif;
  font-variant-numeric: tabular-nums;
  text-align: right;
}
</style>
