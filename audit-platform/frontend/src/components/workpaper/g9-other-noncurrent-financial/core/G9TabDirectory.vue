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
    <div v-if="g9aMarks.length" class="g9a-marks">
      <span class="marks-label">G9A 回填：</span>
      <el-tag v-for="m in g9aMarks" :key="m.key" size="small" type="success" effect="plain">{{ m.label }}</el-tag>
    </div>

    <div class="conclusion-board" data-testid="g9-conclusion-board">
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
      <p>推荐工作流：G9A 程序表 → G9-1 审定 ↔ G9-2 明细（工具种类/指定 → 辅助取数 / 回写审定）→ G9-3 调整 → G9-4 公允价值 → G9-5 L3 调节 → G9-6 凭证 → 附注披露。</p>
      <p>附注披露：按被审计单位监管属性选用上市或国企格式之一（两套表头不同，勿两套重复填全）；可从 G9-1/G9-2 分项带入或导入导出。</p>
    </details>
  </div>
</template>

<script setup lang="ts">
import { computed, inject } from 'vue'
import GtReviewTrigger from '../../GtReviewTrigger.vue'
import { G9_INDEX_ROWS, isG9SheetComplete, jumpToG9Sheet } from '../../composables/g9SheetLabels'
import { G9A_FV_MARK_KEY, G9A_VOUCHER_MARK_KEY } from '../../composables/g9FvCrossHelpers'
import {
  collectG9SheetConclusions,
  summarizeG9Conclusions,
  type G9ConclusionOption,
} from '../../composables/g9Conclusion'

const props = defineProps<{
  allResponses: Map<string, any>
  availableSheets?: Array<{ sheet_name?: string }>
}>()

const applicableRows = computed(() => G9_INDEX_ROWS.filter(r => r.applicable))
const completedCount = computed(() =>
  applicableRows.value.filter(r => isG9SheetComplete(r.code, props.allResponses)).length,
)
const progressPct = computed(() => {
  const total = applicableRows.value.length
  return total > 0 ? Math.round((completedCount.value / total) * 100) : 0
})

const g9aMarks = computed(() => {
  const marks: { key: string; label: string }[] = []
  if (props.allResponses.get(G9A_FV_MARK_KEY)?.conclusion === 'completed') {
    marks.push({ key: 'fv', label: '公允测试/L3 seq8' })
  }
  if (props.allResponses.get(G9A_VOUCHER_MARK_KEY)?.conclusion === 'completed') {
    marks.push({ key: 'voucher', label: '凭证检查' })
  }
  return marks
})

const conclusions = computed(() => collectG9SheetConclusions(props.allResponses))
const conclusionSummary = computed(() => summarizeG9Conclusions(conclusions.value))
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

function optionTagType(opt: G9ConclusionOption): 'success' | 'warning' | 'danger' | 'info' {
  if (opt === 'A') return 'success'
  if (opt === 'B') return 'warning'
  if (opt === 'C') return 'danger'
  return 'info'
}

const jumpToSection = inject<((sheetName: string) => void) | null>('jumpToSection', null)

function goSheet(code: string) {
  jumpToG9Sheet(code, jumpToSection, props.availableSheets)
}
</script>

<style scoped>
.g9-dir { font-size: var(--wp-font-size, 13px); }
.index-header { display: flex; align-items: center; gap: 12px; margin-bottom: 8px; flex-wrap: wrap; }
.title { margin: 0; }
.progress-wrap { flex: 1; min-width: 200px; }
.g9a-marks { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; margin-bottom: 8px; font-size: 12px; }
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
