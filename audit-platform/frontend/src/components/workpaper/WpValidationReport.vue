<template>
  <div class="wp-validation-report">
    <div class="wp-validation-report__summary">
      <el-tag :type="overallTagType" size="large" effect="dark">
        {{ overallLabel }}
      </el-tag>
      <span class="wp-validation-report__counts">
        <el-badge :value="report.passed_count" type="success" :hidden="report.passed_count === 0">
          <span class="wp-validation-report__count-label">通过</span>
        </el-badge>
        <el-badge :value="report.warning_count" type="warning" :hidden="report.warning_count === 0">
          <span class="wp-validation-report__count-label">警告</span>
        </el-badge>
        <el-badge :value="report.error_count" type="danger" :hidden="report.error_count === 0">
          <span class="wp-validation-report__count-label">错误</span>
        </el-badge>
      </span>
    </div>

    <!-- 错误项 -->
    <div v-if="errorItems.length > 0" class="wp-validation-report__section">
      <h4 class="wp-validation-report__section-title wp-validation-report__section-title--error">
        错误 ({{ errorItems.length }})
      </h4>
      <el-table :data="errorItems" size="small" stripe border>
        <el-table-column prop="location" label="位置" width="160" />
        <el-table-column prop="message" label="描述" />
      </el-table>
    </div>

    <!-- 警告项 -->
    <div v-if="warningItems.length > 0" class="wp-validation-report__section">
      <h4 class="wp-validation-report__section-title wp-validation-report__section-title--warning">
        警告 ({{ warningItems.length }})
      </h4>
      <el-table :data="warningItems" size="small" stripe border>
        <el-table-column prop="location" label="位置" width="160" />
        <el-table-column prop="message" label="描述" />
      </el-table>
    </div>

    <!-- 通过项 -->
    <div v-if="passedItems.length > 0" class="wp-validation-report__section">
      <h4 class="wp-validation-report__section-title wp-validation-report__section-title--passed">
        通过 ({{ passedItems.length }})
      </h4>
      <el-table :data="passedItems" size="small" stripe border>
        <el-table-column prop="location" label="位置" width="160" />
        <el-table-column prop="message" label="描述" />
      </el-table>
    </div>
  </div>
</template>

<script setup lang="ts">
/**
 * WpValidationReport — 校验报告展示组件
 *
 * 三级分类 (passed/warnings/errors) 表格展示，
 * 每项显示位置 + 描述。
 *
 * Requirements: 5.6
 */
import { computed } from 'vue'
import type { ValidationReport, ValidationItem } from '@/composables/useWpExportImport'

const props = defineProps<{
  report: ValidationReport
}>()

const overallTagType = computed(() => {
  switch (props.report.overall) {
    case 'error': return 'danger'
    case 'warning': return 'warning'
    default: return 'success'
  }
})

const overallLabel = computed(() => {
  switch (props.report.overall) {
    case 'error': return '校验未通过'
    case 'warning': return '校验通过（有警告）'
    default: return '校验通过'
  }
})

const errorItems = computed(() =>
  props.report.items.filter((i: ValidationItem) => i.level === 'error'),
)

const warningItems = computed(() =>
  props.report.items.filter((i: ValidationItem) => i.level === 'warning'),
)

const passedItems = computed(() =>
  props.report.items.filter((i: ValidationItem) => i.level === 'passed'),
)
</script>

<style scoped>
.wp-validation-report__summary {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-bottom: 16px;
}

.wp-validation-report__counts {
  display: flex;
  gap: 20px;
}

.wp-validation-report__count-label {
  font-size: 13px;
  color: var(--el-text-color-secondary);
}

.wp-validation-report__section {
  margin-top: 12px;
}

.wp-validation-report__section-title {
  font-size: 14px;
  font-weight: 600;
  margin-bottom: 8px;
  padding-left: 8px;
  border-left: 3px solid;
}

.wp-validation-report__section-title--error {
  border-color: var(--el-color-danger);
  color: var(--el-color-danger);
}

.wp-validation-report__section-title--warning {
  border-color: var(--el-color-warning);
  color: var(--el-color-warning);
}

.wp-validation-report__section-title--passed {
  border-color: var(--el-color-success);
  color: var(--el-color-success);
}
</style>
