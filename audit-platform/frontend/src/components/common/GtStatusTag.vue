<!--
  GtStatusTag — 通用状态标签组件 [R5.7, R7-S3-02 简化]

  唯一数据源：dictStore（后端 /api/system/dicts 下发）。
  不再支持前端硬编码 statusMaps.ts 回退。

  用法：
    <GtStatusTag dict-key="wp_status" :value="row.status" />
    <GtStatusTag dict-key="adjustment_status" :value="row.review_status" size="default" />

  动画：value 变化时自动添加 .is-flipping 类触发 gt-polish.css flip 动画（400ms），
  对应 [proposal-remaining-18 task 5.5 UI-8]。可通过 :flip="false" 关闭。
-->
<template>
  <el-tag
    :type="tagType as any"
    :size="size"
    effect="light"
    :class="{ 'is-flipping': flipping }"
  >{{ tagLabel }}</el-tag>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useDictStore } from '@/stores/dict'

const props = withDefaults(defineProps<{
  /** dictStore 字典键（如 'wp_status'、'adjustment_status'） */
  dictKey: string
  /** 当前状态值 */
  value: string | undefined | null
  /** 标签尺寸，默认 small */
  size?: 'large' | 'default' | 'small'
  /** 是否在 value 变化时播放 flip 动画，默认 true */
  flip?: boolean
}>(), {
  size: 'small',
  flip: true,
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

// ─── flip 动画触发（gt-polish.css .is-flipping，400ms）───
const flipping = ref(false)
let flipTimer: ReturnType<typeof setTimeout> | null = null
watch(
  () => props.value,
  (newVal, oldVal) => {
    if (!props.flip) return
    // 首次赋值不触发（oldVal === undefined），仅在 value 真变化时触发
    if (oldVal !== undefined && newVal !== oldVal) {
      if (flipTimer) clearTimeout(flipTimer)
      flipping.value = true
      flipTimer = setTimeout(() => {
        flipping.value = false
        flipTimer = null
      }, 400)
    }
  },
)
</script>
