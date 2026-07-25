<template>
  <div class="i2-tab-index">
    <!-- 编制信息由页面级头部统一渲染，此处不重复 -->

    <!-- ═══ 目录卡（标题 + 复核 + 编制/使用手册 + 进度条 → 跨表结论口径 → 编制提示） ═══ -->
    <div class="i2-dir">
      <div class="index-header">
        <h3 class="title">I2 开发支出底稿目录</h3>
        <GtReviewTrigger section-id="I2-index-directory" />
        <div class="handbook-btns">
          <el-button size="small" type="primary" plain @click="openHandbook('preparation')">📖 编制手册</el-button>
          <el-button size="small" @click="openHandbook('usage')">使用手册</el-button>
        </div>
        <div class="progress-wrap">
          <span>编制进度 {{ completedCount }}/{{ totalCount }}</span>
          <el-progress :percentage="progressPercent" :stroke-width="10" />
        </div>
      </div>

      <I2PreparationHandbookDialog v-model="handbookVisible" :initial-tab="handbookTab" />

      <div class="conclusion-board" data-testid="i2-conclusion-board">
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
          <li>开发支出（1717）资产借方：期末 = 期初 + 借 − 贷；审定回写 TB(1717)</li>
          <li>I2-6 CAS6 五条件是审计重点：①技术可行性②完成意图③经济利益方式④资源支持⑤可靠计量（须同时满足）</li>
          <li>I6↔I2 双向联动：研发费用（I6 费用化）+ 开发支出（I2 资本化）= 研发总额</li>
          <li>推荐工作流：I2A → I2-2 明细 → I2-6 资本化判断 → I2-8~12 检查 → I2-13/14 截止 → I2-15/16 减值 → I2-3 调整回写 I2-1 → 附注</li>
          <li>各表填妥"审计说明或结论"后目录标签转为"已填"</li>
        </ul>
      </details>
    </div>

    <!-- ═══ 底稿架构（4 阶段泳道） ═══ -->
    <div class="i2-arch">
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
    <div v-if="cycleWorkpapers.length" class="i2-cycle">
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
 * I2TabIndex.vue — I2 开发支出底稿目录（严格镜像 I1/E1 标准）
 *
 * 结构：目录卡（标题+复核+编制/使用手册+进度→跨表结论口径→编制提示）
 *       + 底稿架构 4 阶段泳道（GtBArchitectureTree）+ 本循环底稿目录 grid。
 * 编制信息由页面级头部渲染，此处不重复。消费主入口传入的 allResponses，emit navigate-sheet。
 */
import { computed, ref, onMounted, defineAsyncComponent } from 'vue'
import { useRouter } from 'vue-router'
import { loadCycleWorkpaperCards, type CycleWpCard } from '@/services/cycleDirectory'
import GtReviewTrigger from '../../GtReviewTrigger.vue'
import GtBArchitectureTree from '../../GtBArchitectureTree.vue'

const I2PreparationHandbookDialog = defineAsyncComponent(() => import('../I2PreparationHandbookDialog.vue'))

const props = defineProps<{
  sheetName?: string
  wpId: string
  projectId: string
  allResponses?: Map<string, any>
  isReadonly?: boolean
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

interface SheetRow {
  name: string
  code: string
  sheetKey: string
  prefix: string
  conclPrefix?: string
}

/** I2 各 sheet（sheetKey 沿用主入口 currentSheet 分发所用字符串）。 */
const allSheets = computed<SheetRow[]>(() => [
  { name: '开发支出实质性程序表', code: 'I2A', sheetKey: 'Procedure_Table_I2A 实质性程序表', prefix: 'I2A-' },
  { name: '审定表', code: 'I2-1', sheetKey: 'Adjudication_I2_1 审定表', prefix: 'I2-1-', conclPrefix: 'I2-1-' },
  { name: '明细表', code: 'I2-2', sheetKey: 'Detail_I2_2 明细表', prefix: 'I2-2-', conclPrefix: 'I2-2-' },
  { name: '调整分录汇总', code: 'I2-3', sheetKey: 'Adjustment_I2_3 调整分录', prefix: 'I2-3-' },
  { name: '会计政策检查', code: 'I2-4', sheetKey: 'Policy_Check_I2_4 会计政策检查', prefix: 'I2-4-', conclPrefix: 'I2-4-' },
  { name: '实质性分析', code: 'I2-5', sheetKey: 'Analysis_I2_5 实质性分析', prefix: 'I2-5-', conclPrefix: 'I2-5-' },
  { name: '研发项目资本化时点判断', code: 'I2-6', sheetKey: 'Capitalization_I2_6 资本化时点判断', prefix: 'I2-6-', conclPrefix: 'I2-6-' },
  { name: '研发项目构成明细表', code: 'I2-7', sheetKey: 'Project_Detail_I2_7 项目构成', prefix: 'I2-7-', conclPrefix: 'I2-7-' },
  { name: '研发材料投入检查表', code: 'I2-8', sheetKey: 'Material_Check_I2_8 材料投入', prefix: 'I2-8-', conclPrefix: 'I2-8-' },
  { name: '研发人员认定检查表', code: 'I2-9', sheetKey: 'Staff_Check_I2_9 人员认定', prefix: 'I2-9-', conclPrefix: 'I2-9-' },
  { name: '研发人员工时检查表', code: 'I2-10', sheetKey: 'WorkHour_Check_I2_10 工时检查', prefix: 'I2-10-', conclPrefix: 'I2-10-' },
  { name: '委外研发检查表', code: 'I2-11', sheetKey: 'Outsource_Check_I2_11 委外研发', prefix: 'I2-11-', conclPrefix: 'I2-11-' },
  { name: '针对性检查表', code: 'I2-12', sheetKey: 'Targeted_Check_I2_12 针对性检查', prefix: 'I2-12-', conclPrefix: 'I2-12-' },
  { name: '截止性测试（账到单据）', code: 'I2-13', sheetKey: 'Cutoff_Forward_I2_13 截止账到单据', prefix: 'I2-13-', conclPrefix: 'I2-13-' },
  { name: '截止性测试（单据到账）', code: 'I2-14', sheetKey: 'Cutoff_Backward_I2_14 截止单据到账', prefix: 'I2-14-', conclPrefix: 'I2-14-' },
  { name: '减值准备测试表', code: 'I2-15', sheetKey: 'Impairment_I2_15 减值测试', prefix: 'I2-15-', conclPrefix: 'I2-15-' },
  { name: '可收回金额测试', code: 'I2-16', sheetKey: 'Recoverable_I2_16 可收回金额', prefix: 'I2-16-', conclPrefix: 'I2-16-' },
  { name: '附注披露信息（上市公司）', code: '附注上市', sheetKey: 'Disclosure_Listed 附注上市', prefix: 'I2-disc-listed-' },
  { name: '附注披露信息（国有企业）', code: '附注国企', sheetKey: 'Disclosure_SOE 附注国企', prefix: 'I2-disc-soe-' },
])

// ─── 进度计算 ─────────────────────────────────────────────────────────────────
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

const totalCount = computed(() => allSheets.value.length)
const completedCount = computed(() => allSheets.value.filter(r => calcSheetProgress(r.prefix, 3) >= 100).length)
const progressPercent = computed(() => {
  if (totalCount.value === 0) return 0
  const avg = allSheets.value.reduce((sum, r) => sum + calcSheetProgress(r.prefix, 3), 0) / totalCount.value
  return Math.round(avg)
})

// ─── 底稿架构泳道 ─────────────────────────────────────────────────────────────
const COMPONENT_TYPE_MAP: Record<string, string> = {
  I2A: 'a-program-console',
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
const I2_CONCLUSION_CODES = new Set([
  'I2-1', 'I2-2', 'I2-4', 'I2-5', 'I2-6', 'I2-7', 'I2-8', 'I2-9', 'I2-10', 'I2-11', 'I2-12', 'I2-13', 'I2-14', 'I2-15', 'I2-16',
])

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
    .filter(s => s.conclPrefix && I2_CONCLUSION_CODES.has(s.code))
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
.i2-tab-index { padding: 16px; font-size: var(--wp-font-size, 13px); }

.i2-dir { margin-bottom: 20px; }
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

.i2-arch { margin-top: 16px; }
.arch-header { display: flex; align-items: baseline; gap: 12px; margin-bottom: 12px; }
.arch-title { margin: 0; font-size: 16px; font-weight: 600; color: #303133; }
.arch-hint { font-size: 12px; color: #909399; }

.i2-cycle { margin-top: 28px; }
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
