<!--
  ImportPreviewDialog.vue — 坏账准备明细表 Excel 导入预览弹窗

  展示 import-parse 返回的匹配结果，用户确认后触发 commit。
  - el-table 展示行号/项目名/匹配状态
  - 状态标记：matched 绿色 / unmatched 红色
  - 底部统计 + 确认/取消按钮
  Requirements: 3.4, 3.5, 3.7
-->

<template>
  <el-dialog
    :model-value="visible"
    title="导入预览"
    width="680px"
    :close-on-click-modal="false"
    @update:model-value="$emit('update:visible', $event)"
  >
    <div v-if="parseResult" class="import-preview">
      <el-table :data="parseResult.rows" max-height="400" border size="small">
        <el-table-column label="行号" prop="excel_row_index" width="70" align="center" />
        <el-table-column label="项目名" prop="excel_label" min-width="180" />
        <el-table-column label="状态" width="100" align="center">
          <template #default="{ row }">
            <span
              class="import-status-badge"
              :class="row.status === 'matched' ? 'badge-matched' : 'badge-unmatched'"
            >
              {{ row.status === 'matched' ? '已匹配' : '未匹配' }}
            </span>
          </template>
        </el-table-column>
      </el-table>

      <div class="import-stats">
        <span class="stat-matched">{{ parseResult.matched_count }} 行匹配</span>
        <span class="stat-sep">/</span>
        <span class="stat-unmatched">{{ parseResult.unmatched_count }} 行未匹配</span>
      </div>
    </div>

    <template #footer>
      <el-button @click="$emit('cancel')">取消</el-button>
      <el-button type="primary" @click="$emit('confirm')">确认导入</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
interface ImportRow {
  excel_row_index: number
  excel_label: string
  status: string
  amounts: Record<string, string | null>
}

interface ImportParseResult {
  rows: ImportRow[]
  matched_count: number
  unmatched_count: number
}

defineProps<{
  visible: boolean
  parseResult: ImportParseResult | null
}>()

defineEmits<{
  (e: 'confirm'): void
  (e: 'cancel'): void
  (e: 'update:visible', val: boolean): void
}>()
</script>

<style scoped>
.import-preview {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.import-status-badge {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 12px;
  font-weight: 500;
}
.badge-matched {
  background: #e8f5e9;
  color: #2e7d32;
}
.badge-unmatched {
  background: #ffebee;
  color: #c62828;
}
.import-stats {
  text-align: center;
  font-size: var(--wp-font-size, 13px);
  padding: 8px 0;
}
.stat-matched {
  color: #2e7d32;
  font-weight: 500;
}
.stat-unmatched {
  color: #c62828;
  font-weight: 500;
}
.stat-sep {
  margin: 0 8px;
  color: #999;
}
</style>
