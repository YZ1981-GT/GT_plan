<template>
  <div class="h10-dir" data-testid="h10-directory">
    <div class="index-header">
      <h3 class="title">H10 底稿目录</h3>
      <GtReviewTrigger section-id="H10-index-directory" />
      <div class="progress-wrap">
        <span class="progress-label">编制进度 {{ completedCount }}/{{ applicableRows.length }}</span>
        <el-progress :percentage="progressPct" :stroke-width="10" />
      </div>
    </div>
    <el-table :data="indexRows" border size="small" style="font-size:13px">
      <el-table-column label="序号" prop="seq" width="56" align="center" />
      <el-table-column label="分组" prop="group" width="72" />
      <el-table-column label="索引" prop="code" width="88" />
      <el-table-column label="底稿名称" min-width="220">
        <template #default="{ row }">
          <span>{{ row.name }}</span>
          <GtIndexChip v-if="row.applicable && jumpToSection" :label="row.code" :prevent-navigate="true" :validate="false"
            class="index-chip" @click="jumpToSection(row.sheetLabel)" />
          <el-tag v-if="row.applicable && isH10SheetComplete(row.code, allResponses)" type="success" size="small" class="done-tag">已编制</el-tag>
        </template>
      </el-table-column>
    </el-table>

    <el-card shadow="never" class="trace-card">
      <template #header>来源追溯链状态（H1~H8 + H6）</template>
      <el-table :data="sourceTrace" border size="small" style="font-size:12px">
        <el-table-column label="来源底稿" prop="label" min-width="180" />
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag size="small" :type="row.status === 'done' ? 'success' : row.status === 'pending' ? 'warning' : 'info'">
              {{ row.status === 'done' ? '已链接' : row.status === 'pending' ? '待确认' : '未编制' }}
            </el-tag>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <details class="methodology-hint">
      <summary>编制提示</summary>
      <p>推荐工作流：H10A 程序表 → H10-1 审定（6115 发生额）↔ H10-2 明细 → H10-3 调整 → H10-4 检查 → 附注披露。H6 清理结转通过 EventBus 自动汇入明细。</p>
    </details>
  </div>
</template>

<script setup lang="ts">
import { computed, inject } from 'vue'
import GtIndexChip from '../../GtIndexChip.vue'
import GtReviewTrigger from '../../GtReviewTrigger.vue'
import {
  H10_INDEX_ROWS,
  resolveH10SheetLabel,
  isH10SheetComplete,
  getH10SourceTraceStatus,
} from '../../composables/h10SheetLabels'

const props = defineProps<{
  allResponses: Map<string, any>
  availableSheets?: Array<{ sheet_name?: string }>
}>()

const indexRows = computed(() =>
  H10_INDEX_ROWS.map(row => ({
    ...row,
    sheetLabel: resolveH10SheetLabel(row.code, props.availableSheets),
  })),
)
const applicableRows = computed(() => indexRows.value.filter(r => r.applicable))
const completedCount = computed(() =>
  applicableRows.value.filter(r => isH10SheetComplete(r.code, props.allResponses)).length,
)
const progressPct = computed(() => {
  const total = applicableRows.value.length
  return total > 0 ? Math.round((completedCount.value / total) * 100) : 0
})
const sourceTrace = computed(() => getH10SourceTraceStatus(props.allResponses))
const jumpToSection = inject<((sheetName: string) => void) | null>('jumpToSection', null)
</script>

<style scoped>
.h10-dir { font-size: var(--wp-font-size, 13px); }
.index-header { display: flex; align-items: center; gap: 12px; margin-bottom: 12px; flex-wrap: wrap; }
.title { margin: 0; font-size: 15px; }
.progress-wrap { flex: 1; min-width: 200px; }
.progress-label { font-size: 12px; color: #909399; display: block; margin-bottom: 4px; }
.index-chip { margin-left: 8px; }
.done-tag { margin-left: 6px; }
.trace-card { margin-top: 12px; }
.methodology-hint { margin-top: 12px; font-size: 12px; color: #606266; }
</style>
