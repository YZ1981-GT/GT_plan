<template>
  <div class="g6-dir" data-testid="g6-directory">
    <div class="index-header">
      <h3 class="title">G6 底稿目录</h3>
      <GtReviewTrigger section-id="G6-index-directory" />
      <div class="progress-wrap">
        <span>编制进度 {{ completedCount }}/{{ applicableRows.length }}</span>
        <el-progress :percentage="progressPct" :stroke-width="10" />
      </div>
    </div>

    <div v-if="g6aMarks.length" class="g6a-marks">
      <span class="marks-label">G6A 回填：</span>
      <el-tag v-for="m in g6aMarks" :key="m.key" size="small" type="success" effect="plain">{{ m.label }}</el-tag>
    </div>

    <div class="conclusion-board" data-testid="g6-conclusion-board">
      <div class="board-head">
        <strong>跨表结论口径</strong>
        <el-tag size="small" :type="worstTagType">{{ worstLabel }}</el-tag>
        <span class="board-meta">已填 {{ filledCount }}/{{ conclusionSheets.length }}</span>
      </div>
      <div class="board-tags">
        <el-tag
          v-for="c in conclusionSheets"
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
      <p>推荐工作流：G6A 程序表 → G6-1 审定 → G6-2 明细 → G6-6 实际利率法利息 → G6-7 业务模式 → G6-8 SPPI → G6-5 公允价值 → G6-9/10 盘点 → G6-11~14 ECL → G6-15 凭证 → G0 函证 → G6-3 坏账 → G6-4 调整 → 附注披露。</p>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * G6TabDirectory.vue — G6 底稿目录
 *
 * 完全对齐 G8TabDirectory 标准结构：
 * - 进度条（allResponses 驱动）
 * - 跨表结论口径看板（tag 网格 + 最差结论 + 跳转）
 * - G6A 程序表回填标记
 * - 编制提示（details 折叠）
 * - inject('jumpToSection') 跳转
 */
import { computed, inject } from 'vue'
import GtReviewTrigger from '../../GtReviewTrigger.vue'

const props = defineProps<{
  allResponses: Map<string, any>
  availableSheets?: Array<{ sheet_name?: string }>
}>()

// ═══ 底稿清单 ═══
interface IndexRow {
  code: string
  name: string
  applicable: boolean
}

const G6_INDEX_ROWS: IndexRow[] = [
  { code: 'G6A', name: '实质性程序表', applicable: true },
  { code: 'G6-1', name: '审定表', applicable: true },
  { code: 'G6-2', name: '明细表', applicable: true },
  { code: 'G6-3', name: '坏账准备测算表', applicable: true },
  { code: 'G6-4', name: '调整分录汇总', applicable: true },
  { code: 'G6-5', name: '公允价值测试表', applicable: true },
  { code: 'G6-6', name: '实际利率法利息测算', applicable: true },
  { code: 'G6-7', name: '业务模式分析', applicable: true },
  { code: 'G6-8', name: 'SPPI合同现金流测试', applicable: true },
  { code: 'G6-9', name: '有价证券盘点表', applicable: true },
  { code: 'G6-10', name: '盘点倒轧表', applicable: true },
  { code: 'G6-11', name: '三阶段划分检查', applicable: true },
  { code: 'G6-12', name: '减值准备测算表', applicable: true },
  { code: 'G6-13', name: '预期信用损失计量', applicable: true },
  { code: 'G6-14', name: '转回核销检查', applicable: true },
  { code: 'G6-15', name: '凭证检查表', applicable: true },
]

// ═══ 进度 ═══
function isSheetComplete(code: string): boolean {
  if (!props.allResponses || !props.allResponses.entries) return false
  for (const [key, val] of props.allResponses.entries()) {
    if (key.startsWith(code) && (val?.conclusion || val?.remark)) return true
  }
  return false
}

const applicableRows = computed(() => G6_INDEX_ROWS.filter(r => r.applicable))
const completedCount = computed(() => applicableRows.value.filter(r => isSheetComplete(r.code)).length)
const progressPct = computed(() => {
  const total = applicableRows.value.length
  return total > 0 ? Math.round((completedCount.value / total) * 100) : 0
})

// ═══ G6A 回填标记 ═══
const g6aMarks = computed(() => {
  const marks: { key: string; label: string }[] = []
  const get = (id: string) => props.allResponses?.get?.(id)
  if (get('G6A-seq2')?.conclusion === 'completed' || get('G6A-seq2')?.remark) {
    marks.push({ key: 'adjudication', label: '审定表 seq2' })
  }
  if (get('G6A-seq4')?.conclusion === 'completed' || get('G6A-seq4')?.remark) {
    marks.push({ key: 'interest', label: '利息测算 seq4' })
  }
  if (get('G6A-seq6')?.conclusion === 'completed' || get('G6A-seq6')?.remark) {
    marks.push({ key: 'sppi', label: 'SPPI/业务模式 seq6' })
  }
  if (get('G6A-seq8')?.conclusion === 'completed' || get('G6A-seq8')?.remark) {
    marks.push({ key: 'ecl', label: 'ECL减值 seq8' })
  }
  if (get('G6A-seq10')?.conclusion === 'completed' || get('G6A-seq10')?.remark) {
    marks.push({ key: 'voucher', label: '凭证检查 seq10' })
  }
  return marks
})

// ═══ 跨表结论口径看板 ═══
type ConclusionOption = '' | 'A' | 'B' | 'C'

interface ConclusionSheet {
  code: string
  option: ConclusionOption
  filled: boolean
}

const CONCLUSION_KEYS: { code: string; itemId: string }[] = [
  { code: 'G6-1', itemId: 'G6-1-conclusion' },
  { code: 'G6-2', itemId: 'G6-2-conclusion' },
  { code: 'G6-3', itemId: 'G6-3-conclusion' },
  { code: 'G6-5', itemId: 'G6-5-conclusion' },
  { code: 'G6-7', itemId: 'G6-7-conclusion' },
  { code: 'G6-8', itemId: 'G6-8-conclusion' },
  { code: 'G6-11', itemId: 'G6-11-conclusion' },
  { code: 'G6-12', itemId: 'G6-12-conclusion' },
  { code: 'G6-15', itemId: 'G6-15-conclusion' },
]

const conclusionSheets = computed<ConclusionSheet[]>(() => {
  const map = props.allResponses
  return CONCLUSION_KEYS.map(({ code, itemId }) => {
    const raw = map?.get?.(itemId)
    const text = raw?.conclusion || raw?.remark || ''
    const option: ConclusionOption = text.startsWith('A') ? 'A'
      : text.startsWith('B') ? 'B'
        : text.startsWith('C') ? 'C'
          : ''
    return { code, option, filled: !!option }
  })
})

const filledCount = computed(() => conclusionSheets.value.filter(c => c.filled).length)
const hasWarnConclusions = computed(() =>
  conclusionSheets.value.some(c => !c.filled || c.option === 'B' || c.option === 'C'),
)

const worstLabel = computed(() => {
  const opts = conclusionSheets.value.map(c => c.option).filter(Boolean)
  if (opts.includes('C')) return '存在 C'
  if (opts.includes('B')) return '存在 B'
  if (opts.length === conclusionSheets.value.length) return '总体 A'
  return '结论未齐'
})

const worstTagType = computed<'success' | 'warning' | 'danger' | 'info'>(() => {
  const opts = conclusionSheets.value.map(c => c.option).filter(Boolean)
  if (opts.includes('C')) return 'danger'
  if (opts.includes('B')) return 'warning'
  if (opts.length === conclusionSheets.value.length) return 'success'
  return 'info'
})

function optionTagType(opt: ConclusionOption): 'success' | 'warning' | 'danger' | 'info' {
  if (opt === 'A') return 'success'
  if (opt === 'B') return 'warning'
  if (opt === 'C') return 'danger'
  return 'info'
}

// ═══ 跳转 ═══
const jumpToSection = inject<((sheetName: string) => void) | null>('jumpToSection', null)

function resolveSheetLabel(code: string): string {
  if (props.availableSheets?.length) {
    const hit = props.availableSheets.find(s =>
      s.sheet_name && s.sheet_name.includes(code),
    )
    if (hit?.sheet_name) return hit.sheet_name
  }
  return code
}

function goSheet(code: string) {
  if (!jumpToSection) return
  jumpToSection(resolveSheetLabel(code))
}
</script>

<style scoped>
.g6-dir { font-size: var(--wp-font-size, 13px); }
.index-header { display: flex; align-items: center; gap: 12px; margin-bottom: 8px; flex-wrap: wrap; }
.title { margin: 0; }
.progress-wrap { flex: 1; min-width: 200px; }
.g6a-marks { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; margin-bottom: 8px; font-size: 12px; }
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
