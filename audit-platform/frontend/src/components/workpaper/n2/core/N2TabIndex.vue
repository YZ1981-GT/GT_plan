<template>
  <div class="n2-tab-index">
    <!-- ═══ 顶部标识头 ═══ -->
    <div class="n2-header-bar">
      <span class="header-code">底稿编码 N2</span>
      <span class="header-sep">|</span>
      <span class="header-subject">科目 2221 应交税费</span>
      <span class="header-sep">|</span>
      <span class="header-direction">负债类 / 贷方</span>
    </div>

    <!-- ═══ 负债类贷方科目醒目标注 ═══ -->
    <div class="n2-liability-badge">
      <el-icon><WarningFilled /></el-icon>
      <span>应交税费为负债类贷方科目（期末 = 期初 + 贷方 − 借方），涵盖增值税/城建税/房产税/土地增值税/出口退税等多税种</span>
    </div>

    <!-- ═══ 蓝色渐变操作引导区 ═══ -->
    <div class="n2-guide">
      <div class="n2-guide-header">
        <el-icon><InfoFilled /></el-icon>
        <span>操作步骤引导</span>
      </div>
      <div class="n2-guide-steps">
        <div class="step-item">
          <span class="step-num">①</span>
          <span class="step-text">填写审定表（N2-1）确认各税种期末余额（负债类：期初+贷方−借方）</span>
        </div>
        <div class="step-item">
          <span class="step-num">②</span>
          <span class="step-text">录入明细（N2-2）按税种逐项列示计提/缴纳/期末</span>
        </div>
        <div class="step-item">
          <span class="step-num">③</span>
          <span class="step-text">完成增值税测算（N2-6）+ 其他税费测算（N2-8/N2-9/N2-10）</span>
        </div>
        <div class="step-item">
          <span class="step-num">④</span>
          <span class="step-text">税收政策检查（N2-4）+ 认定表（N2-5）+ 检查表（N2-11）+ 附注</span>
        </div>
      </div>
    </div>

    <!-- ═══ 总体进度 ═══ -->
    <div class="n2-progress-section">
      <div class="progress-info">
        <span>编制进度</span>
        <span class="progress-text">{{ completedCount }} / {{ effectiveTotal }} ({{ progressPercent }}%)</span>
      </div>
      <el-progress :percentage="progressPercent" :stroke-width="8" :show-text="false" />
    </div>

    <!-- ═══ 多税种统计仪表板 ═══ -->
    <div class="n2-tax-dashboard">
      <div class="dashboard-title">各税种完成状态</div>
      <div class="dashboard-cards">
        <div
          v-for="card in taxStatusCards"
          :key="card.tax"
          class="tax-card"
          :class="[`tax-card--${card.status}`]"
        >
          <div class="tax-card-name">{{ card.tax }}</div>
          <div class="tax-card-status">
            <span v-if="card.status === 'done'" class="status-icon status-done">✓</span>
            <span v-else-if="card.status === 'warn'" class="status-icon status-warn">⚠</span>
            <span v-else class="status-icon status-pending">○</span>
            <span class="status-label">{{ card.label }}</span>
          </div>
        </div>
      </div>
    </div>

    <!-- ═══ 底稿目录表格 ═══ -->
    <el-card shadow="never" class="n2-index-card">
      <template #header>
        <span class="card-title">致同会计师事务所 / 应交税费底稿</span>
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
        <el-table-column prop="name" label="内容" min-width="240">
          <template #default="{ row }">
            <span :class="row.skip ? 'sheet-name-skip' : 'sheet-name-link'">{{ row.name }}</span>
            <el-tag v-if="row.isCore" size="small" type="danger" class="core-tag">核心</el-tag>
            <el-tag v-if="row.skip" size="small" type="info" class="skip-tag">OnlyOffice</el-tag>
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
            <span v-else class="skip-label">跳过</span>
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
            <el-button
              v-if="!row.skip"
              type="primary"
              link
              size="small"
              @click.stop="handleNavigate(row)"
            >
              进入
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- ═══ 编制提示（折叠） ═══ -->
    <details class="n2-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li>应交税费（2221）为<strong>负债类贷方科目</strong>：期末 = 期初 + 本期贷方（计提增加）− 本期借方（缴纳减少）</li>
        <li>本底稿涵盖<strong>多税种测算</strong>：增值税/城建税及附加/房产税/土地增值税/出口退税</li>
        <li>增值税核心公式：应交增值税 = 销项税额 −（进项税额 − 进项转出）</li>
        <li>城建税及附加计税依据取自N2-6增值税测算结果，城建税率分市区7%/县城5%/其他1%</li>
        <li>房产税：从价=原值×(1−扣除比例)×1.2%；从租=租金×12%</li>
        <li>土地增值税：四级超率累进（30%/40%/50%/60%），增值率=增值额/扣除项目</li>
        <li>各税种计提联动N4税金及附加（通过EventBus 'tax-accrual:updated'）</li>
        <li>O1A原底稿/出口退税额复核示例为参考性辅助sheet，走OnlyOffice</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * N2TabIndex — N2 应交税费底稿目录
 *
 * 18 行 sheet 目录（2 行标记 skip：O1A原底稿、出口退税额复核示例）。
 * 有效sheet 16 个，进度条展示 n/16 完成度。
 * 多税种统计仪表板：增值税/城建税/房产税/土地增值税/出口退税 完成状态。
 * 联动状态列：从 useN2CrossSheet 获取各sheet勾稽状态。
 * 点击行 emit navigate 事件（由 GtN2TaxesPayable 监听切换 sheetName）。
 *
 * Requirements: 1.2, 1.11
 */
import { computed } from 'vue'
import { InfoFilled, WarningFilled } from '@element-plus/icons-vue'
import GtIndexChip from '@/components/workpaper/GtIndexChip.vue'
import { useN2CrossSheet } from '../../composables/useN2CrossSheet'

// ─── Props / Emits ───────────────────────────────────────────────────────────

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly?: boolean
}>()

const emit = defineEmits<{
  (e: 'navigate', sheetCode: string): void
}>()

// ─── CrossSheet 联动 ─────────────────────────────────────────────────────────

const allResponsesRef = computed(() => props.allResponses)
const {
  adjudicationVsDetail,
  adjudicationVsCalcTables,
} = useN2CrossSheet(allResponsesRef)

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

// ─── Sheet 目录行定义（18行，2行 skip） ──────────────────────────────────────

const sheetRows = computed<SheetRow[]>(() => {
  // 联动状态计算
  const hasData = props.allResponses.size > 0
  const detailMatch = adjudicationVsDetail.value.isMatch
  const calcMatches = adjudicationVsCalcTables.value

  // N2-1审定表需同时与明细和各测算表勾稽
  const n2_1Linkage: LinkageStatus =
    detailMatch && calcMatches.every(c => c.isMatch)
      ? 'matched'
      : (hasData ? 'diff' : 'none')

  const n2_2Linkage: LinkageStatus =
    detailMatch ? 'matched' : (hasData ? 'diff' : 'none')

  // 找到特定税种的测算勾稽状态
  const findCalcStatus = (tax: string): LinkageStatus => {
    const item = calcMatches.find(c => c.tax === tax)
    if (!item) return 'none'
    return item.isMatch ? 'matched' : (hasData ? 'diff' : 'none')
  }

  return [
    { seq: 1, name: '底稿目录', code: '', sheetKey: '底稿目录', progress: 100, isCore: false, skip: false, linkageStatus: 'none' },
    { seq: 2, name: '应交税费实质性程序表', code: 'N2A', sheetKey: '应交税费实质性程序表N2A', progress: 0, isCore: false, skip: false, linkageStatus: 'none' },
    { seq: 3, name: '应交税费审定表', code: 'N2-1', sheetKey: '审定表N2-1', progress: 0, isCore: true, skip: false, linkageStatus: n2_1Linkage },
    { seq: 4, name: '应交税费明细表', code: 'N2-2', sheetKey: '明细表N2-2', progress: 0, isCore: true, skip: false, linkageStatus: n2_2Linkage },
    { seq: 5, name: '调整分录汇总', code: 'N2-3', sheetKey: '调整分录汇总N2-3', progress: 0, isCore: false, skip: false, linkageStatus: 'none' },
    { seq: 6, name: '税收政策检查', code: 'N2-4', sheetKey: '税收政策检查N2-4', progress: 0, isCore: false, skip: false, linkageStatus: 'none' },
    { seq: 7, name: '应交税金认定表', code: 'N2-5', sheetKey: '认定表N2-5', progress: 0, isCore: false, skip: false, linkageStatus: 'none' },
    { seq: 8, name: '增值税测算表', code: 'N2-6', sheetKey: '增值税测算表N2-6', progress: 0, isCore: true, skip: false, linkageStatus: findCalcStatus('增值税') },
    { seq: 9, name: '出口退税核对表', code: 'N2-7', sheetKey: '出口退税核对表N2-7', progress: 0, isCore: false, skip: false, linkageStatus: 'none' },
    { seq: 10, name: '其他税费测算表', code: 'N2-8', sheetKey: '其他税费测算表N2-8', progress: 0, isCore: true, skip: false, linkageStatus: findCalcStatus('城建税') },
    { seq: 11, name: '房产税测算表', code: 'N2-9', sheetKey: '房产税测算表N2-9', progress: 0, isCore: false, skip: false, linkageStatus: findCalcStatus('房产税') },
    { seq: 12, name: '土地增值税测算表', code: 'N2-10', sheetKey: '土地增值税测算表N2-10', progress: 0, isCore: false, skip: false, linkageStatus: findCalcStatus('土地增值税') },
    { seq: 13, name: '应交税费检查表', code: 'N2-11', sheetKey: '应交税费检查表N2-11', progress: 0, isCore: false, skip: false, linkageStatus: 'none' },
    { seq: 14, name: '附注披露信息（上市公司）', code: '', sheetKey: '附注上市', progress: 0, isCore: false, skip: false, linkageStatus: 'none' },
    { seq: 15, name: '附注披露信息（国有企业）', code: '', sheetKey: '附注国企', progress: 0, isCore: false, skip: false, linkageStatus: 'none' },
    { seq: 16, name: 'O1A原底稿', code: '', sheetKey: 'O1A原底稿', progress: 0, isCore: false, skip: true, linkageStatus: 'none' },
    { seq: 17, name: '出口退税额复核示例', code: '', sheetKey: '出口退税额复核示例', progress: 0, isCore: false, skip: true, linkageStatus: 'none' },
  ]
})

// ─── 进度计算（有效sheet = 排除 skip 的 16 个，再排除目录自身 = 15 个计量对象） ─

const effectiveSheets = computed(() => sheetRows.value.filter(r => !r.skip && r.seq !== 1))
const effectiveTotal = computed(() => effectiveSheets.value.length)
const completedCount = computed(() => effectiveSheets.value.filter(r => r.progress >= 100).length)
const progressPercent = computed(() => {
  if (effectiveTotal.value === 0) return 0
  const avg = effectiveSheets.value.reduce((s, r) => s + r.progress, 0) / effectiveTotal.value
  return Math.round(avg)
})

// ─── 多税种统计仪表板 ────────────────────────────────────────────────────────

interface TaxStatusCard {
  tax: string
  status: 'done' | 'warn' | 'pending'
  label: string
}

const taxStatusCards = computed<TaxStatusCard[]>(() => {
  const hasData = props.allResponses.size > 0
  const calcResults = adjudicationVsCalcTables.value

  function getStatus(taxName: string): TaxStatusCard {
    const match = calcResults.find(c => c.tax === taxName)
    if (!hasData || !match) return { tax: taxName, status: 'pending', label: '待编制' }
    return match.isMatch
      ? { tax: taxName, status: 'done', label: '已核对' }
      : { tax: taxName, status: 'warn', label: '有差异' }
  }

  // 出口退税独立判断（无测算交叉验证，仅看N2-7是否有数据）
  const exportRefundStatus: TaxStatusCard = hasData && props.allResponses.has('N2-7-total')
    ? { tax: '出口退税', status: 'done', label: '已核对' }
    : { tax: '出口退税', status: 'pending', label: '待编制' }

  return [
    getStatus('增值税'),
    getStatus('城建税'),
    getStatus('房产税'),
    getStatus('土地增值税'),
    exportRefundStatus,
  ]
})

// ─── 交互 ────────────────────────────────────────────────────────────────────

function handleRowClick(row: SheetRow) {
  if (row.skip) return
  if (props.isReadonly && row.progress === 0) return
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
</script>

<style scoped>
.n2-tab-index {
  padding: 12px;
  font-size: var(--wp-font-size, 13px);
}

/* ─── 顶部标识头 ─── */
.n2-header-bar {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 16px;
  margin-bottom: 16px;
  background: #f5f7fa;
  border: 1px solid #dcdfe6;
  border-radius: 6px;
  font-size: var(--wp-font-size, 13px);
}

.header-code {
  font-weight: 600;
  color: #303133;
}

.header-sep {
  color: #c0c4cc;
}

.header-subject {
  color: #606266;
}

.header-direction {
  font-weight: 500;
  color: #e6a23c;
}

/* ─── 负债类贷方科目醒目标注 ─── */
.n2-liability-badge {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 16px;
  margin-bottom: 16px;
  background: linear-gradient(135deg, #fce4ec 0%, #f8bbd0 100%);
  border: 1px solid #f48fb1;
  border-left: 4px solid #e91e63;
  border-radius: 6px;
  font-size: var(--wp-font-size, 13px);
  font-weight: 500;
  color: #880e4f;
}

.n2-liability-badge .el-icon {
  font-size: 16px;
  color: #e91e63;
  flex-shrink: 0;
}

/* ─── 蓝色渐变引导区 ─── */
.n2-guide {
  background: linear-gradient(135deg, #e8f4fd 0%, #d6eaf8 100%);
  border: 1px solid #b3d9f2;
  border-radius: 8px;
  padding: 14px 20px;
  margin-bottom: 16px;
}

.n2-guide-header {
  display: flex;
  align-items: center;
  gap: 6px;
  font-weight: 500;
  color: #1a73e8;
  margin-bottom: 10px;
  font-size: var(--wp-font-size, 13px);
}

.n2-guide-steps {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 8px 24px;
}

.step-item {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: var(--wp-font-size, 13px);
  color: #374151;
}

.step-num {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  border-radius: 50%;
  background: #1a73e8;
  color: #fff;
  font-size: 11px;
  font-weight: 600;
  flex-shrink: 0;
}

.step-text {
  font-size: var(--wp-font-size, 13px);
}

/* ─── 进度条区 ─── */
.n2-progress-section {
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

/* ─── 多税种统计仪表板 ─── */
.n2-tax-dashboard {
  margin-bottom: 16px;
  padding: 14px 16px;
  background: #fafbfc;
  border: 1px solid #ebeef5;
  border-radius: 8px;
}

.dashboard-title {
  font-size: var(--wp-font-size, 13px);
  font-weight: 500;
  color: #303133;
  margin-bottom: 10px;
}

.dashboard-cards {
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  gap: 10px;
}

.tax-card {
  padding: 10px 12px;
  border-radius: 6px;
  border: 1px solid #e4e7ed;
  background: #fff;
  text-align: center;
  transition: box-shadow 0.2s;
}

.tax-card:hover {
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
}

.tax-card--done {
  border-color: #a5d6a7;
  background: #e8f5e9;
}

.tax-card--warn {
  border-color: #ffcc80;
  background: #fff3e0;
}

.tax-card--pending {
  border-color: #e4e7ed;
  background: #fafafa;
}

.tax-card-name {
  font-size: 12px;
  font-weight: 500;
  color: #303133;
  margin-bottom: 6px;
}

.tax-card-status {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 4px;
}

.status-icon {
  font-size: var(--wp-font-size, 13px);
  font-weight: 600;
}

.status-done {
  color: #43a047;
}

.status-warn {
  color: #e65100;
}

.status-pending {
  color: #bdbdbd;
}

.status-label {
  font-size: 11px;
  color: #909399;
}

/* ─── 目录卡片 ─── */
.n2-index-card {
  margin-bottom: 16px;
}

.card-title {
  font-size: 14px;
  font-weight: 600;
  color: #303133;
}

.sheet-name-link {
  color: #1a73e8;
  cursor: pointer;
  font-size: var(--wp-font-size, 13px);
}

.sheet-name-link:hover {
  text-decoration: underline;
}

.sheet-name-skip {
  color: #c0c4cc;
  font-size: var(--wp-font-size, 13px);
  text-decoration: line-through;
}

.no-index {
  color: #c0c4cc;
}

.core-tag {
  margin-left: 8px;
  font-size: 11px;
  vertical-align: middle;
}

.skip-tag {
  margin-left: 8px;
  font-size: 11px;
  vertical-align: middle;
}

.progress-label {
  display: inline-block;
  margin-left: 8px;
  font-size: 12px;
  color: #909399;
  width: 32px;
}

.skip-label {
  font-size: 12px;
  color: #c0c4cc;
  font-style: italic;
}

/* ─── 联动状态 badge ─── */
.linkage-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  border-radius: 50%;
  font-size: var(--wp-font-size, 13px);
  font-weight: 600;
}

.linkage-ok {
  background: #e8f5e9;
  color: #43a047;
  border: 1px solid #a5d6a7;
}

.linkage-warn {
  background: #fff3e0;
  color: #e65100;
  border: 1px solid #ffcc80;
}

.linkage-na {
  background: #f5f5f5;
  color: #bdbdbd;
  border: 1px solid #e0e0e0;
}

:deep(.skip-row) {
  background-color: #f9f9f9 !important;
  opacity: 0.6;
}

:deep(.skip-row:hover) {
  cursor: not-allowed !important;
}

:deep(.completed-row) {
  background-color: #f0f9eb !important;
}

:deep(.el-table) {
  font-size: var(--wp-font-size, 13px);
}

:deep(.el-table .el-table__row) {
  cursor: pointer;
}

:deep(.el-table .el-table__row:hover) {
  background-color: #ecf5ff !important;
}

/* ─── 编制提示折叠 ─── */
.n2-details-tip {
  margin-top: 12px;
  padding: 12px 16px;
  background: #fafafa;
  border: 1px solid #ebeef5;
  border-radius: 6px;
  font-size: var(--wp-font-size, 13px);
  color: #606266;
}

.n2-details-tip summary {
  cursor: pointer;
  font-weight: 500;
  color: #303133;
  margin-bottom: 8px;
}

.n2-details-tip ul {
  padding-left: 20px;
  margin: 8px 0 0;
  line-height: 1.8;
}
</style>
