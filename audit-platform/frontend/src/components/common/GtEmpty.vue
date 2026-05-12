<!--
  GtEmpty — 统一空态组件 [R7-S1-09]
  所有空态必须经此组件，文案不再自由发挥。

  用法：
    <GtEmpty title="暂无底稿" description="请先导入账套数据" action-text="去导入" @action="goImport" icon="📋" />
-->
<template>
  <div class="gt-empty">
    <el-empty :image-size="80">
      <template #image v-if="icon">
        <span class="gt-empty__icon">{{ icon }}</span>
      </template>
      <template #description>
        <h4 class="gt-empty__title">{{ title }}</h4>
        <p v-if="description" class="gt-empty__desc">{{ description }}</p>
      </template>
      <el-button v-if="actionText" type="primary" @click="$emit('action')">
        {{ actionText }}
      </el-button>
    </el-empty>
  </div>
</template>

<script setup lang="ts">
defineProps<{
  /** 主标题（必填） */
  title: string
  /** 描述文字（可选） */
  description?: string
  /** 操作按钮文字（可选，不传则不显示按钮） */
  actionText?: string
  /** emoji 图标（可选，替代默认空态图） */
  icon?: string
}>()

defineEmits<{ (e: 'action'): void }>()
</script>

<style scoped>
.gt-empty {
  display: flex;
  justify-content: center;
  align-items: center;
  min-height: 200px;
  padding: var(--gt-space-8) var(--gt-space-4);
}
.gt-empty__icon {
  font-size: 48px;
  line-height: 1;
}
.gt-empty__title {
  margin: 0 0 var(--gt-space-2);
  font-size: var(--gt-font-size-md);
  font-weight: 600;
  color: var(--gt-color-text);
}
.gt-empty__desc {
  margin: 0;
  font-size: var(--gt-font-size-sm);
  color: var(--gt-color-text-secondary);
}
</style>
