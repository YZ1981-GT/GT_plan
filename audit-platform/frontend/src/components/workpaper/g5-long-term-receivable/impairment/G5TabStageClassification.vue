<template>
  <div class="g5-skip-notice">
    <el-alert type="info" :closable="false" show-icon title="G5-9 三阶段划分 — 暂缓实现">
      <p>本表依赖 G4-9 三阶段划分交互方案，待 G4-9 完成后复用同一渲染模式。</p>
      <p>当前请使用 OnlyOffice 模式编辑，或先在 G5-3 坏账准备明细中录入阶段信息。</p>
    </el-alert>
  </div>
</template>

<script setup lang="ts">
defineProps<{ htmlData?: any; wpId: string; projectId: string; readonly?: boolean }>()
</script>

<style scoped>
.g5-skip-notice { padding: 16px; font-size: 13px; }
.g5-skip-notice p { margin: 4px 0; }
</style>
