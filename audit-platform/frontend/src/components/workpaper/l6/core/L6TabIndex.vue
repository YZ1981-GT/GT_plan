<template>
  <div class="l6-tab-index">
    <!-- 编制信息由页面级头部统一渲染，此处不重复 -->

    <!-- ═══ 目录卡（标题 + 复核 + 编制/使用手册 + 进度条 → 跨表结论口径 → 编制提示） ═══ -->
    <div class="l6-dir">
      <div class="index-header">
        <h3 class="title">L6 专项应付款底稿目录</h3>
        <GtReviewTrigger section-id="L6-index-directory" />
        <div class="handbook-btns">
          <el-button size="small" type="primary" plain @click="openHandbook('preparation')">📖 编制手册</el-button>
          <el-button size="small" @click="openHandbook('usage')">使用手册</el-button>
        </div>
        <div class="progress-wrap">
          <span>编制进度 {{ completedCount }}/{{ totalCount }}</span>
          <el-progress :percentage="progressPercent" :stroke-width="10" />
        </div>
      </div>

      <L6PreparationHandbookDialog v-model="handbookVisible" :initial-tab="handbookTab" />

      <div class="conclusion-board" data-testid="l6-conclusion-board">
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
            @click="emit('navigate', c.sheetKey)"
          >
            {{ c.code }} {{ c.filled ? '已填' : '未填' }}
          </el-tag>
        </div>
        <p v-if="conclusionHasUnfilled" class="board-hint">存在未填审计结论，请点击标签跳转补全审计说明与结论。</p>
      </div>

      <details class="methodology-hint">
        <summary>编制提示</summary>
        <ul>
          <li>专项应付款为<strong>负债类贷方科目</strong>（2601）：期末 = 期初 + 贷方（拨入）− 借方（使用/结转）</li>
          <li>审定表按<strong>专项项目</strong>分类，双期列示（期初/期末各未审、账项调整、重分类、审定）；项目行为<strong>动态行</strong>，从 L6-2 明细带入、可增删</li>
          <li>专项应付款<strong>无"减一年内到期"口径</strong>（区别于长期借款 L3），不区分流动/非流动到期</li>
          <li><strong>专款专用</strong>是核心程序（L6-4）：核查实际用途与批准用途是否一致，关注挪用；结余资金按规定处理（返还/继续使用/结转收益）</li>
          <li>与<strong>专项储备（4301）、递延收益（2401）</strong>区分，核对拨款文件资金性质防错分类</li>
          <li>审定合计（按专项）回写 TB(2601) 并驱动附注披露；各表填妥"审计说明或结论"后目录标签转为"已填"</li>
        </ul>
      </details>
    </div>

    <!-- ═══ 底稿架构（4 阶段泳道） ═══ -->
    <div class="l6-arch">
      <div class="arch-header">
        <h4 class="arch-title">底稿架构</h4>
        <span class="arch-hint">点击卡片可跳转至对应底稿</span>
      </div>
      <GtBArchitectureTree
        :wp-id="wpId"
        :project-id="projectId"
        :active-sheet="''"
        :html-data="archHtmlData"
        @navigate="handleNavigate"
      />
    </div>

    <!-- ═══ 本循环底稿目录（L 循环其他科目，可跳转） ═══ -->
    <div v-if="cycleWorkpapers.length" class="l6-cycle">
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

<script setup lang="ts">
/**
 * L6TabIndex.vue — L6 专项应付款底稿目录（严格镜像 L1/E1 标准）
 *
 * 结构：目录卡（标题+复核+编制/使用手册+进度→跨表结论口径→编制提示）
 *       + 底稿架构 4 阶段泳道（GtBArchitectureTree）+ 本循环底稿目录 grid。
 * 编制信息由页面级头部渲染，此处不重复。自包含：自行拉取 checklist-responses。
 *
 * 负债类贷方科目（2601 专项应付款）— 期末=期初+贷方−借方；审定按专项项目双期动态行，
 * 从 L6-2 明细带入；无减一年内到期；L6-4 专款专用核查为核心程序；与专项储备/递延收益区分。
 *
 * 🔴 L6 各表审计说明/结论存储键前缀不一致（L6-L6-1-/L6-2-/L6-L6-4-），
 *    故 conclusionSheets 携各自 conclPrefix；calcSheetProgress 用真实前缀。
 */
import { computed, ref, onMounted, defineAsyncComponent } from 'vue'
import { useRouter } from 'vue-router'
import http from '@/utils/http'
import { loadCycleWorkpaperCards, type CycleWpCard } from '@/services/cycleDirectory'
import GtReviewTrigger from '../../GtReviewTrigger.vue'
import GtBArchitectureTree from '../../GtBArchitectureTree.vue'

const L6PreparationHandbookDialog = defineAsyncComponent(() => import('../L6PreparationHandbookDialog.vue'))

// ─── Props / Emits ───────────────────────────────────────────────────────────
const props = defineProps<{
  wpId: string
  projectId: string
  isReadonly: boolean
}>()

const emit = defineEmits<{
  (e: 'navigate', sheetName: string): void
}>()

const router = useRouter()

// ─── 编制/使用手册弹窗 ─────────────────────────────────────────────────────────
const handbookVisible = ref(false)
const handbookTab = ref<'preparation' | 'usage'>('preparation')
function openHandbook(tab: 'preparation' | 'usage') {
  handbookTab.value = tab
  handbookVisible.value = true
}

// ─── 自包含：拉取本底稿 checklist-responses（主入口不持有 allResponses） ─────────
const responses = ref<Map<string, any>>(new Map())
onMounted(async () => {
  if (!props.wpId) return
  try {
    const res: any = await http.get(`/api/workpapers/${props.wpId}/checklist-responses`)
    const list = res?.data?.items ?? res?.items ?? res?.data ?? res
    const map = new Map<string, any>()
    if (Array.isArray(list)) {
      for (const it of list) {
        if (it?.item_id) map.set(it.item_id, it)
      }
    }
    responses.value = map
  } catch {
    /* silent：拉取失败则看板全显未填 */
  }
})

// ─── Sheet 行定义 ─────────────────────────────────────────────────────────────
interface SheetRow {
  name: string
  code: string
  sheetKey: string
  progress: number
  /** 审计说明/结论存储键前缀（各表不一致，仅结论核心表有） */
  conclPrefix?: string
}

/** 按 responses 中以指定前缀存储的字段数计算完成度。 */
function calcSheetProgress(prefix: string, expectedFields: number): number {
  const map = responses.value
  if (!map || map.size === 0) return 0
  let count = 0
  for (const key of map.keys()) {
    if (key.startsWith(prefix)) count++
  }
  if (count === 0) return 0
  if (count >= expectedFields) return 100
  return Math.min(Math.round((count / expectedFields) * 100), 99)
}

const allSheets = computed<SheetRow[]>(() => [
  { name: '专项应付款实质性程序表', code: 'L6A', sheetKey: '专项应付款实质性程序表L6A', progress: calcSheetProgress('L6-L6A-', 5) },
  { name: '审定表（按专项项目，双期动态行）', code: 'L6-1', sheetKey: '审定表L6-1', progress: calcSheetProgress('L6-L6-1-', 6), conclPrefix: 'L6-L6-1-' },
  { name: '明细表（按专项项目逐项）', code: 'L6-2', sheetKey: '明细表L6-2', progress: calcSheetProgress('L6-L6-2-', 4), conclPrefix: 'L6-2-' },
  { name: '调整分录汇总', code: 'L6-3', sheetKey: '调整分录汇总L6-3', progress: calcSheetProgress('L6-L6-3-', 2) },
  { name: '专项应付款检查表（专款专用核查）', code: 'L6-4', sheetKey: '专项应付款检查表L6-4', progress: calcSheetProgress('L6-L6-4-', 4), conclPrefix: 'L6-L6-4-' },
  { name: '附注披露信息核对（上市公司）', code: '附注上市', sheetKey: '附注披露信息（上市公司）', progress: calcSheetProgress('L6-disc-listed-', 3) },
  { name: '附注披露信息核对（国企）', code: '附注国企', sheetKey: '附注披露信息（国企）', progress: calcSheetProgress('L6-disc-soe-', 3) },
])

// ─── 进度计算 ─────────────────────────────────────────────────────────────────
const totalCount = computed(() => allSheets.value.length)
const completedCount = computed(() => allSheets.value.filter(r => r.progress >= 100).length)
const progressPercent = computed(() => {
  if (totalCount.value === 0) return 0
  const avg = allSheets.value.reduce((sum, r) => sum + r.progress, 0) / totalCount.value
  return Math.round(avg)
})

// ─── 底稿架构泳道（GtBArchitectureTree 数据源） ───────────────────────────────
const COMPONENT_TYPE_MAP: Record<string, string> = {
  L6A: 'a-program-console',
  '附注上市': 'c-note-table',
  '附注国企': 'c-note-table',
}
function sheetStatus(progress: number): string {
  if (progress >= 100) return 'completed'
  if (progress > 0) return 'in_progress'
  return 'pending'
}
const archHtmlData = computed(() => ({
  navigation_rows: allSheets.value.map((s, i) => ({
    seq: i + 1,
    content: s.sheetKey,
    sheet_name: s.sheetKey,
    index_ref: s.code,
    component_type: COMPONENT_TYPE_MAP[s.code] ?? 'd-form-table',
    status: sheetStatus(s.progress),
  })),
}))

// ─── 跨表结论口径看板 ─────────────────────────────────────────────────────────
/** 有审计结论/说明的核心表（审定/明细/检查；程序表、调整分录、附注不计入） */
const L6_CONCLUSION_CODES = new Set(['L6-1', 'L6-2', 'L6-4'])

/**
 * 按各表真实 conclPrefix 判定审计说明/结论是否已填。
 * key 含 conclPrefix 且匹配 /conclusion|audit-note|note/ 且文本非空即为已填。
 * L6 各前缀（L6-L6-1-/L6-2-/L6-L6-4-）在 note/conclusion 键范围内无跨表误匹配。
 */
function isConclusionFilled(conclPrefix: string): boolean {
  const map = responses.value
  if (!map?.size) return false
  for (const [key, val] of map.entries()) {
    if (!key.includes(conclPrefix)) continue
    if (!/conclusion|audit-note|note/i.test(key)) continue
    const text = (val?.remark ?? val?.conclusion ?? '') as string
    if (typeof text === 'string' && text.trim().length > 0) return true
  }
  return false
}

const conclusionSheets = computed(() =>
  allSheets.value
    .filter(s => s.conclPrefix && L6_CONCLUSION_CODES.has(s.code))
    .map(s => ({ code: s.code, sheetKey: s.sheetKey, filled: isConclusionFilled(s.conclPrefix as string) })),
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

// ─── 交互 ────────────────────────────────────────────────────────────────────
function handleNavigate(sheetName: string) {
  if (sheetName) emit('navigate', sheetName)
}

// ─── 本循环底稿目录（L 循环其他科目，跨底稿跳转；canonical 源模板过滤污染） ───
const cycleWorkpapers = ref<CycleWpCard[]>([])
async function loadCycleWorkpapers(): Promise<void> {
  cycleWorkpapers.value = await loadCycleWorkpaperCards(props.projectId, 'L', props.wpId)
}
function onCycleCardClick(wp: CycleWpCard): void {
  if (!wp.wp_id || wp.is_current || !props.projectId) return
  router.push({ name: 'WorkpaperEditor', params: { projectId: props.projectId, wpId: wp.wp_id } })
}
onMounted(loadCycleWorkpapers)
</script>

<style scoped>
.l6-tab-index {
  padding: 16px;
  font-size: var(--wp-font-size, 13px);
}

/* ─── 目录卡 ─── */
.l6-dir { margin-bottom: 20px; }
.index-header { display: flex; align-items: center; gap: 12px; margin-bottom: 8px; flex-wrap: wrap; }
.title { margin: 0; font-size: 16px; font-weight: 600; color: #303133; }
.handbook-btns { display: flex; gap: 6px; }
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
.methodology-hint summary { cursor: pointer; font-weight: 500; color: #303133; }
.methodology-hint ul { padding-left: 20px; margin: 8px 0 0; line-height: 1.8; }

/* ─── 底稿架构 ─── */
.l6-arch { margin-top: 16px; }
.arch-header { display: flex; align-items: baseline; gap: 12px; margin-bottom: 12px; }
.arch-title { margin: 0; font-size: 16px; font-weight: 600; color: #303133; }
.arch-hint { font-size: 12px; color: #909399; }

/* ─── 本循环底稿目录 ─── */
.l6-cycle { margin-top: 28px; }
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
