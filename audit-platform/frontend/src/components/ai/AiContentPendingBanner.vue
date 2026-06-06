<!--
  AiContentPendingBanner — AI 内容待确认计数顶部 banner（spec global-refinement-v3 Task 6.4）
  ===========================================================================================
  在 5 视图（WorkpaperEditor / Adjustments / Misstatements / DisclosureEditor / ReviewWorkbench）
  顶部展示 AI 待确认数量提示。
  
  调用 GET /api/projects/{pid}/ai-content/pending（可能 404 —— catch 后 pendingCount=0 静默降级，
  端点完整实现属于 Task 6.5 范围）。
  
  用法：
    <AiContentPendingBanner :project-id="projectId" />
  
  Props:
    projectId: string  必需，传入当前项目 ID
  
  Emits:
    (e: 'view'): void  用户点击「查看明细」时触发，父视图可展开 AI 内容面板/抽屉
  
  Expose:
    refresh(): Promise<void>  父组件可调用主动刷新计数（如保存底稿后）
-->
<template>
  <div v-if="pendingCount > 0" class="gt-ai-pending-banner">
    <span class="gt-ai-pending-banner__icon">🤖</span>
    <span class="gt-ai-pending-banner__text">
      该项目尚有 <strong>{{ pendingCount }}</strong> 段 AI 生成内容待确认
    </span>
    <el-button
      class="gt-ai-pending-banner__btn"
      size="small"
      text
      @click="onView"
    >
      查看明细 →
    </el-button>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import { api } from '@/services/apiProxy'

const props = defineProps<{
  projectId: string | null | undefined
}>()

const emit = defineEmits<{
  (e: 'view'): void
}>()

const pendingCount = ref(0)

async function load() {
  if (!props.projectId) {
    pendingCount.value = 0
    return
  }
  try {
    const data: any = await api.get(`/api/projects/${props.projectId}/ai-content/pending`, { _silent: true } as any)
    // 兼容多种返回形态：{items: [...], count: N} 或 [...] 或 { pending: N }
    if (Array.isArray(data)) {
      pendingCount.value = data.length
    } else if (data && typeof data.count === 'number') {
      pendingCount.value = data.count
    } else if (data && Array.isArray(data.items)) {
      pendingCount.value = data.items.length
    } else if (data && typeof data.pending === 'number') {
      pendingCount.value = data.pending
    } else {
      pendingCount.value = 0
    }
  } catch {
    // 后端端点可能尚未实现（Task 6.5 范围），静默降级
    pendingCount.value = 0
  }
}

function onView() {
  emit('view')
}

onMounted(load)

watch(() => props.projectId, load)

defineExpose({ refresh: load })
</script>

<style scoped>
.gt-ai-pending-banner {
  display: flex;
  align-items: center;
  gap: 12px;
  width: 100%;
  padding: 8px 16px;
  margin-bottom: 8px;
  background: linear-gradient(135deg, rgba(107, 63, 160, 0.08), rgba(107, 63, 160, 0.04));
  border: 1px solid var(--gt-color-primary-light, #b794f6);
  border-left: 3px solid var(--gt-color-primary, #6b3fa0);
  border-radius: 4px;
  font-size: 13px;
  color: var(--gt-color-text-primary, #303133);
  box-sizing: border-box;
}

.gt-ai-pending-banner__icon {
  font-size: 16px;
}

.gt-ai-pending-banner__text {
  flex: 1;
}

.gt-ai-pending-banner__text strong {
  color: var(--gt-color-primary, #6b3fa0);
  font-weight: 600;
  margin: 0 2px;
}

.gt-ai-pending-banner__btn {
  --el-button-text-color: var(--gt-color-primary, #6b3fa0);
  font-weight: 500;
}
</style>
