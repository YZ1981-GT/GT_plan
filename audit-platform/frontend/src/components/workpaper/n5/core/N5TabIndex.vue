<template>
  <div class="n5-tab-index">
    <!-- ═══ 顶部标识头 ═══ -->
    <div class="n5-header-bar">
      <span class="header-code">底稿编码 N5</span>
      <span class="header-sep">|</span>
      <span class="header-subject">科目 6801 所得税费用</span>
      <span class="header-sep">|</span>
      <span class="header-direction">损益类 / 借方 / 取发生额</span>
    </div>

    <!-- ═══ 损益类科目醒目标注 ═══ -->
    <div class="n5-expense-badge">
      <el-icon><WarningFilled /></el-icon>
      <span>所得税费用(6801)为损益类借方科目，取本期发生额（借方发生−贷方发生），非期末余额。所得税费用 = 当期所得税 + 递延所得税费用</span>
    </div>

    <!-- ═══ 蓝色渐变操作引导区 ═══ -->
    <div class="n5-guide">
      <div class="n5-guide-header">
        <el-icon><InfoFilled /></el-icon>
        <span>操作步骤引导</span>
      </div>
      <div class="n5-guide-steps">
        <div class="step-item">
          <span class="step-num">①</span>
          <span class="step-text">完成当期所得税计算(N5-4)：会计利润±纳税调整→应纳税所得额×税率</span>
        </div>
        <div class="step-item">
          <span class="step-num">②</span>
          <span class="step-text">填写纳税调整明细(N5-5) + 税收优惠(N5-6) + 研发加计(N5-6-1)</span>
        </div>
        <div class="step-item">
          <span class="step-num">③</span>
          <span class="step-text">核对递延所得税费用(N5-8)：确认与N1/N3本期变动一致</span>
        </div>
        <div class="step-item">
          <span class="step-num">④</span>
          <span class="step-text">完成审定表(N5-1)：当期+递延→所得税费用合计→TB回写6801</span>
        </div>
      </div>
    </div>

    <!-- ═══ 纳税调整仪表板 + 有效税率 ═══ -->
    <div class="n5-dashboard">
      <div class="dashboard-item">
        <span class="dash-label">当期所得税</span>
        <span class="dash-value">{{ fmtAmount(calcResult.current) }}</span>
      </div>
      <div class="dashboard-item">
        <span class="dash-label">递延所得税费用</span>
        <span class="dash-value">{{ fmtAmount(calcResult.deferred) }}</span>
      </div>
      <div class="dashboard-item dashboard-total">
        <span class="dash-label">所得税费用合计</span>
        <span class="dash-value">{{ fmtAmount(calcResult.total) }}</span>
      </div>
      <div class="dashboard-item dashboard-rate">
        <span class="dash-label">有效税率</span>
        <span class="dash-value">{{ etr.rate != null ? fmtPercent(etr.rate) : '—' }}</span>
      </div>
    </div>

    <!-- ═══ 跨底稿联动状态 ═══ -->
    <div class="n5-linkage-panel">
      <div class="linkage-title">跨底稿联动状态</div>
      <div class="linkage-items">
        <div class="linkage-item">
          <GtIndexChip value="N1" />
          <span class="linkage-desc">递延税资产变动</span>
          <span :class="['linkage-status', deferredRec.n1Change !== 0 ? 'linked' : 'pending']">
            {{ deferredRec.n1Change !== 0 ? '✓ 已接收' : '○ 待编制' }}
          </span>
        </div>
        <div class="linkage-item">
          <GtIndexChip value="N3" />
          <span class="linkage-desc">递延税负债变动</span>
          <span :class="['linkage-status', deferredRec.n3Change !== 0 ? 'linked' : 'pending']">
            {{ deferredRec.n3Change !== 0 ? '✓ 已接收' : '○ 待编制' }}
          </span>
        </div>
        <div class="linkage-item">
          <GtIndexChip value="I6" />
          <span class="linkage-desc">研发费用(费用化)</span>
          <span :class="['linkage-status', rdData.expensed !== 0 ? 'linked' : 'pending']">
            {{ rdData.expensed !== 0 ? '✓ 已接收' : '○ 待编制' }}
          </span>
        </div>
        <div class="linkage-item">
          <GtIndexChip value="I2" />
          <span class="linkage-desc">开发支出(资本化)</span>
          <span :class="['linkage-status', rdData.capitalized !== 0 ? 'linked' : 'pending']">
            {{ rdData.capitalized !== 0 ? '✓ 已接收' : '○ 待编制' }}
          </span>
        </div>
        <div class="linkage-item">
          <GtIndexChip value="A" />
          <span class="linkage-desc">利润表会计利润</span>
          <span :class="['linkage-status', profitData.accountingProfit !== 0 ? 'linked' : 'pending']">
            {{ profitData.accountingProfit !== 0 ? '✓ 已接收' : '○ 待编制' }}
          </span>
        </div>
      </div>
    </div>

    <!-- ═══ 总体进度 ═══ -->
    <div class="n5-progress-section">
      <div class="progress-info">
        <span>编制进度</span>
        <span class="progress-text">{{ completedCount }} / {{ effectiveTotal }} ({{ progressPercent }}%)</span>
      </div>
      <el-progress :percentage="progressPercent" :stroke-width="8" :show-text="false" />
    </div>

    <!-- ═══ 底稿目录表格 ═══ -->
    <el-card shadow="never" class="n5-index-card">
      <template #header>
        <span class="card-title">致同会计师事务所 / 所得税费用底稿</span>
      </template>
      <el-table
        :data="sheetRows"
        border
        size="small"
        highlight-current-row
        style="width: 100%"
        :row-class-name="getRowClassName"
        @row-click="handleRowClick"
      >
        <el-table-column prop="seq" label="序号" width="60" align="center" />
        <el-table-column prop="name" label="内容" min-width="280">
          <template #default="{ row }">
            <span :class="row.skip ? 'sheet-name-skip' : 'sheet-name-link'">{{ row.name }}</span>
            <el-tag v-if="row.isCore" size="small" type="danger" class="core-tag">核心</el-tag>
            <el-tag v-if="row.skip" size="small" type="info" class="skip-tag">Skip</el-tag>
            <el-tag v-if="row.group === 'calc'" size="small" type="warning" class="group-tag">计算</el-tag>
            <el-tag v-if="row.group === 'benefit'" size="small" type="success" class="group-tag">优惠</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="索引号" width="100" align="center">
          <template #default="{ row }">
            <GtIndexChip v-if="row.code" :value="row.code" />
            <span v-else class="no-index">—</span>
          </template>
        </el-table-column>
        <el-table-column label="进度" width="140" align="center">
          <template #default="{ row }">
            <template v-if="!row.skip">
              <el-progress
                :percentage="row.progress"
                :stroke-width="6"
                :show-text="false"
                :color="getProgressColor(row.progress)"
                style="width: 80px; display: inline-block"
              />
              <span class="progress-label">{{ row.progress }}%</span>
            </template>
            <span v-else class="skip-label">—</span>
          </template>
        </el-table-column>
        <el-table-column label="联动" width="80" align="center">
          <template #default="{ row }">
            <span v-if="row.linkageStatus === 'matched'" class="linkage-badge linkage-ok">✓</span>
            <span v-else-if="row.linkageStatus === 'diff'" class="linkage-badge linkage-warn">⚠</span>
            <span v-else class="linkage-badge linkage-na">—</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="80" align="center">
          <template #default="{ row }">
            <el-button v-if="!row.skip" type="primary" link size="small" @click.stop="handleNavigate(row)">进入</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- ═══ 编制提示（折叠） ═══ -->
    <details class="n5-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li>所得税费用(6801)为<strong>损益类借方科目</strong>，取本期发生额（借方发生−贷方发生）</li>
        <li>所得税费用 = 当期所得税费用 + 递延所得税费用</li>
        <li>当期所得税 = 应纳税所得额 × 适用税率 − 减免税额 − 抵免税额</li>
        <li>应纳税所得额 = 会计利润 + 纳税调增 − 纳税调减</li>
        <li>递延所得税费用 = 递延税负债本期增加 − 递延税资产本期增加</li>
        <li>有效税率 = 所得税费用 / 会计利润（合理性分析，异常需说明）</li>
        <li>N3A原底稿标记Skip，走OnlyOffice fallback不做HTML组件化</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * N5TabIndex — N5 所得税费用底稿目录
 *
 * 15行sheet目录（N3A标记skip）。有效sheet 14个，进度条展示完成度。
 * 纳税调整仪表板：当期所得税/递延所得税/合计/有效税率。
 * 联动状态：N1/N3/I6/I2/A跨底稿接收状态。
 * 点击行 emit navigate 事件切换 sheetName。
 *
 * Spec: .kiro/specs/n5-income-tax-expense/ Task 4.1
 * Requirements: 1.2, 1.11
 */
import { computed, type Ref } from 'vue'
import { InfoFilled, WarningFilled } from '@element-plus/icons-vue'
import GtIndexChip from '@/components/workpaper/GtIndexChip.vue'
import { useN5CrossSheet } from '../../composables/useN5CrossSheet'

// ─── Props / Emits ───────────────────────────────────────────────────────────

const props = defineProps<{
  allResponses: Map<string, any>
  wpId: string
  projectId: string
  isReadonly: boolean
}>()

const emit = defineEmits<{
  (e: 'navigate', sheetCode: string): void
}>()

// ─── CrossSheet（有效税率+联动状态） ─────────────────────────────────────────

const allResponsesRef = computed(() => props.allResponses)
const wpIdRef = computed(() => props.wpId) as Ref<string>
const projectIdRef = computed(() => props.projectId) as Ref<string>

const {
  adjudicationVsCalc,
  deferredReconcile,
  rdFromI6I2,
  profitFromIncomeStatement,
  effectiveTaxRate,
} = useN5CrossSheet(allResponsesRef, { wpId: wpIdRef, projectId: projectIdRef })

const calcResult = adjudicationVsCalc
const deferredRec = deferredReconcile
const rdData = rdFromI6I2
const profitData = profitFromIncomeStatement
const etr = effectiveTaxRate

// ─── Types ───────────────────────────────────────────────────────────────────

type LinkageStatus = 'matched' | 'diff' | 'none'

interface SheetRow {
  seq: number
  name: string
  code: string
  sheetKey: string
  progress: number
  isCore: boolean
  skip: boolean
  group: 'core' | 'calc' | 'benefit' | ''
  linkageStatus: LinkageStatus
}

// ─── Sheet 目录行定义（15行，N3A skip） ─────────────────────────────────────

const sheetRows = computed<SheetRow[]>(() => {
  const hasData = props.allResponses.size > 0
  return [
    { seq: 1, name: '所得税费用审计程序表', code: 'N5A', sheetKey: 'N5A', progress: getSheetProgress('N5A'), isCore: false, skip: false, group: '', linkageStatus: 'none' },
    { seq: 2, name: '所得税费用审定表', code: 'N5-1', sheetKey: 'N5-1', progress: getSheetProgress('N5-1'), isCore: true, skip: false, group: 'core', linkageStatus: hasData && calcResult.value.total !== 0 ? 'matched' : 'none' },
    { seq: 3, name: '所得税费用明细表', code: 'N5-2', sheetKey: 'N5-2', progress: getSheetProgress('N5-2'), isCore: false, skip: false, group: 'core', linkageStatus: 'none' },
    { seq: 4, name: '调整分录汇总', code: 'N5-3', sheetKey: 'N5-3', progress: getSheetProgress('N5-3'), isCore: false, skip: false, group: 'core', linkageStatus: 'none' },
    { seq: 5, name: '当期所得税费用计算表', code: 'N5-4', sheetKey: 'N5-4', progress: getSheetProgress('N5-4'), isCore: true, skip: false, group: 'calc', linkageStatus: hasData && calcResult.value.current !== 0 ? 'matched' : 'none' },
    { seq: 6, name: '纳税调整明细表(107行)', code: 'N5-5', sheetKey: 'N5-5', progress: getSheetProgress('N5-5'), isCore: true, skip: false, group: 'calc', linkageStatus: 'none' },
    { seq: 7, name: '税收优惠明细表', code: 'N5-6', sheetKey: 'N5-6', progress: getSheetProgress('N5-6'), isCore: false, skip: false, group: 'benefit', linkageStatus: 'none' },
    { seq: 8, name: '研发加计扣除', code: 'N5-6-1', sheetKey: 'N5-6-1', progress: getSheetProgress('N5-6-1'), isCore: true, skip: false, group: 'benefit', linkageStatus: rdData.value.expensed !== 0 ? 'matched' : 'none' },
    { seq: 9, name: '高新技术企业认定检查', code: 'N5-6-2', sheetKey: 'N5-6-2', progress: getSheetProgress('N5-6-2'), isCore: false, skip: false, group: 'benefit', linkageStatus: 'none' },
    { seq: 10, name: '财产损失明细表', code: 'N5-7', sheetKey: 'N5-7', progress: getSheetProgress('N5-7'), isCore: false, skip: false, group: 'benefit', linkageStatus: 'none' },
    { seq: 11, name: '递延所得税费用核对表', code: 'N5-8', sheetKey: 'N5-8', progress: getSheetProgress('N5-8'), isCore: true, skip: false, group: 'calc', linkageStatus: deferredRec.value.deferredExpense !== 0 ? 'matched' : 'none' },
    { seq: 12, name: '附注披露信息（上市）', code: '', sheetKey: '附注上市', progress: getSheetProgress('附注上市'), isCore: false, skip: false, group: 'core', linkageStatus: 'none' },
    { seq: 13, name: '附注披露信息（国企）', code: '', sheetKey: '附注国企', progress: getSheetProgress('附注国企'), isCore: false, skip: false, group: 'core', linkageStatus: 'none' },
    { seq: 14, name: 'N3A原底稿（递延税负债辅助）', code: 'N3A', sheetKey: 'N3A-skip', progress: 0, isCore: false, skip: true, group: '', linkageStatus: 'none' },
    { seq: 15, name: 'GT_Custom（系统占位）', code: '', sheetKey: 'GT_Custom', progress: 0, isCore: false, skip: true, group: '', linkageStatus: 'none' },
  ]
})

// ─── 进度计算 ────────────────────────────────────────────────────────────────

function getSheetProgress(code: string): number {
  if (props.allResponses.size === 0) return 0
  const prefixMap: Record<string, string> = {
    'N5A': 'N5A-', 'N5-1': 'N5-1-', 'N5-2': 'N5-2-', 'N5-3': 'N5-3-',
    'N5-4': 'N5-4-', 'N5-5': 'N5-5-', 'N5-6': 'N5-6-', 'N5-6-1': 'N5-6-1-',
    'N5-6-2': 'N5-6-2-', 'N5-7': 'N5-7-', 'N5-8': 'N5-8-',
    '附注上市': 'N5-disclosure-listed-', '附注国企': 'N5-disclosure-soe-',
  }
  const prefix = prefixMap[code]
  if (!prefix) return 0
  let filled = 0
  let total = 0
  for (const [key] of props.allResponses) {
    if (key.startsWith(prefix)) {
      total++
      const val = props.allResponses.get(key)
      if (val?.conclusion != null && val.conclusion !== '' && val.conclusion !== '0') filled++
    }
  }
  if (total === 0) return 0
  return Math.round((filled / total) * 100)
}

const effectiveSheets = computed(() => sheetRows.value.filter(r => !r.skip))
const effectiveTotal = computed(() => effectiveSheets.value.length)
const completedCount = computed(() => effectiveSheets.value.filter(r => r.progress >= 100).length)
const progressPercent = computed(() => {
  if (effectiveTotal.value === 0) return 0
  const avg = effectiveSheets.value.reduce((s, r) => s + r.progress, 0) / effectiveTotal.value
  return Math.round(avg)
})

// ─── 交互 ────────────────────────────────────────────────────────────────────

function handleRowClick(row: SheetRow) {
  if (row.skip) return
  emit('navigate', row.sheetKey)
}

function handleNavigate(row: SheetRow) {
  emit('navigate', row.sheetKey)
}

function getRowClassName({ row }: { row: SheetRow }): string {
  if (row.skip) return 'skip-row'
  if (row.progress >= 100) return 'completed-row'
  return ''
}

function getProgressColor(percent: number): string {
  if (percent >= 100) return '#67c23a'
  if (percent >= 50) return '#409eff'
  return '#e6e8eb'
}

// ─── 格式化 ──────────────────────────────────────────────────────────────────

function fmtAmount(val: number | null | undefined): string {
  if (val == null || val === 0) return '—'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function fmtPercent(val: number | null | undefined): string {
  if (val == null) return '—'
  return (val * 100).toFixed(2) + '%'
}
</script>

<style scoped>
.n5-tab-index { padding: 12px; font-size: var(--wp-font-size, 13px); }

.n5-header-bar {
  display: flex; align-items: center; gap: 12px;
  padding: 10px 16px; margin-bottom: 16px;
  background: #f5f7fa; border: 1px solid #dcdfe6; border-radius: 6px; font-size: var(--wp-font-size, 13px);
}
.header-code { font-weight: 600; color: #303133; }
.header-sep { color: #c0c4cc; }
.header-subject { color: #606266; }
.header-direction { font-weight: 500; color: #e6a23c; }

.n5-expense-badge {
  display: flex; align-items: center; gap: 8px;
  padding: 10px 16px; margin-bottom: 16px;
  background: linear-gradient(135deg, #fff3e0 0%, #ffe0b2 100%);
  border: 1px solid #ffcc80; border-left: 4px solid #f57c00;
  border-radius: 6px; font-size: var(--wp-font-size, 13px); font-weight: 500; color: #e65100;
}
.n5-expense-badge .el-icon { font-size: 16px; color: #f57c00; flex-shrink: 0; }

.n5-guide {
  background: linear-gradient(135deg, #e8f4fd 0%, #d6eaf8 100%);
  border: 1px solid #b3d9f2; border-radius: 8px; padding: 14px 20px; margin-bottom: 16px;
}
.n5-guide-header { display: flex; align-items: center; gap: 6px; font-weight: 500; color: #1a73e8; margin-bottom: 10px; font-size: var(--wp-font-size, 13px); }
.n5-guide-steps { display: grid; grid-template-columns: repeat(2, 1fr); gap: 8px 24px; }
.step-item { display: flex; align-items: center; gap: 8px; font-size: var(--wp-font-size, 13px); color: #374151; }
.step-num { display: inline-flex; align-items: center; justify-content: center; width: 22px; height: 22px; border-radius: 50%; background: #1a73e8; color: #fff; font-size: 11px; font-weight: 600; flex-shrink: 0; }

.n5-dashboard {
  display: flex; gap: 12px; margin-bottom: 16px; padding: 14px 16px;
  background: #fafbfc; border: 1px solid #ebeef5; border-radius: 8px;
}
.dashboard-item { flex: 1; text-align: center; padding: 8px; border-radius: 6px; background: #fff; border: 1px solid #ebeef5; }
.dashboard-total { background: #ecf5ff; border-color: #b3d8ff; }
.dashboard-rate { background: #f0f9eb; border-color: #c2e7b0; }
.dash-label { display: block; font-size: 12px; color: #909399; margin-bottom: 4px; }
.dash-value { display: block; font-size: 15px; font-weight: 600; color: #303133; }

.n5-linkage-panel { margin-bottom: 16px; padding: 14px 16px; background: #f0f9ff; border: 1px solid #bae6fd; border-radius: 8px; }
.linkage-title { font-size: var(--wp-font-size, 13px); font-weight: 500; color: #0369a1; margin-bottom: 10px; }
.linkage-items { display: flex; flex-wrap: wrap; gap: 10px; }
.linkage-item { display: flex; align-items: center; gap: 8px; padding: 6px 12px; background: #fff; border: 1px solid #e2e8f0; border-radius: 6px; font-size: 12px; }
.linkage-desc { color: #606266; }
.linkage-status { font-weight: 500; font-size: 11px; }
.linkage-status.linked { color: #43a047; }
.linkage-status.pending { color: #9e9e9e; }

.n5-progress-section { margin-bottom: 16px; padding: 12px 16px; background: #f5f7fa; border-radius: 6px; }
.progress-info { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; font-size: var(--wp-font-size, 13px); color: #606266; }
.progress-text { font-weight: 600; color: #303133; }

.n5-index-card { margin-bottom: 16px; }
.card-title { font-size: 14px; font-weight: 600; color: #303133; }
.sheet-name-link { color: #1a73e8; cursor: pointer; font-size: var(--wp-font-size, 13px); }
.sheet-name-link:hover { text-decoration: underline; }
.sheet-name-skip { color: #c0c4cc; font-size: var(--wp-font-size, 13px); text-decoration: line-through; }
.no-index { color: #c0c4cc; }
.core-tag, .skip-tag, .group-tag { margin-left: 8px; font-size: 11px; vertical-align: middle; }
.progress-label { display: inline-block; margin-left: 8px; font-size: 12px; color: #909399; width: 32px; }
.skip-label { font-size: 12px; color: #c0c4cc; font-style: italic; }

.linkage-badge { display: inline-flex; align-items: center; justify-content: center; width: 24px; height: 24px; border-radius: 50%; font-size: var(--wp-font-size, 13px); font-weight: 600; }
.linkage-ok { background: #e8f5e9; color: #43a047; border: 1px solid #a5d6a7; }
.linkage-warn { background: #fff3e0; color: #e65100; border: 1px solid #ffcc80; }
.linkage-na { background: #f5f5f5; color: #bdbdbd; border: 1px solid #e0e0e0; }

:deep(.skip-row) { background-color: #f9f9f9 !important; opacity: 0.6; }
:deep(.skip-row:hover) { cursor: not-allowed !important; }
:deep(.completed-row) { background-color: #f0f9eb !important; }
:deep(.el-table) { font-size: var(--wp-font-size, 13px); }
:deep(.el-table .el-table__row) { cursor: pointer; }
:deep(.el-table .el-table__row:hover) { background-color: #ecf5ff !important; }

.n5-details-tip { margin-top: 12px; padding: 12px 16px; background: #fafafa; border: 1px solid #ebeef5; border-radius: 6px; font-size: var(--wp-font-size, 13px); color: #606266; }
.n5-details-tip summary { cursor: pointer; font-weight: 500; color: #303133; margin-bottom: 8px; }
.n5-details-tip ul { padding-left: 20px; margin: 8px 0 0; line-height: 1.8; }
</style>
