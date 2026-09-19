<template>
  <div class="bulk-import-report">
    <el-alert
      :title="dryRun ? '预检报告（未写库）' : '导入报告'"
      :type="reportAlertType"
      :closable="false"
      show-icon
      style="margin-bottom: 12px;"
    />

    <!-- 汇总 -->
    <div v-if="report?.summary" class="report-summary">
      <el-tag type="success">成功: {{ report.summary.success }}</el-tag>
      <el-tag v-if="report.summary.partial" type="warning">部分: {{ report.summary.partial }}</el-tag>
      <el-tag v-if="report.summary.failed" type="danger">失败: {{ report.summary.failed }}</el-tag>
      <el-tag v-if="report.summary.blocked" type="info">受阻: {{ report.summary.blocked }}</el-tag>
      <el-tag v-if="report.summary.missing" type="info">缺失: {{ report.summary.missing }}</el-tag>
      <el-tag v-if="report.summary.unlisted" type="info">未登记: {{ report.summary.unlisted }}</el-tag>
      <el-tag v-if="report.summary.conflict_rejected" type="danger">冲突拒绝: {{ report.summary.conflict_rejected }}</el-tag>
      <el-tag v-if="report.summary.skipped" type="info">跳过: {{ report.summary.skipped }}</el-tag>
      <el-tag v-if="report.rolled_back" type="danger">已回滚</el-tag>
    </div>

    <!-- 逐 sheet 表格 -->
    <el-table
      v-if="report?.sheets?.length"
      :data="report.sheets"
      size="small"
      stripe
      style="margin-top: 12px; font-size: 13px;"
      max-height="300"
    >
      <el-table-column prop="sheet_code" label="Sheet" width="140" />
      <el-table-column prop="status" label="状态" width="120">
        <template #default="{ row }">
          <el-tag :type="statusTagType(row.status)" size="small">
            {{ statusLabel(row.status) }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="rows" label="行数" width="80">
        <template #default="{ row }">
          {{ row.rows ?? '—' }}
        </template>
      </el-table-column>
      <el-table-column label="备注/错误">
        <template #default="{ row }">
          <span v-if="row.errors?.length" class="text-danger">
            {{ row.errors.join('; ') }}
          </span>
          <span v-else-if="row.reason">{{ row.reason }}</span>
          <span v-else-if="row.warnings?.length" class="text-warning">
            {{ row.warnings.join('; ') }}
          </span>
          <span v-else>—</span>
        </template>
      </el-table-column>
    </el-table>

    <el-empty v-else description="无报告数据" />
  </div>
</template>

<script setup lang="ts">
/**
 * WpBulkImportReport — 批量导入报告组件（逐 sheet 表格）
 *
 * DryRun 预检与正式导入共用。
 *
 * Requirements: 2.5, 8.4
 *
 * NOTE: 本文件由 Task 6.1 创建基础结构，Task 6.2 完善交互细节。
 */
import { computed } from 'vue'
import type { ImportReport } from '@/composables/useBulkTabImportExport'

const props = defineProps<{
  report: ImportReport | null
  dryRun: boolean
}>()

const reportAlertType = computed(() => {
  if (!props.report) return 'info'
  if (props.dryRun) return 'info'
  const s = props.report.summary
  if ((s.failed ?? 0) > 0) return 'error'
  if ((s.partial ?? 0) > 0 || (s.blocked ?? 0) > 0) return 'warning'
  return 'success'
})

function statusTagType(status: string): string {
  switch (status) {
    case 'success': return 'success'
    case 'partial': return 'warning'
    case 'failed': return 'danger'
    case 'conflict_rejected': return 'danger'
    case 'blocked_by_status': return 'info'
    case 'missing': return 'info'
    case 'unlisted': return 'info'
    case 'skipped': return 'info'
    default: return ''
  }
}

function statusLabel(status: string): string {
  switch (status) {
    case 'success': return '成功'
    case 'partial': return '部分成功'
    case 'failed': return '失败'
    case 'conflict_rejected': return '冲突拒绝'
    case 'blocked_by_status': return '状态受阻'
    case 'missing': return '文件缺失'
    case 'unlisted': return '未登记'
    case 'skipped': return '跳过'
    default: return status
  }
}
</script>

<style scoped>
.report-summary {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.text-warning {
  color: var(--el-color-warning);
  font-size: 12px;
}

.text-danger {
  color: var(--el-color-danger);
  font-size: 12px;
}
</style>
