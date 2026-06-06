<template>
  <div v-for="(list, docType) in grouped" :key="docType" class="deliverable-group">
    <h3 class="deliverable-group__title">{{ label(docType) }}</h3>
    <el-table :data="list" stripe size="small">
      <el-table-column prop="file_name" label="文件名" min-width="200">
        <template #default="{ row }">{{ row.file_name || label(row.doc_type) }}</template>
      </el-table-column>
      <el-table-column prop="version_no" label="版本" width="70" />
      <el-table-column prop="status" label="状态" width="100" />
      <el-table-column prop="exporter_name" label="导出者" width="120" />
      <el-table-column prop="exported_at" label="导出时间" width="170" />
      <el-table-column prop="file_size" label="大小" width="100">
        <template #default="{ row }">{{ formatSize(row.file_size) }}</template>
      </el-table-column>
      <el-table-column label="操作" width="280" fixed="right">
        <template #default="{ row }">
          <el-button link type="primary" @click="emit('select', row)">选中</el-button>
          <el-button link type="primary" @click="emit('toggle-versions', row.task_id)">版本链</el-button>
          <el-button link type="primary" @click="emit('preview', row)">预览</el-button>
          <el-button
            v-if="!['confirmed', 'signed', 'archived'].includes(row.status)"
            link
            type="primary"
            @click="emit('edit', row)"
          >
            编辑
          </el-button>
          <el-button link type="primary" @click="emit('download', row)">下载</el-button>
        </template>
      </el-table-column>
    </el-table>
  </div>
  <el-empty v-if="!Object.keys(grouped).length" description="暂无交付物，请使用上方生成入口创建" />
</template>

<script setup lang="ts">
import type { DeliverableItem } from '@/services/deliverableApi'

defineProps<{
  grouped: Record<string, DeliverableItem[]>
  expandedTaskId: string | null
}>()

const emit = defineEmits<{
  'toggle-versions': [taskId: string]
  preview: [item: DeliverableItem]
  download: [item: DeliverableItem]
  edit: [item: DeliverableItem]
  select: [item: DeliverableItem]
}>()

const LABELS: Record<string, string> = {
  audit_report: '审计报告正文',
  financial_report: '财务报表',
  disclosure_notes: '附注',
  full_package: '全套包',
}

function label(docType: string) {
  return LABELS[docType] || docType
}

function formatSize(size: number | null) {
  if (!size) return '-'
  if (size < 1024) return `${size} B`
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`
  return `${(size / 1024 / 1024).toFixed(1)} MB`
}
</script>

<style scoped>
.deliverable-group {
  margin-bottom: 20px;
}
.deliverable-group__title {
  margin: 0 0 8px;
  font-size: 15px;
}
</style>
