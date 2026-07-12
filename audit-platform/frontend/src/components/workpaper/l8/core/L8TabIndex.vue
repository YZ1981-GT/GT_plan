<template>
  <div class="l8-tab-index">
    <!-- ═══ 项目信息区 ═══ -->
    <el-card shadow="never" class="l8-project-info">
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
    <div class="l8-guide">
      <div class="l8-guide-header">
        <el-icon><InfoFilled /></el-icon>
        <span>操作步骤引导</span>
      </div>
      <div class="l8-guide-steps">
        <div class="step-item">
          <span class="step-num">①</span>
          <span class="step-text">填写审定表（L8-1）确认财务费用本期发生额（损益类/借方发生-贷方发生）</span>
        </div>
        <div class="step-item">
          <span class="step-num">②</span>
          <span class="step-text">录入明细（L8-2）按项目列示利息支出/收入/汇兑/手续费</span>
        </div>
        <div class="step-item">
          <span class="step-num">③</span>
          <span class="step-text">核对非金融利息测算（L8-4）+ 截止测试（L8-5）</span>
        </div>
        <div class="step-item">
          <span class="step-num">④</span>
          <span class="step-text">完成检查表（L8-6）+ 录入调整分录（L8-3）+ 核对附注</span>
        </div>
      </div>
    </div>

    <!-- ═══ 总体进度 ═══ -->
    <div class="l8-progress-section">
      <div class="progress-info">
        <span>编制进度</span>
        <span class="progress-text">{{ completedCount }} / {{ totalCount }} ({{ progressPercent }}%)</span>
      </div>
      <el-progress :percentage="progressPercent" :stroke-width="8" :show-text="false" />
    </div>

    <!-- ═══ 底稿目录表格 ═══ -->
    <el-card shadow="never" class="l8-index-card">
      <template #header>
        <span class="card-title">致同会计师事务所 / 财务费用底稿</span>
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
        <el-table-column prop="name" label="内容" min-width="260">
          <template #default="{ row }">
            <span class="sheet-name-link">{{ row.name }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="code" label="索引号" width="100" align="center" />
        <el-table-column label="进度" width="140" align="center">
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
        <el-table-column label="操作" width="80" align="center">
          <template #default="{ row }">
            <el-button
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
    <details class="l8-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li>财务费用为<strong>损益类科目</strong>：取本期发生额（借方发生 − 贷方发生），非期末余额</li>
        <li>科目编码：6603 财务费用</li>
        <li>L8是L筹资循环利息汇聚终点：接收L1短期借款/L3长期借款/L4应付债券利息 + L5摊销</li>
        <li>明细按费用项目列示：利息支出/利息收入/汇兑损益/手续费/其他</li>
        <li>非金融机构利息支出超过同期金融机构利率部分不可税前扣除</li>
        <li>截止性测试：序时账报告日±天数自动提取，检查费用归属期间正确性</li>
        <li>附注披露根据企业类型（上市/国企）自动切换模板</li>
        <li>调整分录需保持借贷平衡，通过EventBus同步更新审定表</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * L8TabIndex — L8 财务费用底稿目录
 *
 * 10 行 sheet 目录列表 + 进度条。
 * 点击行 emit navigate 事件（由 GtL8FinancialExpenses 监听切换 sheetName）。
 * 引导区 4 步：审定表(发生额) → 明细(费用项目) → 利息测算+截止 → 检查+调整+附注。
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
  progress: number
}

/**
 * 10 行 sheet 目录（底稿目录自身作为第0行展示）。
 * 进度条默认 0%，后续集成时根据 checklist_responses 数据填充。
 */
const sheetRows = computed<SheetRow[]>(() => [
  {
    seq: 0,
    name: '底稿目录',
    code: 'L8',
    sheetKey: '底稿目录',
    progress: 100,
  },
  {
    seq: 1,
    name: '财务费用实质性程序表',
    code: 'L8A',
    sheetKey: '实质性程序表L8A',
    progress: 0,
  },
  {
    seq: 2,
    name: '审定表',
    code: 'L8-1',
    sheetKey: '审定表L8-1',
    progress: 0,
  },
  {
    seq: 3,
    name: '附注披露信息核对（上市公司）',
    code: '附注上市',
    sheetKey: '附注披露信息（上市公司）',
    progress: 0,
  },
  {
    seq: 4,
    name: '附注披露信息核对（国企）',
    code: '附注国企',
    sheetKey: '附注披露信息（国企）',
    progress: 0,
  },
  {
    seq: 5,
    name: '明细表',
    code: 'L8-2',
    sheetKey: '明细表L8-2',
    progress: 0,
  },
  {
    seq: 6,
    name: '调整分录汇总',
    code: 'L8-3',
    sheetKey: '调整分录汇总L8-3',
    progress: 0,
  },
  {
    seq: 7,
    name: '非金融机构利息支出测算表',
    code: 'L8-4',
    sheetKey: '非金融机构利息支出测算表L8-4',
    progress: 0,
  },
  {
    seq: 8,
    name: '截止性测试',
    code: 'L8-5',
    sheetKey: '截止性测试L8-5',
    progress: 0,
  },
  {
    seq: 9,
    name: '财务费用检查表',
    code: 'L8-6',
    sheetKey: '财务费用检查表L8-6',
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

function handleNavigate(row: SheetRow) {
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
.l8-tab-index {
  padding: 12px;
  font-size: var(--wp-font-size, 13px);
}

/* ─── 项目信息区 ─── */
.l8-project-info {
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
.l8-guide {
  background: linear-gradient(135deg, #e8f4fd 0%, #d6eaf8 100%);
  border: 1px solid #b3d9f2;
  border-radius: 8px;
  padding: 14px 20px;
  margin-bottom: 16px;
}

.l8-guide-header {
  display: flex;
  align-items: center;
  gap: 6px;
  font-weight: 500;
  color: #1a73e8;
  margin-bottom: 10px;
  font-size: var(--wp-font-size, 13px);
}

.l8-guide-steps {
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
.l8-progress-section {
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
.l8-index-card {
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
.l8-details-tip {
  margin-top: 12px;
  padding: 12px 16px;
  background: #fafafa;
  border: 1px solid #ebeef5;
  border-radius: 6px;
  font-size: var(--wp-font-size, 13px);
  color: #606266;
}

.l8-details-tip summary {
  cursor: pointer;
  font-weight: 500;
  color: #303133;
  margin-bottom: 8px;
}

.l8-details-tip ul {
  padding-left: 20px;
  margin: 8px 0 0;
  line-height: 1.8;
}
</style>
