<template>
  <aside id="dsh-panel-region" class="dsh-panel-load-error" role="alert">
    <div class="dsh-panel-load-error__content">
      <strong>AI 助手加载失败</strong>
      <p>项目页面仍可继续使用，请关闭后稍后重试。</p>
      <button type="button" class="dsh-panel-load-error__close" @click="emit('update:modelValue', false)">
        关闭
      </button>
    </div>
  </aside>
</template>

<script setup lang="ts">
defineProps<{ modelValue?: boolean; error?: Error }>()
const emit = defineEmits<{ 'update:modelValue': [value: boolean] }>()
</script>

<style scoped>
.dsh-panel-load-error {
  display: flex;
  flex: 0 0 360px;
  align-items: center;
  justify-content: center;
  min-width: 320px;
  max-width: 420px;
  padding: 24px;
  border-left: 1px solid var(--el-border-color-light, #e4e7ed);
  background: var(--el-bg-color, #fff);
  color: var(--el-text-color-primary, #303133);
}

.dsh-panel-load-error__content {
  text-align: center;
}

.dsh-panel-load-error p {
  margin: 8px 0 16px;
  color: var(--el-text-color-secondary, #909399);
  font-size: 13px;
  line-height: 1.5;
}

.dsh-panel-load-error__close {
  padding: 7px 16px;
  border: 1px solid var(--el-border-color, #dcdfe6);
  border-radius: 4px;
  background: var(--el-fill-color-blank, #fff);
  color: var(--el-text-color-regular, #606266);
  cursor: pointer;
}
</style>
