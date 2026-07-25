<template>
  <div class="l5-tab-index">
    <!-- 编制信息由页面级头部统一渲染，此处不重复 -->

    <!-- ═══ 目录卡（标题 + 复核 + 编制/使用手册 + 进度条 → 跨表结论口径 → 编制提示） ═══ -->
    <div class="l5-dir">
      <div class="index-header">
        <h3 class="title">L5 长期应付款底稿目录</h3>
        <GtReviewTrigger section-id="L5-index-directory" />
        <div class="handbook-btns">
          <el-button size="small" type="primary" plain @click="openHandbook('preparation')">📖 编制手册</el-button>
          <el-button size="small" @click="openHandbook('usage')">使用手册</el-button>
        </div>
        <div class="progress-wrap">
          <span>编制进度 {{ completedCount }}/{{ totalCount }}</span>
          <el-progress :percentage="progressPercent" :stroke-width="10" />
        </div>
      </div>

      <L5PreparationHandbookDialog v-model="handbookVisible" :initial-tab="handbookTab" />

      <div class="conclusion-board" data-testid="l5-conclusion-board">
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
          <li>长期应付款为<strong>负债类贷方科目</strong>（2701）：期末 = 期初 + 贷方（新增借入）− 借方（偿还）</li>
          <li>未确认融资费用为<strong>负债备抵类借方科目</strong>（2702）：期末 = 期初 + 借方（新增）− 贷方（摊销转出）；<strong>净额 = 原值 − 未确认融资费用</strong></li>
          <li>审定表三区段（一、原值 / 二、未确认融资费用 / 三、净值逐行）双期列示（期初/期末各未审、账项调整、重分类、审定），并<strong>减一年内到期</strong>得披露审定数</li>
          <li><strong>实际利率法摊销</strong>（L5-5）：每期摊销 = 期初摊余成本 × 实际利率；末期未确认余额趋近 0（±1 元），本期摊销联动 L8 财务费用</li>
          <li>与经审计财报核对<strong>含专项应付款</strong>；关联方长期应付款需检查交易条件公允性</li>
          <li>审定净额期末合计回写 TB（2701 原值 + 2702 未确认融资费用）并驱动附注披露；各表填妥"审计说明或结论"后目录标签转为"已填"</li>
        </ul>
      </details>
    </div>

    <!-- ═══ 底稿架构（4 阶段泳道） ═══ -->
    <div class="l5-arch">
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
    <div v-if="cycleWorkpapers.length" class="l5-cycle">
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
 * L5TabIndex.vue — L5 长期应付款底稿目录（严格镜像 L1/E1 标准）
 *
 * 结构：目录卡（标题+复核+编制/使用手册+进度→跨表结论口径→编制提示）
 *       + 底稿架构 4 阶段泳道（GtBArchitectureTree）+ 本循环底稿目录 grid。
 * 编制信息由页面级头部渲染，此处不重复。自包含：自行拉取 checklist-responses。
 *
 * 负债类贷方科目（2701 长期应付款）+ 负债备抵借方（2702 未确认融资费用）；净额=原值−未确认融资费用；
 * 审定表三区段双期+减一年内到期，L5-5 实际利率法摊销联动 L8，与经审计财报核对含专项应付款。
 *
 * 🔴 L5 各表审计说明/结论存储键前缀不统一（真实前缀，非照抄 L1）：
 *    L5-1→L5-L5-1-(note/conclusion)；L5-2→L5-2-auditNote；L5-3→L5-3-auditNote；
 *    L5-7→L5-L5-7-conclusion；附注→L5-disc-listed-/L5-disc-soe-conclusion。
 *    L5-5 摊销/L5-6 关联方无独立审计结论，不计入结论看板。
 */
import { computed, ref, onMounted, defineAsyncComponent } from 'vue'
import { useRouter } from 'vue-router'
import http from '@/utils/http'
import { loadCycleWorkpaperCards, type CycleWpCard } from '@/services/cycleDirectory'
import GtReviewTrigger from '../../GtReviewTrigger.vue'
import GtBArchitectureTree from '../../GtBArchitectureTree.vue'

const L5PreparationHandbookDialog = defineAsyncComponent(() => import('../L5PreparationHandbookDialog.vue'))

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
  /** 审计说明/结论存储键前缀（真实，仅结论核心表有） */
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
  { name: '长期应付款实质性程序表', code: 'L5A', sheetKey: '长期应付款实质性程序表L5A', progress: calcSheetProgress('L5-L5A-', 5) },
  { name: '审定表（三区段：原值/未确认融资费用/净值，双期）', code: 'L5-1', sheetKey: '审定表L5-1', progress: calcSheetProgress('L5-L5-1-', 4), conclPrefix: 'L5-L5-1-' },
  { name: '明细表（按款项：融资租赁/分期购入/其他）', code: 'L5-2', sheetKey: '明细表L5-2', progress: calcSheetProgress('L5-L5-2-', 1), conclPrefix: 'L5-2-' },
  { name: '未确认融资费用明细表', code: 'L5-3', sheetKey: '未确认融资费用明细表L5-3', progress: calcSheetProgress('L5-L5-3-', 1), conclPrefix: 'L5-3-' },
  { name: '调整分录汇总', code: 'L5-4', sheetKey: '调整分录汇总L5-4', progress: calcSheetProgress('L5-L5-4-', 6) },
  { name: '未确认融资费用测算表（实际利率法，联动 L8）', code: 'L5-5', sheetKey: '未确认融资费用测算表L5-5', progress: calcSheetProgress('L5-L5-5-', 2) },
  { name: '关联方及交易检查表', code: 'L5-6', sheetKey: '关联方及交易检查表L5-6', progress: calcSheetProgress('L5-L5-6-', 1) },
  { name: '长期应付款检查表', code: 'L5-7', sheetKey: '长期应付款检查表L5-7', progress: calcSheetProgress('L5-L5-7-', 1), conclPrefix: 'L5-L5-7-' },
  { name: '附注披露信息核对（上市公司）', code: '附注上市', sheetKey: '附注披露信息（上市公司）', progress: calcSheetProgress('L5-disc-listed-', 1), conclPrefix: 'L5-disc-listed-' },
  { name: '附注披露信息核对（国企）', code: '附注国企', sheetKey: '附注披露信息（国企）', progress: calcSheetProgress('L5-disc-soe-', 1), conclPrefix: 'L5-disc-soe-' },
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
  L5A: 'a-program-console',
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
/** 有审计结论/说明的核心表（审定/明细/检查类；程序表、调整分录、摊销、关联方、附注不计入） */
const L5_CONCLUSION_CODES = new Set(['L5-1', 'L5-2', 'L5-3', 'L5-7'])

/**
 * 按各表真实 conclPrefix 判定审计说明/结论是否已填。
 * key 含 conclPrefix 且匹配 /conclusion|audit-note|note/ 且文本非空即为已填。
 * L5-L5-1- / L5-2- / L5-3- / L5-L5-7- 各自的 note/conclusion 键均命中，rows/total 等被正则过滤。
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
    .filter(s => s.conclPrefix && L5_CONCLUSION_CODES.has(s.code))
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
.l5-tab-index {
  padding: 16px;
  font-size: var(--wp-font-size, 13px);
}

/* ─── 目录卡 ─── */
.l5-dir { margin-bottom: 20px; }
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
.l5-arch { margin-top: 16px; }
.arch-header { display: flex; align-items: baseline; gap: 12px; margin-bottom: 12px; }
.arch-title { margin: 0; font-size: 16px; font-weight: 600; color: #303133; }
.arch-hint { font-size: 12px; color: #909399; }

/* ─── 本循环底稿目录 ─── */
.l5-cycle { margin-top: 28px; }
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
