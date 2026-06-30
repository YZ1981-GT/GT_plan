<template>
  <div class="d6-tab-related-party">
    <!-- 双模式切换 -->
    <div class="mode-toolbar">
      <el-segmented v-model="viewMode" :options="modeOptions" size="small" />
    </div>

    <template v-if="viewMode === 'structured'">
      <el-empty description="关联方检查 D6-5（14列）— 待实现" />
    </template>

    <!-- OO 在线编辑模式 -->
    <div v-else class="oo-mode-placeholder">
      <el-empty description="OnlyOffice 在线编辑模式（待OO服务就绪后启用）" />
    </div>
  </div>
</template>

<script setup lang="ts">
/**
 * D6TabRelatedParty.vue — 关联关系及交易检查 D6-5
 * 14列 + 从D6-2导入关联方
 * 完整实现见 Task 20
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
.d6-tab-related-party { padding: 16px; }
.mode-toolbar { margin-bottom: 12px; }
.oo-mode-placeholder { padding: 40px 0; }
</style>
