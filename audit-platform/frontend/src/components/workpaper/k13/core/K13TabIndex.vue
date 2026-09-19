<template>
  <div class="k13-tab-index">
    <!-- 编制信息由页面级头部统一渲染，此处不重复 -->

    <!-- ═══ 目录卡（标题 + 复核 + 编制/使用手册 + 进度条 → 跨表结论口径 → 编制提示） ═══ -->
    <div class="k13-dir">
      <div class="index-header">
        <h3 class="title">K13 底稿目录</h3>
        <GtReviewTrigger section-id="K13-index-directory" />
        <div class="handbook-btns">
          <el-button size="small" type="primary" plain @click="openHandbook('preparation')">📖 编制手册</el-button>
          <el-button size="small" @click="openHandbook('usage')">使用手册</el-button>
        </div>
        <div class="progress-wrap">
          <span>编制进度 {{ completedCount }}/{{ totalCount }}</span>
          <el-progress :percentage="progressPercent" :stroke-width="10" />
        </div>
      </div>

      <K13PreparationHandbookDialog v-model="handbookVisible" :initial-tab="handbookTab" />

      <div class="conclusion-board" data-testid="k13-conclusion-board">
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
            @click="emit('navigate-sheet', c.sheetKey)"
          >
            {{ c.code }} {{ c.filled ? '已填' : '未填' }}
          </el-tag>
        </div>
        <p v-if="conclusionHasUnfilled" class="board-hint">存在未填审计结论，请点击标签跳转补全审计说明与结论。</p>
      </div>

      <details class="methodology-hint">
        <summary>编制提示</summary>
        <ul>
          <li>营业外支出为<strong>损益类借方科目</strong>（6711）：取本期<strong>借方发生额</strong>累计（借方 = 支出增加），非期末余额</li>
          <li>营业外支出 = 与日常活动无关的损失（毁损报废/捐赠/罚款/非常损失等）</li>
          <li>关注税前扣除性：罚款/滞纳金/赞助支出等不得税前扣除，需关注纳税调整（联动 N4）</li>
          <li>审定数 = 未审数 + AJE + RJE；审定发生额回写试算平衡表 6711；调整分录联动 A13</li>
          <li>K13-2 明细合计应与 K13-1 审定表一致；各表填妥"审计说明或结论"后目录标签转为"已填"</li>
        </ul>
      </details>
    </div>

    <!-- ═══ 底稿架构（4 阶段泳道） ═══ -->
    <div class="k13-arch">
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

    <!-- ═══ 本循环底稿目录（K 循环其他科目，可跳转） ═══ -->
    <div v-if="cycleWorkpapers.length" class="k13-cycle">
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
 * K13TabIndex.vue — K13 营业外支出底稿目录（严格镜像 E1 标准）
 *
 * 结构：目录卡（标题+复核+编制/使用手册+进度→跨表结论口径→编制提示）
 *       + 底稿架构 4 阶段泳道（GtBArchitectureTree）+ 本循环底稿目录 grid。
 * 编制信息由页面级头部渲染，此处不重复。
 *
 * 损益类科目（6711营业外支出）— 借方=支出增加，取发生额非余额。
 */
import { computed, ref, onMounted, defineAsyncComponent } from 'vue'
import { useRouter } from 'vue-router'
import { loadCycleWorkpaperCards, type CycleWpCard } from '@/services/cycleDirectory'
import GtReviewTrigger from '../../GtReviewTrigger.vue'
import GtBArchitectureTree from '../../GtBArchitectureTree.vue'

const K13PreparationHandbookDialog = defineAsyncComponent(() => import('../K13PreparationHandbookDialog.vue'))

// ─── Props / Emits ───────────────────────────────────────────────────────────
const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const emit = defineEmits<{
  (e: 'navigate-sheet', sheetName: string): void
}>()

const router = useRouter()

// ─── 编制/使用手册弹窗 ─────────────────────────────────────────────────────────
const handbookVisible = ref(false)
const handbookTab = ref<'preparation' | 'usage'>('preparation')
function openHandbook(tab: 'preparation' | 'usage') {
  handbookTab.value = tab
  handbookVisible.value = true
}

// ─── Sheet 行定义 ─────────────────────────────────────────────────────────────
interface SheetRow {
  seq: number
  name: string
  code: string
  sheetKey: string
  group: 'core' | 'inspection' | 'disclosure'
  progressKeys: string[]
  progress: number
}

/** 按 K13 真实存储 key（JSON-array 单键 / 前缀）计算完成度（二值：有数据→100，无→0）。 */
function calcSheetProgress(progressKeys: string[]): number {
  const map = props.allResponses
  if (!map || map.size === 0) return 0
  const keys = [...map.keys()]
  const hasData = progressKeys.some(pk => map.has(pk) || keys.some(k => k.startsWith(pk)))
  return hasData ? 100 : 0
}

const allSheets = computed<SheetRow[]>(() => {
  const rows: Omit<SheetRow, 'progress'>[] = [
    { seq: 1, name: '实质性程序表', code: 'K13A', sheetKey: '营业外支出实质性程序表K13A', group: 'core', progressKeys: ['K13-K13A-'] },
    { seq: 2, name: '审定表', code: 'K13-1', sheetKey: '审定表K13-1', group: 'core', progressKeys: ['K13-1-rows'] },
    { seq: 3, name: '明细表', code: 'K13-2', sheetKey: '明细表K13-2', group: 'core', progressKeys: ['K13-2-detail-rows'] },
    { seq: 4, name: '调整分录汇总', code: 'K13-3', sheetKey: '调整分录汇总K13-3', group: 'core', progressKeys: ['K13-3-'] },
    { seq: 5, name: '营业外支出检查表', code: 'K13-4', sheetKey: '营业外支出检查表K13-4', group: 'inspection', progressKeys: ['K13-4-check-rows'] },
    { seq: 6, name: '附注披露信息（上市公司）', code: '附注上市', sheetKey: '附注披露信息（上市公司）', group: 'disclosure', progressKeys: ['K13-disc-listed-'] },
    { seq: 7, name: '附注披露信息（国有企业）', code: '附注国企', sheetKey: '附注披露信息（国有企业）', group: 'disclosure', progressKeys: ['K13-disc-soe-'] },
  ]
  return rows.map(r => ({ ...r, progress: calcSheetProgress(r.progressKeys) }))
})

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
  K13A: 'a-program-console',
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
/** 有审计结论/说明的 sheet（K13A 程序表、K13-3 调整分录、附注、目录本身不计入） */
const K13_CONCLUSION_CODES = new Set(['K13-1', 'K13-2', 'K13-4'])

/** includes(`${code}-`) 兼容不同存储前缀深度，尾部连字符保证边界安全。 */
function isConclusionFilled(code: string): boolean {
  const map = props.allResponses
  if (!map?.size) return false
  const token = `${code}-`
  for (const [key, val] of map.entries()) {
    if (!key.includes(token)) continue
    if (!/conclusion|audit-note/i.test(key)) continue
    const text = (val?.remark ?? val?.conclusion ?? '') as string
    if (typeof text === 'string' && text.trim().length > 0) return true
  }
  return false
}

const conclusionSheets = computed(() =>
  allSheets.value
    .filter(s => K13_CONCLUSION_CODES.has(s.code))
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
  if (sheetName) emit('navigate-sheet', sheetName)
}

// ─── 本循环底稿目录（K 循环其他科目，跨底稿跳转；canonical 源模板过滤污染） ───
const cycleWorkpapers = ref<CycleWpCard[]>([])

async function loadCycleWorkpapers(): Promise<void> {
  cycleWorkpapers.value = await loadCycleWorkpaperCards(props.projectId, 'K', props.wpId)
}

function onCycleCardClick(wp: CycleWpCard): void {
  if (!wp.wp_id || wp.is_current || !props.projectId) return
  router.push({ name: 'WorkpaperEditor', params: { projectId: props.projectId, wpId: wp.wp_id } })
}

onMounted(loadCycleWorkpapers)
</script>

<style scoped>
.k13-tab-index {
  padding: 16px;
  font-size: var(--wp-font-size, 13px);
}

/* ─── 目录卡 ─── */
.k13-dir { margin-bottom: 20px; }
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
.k13-arch { margin-top: 16px; }
.arch-header { display: flex; align-items: baseline; gap: 12px; margin-bottom: 12px; }
.arch-title { margin: 0; font-size: 16px; font-weight: 600; color: #303133; }
.arch-hint { font-size: 12px; color: #909399; }

/* ─── 本循环底稿目录 ─── */
.k13-cycle { margin-top: 28px; }
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
