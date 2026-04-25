<template>
  <div class="mobile-workpaper-editor">
    <div class="mobile-toolbar">
      <el-button size="small" @click="$router.back()">← 返回</el-button>
      <span class="title">{{ wpName || '底稿编辑' }}</span>
      <el-button size="small" type="primary" @click="handleDownload">下载</el-button>
    </div>
    <div class="mobile-content">
      <el-empty description="移动端底稿编辑器（开发中）">
        <template #image><span style="font-size:48px">📱</span></template>
        <el-button type="primary" @click="handleDownload">下载底稿到本地编辑</el-button>
      </el-empty>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ElMessage } from 'element-plus'

defineProps<{ wpId?: string; wpName?: string }>()

function handleDownload() {
  ElMessage.info('下载功能开发中')
}
</script>

<style scoped>
.mobile-workpaper-editor { padding: 12px; max-width: 100vw; }
.mobile-toolbar { display: flex; align-items: center; gap: 8px; padding: 8px 0; border-bottom: 1px solid #eee; }
.mobile-toolbar .title { flex: 1; font-weight: 500; text-align: center; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.mobile-content { padding: 24px 0; }
</style>
