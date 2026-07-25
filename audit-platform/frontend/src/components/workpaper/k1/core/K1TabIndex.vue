<template>
  <div class="k1-tab-index">
    <!-- 编制信息由页面级头部统一渲染，此处不重复 -->

    <!-- ═══ 目录卡（标题 + 复核 + 编制/使用手册 + 进度条 → 跨表结论口径 → 编制提示，对齐 E1TabDirectory） ═══ -->
    <div class="k1-dir">
      <div class="index-header">
        <h3 class="title">K1 底稿目录</h3>
        <GtReviewTrigger section-id="K1-index-directory" />
        <div class="handbook-btns">
          <el-button size="small" type="primary" plain @click="openHandbook('preparation')">📖 编制手册</el-button>
          <el-button size="small" @click="openHandbook('usage')">使用手册</el-button>
        </div>
        <div class="progress-wrap">
          <span>编制进度 {{ completedCount }}/{{ totalCount }}</span>
          <el-progress :percentage="progressPercent" :stroke-width="10" />
        </div>
      </div>

      <K1PreparationHandbookDialog v-model="handbookVisible" :initial-tab="handbookTab" />

      <!-- 跨表结论口径看板 -->
      <div class="conclusion-board" data-testid="k1-conclusion-board">
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
          <li>其他应收款为<strong>资产类借方科目</strong>（1221）：期末 = 期初 + 借方 − 贷方</li>
          <li>坏账准备为<strong>资产备抵类贷方科目</strong>：期末 = 期初 + 贷方 − 借方；账面净值 = 其他应收款 − 坏账准备</li>
          <li>推荐工作流：K1A 程序 → K1-2 明细 → K1-6 政策 → K1-7 三阶段 → K1-8 测算 → K1-3 坏账明细 → K1-5/9/10/11/12 检查 → K1-4 调整回写 K1-1 → 附注披露</li>
          <li>K1-8 测算结果应与 K1-3 企业计提交叉验证；各表填妥"审计说明或结论"后目录标签转为"已填"</li>
        </ul>
      </details>
    </div>

    <!-- ═══ 底稿架构（4 阶段泳道，对齐 E1） ═══ -->
    <div class="k1-arch">
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

    <!-- ═══ 本循环底稿目录（K 循环其他科目，可跳转，对齐 E1） ═══ -->
    <div v-if="cycleWorkpapers.length" class="k1-cycle">
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
 * K1TabIndex.vue — K1 其他应收款底稿目录（严格镜像 E1 标准）
 *
 * 结构对齐 E1（GtBIndex + E1TabDirectory）：
 *   ① 编制信息（可折叠，来自 project_context）
 *   ② 目录卡：标题 + 复核 + 编制/使用手册 + 进度条 → 跨表结论口径看板 → 编制提示
 *   ③ 底稿架构 4 阶段泳道（GtBArchitectureTree）
 *   ④ 跨表勾稽（K1 增强，保留）
 *
 * 点击卡片/标签 emit navigate-sheet（由 GtK1OtherReceivables 监听切换 sheetName）。
 * 从 allResponses 计算各 sheet 完成度与结论口径。
 */
import { computed, ref, onMounted, defineAsyncComponent } from 'vue'
import { useRouter } from 'vue-router'
import { calcK1SheetProgress } from '../../composables/k1SheetProgress'
import { loadCycleWorkpaperCards, type CycleWpCard } from '@/services/cycleDirectory'
import GtReviewTrigger from '../../GtReviewTrigger.vue'
import GtBArchitectureTree from '../../GtBArchitectureTree.vue'

const K1PreparationHandbookDialog = defineAsyncComponent(() => import('../K1PreparationHandbookDialog.vue'))

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
  group: 'core' | 'impairment' | 'inspection' | 'disclosure'
  progress: number
}

function sheetProgress(code: string): number {
  return calcK1SheetProgress(props.allResponses, code)
}

const allSheets = computed<SheetRow[]>(() => [
  { seq: 1, name: '其他应收款实质性程序表', code: 'K1A', sheetKey: '其他应收款实质性程序表K1A', group: 'core', progress: sheetProgress('K1A') },
  { seq: 2, name: '审定表', code: 'K1-1', sheetKey: '审定表K1-1', group: 'core', progress: sheetProgress('K1-1') },
  { seq: 3, name: '明细表', code: 'K1-2', sheetKey: '明细表K1-2', group: 'core', progress: sheetProgress('K1-2') },
  { seq: 4, name: '坏账准备明细表', code: 'K1-3', sheetKey: '坏账准备明细表K1-3', group: 'core', progress: sheetProgress('K1-3') },
  { seq: 5, name: '调整分录汇总', code: 'K1-4', sheetKey: '调整分录汇总K1-4', group: 'core', progress: sheetProgress('K1-4') },
  { seq: 6, name: '信用减值损失会计政策检查', code: 'K1-6', sheetKey: '信用减值损失会计政策检查K1-6', group: 'impairment', progress: sheetProgress('K1-6') },
  { seq: 7, name: '三阶段划分检查表', code: 'K1-7', sheetKey: '三阶段划分检查表K1-7', group: 'impairment', progress: sheetProgress('K1-7') },
  { seq: 8, name: '坏账准备测算', code: 'K1-8', sheetKey: '坏账准备测算K1-8', group: 'impairment', progress: sheetProgress('K1-8') },
  { seq: 9, name: '大额其他应收款情况分析表', code: 'K1-5', sheetKey: '大额其他应收款情况分析表K1-5', group: 'inspection', progress: sheetProgress('K1-5') },
  { seq: 10, name: '坏账准备转回(收回)核销检查表', code: 'K1-9', sheetKey: '坏账准备转回(收回)核销检查表K1-9', group: 'inspection', progress: sheetProgress('K1-9') },
  { seq: 11, name: '长期未收回款项检查表', code: 'K1-10', sheetKey: '长期未收回款项检查表K1-10', group: 'inspection', progress: sheetProgress('K1-10') },
  { seq: 12, name: '关联方及交易检查表', code: 'K1-11', sheetKey: '关联方及交易检查表K1-11', group: 'inspection', progress: sheetProgress('K1-11') },
  { seq: 13, name: '其他应收款检查表', code: 'K1-12', sheetKey: '其他应收款检查表K1-12', group: 'inspection', progress: sheetProgress('K1-12') },
  { seq: 14, name: '附注披露信息（上市公司）', code: '附注上市', sheetKey: '附注披露信息（上市公司）', group: 'disclosure', progress: sheetProgress('附注上市') },
  { seq: 15, name: '附注披露信息（国企）', code: '附注国企', sheetKey: '附注披露信息（国企）', group: 'disclosure', progress: sheetProgress('附注国企') },
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
/** component_type 决定 4 阶段归类：a-program-console(含程序表)→审计计划 / 含审定表→科目审定 / c-note-table·含调整分录→披露 / 其余→实质性程序 */
const COMPONENT_TYPE_MAP: Record<string, string> = {
  K1A: 'a-program-console',
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
/** 有审计结论/说明的 sheet（K1-4 调整分录、附注、目录本身不计入） */
const K1_CONCLUSION_CODES = new Set([
  'K1-1', 'K1-2', 'K1-3', 'K1-5', 'K1-6', 'K1-7', 'K1-8', 'K1-9', 'K1-10', 'K1-11', 'K1-12',
])

/**
 * 判定某 sheet 审计结论/说明是否已填。
 * K1 各表 conclusion 键命名不统一（-audit-conclusion / -conclusion / -audit-note），
 * 故按「前缀 + 含 conclusion/audit-note + 非空」扫描真实持久化数据，避免臆造 key 造成假绿。
 */
function isConclusionFilled(code: string): boolean {
  const map = props.allResponses
  if (!map?.size) return false
  const token = `${code}-`
  for (const [key, val] of map.entries()) {
    // includes(`${code}-`) 而非 startsWith：兼容不同存储前缀深度（K1=`K1-1-*` / K2=`K2-K2-1-*`）
    // 尾部连字符保证边界安全（K1-1- 不误匹配 K1-10-/K1-11-）
    if (!key.includes(token)) continue
    if (!/conclusion|audit-note/i.test(key)) continue
    const text = (val?.remark ?? val?.conclusion ?? '') as string
    if (typeof text === 'string' && text.trim().length > 0) return true
  }
  return false
}

const conclusionSheets = computed(() =>
  allSheets.value
    .filter(s => K1_CONCLUSION_CODES.has(s.code))
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

// ─── 本循环底稿目录（K 循环其他科目，跨底稿跳转，对齐 E1） ─────────────────────
const cycleWorkpapers = ref<CycleWpCard[]>([])

/** 拉取本项目 K 循环 canonical 科目（源模板过滤污染），构建可跳转卡片网格。 */
async function loadCycleWorkpapers(): Promise<void> {
  cycleWorkpapers.value = await loadCycleWorkpaperCards(props.projectId, 'K', props.wpId)
}

/** 跨底稿跳转：同循环其他底稿 router.push 打开对应 WorkpaperEditor（未生成/当前不跳）。 */
function onCycleCardClick(wp: CycleWpCard): void {
  if (!wp.wp_id || wp.is_current || !props.projectId) return
  router.push({ name: 'WorkpaperEditor', params: { projectId: props.projectId, wpId: wp.wp_id } })
}

onMounted(loadCycleWorkpapers)
</script>

<style scoped>
.k1-tab-index {
  padding: 16px;
  font-size: var(--wp-font-size, 13px);
}

/* ─── 目录卡（对齐 E1TabDirectory） ─── */
.k1-dir { margin-bottom: 20px; }
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
.k1-arch { margin-top: 16px; }
.arch-header { display: flex; align-items: baseline; gap: 12px; margin-bottom: 12px; }
.arch-title { margin: 0; font-size: 16px; font-weight: 600; color: #303133; }
.arch-hint { font-size: 12px; color: #909399; }

/* ─── 本循环底稿目录（对齐 GtBIndex 循环 grid） ─── */
.k1-cycle { margin-top: 28px; }
.cycle-header { display: flex; align-items: baseline; gap: 12px; margin-bottom: 12px; }
.cycle-title { margin: 0; font-size: 16px; font-weight: 600; color: #303133; }
.cycle-hint { font-size: 12px; color: #909399; }
.cycle-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
  gap: 10px;
}
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
.cycle-card:hover {
  border-color: var(--gt-color-primary, #4b2d77);
  box-shadow: 0 2px 8px rgba(75, 45, 119, 0.12);
  transform: translateY(-2px);
}
.cycle-card.is-current {
  border-color: var(--gt-color-primary, #4b2d77);
  background: var(--gt-color-primary-bg, #f4f0fa);
  box-shadow: 0 0 0 1px var(--gt-color-primary, #4b2d77);
  cursor: default;
}
.cycle-card.is-disabled { opacity: 0.5; cursor: not-allowed; }
.cycle-card.is-disabled:hover { border-color: var(--gt-color-border-purple, #e8e4f0); box-shadow: none; transform: none; }
.cycle-card-top { display: flex; align-items: center; gap: 6px; }
.cycle-code { font-size: var(--wp-font-size, 13px); font-weight: 700; color: var(--gt-color-primary, #4b2d77); }
.cycle-current-tag { margin-left: auto; }
.cycle-name {
  font-size: var(--wp-font-size, 13px);
  line-height: 1.4;
  color: #303133;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
</style>
