<script setup lang="ts">
/**
 * CutoffHistoryDrawer — 提取历史侧栏
 *
 * Spec: .kiro/specs/cutoff-test-auto-sampling/
 * Task: 9.1
 *
 * 功能：
 * - el-drawer（direction=rtl，width=480px）展示提取历史
 * - el-timeline 展示历史记录列表（按时间倒序）
 * - 每条记录显示：操作时间 | 操作人 | 填充模式 | 填充笔数 | 匹配总笔数
 * - el-collapse 展开查看完整 extraction_criteria JSON
 * - 最新非撤销记录显示"撤销"按钮；其他记录按钮禁用 + tooltip
 * - 已撤销记录灰色删除线样式 + is_undone 标记
 * - 撤销确认弹窗（el-message-box）
 *
 * Requirements: 5.3, 5.4, 5.7, 5.8, 9.4
 */
import { computed } from 'vue'
import { ElMessageBox } from 'element-plus'
import type { ExtractionLogEntry, FillMode } from '../composables/useCutoffAutoSampling'

// ─── Props ────────────────────────────────────────────────────────────────────

interface Props {
  visible: boolean
  historyList: ExtractionLogEntry[]
}

const props = defineProps<Props>()

// ─── Emits ────────────────────────────────────────────────────────────────────

const emit = defineEmits<{
  (e: 'update:visible', v: boolean): void
  (e: 'undo', logId: string): void
}>()

// ─── Computed ─────────────────────────────────────────────────────────────────

const drawerVisible = computed({
  get: () => props.visible,
  set: (v: boolean) => emit('update:visible', v),
})

/**
 * 找到列表中第一条 isUndone===false 的记录ID（列表已按 createdAt DESC 排序）
 * 仅该记录可执行撤销操作
 */
const latestUndoableId = computed<string | null>(() => {
  const entry = props.historyList.find(item => !item.isUndone)
  return entry?.id ?? null
})

// ─── 填充模式中文映射 ─────────────────────────────────────────────────────────

const FILL_MODE_LABELS: Record<FillMode, string> = {
  append: '追加',
  replace: '替换',
  merge: '合并去重',
}

function getFillModeLabel(mode: FillMode): string {
  return FILL_MODE_LABELS[mode] || mode
}

// ─── Timeline 节点类型映射 ─────────────────────────────────────────────────────

function getTimelineNodeType(entry: ExtractionLogEntry): string {
  if (entry.isUndone) return 'info'
  if (entry.id === latestUndoableId.value) return 'primary'
  return 'success'
}

// ─── 撤销操作 ─────────────────────────────────────────────────────────────────

async function handleUndo(logId: string) {
  try {
    await ElMessageBox.confirm(
      '将回滚到本次填充前的状态，是否继续？',
      '确认撤销',
      {
        confirmButtonText: '确认撤销',
        cancelButtonText: '取消',
        type: 'warning',
      },
    )
    emit('undo', logId)
  } catch {
    // 用户点取消，不执行任何操作
  }
}

/**
 * 判断某条记录是否为可撤销的最新记录
 */
function isUndoable(entry: ExtractionLogEntry): boolean {
  return !entry.isUndone && entry.id === latestUndoableId.value
}

/**
 * 格式化 extraction_criteria JSON 展示
 */
function formatCriteria(criteria: unknown): string {
  try {
    return JSON.stringify(criteria, null, 2)
  } catch {
    return String(criteria)
  }
}
</script>

<template>
  <el-drawer
    v-model="drawerVisible"
    title="提取历史"
    direction="rtl"
    size="480px"
    :destroy-on-close="false"
  >
    <!-- 空状态 -->
    <el-empty v-if="historyList.length === 0" description="暂无提取记录" />

    <!-- 历史时间线 -->
    <el-timeline v-else>
      <el-timeline-item
        v-for="entry in historyList"
        :key="entry.id"
        :type="getTimelineNodeType(entry)"
        :timestamp="entry.createdAt"
        placement="top"
      >
        <div
          class="history-entry"
          :class="{ 'history-entry--undone': entry.isUndone }"
        >
          <!-- 记录摘要信息 -->
          <div class="entry-header">
            <div class="entry-meta">
              <span class="entry-user">{{ entry.userId }}</span>
              <el-tag size="small" :type="entry.isUndone ? 'info' : 'primary'" effect="plain">
                {{ getFillModeLabel(entry.fillMode) }}
              </el-tag>
              <span v-if="entry.isUndone" class="undone-badge">(已撤销)</span>
            </div>
            <div class="entry-stats">
              <span>填充 <strong>{{ entry.filledCount }}</strong> 笔</span>
              <span class="stats-sep">|</span>
              <span>匹配 {{ entry.totalMatched }} 笔</span>
            </div>
          </div>

          <!-- 提取条件折叠展示 -->
          <el-collapse class="entry-collapse">
            <el-collapse-item title="查看提取条件">
              <pre class="criteria-json">{{ formatCriteria(entry.extractionCriteria) }}</pre>
            </el-collapse-item>
          </el-collapse>

          <!-- 撤销按钮 -->
          <div v-if="!entry.isUndone" class="entry-actions">
            <el-tooltip
              v-if="!isUndoable(entry)"
              content="仅可撤销最近一次操作"
              placement="top"
            >
              <el-button size="small" type="warning" plain disabled>
                撤销
              </el-button>
            </el-tooltip>
            <el-button
              v-else
              size="small"
              type="warning"
              plain
              @click="handleUndo(entry.id)"
            >
              撤销
            </el-button>
          </div>
        </div>
      </el-timeline-item>
    </el-timeline>
  </el-drawer>
</template>

<style scoped>
/* 历史记录条目 */
.history-entry {
  padding: 4px 0;
}

.history-entry--undone {
  opacity: 0.55;
}

.history-entry--undone .entry-header {
  text-decoration: line-through;
  color: #909399;
}

/* 条目头部 */
.entry-header {
  margin-bottom: 6px;
}

.entry-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 4px;
  font-size: 13px;
}

.entry-user {
  font-weight: 500;
  color: #303133;
}

.history-entry--undone .entry-user {
  color: #909399;
}

.undone-badge {
  color: #909399;
  font-size: 12px;
  font-style: italic;
}

.entry-stats {
  font-size: 13px;
  color: #606266;
}

.entry-stats strong {
  color: #303133;
  font-size: 14px;
}

.history-entry--undone .entry-stats {
  color: #909399;
}

.history-entry--undone .entry-stats strong {
  color: #909399;
}

.stats-sep {
  margin: 0 6px;
  color: #c0c4cc;
}

/* 条件折叠区域 */
.entry-collapse {
  margin: 8px 0;
  border: none;
}

.entry-collapse :deep(.el-collapse-item__header) {
  font-size: 12px;
  color: #909399;
  height: 28px;
  line-height: 28px;
  background: transparent;
  border-bottom: none;
}

.entry-collapse :deep(.el-collapse-item__wrap) {
  border-bottom: none;
}

.entry-collapse :deep(.el-collapse-item__content) {
  padding-bottom: 4px;
}

.criteria-json {
  font-family: 'Menlo', 'Monaco', 'Courier New', monospace;
  font-size: 11px;
  line-height: 1.5;
  color: #606266;
  background: #f5f7fa;
  border: 1px solid #ebeef5;
  border-radius: 4px;
  padding: 8px 12px;
  margin: 0;
  overflow-x: auto;
  white-space: pre-wrap;
  word-break: break-all;
  max-height: 200px;
  overflow-y: auto;
}

/* 操作按钮区域 */
.entry-actions {
  margin-top: 8px;
}

/* Timeline 全局样式微调 */
:deep(.el-timeline-item__timestamp) {
  font-size: 12px;
  color: #909399;
}

:deep(.el-timeline) {
  padding-left: 4px;
}
</style>
