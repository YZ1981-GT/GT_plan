<!--
  GtStatusTag — 通用状态标签组件 [R5.7]
  配合 statusMaps.ts 使用，消除各模块重复的 el-tag + statusTagType/statusLabel 模式

  用法：
    <GtStatusTag :status-map="WP_STATUS" :value="row.status" />
    <GtStatusTag :status-map="ADJUSTMENT_STATUS" :value="row.review_status" />
-->
<template>
  <el-tag :type="tagType" size="small">{{ tagLabel }}</el-tag>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { getStatusLabel, getStatusType } from '@/utils/statusMaps'
import type { StatusMap } from '@/utils/statusMaps'

const props = defineProps<{
  /** 状态映射表（如 WP_STATUS / ADJUSTMENT_STATUS） */
  statusMap: StatusMap
  /** 当前状态值 */
  value: string | undefined | null
}>()

const tagType = computed(() => getStatusType(props.statusMap, props.value))
const tagLabel = computed(() => getStatusLabel(props.statusMap, props.value))
</script>
