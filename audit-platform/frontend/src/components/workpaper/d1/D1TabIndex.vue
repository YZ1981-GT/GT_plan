<script setup lang="ts">
/**
 * D1TabIndex — 应收票据底稿目录（对齐 J1/D4 GtBArchitectureTree 范式）
 *
 * 复用 GtBArchitectureTree（4 阶段泳道卡片：审计计划/科目审定/实质性程序/披露与调整），
 * 由 D1 各 sheet 构造 navigation_rows 喂入。点击卡片 → inject('jumpToSection') 切换 sheet。
 */
import { computed, inject } from 'vue'
import GtBArchitectureTree from '../GtBArchitectureTree.vue'
import { D1_INDEX_ROWS, resolveD1SheetLabel } from '../composables/d1SheetLabels'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
  availableSheets?: Array<{ sheet_name?: string }>
}>()

interface NavRow {
  content: string
  index_ref: string
  component_type: string
  progressKeys: string[]
}

/**
 * D1 各 sheet → navigation_rows
 * component_type 决定 GtBArchitectureTree 阶段归类：
 * - a-program-console → 审计计划
 * - d-form-table (审定表) → 科目审定
 * - c-note-table → 披露与调整
 * - 其余 → 实质性程序
 */
const NAV_ROWS: NavRow[] = [
  // 审计计划
  { content: '应收票据实质性程序表 D1A', index_ref: 'D1A', component_type: 'a-program-console', progressKeys: [] },
  // 科目审定
  { content: '审定表D1-1', index_ref: 'D1-1', component_type: 'd-form-table', progressKeys: ['D1-adj-'] },
  // 实质性程序
  { content: '按类别明细表D1-2', index_ref: 'D1-2', component_type: 'd-form-table-detail', progressKeys: ['D1-cat-rows'] },
  { content: '按客户明细表D1-3', index_ref: 'D1-3', component_type: 'd-form-table-detail', progressKeys: ['D1-cust-rows'] },
  { content: '坏账准备D1-4', index_ref: 'D1-4', component_type: 'd-form-table-detail', progressKeys: ['D1-bd-individual-rows', 'D1-bd-portfolio-rows'] },
  { content: '调整分录D1-5', index_ref: 'D1-5', component_type: 'd-form-table-detail', progressKeys: ['D1-entry-rows'] },
  { content: '基准日后应收款项回收D1-6', index_ref: 'D1-6', component_type: 'd-form-table-detail', progressKeys: ['D1-bm-basis-rows'] },
  { content: '票据备查簿核对D1-7', index_ref: 'D1-7', component_type: 'd-form-table-detail', progressKeys: ['D1-memo-rows'] },
  { content: '贴现背书明细D1-8', index_ref: 'D1-8', component_type: 'd-form-table-detail', progressKeys: ['D1-endorse-discount-rows', 'D1-endorse-transfer-rows'] },
  { content: '利息计算检查D1-9', index_ref: 'D1-9', component_type: 'd-form-table-detail', progressKeys: ['D1-interest-rows'] },
  { content: '票据监盘D1-10', index_ref: 'D1-10', component_type: 'd-form-table-detail', progressKeys: ['D1-inventory-rows'] },
  { content: '关联方D1-11', index_ref: 'D1-11', component_type: 'd-form-table-detail', progressKeys: ['D1-rp-rows'] },
  { content: '质押检查D1-12', index_ref: 'D1-12', component_type: 'd-form-table-detail', progressKeys: ['D1-pledge-rows'] },
  { content: '抽凭检查D1-13', index_ref: 'D1-13', component_type: 'd-form-table-detail', progressKeys: ['D1-sampling-vouching-rows', 'D1-sampling-specific-samples'] },
  { content: '会计政策检查D1-14', index_ref: 'D1-14', component_type: 'd-form-table-detail', progressKeys: ['D1-policy-paragraphs'] },
  { content: 'ECL减值模型D1-15', index_ref: 'D1-15', component_type: 'd-form-table-detail', progressKeys: ['D1-ecl-portfolio-rows', 'D1-ecl-individual-rows'] },
  { content: '核销与转回D1-16', index_ref: 'D1-16', component_type: 'd-form-table-detail', progressKeys: ['D1-writeoff-reversal-rows', 'D1-writeoff-writeoff-rows'] },
  // 披露与调整
  { content: '附注披露信息（上市公司）', index_ref: '附注上市', component_type: 'c-note-table', progressKeys: ['D1-disc-'] },
  { content: '附注披露信息（国有企业）', index_ref: '附注国企', component_type: 'c-note-table', progressKeys: ['D1-disc-'] },
]

const jumpToSection = inject<((sheetName: string) => void) | null>('jumpToSection', null)

function rowStatus(row: NavRow): string {
  if (row.progressKeys.length === 0) return ''
  const map = props.allResponses
  if (!map || map.size === 0) return 'pending'
  const keys = [...map.keys()]
  const hasData = row.progressKeys.some(pk => {
    if (pk.endsWith('-')) return keys.some(k => k.startsWith(pk))
    return map.has(pk) || keys.some(k => k.startsWith(pk))
  })
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
  <div class="d1-tab-index">
    <!-- 编制进度条 -->
    <div class="progress-bar-section">
      <div class="progress-info">
        <span>编制进度</span>
        <span class="progress-text">{{ completedCount }} / {{ applicableCount }} ({{ progressPercent }}%)</span>
      </div>
      <el-progress :percentage="progressPercent" :stroke-width="8" :show-text="false" />
    </div>

    <!-- 底稿架构（4 阶段泳道卡片） -->
    <div class="index-header">
      <h4 class="index-title">D1 应收票据底稿架构</h4>
      <span class="index-hint">点击卡片可跳转至对应底稿</span>
    </div>
    <GtBArchitectureTree
      :active-sheet="''"
      :html-data="archHtmlData"
      @navigate="handleNavigate"
    />

    <details class="methodology-hint">
      <summary>编制提示</summary>
      <p>推荐工作流：D1A 程序表 → D1-1 审定表 → D1-2/D1-3 明细 → D1-4 坏账 → D1-14/D1-15 ECL → D1-5 调整分录。监盘核查组 D1-10~D1-13 可与 D1-1 审定表交叉核对。</p>
    </details>
  </div>
</template>

<style scoped>
.d1-tab-index {
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
.methodology-hint {
  margin-top: 16px;
  padding: 10px 12px;
  border-left: 3px solid #409eff;
  background: #ecf5ff;
  border-radius: 0 4px 4px 0;
  font-size: var(--wp-font-size, 13px);
  color: #606266;
}
.methodology-hint summary {
  cursor: pointer;
  font-weight: 500;
  color: #409eff;
}
</style>
