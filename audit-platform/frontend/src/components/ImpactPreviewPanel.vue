<script setup lang="ts">
/**
 * ImpactPreviewPanel — 影响预判面板 [enterprise-linkage 3.8]
 *
 * 三栏展示：试算表行次 / 报表行次 / 底稿列表
 * 已锁定报表警告提示，未映射科目提示。
 */
import type { ImpactPreviewResult } from '@/composables/useImpactPreview'

defineProps<{
  preview: ImpactPreviewResult | null
  loading: boolean
}>()
</script>

<template>
  <div class="impact-preview-panel">
    <!-- Loading -->
    <div v-if="loading" class="impact-loading">
      <el-icon class="is-loading"><i class="el-icon-loading" /></el-icon>
      <span>计算影响范围...</span>
    </div>

    <!-- No data -->
    <div v-else-if="!preview" class="impact-empty">
      输入科目编码后自动预览影响范围
    </div>

    <!-- Unmapped account -->
    <div v-else-if="preview.unmapped_account" class="impact-unmapped">
      <el-alert type="info" :closable="false" show-icon>
        未映射科目，无法计算影响范围
      </el-alert>
    </div>

    <!-- Results -->
    <template v-else>
      <!-- Final report warning -->
      <el-alert
        v-if="preview.has_final_report_warning"
        type="warning"
        :closable="false"
        show-icon
        style="margin-bottom: 12px"
      >
        该操作将影响已定稿报表
      </el-alert>

      <div class="impact-columns">
        <!-- TB rows -->
        <div class="impact-col">
          <div class="impact-col-title">试算表行次（{{ preview.affected_tb_rows.length }}）</div>
          <div v-if="preview.affected_tb_rows.length === 0" class="impact-col-empty">无影响</div>
          <div v-for="row in preview.affected_tb_rows" :key="row.row_code" class="impact-row">
            <span class="impact-row-code">{{ row.row_code }}</span>
            <span class="impact-row-name">{{ row.row_name }}</span>
          </div>
        </div>

        <!-- Report rows -->
        <div class="impact-col">
          <div class="impact-col-title">报表行次（{{ preview.affected_report_rows.length }}）</div>
          <div v-if="preview.affected_report_rows.length === 0" class="impact-col-empty">无影响</div>
          <div v-for="row in preview.affected_report_rows" :key="`${row.report_type}-${row.row_code}`" class="impact-row">
            <el-tag size="small" type="info" effect="plain">{{ row.report_type }}</el-tag>
            <span class="impact-row-name">{{ row.row_name }}</span>
          </div>
        </div>

        <!-- Workpapers -->
        <div class="impact-col">
          <div class="impact-col-title">底稿（{{ preview.affected_workpapers.length }}）</div>
          <div v-if="preview.affected_workpapers.length === 0" class="impact-col-empty">无影响</div>
          <div v-for="wp in preview.affected_workpapers" :key="wp.wp_id" class="impact-row">
            <span class="impact-row-code">{{ wp.wp_code }}</span>
            <span class="impact-row-name">{{ wp.wp_name }}</span>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<style scoped>
.impact-preview-panel {
  padding: 8px 0;
}
.impact-loading,
.impact-empty,
.impact-unmapped {
  text-align: center;
  padding: 16px;
  font-size: var(--gt-font-size-sm);
  color: var(--gt-color-info);
}
.impact-loading {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
}
.impact-columns {
  display: grid;
  grid-template-columns: 1fr 1fr 1fr;
  gap: 12px;
}
.impact-col {
  border: 1px solid #ebeef5;
  border-radius: 6px;
  padding: 8px;
  max-height: 200px;
  overflow-y: auto;
}
.impact-col-title {
  font-size: var(--gt-font-size-xs);
  font-weight: 600;
  color: var(--gt-color-text-primary);
  margin-bottom: 6px;
  padding-bottom: 4px;
  border-bottom: 1px solid #ebeef5;
}
.impact-col-empty {
  font-size: var(--gt-font-size-xs);
  color: var(--gt-color-text-placeholder);
  text-align: center;
  padding: 8px 0;
}
.impact-row {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 3px 0;
  font-size: var(--gt-font-size-xs);
}
.impact-row-code {
  color: var(--gt-color-teal);
  font-family: 'Arial Narrow', Arial, sans-serif;
  white-space: nowrap;
}
.impact-row-name {
  color: var(--gt-color-text-regular);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
