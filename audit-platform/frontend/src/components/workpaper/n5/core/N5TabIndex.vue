<template>
  <div class="n5-tab-index">
    <!-- 编制信息由页面级头部统一渲染，此处不重复 -->

    <!-- ═══ 目录卡（标题 + 复核 + 编制/使用手册 + 进度条 → 跨表结论口径 → 编制提示） ═══ -->
    <div class="n5-dir">
      <div class="index-header">
        <h3 class="title">N5 底稿目录</h3>
        <GtReviewTrigger section-id="N5-index-directory" />
        <div class="handbook-btns">
          <el-button size="small" type="primary" plain @click="openHandbook('preparation')">📖 编制手册</el-button>
          <el-button size="small" @click="openHandbook('usage')">使用手册</el-button>
        </div>
        <div class="progress-wrap">
          <span>编制进度 {{ completedCount }}/{{ totalCount }}</span>
          <el-progress :percentage="progressPercent" :stroke-width="10" />
        </div>
      </div>

      <N5PreparationHandbookDialog v-model="handbookVisible" :initial-tab="handbookTab" />

      <div class="conclusion-board" data-testid="n5-conclusion-board">
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
          <li>所得税费用为<strong>损益类借方科目</strong>（6801）：取本期发生额（借方发生 − 贷方发生），非期末余额</li>
          <li>所得税费用 = 当期所得税费用（N5-4）+ 递延所得税费用（N5-8）</li>
          <li>当期所得税 = 应纳税所得额 × 适用税率 − 减免 − 抵免；应纳税所得额 = 会计利润 + 纳税调增 − 纳税调减</li>
          <li>递延所得税费用 = 递延税负债本期增加 − 递延税资产本期增加（核对 N1/N3）</li>
          <li>有效税率 = 所得税费用 ÷ 会计利润（合理性分析）；审定合计回写 TB(6801 发生额) 并进利润表；各表填妥"审计说明或结论"后目录标签转为"已填"</li>
        </ul>
      </details>
    </div>

    <!-- ═══ 底稿架构（4 阶段泳道） ═══ -->
    <div class="n5-arch">
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

    <!-- ═══ 本循环底稿目录（N 循环其他科目，可跳转） ═══ -->
    <div v-if="cycleWorkpapers.length" class="n5-cycle">
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
 * N5TabIndex.vue — N5 所得税费用底稿目录（严格镜像 N1 标准）
 *
 * 结构：目录卡（标题+复核+编制/使用手册+进度→跨表结论口径→编制提示）
 *       + 底稿架构 4 阶段泳道（GtBArchitectureTree）+ 本循环底稿目录 grid。
 * 编制信息由页面级头部渲染，此处不重复。自包含：自行拉取 checklist-responses。
 *
 * 损益类借方科目（6801 所得税费用）— 取本期发生额，当期 + 递延核对 N1/N3。
 * 注：N5-6/N5-6-1/N5-6-2 编码存在前缀重叠，isConclusionFilled 已排除更长兄弟编码误算。
 */
import { computed, ref, onMounted, defineAsyncComponent } from 'vue'
import { useRouter } from 'vue-router'
import http from '@/utils/http'
import { loadCycleWorkpaperCards, type CycleWpCard } from '@/services/cycleDirectory'
import GtReviewTrigger from '../../GtReviewTrigger.vue'
import GtBArchitectureTree from '../../GtBArchitectureTree.vue'

const N5PreparationHandbookDialog = defineAsyncComponent(() => import('../N5PreparationHandbookDialog.vue'))

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
  { name: '所得税费用审计程序表', code: 'N5A', sheetKey: '所得税审计程序表N5A', progress: calcSheetProgress('N5-N5A-', 5) },
  { name: '审定表', code: 'N5-1', sheetKey: '所得税费用审定表N5-1', progress: calcSheetProgress('N5-1-', 6) },
  { name: '明细表', code: 'N5-2', sheetKey: '所得税费用明细表N5-2', progress: calcSheetProgress('N5-2-', 4) },
  { name: '调整分录汇总', code: 'N5-3', sheetKey: '调整分录汇总表N5-3', progress: calcSheetProgress('N5-3-', 4) },
  { name: '当期所得税费用计算表', code: 'N5-4', sheetKey: '当期所得税费用计算表N5-4', progress: calcSheetProgress('N5-4-', 6) },
  { name: '纳税调整明细表', code: 'N5-5', sheetKey: '纳税调整明细表N5-5', progress: calcSheetProgress('N5-5-', 6) },
  { name: '税收优惠明细表', code: 'N5-6', sheetKey: '税收优惠明细表N5-6', progress: calcSheetProgress('N5-6-', 4) },
  { name: '加计扣除研发费用情况明细表', code: 'N5-6-1', sheetKey: '加计扣除研发费用情况明细表N5-6-1', progress: calcSheetProgress('N5-6-1-', 4) },
  { name: '高新技术企业认定条件检查表', code: 'N5-6-2', sheetKey: '高新技术企业认定条件检查表N5-6-2', progress: calcSheetProgress('N5-6-2-', 4) },
  { name: '财产损失明细表', code: 'N5-7', sheetKey: '财产损失明细表N5-7', progress: calcSheetProgress('N5-7-', 4) },
  { name: '递延所得税费用核对表', code: 'N5-8', sheetKey: '递延所得税费用核对表N5-8', progress: calcSheetProgress('N5-8-', 6) },
  { name: '附注披露信息（上市公司）', code: '附注上市', sheetKey: '附注披露信息（上市公司）', progress: calcSheetProgress('N5-disclosure-listed-', 3) },
  { name: '附注披露信息（国企）', code: '附注国企', sheetKey: '附注披露信息（国企', progress: calcSheetProgress('N5-disclosure-soe-', 3) },
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
  N5A: 'a-program-console',
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
/** 有审计结论/说明的 sheet（程序表、调整分录、附注不计入；审定/明细/测算/检查计入） */
const N5_CONCLUSION_CODES = new Set(['N5-1', 'N5-2', 'N5-4', 'N5-5', 'N5-6', 'N5-6-1', 'N5-6-2', 'N5-7', 'N5-8'])

/**
 * includes(`${code}-`) 兼容不同存储前缀深度，尾部连字符保证边界安全；
 * 并排除更长兄弟编码（N5-6 的 N5-6-1/N5-6-2）误算——N5 存在编码重叠，此排除必需。
 */
function isConclusionFilled(code: string): boolean {
  const map = responses.value
  if (!map?.size) return false
  const token = `${code}-`
  const longer = Array.from(N5_CONCLUSION_CODES).filter(c => c !== code && c.startsWith(token))
  for (const [key, val] of map.entries()) {
    if (!key.includes(token)) continue
    if (longer.some(lc => key.includes(`${lc}-`))) continue
    if (!/conclusion|audit-note|note/i.test(key)) continue
    const text = (val?.remark ?? val?.conclusion ?? '') as string
    if (typeof text === 'string' && text.trim().length > 0) return true
  }
  return false
}

const conclusionSheets = computed(() =>
  allSheets.value
    .filter(s => N5_CONCLUSION_CODES.has(s.code))
    .map(s => ({ code: s.code, sheetKey: s.sheetKey, filled: isConclusionFilled(s.code) })),
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

// ─── 本循环底稿目录（N 循环其他科目，跨底稿跳转；canonical 源模板过滤污染） ───
const cycleWorkpapers = ref<CycleWpCard[]>([])
async function loadCycleWorkpapers(): Promise<void> {
  cycleWorkpapers.value = await loadCycleWorkpaperCards(props.projectId, 'N', props.wpId)
}
function onCycleCardClick(wp: CycleWpCard): void {
  if (!wp.wp_id || wp.is_current || !props.projectId) return
  router.push({ name: 'WorkpaperEditor', params: { projectId: props.projectId, wpId: wp.wp_id } })
}
onMounted(loadCycleWorkpapers)
</script>

<style scoped>
.n5-tab-index {
  padding: 16px;
  font-size: var(--wp-font-size, 13px);
}

/* ─── 目录卡 ─── */
.n5-dir { margin-bottom: 20px; }
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
.n5-arch { margin-top: 16px; }
.arch-header { display: flex; align-items: baseline; gap: 12px; margin-bottom: 12px; }
.arch-title { margin: 0; font-size: 16px; font-weight: 600; color: #303133; }
.arch-hint { font-size: 12px; color: #909399; }

/* ─── 本循环底稿目录 ─── */
.n5-cycle { margin-top: 28px; }
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
