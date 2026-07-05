<script setup lang="ts">
/**
 * D3TabIndex — 统一底稿目录（比照 D4TabIndex / D1TabIndex）
 */
import { computed, inject } from 'vue'
import GtIndexChip from '../GtIndexChip.vue'
import GtReviewDot from '../GtReviewDot.vue'
import GtReviewTrigger from '../GtReviewTrigger.vue'
import { D3_INDEX_ROWS, resolveD3SheetLabel } from '../composables/d3SheetLabels'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
  availableSheets?: Array<{ sheet_name?: string }>
  applicableStandards?: string
}>()

const indexRows = computed(() => {
  const std = (props.applicableStandards || '').toLowerCase()
  return D3_INDEX_ROWS.map(row => {
    let applicable = row.applicable
    if (row.code === '附注上市') {
      applicable = std.includes('listed') || !std
    }
    if (row.code === '附注国企') {
      applicable = std.includes('soe') || !std
    }
    return {
      ...row,
      applicable,
      sheetLabel: resolveD3SheetLabel(row.code, props.availableSheets),
    }
  })
})

function hasJsonRows(m: Map<string, any>, key: string): boolean {
  const raw = m.get(key)?.remark
  if (!raw) return false
  try {
    const parsed = JSON.parse(raw)
    return Array.isArray(parsed) && parsed.length > 0
  } catch {
    return false
  }
}

function hasText(m: Map<string, any>, key: string): boolean {
  const v = m.get(key)?.remark
  return typeof v === 'string' && v.trim().length > 0
}

function isSheetComplete(code: string, m: Map<string, any>): boolean {
  switch (code) {
    case 'D3A':
      return [...m.keys()].some(k => k.startsWith('D3-proc-'))
    case 'D3-1':
      return [...m.keys()].some(k => k.startsWith('D3-adj-'))
    case 'D3-2':
      return hasJsonRows(m, 'D3-det-rows')
    case 'D3-3':
      return hasJsonRows(m, 'D3-aje-rows')
    case 'D3-4':
      return hasJsonRows(m, 'D3-ana-debit-rows') || hasJsonRows(m, 'D3-ana-credit-rows') || hasText(m, 'D3-ana-note')
    case 'D3-5':
      return hasJsonRows(m, 'D3-lt-rows')
    case 'D3-6':
      return hasJsonRows(m, 'D3-rp-rows')
    case 'D3-7':
      return hasJsonRows(m, 'D3-vc-current-rows') || hasJsonRows(m, 'D3-vc-post-rows')
    case '附注上市':
    case '附注国企':
      return [...m.keys()].some(k => k.startsWith('D3-disc-'))
    default:
      return false
  }
}

const applicableRows = computed(() => indexRows.value.filter(r => r.applicable))

const completedCount = computed(() =>
  applicableRows.value.filter(r => isSheetComplete(r.code, props.allResponses)).length,
)

const progressPct = computed(() => {
  const total = applicableRows.value.length
  return total > 0 ? Math.round((completedCount.value / total) * 100) : 0
})

const jumpToSection = inject<((sheetName: string) => void) | null>('jumpToSection', null)
</script>

<template>
  <div class="d3-tab-index">
    <div class="index-header">
      <h3>D3 预收账款底稿目录</h3>
      <GtReviewTrigger section-id="D3-index-directory" />
      <div class="progress-wrap">
        <span class="progress-label">编制进度 {{ completedCount }}/{{ applicableRows.length }}</span>
        <el-progress :percentage="progressPct" :stroke-width="10" />
      </div>
    </div>

    <el-table :data="indexRows" size="small" border stripe>
      <el-table-column prop="seq" label="序号" width="60" align="center" />
      <el-table-column prop="group" label="分组" width="80" />
      <el-table-column prop="code" label="索引号" width="90" />
      <el-table-column label="底稿名称" min-width="260">
        <template #default="{ row }">
          <span :class="{ 'na-row': !row.applicable }">{{ row.name }}</span>
          <GtIndexChip
            v-if="row.applicable && jumpToSection"
            :label="row.code"
            class="index-chip"
            @click="jumpToSection(row.sheetLabel)"
          />
          <el-tag
            v-if="row.applicable && isSheetComplete(row.code, allResponses)"
            type="success"
            size="small"
            class="done-tag"
          >已编制</el-tag>
          <GtReviewDot v-if="row.applicable" :section-id="`D3-index-${row.code}`" class="index-review-dot" />
        </template>
      </el-table-column>
      <el-table-column label="适用" width="70" align="center">
        <template #default="{ row }">
          <el-tag :type="row.applicable ? 'success' : 'info'" size="small">
            {{ row.applicable ? '适用' : 'N/A' }}
          </el-tag>
        </template>
      </el-table-column>
    </el-table>

    <details class="methodology-hint">
      <summary>编制提示</summary>
      <p>推荐工作流：D3A 程序表 → D3-1 审定表 → D3-2 明细 → D3-4 分析 → D3-3 调整分录。检查程序 D3-5~D3-7 可与 D3-2 明细交叉核对。</p>
    </details>
  </div>
</template>

<style scoped>
.d3-tab-index { padding: 4px 0; }
.index-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; flex-wrap: wrap; gap: 8px; }
.index-header h3 { margin: 0; font-size: 16px; color: #303133; }
.progress-wrap { min-width: 220px; }
.progress-label { font-size: 12px; color: #606266; display: block; margin-bottom: 4px; }
.index-chip { margin-left: 8px; }
.done-tag { margin-left: 6px; }
.index-review-dot { margin-left: 4px; }
.na-row { color: #909399; }
.methodology-hint {
  margin-top: 16px;
  padding: 10px 12px;
  border-left: 3px solid #409eff;
  background: #ecf5ff;
  border-radius: 0 4px 4px 0;
  font-size: 13px;
  color: #606266;
}
.methodology-hint summary { cursor: pointer; font-weight: 500; color: #409eff; }
</style>
