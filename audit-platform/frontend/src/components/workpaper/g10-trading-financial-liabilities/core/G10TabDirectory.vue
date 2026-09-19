<template>
  <div class="g10-dir" data-testid="g10-directory">
    <div class="index-header">
      <h3 class="title">G10 底稿目录</h3>
      <GtReviewTrigger section-id="G10-index-directory" />
      <div class="progress-wrap">
        <span>编制进度 {{ completedCount }}/{{ applicableRows.length }}</span>
        <el-progress :percentage="progressPct" :stroke-width="10" />
      </div>
    </div>

    <div v-if="g10aMarks.length" class="g10a-marks" data-testid="g10a-procedure-marks">
      <span class="marks-label">G10A 回填：</span>
      <el-tag
        v-for="m in g10aMarks"
        :key="m.key"
        size="small"
        type="success"
        effect="plain"
        class="mark-tag"
        :class="{ clickable: !!jumpToSection }"
        @click="goG10AProcedure(m.programNos)"
      >
        {{ m.label }}
      </el-tag>
    </div>

    <div class="conclusion-board" data-testid="g10-conclusion-board">
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
      <p>推荐工作流：G10A 程序表 → G10-1 审定 ↔ G10-2 明细（回写分项）→ G10-3 调整（按行回写）→ G10-4~8 专项检查 → 附注披露（分项带入）。G10-4~8 异常可推送至 G10-3 并回写 G10-1。</p>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * G10TabDirectory — 对齐 G4TabDirectory 标准结构：
 * 进度条 + G10A 回填标记 + 跨表结论口径 + 折叠编制提示
 */
import { computed, inject } from 'vue'
import GtReviewTrigger from '../../GtReviewTrigger.vue'
import { G10_INDEX_ROWS, resolveG10SheetLabel, isG10SheetComplete, jumpToG10Sheet } from '../../composables/g10SheetLabels'
import { collectG10AProcedureMarks, G10A_PROCEDURE_SHEET } from '../../composables/g10FvCrossHelpers'
import {
  collectG10SheetConclusions,
  summarizeG10Conclusions,
  type G10ConclusionOption,
} from '../../composables/g10Conclusion'
import { dispatchProcedureFocus } from '../../composables/g8CrossHelpers'

const props = defineProps<{
  allResponses: Map<string, any>
  availableSheets?: Array<{ sheet_name?: string }>
}>()

const indexRows = computed(() =>
  G10_INDEX_ROWS.map(row => ({
    ...row,
    sheetLabel: resolveG10SheetLabel(row.code, props.availableSheets),
  })),
)
const applicableRows = computed(() => indexRows.value.filter(r => r.applicable))
const completedCount = computed(() =>
  applicableRows.value.filter(r => isG10SheetComplete(r.code, props.allResponses)).length,
)
const progressPct = computed(() => {
  const total = applicableRows.value.length
  return total > 0 ? Math.round((completedCount.value / total) * 100) : 0
})

const g10aMarks = computed(() => collectG10AProcedureMarks(props.allResponses))

const conclusions = computed(() => collectG10SheetConclusions(props.allResponses))
const conclusionSummary = computed(() => summarizeG10Conclusions(conclusions.value))
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

function optionTagType(opt: G10ConclusionOption): 'success' | 'warning' | 'danger' | 'info' {
  if (opt === 'A') return 'success'
  if (opt === 'B') return 'warning'
  if (opt === 'C') return 'danger'
  return 'info'
}

const jumpToSection = inject<((sheetName: string) => void) | null>('jumpToSection', null)

function goG10AProcedure(programNos: readonly number[]) {
  if (!jumpToSection) return
  jumpToSection('G10A')
  setTimeout(() => {
    dispatchProcedureFocus({
      programNos: [...programNos],
      sheetCode: 'G10A',
      sheetName: G10A_PROCEDURE_SHEET,
    })
  }, 400)
}

function goSheet(code: string) {
  jumpToG10Sheet(code, jumpToSection, props.availableSheets)
}
</script>

<style scoped>
.g10-dir { font-size: var(--wp-font-size, 13px); }
.index-header { display: flex; align-items: center; gap: 12px; margin-bottom: 8px; flex-wrap: wrap; }
.title { margin: 0; }
.progress-wrap { flex: 1; min-width: 200px; }
.g10a-marks { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; margin-bottom: 8px; font-size: 12px; }
.marks-label { color: #909399; }
.mark-tag.clickable { cursor: pointer; }
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
