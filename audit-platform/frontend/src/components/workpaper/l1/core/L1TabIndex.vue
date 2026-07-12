<template>
  <div class="l1-tab-index">
    <!-- ═══ 项目信息区 ═══ -->
    <el-card shadow="never" class="l1-project-info">
      <div class="info-grid">
        <div class="info-item">
          <span class="info-label">客户名称</span>
          <span class="info-value">{{ projectInfo.clientName || '—' }}</span>
        </div>
        <div class="info-item">
          <span class="info-label">会计期间</span>
          <span class="info-value">{{ projectInfo.accountingPeriod || '—' }}</span>
        </div>
        <div class="info-item">
          <span class="info-label">编制人</span>
          <span class="info-value">{{ projectInfo.preparer || '—' }}</span>
        </div>
        <div class="info-item">
          <span class="info-label">复核人</span>
          <span class="info-value">{{ projectInfo.reviewer || '—' }}</span>
        </div>
      </div>
    </el-card>

    <!-- ═══ 蓝色渐变操作引导区 ═══ -->
    <div class="l1-guide">
      <div class="l1-guide-header">
        <el-icon><InfoFilled /></el-icon>
        <span>操作步骤引导</span>
      </div>
      <div class="l1-guide-steps">
        <div class="step-item">
          <span class="step-num">①</span>
          <span class="step-text">填写审定表（L1-1）确认科目余额</span>
        </div>
        <div class="step-item">
          <span class="step-num">②</span>
          <span class="step-text">录入借款明细（L1-2）按合同列示</span>
        </div>
        <div class="step-item">
          <span class="step-num">③</span>
          <span class="step-text">利息测算（L1-5）验证应计利息</span>
        </div>
        <div class="step-item">
          <span class="step-num">④</span>
          <span class="step-text">征信/逾期核对（L1-4/L1-7）确认完整性</span>
        </div>
      </div>
    </div>

    <!-- ═══ 总体进度 ═══ -->
    <div class="l1-progress-section">
      <div class="progress-info">
        <span>编制进度</span>
        <span class="progress-text">{{ completedCount }} / {{ totalCount }} ({{ progressPercent }}%)</span>
      </div>
      <el-progress :percentage="progressPercent" :stroke-width="8" :show-text="false" />
    </div>

    <!-- ═══ 底稿目录表格 ═══ -->
    <el-card shadow="never" class="l1-index-card">
      <template #header>
        <span class="card-title">L1 短期借款底稿目录</span>
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
        <el-table-column prop="name" label="底稿名称" min-width="220">
          <template #default="{ row }">
            <span class="sheet-name-link">{{ row.name }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="code" label="索引号" width="90" align="center" />
        <el-table-column prop="description" label="简要说明" min-width="200" />
        <el-table-column label="完成进度" width="140" align="center">
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
    <details class="l1-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li>短期借款为<strong>负债类贷方科目</strong>：期末 = 期初 + 贷方（借入）− 借方（归还）</li>
        <li>利息测算采用 <strong>365 天制</strong>：利息 = 本金 × 年利率 × 天数 / 365</li>
        <li>征信报告核对保证借款完整性：差异需逐笔说明</li>
        <li>逾期贷款需评价风险等级并关注展期情况</li>
        <li>L1-5 利息测算结果将联动 L2 应付利息 / L8 财务费用</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * L1TabIndex — L1 短期借款底稿目录
 *
 * 12 行 sheet 目录列表（排除底稿目录自身）+ 进度条。
 * 点击行 emit navigate 事件（由 GtL1ShortTermLoans 监听切换 sheetName）。
 * 引导区 4 步：审定表 → 明细 → 利息测算 → 征信/逾期核对。
 *
 * Requirements: 1.2
 */
import { computed } from 'vue'
import { InfoFilled } from '@element-plus/icons-vue'

// ─── Props / Emits ───────────────────────────────────────────────────────────

const props = defineProps<{
  wpId: string
  projectId: string
  isReadonly: boolean
}>()

const emit = defineEmits<{
  (e: 'navigate', sheetName: string): void
}>()

// ─── Sheet 目录行定义 ────────────────────────────────────────────────────────

interface SheetRow {
  seq: number
  name: string
  code: string
  /** sheetName（传给父组件用于 v-if 分发） */
  sheetKey: string
  description: string
  progress: number
}

/**
 * 12 行 sheet 目录（底稿目录自身不出现在列表中）。
 * 进度条默认 0%，后续集成时根据 checklist_responses 数据填充。
 */
const sheetRows = computed<SheetRow[]>(() => [
  {
    seq: 1,
    name: '短期借款实质性程序表',
    code: 'L1A',
    sheetKey: ' 短期借款实质性程序表L1A',
    description: '实质性程序清单与执行情况',
    progress: 0,
  },
  {
    seq: 2,
    name: '审定表',
    code: 'L1-1',
    sheetKey: '审定表L1-1',
    description: '科目审定汇总（负债类贷方，期末=期初+贷-借）',
    progress: 0,
  },
  {
    seq: 3,
    name: '附注披露信息核对（上市公司）',
    code: '附注上市',
    sheetKey: '附注披露信息核对（上市公司）',
    description: '上市公司短期借款附注披露核对',
    progress: 0,
  },
  {
    seq: 4,
    name: '附注披露信息核对（国企）',
    code: '附注国企',
    sheetKey: '附注披露信息核对（国企）',
    description: '国有企业短期借款附注披露核对',
    progress: 0,
  },
  {
    seq: 5,
    name: '明细表',
    code: 'L1-2',
    sheetKey: '明细表L1-2',
    description: '按借款银行/合同逐笔列示借款明细（30列）',
    progress: 0,
  },
  {
    seq: 6,
    name: '调整分录汇总',
    code: 'L1-3',
    sheetKey: '调整分录汇总L1-3',
    description: 'AJE/RJE管理（借贷平衡校验）',
    progress: 0,
  },
  {
    seq: 7,
    name: '征信报告核对表',
    code: 'L1-4',
    sheetKey: '征信报告核对表L1-4',
    description: '征信报告与账面余额核对（完整性认定）',
    progress: 0,
  },
  {
    seq: 8,
    name: '利息测算表',
    code: 'L1-5',
    sheetKey: '利息测算表L1-5',
    description: '利息=本金×利率×天数/365（联动L2/L8）',
    progress: 0,
  },
  {
    seq: 9,
    name: '贷款合同检查',
    code: 'L1-6',
    sheetKey: '贷款合同检查L1-6',
    description: '合同要素检查（32列分区段+行级OCR）',
    progress: 0,
  },
  {
    seq: 10,
    name: '逾期贷款检查表',
    code: 'L1-7',
    sheetKey: '逾期贷款检查表L1-7',
    description: '逾期天数计算与风险评价',
    progress: 0,
  },
  {
    seq: 11,
    name: '抵质押资产检查表',
    code: 'L1-8',
    sheetKey: '抵质押资产检查表L1-8',
    description: '担保比例=担保借款/账面价值×100%',
    progress: 0,
  },
  {
    seq: 12,
    name: '短期借款检查表',
    code: 'L1-9',
    sheetKey: '短期借款检查表L1-9',
    description: '综合核对清单与审计结论',
    progress: 0,
  },
])

// ─── 进度计算 ─────────────────────────────────────────────────────────────────

const totalCount = computed(() => sheetRows.value.length)

const completedCount = computed(() =>
  sheetRows.value.filter(r => r.progress >= 100).length,
)

const progressPercent = computed(() => {
  if (totalCount.value === 0) return 0
  const avgProgress = sheetRows.value.reduce((sum, r) => sum + r.progress, 0) / totalCount.value
  return Math.round(avgProgress)
})

// ─── 项目信息（简单版：默认占位，后续集成时从 render-config 填充） ──────────

const projectInfo = computed(() => ({
  clientName: '',
  accountingPeriod: '',
  preparer: '',
  reviewer: '',
}))

// ─── 交互 ────────────────────────────────────────────────────────────────────

function handleRowClick(row: SheetRow) {
  if (props.isReadonly && row.progress === 0) return
  emit('navigate', row.sheetKey)
}

function getRowClassName({ row }: { row: SheetRow }): string {
  return row.progress >= 100 ? 'completed-row' : ''
}

function getProgressColor(percent: number): string {
  if (percent >= 100) return '#67c23a'
  if (percent >= 50) return '#409eff'
  return '#e6e8eb'
}
</script>

<style scoped>
.l1-tab-index {
  padding: 12px;
  font-size: var(--wp-font-size, 13px);
}

/* ─── 项目信息区 ─── */
.l1-project-info {
  margin-bottom: 16px;
}

.info-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 12px 32px;
}

.info-item {
  display: flex;
  align-items: center;
  gap: 8px;
}

.info-label {
  font-size: var(--wp-font-size, 13px);
  color: #909399;
  white-space: nowrap;
}

.info-value {
  font-size: var(--wp-font-size, 13px);
  font-weight: 500;
  color: #303133;
}

/* ─── 蓝色渐变引导区 ─── */
.l1-guide {
  background: linear-gradient(135deg, #e8f4fd 0%, #d6eaf8 100%);
  border: 1px solid #b3d9f2;
  border-radius: 8px;
  padding: 14px 20px;
  margin-bottom: 16px;
}

.l1-guide-header {
  display: flex;
  align-items: center;
  gap: 6px;
  font-weight: 500;
  color: #1a73e8;
  margin-bottom: 10px;
  font-size: var(--wp-font-size, 13px);
}

.l1-guide-steps {
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
}

.step-text {
  font-size: var(--wp-font-size, 13px);
}

/* ─── 进度条区 ─── */
.l1-progress-section {
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

/* ─── 目录卡片 ─── */
.l1-index-card {
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

.progress-label {
  display: inline-block;
  margin-left: 8px;
  font-size: 12px;
  color: #909399;
  width: 32px;
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
.l1-details-tip {
  margin-top: 12px;
  padding: 12px 16px;
  background: #fafafa;
  border: 1px solid #ebeef5;
  border-radius: 6px;
  font-size: var(--wp-font-size, 13px);
  color: #606266;
}

.l1-details-tip summary {
  cursor: pointer;
  font-weight: 500;
  color: #303133;
  margin-bottom: 8px;
}

.l1-details-tip ul {
  padding-left: 20px;
  margin: 8px 0 0;
  line-height: 1.8;
}
</style>
