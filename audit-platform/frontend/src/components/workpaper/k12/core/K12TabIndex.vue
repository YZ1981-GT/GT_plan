<template>
  <div class="k12-tab-index">
    <!-- ═══ 总体进度 ═══ -->
    <div class="progress-bar-section">
      <div class="progress-info">
        <span>编制进度</span>
        <span class="progress-text">{{ completedCount }} / {{ applicableCount }} ({{ progressPercent }}%)</span>
      </div>
      <el-progress :percentage="progressPercent" :stroke-width="8" :show-text="false" />
    </div>

    <!-- ═══ 蓝色渐变操作引导区 ═══ -->
    <div class="k12-guide">
      <div class="k12-guide-header">
        <el-icon><InfoFilled /></el-icon>
        <span>操作步骤引导</span>
      </div>
      <div class="k12-guide-steps">
        <div class="step-item"><span class="step-num">①</span><span class="step-text">填写明细表（K12-2）逐笔登记营业外收入明细</span></div>
        <div class="step-item"><span class="step-num">②</span><span class="step-text">填写审定表（K12-1）确认发生额 → TB回写6301</span></div>
        <div class="step-item"><span class="step-num">③</span><span class="step-text">录入调整分录（K12-3）管理AJE/RJE → 联动A13</span></div>
        <div class="step-item"><span class="step-num">④</span><span class="step-text">完成检查表（K12-4）凭证级核实分类正确性与合规性</span></div>
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
        <li>K12为损益类科目（6301营业外收入），取本期贷方发生额累计（贷方=收入增加），非期末余额</li>
        <li>营业外收入指与日常活动无关的利得：政府补助/盘盈利得/捐赠利得/碳排放配额出售利得等</li>
        <li>与日常活动相关的其他收益（6117）属K10底稿，注意分类正确性</li>
        <li>审定数=未审数+AJE+RJE；调整分录联动A13</li>
        <li>关注非经常性损益列报的正确性；附注按来源分别披露营业外收入金额</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * K12TabIndex.vue — K12 营业外收入底稿目录（对齐 D4/b-index 底稿架构范式）
 *
 * P2：复用 GtBArchitectureTree（4 阶段泳道卡片：审计计划/科目审定/实质性程序/披露与调整），
 * 由 K12 各 sheet 构造 navigation_rows 喂入。点击卡片 → emit('navigate-sheet', 完整sheet名)
 * → GtK12NonOperatingIncome 转发 → GtWpRenderer 按 sheet_name.includes 匹配。
 */
import { computed, defineAsyncComponent, type Ref } from 'vue'
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

/** K12 各 sheet → navigation_rows（content=完整 sheet 名，供 includes 匹配）。
 *  component_type + 名称关键词 决定 GtBArchitectureTree 的阶段归类。 */
const NAV_ROWS: NavRow[] = [
  { content: '营业外收入实质性程序表K12A', index_ref: 'K12A', component_type: 'a-program-console', progressKeys: ['K12-K12A-'] },
  { content: '审定表K12-1', index_ref: 'K12-1', component_type: 'd-form-table', progressKeys: ['K12-1-rows'] },
  { content: '明细表K12-2', index_ref: 'K12-2', component_type: 'd-form-table', progressKeys: ['K12-2-detail-rows'] },
  { content: '调整分录汇总K12-3', index_ref: 'K12-3', component_type: 'd-form-table', progressKeys: ['K12-3-'] },
  { content: '营业外收入检查表K12-4', index_ref: 'K12-4', component_type: 'd-form-table', progressKeys: ['K12-4-check-rows'] },
  { content: '附注披露信息（上市公司）', index_ref: 'K12-附注上市', component_type: 'c-note-table', progressKeys: ['K12-disc-listed-'] },
  { content: '附注披露信息（国有企业）', index_ref: 'K12-附注国企', component_type: 'c-note-table', progressKeys: ['K12-disc-soe-'] },
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
.k12-tab-index { padding: 12px; font-size: var(--wp-font-size, 13px); }

.progress-bar-section {
  margin-bottom: 16px; padding: 12px 16px;
  background: #f5f7fa; border-radius: 6px;
}
.progress-info {
  display: flex; justify-content: space-between; align-items: center;
  margin-bottom: 8px; font-size: var(--wp-font-size, 13px); color: #606266;
}
.progress-text { font-weight: 600; color: #303133; }

.k12-guide {
  margin-bottom: 16px; padding: 14px 18px;
  background: linear-gradient(135deg, #e8f4fd 0%, #d1ecf9 100%);
  border-radius: 8px; border-left: 4px solid #409eff;
}
.k12-guide-header {
  display: flex; align-items: center; gap: 6px;
  font-weight: 600; color: #303133; margin-bottom: 10px;
}
.k12-guide-steps { display: grid; grid-template-columns: 1fr 1fr; gap: 6px 16px; }
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
