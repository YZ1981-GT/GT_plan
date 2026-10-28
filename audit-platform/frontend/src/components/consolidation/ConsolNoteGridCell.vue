<script setup lang="ts">
/**
 * 合并附注表格单元格（spec excel-style-table-editing 5.6）。
 *
 * 原 ConsolNoteTab 用 useLazyEdit + @click 自己切输入框、@input 即改行；现在交给 GtGridCell / GridKernel：
 * Excel 方式双击 / F2 / 直接输入，单击编辑方式单击，经典方式常驻。单向 modelValue 让 Esc 真正还原，提交才改行。
 */
import { computed } from 'vue'
import type { CellComment } from '@/composables/useCellComments'
import CommentTooltip from '@/components/common/CommentTooltip.vue'
import GtGridCell from '@/components/grid/GtGridCell.vue'
import { ElInput } from '@/components/grid/adapters'

const props = withDefaults(defineProps<{
  value: unknown
  label: string
  editable: boolean
  manual?: boolean
  left?: boolean
  comment?: CellComment | null
}>(), { manual: false, left: false, comment: undefined })

const emit = defineEmits<{ commit: [value: string] }>()

const text = computed(() => props.value == null ? '' : String(props.value))
const display = computed(() => text.value || '-')
</script>

<template>
  <CommentTooltip :comment="comment">
    <GtGridCell :editable="editable" :value="value" :text="text">
      <template #display>
        <span
          class="gt-note-cell-text"
          :class="{ 'gt-note-cell-editable': editable, 'gt-note-cell-manual': manual }"
          :title="manual ? '手工单元格：按公式填入时保留' : ''"
          :style="{ textAlign: left ? 'left' : 'right' }"
        >{{ display }}</span>
      </template>
      <ElInput
        :model-value="text"
        size="small"
        :placeholder="label"
        :class="{ 'gt-note-cell-manual': manual }"
        :style="{ textAlign: left ? 'left' : 'right' }"
        @change="emit('commit', String($event ?? ''))"
      />
    </GtGridCell>
  </CommentTooltip>
</template>
