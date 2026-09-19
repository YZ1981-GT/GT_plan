<script setup lang="ts">
/**
 * G12TabDirectory — 对齐 G4TabDirectory 标准结构
 */
import { computed, inject } from 'vue'
import GtReviewTrigger from '../../GtReviewTrigger.vue'
import { G12_CORE_WORKFLOW_HINT } from '../../composables/g12Constants'
import { G12_INDEX_ROWS, resolveG12SheetLabel, isG12SheetComplete } from '../../composables/g12SheetLabels'
import {
  collectG12SheetConclusions,
  summarizeG12Conclusions,
  type G12ConclusionOption,
} from '../../composables/g12Conclusion'

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

const conclusions = computed(() => collectG12SheetConclusions(props.allResponses))
const conclusionSummary = computed(() => summarizeG12Conclusions(conclusions.value))
const hasWarnConclusions = computed(() =>
  conclusions.value.some((c) => !c.filled || c.option === 'B' || c.option === 'C'),
)

const conclusionWorstLabel = computed(() => {
  const w = conclusionSummary.value.worst
  if (w === 'A') return '总体 A'
  if (w === 'B') return '存在 B'
  if (w === 'C') return '存在 C'
  return '结论未齐'
})

const conclusionWorstTagType = computed(() => {
  const w = conclusionSummary.value.worst
  if (w === 'A') return 'success'
  if (w === 'B') return 'warning'
  if (w === 'C') return 'danger'
  return 'info'
})

function optionTagType(opt: G12ConclusionOption): 'success' | 'warning' | 'danger' | 'info' {
  if (opt === 'A') return 'success'
  if (opt === 'B') return 'warning'
  if (opt === 'C') return 'danger'
  return 'info'
}

const jumpToSection = inject<((sheetName: string) => void) | null>('jumpToSection', null)

function goSheet(code: string) {
  if (!jumpToSection) return
  jumpToSection(resolveG12SheetLabel(code, props.availableSheets))
}
</script>

<template>
  <div class="g12-dir" data-testid="g12-directory">
    <div class="index-header">
      <h3 class="title">G12 底稿目录</h3>
      <GtReviewTrigger section-id="G12-index-directory" />
      <div class="progress-wrap">
        <span>编制进度 {{ completedCount }}/{{ applicableRows.length }}</span>
        <el-progress :percentage="progressPct" :stroke-width="10" />
      </div>
    </div>

    <div class="conclusion-board" data-testid="g12-conclusion-board">
      <div class="board-head">
        <strong>跨表结论口径</strong>
        <el-tag size="small" :type="conclusionWorstTagType">{{ conclusionWorstLabel }}</el-tag>
        <span class="board-meta">已填 {{ conclusionSummary.filled }}/{{ conclusionSummary.total }}</span>
      </div>
      <div class="board-tags">
        <el-tag
          v-for="c in conclusions"
          :key="c.code"
          size="small"
          class="concl-tag"
          :type="optionTagType(c.option)"
          effect="plain"
          :class="{ clickable: !!jumpToSection }"
          @click="goSheet(c.code)"
        >
          {{ c.code }} {{ c.option || '未填' }}
        </el-tag>
      </div>
      <p v-if="hasWarnConclusions" class="board-hint">存在 B/C 口径或未填结论，请点击标签跳转补全说明。</p>
    </div>

    <details class="methodology-hint">
      <summary>编制提示</summary>
      <p>{{ G12_CORE_WORKFLOW_HINT }}</p>
      <p>配套可并行：G12A 程序表、G12-2↔G12-4 FV 测试、G12-5 净敞口头寸、G12-6 凭证检查；完成后回到主闭环发布审定数并同步附注。</p>
    </details>
  </div>
</template>

<style scoped>
.g12-dir { font-size: var(--wp-font-size, 13px); }
.index-header { display: flex; align-items: center; gap: 12px; margin-bottom: 8px; flex-wrap: wrap; }
.title { margin: 0; }
.progress-wrap { flex: 1; min-width: 200px; }
.conclusion-board {
  margin-bottom: 12px;
  padding: 10px 12px;
  background: #f5f7fa;
  border-radius: 6px;
  border-left: 3px solid #409eff;
}
.board-head { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; flex-wrap: wrap; }
.board-meta { font-size: 12px; color: #909399; }
.board-tags { display: flex; flex-wrap: wrap; gap: 6px; }
.concl-tag.clickable { cursor: pointer; }
.board-hint { margin: 8px 0 0; font-size: 12px; color: #e6a23c; }
.methodology-hint { margin-top: 12px; font-size: 12px; color: #606266; }
</style>
