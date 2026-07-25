<script setup lang="ts">
/**
 * D1TabIndex — 应收票据底稿目录（E1 标准「加法式增强」）
 *
 * 保留现有 NAV_ROWS + GtBArchitectureTree + inject('jumpToSection') 导航机制不动，
 * 在其上补齐 E1 标准缺失区块：目录卡头部(复核+编制/使用手册)、跨表结论口径看板、
 * 本循环底稿目录 grid。
 */
import { computed, inject, ref, onMounted, defineAsyncComponent } from 'vue'
import { useRouter } from 'vue-router'
import GtBArchitectureTree from '../GtBArchitectureTree.vue'
import GtReviewTrigger from '../GtReviewTrigger.vue'
import { loadCycleWorkpaperCards, type CycleWpCard } from '@/services/cycleDirectory'

const D1PreparationHandbookDialog = defineAsyncComponent(() => import('./D1PreparationHandbookDialog.vue'))

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
  availableSheets?: Array<{ sheet_name?: string }>
}>()

interface NavRow {
  content: string
  index_ref: string
  component_type: string
  progressKeys: string[]
}

/**
 * D1 各 sheet → navigation_rows
 * component_type 决定 GtBArchitectureTree 阶段归类：
 * - a-program-console → 审计计划
 * - d-form-table (审定表) → 科目审定
 * - c-note-table → 披露与调整
 * - 其余 → 实质性程序
 */
const NAV_ROWS: NavRow[] = [
  // 审计计划
  { content: '应收票据实质性程序表 D1A', index_ref: 'D1A', component_type: 'a-program-console', progressKeys: [] },
  // 科目审定
  { content: '审定表D1-1', index_ref: 'D1-1', component_type: 'd-form-table', progressKeys: ['D1-adj-'] },
  // 实质性程序
  { content: '按类别明细表D1-2', index_ref: 'D1-2', component_type: 'd-form-table-detail', progressKeys: ['D1-cat-rows'] },
  { content: '按客户明细表D1-3', index_ref: 'D1-3', component_type: 'd-form-table-detail', progressKeys: ['D1-cust-rows'] },
  { content: '坏账准备D1-4', index_ref: 'D1-4', component_type: 'd-form-table-detail', progressKeys: ['D1-bd-individual-rows', 'D1-bd-portfolio-rows'] },
  { content: '调整分录D1-5', index_ref: 'D1-5', component_type: 'd-form-table-detail', progressKeys: ['D1-entry-rows'] },
  { content: '基准日后应收款项回收D1-6', index_ref: 'D1-6', component_type: 'd-form-table-detail', progressKeys: ['D1-bm-basis-rows'] },
  { content: '票据备查簿核对D1-7', index_ref: 'D1-7', component_type: 'd-form-table-detail', progressKeys: ['D1-memo-rows'] },
  { content: '贴现背书明细D1-8', index_ref: 'D1-8', component_type: 'd-form-table-detail', progressKeys: ['D1-endorse-discount-rows', 'D1-endorse-transfer-rows'] },
  { content: '利息计算检查D1-9', index_ref: 'D1-9', component_type: 'd-form-table-detail', progressKeys: ['D1-interest-rows'] },
  { content: '票据监盘D1-10', index_ref: 'D1-10', component_type: 'd-form-table-detail', progressKeys: ['D1-inventory-rows'] },
  { content: '关联方D1-11', index_ref: 'D1-11', component_type: 'd-form-table-detail', progressKeys: ['D1-rp-rows'] },
  { content: '质押检查D1-12', index_ref: 'D1-12', component_type: 'd-form-table-detail', progressKeys: ['D1-pledge-rows'] },
  { content: '抽凭检查D1-13', index_ref: 'D1-13', component_type: 'd-form-table-detail', progressKeys: ['D1-sampling-vouching-rows', 'D1-sampling-specific-samples'] },
  { content: '会计政策检查D1-14', index_ref: 'D1-14', component_type: 'd-form-table-detail', progressKeys: ['D1-policy-paragraphs'] },
  { content: 'ECL减值模型D1-15', index_ref: 'D1-15', component_type: 'd-form-table-detail', progressKeys: ['D1-ecl-portfolio-rows', 'D1-ecl-individual-rows'] },
  { content: '核销与转回D1-16', index_ref: 'D1-16', component_type: 'd-form-table-detail', progressKeys: ['D1-writeoff-reversal-rows', 'D1-writeoff-writeoff-rows'] },
  // 披露与调整
  { content: '附注披露信息（上市公司）', index_ref: '附注上市', component_type: 'c-note-table', progressKeys: ['D1-disc-'] },
  { content: '附注披露信息（国有企业）', index_ref: '附注国企', component_type: 'c-note-table', progressKeys: ['D1-disc-'] },
]

const jumpToSection = inject<((sheetName: string) => void) | null>('jumpToSection', null)

function rowStatus(row: NavRow): string {
  if (row.progressKeys.length === 0) return ''
  const map = props.allResponses
  if (!map || map.size === 0) return 'pending'
  const keys = [...map.keys()]
  const hasData = row.progressKeys.some(pk => {
    if (pk.endsWith('-')) return keys.some(k => k.startsWith(pk))
    return map.has(pk) || keys.some(k => k.startsWith(pk))
  })
  return hasData ? 'completed' : 'pending'
}

/** 喂给 GtBArchitectureTree 的 htmlData.navigation_rows */
const archHtmlData = computed(() => ({
  navigation_rows: NAV_ROWS.map((r, i) => ({
    seq: i + 1,
    content: r.content,
    sheet_name: r.content,
    index_ref: r.index_ref,
    component_type: r.component_type,
    status: rowStatus(r),
  })),
}))

// ─── 编制进度 ─────────────────────────────────────────────────────────
const progressRows = computed(() => NAV_ROWS.filter(r => r.progressKeys.length > 0))
const completedCount = computed(() => progressRows.value.filter(r => rowStatus(r) === 'completed').length)
const applicableCount = computed(() => progressRows.value.length)
const progressPercent = computed(() =>
  applicableCount.value === 0 ? 0 : Math.round((completedCount.value / applicableCount.value) * 100),
)

function handleNavigate(sheetName: string) {
  if (jumpToSection && sheetName) jumpToSection(sheetName)
}

// ─── 编制/使用手册弹窗 ─────────────────────────────────────────────────
const handbookVisible = ref(false)
const handbookTab = ref<'preparation' | 'usage'>('preparation')
function openHandbook(tab: 'preparation' | 'usage') {
  handbookTab.value = tab
  handbookVisible.value = true
}

// ─── 跨表结论口径看板（审定/明细/检查类数据承载表，排除程序表/附注/调整分录）───
/** includes(`${code}-`) 兼容不同存储前缀深度，尾部连字符保证边界安全。 */
function isConclusionFilled(code: string): boolean {
  const map = props.allResponses instanceof Map ? props.allResponses : (props.allResponses as any)?.value ?? new Map()
  if (!map?.size) return false
  const token = `${code}-`
  for (const [key, val] of map.entries()) {
    if (!key.includes(token)) continue
    if (!/conclusion|audit-note|note/i.test(key)) continue
    const text = (val?.remark ?? val?.conclusion ?? '') as string
    if (typeof text === 'string' && text.trim().length > 0) return true
  }
  return false
}

const CONCLUSION_RE = /^D1-\d+$/
const conclusionSheets = computed(() =>
  NAV_ROWS
    .filter(r => CONCLUSION_RE.test(r.index_ref) && !/调整分录/.test(r.content))
    .map(r => ({ code: r.index_ref, sheetKey: r.content, filled: isConclusionFilled(r.index_ref) })),
)
const conclusionFilledCount = computed(() => conclusionSheets.value.filter(c => c.filled).length)
const conclusionHasUnfilled = computed(() => conclusionSheets.value.some(c => !c.filled))
const conclusionWorstLabel = computed(() => {
  if (conclusionFilledCount.value === 0) return '结论未填'
  if (conclusionHasUnfilled.value) return `结论未齐 ${conclusionSheets.value.length - conclusionFilledCount.value} 项`
  return '总体已齐'
})
const conclusionWorstType = computed<'success' | 'warning' | 'info'>(() => {
  if (conclusionFilledCount.value === 0) return 'info'
  if (conclusionHasUnfilled.value) return 'warning'
  return 'success'
})

// ─── 本循环底稿目录（D 循环其他科目，跨底稿跳转）───────────────────────
const router = useRouter()
const cycleWorkpapers = ref<CycleWpCard[]>([])
async function loadCycleWorkpapers(): Promise<void> {
  cycleWorkpapers.value = await loadCycleWorkpaperCards(props.projectId, 'D', props.wpId)
}
function onCycleCardClick(wp: CycleWpCard): void {
  if (!wp.wp_id || wp.is_current || !props.projectId) return
  router.push({ name: 'WorkpaperEditor', params: { projectId: props.projectId, wpId: wp.wp_id } })
}
onMounted(loadCycleWorkpapers)
</script>

<template>
  <div class="d1-tab-index">
    <!-- ═══ 目录卡（标题 + 复核 + 编制/使用手册 + 进度 → 跨表结论口径 → 编制提示） ═══ -->
    <div class="d1-dir">
      <div class="index-header">
        <h3 class="title">D1 底稿目录</h3>
        <GtReviewTrigger section-id="D1-index-directory" />
        <div class="handbook-btns">
          <el-button size="small" type="primary" plain @click="openHandbook('preparation')">📖 编制手册</el-button>
          <el-button size="small" @click="openHandbook('usage')">使用手册</el-button>
        </div>
        <div class="progress-wrap">
          <span class="progress-label">编制进度 {{ completedCount }}/{{ applicableCount }} ({{ progressPercent }}%)</span>
          <el-progress :percentage="progressPercent" :stroke-width="10" />
        </div>
      </div>

      <D1PreparationHandbookDialog v-model="handbookVisible" :initial-tab="handbookTab" />

      <div class="conclusion-board">
        <div class="board-head">
          <strong>跨表结论口径</strong>
          <el-tag size="small" :type="conclusionWorstType">{{ conclusionWorstLabel }}</el-tag>
          <span class="board-meta">已填 {{ conclusionFilledCount }}/{{ conclusionSheets.length }}</span>
        </div>
        <div class="board-tags">
          <el-tag
            v-for="c in conclusionSheets"
            :key="c.code"
            size="small"
            class="concl-tag clickable"
            :type="c.filled ? 'success' : 'info'"
            effect="plain"
            @click="handleNavigate(c.sheetKey)"
          >
            {{ c.code }} {{ c.filled ? '已填' : '未填' }}
          </el-tag>
        </div>
        <p v-if="conclusionHasUnfilled" class="board-hint">存在未填审计结论，请点击标签跳转补全审计说明与结论。</p>
      </div>

      <details class="methodology-hint">
        <summary>编制提示</summary>
        <p>推荐工作流：D1A 程序表 → D1-1 审定表 → D1-2/D1-3 明细 → D1-4 坏账 → D1-14/D1-15 ECL → D1-5 调整分录。监盘核查组 D1-10~D1-13 可与 D1-1 审定表交叉核对。</p>
      </details>
    </div>

    <!-- ═══ 底稿架构（4 阶段泳道卡片，NAV_ROWS 不动） ═══ -->
    <div class="d1-arch">
      <div class="arch-header">
        <h4 class="arch-title">D1 应收票据底稿架构</h4>
        <span class="arch-hint">点击卡片可跳转至对应底稿</span>
      </div>
      <GtBArchitectureTree
        :active-sheet="''"
        :html-data="archHtmlData"
        @navigate="handleNavigate"
      />
    </div>

    <!-- ═══ 本循环底稿目录（D 循环其他科目，可跳转） ═══ -->
    <div v-if="cycleWorkpapers.length" class="d1-cycle">
      <div class="cycle-header">
        <h4 class="cycle-title">本循环底稿目录</h4>
        <span class="cycle-hint">点击可跳转至同循环其他底稿（灰色表示尚未生成）</span>
      </div>
      <div class="cycle-grid">
        <div
          v-for="wp in cycleWorkpapers"
          :key="wp.wp_code"
          class="cycle-card"
          :class="{ 'is-current': wp.is_current, 'is-disabled': !wp.wp_id }"
          @click="onCycleCardClick(wp)"
        >
          <div class="cycle-card-top">
            <span class="cycle-code">{{ wp.wp_code }}</span>
            <el-tag v-if="wp.is_current" size="small" effect="plain" class="cycle-current-tag">当前</el-tag>
          </div>
          <span class="cycle-name" :title="wp.wp_name">{{ wp.wp_name }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.d1-tab-index { padding: 12px; font-size: var(--wp-font-size, 13px); }

/* ─── 目录卡 ─── */
.d1-dir { margin-bottom: 20px; }
.index-header { display: flex; align-items: center; gap: 12px; margin-bottom: 8px; flex-wrap: wrap; }
.title { margin: 0; font-size: 16px; font-weight: 600; color: #303133; }
.handbook-btns { display: flex; gap: 6px; }
.progress-wrap { flex: 1; min-width: 220px; }
.progress-label { font-size: 12px; color: #606266; display: block; margin-bottom: 4px; }
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
.methodology-hint {
  margin-top: 12px;
  padding: 10px 12px;
  border-left: 3px solid #409eff;
  background: #ecf5ff;
  border-radius: 0 4px 4px 0;
  font-size: var(--wp-font-size, 13px);
  color: #606266;
}
.methodology-hint summary { cursor: pointer; font-weight: 500; color: #409eff; }

/* ─── 底稿架构 ─── */
.d1-arch { margin-top: 16px; }
.arch-header { display: flex; align-items: baseline; gap: 12px; margin-bottom: 12px; }
.arch-title { margin: 0; font-size: 16px; font-weight: 600; color: #303133; }
.arch-hint { font-size: 12px; color: #909399; }

/* ─── 本循环底稿目录 ─── */
.d1-cycle { margin-top: 28px; }
.cycle-header { display: flex; align-items: baseline; gap: 12px; margin-bottom: 12px; }
.cycle-title { margin: 0; font-size: 16px; font-weight: 600; color: #303133; }
.cycle-hint { font-size: 12px; color: #909399; }
.cycle-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: 10px; }
.cycle-card {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 10px 12px;
  border: 1px solid var(--gt-color-border-purple, #e8e4f0);
  border-radius: 8px;
  background: #fff;
  cursor: pointer;
  transition: all 0.2s;
}
.cycle-card:hover { border-color: var(--gt-color-primary, #4b2d77); box-shadow: 0 2px 8px rgba(75, 45, 119, 0.12); transform: translateY(-2px); }
.cycle-card.is-current { border-color: var(--gt-color-primary, #4b2d77); background: var(--gt-color-primary-bg, #f4f0fa); box-shadow: 0 0 0 1px var(--gt-color-primary, #4b2d77); cursor: default; }
.cycle-card.is-disabled { opacity: 0.5; cursor: not-allowed; }
.cycle-card.is-disabled:hover { border-color: var(--gt-color-border-purple, #e8e4f0); box-shadow: none; transform: none; }
.cycle-card-top { display: flex; align-items: center; gap: 6px; }
.cycle-code { font-size: var(--wp-font-size, 13px); font-weight: 700; color: var(--gt-color-primary, #4b2d77); }
.cycle-current-tag { margin-left: auto; }
.cycle-name { font-size: var(--wp-font-size, 13px); line-height: 1.4; color: #303133; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
</style>
