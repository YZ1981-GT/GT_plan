<template>
  <div class="g11-dir" data-testid="g11-directory">
    <div class="index-header">
      <h3 class="title">G11 底稿目录</h3>
      <GtReviewTrigger section-id="G11-index-directory" />
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
          <el-tag v-if="row.applicable && isG11SheetComplete(row.code, allResponses)" type="success" size="small" class="done-tag">已编制</el-tag>
        </template>
      </el-table-column>
    </el-table>
    <details class="methodology-hint">
      <summary>编制提示</summary>
      <p>推荐工作流：G11A 程序表 → G11-1 审定 ↔ G11-2 明细 → G11-3 调整 → G11-4 收益率分析 → G11-5 凭证检查 → 附注披露。</p>
    </details>
  </div>
</template>

<script setup lang="ts">
import { computed, inject } from 'vue'
import GtIndexChip from '../../GtIndexChip.vue'
import GtReviewTrigger from '../../GtReviewTrigger.vue'
import { G11_INDEX_ROWS, resolveG11SheetLabel, isG11SheetComplete } from '../../composables/g11SheetLabels'

const props = defineProps<{
  allResponses: Map<string, any>
  availableSheets?: Array<{ sheet_name?: string }>
}>()

const indexRows = computed(() =>
  G11_INDEX_ROWS.map(row => ({
    ...row,
    sheetLabel: resolveG11SheetLabel(row.code, props.availableSheets),
  })),
)
const applicableRows = computed(() => indexRows.value.filter(r => r.applicable))
const completedCount = computed(() =>
  applicableRows.value.filter(r => isG11SheetComplete(r.code, props.allResponses)).length,
)
const progressPct = computed(() => {
  const total = applicableRows.value.length
  return total > 0 ? Math.round((completedCount.value / total) * 100) : 0
})
const jumpToSection = inject<((sheetName: string) => void) | null>('jumpToSection', null)
</script>

<style scoped>
.g11-dir { font-size: 13px; }
.index-header { display: flex; align-items: center; gap: 12px; margin-bottom: 12px; flex-wrap: wrap; }
.title { margin: 0; font-size: 15px; }
.progress-wrap { flex: 1; min-width: 200px; }
.progress-label { font-size: 12px; color: #909399; display: block; margin-bottom: 4px; }
.index-chip { margin-left: 8px; }
.done-tag { margin-left: 6px; }
.methodology-hint { margin-top: 12px; font-size: 12px; color: #606266; }
</style>
