<template>
  <el-card shadow="never" class="gt-custom-coding">
    <el-result icon="info" title="自定义编码功能开发中" sub-title="该功能允许用户为特定项目或事务所自定义底稿编码体系，预计后续版本支持">
      <template #extra>
        <el-button type="primary" @click="$emit('close')">返回</el-button>
      </template>
    </el-result>
  </el-card>
</template>

<script setup lang="ts">
defineEmits<{ (e: 'close'): void }>()
</script>

<style scoped>
.gt-custom-coding { border-radius: var(--gt-radius-md); }
</style>
