<template>
  <div class="k8-tab-index">
    <!-- ═══ 总体进度 ═══ -->
    <div class="k8-progress-section">
      <div class="progress-info">
        <span>编制进度</span>
        <span class="progress-text">{{ completedCount }} / {{ totalCount }} 已完成 ({{ progressPercent }}%)</span>
      </div>
      <el-progress :percentage="progressPercent" :stroke-width="8" :show-text="false" />
      <div class="progress-stats">
        <el-tag size="small" type="success">已完成 {{ completedCount }}</el-tag>
        <el-tag size="small" type="primary">进行中 {{ inProgressCount }}</el-tag>
        <el-tag size="small" type="info">未开始 {{ notStartedCount }}</el-tag>
      </div>
    </div>

    <!-- ═══ 蓝色渐变操作引导区 ═══ -->
    <div class="k8-guide">
      <div class="k8-guide-header">
        <el-icon><InfoFilled /></el-icon>
        <span>操作步骤引导</span>
      </div>
      <div class="k8-guide-steps">
        <div class="step-item">
          <span class="step-num">①</span>
          <span class="step-text">填写明细表（K8-2）登记各项销售费用明细科目发生额</span>
        </div>
        <div class="step-item">
          <span class="step-num">②</span>
          <span class="step-text">完成实质性分析（K8-4）识别同比/环比异常波动</span>
        </div>
        <div class="step-item">
          <span class="step-num">③</span>
          <span class="step-text">执行截止测试（K8-6/K8-7）验证期末费用截止正确</span>
        </div>
        <div class="step-item">
          <span class="step-num">④</span>
          <span class="step-text">填写审定表（K8-1）确认发生额 → TB回写6601</span>
        </div>
        <div class="step-item">
          <span class="step-num">⑤</span>
          <span class="step-text">完成合同检查（K8-5）+ 综合检查（K8-8）→ 审计结论</span>
        </div>
        <div class="step-item">
          <span class="step-num">⑥</span>
          <span class="step-text">填写附注披露 → 确认披露完整性</span>
        </div>
      </div>
    </div>

    <!-- ═══ 跨底稿引用 ═══ -->
    <div class="k8-cross-refs">
      <span class="cross-refs-label">关联底稿：</span>
      <GtIndexChip value="K8A" :context-project-id="props.projectId" />
      <GtIndexChip value="K9" :context-project-id="props.projectId" />
      <GtIndexChip value="J1" :context-project-id="props.projectId" />
      <GtIndexChip value="A13" :context-project-id="props.projectId" />
    </div>

    <!-- ═══ 核心组（审定/明细/调整/程序表） ═══ -->
    <el-card shadow="never" class="k8-group-card group-core">
      <template #header>
        <span class="group-title">核心底稿</span>
        <el-tag size="small" type="success" effect="light">{{ groupProgress('core') }}</el-tag>
      </template>
      <el-table
        :data="coreSheets"
        border
        size="small"
        highlight-current-row
        style="width: 100%"
        :row-class-name="getRowClassName"
        @row-click="handleRowClick"
      >
        <el-table-column prop="seq" label="序号" width="56" align="center" />
        <el-table-column prop="name" label="底稿名称" min-width="220">
          <template #default="{ row }">
            <span class="sheet-name-link">{{ row.name }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="code" label="索引号" width="80" align="center" />
        <el-table-column prop="description" label="简要说明" min-width="280" />
        <el-table-column label="完成进度" width="150" align="center">
          <template #default="{ row }">
            <el-progress
              :percentage="row.progress"
              :stroke-width="6"
              :show-text="false"
              :color="getProgressColor(row.progress)"
              style="width: 80px; display: inline-block"
            />
            <span class="progress-label">{{ row.progress }}%</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- ═══ 分析与截止测试组 ═══ -->
    <el-card shadow="never" class="k8-group-card group-analysis">
      <template #header>
        <span class="group-title">分析与截止测试</span>
        <el-tag size="small" type="warning" effect="light">{{ groupProgress('analysis') }}</el-tag>
      </template>
      <el-table
        :data="analysisSheets"
        border
        size="small"
        highlight-current-row
        style="width: 100%"
        :row-class-name="getRowClassName"
        @row-click="handleRowClick"
      >
        <el-table-column prop="seq" label="序号" width="56" align="center" />
        <el-table-column prop="name" label="底稿名称" min-width="220">
          <template #default="{ row }">
            <span class="sheet-name-link">{{ row.name }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="code" label="索引号" width="80" align="center" />
        <el-table-column prop="description" label="简要说明" min-width="280" />
        <el-table-column label="完成进度" width="150" align="center">
          <template #default="{ row }">
            <el-progress
              :percentage="row.progress"
              :stroke-width="6"
              :show-text="false"
              :color="getProgressColor(row.progress)"
              style="width: 80px; display: inline-block"
            />
            <span class="progress-label">{{ row.progress }}%</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- ═══ 检查组 ═══ -->
    <el-card shadow="never" class="k8-group-card group-inspection">
      <template #header>
        <span class="group-title">合同与综合检查</span>
        <el-tag size="small" type="danger" effect="light">{{ groupProgress('inspection') }}</el-tag>
      </template>
      <el-table
        :data="inspectionSheets"
        border
        size="small"
        highlight-current-row
        style="width: 100%"
        :row-class-name="getRowClassName"
        @row-click="handleRowClick"
      >
        <el-table-column prop="seq" label="序号" width="56" align="center" />
        <el-table-column prop="name" label="底稿名称" min-width="220">
          <template #default="{ row }">
            <span class="sheet-name-link">{{ row.name }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="code" label="索引号" width="80" align="center" />
        <el-table-column prop="description" label="简要说明" min-width="280" />
        <el-table-column label="完成进度" width="150" align="center">
          <template #default="{ row }">
            <el-progress
              :percentage="row.progress"
              :stroke-width="6"
              :show-text="false"
              :color="getProgressColor(row.progress)"
              style="width: 80px; display: inline-block"
            />
            <span class="progress-label">{{ row.progress }}%</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- ═══ 附注组 ═══ -->
    <el-card shadow="never" class="k8-group-card group-disclosure">
      <template #header>
        <span class="group-title">附注披露</span>
        <el-tag size="small" effect="light">{{ groupProgress('disclosure') }}</el-tag>
      </template>
      <el-table
        :data="disclosureSheets"
        border
        size="small"
        highlight-current-row
        style="width: 100%"
        :row-class-name="getRowClassName"
        @row-click="handleRowClick"
      >
        <el-table-column prop="seq" label="序号" width="56" align="center" />
        <el-table-column prop="name" label="底稿名称" min-width="220">
          <template #default="{ row }">
            <span class="sheet-name-link">{{ row.name }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="code" label="索引号" width="80" align="center" />
        <el-table-column prop="description" label="简要说明" min-width="280" />
        <el-table-column label="完成进度" width="150" align="center">
          <template #default="{ row }">
            <el-progress
              :percentage="row.progress"
              :stroke-width="6"
              :show-text="false"
              :color="getProgressColor(row.progress)"
              style="width: 80px; display: inline-block"
            />
            <span class="progress-label">{{ row.progress }}%</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- ═══ 编制提示（折叠） ═══ -->
    <details class="k8-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li>销售费用为<strong>损益类借方科目</strong>（6601）：取<strong>发生额</strong>非期末余额！</li>
        <li>费用类发生额 = 借方发生累计 − 贷方发生（红冲）</li>
        <li>审定数 = 未审数 + AJE + RJE</li>
        <li>实质性分析：同比变动率 = (本期−上期)/上期；占收入比 = 费用/营业收入</li>
        <li>截止双向：K8-6 记账凭证→原始凭证（存在认定）；K8-7 原始凭证→记账凭证（完整性认定）</li>
        <li>关联底稿：K9管理费用(同类损益)、J1职工薪酬(薪酬分配)、A13错报汇总</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * K8TabIndex.vue — K8 销售费用底稿目录（12 sheet进度表）
 *
 * 12个功能sheet分4组（核心/分析与截止/检查/附注）展示进度。
 * 点击行 emit navigate-sheet 事件切换 sheetName。
 * GtIndexChip 跨底稿跳转（K8A/K9/J1/A13）
 *
 * 损益类科目（6601销售费用）— 取发生额非余额！
 *
 * Spec: .kiro/specs/k8-selling-expenses/ | Task: 4.1
 * Requirements: 1.2
 */
import { computed, defineAsyncComponent, type Ref } from 'vue'
import { InfoFilled } from '@element-plus/icons-vue'

const GtIndexChip = defineAsyncComponent(() => import('../../GtIndexChip.vue'))

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any> | Ref<Map<string, any>>
  isReadonly: boolean
}>()

const emit = defineEmits<{
  (e: 'navigate-sheet', sheetName: string): void
}>()

// ─── Sheet Row 定义 ──────────────────────────────────────────────────────────

interface SheetRow {
  seq: number
  name: string
  code: string
  sheetKey: string
  description: string
  group: 'core' | 'analysis' | 'inspection' | 'disclosure'
  progress: number
}

function getResponses(): Map<string, any> {
  const r = props.allResponses
  if (r instanceof Map) return r
  return (r as any)?.value ?? new Map()
}

function calcSheetProgress(prefix: string, expectedFields: number): number {
  const responses = getResponses()
  if (!responses || responses.size === 0) return 0
  let count = 0
  for (const key of responses.keys()) {
    if (key.startsWith(prefix)) count++
  }
  if (count === 0) return 0
  if (count >= expectedFields) return 100
  return Math.min(Math.round((count / expectedFields) * 100), 99)
}

/**
 * 12 sheets（从k8_structure_summary.json）：
 * 1. 底稿目录 (K8) — 本页面
 * 2. 实质性程序表K8A
 * 3. 审定表K8-1
 * 4. 附注披露信息（上市公司）
 * 5. 附注披露信息（国企）
 * 6. 明细表K8-2
 * 7. 调整分录汇总K8-3
 * 8. 实质性分析K8-4
 * 9. 合同检查表K8-5
 * 10. 截止性测试(从记账凭证至原始凭证）K8-6
 * 11. 截止性测试（从原始凭证至记账凭证）K8-7
 * 12. 销售费用检查表K8-8
 *
 * sheetKey值对齐GtK8SellingExpenses.vue的currentSheet匹配逻辑
 */
const allSheets = computed<SheetRow[]>(() => [
  // ─── 核心组 ───
  { seq: 1, name: '实质性程序表', code: 'K8A', sheetKey: '实质性程序表K8A', description: '销售费用实质性程序清单与执行情况', group: 'core', progress: calcSheetProgress('K8A-', 5) },
  { seq: 2, name: '审定表', code: 'K8-1', sheetKey: '审定表K8-1', description: '损益类6601审定（发生额！73公式）+TB回写', group: 'core', progress: calcSheetProgress('K8-1-', 10) },
  { seq: 3, name: '明细表', code: 'K8-2', sheetKey: '明细表K8-2', description: '27列3区段+费用明细科目发生额+48行', group: 'core', progress: calcSheetProgress('K8-2-', 8) },
  { seq: 4, name: '调整分录汇总', code: 'K8-3', sheetKey: '调整分录汇总K8-3', description: 'AJE/RJE管理（借贷平衡）→联动A13', group: 'core', progress: calcSheetProgress('K8-3-', 4) },
  // ─── 分析与截止组 ───
  { seq: 5, name: '实质性分析', code: 'K8-4', sheetKey: '实质性分析K8-4', description: '同比/环比/占收入比/异常波动识别（25公式）', group: 'analysis', progress: calcSheetProgress('K8-4-', 8) },
  { seq: 6, name: '截止性测试（记账→原始）', code: 'K8-6', sheetKey: '截止性测试(从记账凭证至原始凭证）K8-6', description: '从记账凭证到原始凭证方向（存在认定）44行', group: 'analysis', progress: calcSheetProgress('K8-6-', 6) },
  { seq: 7, name: '截止性测试（原始→记账）', code: 'K8-7', sheetKey: '截止性测试（从原始凭证至记账凭证）K8-7', description: '从原始凭证到记账凭证方向（完整性认定）44行', group: 'analysis', progress: calcSheetProgress('K8-7-', 6) },
  // ─── 检查组 ───
  { seq: 8, name: '合同检查表', code: 'K8-5', sheetKey: '合同检查表K8-5', description: '重大费用合同真实性/金额匹配/审批检查', group: 'inspection', progress: calcSheetProgress('K8-5-', 5) },
  { seq: 9, name: '销售费用检查表', code: 'K8-8', sheetKey: '销售费用检查表K8-8', description: '综合检查逐项合规/不合规/不适用判断', group: 'inspection', progress: calcSheetProgress('K8-8-', 5) },
  // ─── 附注组 ───
  { seq: 10, name: '附注披露信息（上市公司）', code: '附注上市', sheetKey: '附注披露信息（上市公司）', description: '42行28列按费用性质披露', group: 'disclosure', progress: calcSheetProgress('K8-disclosure-listed-', 5) },
  { seq: 11, name: '附注披露信息（国企）', code: '附注国企', sheetKey: '附注披露信息（国企）', description: '30行5列国企版附注披露', group: 'disclosure', progress: calcSheetProgress('K8-disclosure-soe-', 5) },
])

const coreSheets = computed(() => allSheets.value.filter(s => s.group === 'core'))
const analysisSheets = computed(() => allSheets.value.filter(s => s.group === 'analysis'))
const inspectionSheets = computed(() => allSheets.value.filter(s => s.group === 'inspection'))
const disclosureSheets = computed(() => allSheets.value.filter(s => s.group === 'disclosure'))

const totalCount = computed(() => allSheets.value.length)
const completedCount = computed(() => allSheets.value.filter(r => r.progress >= 100).length)
const inProgressCount = computed(() => allSheets.value.filter(r => r.progress > 0 && r.progress < 100).length)
const notStartedCount = computed(() => allSheets.value.filter(r => r.progress === 0).length)
const progressPercent = computed(() => {
  if (totalCount.value === 0) return 0
  return Math.round(allSheets.value.reduce((s, r) => s + r.progress, 0) / totalCount.value)
})

function groupProgress(group: string): string {
  const sheets = allSheets.value.filter(s => s.group === group)
  return `${sheets.filter(s => s.progress >= 100).length}/${sheets.length}`
}

function handleRowClick(row: SheetRow) {
  emit('navigate-sheet', row.sheetKey)
}

function getRowClassName({ row }: { row: SheetRow }): string {
  if (row.progress >= 100) return 'completed-row'
  if (row.progress > 0) return 'in-progress-row'
  return ''
}

function getProgressColor(p: number): string {
  if (p >= 100) return '#67c23a'
  if (p >= 50) return '#409eff'
  if (p > 0) return '#e6a23c'
  return '#e6e8eb'
}
</script>

<style scoped>
.k8-tab-index { padding: 12px; font-size: 13px; }

/* ─── 进度区 ─── */
.k8-progress-section { margin-bottom: 16px; padding: 14px 16px; background: #f5f7fa; border-radius: 8px; }
.progress-info { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; font-size: 13px; color: #606266; }
.progress-text { font-weight: 600; color: #303133; }
.progress-stats { display: flex; gap: 8px; margin-top: 10px; }

/* ─── 引导区 ─── */
.k8-guide { background: linear-gradient(135deg, #e8f4fd 0%, #d6eaf8 100%); border: 1px solid #b3d9f2; border-radius: 8px; padding: 14px 20px; margin-bottom: 16px; }
.k8-guide-header { display: flex; align-items: center; gap: 6px; font-weight: 500; color: #1a73e8; margin-bottom: 10px; font-size: 13px; }
.k8-guide-steps { display: grid; grid-template-columns: repeat(2, 1fr); gap: 8px 24px; }
.step-item { display: flex; align-items: center; gap: 8px; font-size: 13px; color: #374151; }
.step-num { display: inline-flex; align-items: center; justify-content: center; width: 22px; height: 22px; border-radius: 50%; background: #1a73e8; color: #fff; font-size: 11px; font-weight: 600; flex-shrink: 0; }

/* ─── 跨底稿引用 ─── */
.k8-cross-refs { display: flex; align-items: center; gap: 8px; margin-bottom: 14px; padding: 8px 12px; background: #f5f7fa; border-radius: 6px; }
.cross-refs-label { font-size: 13px; color: #909399; }

/* ─── 分组卡片 ─── */
.k8-group-card { margin-bottom: 14px; }
.k8-group-card :deep(.el-card__header) { display: flex; align-items: center; justify-content: space-between; padding: 10px 16px; }
.group-title { font-size: 14px; font-weight: 600; color: #303133; }
.group-core :deep(.el-card__header) { background: linear-gradient(90deg, #f0faf0 0%, #f8fdf8 100%); }
.group-analysis :deep(.el-card__header) { background: linear-gradient(90deg, #eef6ff 0%, #f5faff 100%); }
.group-inspection :deep(.el-card__header) { background: linear-gradient(90deg, #fff7ed 0%, #fffbf5 100%); }
.group-disclosure :deep(.el-card__header) { background: linear-gradient(90deg, #fefce8 0%, #fefdf5 100%); }

/* ─── 表格 ─── */
.sheet-name-link { color: #1a73e8; cursor: pointer; font-size: 13px; }
.sheet-name-link:hover { text-decoration: underline; }
.progress-label { display: inline-block; margin-left: 8px; font-size: 12px; color: #909399; width: 36px; }
:deep(.completed-row) { background-color: #f0f9eb !important; }
:deep(.in-progress-row) { background-color: #fdf6ec !important; }
:deep(.el-table) { font-size: 13px; }
:deep(.el-table .el-table__row) { cursor: pointer; }
:deep(.el-table .el-table__row:hover) { background-color: #ecf5ff !important; }

/* ─── 编制提示 ─── */
.k8-details-tip { margin-top: 12px; padding: 12px 16px; background: #fafafa; border: 1px solid #ebeef5; border-radius: 6px; font-size: 13px; color: #606266; }
.k8-details-tip summary { cursor: pointer; font-weight: 500; color: #303133; margin-bottom: 8px; }
.k8-details-tip ul { padding-left: 20px; margin: 8px 0 0; line-height: 1.8; }
</style>
