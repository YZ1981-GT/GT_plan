<template>
  <div class="gt-trimming-panel">
    <!-- 顶部统计摘要 -->
    <div class="gt-trimming-stats-bar">
      <div class="gt-trimming-stat">
        <span class="gt-trimming-stat-label">总程序数</span>
        <span class="gt-trimming-stat-value">{{ stats.total }}</span>
      </div>
      <div class="gt-trimming-stat">
        <span class="gt-trimming-stat-label">已裁剪</span>
        <span class="gt-trimming-stat-value gt-trimmed">{{ stats.trimmed }}</span>
      </div>
      <div class="gt-trimming-stat">
        <span class="gt-trimming-stat-label">裁剪率</span>
        <span class="gt-trimming-stat-value" :class="{ 'gt-warning': stats.trimRate > 50 }">
          {{ stats.trimRate }}%
        </span>
      </div>
    </div>

    <!-- 批量筛选器（manager+ 可见） -->
    <BatchTrimSelector
      v-if="canTrim"
      :rows="rows"
      @batch-trim="handleBatchTrim"
    />

    <!-- 程序行列表 -->
    <div class="gt-trimming-list">
      <div
        v-for="row in rows"
        :key="row.row"
        class="gt-trimming-row"
        :class="{ 'is-trimmed': row.status === 'not_applicable' }"
      >
        <div class="gt-trimming-row-info">
          <span class="gt-trimming-row-id">{{ row.row }}</span>
          <span class="gt-trimming-row-desc">{{ row.description || '—' }}</span>
          <el-tag
            v-if="row.status === 'not_applicable'"
            type="info"
            size="small"
            class="gt-trimming-na-tag"
          >
            N/A
          </el-tag>
        </div>

        <!-- 裁剪理由摘要（已裁剪行） -->
        <div v-if="row.status === 'not_applicable'" class="gt-trimming-row-reason">
          <span class="gt-trimming-reason-text">
            {{ getReasonLabel(row.reason_code) }}
            <template v-if="row.reason_text">: {{ row.reason_text }}</template>
          </span>
        </div>

        <!-- 操作按钮（manager+ 可见） -->
        <div v-if="canTrim" class="gt-trimming-row-actions">
          <el-button
            v-if="row.status !== 'not_applicable'"
            type="warning"
            text
            size="small"
            @click="handleTrimSingle(row)"
          >
            标记 N/A
          </el-button>
          <el-button
            v-if="row.status === 'not_applicable'"
            type="success"
            text
            size="small"
            @click="handleRevert(row)"
          >
            恢复
          </el-button>
        </div>
      </div>

      <div v-if="rows.length === 0 && !loading" class="gt-trimming-empty">
        暂无程序行数据
      </div>
      <div v-if="loading" class="gt-trimming-loading">
        <el-icon class="is-loading"><Loading /></el-icon> 加载中...
      </div>
    </div>

    <!-- TrimReasonDialog -->
    <TrimReasonDialog
      :visible="showReasonDialog"
      @update:visible="showReasonDialog = $event"
      @confirm="handleReasonConfirm"
      @cancel="showReasonDialog = false"
    />
  </div>
</template>

<script setup lang="ts">
/**
 * ProcedureTrimmingPanel — 程序适用性裁剪主面板
 *
 * 作为 WorkpaperAuditNav 新 tab "程序适用性"
 * - 顶部统计摘要（总程序数 / 已裁剪数 / 裁剪率）
 * - 程序行列表：行号 + 程序描述 + 当前状态 + N/A 标记
 * - "标记 N/A" 按钮（manager+ 可见）→ 弹出 TrimReasonDialog
 * - "恢复" 按钮（manager+ 可见）→ 直接调用 revertRows
 * - RBAC：assistant/auditor 角色隐藏操作按钮（只读模式）
 *
 * @see requirements.md Requirement 1.1, 1.2, 1.3, 1.4, 2.1, 4.1, 8.2
 */
import { ref, computed } from 'vue'
import { Loading } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { usePermission } from '@/composables/usePermission'
import { useProcedureTrimming } from '@/composables/useProcedureTrimming'
import TrimReasonDialog from './TrimReasonDialog.vue'
import BatchTrimSelector from './BatchTrimSelector.vue'
import type { TrimRow, TrimReason } from '@/composables/useProcedureTrimming'

interface Props {
  projectId: string
  wpId: string
  sheetKey: string
}

const props = defineProps<Props>()

const { rows, stats, loading, trimRows, revertRows } = useProcedureTrimming(
  props.projectId,
  props.wpId,
  props.sheetKey,
)

// RBAC: manager+ 可操作
const { role } = usePermission()
const canTrim = computed(() => {
  return ['admin', 'partner', 'manager'].includes(role.value)
})

// 单行裁剪
const showReasonDialog = ref(false)
const pendingTrimRow = ref<TrimRow | null>(null)

function handleTrimSingle(row: TrimRow) {
  pendingTrimRow.value = row
  showReasonDialog.value = true
}

async function handleReasonConfirm(payload: { reason_code: string; reason_text: string | null }) {
  if (!pendingTrimRow.value) return
  const result = await trimRows(
    [pendingTrimRow.value.row],
    { reason_code: payload.reason_code, reason_text: payload.reason_text } as TrimReason,
  )
  if (result.ok) {
    ElMessage.success(`已标记 ${result.succeeded.length} 行为 N/A`)
  } else {
    ElMessage.error(result.message || '操作失败')
  }
  pendingTrimRow.value = null
}

// 恢复
async function handleRevert(row: TrimRow) {
  const result = await revertRows([row.row])
  if (result.ok) {
    ElMessage.success(`已恢复 ${result.succeeded.length} 行`)
  } else {
    ElMessage.error(result.message || '恢复失败')
  }
}

// 批量裁剪
async function handleBatchTrim(payload: { rowIds: string[]; reason_code: string; reason_text: string | null }) {
  const result = await trimRows(
    payload.rowIds,
    { reason_code: payload.reason_code, reason_text: payload.reason_text } as TrimReason,
  )
  if (result.ok) {
    const msg = `批量裁剪完成：成功 ${result.succeeded.length} / 跳过 ${result.skipped.length} / 失败 ${result.failed.length}`
    ElMessage.success(msg)
  } else {
    ElMessage.error(result.message || '批量操作失败')
  }
}

// 理由标签映射
function getReasonLabel(code?: string): string {
  const map: Record<string, string> = {
    no_related_business: '无相关业务',
    low_risk_assessment: '风险评估为低',
    control_test_effective: '控制测试有效',
    other: '其他',
  }
  return map[code || ''] || code || '—'
}
</script>

<style scoped>
.gt-trimming-panel {
  padding: 8px 0;
}
.gt-trimming-stats-bar {
  display: flex;
  gap: 16px;
  padding: 8px 12px;
  background: var(--el-fill-color-light, #f5f7fa);
  border-radius: 6px;
  margin-bottom: 10px;
}
.gt-trimming-stat {
  display: flex;
  flex-direction: column;
  align-items: center;
}
.gt-trimming-stat-label {
  font-size: 11px;
  color: var(--el-text-color-secondary, #909399);
}
.gt-trimming-stat-value {
  font-size: 16px;
  font-weight: 700;
  color: var(--el-text-color-primary, #303133);
}
.gt-trimming-stat-value.gt-trimmed {
  color: var(--el-color-warning, #e6a23c);
}
.gt-trimming-stat-value.gt-warning {
  color: var(--el-color-danger, #f56c6c);
}
.gt-trimming-list {
  margin-top: 10px;
}
.gt-trimming-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  padding: 6px 8px;
  border-bottom: 1px solid var(--el-border-color-extra-light, #f2f6fc);
  transition: background 0.15s;
}
.gt-trimming-row:hover {
  background: var(--el-fill-color-lighter, #fafafa);
}
.gt-trimming-row.is-trimmed {
  background: var(--el-fill-color-light, #f5f7fa);
  opacity: 0.75;
}
.gt-trimming-row-info {
  display: flex;
  align-items: center;
  gap: 6px;
  flex: 1;
  min-width: 0;
}
.gt-trimming-row-id {
  font-size: 12px;
  font-weight: 600;
  color: var(--el-color-primary, #409eff);
  min-width: 32px;
}
.gt-trimming-row-desc {
  font-size: 12px;
  color: var(--el-text-color-regular, #606266);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.gt-trimming-na-tag {
  flex-shrink: 0;
}
.gt-trimming-row-reason {
  width: 100%;
  padding-left: 38px;
}
.gt-trimming-reason-text {
  font-size: 11px;
  color: var(--el-text-color-secondary, #909399);
  font-style: italic;
}
.gt-trimming-row-actions {
  flex-shrink: 0;
}
.gt-trimming-empty,
.gt-trimming-loading {
  text-align: center;
  padding: 20px;
  font-size: 12px;
  color: var(--el-text-color-secondary, #909399);
}
</style>
