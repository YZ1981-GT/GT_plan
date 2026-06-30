<template>
  <div class="d6-tab-disclosure">
    <!-- 双模式切换 -->
    <div class="mode-toolbar">
      <el-segmented v-model="viewMode" :options="modeOptions" size="small" />
    </div>

    <template v-if="viewMode === 'structured'">
      <el-empty :description="`附注披露（${variant === 'listed' ? '上市公司' : '国企'}）— 待实现`" />
    </template>

    <!-- OO 在线编辑模式 -->
    <div v-else class="oo-mode-placeholder">
      <el-empty description="OnlyOffice 在线编辑模式（待OO服务就绪后启用）" />
    </div>
  </div>
</template>

<script setup lang="ts">
/**
 * D6TabDisclosure.vue — 附注披露信息
 * 上市公司版：5子节163公式
 * 国企版：3子节简化版
 * 完整实现见 Task 25
 */
import { ref } from 'vue'

defineProps<{
  wpId: string
  projectId: string
  isReadonly: boolean
  allResponses: Map<string, any>
  debouncedSave: (itemId: string, data: any) => void
  crossSheet: any
  variant: 'listed' | 'soe'
}>()

const viewMode = ref('structured')
const modeOptions = [
  { label: '结构化视图', value: 'structured' },
  { label: '在线编辑', value: 'onlyoffice' },
]
</script>

<style scoped>
.d6-tab-disclosure { padding: 16px; }
.mode-toolbar { margin-bottom: 12px; }
.oo-mode-placeholder { padding: 40px 0; }
</style>
