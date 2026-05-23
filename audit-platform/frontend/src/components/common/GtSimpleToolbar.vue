<!--
  GtSimpleToolbar — 白色简洁工具栏 [proposal-remaining-18 G-1]
  适用于简单 CRUD 列表管理页（人员档案/知识库/附件/回收站/校验规则等）。
  左侧标题 + 右侧操作按钮，白底浅阴影，不使用紫色渐变。

  紫色渐变请使用 GtPageHeader（用于项目级编辑器/仪表盘等需要视觉层级的页面）。

  用法：
    <GtSimpleToolbar title="知识库" :show-back="true" @back="goHome">
      <template #actions>
        <el-button>新建</el-button>
        <el-button>导入</el-button>
      </template>
    </GtSimpleToolbar>
-->
<template>
  <div class="gt-simple-toolbar">
    <div class="gt-st-left">
      <el-button v-if="showBack" link size="small" class="gt-st-back" @click="$emit('back')">
        ← 返回
      </el-button>
      <h2 class="gt-st-title">{{ title }}</h2>
      <slot name="title-extra" />
    </div>
    <div class="gt-st-actions">
      <slot name="actions" />
    </div>
  </div>
</template>

<script setup lang="ts">
withDefaults(defineProps<{
  /** 页面标题 */
  title: string
  /** 显示返回按钮 */
  showBack?: boolean
}>(), {
  showBack: false,
})

defineEmits<{
  (e: 'back'): void
}>()
</script>

<style scoped>
.gt-simple-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 12px 16px;
  background: var(--gt-color-bg-white, #fff);
  border-radius: 8px;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.04);
  margin-bottom: 12px;
  flex-wrap: wrap;
}

.gt-st-left {
  display: flex;
  align-items: center;
  gap: 12px;
  min-width: 0;
}

.gt-st-title {
  margin: 0;
  font-size: var(--gt-font-size-md, 16px);
  font-weight: 700;
  color: var(--gt-color-primary, #6750a4);
  white-space: nowrap;
}

.gt-st-back {
  padding: 0;
  font-size: var(--gt-font-size-sm, 13px);
  color: var(--gt-color-text-secondary, #606266);
}
.gt-st-back:hover {
  color: var(--gt-color-primary, #6750a4);
}

.gt-st-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
</style>
