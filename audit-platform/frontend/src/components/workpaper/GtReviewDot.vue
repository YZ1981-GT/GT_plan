<script setup lang="ts">
/**
 * 复核线程蓝/红点指示器（section 级或行级）
 */
import { computed, inject } from 'vue'

const props = defineProps<{
  sectionId?: string
  rowPrefix?: string
  rowKey?: string
}>()

type DotFn = (id: string) => 'blue' | 'red' | null
type RowDotFn = (prefix: string, rowKey: string) => 'blue' | 'red' | null

const getThreadDot = inject<DotFn | null>('getThreadDot', null)
  ?? inject<DotFn | null>('d1GetThreadDot', null)
  ?? inject<DotFn | null>('d2GetThreadDot', null)
  ?? inject<DotFn | null>('d3GetThreadDot', null)
const getRowDot = inject<RowDotFn | null>('getRowDot', null)
  ?? inject<RowDotFn | null>('d1GetRowDot', null)
  ?? inject<RowDotFn | null>('d2GetRowDot', null)
  ?? inject<RowDotFn | null>('d3GetRowDot', null)

const dot = computed((): 'blue' | 'red' | null => {
  if (props.sectionId && getThreadDot) {
    return getThreadDot(props.sectionId)
  }
  if (props.rowPrefix && props.rowKey && getRowDot) {
    return getRowDot(props.rowPrefix, props.rowKey)
  }
  return null
})
</script>

<template>
  <span v-if="dot" :class="['gt-review-dot', dot]" />
</template>

<style scoped>
.gt-review-dot {
  display: inline-block;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  margin-left: 4px;
  vertical-align: super;
}
.gt-review-dot.blue { background: #409eff; }
.gt-review-dot.red { background: #f56c6c; }
</style>
