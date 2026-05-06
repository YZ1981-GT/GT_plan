<!--
  GtStatusTag — 通用状态标签组件 [R5.7]
  配合 statusMaps.ts 使用，消除各模块重复的 el-tag + statusTagType/statusLabel 模式。
  优先使用 dictStore 数据（服务端字典），dictStore 未加载时回退到 statusMaps.ts。

  用法：
    <!-- 方式1：传 statusMap + statusMapName，自动推断 dictStore key（推荐） -->
    <GtStatusTag :status-map="WP_STATUS" status-map-name="WP_STATUS" :value="row.status" />
    <!-- 方式2：显式传 dictKey -->
    <GtStatusTag dict-key="wp_status" :value="row.status" />
    <!-- 方式3：只传 statusMap，不走 dictStore（兼容旧用法） -->
    <GtStatusTag :status-map="WP_STATUS" :value="row.status" />
-->
<template>
  <el-tag :type="tagType as any" :size="size">{{ tagLabel }}</el-tag>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { getStatusLabel, getStatusType } from '@/utils/statusMaps'
import type { StatusMap } from '@/utils/statusMaps'
import { useDictStore } from '@/stores/dict'

// statusMap 变量名 → dictStore key 的映射表
// 当调用方传入 statusMapName 时，自动推断对应的 dictStore key，实现 dictStore 优先
const STATUS_MAP_TO_DICT_KEY: Record<string, string> = {
  WP_STATUS: 'wp_status',
  WP_REVIEW_STATUS: 'wp_review_status',
  ADJUSTMENT_STATUS: 'adjustment_status',
  REPORT_STATUS: 'report_status',
  TEMPLATE_STATUS: 'template_status',
  PROJECT_STATUS: 'project_status',
  ISSUE_STATUS: 'issue_status',
  PDF_TASK_STATUS: 'pdf_task_status',
}

const props = defineProps<{
  /** 状态映射表（如 WP_STATUS / ADJUSTMENT_STATUS） */
  statusMap?: StatusMap
  /**
   * statusMap 对应的变量名（如 'WP_STATUS'），用于自动推断 dictStore key。
   * 传入后组件会优先查 dictStore，无需再单独传 dictKey。
   */
  statusMapName?: string
  /** dictStore 字典键（如 'wp_status'），优先级最高，与 statusMapName 二选一 */
  dictKey?: string
  /** 当前状态值 */
  value: string | undefined | null
  /** 标签尺寸，默认 small */
  size?: 'large' | 'default' | 'small'
}>()

const dictStore = useDictStore()

/** 解析最终使用的 dictStore key：显式 dictKey > statusMapName 推断 */
const resolvedDictKey = computed(() => {
  if (props.dictKey) return props.dictKey
  if (props.statusMapName) return STATUS_MAP_TO_DICT_KEY[props.statusMapName] ?? null
  return null
})

const tagType = computed(() => {
  if (!props.value) return 'info'
  // 优先：dictStore（通过 dictKey 或 statusMapName 推断）
  if (resolvedDictKey.value && dictStore.loaded) {
    const t = dictStore.type(resolvedDictKey.value, props.value)
    if (t) return t
  }
  // 回退：statusMaps.ts
  if (props.statusMap) return getStatusType(props.statusMap, props.value)
  return 'info'
})

const tagLabel = computed(() => {
  if (!props.value) return '—'
  // 优先：dictStore
  if (resolvedDictKey.value && dictStore.loaded) {
    const l = dictStore.label(resolvedDictKey.value, props.value)
    if (l && l !== props.value) return l
  }
  // 回退：statusMaps.ts
  if (props.statusMap) return getStatusLabel(props.statusMap, props.value)
  return props.value
})
</script>
