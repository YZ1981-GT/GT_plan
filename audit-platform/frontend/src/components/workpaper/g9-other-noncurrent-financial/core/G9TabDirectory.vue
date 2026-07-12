<template>
  <div class="g9-dir" data-testid="g9-directory">
    <div class="index-header">
      <h3 class="title">G9 底稿目录</h3>
      <GtReviewTrigger section-id="G9-index-directory" />
      <div class="progress-wrap">
        <span>编制进度 {{ completedCount }}/{{ applicableRows.length }}</span>
        <el-progress :percentage="progressPct" :stroke-width="10" />
      </div>
    </div>
    <el-table :data="indexRows" border size="small" style="font-size:13px">
      <el-table-column label="序号" prop="seq" width="56" align="center" />
      <el-table-column label="索引" prop="code" width="88" />
      <el-table-column label="底稿名称" min-width="220">
        <template #default="{ row }">
          <span>{{ row.name }}</span>
          <GtIndexChip v-if="row.applicable && jumpToSection" :label="row.code" :prevent-navigate="true" :validate="false"
            class="index-chip" @click="jumpToSection(row.sheetLabel)" />
        </template>
      </el-table-column>
    </el-table>
    <details class="methodology-hint">
      <summary>编制提示</summary>
      <p>推荐工作流：G9A 程序表 → G9-1 审定 ↔ G9-2 明细 → G9-3 调整 → G9-4/G9-5 公允价值 → G9-6 凭证 → 附注披露。</p>
    </details>
  </div>
</template>

<script setup lang="ts">
import { computed, inject } from 'vue'
import GtIndexChip from '../../GtIndexChip.vue'
import GtReviewTrigger from '../../GtReviewTrigger.vue'
import { G9_INDEX_ROWS, resolveG9SheetLabel, isG9SheetComplete } from '../../composables/g9SheetLabels'

const props = defineProps<{
  allResponses: Map<string, any>
  availableSheets?: Array<{ sheet_name?: string }>
}>()

const indexRows = computed(() =>
  G9_INDEX_ROWS.map(row => ({
    ...row,
    sheetLabel: resolveG9SheetLabel(row.code, props.availableSheets),
  })),
)
const applicableRows = computed(() => indexRows.value.filter(r => r.applicable))
const completedCount = computed(() =>
  applicableRows.value.filter(r => isG9SheetComplete(r.code, props.allResponses)).length,
)
const progressPct = computed(() => {
  const total = applicableRows.value.length
  return total > 0 ? Math.round((completedCount.value / total) * 100) : 0
})
const jumpToSection = inject<((sheetName: string) => void) | null>('jumpToSection', null)
</script>

<style scoped>
.g9-dir { font-size: var(--wp-font-size, 13px); }
.index-header { display: flex; align-items: center; gap: 12px; margin-bottom: 8px; flex-wrap: wrap; }
.title { margin: 0; }
.progress-wrap { flex: 1; min-width: 200px; }
.index-chip { margin-left: 8px; }
</style>
