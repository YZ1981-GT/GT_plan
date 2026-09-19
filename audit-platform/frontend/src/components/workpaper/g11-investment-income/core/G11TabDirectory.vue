<template>
  <div class="g11-dir" data-testid="g11-directory">
    <div class="index-header">
      <h3 class="title">G11 底稿目录</h3>
      <GtReviewTrigger section-id="G11-index-directory" />
      <div class="progress-wrap">
        <span>编制进度 {{ completedCount }}/{{ applicableRows.length }}</span>
        <el-progress :percentage="progressPct" :stroke-width="10" />
      </div>
    </div>

    <div v-if="g11aMarks.length" class="g11a-marks" data-testid="g11a-procedure-marks">
      <span class="marks-label">G11A 回填：</span>
      <el-tag v-for="m in g11aMarks" :key="m.key" size="small" type="success" effect="plain">{{ m.label }}</el-tag>
    </div>

    <div class="conclusion-board" data-testid="g11-conclusion-board">
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
      <p>推荐工作流：G11A 程序表 → G11-1 审定 ↔ G11-2 明细 → G11-3 调整 → G11-4 收益率 → G11-5 凭证检查 → 附注披露（分项带入）。G7-14 权益法差异可带入 G11-2 或推送 G11-3。</p>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * G11TabDirectory — 对齐 G4TabDirectory 标准结构
 */
import { computed, inject } from 'vue'
import GtReviewTrigger from '../../GtReviewTrigger.vue'
import { G11_INDEX_ROWS, resolveG11SheetLabel, isG11SheetComplete } from '../../composables/g11SheetLabels'
import {
  collectG11AProcedureMarks,
  collectG11SheetConclusions,
  summarizeG11Conclusions,
  type G11ConclusionOption,
} from '../../composables/g11Conclusion'

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

const g11aMarks = computed(() => collectG11AProcedureMarks(props.allResponses))

const conclusions = computed(() => collectG11SheetConclusions(props.allResponses))
const conclusionSummary = computed(() => summarizeG11Conclusions(conclusions.value))
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

function optionTagType(opt: G11ConclusionOption): 'success' | 'warning' | 'danger' | 'info' {
  if (opt === 'A') return 'success'
  if (opt === 'B') return 'warning'
  if (opt === 'C') return 'danger'
  return 'info'
}

const jumpToSection = inject<((sheetName: string) => void) | null>('jumpToSection', null)

function goSheet(code: string) {
  if (!jumpToSection) return
  jumpToSection(resolveG11SheetLabel(code, props.availableSheets))
}
</script>

<style scoped>
.g11-dir { font-size: var(--wp-font-size, 13px); }
.index-header { display: flex; align-items: center; gap: 12px; margin-bottom: 8px; flex-wrap: wrap; }
.title { margin: 0; }
.progress-wrap { flex: 1; min-width: 200px; }
.g11a-marks { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; margin-bottom: 8px; font-size: 12px; }
.marks-label { color: #909399; }
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
