<template>
  <div class="gt-wp-matrix-wrapper" style="flex: 1; min-height: 0">
    <InnerMatrix
      :project-id="props.projectId"
      :workpapers="matrixWpItems"
      :members="members"
      :can-assign="canAssign"
      style="flex: 1; min-height: 0"
      @cell-click="onCellClick"
      @open-assign="onOpenAssign"
    />

    <!-- 委派确认弹窗：矩阵所有委派动作统一走此弹窗（两步确认 + enhanced 端点发通知） -->
    <BatchAssignDialog
      v-model="assignVisible"
      :project-id="props.projectId"
      :wp-ids="assignWpIds"
      :wp-list="matrixWpItems"
      @assigned="onAssigned"
    />
  </div>
</template>

<script setup lang="ts">
/**
 * WorkpaperDelegationMatrix — 薄包装 SFC
 * 桥接已有 components/workpaper/WorkpaperAssignmentMatrix.vue
 * 角色隐藏逻辑由 Shell Tab 控制（本 SFC 不做角色判断）
 * 委派动作托管 BatchAssignDialog：单元格/未分配标签点击 → 打开弹窗确认 → 走 batch-assign-enhanced（发通知）
 * Requirements: 2.3, 3.1, 3.2, 3.5, 4.3, 4.5
 */
import { inject, computed, ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { WP_LIST_CONTEXT_KEY } from '@/composables/useWorkpaperListContext'
import type { WpChildProps, WpChildEmits } from '@/composables/useWorkpaperListContext'
import { usePermissionMatrix } from '@/composables/usePermissionMatrix'
import InnerMatrix from '@/components/workpaper/WorkpaperAssignmentMatrix.vue'
import BatchAssignDialog from '@/components/assignment/BatchAssignDialog.vue'
import { listUsers } from '@/services/commonApi'
import type { WpIndexItem, WorkpaperDetail } from '@/services/workpaperApi'

defineOptions({ name: 'WorkpaperDelegationMatrix' })

const props = defineProps<WpChildProps>()
// 保留子 SFC 契约声明（本组件委派动作自持弹窗，不再走 mutate）
defineEmits<WpChildEmits>()

const ctx = inject(WP_LIST_CONTEXT_KEY)
if (!ctx) throw new ReferenceError('WpListContext not provided — must be used inside WorkpaperList Shell')

// 委派需项目经理/合伙人权限（与后端 batch-assign-enhanced 的 require_project_delegator 对齐）
const { currentRole, projectRole } = usePermissionMatrix(props.projectId)
const canAssign = computed(() =>
  ['admin', 'partner', 'manager'].includes(currentRole.value) ||
  ['manager', 'partner'].includes(projectRole.value || '')
)

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

// ─── 委派弹窗 ────────────────────────────────────────────────────────────────
const assignVisible = ref(false)
const assignWpIds = ref<string[]>([])

function onCellClick(_payload: { member_id: string; cycle: string }) {
  // 选中提示，真正分配走 onOpenAssign → 弹窗确认
}

function onOpenAssign(payload: { wp_ids: string[] }) {
  if (!payload.wp_ids?.length) {
    ElMessage.info('该单元格暂无可委派底稿')
    return
  }
  assignWpIds.value = payload.wp_ids
  assignVisible.value = true
}

async function onAssigned() {
  // 委派完成 → 刷新矩阵数据
  await ctx.fetchWpIndex()
}
</script>
