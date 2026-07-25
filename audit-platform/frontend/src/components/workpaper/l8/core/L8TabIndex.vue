<template>
  <div class="l8-tab-index">
    <!-- 编制信息由页面级头部统一渲染，此处不重复 -->

    <!-- ═══ 目录卡（标题 + 复核 + 编制/使用手册 + 进度条 → 跨表结论口径 → 编制提示） ═══ -->
    <div class="l8-dir">
      <div class="index-header">
        <h3 class="title">L8 财务费用底稿目录</h3>
        <GtReviewTrigger section-id="L8-index-directory" />
        <div class="handbook-btns">
          <el-button size="small" type="primary" plain @click="openHandbook('preparation')">📖 编制手册</el-button>
          <el-button size="small" @click="openHandbook('usage')">使用手册</el-button>
        </div>
        <div class="progress-wrap">
          <span>编制进度 {{ completedCount }}/{{ totalCount }}</span>
          <el-progress :percentage="progressPercent" :stroke-width="10" />
        </div>
      </div>

      <L8PreparationHandbookDialog v-model="handbookVisible" :initial-tab="handbookTab" />

      <div class="conclusion-board" data-testid="l8-conclusion-board">
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
          <li>财务费用为<strong>损益类借方科目</strong>（6603）：本期发生额 = 借方发生 − 贷方发生（<strong>非期末余额</strong>），从 tb_ledger 取本期借贷发生额</li>
          <li>费用构成：利息支出 − 利息收入 + 汇兑损益 + 手续费 + 其他；利息收入冲减、汇兑损益按净额列示</li>
          <li>利息支出联动 <strong>L1 短期借款 / L3 长期借款 / L4 应付债券</strong> 利息测算 + <strong>L5 未确认融资费用摊销</strong></li>
          <li>非金融机构（企业间）借款利息超同期同类金融机构贷款利率部分不可税前扣除（L8-4）</li>
          <li>截止性测试（L8-5）：报告日 ± 天数序时账逐笔检查费用归属期间；审定合计回写 TB(6603) 并驱动附注披露</li>
        </ul>
      </details>
    </div>

    <!-- ═══ 底稿架构（4 阶段泳道） ═══ -->
    <div class="l8-arch">
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
    <div v-if="cycleWorkpapers.length" class="l8-cycle">
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
 * L8TabIndex.vue — L8 财务费用底稿目录（严格镜像 L1/E1 标准）
 *
 * 结构：目录卡（标题+复核+编制/使用手册+进度→跨表结论口径→编制提示）
 *       + 底稿架构 4 阶段泳道（GtBArchitectureTree）+ 本循环底稿目录 grid。
 * 编制信息由页面级头部渲染，此处不重复。自包含：自行拉取 checklist-responses。
 *
 * 损益类借方科目（6603 财务费用）— 本期发生额=借方发生−贷方发生（非期末余额）；
 * 费用构成=利息支出−利息收入+汇兑损益+手续费+其他；利息支出联动 L1/L3/L4 利息测算+L5 摊销；
 * L8-4 评价非金融机构利息税前扣除性，L8-5 截止测试查费用归属期间。
 *
 * 🔴 L8 各表审计说明/结论存储键为编码式（L8-1-/L8-2-/L8-5-/L8-6-/L8-disc-listed-/L8-disc-soe-），
 *    故 conclusionSheets 携各自 conclPrefix；calcSheetProgress 用真实前缀。
 *    L8-4 非金融利息测算无结论键（不入结论看板）；L8-3 调整、L8A 程序表、附注不计入看板。
 */
import { computed, ref, onMounted, defineAsyncComponent } from 'vue'
import { useRouter } from 'vue-router'
import http from '@/utils/http'
import { loadCycleWorkpaperCards, type CycleWpCard } from '@/services/cycleDirectory'
import GtReviewTrigger from '../../GtReviewTrigger.vue'
import GtBArchitectureTree from '../../GtBArchitectureTree.vue'

const L8PreparationHandbookDialog = defineAsyncComponent(() => import('../L8PreparationHandbookDialog.vue'))

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
  /** 审计说明/结论存储键前缀（编码式，仅结论核心表有） */
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
  { name: '财务费用实质性程序表', code: 'L8A', sheetKey: '实质性程序表L8A', progress: calcSheetProgress('L8-L8A-', 5) },
  { name: '审定表（损益类借方，取本期发生额）', code: 'L8-1', sheetKey: '审定表L8-1', progress: calcSheetProgress('L8-1-', 6), conclPrefix: 'L8-1-' },
  { name: '明细表（按费用项目：利息支出/收入/汇兑/手续费/其他）', code: 'L8-2', sheetKey: '明细表L8-2', progress: calcSheetProgress('L8-2-', 4), conclPrefix: 'L8-2-' },
  { name: '调整分录汇总', code: 'L8-3', sheetKey: '调整分录汇总L8-3', progress: calcSheetProgress('L8-3-', 2) },
  { name: '非金融机构利息支出测算表（税前扣除性）', code: 'L8-4', sheetKey: '非金融机构利息支出测算表L8-4', progress: calcSheetProgress('L8-4-', 4) },
  { name: '截止性测试（序时账报告日±天数）', code: 'L8-5', sheetKey: '截止性测试L8-5', progress: calcSheetProgress('L8-5-', 4), conclPrefix: 'L8-5-' },
  { name: '财务费用检查表', code: 'L8-6', sheetKey: '财务费用检查表L8-6', progress: calcSheetProgress('L8-6-', 4), conclPrefix: 'L8-6-' },
  { name: '附注披露信息核对（上市公司）', code: '附注上市', sheetKey: '附注披露信息（上市公司）', progress: calcSheetProgress('L8-disclosure-listed-', 3) },
  { name: '附注披露信息核对（国企）', code: '附注国企', sheetKey: '附注披露信息（国企）', progress: calcSheetProgress('L8-disclosure-soe-', 3) },
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
  L8A: 'a-program-console',
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
/** 有审计结论/说明的核心表（审定/明细/截止/检查类；程序表、调整分录、附注、无结论键的测算表不计入） */
const L8_CONCLUSION_CODES = new Set(['L8-1', 'L8-2', 'L8-5', 'L8-6'])

/**
 * 按各表真实 conclPrefix（编码式）判定审计说明/结论是否已填。
 * key 含 conclPrefix 且匹配 /conclusion|audit-note|note/ 且文本非空即为已填；
 * L8 编码前缀（L8-1-/L8-2-/L8-5-/L8-6-）互不为前缀（无 L8-10~L8-19），无兄弟重叠。
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
    .filter(s => s.conclPrefix && L8_CONCLUSION_CODES.has(s.code))
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
.l8-tab-index {
  padding: 16px;
  font-size: var(--wp-font-size, 13px);
}

/* ─── 目录卡 ─── */
.l8-dir { margin-bottom: 20px; }
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
.l8-arch { margin-top: 16px; }
.arch-header { display: flex; align-items: baseline; gap: 12px; margin-bottom: 12px; }
.arch-title { margin: 0; font-size: 16px; font-weight: 600; color: #303133; }
.arch-hint { font-size: 12px; color: #909399; }

/* ─── 本循环底稿目录 ─── */
.l8-cycle { margin-top: 28px; }
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
