<script setup lang="ts">
/**
 * J1TabIndex — 应付职工薪酬底稿目录（严格镜像 E1 标准）
 *
 * 结构：目录卡（标题+复核+编制/使用手册+进度→跨表结论口径→编制提示）
 *       + 底稿架构 4 阶段泳道（GtBArchitectureTree）+ 本循环底稿目录 grid。
 * 导航经 inject('jumpToSection')（GtJ1 provide → emit navigate-sheet）；消费主入口传入 allResponses。
 */
import { computed, inject, ref, onMounted, defineAsyncComponent } from 'vue'
import { useRouter } from 'vue-router'
import { loadCycleWorkpaperCards, type CycleWpCard } from '@/services/cycleDirectory'
import GtReviewTrigger from '../../GtReviewTrigger.vue'
import GtBArchitectureTree from '../../GtBArchitectureTree.vue'

const J1PreparationHandbookDialog = defineAsyncComponent(() => import('../J1PreparationHandbookDialog.vue'))

const props = defineProps<{
  wpId?: string
  projectId?: string
  allResponses?: Map<string, { item_id: string; conclusion: string | null; remark: string | null }>
  isReadonly?: boolean
}>()

const router = useRouter()

// ─── 编制/使用手册弹窗 ─────────────────────────────────────────────────────────
const handbookVisible = ref(false)
const handbookTab = ref<'preparation' | 'usage'>('preparation')
function openHandbook(tab: 'preparation' | 'usage') {
  handbookTab.value = tab
  handbookVisible.value = true
}

interface NavRow {
  content: string
  index_ref: string
  component_type: string
  progressKeys: string[]
}

/** J1 各 sheet → navigation_rows（content=完整 sheet 名，供 jumpToSection includes 匹配）。 */
const NAV_ROWS: NavRow[] = [
  { content: '应付职工薪酬实质性程序表 J1A', index_ref: 'J1A', component_type: 'a-program-console', progressKeys: [] },
  { content: '审定表J1-1', index_ref: 'J1-1', component_type: 'd-form-table', progressKeys: ['J1-adjudication-data'] },
  { content: '明细表J1-2', index_ref: 'J1-2', component_type: 'd-form-table', progressKeys: ['J1-detail-data'] },
  { content: '调整分录汇总表J1-3', index_ref: 'J1-3', component_type: 'd-form-table', progressKeys: ['J1-adjustment', 'J1-3'] },
  { content: '月度分析表J1-4', index_ref: 'J1-4', component_type: 'd-form-table', progressKeys: ['J1-monthly-data'] },
  { content: '与同行业对比分析表J1-5', index_ref: 'J1-5', component_type: 'd-form-table', progressKeys: ['J1-industry-data', 'J1-company-info'] },
  { content: '计提情况检查表J1-6', index_ref: 'J1-6', component_type: 'd-form-table', progressKeys: ['J1-accrual-check', 'J1-6'] },
  { content: '分配情况检查表J1-7', index_ref: 'J1-7', component_type: 'd-form-table', progressKeys: ['J1-allocation-check', 'J1-7'] },
  { content: '检查表J1-8', index_ref: 'J1-8', component_type: 'd-form-table', progressKeys: ['J1-general-check', 'J1-8'] },
  { content: '非货币性福利检查表J1-9', index_ref: 'J1-9', component_type: 'd-form-table', progressKeys: ['J1-non-monetary', 'J1-9'] },
  { content: '辞退福利检查表J1-10', index_ref: 'J1-10', component_type: 'd-form-table', progressKeys: ['J1-severance-check', 'J1-10'] },
  { content: '附注披露信息（上市公司）', index_ref: 'J1-附注上市', component_type: 'c-note-table', progressKeys: ['J1-disclosure-listed'] },
  { content: '附注披露信息（国有企业）', index_ref: 'J1-附注国企', component_type: 'c-note-table', progressKeys: ['J1-disclosure-soe'] },
  { content: 'IPO企业薪酬审计提示', index_ref: 'J1-IPO', component_type: 'h-static-doc', progressKeys: [] },
]

const jumpToSection = inject<((sheetName: string) => void) | null>('jumpToSection', null)

function rowStatus(row: NavRow): string {
  if (row.progressKeys.length === 0) return ''
  const map = props.allResponses
  if (!map || map.size === 0) return 'pending'
  const keys = [...map.keys()]
  const hasData = row.progressKeys.some(pk => map.has(pk) || keys.some(k => k.startsWith(pk)))
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
const totalCount = computed(() => progressRows.value.length)
const progressPercent = computed(() =>
  totalCount.value === 0 ? 0 : Math.round((completedCount.value / totalCount.value) * 100),
)

function handleNavigate(sheetName: string) {
  if (jumpToSection && sheetName) jumpToSection(sheetName)
}

// ─── 跨表结论口径看板 ─────────────────────────────────────────────────────────
/** 有审计结论的核心表（审定/明细/检查类；程序表、调整分录、附注、分析、IPO 不计入） */
interface ConclSheet { code: string; sheetKey: string }
const CONCLUSION_SHEETS: ConclSheet[] = [
  { code: 'J1-1', sheetKey: '审定表J1-1' },
  { code: 'J1-2', sheetKey: '明细表J1-2' },
  { code: 'J1-6', sheetKey: '计提情况检查表J1-6' },
  { code: 'J1-7', sheetKey: '分配情况检查表J1-7' },
  { code: 'J1-8', sheetKey: '检查表J1-8' },
]

/** key 含 `${code}-` 且匹配 /conclusion|audit-note|note/ 且文本非空即已填。 */
function isConclusionFilled(code: string): boolean {
  const map = props.allResponses
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

const conclusionSheets = computed(() =>
  CONCLUSION_SHEETS.map(s => ({ code: s.code, sheetKey: s.sheetKey, filled: isConclusionFilled(s.code) })),
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

// ─── 本循环底稿目录（J 循环其他科目，跨底稿跳转；canonical 源模板过滤污染） ───
const cycleWorkpapers = ref<CycleWpCard[]>([])
async function loadCycleWorkpapers(): Promise<void> {
  if (!props.projectId || !props.wpId) return
  cycleWorkpapers.value = await loadCycleWorkpaperCards(props.projectId, 'J', props.wpId)
}
function onCycleCardClick(wp: CycleWpCard): void {
  if (!wp.wp_id || wp.is_current || !props.projectId) return
  router.push({ name: 'WorkpaperEditor', params: { projectId: props.projectId, wpId: wp.wp_id } })
}
onMounted(loadCycleWorkpapers)
</script>

<template>
  <div class="j1-tab-index">
    <!-- ═══ 目录卡（标题 + 复核 + 编制/使用手册 + 进度条 → 跨表结论口径 → 编制提示） ═══ -->
    <div class="j1-dir">
      <div class="index-header">
        <h3 class="title">J1 底稿目录</h3>
        <GtReviewTrigger section-id="J1-index-directory" />
        <div class="handbook-btns">
          <el-button size="small" type="primary" plain @click="openHandbook('preparation')">📖 编制手册</el-button>
          <el-button size="small" @click="openHandbook('usage')">使用手册</el-button>
        </div>
        <div class="progress-wrap">
          <span>编制进度 {{ completedCount }}/{{ totalCount }}</span>
          <el-progress :percentage="progressPercent" :stroke-width="10" />
        </div>
      </div>

      <J1PreparationHandbookDialog v-model="handbookVisible" :initial-tab="handbookTab" />

      <div class="conclusion-board" data-testid="j1-conclusion-board">
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
        <ul>
          <li>应付职工薪酬为<strong>负债类贷方科目</strong>（2211）：期末 = 期初 + 计提 − 支付；按项目（工资/社保/公积金/工会/教育经费等）分类</li>
          <li>J1-6 计提检查（标准恰当）+ J1-7 分配检查（成本/费用去向正确）是核心程序</li>
          <li>辞退福利（J1-10）按 CAS9 在不能撤回时确认，利用精算专家（S12/S12A）；非货币性福利（J1-9）按公允价值计量</li>
          <li>审定期末回写 TB(2211) 并驱动附注披露；各表填妥"审计说明或结论"后目录标签转为"已填"</li>
        </ul>
      </details>
    </div>

    <!-- ═══ 底稿架构（4 阶段泳道） ═══ -->
    <div class="j1-arch">
      <div class="arch-header">
        <h4 class="arch-title">底稿架构</h4>
        <span class="arch-hint">点击卡片可跳转至对应底稿</span>
      </div>
      <GtBArchitectureTree
        :active-sheet="''"
        :html-data="archHtmlData"
        @navigate="handleNavigate"
      />
    </div>

    <!-- ═══ 本循环底稿目录（J 循环其他科目，可跳转） ═══ -->
    <div v-if="cycleWorkpapers.length" class="j1-cycle">
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
.j1-tab-index { padding: 16px; font-size: var(--wp-font-size, 13px); }

/* ─── 目录卡 ─── */
.j1-dir { margin-bottom: 20px; }
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
.j1-arch { margin-top: 16px; }
.arch-header { display: flex; align-items: baseline; gap: 12px; margin-bottom: 12px; }
.arch-title { margin: 0; font-size: 16px; font-weight: 600; color: #303133; }
.arch-hint { font-size: 12px; color: #909399; }

/* ─── 本循环底稿目录 ─── */
.j1-cycle { margin-top: 28px; }
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
