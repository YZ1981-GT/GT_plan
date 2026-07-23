<template>
  <div class="k13-tab-index">
    <!-- ═══ 总体进度 ═══ -->
    <div class="progress-bar-section">
      <div class="progress-info">
        <span>编制进度</span>
        <span class="progress-text">{{ completedCount }} / {{ applicableCount }} ({{ progressPercent }}%)</span>
      </div>
      <el-progress :percentage="progressPercent" :stroke-width="8" :show-text="false" />
    </div>

    <!-- ═══ 蓝色渐变操作引导区 ═══ -->
    <div class="k13-guide">
      <div class="k13-guide-header">
        <el-icon><InfoFilled /></el-icon>
        <span>操作步骤引导</span>
      </div>
      <div class="k13-guide-steps">
        <div class="step-item"><span class="step-num">①</span><span class="step-text">填写明细表（K13-2）逐笔登记营业外支出明细</span></div>
        <div class="step-item"><span class="step-num">②</span><span class="step-text">填写审定表（K13-1）确认发生额 → TB回写6711</span></div>
        <div class="step-item"><span class="step-num">③</span><span class="step-text">录入调整分录（K13-3）管理AJE/RJE → 联动A13</span></div>
        <div class="step-item"><span class="step-num">④</span><span class="step-text">完成检查表（K13-4）核实分类正确性与税前扣除性</span></div>
      </div>
    </div>

    <!-- ═══ 底稿架构（4 阶段泳道卡片，对齐 D4/b-index 范式） ═══ -->
    <div class="index-header">
      <h4 class="index-title">底稿架构</h4>
      <span class="index-hint">点击卡片可跳转至对应底稿</span>
    </div>
    <GtBArchitectureTree
      :active-sheet="''"
      :html-data="archHtmlData"
      @navigate="handleNavigate"
    />

    <!-- ═══ 编制提示 ═══ -->
    <details class="compile-hint">
      <summary>📋 编制提示</summary>
      <ul>
        <li>K13为损益类科目（6711），取本期借方发生额累计（借方=支出增加），非期末余额</li>
        <li>营业外支出指与日常活动无关的损失：非流动资产处置损失/捐赠支出/罚款滞纳金/债务重组损失/资产盘亏损失等</li>
        <li>捐赠支出、罚款滞纳金等需关注税前扣除性（K13-4检查表）</li>
        <li>审定数=未审数+AJE+RJE；调整分录联动A13</li>
        <li>附注按去向分别披露营业外支出金额</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * K13TabIndex.vue — K13 营业外支出底稿目录（对齐 D4/b-index 底稿架构范式）
 *
 * 复用 GtBArchitectureTree（4 阶段泳道卡片：审计计划/科目审定/实质性程序/披露与调整），
 * 由 K13 各 sheet 构造 navigation_rows 喂入。点击卡片 → emit('navigate-sheet', 完整sheet名)
 * → GtK13NonOperatingExpense 转发 → GtWpRenderer 按 sheet_name.includes 匹配。
 */
import { computed, type Ref } from 'vue'
import { defineAsyncComponent } from 'vue'
import { InfoFilled } from '@element-plus/icons-vue'

const GtBArchitectureTree = defineAsyncComponent(() => import('../../GtBArchitectureTree.vue'))

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any> | Ref<Map<string, any>>
  isReadonly: boolean
}>()

const emit = defineEmits<{
  (e: 'navigate-sheet', sheetName: string): void
}>()

interface NavRow {
  content: string
  index_ref: string
  component_type: string
  progressKeys: string[]
}

/** K13 各 sheet → navigation_rows（content=完整 sheet 名，供 includes 匹配）。 */
const NAV_ROWS: NavRow[] = [
  { content: '营业外支出实质性程序表K13A', index_ref: 'K13A', component_type: 'a-program-console', progressKeys: ['K13-K13A-'] },
  { content: '审定表K13-1', index_ref: 'K13-1', component_type: 'd-form-table', progressKeys: ['K13-1-rows'] },
  { content: '明细表K13-2', index_ref: 'K13-2', component_type: 'd-form-table', progressKeys: ['K13-2-'] },
  { content: '调整分录汇总K13-3', index_ref: 'K13-3', component_type: 'd-form-table', progressKeys: ['K13-3-adj-entries', 'K13-3-'] },
  { content: '营业外支出检查表K13-4', index_ref: 'K13-4', component_type: 'd-form-table', progressKeys: ['K13-4-'] },
  { content: '附注披露信息（上市公司）', index_ref: 'K13-附注上市', component_type: 'c-note-table', progressKeys: ['K13-disc-listed-', 'K13-disclosure-listed-'] },
  { content: '附注披露信息（国有企业）', index_ref: 'K13-附注国企', component_type: 'c-note-table', progressKeys: ['K13-disc-soe-', 'K13-disclosure-soe-'] },
]

function getResponses(): Map<string, any> {
  const r = props.allResponses
  if (r instanceof Map) return r
  return (r as any)?.value ?? new Map()
}

function rowStatus(row: NavRow): string {
  if (row.progressKeys.length === 0) return ''
  const map = getResponses()
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

// ─── 编制进度 ────────────────────────────────────────────────────────────────
const progressRows = computed(() => NAV_ROWS.filter(r => r.progressKeys.length > 0))
const completedCount = computed(() => progressRows.value.filter(r => rowStatus(r) === 'completed').length)
const applicableCount = computed(() => progressRows.value.length)
const progressPercent = computed(() =>
  applicableCount.value === 0 ? 0 : Math.round((completedCount.value / applicableCount.value) * 100),
)

function handleNavigate(sheetName: string): void {
  if (sheetName) emit('navigate-sheet', sheetName)
}
</script>

<style scoped>
.k13-tab-index { padding: 12px; font-size: var(--wp-font-size, 13px); }

.progress-bar-section {
  margin-bottom: 16px; padding: 12px 16px;
  background: #f5f7fa; border-radius: 6px;
}
.progress-info {
  display: flex; justify-content: space-between; align-items: center;
  margin-bottom: 8px; font-size: var(--wp-font-size, 13px); color: #606266;
}
.progress-text { font-weight: 600; color: #303133; }

.k13-guide {
  margin-bottom: 16px; padding: 14px 18px;
  background: linear-gradient(135deg, #e8f4fd 0%, #d1ecf9 100%);
  border-radius: 8px; border-left: 4px solid #409eff;
}
.k13-guide-header {
  display: flex; align-items: center; gap: 6px;
  font-weight: 600; color: #303133; margin-bottom: 10px;
}
.k13-guide-steps { display: grid; grid-template-columns: 1fr 1fr; gap: 6px 16px; }
.step-item { display: flex; align-items: flex-start; gap: 6px; }
.step-num { color: #409eff; font-weight: 700; min-width: 18px; }
.step-text { color: #606266; line-height: 1.5; }

.index-header { display: flex; align-items: baseline; gap: 12px; margin-bottom: 12px; }
.index-title { margin: 0; font-size: 16px; font-weight: 600; color: #303133; }
.index-hint { font-size: 12px; color: #909399; }

.compile-hint {
  margin-top: 16px; padding: 10px 14px;
  background: #fafafa; border-radius: 6px;
  font-size: 12px; color: #606266;
}
.compile-hint summary { cursor: pointer; font-weight: 500; margin-bottom: 6px; }
.compile-hint ul { padding-left: 20px; margin: 0; line-height: 1.8; }
</style>
