<template>
<div class="f1-consistency">
  <div class="cc-bar">
    <span class="cc-title">披露勾稽</span>
    <el-tag size="small" type="success">通过 {{ stat.pass }}</el-tag>
    <el-tag v-if="stat.error" size="small" type="danger">异常 {{ stat.error }}</el-tag>
    <el-tag v-if="stat.warning" size="small" type="warning">提示 {{ stat.warning }}</el-tag>
    <el-tag v-if="stat.skipped" size="small" type="info">跳过 {{ stat.skipped }}</el-tag>
    <span v-if="!stat.total" class="muted">暂无可比对数据</span>
    <el-button size="small" text type="primary" @click="expanded = !expanded">
      {{ expanded ? '收起明细' : '展开明细' }}
    </el-button>
  </div>

  <el-table
    v-if="expanded"
    :data="results"
    size="small"
    class="cc-table"
    :row-class-name="rowClass"
    style="width:100%"
  >
    <el-table-column label="校验项" min-width="260">
      <template #default="{ row }">
        <el-tooltip :content="row.rule" placement="top" :show-after="200">
          <span class="rule-label">{{ row.label }}</span>
        </el-tooltip>
        <el-tag size="small" type="info" class="rule-id">{{ row.id }}</el-tag>
      </template>
    </el-table-column>
    <el-table-column label="左值" min-width="130" align="right">
      <template #default="{ row }">
        <span v-if="row.left !== null">{{ fmtAmount(row.left) }}</span>
        <span v-else class="muted">—</span>
      </template>
    </el-table-column>
    <el-table-column label="右值" min-width="130" align="right">
      <template #default="{ row }">
        <span v-if="row.right !== null">{{ fmtAmount(row.right) }}</span>
        <span v-else class="muted">—</span>
      </template>
    </el-table-column>
    <el-table-column label="差异" min-width="120" align="right">
      <template #default="{ row }">
        <span v-if="row.diff !== null" :class="{ 'diff-bad': row.level === 'error' }">
          {{ fmtAmount(row.diff) }}
        </span>
        <span v-else class="muted">—</span>
      </template>
    </el-table-column>
    <el-table-column label="结论" min-width="90">
      <template #default="{ row }">
        <el-tag size="small" :type="levelTag(row.level).type">{{ levelTag(row.level).text }}</el-tag>
      </template>
    </el-table-column>
    <el-table-column label="说明" min-width="240">
      <template #default="{ row }">
        <span class="detail-text">{{ row.detail }}</span>
      </template>
    </el-table-column>
    <el-table-column label="追溯" min-width="150">
      <template #default="{ row }">
        <span v-for="ref in row.refs" :key="ref" class="chip-wrap">
          <GtIndexChip :value="ref" :context-project-id="projectId" />
        </span>
      </template>
    </el-table-column>
  </el-table>
</div>
</template>

<script setup lang="ts">
/**
 * F1DisclosureConsistencyPanel — F1 披露内部勾稽面板
 *
 * 规则引擎在 `composables/f1DisclosureConsistency.ts`（纯函数，规则全取 F7-1~F7-14）。
 * 本组件只做展示：紧凑单行 bar + 折叠明细表 + 规则 tooltip + GtIndexChip 追溯。
 *
 * spec: .kiro/specs/f1-four-table-extraction-and-disclosure-alignment/ R8.1
 */
import { computed, ref } from 'vue'
import { useDisplayPrefsStore } from '@/stores/displayPrefs'
import {
  summarizeF1Checks,
  type F1CheckLevel,
  type F1CheckResult,
} from '../composables/f1DisclosureConsistency'
// @ts-ignore - GtIndexChip may not have type declarations
import GtIndexChip from '../GtIndexChip.vue'

const props = defineProps<{
  results: F1CheckResult[]
  projectId?: string
}>()

const displayPrefs = useDisplayPrefsStore()
const expanded = ref(false)

const results = computed(() => props.results ?? [])
const stat = computed(() => summarizeF1Checks(results.value))

const LEVEL_TAG: Record<F1CheckLevel, { text: string; type: 'success' | 'warning' | 'danger' | 'info' }> = {
  pass: { text: '通过', type: 'success' },
  warning: { text: '提示', type: 'warning' },
  error: { text: '异常', type: 'danger' },
  skipped: { text: '跳过', type: 'info' },
}

function levelTag(level: F1CheckLevel) {
  return LEVEL_TAG[level] ?? LEVEL_TAG.skipped
}

function rowClass({ row }: { row: F1CheckResult }): string {
  return row.level === 'error' ? 'cc-row-error' : ''
}

function fmtAmount(v: number | null | undefined): string {
  return displayPrefs.fmtAmount(v)
}
</script>

<style scoped>
.f1-consistency { margin-bottom: 10px; }
.cc-bar {
  display: flex; align-items: center; gap: 8px; flex-wrap: wrap;
  padding: 6px 12px; background: #f5f7fa; border-radius: 4px;
  font-size: var(--wp-font-size, 13px);
}
.cc-title { font-weight: 600; color: #303133; }
.cc-table { margin-top: 6px; font-size: var(--wp-font-size, 13px); }
.cc-table :deep(.cc-row-error) { background: #fef0f0; }
.rule-label { border-bottom: 1px dashed #909399; cursor: help; }
.rule-id { margin-left: 6px; }
.detail-text { color: #606266; line-height: 1.5; }
.diff-bad { color: #f56c6c; font-weight: 600; }
.muted { color: #909399; }
.chip-wrap { display: inline-flex; margin-right: 4px; }
</style>
