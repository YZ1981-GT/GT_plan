<template>
  <div class="gt-wp-lifecycle-wrapper" style="flex: 1; min-height: 0">
    <InnerLifecycle
      :project-id="props.projectId"
      :workpapers="lifecycleWpItems"
      :loading="ctx.loading.value"
      style="flex: 1; min-height: 0"
      @switch-view="onSwitchView"
      @open-workpaper="onOpenWorkpaper"
      @refresh="onRefresh"
    />
  </div>
</template>

<script setup lang="ts">
/**
 * WorkpaperLifecycleView — 薄包装 SFC
 * 桥接已有 components/workpaper/WorkpaperLifecycleView.vue + lifecycle computed
 * Requirements: 2.1, 3.1, 3.2, 4.7
 */
import { inject, computed } from 'vue'
import { WP_LIST_CONTEXT_KEY } from '@/composables/useWorkpaperListContext'
import type { WpChildProps, WpChildEmits } from '@/composables/useWorkpaperListContext'
import InnerLifecycle from '@/components/workpaper/WorkpaperLifecycleView.vue'
import type { WpIndexItem, WorkpaperDetail } from '@/services/workpaperApi'

defineOptions({ name: 'WorkpaperLifecycleView' })

const props = defineProps<WpChildProps>()
const emit = defineEmits<WpChildEmits>()

const ctx = inject(WP_LIST_CONTEXT_KEY)
if (!ctx) throw new ReferenceError('WpListContext not provided — must be used inside WorkpaperList Shell')

/** 给 LifecycleView 提供合并好的 wp 列表（含 wp_code/wp_name） */
const lifecycleWpItems = computed(() =>
  ctx.wpList.value.map((w: WorkpaperDetail) => {
    const idx = ctx.wpIndex.value.find((i: WpIndexItem) => i.id === w.wp_index_id)
    return {
      id: w.id,
      wp_code: w.wp_code || idx?.wp_code || '',
      wp_name: w.wp_name || idx?.wp_name || '',
      audit_cycle: w.audit_cycle || idx?.audit_cycle || '',
      status: w.status,
      review_status: w.review_status,
      assigned_to: w.assigned_to,
      reviewer: w.reviewer,
      wp_index_id: w.wp_index_id,
    }
  })
)

function onSwitchView(view: string) {
  // 通知 Shell 切换 viewMode
  ctx.viewMode.value = view
}

function onOpenWorkpaper(wpId: string) {
  emit('navigate', wpId)
}

function onRefresh() {
  emit('refresh')
}
</script>
