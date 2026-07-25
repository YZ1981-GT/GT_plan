<template>
  <div class="i1-tab-index">
    <!-- 编制信息由页面级头部统一渲染，此处不重复 -->

    <!-- ═══ 目录卡（标题 + 复核 + 编制/使用手册 + 进度条 → 跨表结论口径 → 编制提示） ═══ -->
    <div class="i1-dir">
      <div class="index-header">
        <h3 class="title">I1 无形资产底稿目录</h3>
        <GtReviewTrigger section-id="I1-index-directory" />
        <div class="handbook-btns">
          <el-button size="small" type="primary" plain @click="openHandbook('preparation')">📖 编制手册</el-button>
          <el-button size="small" @click="openHandbook('usage')">使用手册</el-button>
        </div>
        <div class="progress-wrap">
          <span>编制进度 {{ completedCount }}/{{ totalCount }}</span>
          <el-progress :percentage="progressPercent" :stroke-width="10" />
        </div>
      </div>

      <I1PreparationHandbookDialog v-model="handbookVisible" :initial-tab="handbookTab" />

      <div class="conclusion-board" data-testid="i1-conclusion-board">
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
          <li>三科目三角勾稽：<strong>账面净值 = 原值(1701) − 累计摊销(1702) − 减值准备(1703)</strong>；1701 资产借方(期末=期初+借−贷)，1702/1703 备抵贷方(期末=期初+贷−借)</li>
          <li>推荐工作流：I1A 程序 → I1-2 明细 → I1-4/7/8 政策·寿命·权属 → I1-9 分配 + I1-10/11 摊销测算 → I1-12/13 减值 → I1-5/6 增减 → I1-3 调整回写 I1-1 → 附注披露</li>
          <li>摊销测算双分支：I1-10（不含减值）与 I1-11（含减值）二选一，结果与 I1-9 分配去向配平</li>
          <li>审定合计回写 TB(1701/1702/1703) 并驱动附注披露；各表填妥"审计说明或结论"后目录标签转为"已填"</li>
        </ul>
      </details>
    </div>

    <!-- ═══ 底稿架构（4 阶段泳道） ═══ -->
    <div class="i1-arch">
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

    <!-- ═══ 本循环底稿目录（I 循环其他科目，可跳转） ═══ -->
    <div v-if="cycleWorkpapers.length" class="i1-cycle">
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
 * I1TabIndex.vue — I1 无形资产底稿目录（严格镜像 K1/L1/E1 标准）
 *
 * 结构：目录卡（标题+复核+编制/使用手册+进度→跨表结论口径→编制提示）
 *       + 底稿架构 4 阶段泳道（GtBArchitectureTree）+ 本循环底稿目录 grid。
 * 编制信息由页面级头部渲染，此处不重复。消费主入口传入的 allResponses，emit navigate-sheet。
 *
 * 三科目三角勾稽（1701 无形资产 / 1702 累计摊销 / 1703 减值准备）：净值=原值−摊销−减值。
 *
 * 🔴 I1 各表审计说明/结论 item_id 前缀经实证：审定表 I1-1 用 I1-adj-（I1-adj-audit-note/-audit-conclusion），
 *    其余 sheet 用 I1-{N}-（-audit-note/-audit-conclusion/-conclusion/-note）；conclPrefix 携真实前缀。
 */
import { computed, ref, onMounted, defineAsyncComponent } from 'vue'
import { useRouter } from 'vue-router'
import { loadCycleWorkpaperCards, type CycleWpCard } from '@/services/cycleDirectory'
import GtReviewTrigger from '../../GtReviewTrigger.vue'
import GtBArchitectureTree from '../../GtBArchitectureTree.vue'

const I1PreparationHandbookDialog = defineAsyncComponent(() => import('../I1PreparationHandbookDialog.vue'))

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
  name: string
  code: string
  sheetKey: string
  /** 数据 item_id 前缀（用于进度计算） */
  prefix: string
  /** 审计说明/结论存储键前缀（仅结论核心表有） */
  conclPrefix?: string
}

/** 按 responses 中以指定前缀存储的字段数计算完成度。 */
function calcSheetProgress(prefix: string, expectedFields: number): number {
  const map = props.allResponses
  if (!map || map.size === 0) return 0
  let count = 0
  for (const [key, val] of map.entries()) {
    if (!key.startsWith(prefix)) continue
    const text = (val?.remark ?? val?.conclusion ?? '') as any
    if (text != null && String(text).trim().length > 0) count++
  }
  if (count === 0) return 0
  if (count >= expectedFields) return 100
  return Math.min(Math.round((count / expectedFields) * 100), 99)
}

const allSheets = computed<SheetRow[]>(() => [
  { name: '无形资产实质性程序表', code: 'I1A', sheetKey: '无形资产实质性程序表I1A', prefix: 'I1A-' },
  { name: '审定表（原值/累计摊销/减值三科目）', code: 'I1-1', sheetKey: '审定表I1', prefix: 'I1-adj-', conclPrefix: 'I1-adj-' },
  { name: '明细表（逐项登记）', code: 'I1-2', sheetKey: '明细表I1-2', prefix: 'I1-2-', conclPrefix: 'I1-2-' },
  { name: '调整分录汇总', code: 'I1-3', sheetKey: '调整分录汇总I1-3', prefix: 'I1-3-' },
  { name: '摊销减值政策检查表', code: 'I1-4', sheetKey: '无形资产摊销减值政策检查表I1-4', prefix: 'I1-4-', conclPrefix: 'I1-4-' },
  { name: '增加检查表', code: 'I1-5', sheetKey: '无形资产增加检查表I1-5', prefix: 'I1-5-', conclPrefix: 'I1-5-' },
  { name: '减少明细表', code: 'I1-6', sheetKey: '无形资产减少明细表I1-6', prefix: 'I1-6-', conclPrefix: 'I1-6-' },
  { name: '使用寿命检查表', code: 'I1-7', sheetKey: '使用寿命检查表I1-7', prefix: 'I1-7-', conclPrefix: 'I1-7-' },
  { name: '权属检查表', code: 'I1-8', sheetKey: '无形资产权属检查表I1-8', prefix: 'I1-8-', conclPrefix: 'I1-8-' },
  { name: '摊销分配分析表', code: 'I1-9', sheetKey: '摊销分配分析表I1-9', prefix: 'I1-9-', conclPrefix: 'I1-9-' },
  { name: '摊销测算表（不含减值）', code: 'I1-10', sheetKey: '摊销测算表（不含减值）I1-10', prefix: 'I1-10-', conclPrefix: 'I1-10-' },
  { name: '摊销测算表（含减值）', code: 'I1-11', sheetKey: '摊销测算表（含减值）I1-11', prefix: 'I1-11-', conclPrefix: 'I1-11-' },
  { name: '减值准备测试表', code: 'I1-12', sheetKey: '减值准备测试表I1-12', prefix: 'I1-12-', conclPrefix: 'I1-12-' },
  { name: '可收回金额测试（DCF）', code: 'I1-13', sheetKey: '可收回金额测试I1-13', prefix: 'I1-13-', conclPrefix: 'I1-13-' },
  { name: '附注披露信息（上市公司）', code: '附注上市', sheetKey: '附注披露信息（上市公司）', prefix: 'I1-disc-L-' },
  { name: '附注披露信息（国有企业）', code: '附注国企', sheetKey: '附注披露信息（国有企业）', prefix: 'I1-disc-S-' },
])

// ─── 进度计算 ─────────────────────────────────────────────────────────────────
const totalCount = computed(() => allSheets.value.length)
const completedCount = computed(() => allSheets.value.filter(r => calcSheetProgress(r.prefix, 3) >= 100).length)
const progressPercent = computed(() => {
  if (totalCount.value === 0) return 0
  const avg = allSheets.value.reduce((sum, r) => sum + calcSheetProgress(r.prefix, 3), 0) / totalCount.value
  return Math.round(avg)
})

// ─── 底稿架构泳道（GtBArchitectureTree 数据源） ───────────────────────────────
const COMPONENT_TYPE_MAP: Record<string, string> = {
  I1A: 'a-program-console',
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
    status: sheetStatus(calcSheetProgress(s.prefix, 3)),
  })),
}))

// ─── 跨表结论口径看板 ─────────────────────────────────────────────────────────
/** 有审计结论/说明的核心表（程序表、调整分录、附注不计入） */
const I1_CONCLUSION_CODES = new Set([
  'I1-1', 'I1-2', 'I1-4', 'I1-5', 'I1-6', 'I1-7', 'I1-8', 'I1-9', 'I1-10', 'I1-11', 'I1-12', 'I1-13',
])

/**
 * 按各表真实 conclPrefix 判定审计说明/结论是否已填。
 * key 含 conclPrefix 且匹配 /conclusion|audit-note|note/ 且文本非空即为已填。
 */
function isConclusionFilled(conclPrefix: string): boolean {
  const map = props.allResponses
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
    .filter(s => s.conclPrefix && I1_CONCLUSION_CODES.has(s.code))
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
  if (sheetName) emit('navigate-sheet', sheetName)
}

// ─── 本循环底稿目录（I 循环其他科目，跨底稿跳转；canonical 源模板过滤污染） ───
const cycleWorkpapers = ref<CycleWpCard[]>([])
async function loadCycleWorkpapers(): Promise<void> {
  cycleWorkpapers.value = await loadCycleWorkpaperCards(props.projectId, 'I', props.wpId)
}
function onCycleCardClick(wp: CycleWpCard): void {
  if (!wp.wp_id || wp.is_current || !props.projectId) return
  router.push({ name: 'WorkpaperEditor', params: { projectId: props.projectId, wpId: wp.wp_id } })
}
onMounted(loadCycleWorkpapers)
</script>

<style scoped>
.i1-tab-index {
  padding: 16px;
  font-size: var(--wp-font-size, 13px);
}

/* ─── 目录卡 ─── */
.i1-dir { margin-bottom: 20px; }
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
.i1-arch { margin-top: 16px; }
.arch-header { display: flex; align-items: baseline; gap: 12px; margin-bottom: 12px; }
.arch-title { margin: 0; font-size: 16px; font-weight: 600; color: #303133; }
.arch-hint { font-size: 12px; color: #909399; }

/* ─── 本循环底稿目录 ─── */
.i1-cycle { margin-top: 28px; }
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
