<!--
  GtStatusTag — 通用状态标签组件 [R5.7]
  配合 statusMaps.ts 使用，消除各模块重复的 el-tag + statusTagType/statusLabel 模式。
  优先使用 dictStore 数据（服务端字典），dictStore 未加载时回退到 statusMaps.ts。

  用法：
    <GtStatusTag :status-map="WP_STATUS" :value="row.status" />
    <GtStatusTag :status-map="ADJUSTMENT_STATUS" :value="row.review_status" />
    <!-- 直接使用 dictStore 字典键（不传 statusMap） -->
    <GtStatusTag dict-key="wp_status" :value="row.status" />
-->
<template>
  <el-tag :type="tagType as any" :size="size">{{ tagLabel }}</el-tag>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { getStatusLabel, getStatusType } from '@/utils/statusMaps'
import type { StatusMap } from '@/utils/statusMaps'
import { useDictStore } from '@/stores/dict'

const props = defineProps<{
  /** 状态映射表（如 WP_STATUS / ADJUSTMENT_STATUS），与 dictKey 二选一 */
  statusMap?: StatusMap
  /** dictStore 字典键（如 'wp_status'），优先级高于 statusMap */
  dictKey?: string
  /** 当前状态值 */
  value: string | undefined | null
  /** 标签尺寸，默认 small */
  size?: 'large' | 'default' | 'small'
}>()

const dictStore = useDictStore()

const tagType = computed(() => {
  if (!props.value) return 'info'
  // 优先：dictKey 直接查 dictStore
  if (props.dictKey && dictStore.loaded) {
    const t = dictStore.type(props.dictKey, props.value)
    if (t) return t
  }
  // 次优：statusMap 里查 dictStore（按 dictKey 推断）
  if (props.statusMap && dictStore.loaded) {
    // 尝试从 dictStore 取（dictStore 数据覆盖 statusMap）
    // 此处不做推断，直接回退到 statusMap
  }
  // 回退：statusMaps.ts
  if (props.statusMap) return getStatusType(props.statusMap, props.value)
  return 'info'
})

const tagLabel = computed(() => {
  if (!props.value) return '—'
  // 优先：dictKey 直接查 dictStore
  if (props.dictKey && dictStore.loaded) {
    const l = dictStore.label(props.dictKey, props.value)
    if (l && l !== props.value) return l
  }
  // 回退：statusMaps.ts
  if (props.statusMap) return getStatusLabel(props.statusMap, props.value)
  return props.value
})
</script>
