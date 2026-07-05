<template>
  <div class="g5-skip-notice">
    <el-alert type="info" :closable="false" show-icon title="G5-10 坏账准备测算 — 暂缓实现">
      <p>本表 ECL 公式链与 G4-10 测算表同构，待 G4-10 完成后复用实现。</p>
      <p>当前请使用 OnlyOffice 模式编辑，或参考 G5-3 坏账准备明细表的 ECL 公式链。</p>
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
