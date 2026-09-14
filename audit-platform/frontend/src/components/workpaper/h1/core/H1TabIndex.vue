<script setup lang="ts">
/**
 * H1TabIndex — 固定资产底稿目录（对齐 J1/D4 GtBArchitectureTree 范式）
 *
 * 4 阶段泳道：审计计划 / 科目审定 / 实质性程序 / 披露与调整
 * 点击卡片 → inject('jumpToSection') → GtH1 emit navigate-sheet
 */
import { computed, inject, ref, defineAsyncComponent } from 'vue'
import GtBArchitectureTree from '../../GtBArchitectureTree.vue'
import GtCycleDirExtras from '../../GtCycleDirExtras.vue'

const H1PreparationHandbookDialog = defineAsyncComponent(() => import('../H1PreparationHandbookDialog.vue'))

const props = defineProps<{
  wpId?: string
  projectId?: string
  allResponses?: Map<string, { item_id: string; conclusion: string | null; remark: string | null }>
  isReadonly?: boolean
}>()

interface NavRow {
  content: string
  index_ref: string
  component_type: string
  /** 精确 item_id 或前缀；用精确匹配 / `${pk}-` 前缀，避免 H1-1 误伤 H1-10 */
  progressKeys: string[]
}

const NAV_ROWS: NavRow[] = [
  { content: '固定资产审计程序表H1A', index_ref: 'H1A', component_type: 'a-program-console', progressKeys: ['H1A-c6-prerequisite'] },
  { content: '审定表H1-1', index_ref: 'H1-1', component_type: 'd-form-table', progressKeys: ['H1-1-cost-rows', 'H1-1-dep-rows'] },
  { content: '明细表H1-2', index_ref: 'H1-2', component_type: 'd-form-table', progressKeys: ['H1-2-rows'] },
  { content: '调整分录汇总H1-3', index_ref: 'H1-3', component_type: 'd-form-table', progressKeys: ['H1-3-entries', 'H1-3-rows'] },
  { content: '闲置检查表H1-4', index_ref: 'H1-4', component_type: 'd-form-table', progressKeys: ['H1-4-rows'] },
  { content: '会计政策估计检查表H1-5', index_ref: 'H1-5', component_type: 'd-form-table', progressKeys: ['H1-5-rows'] },
  { content: '分析表H1-6', index_ref: 'H1-6', component_type: 'd-form-table', progressKeys: ['H1-6-rows'] },
  { content: '增加检查表H1-7', index_ref: 'H1-7', component_type: 'd-form-table', progressKeys: ['H1-7-rows'] },
  { content: '减少检查表H1-8', index_ref: 'H1-8', component_type: 'd-form-table', progressKeys: ['H1-8-rows'] },
  { content: '监盘计划H1-9', index_ref: 'H1-9', component_type: 'd-form-table', progressKeys: ['H1-9-form', 'H1-9-info', 'H1-9-selections'] },
  { content: '盘点检查表H1-10', index_ref: 'H1-10', component_type: 'd-form-table', progressKeys: ['H1-10-rows', 'H1-10-meta'] },
  { content: '监盘小结H1-11', index_ref: 'H1-11', component_type: 'd-form-table', progressKeys: ['H1-11-form', 'H1-11-note', 'H1-11-conclusion'] },
  { content: '折旧测算表H1-12', index_ref: 'H1-12', component_type: 'd-form-table', progressKeys: ['H1-12-rows', 'H1-12-A-rows', 'H1-12-B-rows', 'H1-12-C-rows'] },
  { content: '折旧分配分析表H1-13', index_ref: 'H1-13', component_type: 'd-form-table', progressKeys: ['H1-13-rows'] },
  { content: '减值测算表H1-14', index_ref: 'H1-14', component_type: 'd-form-table', progressKeys: ['H1-14-rows'] },
  { content: '可收回金额测试表H1-15', index_ref: 'H1-15', component_type: 'd-form-table', progressKeys: ['H1-15-rows'] },
  { content: '房屋建筑物权属检查表H1-16', index_ref: 'H1-16', component_type: 'd-form-table', progressKeys: ['H1-16-rows'] },
  { content: '运输设备权属检查表H1-17', index_ref: 'H1-17', component_type: 'd-form-table', progressKeys: ['H1-17-rows'] },
  { content: '关联交易检查表H1-18', index_ref: 'H1-18', component_type: 'd-form-table', progressKeys: ['H1-18-rows'] },
  { content: '经营租出固定资产检查表H1-19', index_ref: 'H1-19', component_type: 'd-form-table', progressKeys: ['H1-19-rows'] },
  { content: '融资租出固定资产检查表H1-20', index_ref: 'H1-20', component_type: 'd-form-table', progressKeys: ['H1-20-rows'] },
  { content: '附注披露信息（上市公司）', index_ref: 'H1-附注上市', component_type: 'c-note-table', progressKeys: ['H1-listed-summary', 'H1-listed-movement'] },
  { content: '附注披露信息（国有企业）', index_ref: 'H1-附注国企', component_type: 'c-note-table', progressKeys: ['H1-soe-summary', 'H1-soe-movement', 'H1-disc-soe-summary', 'H1-disc-soe-movement'] },
]

const jumpToSection = inject<((sheetName: string) => void) | null>('jumpToSection', null)

function keyMatches(mapKey: string, pk: string): boolean {
  if (mapKey === pk) return true
  // 允许 H1-1-cost-rows 匹配 progressKey H1-1-，但禁止 H1-1 匹配 H1-10
  if (pk.endsWith('-')) return mapKey.startsWith(pk)
  return mapKey.startsWith(`${pk}-`) || mapKey.startsWith(`${pk}_`)
}

function rowStatus(row: NavRow): string {
  if (row.progressKeys.length === 0) return ''
  const map = props.allResponses
  if (!map || map.size === 0) return 'pending'
  const keys = [...map.keys()]
  const hasData = row.progressKeys.some(
    (pk) => map.has(pk) || keys.some((k) => keyMatches(k, pk)),
  )
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

const progressRows = computed(() => NAV_ROWS.filter((r) => r.progressKeys.length > 0))
const completedCount = computed(() => progressRows.value.filter((r) => rowStatus(r) === 'completed').length)
const applicableCount = computed(() => progressRows.value.length)
const progressPercent = computed(() =>
  applicableCount.value === 0 ? 0 : Math.round((completedCount.value / applicableCount.value) * 100),
)

function handleNavigate(sheetName: string) {
  if (jumpToSection && sheetName) jumpToSection(sheetName)
}

// ─── E1 标准加法式增强：目录卡 + 结论看板 + 本循环 grid ───────────────────
/** 结论看板/跳转值：H1 导航机制为 inject('jumpToSection')，navValue = 完整 sheet 名（content）。 */
const dirSheets = computed(() =>
  NAV_ROWS.map((r) => ({ code: r.index_ref, navValue: r.content, name: r.content })),
)

const handbookVisible = ref(false)
const handbookTab = ref<'preparation' | 'usage'>('preparation')
function openHandbook(tab: 'preparation' | 'usage') {
  handbookTab.value = tab
  handbookVisible.value = true
}
</script>

<template>
  <div class="h1-tab-index">
    <!-- E1 标准加法式增强：目录卡 + 结论看板 + 本循环 grid -->
    <GtCycleDirExtras
      wp-code="H1"
      cycle-letter="H"
      :wp-id="props.wpId"
      :project-id="props.projectId"
      :all-responses="props.allResponses"
      :sheets="dirSheets"
      @navigate="handleNavigate"
      @open-handbook="openHandbook"
    />
    <H1PreparationHandbookDialog v-model="handbookVisible" :initial-tab="handbookTab" />

    <el-alert
      type="info"
      :closable="false"
      show-icon
      class="guide-alert"
      title="建议顺序：H1A 程序 → H1-1 审定 → H1-2 明细 → 检查表(H1-4~8/16~20) → 折旧减值(H1-12~15) → 监盘(H1-9~11) → 附注披露（上市/国企）。"
    />

    <div class="progress-bar-section">
      <div class="progress-info">
        <span>编制进度</span>
        <span class="progress-text">{{ completedCount }} / {{ applicableCount }} ({{ progressPercent }}%)</span>
      </div>
      <el-progress :percentage="progressPercent" :stroke-width="8" :show-text="false" />
    </div>

    <div class="index-header">
      <h4 class="index-title">底稿架构</h4>
      <span class="index-hint">点击卡片跳转对应 sheet</span>
    </div>
    <GtBArchitectureTree
      :active-sheet="''"
      :html-data="archHtmlData"
      @navigate="handleNavigate"
    />
  </div>
</template>

<style scoped>
.h1-tab-index { padding: 12px; }
.guide-alert { margin-bottom: 12px; }
.progress-bar-section {
  margin-bottom: 16px;
  padding: 12px 16px;
  background: #f5f7fa;
  border-radius: 6px;
}
.progress-info {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
  font-size: var(--wp-font-size, 13px);
  color: #606266;
}
.progress-text { font-weight: 600; color: #303133; }
.index-header {
  display: flex;
  align-items: baseline;
  gap: 12px;
  margin-bottom: 12px;
}
.index-title {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  color: #303133;
}
.index-hint { font-size: 12px; color: #909399; }
</style>
