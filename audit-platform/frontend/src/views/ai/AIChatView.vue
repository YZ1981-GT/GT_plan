<template>
  <div class="gt-ai-chat-window">
    <!--
      独立聊天窗口的宿主上下文（dsh-agent-panel-integration Req 3.4/3.5）：
      与其他五个宿主用同一个 adapter 构造 HostContext 请求。
      路由里没有项目时使用显式受限全局知识模式。
    -->
    <PlatformAiChatPanel :host="aiHost" :visible="true" />
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import PlatformAiChatPanel from '@/components/ai/PlatformAiChatPanel.vue'
import { buildAmbientHost } from '@/composables/useAiHostContext'

const route = useRoute()

const aiHost = computed(() =>
  buildAmbientHost({
    projectId: route.params.projectId ?? route.query.project_id,
    wpId: route.params.wpId ?? route.query.wp_id,
  }),
)
</script>

<style scoped>
.gt-ai-chat-window {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
}

.gt-ai-chat-window__scope {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 12px;
  font-size: 12px;
  color: var(--el-text-color-secondary, #909399);
  background: var(--el-fill-color-lighter, #f5f7fa);
  border-bottom: 1px solid var(--el-border-color-lighter, #e4e7ed);
  flex-shrink: 0;
}

.gt-ai-chat-window__scope.is-global {
  color: var(--el-color-warning, #e6a23c);
  background: var(--el-color-warning-light-9, #fdf6ec);
}

.gt-ai-chat-window__hint {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
