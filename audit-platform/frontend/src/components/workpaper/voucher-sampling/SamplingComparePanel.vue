<script setup lang="ts">
/**
 * SamplingComparePanel — 抽凭版本对比面板
 *
 * Spec: .kiro/specs/voucher-sampling-engine/
 * Task: 9.2
 *
 * 功能：
 * - el-dialog 展示两次抽凭的 diff 对比
 * - el-tabs 三栏切换：新增（绿色）/ 删除（红色）/ 保留（无标记）
 * - 每栏 el-table 显示凭证号
 * - 顶部统计摘要：新增N笔 | 删除N笔 | 保留N笔
 *
 * Requirements: 6.3
 */
import { computed } from 'vue'

// ─── Props ────────────────────────────────────────────────────────────────────

interface Props {
  visible: boolean
  compareResult: {
    added: string[]    // voucher_nos
    removed: string[]
    retained: string[]
  }
}

const props = withDefaults(defineProps<Props>(), {
  compareResult: () => ({ added: [], removed: [], retained: [] }),
})

// ─── Emits ────────────────────────────────────────────────────────────────────

const emit = defineEmits<{
  (e: 'update:visible', val: boolean): void
}>()

// ─── 统计 computed ────────────────────────────────────────────────────────────

const addedCount = computed(() => props.compareResult.added.length)
const removedCount = computed(() => props.compareResult.removed.length)
const retainedCount = computed(() => props.compareResult.retained.length)

// ─── Table 数据转换 ──────────────────────────────────────────────────────────

const addedTableData = computed(() =>
  props.compareResult.added.map(no => ({ voucherNo: no }))
)

const removedTableData = computed(() =>
  props.compareResult.removed.map(no => ({ voucherNo: no }))
)

const retainedTableData = computed(() =>
  props.compareResult.retained.map(no => ({ voucherNo: no }))
)

// ─── Dialog 关闭 ─────────────────────────────────────────────────────────────

function handleClose() {
  emit('update:visible', false)
}
</script>

<template>
  <el-dialog
    :model-value="visible"
    title="版本对比结果"
    width="600px"
    :before-close="handleClose"
    @close="handleClose"
    destroy-on-close
  >
    <!-- ═══ 统计摘要 ═══ -->
    <div class="compare-summary">
      <span class="summary-item summary-added">
        新增 <strong>{{ addedCount }}</strong> 笔
      </span>
      <el-divider direction="vertical" />
      <span class="summary-item summary-removed">
        删除 <strong>{{ removedCount }}</strong> 笔
      </span>
      <el-divider direction="vertical" />
      <span class="summary-item summary-retained">
        保留 <strong>{{ retainedCount }}</strong> 笔
      </span>
    </div>

    <!-- ═══ Tab 切换三栏 ═══ -->
    <el-tabs type="border-card" class="compare-tabs">
      <!-- 新增（绿色） -->
      <el-tab-pane>
        <template #label>
          <span class="tab-label tab-label--added">
            新增
            <el-badge :value="addedCount" :max="999" type="success" class="tab-badge" />
          </span>
        </template>
        <el-table
          :data="addedTableData"
          size="small"
          max-height="320"
          empty-text="无新增凭证"
          class="compare-table table--added"
        >
          <el-table-column prop="voucherNo" label="凭证号" />
        </el-table>
      </el-tab-pane>

      <!-- 删除（红色） -->
      <el-tab-pane>
        <template #label>
          <span class="tab-label tab-label--removed">
            删除
            <el-badge :value="removedCount" :max="999" type="danger" class="tab-badge" />
          </span>
        </template>
        <el-table
          :data="removedTableData"
          size="small"
          max-height="320"
          empty-text="无删除凭证"
          class="compare-table table--removed"
        >
          <el-table-column prop="voucherNo" label="凭证号" />
        </el-table>
      </el-tab-pane>

      <!-- 保留（默认/灰色） -->
      <el-tab-pane>
        <template #label>
          <span class="tab-label tab-label--retained">
            保留
            <el-badge :value="retainedCount" :max="999" type="info" class="tab-badge" />
          </span>
        </template>
        <el-table
          :data="retainedTableData"
          size="small"
          max-height="320"
          empty-text="无保留凭证"
          class="compare-table table--retained"
        >
          <el-table-column prop="voucherNo" label="凭证号" />
        </el-table>
      </el-tab-pane>
    </el-tabs>
  </el-dialog>
</template>

<style scoped>
/* ── 统计摘要 ── */
.compare-summary {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  margin-bottom: 16px;
  padding: 12px 16px;
  background: var(--el-fill-color-lighter, #fafafa);
  border-radius: 6px;
  font-size: 14px;
}

.summary-item {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.summary-item strong {
  font-size: 16px;
  margin: 0 2px;
}

.summary-added {
  color: var(--el-color-success, #67c23a);
}

.summary-removed {
  color: var(--el-color-danger, #f56c6c);
}

.summary-retained {
  color: var(--el-text-color-secondary, #909399);
}

/* ── Tab 标签 ── */
.compare-tabs {
  border-radius: 4px;
}

.tab-label {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: var(--wp-font-size, 13px);
}

.tab-label--added {
  color: var(--el-color-success, #67c23a);
}

.tab-label--removed {
  color: var(--el-color-danger, #f56c6c);
}

.tab-label--retained {
  color: var(--el-text-color-regular, #606266);
}

.tab-badge {
  margin-left: 2px;
}

/* ── Table 样式 ── */
.compare-table {
  width: 100%;
}

.table--added :deep(.el-table__header th) {
  background-color: var(--el-color-success-light-9, #f0f9eb) !important;
}

.table--removed :deep(.el-table__header th) {
  background-color: var(--el-color-danger-light-9, #fef0f0) !important;
}

.table--retained :deep(.el-table__header th) {
  background-color: var(--el-fill-color-light, #f5f7fa) !important;
}
</style>
