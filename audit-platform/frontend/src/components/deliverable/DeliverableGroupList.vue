<template>
  <div v-for="(list, docType) in grouped" :key="docType" class="deliverable-group">
    <div class="deliverable-group__title">
      <el-icon class="deliverable-group__icon"><Folder /></el-icon>
      <span>{{ label(docType) }}</span>
      <span class="deliverable-group__count">{{ list.length }}</span>
    </div>
    <el-card class="deliverable-group__card" shadow="never" :body-style="{ padding: '0' }">
      <el-table
        :data="list"
        size="small"
        highlight-current-row
        row-key="task_id"
        :current-row-key="selectedTaskId || undefined"
        @row-click="(row) => emit('select', row)"
      >
        <el-table-column prop="file_name" label="文件名" min-width="240">
          <template #default="{ row }">
            <div class="deliverable-file">
              <el-icon class="deliverable-file__icon" :style="{ color: fileColor(row) }">
                <Document />
              </el-icon>
              <span class="deliverable-file__name">{{ row.file_name || label(row.doc_type) }}</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="version_no" label="版本" width="70" align="center">
          <template #default="{ row }">
            <span class="deliverable-ver">v{{ row.version_no }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="status" label="状态" width="150" align="center">
          <template #default="{ row }">
            <el-tag :type="statusTag(row.status)" size="small" effect="light" round>
              {{ statusLabel(row.status) }}
            </el-tag>
            <!--
              需求 10.3：报表数字与按试算表重算不一致时列表行即可见。
              🔴 判定用后端下发的 `drift_blocked`（should_block_confirm 唯一入口），
              不在前端写 `if (row.drift_report)` —— `{"diffs": []}` 是非空对象但
              表示已比对且一致，那样写会让配了映射的报表常亮一条空告警。
            -->
            <el-tooltip
              v-if="row.drift_blocked"
              :content="row.drift_reason || '报表数字与按试算表重算的结果不一致，本版本不可确认'"
              placement="top"
              :show-after="200"
            >
              <el-tag size="small" type="danger" effect="light" round class="deliverable-drift-tag">
                数字待核
              </el-tag>
            </el-tooltip>
          </template>
        </el-table-column>
        <el-table-column prop="exporter_name" label="导出者" width="110">
          <template #default="{ row }">{{ row.exporter_name || '-' }}</template>
        </el-table-column>
        <el-table-column prop="exported_at" label="导出时间" width="160">
          <template #default="{ row }">
            <span class="deliverable-time">{{ formatTime(row.exported_at) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="file_size" label="大小" width="90" align="right">
          <template #default="{ row }">
            <span class="deliverable-time">{{ formatSize(row.file_size) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="230" fixed="right">
          <template #default="{ row }">
            <div class="deliverable-actions" @click.stop>
              <el-button link type="primary" @click="emit('preview', row)">预览</el-button>
              <el-button
                v-if="!locked(row.status)"
                link
                type="primary"
                @click="emit('edit', row)"
              >
                编辑
              </el-button>
              <el-button link type="primary" @click="emit('download', row)">下载</el-button>
              <el-dropdown
                trigger="click"
                popper-class="deliverable-more-dropdown"
                @command="(cmd: string) => onCommand(cmd, row)"
              >
                <el-button link type="primary" class="deliverable-actions__more">
                  更多<el-icon class="el-icon--right"><ArrowDown /></el-icon>
                </el-button>
                <template #dropdown>
                  <el-dropdown-menu>
                    <el-dropdown-item command="versions">
                      <el-icon><Connection /></el-icon>版本链
                    </el-dropdown-item>
                    <!-- 需求 11.5：每行提供溯源入口（不必先打开在线编辑器） -->
                    <el-dropdown-item command="trace">
                      <el-icon><Share /></el-icon>数据溯源
                    </el-dropdown-item>
                    <el-dropdown-item v-if="docType === 'audit_report'" command="guidance">
                      <el-icon><Reading /></el-icon>下载编制参考版
                    </el-dropdown-item>
                    <el-dropdown-item v-if="!locked(row.status)" command="delete" divided>
                      <span class="deliverable-actions__danger">
                        <el-icon><Delete /></el-icon>删除
                      </span>
                    </el-dropdown-item>
                  </el-dropdown-menu>
                </template>
              </el-dropdown>
            </div>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
  <el-empty v-if="!Object.keys(grouped).length" description="暂无交付物，请使用上方生成入口创建" />
</template>

<script setup lang="ts">
import {
  ArrowDown,
  Connection,
  Delete,
  Document,
  Folder,
  Reading,
  Share,
} from '@element-plus/icons-vue'
import type { DeliverableItem } from '@/services/deliverableApi'
import { useDisplayPrefsStore } from '@/stores/displayPrefs'

const displayPrefs = useDisplayPrefsStore()

/**
 * 格式化导出时间。后端时间戳为 naive UTC（func.now()/utcnow），
 * 补 'Z' 标记后由统一格式化器转本地时区显示。
 */
function formatTime(v: string | null | undefined): string {
  if (!v) return '-'
  const hasTz = /[zZ]|[+-]\d{2}:?\d{2}$/.test(v)
  return displayPrefs.fmtDateTime(hasTz ? v : `${v}Z`)
}

defineProps<{
  grouped: Record<string, DeliverableItem[]>
  expandedTaskId: string | null
  selectedTaskId?: string | null
}>()

const emit = defineEmits<{
  'toggle-versions': [taskId: string]
  preview: [item: DeliverableItem]
  download: [item: DeliverableItem]
  'download-guidance': [item: DeliverableItem]
  edit: [item: DeliverableItem]
  select: [item: DeliverableItem]
  delete: [item: DeliverableItem]
  trace: [item: DeliverableItem]
}>()

function onCommand(cmd: string, row: DeliverableItem) {
  if (cmd === 'versions') emit('toggle-versions', row.task_id)
  else if (cmd === 'guidance') emit('download-guidance', row)
  else if (cmd === 'trace') emit('trace', row)
  else if (cmd === 'delete') emit('delete', row)
}

const LABELS: Record<string, string> = {
  audit_report: '审计报告正文',
  financial_report: '财务报表',
  disclosure_notes: '附注',
  full_package: '全套包',
}

function label(docType: string) {
  return LABELS[docType] || docType
}

// 交付物状态 → 中文标签 + 标签色（全中文化）
const STATUS_MAP: Record<string, { label: string; tag: 'success' | 'warning' | 'info' | 'primary' | 'danger' | '' }> = {
  draft: { label: '草稿', tag: 'info' },
  generated: { label: '已生成', tag: 'primary' },
  editing: { label: '编辑中', tag: 'warning' },
  pending_approval: { label: '待审批', tag: 'warning' },
  confirmed: { label: '已确认', tag: 'success' },
  signed: { label: '已签章', tag: 'success' },
  archived: { label: '已归档', tag: 'info' },
}

function statusLabel(status: string) {
  return STATUS_MAP[status]?.label || status
}

function statusTag(status: string) {
  return STATUS_MAP[status]?.tag ?? ''
}

function locked(status: string) {
  return ['confirmed', 'signed', 'archived'].includes(status)
}

// 文件图标配色：报表类（xlsx）绿，文档类（docx）蓝
function fileColor(row: DeliverableItem) {
  const dt = row.doc_type || ''
  const suffix = row.file_name?.split('.').pop()?.toLowerCase()
  if (suffix === 'xlsx' || suffix === 'xls' || dt.startsWith('financial_report')) {
    return 'var(--el-color-success)'
  }
  return 'var(--el-color-primary)'
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
  margin-bottom: 22px;
}
.deliverable-group__title {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0 0 10px;
  font-size: 14px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}
.deliverable-group__icon {
  color: var(--el-color-primary);
  font-size: 16px;
}
.deliverable-group__count {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 20px;
  height: 18px;
  padding: 0 6px;
  font-size: 12px;
  font-weight: 500;
  color: var(--el-color-primary);
  background: var(--el-color-primary-light-9);
  border-radius: 9px;
}
.deliverable-group__card {
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  overflow: hidden;
}
.deliverable-group__card :deep(.el-table) {
  font-size: 13px;
}
.deliverable-group__card :deep(.el-table th.el-table__cell) {
  background: var(--el-fill-color-lighter);
  color: var(--el-text-color-regular);
  font-weight: 600;
}
.deliverable-group__card :deep(.el-table__row) {
  cursor: pointer;
}
.deliverable-file {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}
.deliverable-file__icon {
  flex-shrink: 0;
  font-size: 16px;
}
.deliverable-file__name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.deliverable-ver {
  font-variant-numeric: tabular-nums;
  color: var(--el-text-color-regular);
}
.deliverable-time {
  color: var(--el-text-color-secondary);
  font-size: 12px;
}
.deliverable-actions {
  display: flex;
  align-items: center;
  gap: 2px;
}
.deliverable-actions__more {
  padding-left: 4px;
}
.deliverable-drift-tag {
  margin-left: 4px;
  cursor: help;
}
.deliverable-actions__danger {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  color: var(--el-color-danger);
}
</style>

<!-- 非 scoped：el-dropdown 菜单 teleport 到 body，scoped 无法命中，用 popper-class 定向 -->
<style>
.deliverable-more-dropdown .el-dropdown-menu__item {
  font-size: 13px;
  line-height: 1.6;
  padding: 6px 14px;
}
.deliverable-more-dropdown .el-dropdown-menu__item .el-icon {
  font-size: 13px;
}
</style>
