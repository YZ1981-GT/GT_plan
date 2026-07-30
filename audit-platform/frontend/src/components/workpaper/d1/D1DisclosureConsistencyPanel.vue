<script setup lang="ts">
/**
 * D1DisclosureConsistencyPanel — 应收票据披露表内部勾稽校验面板
 *
 * 展示范式同 H1（平台已验证）：紧凑单行 bar + 折叠明细表 + 规则 tooltip +
 * `GtIndexChip` 追溯。规则真源 = `d1DisclosureConsistency.ts`（预设 `F4-*`）。
 *
 * spec: .kiro/specs/d1-notes-receivable-disclosure-alignment/ R10.3
 */
import { computed, ref } from 'vue'
import GtIndexChip from '../GtIndexChip.vue'
import type { D1ConsistencySummary, D1ConsistencyCheck } from '../composables/d1DisclosureConsistency'

const props = defineProps<{
  summary: D1ConsistencySummary
  projectId?: string
}>()

const expanded = ref(false)

/** 只显示有结论的项（skip 折叠进「未取数」计数，避免空表刷屏） */
const visibleChecks = computed<D1ConsistencyCheck[]>(() => {
  const order: Record<string, number> = { error: 0, warn: 1, ok: 2, skip: 3 }
  return [...props.summary.checks]
    .filter(c => c.level !== 'skip')
    .sort((a, b) => (order[a.level] ?? 9) - (order[b.level] ?? 9))
})

const barType = computed(() => {
  if (props.summary.errorCount > 0) return 'danger'
  if (props.summary.warnCount > 0) return 'warning'
  return 'success'
})

const barText = computed(() => {
  const s = props.summary
  if (s.errorCount > 0) return `勾稽异常 ${s.errorCount} 项`
  if (s.warnCount > 0) return `勾稽提示 ${s.warnCount} 项`
  if (s.okCount > 0) return `勾稽全部通过（${s.okCount} 项）`
  return '暂无可比对数据'
})

const LEVEL_META: Record<string, { label: string; type: string }> = {
  error: { label: '异常', type: 'danger' },
  warn: { label: '提示', type: 'warning' },
  ok: { label: '通过', type: 'success' },
  skip: { label: '未取数', type: 'info' },
}

function fmt(v: number): string {
  if (!Number.isFinite(v)) return '-'
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<template>
  <div class="d1-cc">
    <!-- 紧凑单行 bar（禁空洞 el-card，平台列表页/校验条统一口径） -->
    <div class="d1-cc__bar" :class="`d1-cc__bar--${barType}`" @click="expanded = !expanded">
      <el-tag :type="barType" size="small" effect="dark">{{ barText }}</el-tag>
      <span class="d1-cc__counts">
        通过 {{ summary.okCount }}
        · 提示 {{ summary.warnCount }}
        · 异常 {{ summary.errorCount }}
        · 未取数 {{ summary.skipCount }}
      </span>
      <span class="d1-cc__hint">规则源：应收票据校验预设 F4-1~F4-30</span>
      <el-button link size="small">{{ expanded ? '收起明细 ▴' : '展开明细 ▾' }}</el-button>
    </div>

    <el-table
      v-if="expanded"
      :data="visibleChecks"
      border
      size="small"
      style="width:100%;margin-top:8px"
      :header-cell-style="{ padding: '4px 6px', lineHeight: '1.35' }"
      :cell-style="{ padding: '3px 6px' }"
    >
      <el-table-column label="结论" width="72" align="center">
        <template #default="{ row }">
          <el-tag :type="LEVEL_META[row.level]?.type" size="small" effect="plain">
            {{ LEVEL_META[row.level]?.label }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="校验项" min-width="240">
        <template #default="{ row }">
          <el-tooltip :content="row.rule" placement="top" :show-after="200">
            <span class="d1-cc__label">{{ row.label }}</span>
          </el-tooltip>
        </template>
      </el-table-column>
      <el-table-column label="本表值" min-width="120" align="right">
        <template #default="{ row }"><span class="d1-cc__num">{{ fmt(row.left) }}</span></template>
      </el-table-column>
      <el-table-column label="勾稽对象值" min-width="120" align="right">
        <template #default="{ row }"><span class="d1-cc__num">{{ fmt(row.right) }}</span></template>
      </el-table-column>
      <el-table-column label="差异" min-width="110" align="right">
        <template #default="{ row }">
          <span class="d1-cc__num" :class="{ 'd1-cc__num--bad': row.level === 'error' }">
            {{ fmt(row.diff) }}
          </span>
        </template>
      </el-table-column>
      <el-table-column label="说明" min-width="220">
        <template #default="{ row }"><span class="d1-cc__detail">{{ row.detail }}</span></template>
      </el-table-column>
      <el-table-column label="追溯" min-width="140">
        <template #default="{ row }">
          <GtIndexChip
            v-for="r in row.refs"
            :key="r"
            :value="r"
            :context-project-id="projectId"
            style="margin-right:4px"
          />
        </template>
      </el-table-column>
    </el-table>
  </div>
</template>

<style scoped>
.d1-cc {
  margin: 8px 0 12px;
}
.d1-cc__bar {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 6px 10px;
  border-radius: 4px;
  border: 1px solid #dcdfe6;
  background: #fafafa;
  cursor: pointer;
  font-size: 12px;
}
.d1-cc__bar--danger { border-left: 3px solid #f56c6c; }
.d1-cc__bar--warning { border-left: 3px solid #e6a23c; }
.d1-cc__bar--success { border-left: 3px solid #67c23a; }
.d1-cc__counts { color: #606266; }
.d1-cc__hint { color: #909399; margin-left: auto; }
.d1-cc__label { border-bottom: 1px dashed #909399; cursor: help; }
.d1-cc__num { font-variant-numeric: tabular-nums; white-space: nowrap; }
.d1-cc__num--bad { color: #f56c6c; font-weight: 600; }
.d1-cc__detail { color: #606266; }
</style>
