<script setup lang="ts">
/**
 * A17ContentRenderer — 渲染模式下解析 chapter content 中的 wp_code 模式
 * 替换为 RefChipInline 组件。
 *
 * 用于只读渲染场景（渲染模式 / source_label 区域）。
 *
 * Requirements: 2.1, 2.4, 2.5
 */
import { computed } from 'vue'
import { extractWpCodes } from '@/composables/useWpCodeParser'
import type { WpCodeNavState } from '@/composables/useA17Navigation'
import RefChipInline from './RefChipInline.vue'

const props = defineProps<{
  content: string
  /** wp_code → nav state 映射（由父组件通过 useA17Navigation 提供） */
  navStateMap: Record<string, WpCodeNavState>
  projectId: string
}>()

interface ContentSegment {
  type: 'text' | 'chip'
  value: string
  navState?: WpCodeNavState
}

/**
 * 将文本内容分割为文本段和 wp_code 芯片段
 */
const segments = computed<ContentSegment[]>(() => {
  if (!props.content) return []

  const wpCodes = extractWpCodes(props.content)
  if (wpCodes.length === 0) {
    return [{ type: 'text', value: props.content }]
  }

  const result: ContentSegment[] = []
  let remaining = props.content

  // 用正则逐个匹配并分割
  const WP_CODE_RE = /[A-S]\d{1,2}(?:-\d{1,2})?(?:[A-Z])?/g
  let match: RegExpExecArray | null
  let lastIndex = 0

  WP_CODE_RE.lastIndex = 0
  while ((match = WP_CODE_RE.exec(remaining)) !== null) {
    // 前面的文本部分
    if (match.index > lastIndex) {
      result.push({ type: 'text', value: remaining.slice(lastIndex, match.index) })
    }
    // wp_code 芯片
    const code = match[0]
    result.push({
      type: 'chip',
      value: code,
      navState: props.navStateMap[code] || { exists: false, wpId: null, disabled: true, tooltip: '该底稿在当前项目中不存在' },
    })
    lastIndex = match.index + code.length
  }
  // 尾部文本
  if (lastIndex < remaining.length) {
    result.push({ type: 'text', value: remaining.slice(lastIndex) })
  }

  return result
})
</script>

<template>
  <span class="a17-content-renderer">
    <template v-for="(seg, idx) in segments" :key="idx">
      <span v-if="seg.type === 'text'" v-html="seg.value" />
      <RefChipInline
        v-else
        :wp-code="seg.value"
        :disabled="seg.navState?.disabled ?? true"
        :tooltip="seg.navState?.tooltip"
        :project-id="projectId"
        :wp-id="seg.navState?.wpId ?? undefined"
      />
    </template>
  </span>
</template>

<style scoped>
.a17-content-renderer {
  display: inline;
}
</style>
