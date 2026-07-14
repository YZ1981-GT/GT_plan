<script setup lang="ts">
/**
 * J1TabIndex — 应付职工薪酬底稿目录（对齐 D4/b-index 底稿架构范式）
 *
 * 复用 GtBArchitectureTree（4 阶段泳道卡片：审计计划/科目审定/实质性程序/披露与调整），
 * 由 J1 各 sheet 构造 navigation_rows 喂入。点击卡片 → inject('jumpToSection') 切换 sheet
 * （GtJ1 provide → emit navigate-sheet → GtWpRenderer 按 sheet_name.includes 匹配）。
 */
import { computed, inject } from 'vue'
import GtBArchitectureTree from '../../GtBArchitectureTree.vue'

const props = defineProps<{
  allResponses?: Map<string, { item_id: string; conclusion: string | null; remark: string | null }>
  isReadonly?: boolean
}>()

interface NavRow {
  content: string
  index_ref: string
  component_type: string
  progressKeys: string[]
}

/** J1 各 sheet → navigation_rows（content=完整 sheet 名，供 jumpToSection includes 匹配）。
 *  component_type 决定 GtBArchitectureTree 的阶段归类（程序表→审计计划 / 审定表→科目审定 /
 *  附注·调整→披露与调整 / 其余→实质性程序）。 */
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
const applicableCount = computed(() => progressRows.value.length)
const progressPercent = computed(() =>
  applicableCount.value === 0 ? 0 : Math.round((completedCount.value / applicableCount.value) * 100),
)

function handleNavigate(sheetName: string) {
  if (jumpToSection && sheetName) jumpToSection(sheetName)
}
</script>

<template>
  <div class="j1-tab-index">
    <!-- 编制进度条 -->
    <div class="progress-bar-section">
      <div class="progress-info">
        <span>编制进度</span>
        <span class="progress-text">{{ completedCount }} / {{ applicableCount }} ({{ progressPercent }}%)</span>
      </div>
      <el-progress :percentage="progressPercent" :stroke-width="8" :show-text="false" />
    </div>

    <!-- 底稿架构（4 阶段泳道卡片，复用 D4/b-index 范式） -->
    <div class="index-header">
      <h4 class="index-title">底稿架构</h4>
      <span class="index-hint">点击卡片可跳转至对应底稿</span>
    </div>
    <GtBArchitectureTree
      :active-sheet="''"
      :html-data="archHtmlData"
      @navigate="handleNavigate"
    />
  </div>
</template>

<style scoped>
.j1-tab-index {
  padding: 12px;
}
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
.progress-text {
  font-weight: 600;
  color: #303133;
}
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
.index-hint {
  font-size: 12px;
  color: #909399;
}
</style>
