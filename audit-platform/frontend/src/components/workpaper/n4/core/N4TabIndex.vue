<template>
  <div class="n4-tab-index">
    <!-- ═══ 顶部标识头 ═══ -->
    <div class="n4-header-bar">
      <span class="header-code">底稿编码 N4</span>
      <span class="header-sep">|</span>
      <span class="header-subject">科目 6403 税金及附加</span>
      <span class="header-sep">|</span>
      <span class="header-direction">损益类 / 借方 / 取本期发生额</span>
    </div>

    <!-- ═══ 损益类科目醒目标注 ═══ -->
    <div class="n4-expense-badge">
      <el-icon><WarningFilled /></el-icon>
      <span>税金及附加(6403)为损益类借方科目，取本期发生额（借方发生−贷方发生），非期末余额。覆盖消费税/城建税/教育费附加/房产税/土地使用税/车船税/印花税/资源税等。</span>
    </div>

    <!-- ═══ 蓝色渐变操作引导区 ═══ -->
    <div class="n4-guide">
      <div class="n4-guide-header">
        <el-icon><InfoFilled /></el-icon>
        <span>操作步骤引导</span>
      </div>
      <div class="n4-guide-steps">
        <div class="step-item">
          <span class="step-num">①</span>
          <span class="step-text">填写明细表(N4-2)逐笔登记各税种计税依据与发生额</span>
        </div>
        <div class="step-item">
          <span class="step-num">②</span>
          <span class="step-text">完成审定表(N4-1)确认各税种审定发生额 → TB回写6403</span>
        </div>
        <div class="step-item">
          <span class="step-num">③</span>
          <span class="step-text">录入调整分录(N4-3)管理AJE/RJE → 联动A13</span>
        </div>
        <div class="step-item">
          <span class="step-num">④</span>
          <span class="step-text">核对N2计提对应：各税种费用确认 = N2应交税费计提额</span>
        </div>
      </div>
    </div>

    <!-- ═══ 各税种统计仪表板 ═══ -->
    <div class="n4-dashboard">
      <div class="dashboard-header">
        <span class="dashboard-title">各税种统计仪表板</span>
        <el-tag size="small" :type="adjudicationVsDetail.isMatch ? 'success' : 'danger'" effect="light">
          {{ adjudicationVsDetail.isMatch ? '审定=明细 ✓' : `差异 ${fmtAmount(adjudicationVsDetail.diff)}` }}
        </el-tag>
      </div>
      <div class="dashboard-grid">
        <div
          v-for="item in taxDashboard"
          :key="item.tax"
          :class="['dashboard-card', item.hasDiff ? 'card-diff' : '']"
        >
          <div class="card-tax-name">{{ item.tax }}</div>
          <div class="card-amounts">
            <div class="card-row">
              <span class="card-label">本期</span>
              <span class="card-value">{{ fmtAmount(item.currentAmount) }}</span>
            </div>
            <div class="card-row">
              <span class="card-label">上期</span>
              <span class="card-value card-prior">{{ fmtAmount(item.priorAmount) }}</span>
            </div>
            <div class="card-row">
              <span class="card-label">同比</span>
              <span :class="['card-value', item.yoyChange > 0 ? 'card-up' : item.yoyChange < 0 ? 'card-down' : '']">
                {{ fmtYoy(item.yoyChange) }}
              </span>
            </div>
          </div>
          <div v-if="item.hasDiff" class="card-diff-badge">N2差异</div>
        </div>
      </div>
    </div>

    <!-- ═══ 跨底稿联动状态 ═══ -->
    <div class="n4-linkage-panel">
      <div class="linkage-title">跨底稿联动状态</div>
      <div class="linkage-items">
        <div class="linkage-item">
          <GtIndexChip value="N4-1" :context-project-id="props.projectId" />
          <span class="linkage-desc">↔ N4-2 审定vs明细</span>
          <span :class="['linkage-status', adjudicationVsDetail.isMatch ? 'linked' : (adjudicationVsDetail.diff !== 0 ? 'diff' : 'pending')]">
            {{ adjudicationVsDetail.isMatch ? '✓ 一致' : (adjudicationVsDetail.diff !== 0 ? '⚠ 差异' : '○ 待编制') }}
          </span>
        </div>
        <div class="linkage-item">
          <GtIndexChip value="N2" :context-project-id="props.projectId" />
          <span class="linkage-desc">N2计提额对应</span>
          <span :class="['linkage-status', n2LinkageStatus === 'matched' ? 'linked' : (n2LinkageStatus === 'diff' ? 'diff' : 'pending')]">
            {{ n2LinkageStatus === 'matched' ? '✓ 费用=计提' : (n2LinkageStatus === 'diff' ? '⚠ 不一致' : '○ N2未编制') }}
          </span>
        </div>
        <div class="linkage-item">
          <GtIndexChip value="TB" :context-project-id="props.projectId" />
          <span class="linkage-desc">TB回写(6403发生额)</span>
          <span :class="['linkage-status', tbWritebackStatus ? 'linked' : 'pending']">
            {{ tbWritebackStatus ? '✓ 已回写' : '○ 待审定' }}
          </span>
        </div>
      </div>
    </div>

    <!-- ═══ 总体进度 ═══ -->
    <div class="n4-progress-section">
      <div class="progress-info">
        <span>编制进度</span>
        <span class="progress-text">{{ completedCount }} / {{ effectiveTotal }} 已完成 ({{ progressPercent }}%)</span>
      </div>
      <el-progress :percentage="progressPercent" :stroke-width="8" :show-text="false" />
    </div>

    <!-- ═══ 底稿目录表格（9行） ═══ -->
    <el-card shadow="never" class="n4-index-card">
      <template #header>
        <span class="card-title">致同会计师事务所 / 税金及附加底稿</span>
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
            <span :class="row.skip ? 'sheet-name-skip' : 'sheet-name-link'">
              <span v-if="row.skip">⏭️ </span>{{ row.name }}
            </span>
            <el-tag v-if="row.isCore" size="small" type="danger" class="core-tag">核心</el-tag>
            <el-tag v-if="row.skip" size="small" type="info" class="skip-tag">Skip</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="索引号" width="100" align="center">
          <template #default="{ row }">
            <GtIndexChip v-if="row.code" :value="row.code" :context-project-id="props.projectId" />
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

    <!-- ═══ 跨底稿引用 ═══ -->
    <div class="n4-cross-refs">
      <span class="cross-refs-label">关联底稿：</span>
      <GtIndexChip value="N4A" :context-project-id="props.projectId" />
      <GtIndexChip value="N2" :context-project-id="props.projectId" />
      <GtIndexChip value="A13" :context-project-id="props.projectId" />
      <GtIndexChip value="TB" :context-project-id="props.projectId" />
    </div>

    <!-- ═══ 编制提示（折叠） ═══ -->
    <details class="n4-details-tip">
      <summary>📋 编制提示</summary>
      <ul>
        <li>税金及附加(6403)为<strong>损益类借方科目</strong>，取本期发生额（借方发生−贷方发生）</li>
        <li>覆盖税种：消费税/城建税/教育费附加/地方教育附加/房产税/土地使用税/车船税/印花税/资源税</li>
        <li>城建税及附加=(增值税+消费税)×税率(7%/5%/1%+3%+2%)</li>
        <li>核心勾稽：N4费用确认 = N2应交税费对应税种本期计提额</li>
        <li>审定数=未审数+AJE+RJE；调整分录联动A13</li>
        <li>O2A原底稿为辅助参考，标记Skip走OnlyOffice fallback</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * N4TabIndex — N4 税金及附加底稿目录
 *
 * 9行sheet目录（O2A标记skip）。有效sheet 7个，进度条展示完成度。
 * 各税种统计仪表板：各税种本期/上期/同比+N2差异标红。
 * 联动状态：N4-1↔N4-2一致性 + N4↔N2计提对应 + TB回写状态。
 * 点击行 emit navigate-sheet 事件切换 sheetName。
 *
 * Spec: .kiro/specs/n4-taxes-and-surcharges/ Task 4.1
 * Requirements: 1.2, 1.11
 */
import { computed, type Ref } from 'vue'
import { InfoFilled, WarningFilled } from '@element-plus/icons-vue'
import GtIndexChip from '@/components/workpaper/GtIndexChip.vue'
import { useN4CrossSheet, TAX_TYPES } from '../../composables/useN4CrossSheet'

// ─── Props / Emits ───────────────────────────────────────────────────────────

const props = defineProps<{
  allResponses: Map<string, any>
  wpId: string
  projectId: string
  isReadonly?: boolean
}>()

const emit = defineEmits<{
  (e: 'navigate-sheet', sheetName: string): void
}>()

// ─── CrossSheet composable ───────────────────────────────────────────────────

const allResponsesRef = computed(() => props.allResponses)
const wpIdRef = computed(() => props.wpId) as Ref<string>
const projectIdRef = computed(() => props.projectId) as Ref<string>

const {
  adjudicationVsDetail,
  n4VsN2Accrual,
  toIncomeStatement,
  taxDiffHighlights,
} = useN4CrossSheet(allResponsesRef, { wpId: wpIdRef, projectId: projectIdRef })

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
  linkageStatus: LinkageStatus
}

interface TaxDashboardItem {
  tax: string
  currentAmount: number
  priorAmount: number
  yoyChange: number
  hasDiff: boolean
}

// ─── Helper: 从 allResponses 取数 ───────────────────────────────────────────

function parseNum(val: any): number {
  if (val == null || val === '' || val === '—') return 0
  const n = Number(val)
  return isNaN(n) ? 0 : n
}

function getResponseValue(itemId: string): number {
  const resp = props.allResponses.get(itemId)
  return parseNum(resp?.conclusion)
}

// ─── 各税种统计仪表板数据 ────────────────────────────────────────────────────

const taxDashboard = computed<TaxDashboardItem[]>(() => {
  return TAX_TYPES.map((tax) => {
    const currentAmount = getResponseValue(`N4-1-${tax}-audited`)
    const priorAmount = getResponseValue(`N4-1-${tax}-prior`)
    const yoyChange = priorAmount !== 0
      ? (currentAmount - priorAmount) / Math.abs(priorAmount)
      : (currentAmount !== 0 ? 1 : 0)
    const hasDiff = taxDiffHighlights.value.get(tax) ?? false
    return { tax, currentAmount, priorAmount, yoyChange, hasDiff }
  })
})

// ─── N2联动状态 ──────────────────────────────────────────────────────────────

const n2LinkageStatus = computed<'matched' | 'diff' | 'pending'>(() => {
  const items = n4VsN2Accrual.value
  // 如果所有计提额都为0 → N2未编制
  const hasAnyAccrual = items.some(i => i.accrual !== 0)
  if (!hasAnyAccrual) return 'pending'
  // 如果有任何差异
  const hasDiff = items.some(i => Math.abs(i.diff) >= 0.01)
  return hasDiff ? 'diff' : 'matched'
})

// ─── TB回写状态 ──────────────────────────────────────────────────────────────

const tbWritebackStatus = computed<boolean>(() => {
  return toIncomeStatement.value.amount !== 0
})

// ─── Sheet 目录行定义（9行，O2A skip） ──────────────────────────────────────

const sheetRows = computed<SheetRow[]>(() => {
  return [
    { seq: 1, name: '底稿目录', code: 'N4', sheetKey: '底稿目录', progress: 100, isCore: false, skip: false, linkageStatus: 'none' },
    { seq: 2, name: '税金及附加审计程序表 N4A', code: 'N4A', sheetKey: 'N4A', progress: getSheetProgress('N4A'), isCore: false, skip: false, linkageStatus: 'none' },
    { seq: 3, name: '税金及附加审定表 N4-1', code: 'N4-1', sheetKey: 'N4-1', progress: getSheetProgress('N4-1'), isCore: true, skip: false, linkageStatus: getAdjLinkageStatus() },
    { seq: 4, name: '税金及附加明细表 N4-2', code: 'N4-2', sheetKey: 'N4-2', progress: getSheetProgress('N4-2'), isCore: true, skip: false, linkageStatus: getDetailLinkageStatus() },
    { seq: 5, name: '调整分录汇总 N4-3', code: 'N4-3', sheetKey: 'N4-3', progress: getSheetProgress('N4-3'), isCore: false, skip: false, linkageStatus: 'none' },
    { seq: 6, name: '附注披露信息（上市公司）', code: '', sheetKey: '附注上市', progress: getSheetProgress('附注上市'), isCore: false, skip: false, linkageStatus: 'none' },
    { seq: 7, name: '附注披露信息（国有企业）', code: '', sheetKey: '附注国企', progress: getSheetProgress('附注国企'), isCore: false, skip: false, linkageStatus: 'none' },
    { seq: 8, name: 'O2A原底稿', code: 'O2A', sheetKey: 'O2A-skip', progress: 0, isCore: false, skip: true, linkageStatus: 'none' },
    { seq: 9, name: 'GT_Custom配置', code: '', sheetKey: 'GT_Custom', progress: 0, isCore: false, skip: true, linkageStatus: 'none' },
  ]
})

function getAdjLinkageStatus(): LinkageStatus {
  if (adjudicationVsDetail.value.isMatch && toIncomeStatement.value.amount !== 0) return 'matched'
  if (!adjudicationVsDetail.value.isMatch && adjudicationVsDetail.value.diff !== 0) return 'diff'
  return 'none'
}

function getDetailLinkageStatus(): LinkageStatus {
  if (adjudicationVsDetail.value.isMatch && toIncomeStatement.value.amount !== 0) return 'matched'
  if (!adjudicationVsDetail.value.isMatch && adjudicationVsDetail.value.diff !== 0) return 'diff'
  return 'none'
}

// ─── 进度计算 ────────────────────────────────────────────────────────────────

function getSheetProgress(code: string): number {
  if (props.allResponses.size === 0) return 0
  const prefixMap: Record<string, string> = {
    'N4A': 'N4-N4A-',
    'N4-1': 'N4-1-',
    'N4-2': 'N4-2-',
    'N4-3': 'N4-3-',
    '附注上市': 'N4-disclosure-listed-',
    '附注国企': 'N4-disclosure-soe-',
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
  emit('navigate-sheet', row.sheetKey)
}

function handleNavigate(row: SheetRow) {
  emit('navigate-sheet', row.sheetKey)
}

function getRowClassName({ row }: { row: SheetRow }): string {
  if (row.skip) return 'skip-row'
  if (row.progress >= 100) return 'completed-row'
  return ''
}

function getProgressColor(percent: number): string {
  if (percent >= 100) return '#67c23a'
  if (percent >= 50) return '#409eff'
  if (percent > 0) return '#e6a23c'
  return '#e6e8eb'
}

// ─── 格式化 ──────────────────────────────────────────────────────────────────

function fmtAmount(val: number | null | undefined): string {
  if (val == null || val === 0) return '—'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function fmtYoy(val: number): string {
  if (val === 0) return '—'
  const sign = val > 0 ? '↑' : '↓'
  return `${sign} ${(Math.abs(val) * 100).toFixed(1)}%`
}
</script>

<style scoped>
.n4-tab-index { padding: 12px; font-size: var(--wp-font-size, 13px); }

.n4-header-bar {
  display: flex; align-items: center; gap: 12px;
  padding: 10px 16px; margin-bottom: 16px;
  background: #f5f7fa; border: 1px solid #dcdfe6; border-radius: 6px; font-size: var(--wp-font-size, 13px);
}
.header-code { font-weight: 600; color: #303133; }
.header-sep { color: #c0c4cc; }
.header-subject { color: #606266; }
.header-direction { font-weight: 500; color: #e6a23c; }

.n4-expense-badge {
  display: flex; align-items: center; gap: 8px;
  padding: 10px 16px; margin-bottom: 16px;
  background: linear-gradient(135deg, #fff3e0 0%, #ffe0b2 100%);
  border: 1px solid #ffcc80; border-left: 4px solid #f57c00;
  border-radius: 6px; font-size: var(--wp-font-size, 13px); font-weight: 500; color: #e65100;
}
.n4-expense-badge .el-icon { font-size: 16px; color: #f57c00; flex-shrink: 0; }

.n4-guide {
  background: linear-gradient(135deg, #e8f4fd 0%, #d6eaf8 100%);
  border: 1px solid #b3d9f2; border-radius: 8px; padding: 14px 20px; margin-bottom: 16px;
}
.n4-guide-header { display: flex; align-items: center; gap: 6px; font-weight: 500; color: #1a73e8; margin-bottom: 10px; font-size: var(--wp-font-size, 13px); }
.n4-guide-steps { display: grid; grid-template-columns: repeat(2, 1fr); gap: 8px 24px; }
.step-item { display: flex; align-items: center; gap: 8px; font-size: var(--wp-font-size, 13px); color: #374151; }
.step-num { display: inline-flex; align-items: center; justify-content: center; width: 22px; height: 22px; border-radius: 50%; background: #1a73e8; color: #fff; font-size: 11px; font-weight: 600; flex-shrink: 0; }

/* ═══ 仪表板 ═══ */
.n4-dashboard { margin-bottom: 16px; padding: 14px 16px; background: #fafbfc; border: 1px solid #ebeef5; border-radius: 8px; }
.dashboard-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
.dashboard-title { font-size: 14px; font-weight: 600; color: #303133; }
.dashboard-grid { display: grid; grid-template-columns: repeat(5, 1fr); gap: 10px; }
@media (max-width: 1200px) { .dashboard-grid { grid-template-columns: repeat(3, 1fr); } }
@media (max-width: 768px) { .dashboard-grid { grid-template-columns: repeat(2, 1fr); } }
.dashboard-card {
  padding: 10px 12px; border-radius: 6px;
  background: #fff; border: 1px solid #ebeef5;
  position: relative; transition: box-shadow 0.2s;
}
.dashboard-card:hover { box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06); }
.dashboard-card.card-diff { border-color: #f56c6c; background: #fef0f0; }
.card-tax-name { font-size: 12px; font-weight: 600; color: #606266; margin-bottom: 6px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.card-amounts { display: flex; flex-direction: column; gap: 3px; }
.card-row { display: flex; justify-content: space-between; align-items: center; }
.card-label { font-size: 11px; color: #909399; }
.card-value { font-size: 12px; font-weight: 500; color: #303133; }
.card-prior { color: #909399; }
.card-up { color: #e6a23c; }
.card-down { color: #67c23a; }
.card-diff-badge {
  position: absolute; top: 4px; right: 4px;
  font-size: 10px; padding: 1px 4px; border-radius: 3px;
  background: #f56c6c; color: #fff; font-weight: 500;
}

/* ═══ 联动面板 ═══ */
.n4-linkage-panel { margin-bottom: 16px; padding: 14px 16px; background: #f0f9ff; border: 1px solid #bae6fd; border-radius: 8px; }
.linkage-title { font-size: var(--wp-font-size, 13px); font-weight: 500; color: #0369a1; margin-bottom: 10px; }
.linkage-items { display: flex; flex-wrap: wrap; gap: 10px; }
.linkage-item { display: flex; align-items: center; gap: 8px; padding: 6px 12px; background: #fff; border: 1px solid #e2e8f0; border-radius: 6px; font-size: 12px; }
.linkage-desc { color: #606266; }
.linkage-status { font-weight: 500; font-size: 11px; }
.linkage-status.linked { color: #43a047; }
.linkage-status.diff { color: #e6a23c; }
.linkage-status.pending { color: #9e9e9e; }

/* ═══ 进度条 ═══ */
.n4-progress-section { margin-bottom: 16px; padding: 12px 16px; background: #f5f7fa; border-radius: 6px; }
.progress-info { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; font-size: var(--wp-font-size, 13px); color: #606266; }
.progress-text { font-weight: 600; color: #303133; }

/* ═══ 目录卡片 ═══ */
.n4-index-card { margin-bottom: 16px; }
.card-title { font-size: 14px; font-weight: 600; color: #303133; }
.sheet-name-link { color: #1a73e8; cursor: pointer; font-size: var(--wp-font-size, 13px); }
.sheet-name-link:hover { text-decoration: underline; }
.sheet-name-skip { color: #c0c4cc; font-size: var(--wp-font-size, 13px); text-decoration: line-through; }
.no-index { color: #c0c4cc; }
.core-tag, .skip-tag { margin-left: 8px; font-size: 11px; vertical-align: middle; }
.progress-label { display: inline-block; margin-left: 8px; font-size: 12px; color: #909399; width: 32px; }
.skip-label { font-size: 12px; color: #c0c4cc; font-style: italic; }

.linkage-badge { display: inline-flex; align-items: center; justify-content: center; width: 24px; height: 24px; border-radius: 50%; font-size: var(--wp-font-size, 13px); font-weight: 600; }
.linkage-ok { background: #e8f5e9; color: #43a047; border: 1px solid #a5d6a7; }
.linkage-warn { background: #fff3e0; color: #e65100; border: 1px solid #ffcc80; }
.linkage-na { background: #f5f5f5; color: #bdbdbd; border: 1px solid #e0e0e0; }

/* ═══ 跨底稿引用 ═══ */
.n4-cross-refs {
  display: flex; align-items: center; gap: 6px; flex-wrap: wrap;
  margin-bottom: 16px; padding: 8px 12px; background: #f5f7fa; border-radius: 6px;
}
.cross-refs-label { color: #909399; font-size: 12px; white-space: nowrap; }

/* ═══ 行样式 ═══ */
:deep(.skip-row) { background-color: #f9f9f9 !important; opacity: 0.6; }
:deep(.skip-row:hover) { cursor: not-allowed !important; }
:deep(.completed-row) { background-color: #f0f9eb !important; }
:deep(.el-table) { font-size: var(--wp-font-size, 13px); }
:deep(.el-table .el-table__row) { cursor: pointer; }
:deep(.el-table .el-table__row:hover) { background-color: #ecf5ff !important; }

/* ═══ 编制提示 ═══ */
.n4-details-tip { margin-top: 12px; padding: 12px 16px; background: #fafafa; border: 1px solid #ebeef5; border-radius: 6px; font-size: var(--wp-font-size, 13px); color: #606266; }
.n4-details-tip summary { cursor: pointer; font-weight: 500; color: #303133; margin-bottom: 8px; }
.n4-details-tip ul { padding-left: 20px; margin: 8px 0 0; line-height: 1.8; }
</style>
