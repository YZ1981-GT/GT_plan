<!--
  A13DetailEnhanced — A13-2 错报明细增强层

  在 GtDForm d-form-table 基础上为 A13-2 增加：
  1. "来源底稿" 列 (Source_Ref_Chip)
  2. "上年状态" 列 (Prior_Year_Status el-tag)

  Requirements: 6.1~6.6, 4.7
-->
<template>
  <div class="a13-detail-enhanced">
    <!-- 标准 d-form-table -->
    <GtDForm
      :wp-id="wpId"
      :sheet-name="sheetName"
      form-type="d-form-table"
      :schema="schema"
      :html-data="htmlData"
      :readonly="readonly"
      @save="$emit('save', $event)"
    />

    <!-- 增强列渲染：来源底稿 + 上年状态 (覆盖在表格右侧作为补充信息) -->
    <div v-if="enhancedRows.length > 0" class="a13-detail-enhanced__extra">
      <el-table :data="enhancedRows" size="small" border stripe>
        <el-table-column label="序号" prop="seq" width="60" align="center" />
        <el-table-column label="上年状态" width="100" align="center">
          <template #default="{ row }">
            <PriorYearStatusTag :status="row.prior_year_status" />
          </template>
        </el-table-column>
        <el-table-column label="来源底稿" width="120" align="center">
          <template #default="{ row }">
            <SourceRefChip
              :source-wp-code="row.source_wp_code"
              :project-id="resolvedProjectId"
            />
          </template>
        </el-table-column>
      </el-table>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import GtDForm from './GtDForm/GtDForm.vue'
import SourceRefChip from './SourceRefChip.vue'
import PriorYearStatusTag from './PriorYearStatusTag.vue'

const props = defineProps<{
  wpId: string
  sheetName: string
  schema: Record<string, any>
  htmlData: Record<string, any>
  readonly?: boolean
}>()

defineEmits<{
  save: [data: Record<string, any>]
}>()

const route = useRoute()

const resolvedProjectId = computed(
  () => (route.params.projectId as string) || '',
)

interface EnhancedRow {
  seq: number
  prior_year_status?: string
  source_wp_code?: string
}

/** 从 htmlData 中提取行数据的增强列信息 */
const enhancedRows = computed<EnhancedRow[]>(() => {
  const data = props.htmlData
  if (!data) return []

  // d-form-table htmlData 通常是 { rows: [...] } 结构
  const rows = data.rows || data.items || []
  if (!Array.isArray(rows)) return []

  return rows.map((row: any, index: number) => ({
    seq: index + 1,
    prior_year_status: row.prior_year_status || null,
    source_wp_code: row.source_wp_code || null,
  })).filter((r: EnhancedRow) => r.prior_year_status || r.source_wp_code)
})
</script>

<style scoped>
.a13-detail-enhanced__extra {
  margin-top: 16px;
  padding: 12px;
  background: var(--el-bg-color-page);
  border-radius: 4px;
}
.a13-detail-enhanced__extra::before {
  content: '错报属性标注';
  display: block;
  font-size: 13px;
  font-weight: 500;
  color: var(--el-text-color-secondary);
  margin-bottom: 8px;
}
</style>
