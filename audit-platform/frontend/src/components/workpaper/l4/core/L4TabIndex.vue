<template>
  <div class="l4-tab-index">
    <!-- ═══ 项目信息区 ═══ -->
    <el-card shadow="never" class="l4-project-info">
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
    <div class="l4-guide">
      <div class="l4-guide-header">
        <el-icon><InfoFilled /></el-icon>
        <span>操作步骤引导</span>
      </div>
      <div class="l4-guide-steps">
        <div class="step-item">
          <span class="step-num">①</span>
          <span class="step-text">填写审定表（L4-1）确认应付债券科目余额（贷方/负债类）</span>
        </div>
        <div class="step-item">
          <span class="step-num">②</span>
          <span class="step-text">录入明细（L4-2）89列极宽表按区段Tab操作</span>
        </div>
        <div class="step-item">
          <span class="step-num">③</span>
          <span class="step-text">初始计量（L4-6）→后续计量（L4-7 分支选择）→账面核对（L4-8）</span>
        </div>
        <div class="step-item">
          <span class="step-num">④</span>
          <span class="step-text">权益负债划分（L4-5）+检查表（L4-9）+利息联动L2/L8</span>
        </div>
      </div>
    </div>

    <!-- ═══ 总体进度 ═══ -->
    <div class="l4-progress-section">
      <div class="progress-info">
        <span>编制进度</span>
        <span class="progress-text">{{ completedCount }} / {{ totalCount }} ({{ progressPercent }}%)</span>
      </div>
      <el-progress :percentage="progressPercent" :stroke-width="8" :show-text="false" />
    </div>

    <!-- ═══ 底稿目录表格 ═══ -->
    <el-card shadow="never" class="l4-index-card">
      <template #header>
        <span class="card-title">L4 应付债券底稿目录</span>
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
        <el-table-column prop="name" label="底稿名称" min-width="260">
          <template #default="{ row }">
            <span class="sheet-name-link">{{ row.name }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="code" label="索引号" width="100" align="center" />
        <el-table-column prop="description" label="简要说明" min-width="240" />
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
    <details class="l4-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li>应付债券为<strong>负债类贷方科目</strong>：期末 = 期初 + 贷方（发行+利息调整）− 借方（兑付）</li>
        <li><strong>实际利率法</strong>后续计量：每期利息费用 = 期初摊余成本 × 实际利率</li>
        <li>2分支付息方式：<strong>到期一次还本付息</strong>（利息资本化滚入）/ <strong>分期付息到期一次还本</strong>（期间扣减实付）</li>
        <li>初始计量：初始入账金额 = 发行价格 − 交易费用；溢折价 = 初始入账 − 面值</li>
        <li><strong>权益负债划分</strong>：可转债等复合工具需按市场利率折现负债成分，剩余归权益</li>
        <li>L4-7 利息测算结果将联动 L2 应付利息 / L8 财务费用</li>
        <li>最后一期摊余成本应≈面值（允许 ±1 元尾差）</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * L4TabIndex — L4 应付债券底稿目录
 *
 * 12 行 sheet 目录列表（底稿目录自身不出现，L4-7/L4-8各2分支合为1行）+ 进度条。
 * 点击行 emit navigate 事件（由 GtL4BondsPayable 监听切换 sheetName）。
 * 引导区 4 步：审定表 → 明细89列 → 初始/后续/账面核对 → 权益划分+检查+联动。
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
 * 12 行 sheet 目录（底稿目录自身不出现；L4-7/L4-8各2分支在目录中合为1行）。
 * 进度条默认 0%，后续集成时根据 checklist_responses 数据填充。
 */
const sheetRows = computed<SheetRow[]>(() => [
  {
    seq: 1,
    name: '应付债券实质性程序表',
    code: 'L4A',
    sheetKey: '应付债券实质性程序表L4A',
    description: '实质性程序清单与执行情况',
    progress: 0,
  },
  {
    seq: 2,
    name: '审定表',
    code: 'L4-1',
    sheetKey: '审定表L4-1',
    description: '科目审定汇总（负债类贷方，面值/溢折价/摊余成本，含品种小计）',
    progress: 0,
  },
  {
    seq: 3,
    name: '附注披露信息核对（上市公司）',
    code: '附注上市',
    sheetKey: '附注披露信息核对（上市公司）',
    description: '上市公司应付债券附注披露核对',
    progress: 0,
  },
  {
    seq: 4,
    name: '附注披露信息核对（国企）',
    code: '附注国企',
    sheetKey: '附注披露信息核对（国企）',
    description: '国有企业应付债券附注披露核对',
    progress: 0,
  },
  {
    seq: 5,
    name: '应付债券明细表',
    code: 'L4-2',
    sheetKey: '应付债券明细表L4-2',
    description: '89列极宽表！按区段Tab拆分（基础/发行/计息付息/摊余成本/兑付）',
    progress: 0,
  },
  {
    seq: 6,
    name: '划分为金融负债的其他金融工具明细表',
    code: 'L4-3',
    sheetKey: '划分为金融负债的其他金融工具明细表L4-3',
    description: '其他金融工具金融负债分类明细（27×40，8公式）',
    progress: 0,
  },
  {
    seq: 7,
    name: '调整分录汇总',
    code: 'L4-4',
    sheetKey: '调整分录汇总L4-4',
    description: 'AJE/RJE管理（借贷平衡校验+EventBus双向同步L4-1）',
    progress: 0,
  },
  {
    seq: 8,
    name: '权益与负债划分检查表',
    code: 'L4-5',
    sheetKey: '权益与负债划分检查表L4-5',
    description: '复合金融工具分拆：权益成分=发行总额−负债成分现值',
    progress: 0,
  },
  {
    seq: 9,
    name: '应付债券初始计量',
    code: 'L4-6',
    sheetKey: '应付债券初始计量L4-6',
    description: '初始入账=发行价−交易费用；溢折价；IRR求解实际利率',
    progress: 0,
  },
  {
    seq: 10,
    name: '应付债券后续计量',
    code: 'L4-7',
    sheetKey: '应付债券后续计量L4-7',
    description: '核心！实际利率法2分支（到期一次还本付息 / 分期付息到期一次还本）',
    progress: 0,
  },
  {
    seq: 11,
    name: '应付债券账面核对',
    code: 'L4-8',
    sheetKey: '应付债券账面核对L4-8',
    description: '账面摊余成本 vs L4-7测算摊余成本（差异高亮，与L4-7联动）',
    progress: 0,
  },
  {
    seq: 12,
    name: '应付债券检查表',
    code: 'L4-9',
    sheetKey: '应付债券检查表L4-9',
    description: '综合核对清单与审计结论（el-card包裹+AI辅助）',
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
.l4-tab-index {
  padding: 12px;
  font-size: 13px;
}

/* ─── 项目信息区 ─── */
.l4-project-info {
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
  font-size: 13px;
  color: #909399;
  white-space: nowrap;
}

.info-value {
  font-size: 13px;
  font-weight: 500;
  color: #303133;
}

/* ─── 蓝色渐变引导区 ─── */
.l4-guide {
  background: linear-gradient(135deg, #e8f4fd 0%, #d6eaf8 100%);
  border: 1px solid #b3d9f2;
  border-radius: 8px;
  padding: 14px 20px;
  margin-bottom: 16px;
}

.l4-guide-header {
  display: flex;
  align-items: center;
  gap: 6px;
  font-weight: 500;
  color: #1a73e8;
  margin-bottom: 10px;
  font-size: 13px;
}

.l4-guide-steps {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 8px 24px;
}

.step-item {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
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
  font-size: 13px;
}

/* ─── 进度条区 ─── */
.l4-progress-section {
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
  font-size: 13px;
  color: #606266;
}

.progress-text {
  font-weight: 600;
  color: #303133;
}

/* ─── 目录卡片 ─── */
.l4-index-card {
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
  font-size: 13px;
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
  font-size: 13px;
}

:deep(.el-table .el-table__row) {
  cursor: pointer;
}

:deep(.el-table .el-table__row:hover) {
  background-color: #ecf5ff !important;
}

/* ─── 编制提示折叠 ─── */
.l4-details-tip {
  margin-top: 12px;
  padding: 12px 16px;
  background: #fafafa;
  border: 1px solid #ebeef5;
  border-radius: 6px;
  font-size: 13px;
  color: #606266;
}

.l4-details-tip summary {
  cursor: pointer;
  font-weight: 500;
  color: #303133;
  margin-bottom: 8px;
}

.l4-details-tip ul {
  padding-left: 20px;
  margin: 8px 0 0;
  line-height: 1.8;
}
</style>
