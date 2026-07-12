<script setup lang="ts">
import { computed, inject } from 'vue'
import GtIndexChip from '../../GtIndexChip.vue'
import GtReviewDot from '../../GtReviewDot.vue'
import GtReviewTrigger from '../../GtReviewTrigger.vue'
import { G12_INDEX_ROWS, resolveG12SheetLabel, isG12SheetComplete } from '../../composables/g12SheetLabels'

const props = defineProps<{
  allResponses: Map<string, any>
  availableSheets?: Array<{ sheet_name?: string }>
}>()

const indexRows = computed(() =>
  G12_INDEX_ROWS.map(row => ({
    ...row,
    sheetLabel: resolveG12SheetLabel(row.code, props.availableSheets),
  })),
)

const applicableRows = computed(() => indexRows.value.filter(r => r.applicable))

const completedCount = computed(() =>
  applicableRows.value.filter(r => isG12SheetComplete(r.code, props.allResponses)).length,
)

const progressPct = computed(() => {
  const total = applicableRows.value.length
  return total > 0 ? Math.round((completedCount.value / total) * 100) : 0
})

const jumpToSection = inject<((sheetName: string) => void) | null>('jumpToSection', null)
</script>

<template>
  <div class="g12-dir" data-testid="g12-directory">
    <div class="index-header">
      <h3 class="title">G12 底稿目录</h3>
      <GtReviewTrigger section-id="G12-index-directory" />
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
          <span class="index-chip-wrap" :data-testid="`g12-dir-chip-${row.code}`">
            <GtIndexChip
              v-if="row.applicable && jumpToSection"
              :label="row.code"
              :prevent-navigate="true"
              :validate="false"
              class="index-chip"
              @click="jumpToSection(row.sheetLabel)"
            />
          </span>
          <el-tag
            v-if="row.applicable && isG12SheetComplete(row.code, allResponses)"
            type="success"
            size="small"
            class="done-tag"
          >已编制</el-tag>
          <GtReviewDot v-if="row.applicable" :section-id="`G12-index-${row.code}`" class="index-review-dot" />
        </template>
      </el-table-column>
    </el-table>

    <details class="methodology-hint">
      <summary>编制提示</summary>
      <p>推荐工作流：G12A 程序表 → G12-1 审定 → G12-2 套期明细 ↔ G12-4 FV测试 → G12-5 净敞口检查 → G12-6 凭证检查 → 附注披露。</p>
    </details>
  </div>
</template>

<style scoped>
.g12-dir { padding: 12px; font-size: var(--wp-font-size, 13px); }
.index-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; flex-wrap: wrap; gap: 8px; }
.title { margin: 0; font-size: 15px; font-weight: 600; }
.progress-wrap { min-width: 220px; }
.progress-label { font-size: 12px; color: #606266; display: block; margin-bottom: 4px; }
.index-chip { margin-left: 8px; }
.done-tag { margin-left: 6px; }
.index-review-dot { margin-left: 4px; }
.methodology-hint {
  margin-top: 16px; padding: 10px 12px; border-left: 3px solid #409eff;
  background: #ecf5ff; border-radius: 0 4px 4px 0; font-size: var(--wp-font-size, 13px); color: #606266;
}
.methodology-hint summary { cursor: pointer; font-weight: 500; color: #409eff; }
</style>
