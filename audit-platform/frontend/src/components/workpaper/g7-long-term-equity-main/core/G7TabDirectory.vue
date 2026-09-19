<template>
  <div class="g7-dir" data-testid="g7-directory">
    <div class="index-header">
      <h3 class="title">G7 底稿目录</h3>
      <GtReviewTrigger section-id="G7-index-directory" />
      <G7ConsolLinkageEntryDialog
        v-if="projectId"
        :project-id="projectId"
        :year="auditYear"
        :can-edit="canEditCtx"
      />
      <div class="progress-wrap">
        <span>编制进度 {{ completedCount }}/{{ applicableRows.length }}</span>
        <el-progress :percentage="progressPct" :stroke-width="10" />
      </div>
    </div>

    <!-- G7A 回填标记 -->
    <div v-if="g7aMarks.length" class="g7a-marks">
      <span class="marks-label">G7A 回填：</span>
      <el-tag v-for="m in g7aMarks" :key="m.key" size="small" type="success" effect="plain">{{ m.label }}</el-tag>
    </div>

    <!-- 跨表结论口径看板 -->
    <div class="conclusion-board" data-testid="g7-conclusion-board">
      <div class="board-head">
        <strong>跨表结论口径</strong>
        <el-tag size="small" :type="worstTagType">{{ worstLabel }}</el-tag>
        <span class="board-meta">已填 {{ filledConclusionCount }}/{{ conclusionSheets.length }}</span>
      </div>
      <div class="board-tags">
        <el-tag
          v-for="c in conclusionSheets"
          :key="c.code"
          size="small"
          class="concl-tag"
          :type="conclusionTagType(c.option)"
          effect="plain"
          :class="{ clickable: !!jumpToSection }"
          @click="goSheet(c.code)"
        >
          {{ c.code }} {{ c.option || '未填' }}
        </el-tag>
      </div>
      <p v-if="hasWarnConclusions" class="board-hint">存在 B/C 口径或未填结论，请点击标签跳转补全说明。</p>
    </div>

    <!-- 底稿架构 4 阶段泳道（G7 内部 sheet 导航） -->
    <div class="g7-architecture">
      <div class="g7-architecture__header">
        <h4>底稿架构</h4>
        <span class="g7-architecture__hint">点击卡片跳转到对应底稿</span>
      </div>
      <GtBArchitectureTree
        :html-data="architectureHtmlData"
        @navigate="goSheet"
      />
    </div>

    <!-- 编制提示 -->
    <details class="methodology-hint">
      <summary>编制提示</summary>
      <p>推荐工作流：G7A 程序表 → G7-1 审定 → G7-2 明细 → G7-4~6 权益法 → G7-14 核算 → G7-13 成本法 → G7-7~12 子公司 → G7-18 凭证 → G0 函证 → G7-3 调整 → 附注披露。勿重复推送同一差异至 G7-3。</p>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * G7TabDirectory.vue — G7 底稿目录
 *
 * 对齐 G8TabDirectory 的逻辑结构：
 * - 进度条
 * - 跨表结论口径看板（各 sheet 审计结论 A/B/C 汇总 + 跳转）
 * - G7A 程序表回填标记
 * - inject('jumpToSection') 跳转（由 GtWpRenderer / 父主入口 provide）
 */
import { computed, inject } from 'vue'
import GtReviewTrigger from '../../GtReviewTrigger.vue'
import GtBArchitectureTree from '../../GtBArchitectureTree.vue'
import G7ConsolLinkageEntryDialog from './G7ConsolLinkageEntryDialog.vue'
import { useAuditContext } from '@/composables/useAuditContext'

const props = defineProps<{
  allResponses: Map<string, any>
  availableSheets?: Array<{ sheet_name?: string }>
}>()

// 目录页无 projectId prop → 从审计上下文读取（供合并联动入口）
const auditCtx = useAuditContext()
const projectId = computed(() => auditCtx.projectId.value)
const auditYear = computed(() => auditCtx.year.value)
const canEditCtx = computed(() => auditCtx.canEdit.value)

// ═══ 底稿全量清单（用于进度计算） ═══
interface IndexRow {
  code: string
  label: string
  applicable: boolean
}

const G7_INDEX_ROWS: IndexRow[] = [
  { code: 'G7A', label: '长期股权投资实质性程序表', applicable: true },
  { code: 'G7-1', label: '长期股权投资审定表', applicable: true },
  { code: 'G7-2', label: '长期股权投资明细表', applicable: true },
  { code: 'G7-3', label: '调整分录汇总', applicable: true },
  { code: 'G7-4', label: '被投资单位基本信息', applicable: true },
  { code: 'G7-5', label: '被投资单位财务信息', applicable: true },
  { code: 'G7-6', label: '会计政策一致性检查', applicable: true },
  { code: 'G7-7', label: '投资初始确认判断', applicable: true },
  { code: 'G7-8', label: '同一控制下企业合并', applicable: true },
  { code: 'G7-9', label: '非同一控制下企业合并', applicable: true },
  { code: 'G7-10', label: '后续计量检查', applicable: true },
  { code: 'G7-11', label: '处置检查（非一揽子交易）', applicable: true },
  { code: 'G7-12', label: '处置检查（一揽子交易）', applicable: true },
  { code: 'G7-13', label: '成本法后续计量测试', applicable: true },
  { code: 'G7-14', label: '权益法核算测算', applicable: true },
  { code: 'G7-15', label: '内部交易未实现损益', applicable: true },
  { code: 'G7-16', label: '未确认投资损失', applicable: true },
  { code: 'G7-17', label: '长期股权投资减值', applicable: true },
  { code: 'G7-18', label: '凭证检查表', applicable: true },
  { code: 'G7-disc-listed', label: '附注披露信息（上市公司）', applicable: true },
  { code: 'G7-disc-soe', label: '附注披露信息（国企）', applicable: true },
]

// ═══ 进度计算 ═══
const applicableRows = computed(() => G7_INDEX_ROWS.filter(r => r.applicable))

// ═══ 底稿架构树数据（GtBArchitectureTree 需要 navigation_rows） ═══
const architectureHtmlData = computed(() => {
  const navigationRows = G7_INDEX_ROWS.map((row, i) => {
    // 按功能确定 component_type → GtBArchitectureTree 分阶段
    let componentType = 'd-form-table' // 默认→实质性程序
    if (row.code === 'G7A') componentType = 'a-program-console' // → 审计计划
    if (row.code === 'G7-3' || row.code.startsWith('G7-disc')) componentType = 'c-note-table' // → 披露与调整
    return {
      seq: i + 1,
      content: row.label,
      sheet_name: resolveSheetLabel(row.code),
      index_ref: row.code,
      component_type: componentType,
      no_print: false,
    }
  })
  return { navigation_rows: navigationRows }
})

function isSheetComplete(code: string): boolean {
  const map = props.allResponses
  if (!map || map.size === 0) return false
  // 检查常见结论/审计说明 key
  const suffixes = ['-conclusion', '-audit-note', '-note', '-data', '-rows']
  for (const suffix of suffixes) {
    const entry = map.get(`${code}${suffix}`)
    if (entry?.conclusion || entry?.remark) return true
  }
  // 通用前缀匹配
  for (const [key, val] of map.entries()) {
    if (key.startsWith(code) && (val?.conclusion || val?.remark)) return true
  }
  return false
}

const completedCount = computed(() =>
  applicableRows.value.filter(r => isSheetComplete(r.code)).length,
)
const progressPct = computed(() => {
  const total = applicableRows.value.length
  return total > 0 ? Math.round((completedCount.value / total) * 100) : 0
})

// ═══ G7A 回填标记（对齐 G8 g8aMarks） ═══
const g7aMarks = computed(() => {
  const marks: { key: string; label: string }[] = []
  const get = (id: string) => props.allResponses.get(id)
  if (get('G7A-seq2')?.conclusion === 'completed' || get('G7A-seq2')?.remark) {
    marks.push({ key: 'adjudication', label: '审定表 seq2' })
  }
  if (get('G7A-seq3')?.conclusion === 'completed' || get('G7A-seq3')?.remark) {
    marks.push({ key: 'detail', label: '明细表 seq3' })
  }
  if (get('G7A-seq6')?.conclusion === 'completed' || get('G7A-seq6')?.remark) {
    marks.push({ key: 'equity', label: '权益法 seq6' })
  }
  if (get('G7A-seq8')?.conclusion === 'completed' || get('G7A-seq8')?.remark) {
    marks.push({ key: 'fv', label: '公允价值 seq8' })
  }
  if (get('G7A-seq10')?.conclusion === 'completed' || get('G7A-seq10')?.remark) {
    marks.push({ key: 'voucher', label: '凭证检查 seq10' })
  }
  return marks
})

// ═══ 跨表结论看板（对齐 G8 conclusionBoard） ═══
interface ConclusionSheet {
  code: string
  option: string // 'A' | 'B' | 'C' | ''
  filled: boolean
}

const CONCLUSION_KEYS: { code: string; itemId: string }[] = [
  { code: 'G7-1', itemId: 'G7-1-conclusion' },
  { code: 'G7-2', itemId: 'G7-2-conclusion' },
  { code: 'G7-4', itemId: 'G7-4-conclusion' },
  { code: 'G7-5', itemId: 'G7-5-conclusion' },
  { code: 'G7-6', itemId: 'G7-6-conclusion' },
  { code: 'G7-13', itemId: 'G7-13-conclusion' },
  { code: 'G7-14', itemId: 'G7-14-conclusion' },
  { code: 'G7-17', itemId: 'G7-17-conclusion' },
  { code: 'G7-18', itemId: 'G7-18-conclusion' },
]

const conclusionSheets = computed<ConclusionSheet[]>(() => {
  return CONCLUSION_KEYS.map(({ code, itemId }) => {
    const raw = props.allResponses.get(itemId)
    const conclusion = raw?.conclusion || ''
    const option = conclusion.startsWith('A') ? 'A'
      : conclusion.startsWith('B') ? 'B'
        : conclusion.startsWith('C') ? 'C'
          : ''
    return { code, option, filled: !!option }
  })
})

const filledConclusionCount = computed(() => conclusionSheets.value.filter(c => c.filled).length)
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

function conclusionTagType(opt: string): 'success' | 'warning' | 'danger' | 'info' {
  if (opt === 'A') return 'success'
  if (opt === 'B') return 'warning'
  if (opt === 'C') return 'danger'
  return 'info'
}

// ═══ 跳转（对齐 G8：inject jumpToSection + 按 sheet 名模糊匹配） ═══
const jumpToSection = inject<((sheetName: string) => void) | null>('jumpToSection', null)

/** G7 sheet 编码 → 真实 sheet 名映射 */
const G7_SHEET_LABEL_MAP: Record<string, string> = {
  'G7A': '长期股权投资实质性程序表',
  'G7-1': '审定表G7-1',
  'G7-2': '明细表G7-2',
  'G7-3': '调整分录',
  'G7-4': '被投资单位基本信息G7-4',
  'G7-5': '被投资单位财务信息G7-5',
  'G7-6': '会计政策一致性检查G7-6',
  'G7-7': '投资初始确认判断G7-7',
  'G7-8': '同一控制下企业合并G7-8',
  'G7-9': '非同一控制下企业合并G7-9',
  'G7-10': '后续计量检查G7-10',
  'G7-11': '处置检查G7-11',
  'G7-12': '一揽子处置G7-12',
  'G7-13': '成本法后续计量测试G7-13',
  'G7-14': '权益法核算测算G7-14',
  'G7-15': '内部交易未实现损益G7-15',
  'G7-16': '未确认投资损失G7-16',
  'G7-17': '长期股权投资减值G7-17',
  'G7-18': '凭证检查表G7-18',
  'G7-disc-listed': '附注披露信息（上市公司）',
  'G7-disc-soe': '附注披露信息（国企）',
  'G0': 'G0',
}

function resolveSheetLabel(code: string): string {
  // 优先从 availableSheets 精确匹配
  if (props.availableSheets?.length) {
    const hit = props.availableSheets.find(s =>
      s.sheet_name && (s.sheet_name.includes(code) || s.sheet_name === code),
    )
    if (hit?.sheet_name) return hit.sheet_name
  }
  return G7_SHEET_LABEL_MAP[code] || code
}

function goSheet(code: string) {
  if (!jumpToSection) return
  const label = resolveSheetLabel(code)
  jumpToSection(label)
}
</script>

<style scoped>
.g7-dir { font-size: var(--wp-font-size, 13px); }
.index-header { display: flex; align-items: center; gap: 12px; margin-bottom: 8px; flex-wrap: wrap; }
.title { margin: 0; }
.progress-wrap { flex: 1; min-width: 200px; }
.g7a-marks { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; margin-bottom: 8px; font-size: 12px; }
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
.g7-architecture { margin-top: 16px; padding-top: 16px; border-top: 1px solid #e8e4f0; }
.g7-architecture__header { display: flex; align-items: baseline; gap: 12px; margin-bottom: 12px; }
.g7-architecture__header h4 { margin: 0; font-size: 16px; font-weight: 600; color: #303133; }
.g7-architecture__hint { font-size: 12px; color: #909399; }
</style>
