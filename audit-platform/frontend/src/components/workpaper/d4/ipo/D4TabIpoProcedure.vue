<script setup lang="ts">
/**
 * D4TabIpoProcedure — D4-22A IPO程序表
 *
 * Placeholder for a-program-console reuse
 * Requirements: 14.1
 */
defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()
</script>

<template>
  <div class="d4-tab-ipo-procedure">
    <el-alert type="info" :closable="false" show-icon>
      <template #title>IPO/舞弊增强程序表</template>
      <p>此表复用 a-program-console 组件渲染，包含IPO/舞弊相关审计程序清单。</p>
    </el-alert>
    <div class="placeholder-area">
      <el-empty description="程序表加载区域（复用 a-program-console）">
        <template #image><span class="text-3xl">📋</span></template>
      </el-empty>
    </div>
  </div>
</template>

<style scoped>
.d4-tab-ipo-procedure { padding: 16px; }
.placeholder-area { margin-top: 16px; min-height: 200px; }
</style>
