<template>
  <el-tooltip v-if="fixed" content="集团下推的固定行：行名不能改、不能删（合并附注按它对应合并模板行）" placement="top">
    <span class="gt-pushed-mark" data-testid="note-pushed-fixed" aria-label="集团下推的固定行">🔒</span>
  </el-tooltip>
  <el-checkbox
    v-else-if="optional && editable"
    :model-value="inactive"
    size="small"
    class="gt-pushed-optional"
    data-testid="note-pushed-optional"
    @change="(v: string | number | boolean) => emit('toggle', !v)"
    @click.stop
  >本企业不适用</el-checkbox>
  <el-tag v-else-if="optional && inactive" size="small" type="info" class="gt-pushed-optional">本企业不适用</el-tag>
</template>

<script setup lang="ts">
/**
 * 集团下推行的标记（spec note-pull-followup-closure R14）：固定行（required）显示锁、行名只读；可选行（optional）
 * 编辑时可勾「本企业不适用」（写 `_pushed_optional_active = false`，合并拉数不取这一行，R12）。
 */
import { computed } from 'vue'
import { isPushedFixedRow } from '@/composables/useNoteTableStructure'

const props = defineProps<{ row: Record<string, any> | null | undefined; editable: boolean }>()
const emit = defineEmits<{ (e: 'toggle', active: boolean): void }>()

const fixed = computed(() => isPushedFixedRow(props.row))
const optional = computed(() => !!props.row?._pushed_row_id && props.row?._pushed_category === 'optional')
const inactive = computed(() => props.row?._pushed_optional_active === false)
</script>

<style scoped>
.gt-pushed-mark {
  margin-left: 4px;
  font-size: 11px;
  cursor: help;
}
.gt-pushed-optional {
  margin-left: 6px;
}
</style>
