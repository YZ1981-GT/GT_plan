<template>
  <div class="j2-consistency" :class="result.allPass ? 'is-pass' : 'is-fail'">
    <div class="bar" @click="expanded = !expanded">
      <span class="bar-icon">{{ result.allPass ? '✅' : '⚠️' }}</span>
      <span class="bar-text">
        披露内部勾稽 {{ result.checks.length }} 项 ·
        <strong :class="result.allPass ? 'ok-text' : 'err-text'">
          {{ result.allPass ? '全部一致' : `${result.errorCount} 项不平` }}
        </strong>
      </span>
      <span class="bar-hint">{{ expanded ? '收起明细 ▴' : '查看明细 ▾' }}</span>
    </div>
    <div v-show="expanded" class="detail">
      <el-table :data="sortedChecks" size="small" :show-header="true"
        :row-class-name="({ row }) => (row.level === 'error' ? 'check-error-row' : '')">
        <el-table-column label="校验项" min-width="280">
          <template #default="{ row }">
            <el-tooltip :content="row.rule" placement="top" :show-after="200">
              <span class="check-label">{{ row.label }}</span>
            </el-tooltip>
          </template>
        </el-table-column>
        <el-table-column label="本表值" align="right" width="140">
          <template #default="{ row }">{{ fmt(row.left) }}</template>
        </el-table-column>
        <el-table-column label="勾稽值" align="right" width="140">
          <template #default="{ row }">{{ fmt(row.right) }}</template>
        </el-table-column>
        <el-table-column label="差异" align="right" width="120">
          <template #default="{ row }">
            <span :class="row.level === 'error' ? 'err-text' : ''">{{ fmt(row.diff) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="结论" min-width="140">
          <template #default="{ row }">
            <el-tag :type="row.level === 'error' ? 'danger' : 'success'" size="small" effect="plain">
              {{ row.level === 'error' ? '不平' : '一致' }}
            </el-tag>
            <span v-if="row.detail" class="check-detail">{{ row.detail }}</span>
          </template>
        </el-table-column>
        <el-table-column label="追溯" width="100">
          <template #default="{ row }">
            <span v-for="r in row.refs" :key="r" class="chip-wrap">
              <GtIndexChip :value="r" :context-project-id="projectId" />
            </span>
          </template>
        </el-table-column>
      </el-table>
    </div>
  </div>
</template>

<script setup lang="ts">
/**
 * J2DisclosureConsistencyPanel — J2 设定受益计划披露内部勾稽面板
 *
 * 沿用 J1/H1 已验证范式（紧凑单行 bar + 折叠明细表 + 规则 tooltip + GtIndexChip 追溯），
 * 结论由纯函数 `buildJ2SoeConsistency` / `buildJ2ListedConsistency` 产出，本组件不做计算。
 */
import { computed, ref } from 'vue'
import GtIndexChip from '../GtIndexChip.vue'
import { useDisplayPrefsStore } from '@/stores/displayPrefs'
import type { J2ConsistencySummary } from '../composables/j2DisclosureConsistency'

const props = withDefaults(
  defineProps<{
    result: J2ConsistencySummary
    projectId?: string
    defaultExpanded?: boolean
  }>(),
  { projectId: '', defaultExpanded: false },
)

const expanded = ref(props.defaultExpanded)

const sortedChecks = computed(() =>
  [...props.result.checks].sort(
    (a, b) => (a.level === 'error' ? 0 : 1) - (b.level === 'error' ? 0 : 1),
  ),
)

const displayPrefs = useDisplayPrefsStore()
function fmt(v: number): string { return displayPrefs.fmtAmount(v) }
</script>

<style scoped>
.j2-consistency { margin-bottom: 12px; border-radius: 4px; border: 1px solid var(--el-border-color-lighter); font-size: 13px; }
.j2-consistency.is-pass { border-left: 3px solid var(--el-color-success); }
.j2-consistency.is-fail { border-left: 3px solid var(--el-color-warning); }
.bar { display: flex; align-items: center; gap: 8px; padding: 6px 12px; cursor: pointer; user-select: none; }
.bar:hover { background: var(--el-fill-color-light); }
.bar-icon { font-size: 14px; }
.bar-text { flex: 1; color: #606266; }
.bar-hint { color: var(--el-color-primary); font-size: 12px; }
.ok-text { color: var(--el-color-success); }
.err-text { color: var(--el-color-danger); }
.detail { padding: 0 8px 8px; }
.detail :deep(.el-table) { font-size: 13px !important; }
.detail :deep(.el-table th), .detail :deep(.el-table td) { font-size: 13px !important; padding: 4px 6px !important; }
.detail :deep(.check-error-row) { background-color: var(--el-color-danger-light-9) !important; }
.check-label { border-bottom: 1px dashed #909399; cursor: help; }
.check-detail { margin-left: 6px; color: #909399; }
.chip-wrap { display: inline-flex; align-items: center; margin-right: 4px; }
</style>
