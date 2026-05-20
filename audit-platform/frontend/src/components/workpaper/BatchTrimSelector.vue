<template>
  <div class="gt-batch-trim-selector">
    <h4 class="gt-batch-trim-title">📦 批量筛选</h4>

    <!-- 三种筛选维度 -->
    <div class="gt-batch-trim-filters">
      <el-select
        v-model="filterCycle"
        placeholder="按循环筛选"
        clearable
        size="small"
        style="width: 140px"
        @change="updatePreview"
      >
        <el-option
          v-for="c in cycleOptions"
          :key="c"
          :label="c"
          :value="c"
        />
      </el-select>

      <el-select
        v-model="filterAssertion"
        placeholder="按认定筛选"
        clearable
        size="small"
        style="width: 140px"
        @change="updatePreview"
      >
        <el-option
          v-for="a in assertionOptions"
          :key="a"
          :label="a"
          :value="a"
        />
      </el-select>

      <el-select
        v-model="filterRiskLevel"
        placeholder="按风险等级"
        clearable
        size="small"
        style="width: 140px"
        @change="updatePreview"
      >
        <el-option label="高" value="high" />
        <el-option label="中" value="medium" />
        <el-option label="低" value="low" />
      </el-select>
    </div>

    <!-- 实时预览匹配行 -->
    <div class="gt-batch-trim-preview">
      <span class="gt-batch-trim-preview-count">
        匹配 <strong>{{ matchedRows.length }}</strong> 行程序
      </span>
      <div v-if="matchedRows.length > 0" class="gt-batch-trim-preview-list">
        <div
          v-for="row in matchedRows.slice(0, 10)"
          :key="row.row"
          class="gt-batch-trim-preview-item"
        >
          <span class="gt-batch-trim-preview-row">{{ row.row }}</span>
          <span class="gt-batch-trim-preview-desc">{{ row.description || '—' }}</span>
        </div>
        <div v-if="matchedRows.length > 10" class="gt-batch-trim-preview-more">
          ... 还有 {{ matchedRows.length - 10 }} 行
        </div>
      </div>
    </div>

    <!-- 确认按钮 -->
    <div class="gt-batch-trim-actions">
      <el-button
        type="primary"
        size="small"
        :disabled="matchedRows.length === 0"
        @click="handleBatchTrim"
      >
        批量标记 N/A（{{ matchedRows.length }} 行）
      </el-button>
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
 * BatchTrimSelector — 批量裁剪筛选器
 *
 * 三种筛选维度：按循环 / 按认定 / 按风险等级
 * 实时预览匹配程序行列表及数量
 * 选择后触发 TrimReasonDialog → 确认后 emit batch-trim
 *
 * @see requirements.md Requirement 3.1, 3.2
 */
import { ref, computed } from 'vue'
import TrimReasonDialog from './TrimReasonDialog.vue'
import type { TrimRow } from '@/composables/useProcedureTrimming'

interface Props {
  /** 所有程序行（从 useProcedureTrimming.rows 传入） */
  rows: TrimRow[]
}

const props = defineProps<Props>()

const emit = defineEmits<{
  (e: 'batch-trim', payload: { rowIds: string[]; reason_code: string; reason_text: string | null }): void
}>()

const filterCycle = ref('')
const filterAssertion = ref('')
const filterRiskLevel = ref('')
const showReasonDialog = ref(false)

/** 从 rows 中提取可用的循环选项 */
const cycleOptions = computed(() => {
  const cycles = new Set<string>()
  for (const r of props.rows) {
    if (r.cycle) cycles.add(r.cycle)
  }
  return Array.from(cycles).sort()
})

/** 从 rows 中提取可用的认定选项 */
const assertionOptions = computed(() => {
  const assertions = new Set<string>()
  for (const r of props.rows) {
    for (const a of r.assertions || []) {
      assertions.add(a)
    }
  }
  return Array.from(assertions).sort()
})

/** 匹配的程序行（排除已 N/A 的） */
const matchedRows = computed(() => {
  if (!filterCycle.value && !filterAssertion.value && !filterRiskLevel.value) {
    return []
  }
  return props.rows.filter((r) => {
    // 排除已裁剪行
    if (r.status === 'not_applicable') return false
    // 按循环
    if (filterCycle.value && r.cycle !== filterCycle.value) return false
    // 按认定
    if (filterAssertion.value && !(r.assertions || []).includes(filterAssertion.value)) return false
    // 按风险等级
    if (filterRiskLevel.value && r.risk_level !== filterRiskLevel.value) return false
    return true
  })
})

function updatePreview() {
  // matchedRows is computed, auto-updates
}

function handleBatchTrim() {
  if (matchedRows.value.length === 0) return
  showReasonDialog.value = true
}

function handleReasonConfirm(payload: { reason_code: string; reason_text: string | null }) {
  const rowIds = matchedRows.value.map((r) => r.row)
  emit('batch-trim', {
    rowIds,
    reason_code: payload.reason_code,
    reason_text: payload.reason_text,
  })
  showReasonDialog.value = false
  // 重置筛选
  filterCycle.value = ''
  filterAssertion.value = ''
  filterRiskLevel.value = ''
}
</script>

<style scoped>
.gt-batch-trim-selector {
  border: 1px solid var(--el-border-color-lighter, #e4e7ed);
  border-radius: 6px;
  padding: 12px;
  background: var(--el-fill-color-blank, #fff);
}
.gt-batch-trim-title {
  margin: 0 0 10px;
  font-size: 13px;
  font-weight: 600;
  color: var(--el-text-color-primary, #303133);
}
.gt-batch-trim-filters {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 10px;
}
.gt-batch-trim-preview {
  margin-bottom: 10px;
}
.gt-batch-trim-preview-count {
  font-size: 12px;
  color: var(--el-text-color-secondary, #909399);
}
.gt-batch-trim-preview-list {
  margin-top: 6px;
  max-height: 160px;
  overflow-y: auto;
  border: 1px solid var(--el-border-color-lighter, #e4e7ed);
  border-radius: 4px;
  padding: 4px 8px;
}
.gt-batch-trim-preview-item {
  display: flex;
  gap: 8px;
  font-size: 12px;
  padding: 2px 0;
  border-bottom: 1px solid var(--el-border-color-extra-light, #f2f6fc);
}
.gt-batch-trim-preview-item:last-child {
  border-bottom: none;
}
.gt-batch-trim-preview-row {
  font-weight: 600;
  color: var(--el-color-primary, #409eff);
  min-width: 36px;
}
.gt-batch-trim-preview-desc {
  color: var(--el-text-color-regular, #606266);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.gt-batch-trim-preview-more {
  font-size: 11px;
  color: var(--el-text-color-secondary, #909399);
  padding: 4px 0;
}
.gt-batch-trim-actions {
  text-align: right;
}
</style>
