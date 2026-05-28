<template>
  <div class="gt-wp-board-wrapper" style="flex: 1; min-height: 0">
    <InnerKanban
      ref="kanbanRef"
      :project-id="props.projectId"
      :audit-cycle="ctx.filterCycle.value"
      style="flex: 1; min-height: 0"
      @select="onKanbanSelect"
      @assign="onKanbanAssign"
    />
  </div>
</template>

<script setup lang="ts">
/**
 * WorkpaperBoardView — 薄包装 SFC
 * 桥接已有 components/workpaper/WorkpaperKanban.vue + 拖拽逻辑
 * Requirements: 2.2, 3.1, 3.2, 3.5
 */
import { inject, ref } from 'vue'
import { useRouter } from 'vue-router'
import { WP_LIST_CONTEXT_KEY } from '@/composables/useWorkpaperListContext'
import type { WpChildProps, WpChildEmits, MutatePayload } from '@/composables/useWorkpaperListContext'
import InnerKanban from '@/components/workpaper/WorkpaperKanban.vue'

defineOptions({ name: 'WorkpaperBoardView' })

const props = defineProps<WpChildProps>()
const emit = defineEmits<WpChildEmits>()

const ctx = inject(WP_LIST_CONTEXT_KEY)
if (!ctx) throw new ReferenceError('WpListContext not provided — must be used inside WorkpaperList Shell')

const router = useRouter()
const kanbanRef = ref<InstanceType<typeof InnerKanban> | null>(null)

/** 看板卡片点击 → 导航到底稿编辑器 */
function onKanbanSelect(item: any) {
  if (item.wp_id) {
    emit('navigate', item.wp_id)
  } else if (item.id) {
    emit('navigate', item.id)
  }
}

/** 看板卡片委派 → 通过 mutate 事件通知 Shell */
function onKanbanAssign(item: any) {
  const mutatePayload: MutatePayload = {
    action: 'assign',
    data: {
      wp_id: item.wp_id || item.id,
      wp_code: item.wp_code,
      wp_name: item.wp_name,
    },
  }
  emit('mutate', mutatePayload)
}
</script>
