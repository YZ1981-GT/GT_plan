<script setup lang="ts">
/**
 * J2TabIndex — 长期应付职工薪酬（设定受益计划）底稿目录（严格镜像 E1 标准）
 *
 * 结构：目录卡（标题+复核+编制/使用手册+进度→跨表结论口径→编制提示）
 *       + 底稿架构 4 阶段泳道（GtBArchitectureTree）+ 本循环底稿目录 grid。
 * 导航经 inject('jumpToSection')（GtJ2 provide → emit navigate-sheet）；消费主入口传入 allResponses。
 */
import { computed, inject, ref, onMounted, defineAsyncComponent } from 'vue'
import { useRouter } from 'vue-router'
import { loadCycleWorkpaperCards, type CycleWpCard } from '@/services/cycleDirectory'
import GtReviewTrigger from '../GtReviewTrigger.vue'
import GtBArchitectureTree from '../GtBArchitectureTree.vue'

const J2PreparationHandbookDialog = defineAsyncComponent(() => import('./J2PreparationHandbookDialog.vue'))

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

/** J2 各 sheet → navigation_rows（content=完整 sheet 名，供 jumpToSection includes 匹配）。 */
const NAV_ROWS: NavRow[] = [
  { content: '长期应付职工薪酬实质性程序表 J2A', index_ref: 'J2A', component_type: 'a-program-console', progressKeys: [] },
  { content: '审定表J2-1', index_ref: 'J2-1', component_type: 'd-form-table', progressKeys: ['J2-adjudication', 'J2-1'] },
  { content: '明细表J2-2', index_ref: 'J2-2', component_type: 'd-form-table', progressKeys: ['J2-detail', 'J2-2'] },
  { content: '调整分录汇总表J2-3', index_ref: 'J2-3', component_type: 'd-form-table', progressKeys: ['J2-adjustment', 'J2-3'] },
  { content: '计提情况检查表J2-4', index_ref: 'J2-4', component_type: 'd-form-table', progressKeys: ['J2-accrual', 'J2-4'] },
  { content: '附注披露信息（上市公司）', index_ref: 'J2-附注上市', component_type: 'c-note-table', progressKeys: ['J2-disclosure-listed'] },
  { content: '附注披露信息（国有企业）', index_ref: 'J2-附注国企', component_type: 'c-note-table', progressKeys: ['J2-disclosure-soe'] },
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
interface ConclSheet { code: string; sheetKey: string }
const CONCLUSION_SHEETS: ConclSheet[] = [
  { code: 'J2-1', sheetKey: '审定表J2-1' },
  { code: 'J2-2', sheetKey: '明细表J2-2' },
  { code: 'J2-4', sheetKey: '计提情况检查表J2-4' },
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
  <div class="j2-tab-index">
    <!-- ═══ 目录卡 ═══ -->
    <div class="j2-dir">
      <div class="index-header">
        <h3 class="title">J2 底稿目录</h3>
        <GtReviewTrigger section-id="J2-index-directory" />
        <div class="handbook-btns">
          <el-button size="small" type="primary" plain @click="openHandbook('preparation')">📖 编制手册</el-button>
          <el-button size="small" @click="openHandbook('usage')">使用手册</el-button>
        </div>
        <div class="progress-wrap">
          <span>编制进度 {{ completedCount }}/{{ totalCount }}</span>
          <el-progress :percentage="progressPercent" :stroke-width="10" />
        </div>
      </div>

      <J2PreparationHandbookDialog v-model="handbookVisible" :initial-tab="handbookTab" />

      <div class="conclusion-board" data-testid="j2-conclusion-board">
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
          <li>设定受益计划按 <strong>CAS9</strong>：DBO（义务现值）− 计划资产公允价值 = 净负债/净资产；审定 = 未审 + AJE + RJE</li>
          <li>J2-2 按六要素录变动（服务成本/利息净额/重计量），J2-4 检查精算假设与计量恰当（利用精算专家 S12/S12A）</li>
          <li>重计量部分计入 <strong>M9 其他综合收益（OCI）</strong>；审定期末回写 TB 并驱动附注披露</li>
          <li>各表填妥"审计说明或结论"后目录标签转为"已填"</li>
        </ul>
      </details>
    </div>

    <!-- ═══ 底稿架构（4 阶段泳道） ═══ -->
    <div class="j2-arch">
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
    <div v-if="cycleWorkpapers.length" class="j2-cycle">
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
.j2-tab-index { padding: 16px; font-size: var(--wp-font-size, 13px); }

.j2-dir { margin-bottom: 20px; }
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

.j2-arch { margin-top: 16px; }
.arch-header { display: flex; align-items: baseline; gap: 12px; margin-bottom: 12px; }
.arch-title { margin: 0; font-size: 16px; font-weight: 600; color: #303133; }
.arch-hint { font-size: 12px; color: #909399; }

.j2-cycle { margin-top: 28px; }
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
