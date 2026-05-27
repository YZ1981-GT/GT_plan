<!--
  AiContentTag — 通用 🤖 AI 内容标签（spec global-refinement-v3 Task 6.4）
  =====================================================================
  字段渲染层小组件 — 紫色边框 🤖 标签 + 点击弹出 AiContentConfirmDialog。
  支持的状态颜色：
    - pending   紫色虚线（默认）
    - confirmed 绿色实线
    - revised   蓝色实线
    - rejected  红色虚线（半透明）

  用法：
    <AiContentTag
      :ai-content="aiContent"
      @updated="(logId, action) => refresh()"
    />

  Props:
    aiContent: AiContentItemForConfirm & { ai_content_log_id?: string; confirm_action?: string }
  Emits:
    (e: 'updated', logId: string, action: 'confirm' | 'revise' | 'reject')
-->
<template>
  <span class="gt-ai-tag" :class="['gt-ai-tag-' + statusKey]">
    <el-tooltip :content="tooltipText" placement="top" :show-after="200">
      <el-button
        size="small"
        plain
        circle
        class="gt-ai-tag-btn"
        :loading="submitting"
        @click="onClick"
      >🤖</el-button>
    </el-tooltip>
    <AiContentConfirmDialog
      :visible="dialogVisible"
      :ai-content-item="aiContentItem"
      @update:visible="dialogVisible = $event"
      @confirm="onDialogConfirm"
    />
  </span>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '@/services/apiProxy'
import AiContentConfirmDialog, { type AiContentItemForConfirm } from '@/components/ai/AiContentConfirmDialog.vue'

interface AiContentTagItem extends AiContentItemForConfirm {
  ai_content_log_id?: string
  confirm_action?: string | null
}

const props = defineProps<{
  aiContent: AiContentTagItem
}>()

const emit = defineEmits<{
  (e: 'updated', logId: string, action: 'confirm' | 'revise' | 'reject'): void
}>()

const dialogVisible = ref(false)
const submitting = ref(false)

const aiContentItem = computed<AiContentItemForConfirm | null>(() => {
  if (!props.aiContent) return null
  return {
    id: props.aiContent.ai_content_log_id || props.aiContent.id,
    type: props.aiContent.type,
    source_model: props.aiContent.source_model,
    confidence: props.aiContent.confidence,
    content: props.aiContent.content,
    target_cell: props.aiContent.target_cell,
    target_field: props.aiContent.target_field,
    confirmed_by: props.aiContent.confirmed_by,
    confirmed_at: props.aiContent.confirmed_at,
    confirm_action: props.aiContent.confirm_action,
    revised_content: props.aiContent.revised_content,
  }
})

const statusKey = computed(() => {
  const a = props.aiContent?.confirm_action
  if (a === 'confirmed') return 'confirmed'
  if (a === 'revised') return 'revised'
  if (a === 'rejected') return 'rejected'
  return 'pending'
})

const tooltipText = computed(() => {
  const model = props.aiContent?.source_model || '未知'
  const map: Record<string, string> = {
    pending: '待确认',
    confirmed: '已确认',
    revised: '已修订',
    rejected: '已拒绝',
  }
  const status = map[statusKey.value] || '待确认'
  return `AI 生成 · ${model} · ${status}（点击查看）`
})

async function onClick() {
  dialogVisible.value = true
}

async function onDialogConfirm(action: 'accept' | 'revise' | 'reject', revisedContent?: string) {
  const logId = props.aiContent?.ai_content_log_id || props.aiContent?.id
  if (!logId) {
    ElMessage.warning('AI 内容标识缺失，无法提交确认')
    dialogVisible.value = false
    return
  }
  submitting.value = true
  try {
    if (action === 'accept') {
      await api.post(`/api/ai-content/${logId}/confirm`)
      ElMessage.success('AI 内容已确认')
      emit('updated', logId, 'confirm')
    } else if (action === 'revise') {
      await api.post(`/api/ai-content/${logId}/revise`, { revised_content: revisedContent || '' })
      ElMessage.success('AI 内容已修订')
      emit('updated', logId, 'revise')
    } else if (action === 'reject') {
      await api.post(`/api/ai-content/${logId}/reject`)
      ElMessage.success('AI 内容已拒绝')
      emit('updated', logId, 'reject')
    }
  } catch (err: any) {
    // 后端 router 可能尚未挂载（404）— 静默 catch + 中文错误
    const msg = err?.response?.data?.detail || err?.message || '操作失败，请稍后重试'
    ElMessage.error('AI 内容确认失败：' + msg)
  } finally {
    submitting.value = false
    dialogVisible.value = false
  }
}
</script>

<style scoped>
.gt-ai-tag {
  display: inline-flex;
  align-items: center;
}
.gt-ai-tag-btn {
  width: 22px;
  height: 22px;
  min-height: 22px;
  padding: 0;
  font-size: 12px;
  line-height: 1;
}

/* pending：紫色虚线 */
.gt-ai-tag-pending .gt-ai-tag-btn {
  border: 1.5px dashed var(--gt-color-primary, #6b3fa0);
  color: var(--gt-color-primary, #6b3fa0);
  background: transparent;
}
.gt-ai-tag-pending .gt-ai-tag-btn:hover {
  background: var(--gt-color-primary-bg, rgba(107, 63, 160, 0.08));
}

/* confirmed：绿色实线 */
.gt-ai-tag-confirmed .gt-ai-tag-btn {
  border: 1.5px solid var(--el-color-success, #67c23a);
  color: var(--el-color-success, #67c23a);
  background: transparent;
}

/* revised：蓝色实线 */
.gt-ai-tag-revised .gt-ai-tag-btn {
  border: 1.5px solid var(--el-color-primary, #409eff);
  color: var(--el-color-primary, #409eff);
  background: transparent;
}

/* rejected：红色虚线 + 半透明 */
.gt-ai-tag-rejected .gt-ai-tag-btn {
  border: 1.5px dashed var(--el-color-danger, #f56c6c);
  color: var(--el-color-danger, #f56c6c);
  background: transparent;
  opacity: 0.6;
}
</style>
