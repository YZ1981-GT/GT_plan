<template>
  <div class="gt-wp-matrix-wrapper" style="flex: 1; min-height: 0">
    <InnerMatrix
      :project-id="props.projectId"
      :workpapers="matrixWpItems"
      :members="members"
      style="flex: 1; min-height: 0"
      @cell-click="onCellClick"
      @assign="onAssign"
    />
  </div>
</template>

<script setup lang="ts">
/**
 * WorkpaperDelegationMatrix — 薄包装 SFC
 * 桥接已有 components/workpaper/WorkpaperAssignmentMatrix.vue
 * 角色隐藏逻辑由 Shell Tab 控制（本 SFC 不做角色判断）
 * Requirements: 2.3, 3.1, 3.2, 3.5, 4.3, 4.5
 */
import { inject, computed, ref, onMounted } from 'vue'
import { WP_LIST_CONTEXT_KEY } from '@/composables/useWorkpaperListContext'
import type { WpChildProps, WpChildEmits, MutatePayload } from '@/composables/useWorkpaperListContext'
import InnerMatrix from '@/components/workpaper/WorkpaperAssignmentMatrix.vue'
import { listUsers } from '@/services/commonApi'
import type { WpIndexItem, WorkpaperDetail } from '@/services/workpaperApi'

defineOptions({ name: 'WorkpaperDelegationMatrix' })

const props = defineProps<WpChildProps>()
const emit = defineEmits<WpChildEmits>()

const ctx = inject(WP_LIST_CONTEXT_KEY)
if (!ctx) throw new ReferenceError('WpListContext not provided — must be used inside WorkpaperList Shell')

const members = ref<Array<{ id: string; username?: string; full_name?: string; role?: string }>>([])

onMounted(async () => {
  try {
    const users = await listUsers(props.projectId)
    members.value = users || []
  } catch { /* 静默 */ }
})

const matrixWpItems = computed(() =>
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

function onCellClick(_payload: { member_id: string; cycle: string }) {
  // 选中提示，真正分配走 onAssign
}

function onAssign(payload: { wp_ids: string[]; member_id: string }) {
  const mutatePayload: MutatePayload = {
    action: 'batchAssign',
    data: { wp_ids: payload.wp_ids, member_id: payload.member_id },
  }
  emit('mutate', mutatePayload)
}
</script>
