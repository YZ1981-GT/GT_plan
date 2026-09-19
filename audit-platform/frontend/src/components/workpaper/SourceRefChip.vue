<!--
  SourceRefChip — 错报来源底稿标签

  显示规则：
  - source_wp_code 非空时显示可点击 el-tag
  - 点击跳转到源底稿 (通过 cross_wp_references 路由)
  - source_wp_code 为空时不渲染

  Requirements: 6.1, 6.2, 6.3, 6.5, 6.6
-->
<template>
  <el-tag
    v-if="sourceWpCode"
    type="info"
    size="small"
    class="source-ref-chip"
    @click="handleClick"
  >
    <el-icon class="source-ref-chip__icon"><Link /></el-icon>
    {{ sourceWpCode }}
  </el-tag>
</template>

<script setup lang="ts">
import { Link } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { useWorkpaperNavigation } from '@/composables/useWorkpaperNavigation'

const props = defineProps<{
  sourceWpCode?: string | null
  projectId: string
}>()

const { navigateToWorkpaper } = useWorkpaperNavigation()

async function handleClick() {
  if (!props.sourceWpCode) return
  try {
    await navigateToWorkpaper(props.sourceWpCode, props.projectId)
  } catch {
    ElMessage.warning('底稿未找到')
  }
}
</script>

<style scoped>
.source-ref-chip {
  cursor: pointer;
  transition: opacity 0.2s;
}
.source-ref-chip:hover {
  opacity: 0.8;
}
.source-ref-chip__icon {
  margin-right: 2px;
  vertical-align: middle;
}
</style>
