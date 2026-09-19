<script setup lang="ts">
/**
 * WpSection — 底稿 Section 统一布局组件（Wp_Kit）
 *
 * 标准化渲染：标题行 + 审计目标 el-alert + 编制提示 details + 右侧操作区
 * 替代底稿中散落的重复 section 结构（tab-header + el-alert + guidance-fold）
 *
 * @example
 * <WpSection title="坏账准备明细表 D2-3" objective="核实坏账准备计提的完整性..." guidance="坏账准备按单项和组合两种方式计提...">
 *   <template #actions>
 *     <el-button size="small">🤖 AI 辅助</el-button>
 *     <GtReviewTrigger section-id="xxx" />
 *   </template>
 *   <!-- section content -->
 * </WpSection>
 *
 * Feature: platform-global-hardening
 * Requirements: 4.1
 */

defineProps<{
  /** Section 标题文本 */
  title: string
  /** 审计目标（如有则显示 el-alert type=info） */
  objective?: string
  /** 编制提示（如有则显示 details 折叠区） */
  guidance?: string
}>()
</script>

<template>
  <div class="wp-section">
    <!-- 标题行：左侧标题 + 右侧操作按钮 -->
    <div class="wp-section__header">
      <h4 class="wp-section__title">{{ title }}</h4>
      <div class="wp-section__actions">
        <slot name="actions" />
      </div>
    </div>

    <!-- 审计目标 -->
    <el-alert
      v-if="objective"
      type="info"
      :closable="false"
      show-icon
      title="审计目标"
      class="wp-section__objective"
    >
      <template #default>
        <p>{{ objective }}</p>
      </template>
    </el-alert>

    <!-- 主体内容 -->
    <div class="wp-section__body">
      <slot />
    </div>

    <!-- 编制提示 -->
    <details v-if="guidance" class="wp-section__guidance">
      <summary>📋 编制提示</summary>
      <p>{{ guidance }}</p>
    </details>
  </div>
</template>

<style scoped>
.wp-section {
  margin-bottom: 16px;
}

.wp-section__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.wp-section__title {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
  color: #303133;
}

.wp-section__actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.wp-section__objective {
  margin-bottom: 12px;
}

.wp-section__objective p {
  margin: 0;
  line-height: 1.6;
}

.wp-section__body {
  margin-bottom: 12px;
}

.wp-section__guidance {
  margin: 16px 0;
  border-left: 3px solid #409eff;
  background: #ecf5ff;
  padding: 10px 14px;
  border-radius: 0 4px 4px 0;
  font-size: var(--wp-font-size, 13px);
  color: #606266;
}

.wp-section__guidance summary {
  cursor: pointer;
  font-weight: 500;
  color: #409eff;
}

.wp-section__guidance p {
  margin: 6px 0;
  line-height: 1.6;
}
</style>
