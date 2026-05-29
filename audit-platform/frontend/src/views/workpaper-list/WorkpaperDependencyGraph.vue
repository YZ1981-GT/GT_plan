<template>
  <div class="gt-wp-dep-graph-wrapper" style="flex: 1; min-height: 0">
    <InnerGraph
      :project-id="props.projectId"
      style="flex: 1; min-height: 0"
      @navigate="onNavigate"
    />
  </div>
</template>

<script setup lang="ts">
/**
 * WorkpaperDependencyGraph — 薄包装 SFC
 * 桥接已有 components/workpaper/WorkpaperDependencyGraph.vue + D3 lazy import
 * Requirements: 2.4, 3.1, 3.2, 3.3, 3.6, 7.2
 */
import { inject, onMounted } from 'vue'
import { WP_LIST_CONTEXT_KEY } from '@/composables/useWorkpaperListContext'
import type { WpChildProps, WpChildEmits } from '@/composables/useWorkpaperListContext'
import InnerGraph from '@/components/workpaper/WorkpaperDependencyGraph.vue'

defineOptions({ name: 'WorkpaperDependencyGraph' })

const props = defineProps<WpChildProps>()
const emit = defineEmits<WpChildEmits>()

const ctx = inject(WP_LIST_CONTEXT_KEY)
if (!ctx) throw new ReferenceError('WpListContext not provided — must be used inside WorkpaperList Shell')

// D3 lazy import（按需加载，减少首屏 bundle）
let d3Force: typeof import('d3-force') | null = null
onMounted(async () => {
  d3Force = await import('d3-force')
  void d3Force // 预热模块缓存，子组件内部按需使用
})

function onNavigate(code: string) {
  emit('navigate', code)
}
</script>
