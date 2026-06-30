<template>
  <div class="d6-tab-writeoff-check">
    <!-- 双模式切换 -->
    <div class="mode-toolbar">
      <el-segmented v-model="viewMode" :options="modeOptions" size="small" />
    </div>

    <template v-if="viewMode === 'structured'">
      <el-empty description="转回核销检查 D6-9（双段）— 待实现" />
    </template>

    <!-- OO 在线编辑模式 -->
    <div v-else class="oo-mode-placeholder">
      <el-empty description="OnlyOffice 在线编辑模式（待OO服务就绪后启用）" />
    </div>
  </div>
</template>

<script setup lang="ts">
/**
 * D6TabWriteoffCheck.vue — 减值准备转回核销检查 D6-9
 * 双段结构：转回检查 + 核销检查
 * 完整实现见 Task 24
 */
import { ref } from 'vue'

defineProps<{
  wpId: string
  projectId: string
  isReadonly: boolean
  allResponses: Map<string, any>
  saveImmediate: (itemId: string, data: any) => Promise<void>
  debouncedSave: (itemId: string, data: any) => void
}>()

const viewMode = ref('structured')
const modeOptions = [
  { label: '结构化视图', value: 'structured' },
  { label: '在线编辑', value: 'onlyoffice' },
]
</script>

<style scoped>
.d6-tab-writeoff-check { padding: 16px; }
.mode-toolbar { margin-bottom: 12px; }
.oo-mode-placeholder { padding: 40px 0; }
</style>
