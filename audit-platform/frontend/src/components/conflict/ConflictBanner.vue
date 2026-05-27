<!--
  ConflictBanner — 跨模块冲突待调解计数顶部 banner（spec global-refinement-v3 Task 7.5）
  =============================================================================
  在 5 视图（Adjustments / Misstatements / ReportView / DisclosureEditor / WorkpaperEditor）
  顶部展示「未调解冲突」计数提示，点击触发 ConflictResolutionPanel。

  调用 GET /api/projects/{pid}/conflicts/pending（404/0 时静默不渲染）。

  用法：
    <ConflictBanner :project-id="projectId" @view="onView" />

  Props:
    projectId: string  必需，传入当前项目 ID

  Emits:
    (e: 'view'): void  用户点击「查看详情」时触发，父视图可打开 ConflictResolutionPanel

  Expose:
    refresh(): Promise<void>  父组件可主动刷新计数
-->
<template>
  <el-alert
    v-if="pendingCount > 0"
    type="warning"
    show-icon
    :closable="false"
    class="gt-conflict-banner"
  >
    <template #title>
      <div class="gt-conflict-banner__row">
        <span class="gt-conflict-banner__text">
          该项目存在 <strong>{{ pendingCount }}</strong> 段未调解的跨模块冲突
        </span>
        <el-button
          class="gt-conflict-banner__btn"
          size="small"
          type="primary"
          text
          @click="onView"
        >
          查看详情 →
        </el-button>
      </div>
    </template>
  </el-alert>
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
    const data: any = await api.get(
      `/api/projects/${props.projectId}/conflicts/pending`,
    )
    if (Array.isArray(data)) {
      pendingCount.value = data.length
    } else if (data && typeof data.count === 'number') {
      pendingCount.value = data.count
    } else if (data && Array.isArray(data.items)) {
      pendingCount.value = data.items.length
    } else {
      pendingCount.value = 0
    }
  } catch {
    // 端点 404 或网络错误 → 静默降级
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
.gt-conflict-banner {
  margin-bottom: 8px;
}

.gt-conflict-banner__row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  gap: 12px;
}

.gt-conflict-banner__text {
  flex: 1;
  font-size: 13px;
  color: var(--el-color-warning-dark-2, #b88230);
}

.gt-conflict-banner__text strong {
  font-weight: 600;
  margin: 0 2px;
}

.gt-conflict-banner__btn {
  font-weight: 500;
}
</style>
