<template>
  <div class="gt-ai-chat-window">
    <!--
      独立聊天窗口的宿主上下文（dsh-agent-panel-integration Req 3.4/3.5）：
      与其他五个宿主用同一个 adapter 构造 HostContext 请求。
      路由里没有项目时使用显式受限全局知识模式。

      范围说明条不在这里渲染 —— PlatformAiChatPanel 自带
      `.platform-ai-chat-panel__scope`，用的是同一个 hostScopeHint()。
      本视图再加一条就是同一句话显示两遍。
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
/*
 * 🔴 用视口高度而不是 height:100%。
 * 本视图是**顶层路由**（不在 DefaultLayout 内），而 global.css 没给 html/body/#app 设高度，
 * height:100% 会解析成 auto ⇒ 内层 flex 撑不开 ⇒ 消息区的 overflow-y:auto 失效 ⇒
 * 整页滚动、输入区被消息顶到文档底部（用户每发一条都要往下滚才能再输入）。
 * overflow:hidden 把滚动限制在消息区内部，输入区因此常驻可见。
 */
.gt-ai-chat-window {
  display: flex;
  flex-direction: column;
  height: 100vh;
  height: 100dvh; /* 支持动态视口的浏览器覆盖上一行 */
  min-height: 0;
  overflow: hidden;
}

/* 面板本体吃满整个视口高度 */
.gt-ai-chat-window > * {
  flex: 1;
  min-height: 0;
}
</style>
