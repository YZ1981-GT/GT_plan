<template>
  <div class="g7-directory" data-testid="g7-directory">
    <!-- 标题 + 进度 -->
    <div class="dir-header">
      <h3 class="title">G7 底稿目录</h3>
      <GtReviewTrigger section-id="G7-index-directory" />
      <span class="progress-label">编制进度 {{ completedCount }}/{{ totalCount }}</span>
    </div>
    <el-progress
      :percentage="progressPct"
      :stroke-width="14"
      color="#7c3aed"
      class="progress-bar"
    />

    <!-- 跨表结论口径看板 -->
    <div class="conclusion-board">
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
          @click="handleJump(c.code)"
        >
          {{ c.code }} {{ c.option || '未填' }}
        </el-tag>
      </div>
      <p v-if="hasWarnConclusions" class="board-hint">
        存在 B/C 口径或未填结论，请点击标签跳转补全。
      </p>
    </div>

    <!-- G7A 回填标记 -->
    <div v-if="g7aMarks.length" class="g7a-marks">
      <span class="marks-label">G7A 回填：</span>
      <el-tag v-for="m in g7aMarks" :key="m.key" size="small" type="success" effect="plain">
        {{ m.label }}
      </el-tag>
    </div>

    <!-- 编制提示 -->
    <p class="workflow-hint">
      推荐工作流：G7A → G7-1 审定 → G7-2 明细 → G7-4~6 权益法 → G7-14 核算 → G7-13 成本法 → G7-7~12 子公司 → G7-18 凭证 → G0 函证 → G7-3 调整 → 附注
    </p>

    <!-- 底稿结构 -->
    <div class="structure-label">底稿结构 <span>共 {{ totalCount }} 张底稿分 {{ groups.length }} 组</span></div>

    <!-- 分组 -->
    <div
      v-for="(group, gi) in groups"
      :key="group.id"
      class="group-section"
    >
      <div class="group-head">
        <span class="group-num">{{ gi + 1 }}</span>
        <span class="group-title">{{ group.title }}</span>
        <span class="group-count">({{ group.items.length }} 张)</span>
      </div>
      <div class="sheet-grid">
        <div
          v-for="item in group.items"
          :key="item.indexCode"
          class="sheet-card"
          @click="handleJump(item.indexCode)"
        >
          <span class="card-check" :class="item.status">
            {{ item.status === 'done' ? '☑' : '☐' }}
          </span>
          <div class="card-body">
            <span class="card-code">{{ item.indexCode }}</span>
            <span class="card-name">{{ item.content }}</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
/**
 * G7TabDirectory.vue — 底稿目录
 *
 * 完全对齐 G8TabDirectory 的逻辑结构：
 * - 紫色进度条
 * - 跨表结论口径看板（各 sheet 审计结论 A/B/C 汇总 + 跳转）
 * - G7A 程序表回填标记
 * - 三段分组：❶科目审定 ❷实质性程序 ❸披露与其他
 */
import { computed } from 'vue'
import GtReviewTrigger from '../../GtReviewTrigger.vue'

const props = defineProps<{
  htmlData: Record<string, any> | null
  wpId: string
  projectId: string
  isReadonly: boolean
}>()

const emit = defineEmits<{ jump: [code: string] }>()

// ═══ 数据模型 ═══
interface DirectoryItem {
  content: string
  indexCode: string
  status: 'done' | 'pending'
}

interface ConclusionSheet {
  code: string
  option: string // 'A' | 'B' | 'C' | ''
  filled: boolean
}

// ═══ allResponses 取数 ═══
const responses = computed(() =>
  props.htmlData?.responses_snapshot || props.htmlData?.allResponses || {},
)

// ═══ 全部底稿 ═══
const allItems = computed<DirectoryItem[]>(() => {
  const r = responses.value
  return [
    { content: '长期股权投资实质性程序表', indexCode: 'G7A', status: resolveStatus('G7A', r) },
    { content: '长期股权投资审定表', indexCode: 'G7-1', status: resolveStatus('G7-1', r) },
    { content: '长期股权投资明细表', indexCode: 'G7-2', status: resolveStatus('G7-2', r) },
    { content: '调整分录汇总', indexCode: 'G7-3', status: resolveStatus('G7-3', r) },
    { content: '附注披露信息（上市公司）', indexCode: 'G7-附注(上市)', status: resolveStatus('G7-附注(上市)', r) },
    { content: '附注披露信息（国企）', indexCode: 'G7-附注(国企)', status: resolveStatus('G7-附注(国企)', r) },
    { content: '被投资单位基本信息', indexCode: 'G7-4', status: resolveStatus('G7-4', r) },
    { content: '被投资单位财务信息', indexCode: 'G7-5', status: resolveStatus('G7-5', r) },
    { content: '会计政策一致性检查', indexCode: 'G7-6', status: resolveStatus('G7-6', r) },
    { content: '成本法后续计量测试', indexCode: 'G7-13', status: resolveStatus('G7-13', r) },
    { content: '权益法核算测算', indexCode: 'G7-14', status: resolveStatus('G7-14', r) },
    { content: '内部交易未实现损益', indexCode: 'G7-15', status: resolveStatus('G7-15', r) },
    { content: '未确认投资损失', indexCode: 'G7-16', status: resolveStatus('G7-16', r) },
    { content: '长期股权投资减值', indexCode: 'G7-17', status: resolveStatus('G7-17', r) },
    { content: '投资初始确认判断', indexCode: 'G7-7', status: resolveStatus('G7-7', r) },
    { content: '同一控制下企业合并', indexCode: 'G7-8', status: resolveStatus('G7-8', r) },
    { content: '非同一控制下企业合并', indexCode: 'G7-9', status: resolveStatus('G7-9', r) },
    { content: '后续计量检查', indexCode: 'G7-10', status: resolveStatus('G7-10', r) },
    { content: '处置检查（非一揽子交易）', indexCode: 'G7-11', status: resolveStatus('G7-11', r) },
    { content: '处置检查（一揽子交易）', indexCode: 'G7-12', status: resolveStatus('G7-12', r) },
    { content: '凭证检查表', indexCode: 'G7-18', status: resolveStatus('G7-18', r) },
    { content: '投资循环函证', indexCode: 'G0', status: resolveStatus('G0', r) },
    { content: '底稿目录', indexCode: 'G7-目录', status: 'done' as const },
  ]
})

// ═══ 三段分组（对齐 G8：科目审定 / 实质性程序 / 披露与其他） ═══
interface SheetGroup { id: string; title: string; items: DirectoryItem[] }

const groups = computed<SheetGroup[]>(() => {
  const items = allItems.value
  const byCode = (code: string) => items.find(i => i.indexCode === code)!
  return [
    {
      id: 'adjudication',
      title: '科目审定',
      items: ['G7A', 'G7-1'].map(byCode).filter(Boolean),
    },
    {
      id: 'substantive',
      title: '实质性程序',
      items: [
        'G7-2', 'G7-4', 'G7-5', 'G7-6',
        'G7-7', 'G7-8', 'G7-9', 'G7-10', 'G7-11', 'G7-12',
        'G7-13', 'G7-14', 'G7-15', 'G7-16', 'G7-17', 'G7-18',
        'G0',
      ].map(byCode).filter(Boolean),
    },
    {
      id: 'disclosure',
      title: '披露与调整',
      items: ['G7-附注(上市)', 'G7-附注(国企)', 'G7-3', 'G7-目录'].map(byCode).filter(Boolean),
    },
  ]
})

// ═══ 编制进度 ═══
const totalCount = computed(() => allItems.value.length)
const completedCount = computed(() => allItems.value.filter(i => i.status === 'done').length)
const progressPct = computed(() => totalCount.value > 0 ? Math.round((completedCount.value / totalCount.value) * 100) : 0)

// ═══ 跨表结论看板（对齐 G8 conclusionBoard） ═══
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
  const r = responses.value
  return CONCLUSION_KEYS.map(({ code, itemId }) => {
    const raw = r[itemId]
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

// ═══ G7A 回填标记（对齐 G8 g8aMarks） ═══
const g7aMarks = computed(() => {
  const r = responses.value
  const marks: { key: string; label: string }[] = []
  // G7A 程序表关键步骤完成标记
  if (r['G7A-seq2']?.conclusion === 'completed' || r['G7A-seq2']?.remark) {
    marks.push({ key: 'adjudication', label: '审定表 seq2' })
  }
  if (r['G7A-seq3']?.conclusion === 'completed' || r['G7A-seq3']?.remark) {
    marks.push({ key: 'detail', label: '明细表 seq3' })
  }
  if (r['G7A-seq6']?.conclusion === 'completed' || r['G7A-seq6']?.remark) {
    marks.push({ key: 'equity', label: '权益法 seq6' })
  }
  if (r['G7A-seq8']?.conclusion === 'completed' || r['G7A-seq8']?.remark) {
    marks.push({ key: 'fv', label: '公允价值 seq8' })
  }
  if (r['G7A-seq10']?.conclusion === 'completed' || r['G7A-seq10']?.remark) {
    marks.push({ key: 'voucher', label: '凭证检查 seq10' })
  }
  return marks
})

// ═══ 状态判断 ═══
function resolveStatus(code: string, r: Record<string, any>): 'done' | 'pending' {
  if (!r || typeof r !== 'object') return 'pending'
  const keys = Object.keys(r)
  const relatedKeys = keys.filter(k => k.startsWith(code) || k.includes(code))
  if (relatedKeys.length > 0) {
    const hasConclusion = relatedKeys.some(k => r[k]?.conclusion || r[k]?.remark)
    if (hasConclusion) return 'done'
  }
  return 'pending'
}

// ═══ 跳转 ═══
function handleJump(code: string) {
  if (code) emit('jump', code)
}
</script>

<style scoped>
.g7-directory {
  padding: 12px 16px;
  font-size: var(--wp-font-size, 13px);
}

/* ═══ Header ═══ */
.dir-header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 6px;
  flex-wrap: wrap;
}
.title { margin: 0; font-size: 15px; font-weight: 700; }
.progress-label {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-left: auto;
}
.progress-bar { margin-bottom: 14px; }
.progress-bar :deep(.el-progress-bar__outer),
.progress-bar :deep(.el-progress-bar__inner) { border-radius: 6px; }

/* ═══ Conclusion Board ═══ */
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
.concl-tag { cursor: pointer; }
.board-hint { margin: 8px 0 0; font-size: 12px; color: #e6a23c; }

/* ═══ G7A Marks ═══ */
.g7a-marks { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; margin-bottom: 10px; font-size: 12px; }
.marks-label { color: #909399; }

/* ═══ Workflow hint ═══ */
.workflow-hint {
  margin: 0 0 14px;
  padding: 6px 10px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  background: var(--el-fill-color-lighter);
  border-radius: 4px;
  line-height: 1.6;
}

/* ═══ Structure label ═══ */
.structure-label {
  margin-bottom: 12px;
  font-size: 13px;
  font-weight: 600;
}
.structure-label span {
  font-weight: 400;
  color: var(--el-text-color-secondary);
  font-size: 12px;
  margin-left: 8px;
}

/* ═══ Group ═══ */
.group-section { margin-bottom: 20px; }
.group-head {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 10px;
}
.group-num {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 20px; height: 20px;
  border-radius: 50%;
  background: var(--el-color-primary);
  color: #fff;
  font-size: 11px;
  font-weight: 700;
}
.group-title { font-size: 14px; font-weight: 600; }
.group-count { font-size: 12px; color: var(--el-text-color-secondary); }

/* ═══ Sheet Grid ═══ */
.sheet-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 8px;
}
@media (max-width: 1100px) { .sheet-grid { grid-template-columns: repeat(3, 1fr); } }
@media (max-width: 768px) { .sheet-grid { grid-template-columns: repeat(2, 1fr); } }

/* ═══ Sheet Card ═══ */
.sheet-card {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 10px 12px;
  background: #fff;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 6px;
  cursor: pointer;
  transition: box-shadow 0.15s, border-color 0.15s;
}
.sheet-card:hover {
  box-shadow: 0 2px 6px rgba(0, 0, 0, 0.06);
  border-color: var(--el-color-primary-light-5);
}
.card-check { font-size: 14px; line-height: 1; flex-shrink: 0; margin-top: 1px; }
.card-check.done { color: var(--el-color-success); }
.card-check.pending { color: var(--el-border-color); }
.card-body { display: flex; flex-direction: column; gap: 1px; min-width: 0; }
.card-code { font-weight: 600; font-size: 13px; color: var(--el-text-color-primary); }
.card-name {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  line-height: 1.3;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
