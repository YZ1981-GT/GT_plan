<template>
  <div class="gt-ai-conc-btn">
    <el-button
      size="small"
      type="primary"
      plain
      :loading="loading"
      @click="onClick"
    >✨ AI 审计说明</el-button>
    <AiContentConfirmDialog
      v-if="aiResult"
      :visible="dialogVisible"
      :ai-content-item="aiContentItem"
      @update:visible="dialogVisible = $event"
      @confirm="onConfirm"
    />
  </div>
</template>

<script setup lang="ts">
/**
 * AiConclusionButton — 通用 ✨ AI 审计说明按钮（Sprint 2 Task 2.30）
 *
 * 调用 wp_ai_service 4 个生成方法：
 *   - audit_conclusion / variance_analysis / check_conclusion / cutoff_conclusion
 * 输出经 AiContentConfirmDialog 确认后通过 emit('apply', text) 让父组件填入结论。
 */
import { ref, computed } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '@/services/apiProxy'
import AiContentConfirmDialog, { type AiContentItemForConfirm } from '@/components/ai/AiContentConfirmDialog.vue'

interface Props {
  wpId: string
  scenario: 'audit_conclusion' | 'variance_analysis' | 'check_conclusion' | 'cutoff_conclusion'
  sheetKey?: string
  context?: Record<string, any>
}

const props = defineProps<Props>()
const emit = defineEmits<{
  apply: [text: string]
  reject: []
}>()

const loading = ref(false)
const aiResult = ref<any>(null)
const dialogVisible = ref(false)

// 适配 AiContentConfirmDialog 的 aiContentItem 形态
const aiContentItem = computed<AiContentItemForConfirm | null>(() => {
  if (!aiResult.value) return null
  return {
    id: aiResult.value.id || `${props.wpId}-${props.scenario}`,
    type: props.scenario,
    source_model: aiResult.value.model || '',
    confidence: aiResult.value.confidence ?? null,
    content: aiResult.value.text || aiResult.value.summary || '',
    target_cell: null,
    target_field: props.sheetKey || null,
  }
})

async function onClick() {
  loading.value = true
  try {
    const data = await api.post(
      `/api/workpapers/${props.wpId}/ai/${props.scenario.replace(/_/g, '-')}`,
      { sheet_key: props.sheetKey, context: props.context || {} },
    )
    aiResult.value = data
    dialogVisible.value = true
  } catch (err: any) {
    ElMessage.error('AI 生成失败：' + (err?.message || '请稍后重试'))
  } finally {
    loading.value = false
  }
}

function onConfirm(action: 'accept' | 'revise' | 'reject', revisedContent?: string) {
  if (action === 'reject') {
    emit('reject')
  } else {
    const text = revisedContent || aiResult.value?.text || aiResult.value?.summary || ''
    emit('apply', text)
  }
  dialogVisible.value = false
  aiResult.value = null
}
</script>

<style scoped>
.gt-ai-conc-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}
</style>
