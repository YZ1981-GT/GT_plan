<template>
  <div class="shell-home">
    <p class="shell-home__title">{{ title ? `${title}：` : '' }}该环节界面待开发</p>
    <p class="shell-home__hint">平台暂无对应功能，开发完成后在此开放。</p>
  </div>
</template>

<script setup lang="ts">
/**
 * 未开发环节的占位（移植自 CITAR main.tsx 的 NodeScreen 兜底分支）。
 * 空白分不清是没做还是出错了，所以明确写「待开发」。环节名取路由 meta.citarTitle。
 */
import { computed } from 'vue'
import { useRoute } from 'vue-router'

defineOptions({ name: 'CitarPendingNode' })

const route = useRoute()
const title = computed(() => String(route.meta.citarTitle || ''))
</script>

<style scoped src="./styles/shell-home.css"></style>
