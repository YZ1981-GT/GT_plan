<!--
  SkippedSheetPlaceholder.vue — I 类占位/跳过 sheet 渲染组件

  I 类底稿（约 243 sheet：占位 / 不归档 / 删除提示 / 重复 sheet 等）不参与渲染，
  本组件仅展示提示信息，不暴露任何编辑/保存路径。

  锚定 spec workpaper-html-renderer Task 12.2
  Validates: Requirements 3.8（I 占位跳过）
-->
<template>
  <div class="gt-skip-placeholder">
    <el-result
      icon="info"
      title="此 Sheet 不参与渲染"
    >
      <template #sub-title>
        <div class="gt-skip-placeholder__desc">
          <p>{{ defaultDescription }}</p>
          <p v-if="sheetName" class="gt-skip-placeholder__sheet">
            Sheet：<code>{{ sheetName }}</code>
          </p>
          <p v-if="reason" class="gt-skip-placeholder__reason">
            原因：{{ reason }}
          </p>
        </div>
      </template>
    </el-result>
  </div>
</template>

<script setup lang="ts">
defineProps<{
  /** 可选：sheet 名称，用于在提示中展示 */
  sheetName?: string
  /** 可选：跳过原因，用于在提示中展示（如"占位 sheet"/"不归档"等） */
  reason?: string
}>()

const defaultDescription =
  '此 sheet 为 GT_Custom 占位 / 数据 / 列表，前端不可见，但导出 xlsx 时会保留。'
</script>

<style scoped>
.gt-skip-placeholder {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 100%;
  min-height: 300px;
  padding: 24px;
  box-sizing: border-box;
  background: var(--gt-color-bg-page, #f7f6f9);
  border-radius: 8px;
}

.gt-skip-placeholder__desc {
  display: flex;
  flex-direction: column;
  gap: 6px;
  align-items: center;
  font-size: 13px;
  color: var(--gt-color-text-regular, #606266);
}

.gt-skip-placeholder__desc p {
  margin: 0;
}

.gt-skip-placeholder__sheet {
  font-size: 12px;
  color: var(--gt-color-text-tertiary, #909399);
}

.gt-skip-placeholder__sheet code {
  padding: 1px 6px;
  background: var(--gt-color-bg-page, #f5f5f5);
  border-radius: 3px;
  font-family: 'JetBrains Mono', Consolas, monospace;
}

.gt-skip-placeholder__reason {
  font-size: 12px;
  color: var(--gt-color-text-tertiary, #909399);
  font-style: italic;
}
</style>
