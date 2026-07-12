<script setup lang="ts">
/**
 * VersionDiffPanel — 版本 diff 对比面板
 *
 * Spec: .kiro/specs/workpaper-version-trail/
 * Task: 7.1
 *
 * 职责：
 * - 顶部统计卡片：新增 | 删除 | 修改 | 未变
 * - el-table 展示 diff 列表：item_id | 字段 | 版本A值 | 版本B值 | 变更类型
 * - 行颜色：added=绿色背景 deleted=红色背景 modified=黄色背景
 * - el-tag 变更类型标签（新增/删除/修改）
 * - 空状态：两版本完全相同时显示"无差异"
 *
 * Requirements: 4.5, 4.6
 */
import { computed } from 'vue'
import type { DiffResult, DiffItem, SnapshotMeta } from '../composables/useVersionTrail'
import { fmtDateTime } from '@/utils/formatters'

// ─── Props ───────────────────────────────────────────────────────────────────

const props = defineProps<{
  diffResult: DiffResult
  versionA: SnapshotMeta
  versionB: SnapshotMeta
}>()

// ─── 字段名中文映射 ──────────────────────────────────────────────────────────

const FIELD_NAME_MAP: Record<string, string> = {
  conclusion: '结论',
  remark: '备注',
  wp_ref: '底稿引用',
}

function displayFieldName(fieldName?: string): string {
  if (!fieldName) return '-'
  return FIELD_NAME_MAP[fieldName] ?? fieldName
}

// ─── 变更类型配置 ────────────────────────────────────────────────────────────

const CHANGE_TYPE_CONFIG: Record<string, { label: string; tagType: 'success' | 'danger' | 'warning' }> = {
  added: { label: '新增', tagType: 'success' },
  deleted: { label: '删除', tagType: 'danger' },
  modified: { label: '修改', tagType: 'warning' },
}

function getChangeLabel(changeType: string): string {
  return CHANGE_TYPE_CONFIG[changeType]?.label ?? changeType
}

function getChangeTagType(changeType: string): 'success' | 'danger' | 'warning' {
  return CHANGE_TYPE_CONFIG[changeType]?.tagType ?? 'warning'
}

// ─── 统计数据 ────────────────────────────────────────────────────────────────

const stats = computed(() => ({
  added: props.diffResult.added.length,
  deleted: props.diffResult.deleted.length,
  modified: props.diffResult.modified.length,
  unchanged: props.diffResult.unchangedCount,
}))

// ─── 合并 diff 列表（扁平化展示） ───────────────────────────────────────────

interface FlatDiffRow {
  key: string
  itemId: string
  changeType: 'added' | 'deleted' | 'modified'
  fieldName: string | undefined
  valueA: string | null | undefined
  valueB: string | null | undefined
}

const flatDiffRows = computed<FlatDiffRow[]>(() => {
  const rows: FlatDiffRow[] = []

  // added items
  for (const item of props.diffResult.added) {
    rows.push({
      key: `added-${item.itemId}-${item.fieldName ?? ''}`,
      itemId: item.itemId,
      changeType: 'added',
      fieldName: item.fieldName,
      valueA: item.valueA,
      valueB: item.valueB,
    })
  }

  // deleted items
  for (const item of props.diffResult.deleted) {
    rows.push({
      key: `deleted-${item.itemId}-${item.fieldName ?? ''}`,
      itemId: item.itemId,
      changeType: 'deleted',
      fieldName: item.fieldName,
      valueA: item.valueA,
      valueB: item.valueB,
    })
  }

  // modified items
  for (const item of props.diffResult.modified) {
    rows.push({
      key: `modified-${item.itemId}-${item.fieldName ?? ''}`,
      itemId: item.itemId,
      changeType: 'modified',
      fieldName: item.fieldName,
      valueA: item.valueA,
      valueB: item.valueB,
    })
  }

  return rows
})

// ─── 是否无差异 ──────────────────────────────────────────────────────────────

const noDifference = computed(() => {
  return stats.value.added === 0
    && stats.value.deleted === 0
    && stats.value.modified === 0
})

// ─── 行样式 ──────────────────────────────────────────────────────────────────

function getRowClassName({ row }: { row: FlatDiffRow }): string {
  switch (row.changeType) {
    case 'added': return 'diff-row-added'
    case 'deleted': return 'diff-row-deleted'
    case 'modified': return 'diff-row-modified'
    default: return ''
  }
}

// ─── 显示值（null 转为占位文本） ─────────────────────────────────────────────

function displayValue(val: string | null | undefined): string {
  if (val === null || val === undefined || val === '') return '(空)'
  return val
}
</script>

<template>
  <div class="version-diff-panel">
    <!-- 对比版本信息 -->
    <div class="vdp-header">
      <span class="vdp-header-label">
        版本A: {{ fmtDateTime(versionA.createdAt) }}
      </span>
      <span class="vdp-header-vs">→</span>
      <span class="vdp-header-label">
        版本B: {{ fmtDateTime(versionB.createdAt) }}
      </span>
    </div>

    <!-- 统计卡片 -->
    <div class="vdp-stats">
      <div class="vdp-stat-card vdp-stat-added">
        <div class="vdp-stat-value">{{ stats.added }}</div>
        <div class="vdp-stat-label">新增</div>
      </div>
      <div class="vdp-stat-card vdp-stat-deleted">
        <div class="vdp-stat-value">{{ stats.deleted }}</div>
        <div class="vdp-stat-label">删除</div>
      </div>
      <div class="vdp-stat-card vdp-stat-modified">
        <div class="vdp-stat-value">{{ stats.modified }}</div>
        <div class="vdp-stat-label">修改</div>
      </div>
      <div class="vdp-stat-card vdp-stat-unchanged">
        <div class="vdp-stat-value">{{ stats.unchanged }}</div>
        <div class="vdp-stat-label">未变</div>
      </div>
    </div>

    <!-- 摘要文本 -->
    <div v-if="diffResult.summary" class="vdp-summary">
      {{ diffResult.summary }}
    </div>

    <!-- 空状态：无差异 -->
    <el-empty
      v-if="noDifference"
      description="两版本完全相同，无差异"
      :image-size="80"
    />

    <!-- diff 表格 -->
    <el-table
      v-else
      :data="flatDiffRows"
      :row-class-name="getRowClassName"
      :row-key="(row: FlatDiffRow) => row.key"
      border
      stripe
      size="small"
      class="vdp-table"
      max-height="400"
    >
      <el-table-column
        prop="itemId"
        label="条目ID"
        min-width="160"
        show-overflow-tooltip
      />
      <el-table-column
        label="字段"
        min-width="80"
      >
        <template #default="{ row }">
          {{ displayFieldName(row.fieldName) }}
        </template>
      </el-table-column>
      <el-table-column
        label="版本A值"
        min-width="120"
        show-overflow-tooltip
      >
        <template #default="{ row }">
          <span :class="{ 'vdp-value-empty': row.valueA == null || row.valueA === '' }">
            {{ displayValue(row.valueA) }}
          </span>
        </template>
      </el-table-column>
      <el-table-column
        label="版本B值"
        min-width="120"
        show-overflow-tooltip
      >
        <template #default="{ row }">
          <span :class="{ 'vdp-value-empty': row.valueB == null || row.valueB === '' }">
            {{ displayValue(row.valueB) }}
          </span>
        </template>
      </el-table-column>
      <el-table-column
        label="变更类型"
        width="90"
        align="center"
      >
        <template #default="{ row }">
          <el-tag
            size="small"
            :type="getChangeTagType(row.changeType)"
            effect="plain"
          >
            {{ getChangeLabel(row.changeType) }}
          </el-tag>
        </template>
      </el-table-column>
    </el-table>
  </div>
</template>

<style scoped>
.version-diff-panel {
  padding: 0;
}

/* ─── Header ─────────────────────────────────────────────────────────────── */

.vdp-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
  font-size: var(--wp-font-size, 13px);
  color: #606266;
}

.vdp-header-label {
  padding: 4px 8px;
  background: #f0f2f5;
  border-radius: 4px;
  font-family: monospace;
}

.vdp-header-vs {
  font-weight: bold;
  color: #409eff;
}

/* ─── Stats Cards ────────────────────────────────────────────────────────── */

.vdp-stats {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 10px;
  margin-bottom: 12px;
}

.vdp-stat-card {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 10px 8px;
  border-radius: 6px;
  border: 1px solid #ebeef5;
}

.vdp-stat-value {
  font-size: 22px;
  font-weight: 600;
  line-height: 1.2;
}

.vdp-stat-label {
  font-size: 12px;
  color: #909399;
  margin-top: 4px;
}

.vdp-stat-added {
  background: #f0f9eb;
  border-color: #c2e7b0;
}
.vdp-stat-added .vdp-stat-value {
  color: #67c23a;
}

.vdp-stat-deleted {
  background: #fef0f0;
  border-color: #fbc4c4;
}
.vdp-stat-deleted .vdp-stat-value {
  color: #f56c6c;
}

.vdp-stat-modified {
  background: #fdf6ec;
  border-color: #f5dab1;
}
.vdp-stat-modified .vdp-stat-value {
  color: #e6a23c;
}

.vdp-stat-unchanged {
  background: #f4f4f5;
  border-color: #e4e7ed;
}
.vdp-stat-unchanged .vdp-stat-value {
  color: #909399;
}

/* ─── Summary ────────────────────────────────────────────────────────────── */

.vdp-summary {
  margin-bottom: 12px;
  padding: 8px 12px;
  background: #f5f7fa;
  border-radius: 4px;
  font-size: 12px;
  color: #606266;
}

/* ─── Table ──────────────────────────────────────────────────────────────── */

.vdp-table {
  font-size: var(--wp-font-size, 13px);
}

.vdp-value-empty {
  color: #c0c4cc;
  font-style: italic;
}

/* ─── Row Colors ─────────────────────────────────────────────────────────── */

:deep(.diff-row-added) {
  background-color: #f0f9eb !important;
}
:deep(.diff-row-added td.el-table__cell) {
  background-color: #f0f9eb !important;
}

:deep(.diff-row-deleted) {
  background-color: #fef0f0 !important;
}
:deep(.diff-row-deleted td.el-table__cell) {
  background-color: #fef0f0 !important;
}

:deep(.diff-row-modified) {
  background-color: #fdf6ec !important;
}
:deep(.diff-row-modified td.el-table__cell) {
  background-color: #fdf6ec !important;
}
</style>
