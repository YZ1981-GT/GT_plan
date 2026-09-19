<template>
  <div class="g8-dir" data-testid="g8-directory">
    <div class="index-header">
      <h3 class="title">G8 底稿目录</h3>
      <GtReviewTrigger section-id="G8-index-directory" />
      <div class="progress-wrap">
        <span>编制进度 {{ completedCount }}/{{ applicableRows.length }}</span>
        <el-progress :percentage="progressPct" :stroke-width="10" />
      </div>
    </div>
    <div v-if="g8aMarks.length" class="g8a-marks">
      <span class="marks-label">G8A 回填：</span>
      <el-tag v-for="m in g8aMarks" :key="m.key" size="small" type="success" effect="plain">{{ m.label }}</el-tag>
    </div>

    <div class="conclusion-board" data-testid="g8-conclusion-board">
      <div class="board-head">
        <strong>跨表结论口径</strong>
        <el-tag size="small" :type="worstTagType">{{ worstLabel }}</el-tag>
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
      <p>推荐工作流：G8A 程序表 → G8-2 明细 → G8-1「从明细带入未审」↔ TB → G8-4 公允测试（Level3 可查阅「参考中证协」；差异可推送 G8-3）→ G8-3 调整回写 G8-1 → G8-5 指定适当性 → G8-6 凭证 → 附注披露。勿重复推送同一公允差异至 G8-3。</p>
    </details>
  </div>
</template>

<script setup lang="ts">
import { computed, inject } from 'vue'
import GtReviewTrigger from '../../GtReviewTrigger.vue'
import { G8_INDEX_ROWS, resolveG8SheetLabel, isG8SheetComplete } from '../../composables/g8SheetLabels'
import { jumpToG8Sheet, G8A_DESIGNATION_MARK_KEY, G8A_FV_MARK_KEY, G8A_VOUCHER_MARK_KEY } from '../../composables/g8CrossHelpers'
import {
  collectG8SheetConclusions,
  summarizeG8Conclusions,
  type G8ConclusionOption,
} from '../../composables/g8Conclusion'

const props = defineProps<{
  allResponses: Map<string, any>
  availableSheets?: Array<{ sheet_name?: string }>
}>()

const indexRows = computed(() =>
  G8_INDEX_ROWS.map(row => ({
    ...row,
    sheetLabel: resolveG8SheetLabel(row.code, props.availableSheets),
    done: isG8SheetComplete(row.code, props.allResponses),
  })),
)
const applicableRows = computed(() => indexRows.value.filter(r => r.applicable))
const completedCount = computed(() =>
  applicableRows.value.filter(r => r.done).length,
)
const progressPct = computed(() => {
  const total = applicableRows.value.length
  return total > 0 ? Math.round((completedCount.value / total) * 100) : 0
})

const g8aMarks = computed(() => {
  const marks: { key: string; label: string }[] = []
  if (props.allResponses.get(G8A_FV_MARK_KEY)?.conclusion === 'completed') {
    marks.push({ key: 'fv', label: '公允测试 seq3/10' })
  }
  if (props.allResponses.get(G8A_DESIGNATION_MARK_KEY)?.conclusion === 'completed') {
    marks.push({ key: 'desig', label: '指定适当性 seq2' })
  }
  if (props.allResponses.get(G8A_VOUCHER_MARK_KEY)?.conclusion === 'completed') {
    marks.push({ key: 'voucher', label: '凭证检查 seq6/7/12' })
  }
  return marks
})

const conclusions = computed(() => collectG8SheetConclusions(props.allResponses))
const conclusionSummary = computed(() => summarizeG8Conclusions(conclusions.value))
const hasWarnConclusions = computed(() =>
  conclusions.value.some((c) => !c.filled || c.option === 'B' || c.option === 'C'),
)

const worstLabel = computed(() => {
  const w = conclusionSummary.value.worst
  if (w === 'A') return '总体 A'
  if (w === 'B') return '存在 B'
  if (w === 'C') return '存在 C'
  return '结论未齐'
})

const worstTagType = computed(() => {
  const w = conclusionSummary.value.worst
  if (w === 'A') return 'success'
  if (w === 'B') return 'warning'
  if (w === 'C') return 'danger'
  return 'info'
})

function optionTagType(opt: G8ConclusionOption): 'success' | 'warning' | 'danger' | 'info' {
  if (opt === 'A') return 'success'
  if (opt === 'B') return 'warning'
  if (opt === 'C') return 'danger'
  return 'info'
}

const jumpToSection = inject<((sheetName: string) => void) | null>('jumpToSection', null)

function goSheet(code: string) {
  jumpToG8Sheet(code, jumpToSection, props.availableSheets)
}
</script>

<style scoped>
.g8-dir { font-size: var(--wp-font-size, 13px); }
.index-header { display: flex; align-items: center; gap: 12px; margin-bottom: 8px; flex-wrap: wrap; }
.title { margin: 0; }
.progress-wrap { flex: 1; min-width: 200px; }
.g8a-marks { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; margin-bottom: 8px; font-size: 12px; }
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
