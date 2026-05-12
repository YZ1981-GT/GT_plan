<!--
  GtStatusTag — 通用状态标签组件 [R5.7, R7-S3-02 简化]

  唯一数据源：dictStore（后端 /api/system/dicts 下发）。
  不再支持前端硬编码 statusMaps.ts 回退。

  用法：
    <GtStatusTag dict-key="wp_status" :value="row.status" />
    <GtStatusTag dict-key="adjustment_status" :value="row.review_status" size="default" />
-->
<template>
  <el-tag :type="tagType as any" :size="size" effect="light">{{ tagLabel }}</el-tag>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useDictStore } from '@/stores/dict'

const props = withDefaults(defineProps<{
  /** dictStore 字典键（如 'wp_status'、'adjustment_status'） */
  dictKey: string
  /** 当前状态值 */
  value: string | undefined | null
  /** 标签尺寸，默认 small */
  size?: 'large' | 'default' | 'small'
}>(), {
  size: 'small',
})

const dictStore = useDictStore()

const tagType = computed(() => {
  if (!props.value) return 'info'
  if (dictStore.loaded) {
    return dictStore.type(props.dictKey, props.value)
  }
  return 'info'
})

const tagLabel = computed(() => {
  if (!props.value) return '—'
  if (dictStore.loaded) {
    const l = dictStore.label(props.dictKey, props.value)
    if (l && l !== props.value) return l
  }
  return props.value
})
</script>
