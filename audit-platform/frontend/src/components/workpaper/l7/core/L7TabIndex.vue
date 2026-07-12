<template>
  <div class="l7-tab-index">
    <!-- ═══ 项目信息区 ═══ -->
    <el-card shadow="never" class="l7-project-info">
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
    <div class="l7-guide">
      <div class="l7-guide-header">
        <el-icon><InfoFilled /></el-icon>
        <span>操作步骤引导</span>
      </div>
      <div class="l7-guide-steps">
        <div class="step-item">
          <span class="step-num">①</span>
          <span class="step-text">填写审定表（L7-1）确认其他非流动负债科目余额（贷方/负债类）</span>
        </div>
        <div class="step-item">
          <span class="step-num">②</span>
          <span class="step-text">录入明细（L7-2）按项目列示各项其他非流动负债</span>
        </div>
        <div class="step-item">
          <span class="step-num">③</span>
          <span class="step-text">完成检查表（L7-4）核对清单 + 审计结论</span>
        </div>
        <div class="step-item">
          <span class="step-num">④</span>
          <span class="step-text">录入调整分录（L7-3）+ 核对附注披露信息</span>
        </div>
      </div>
    </div>

    <!-- ═══ 总体进度 ═══ -->
    <div class="l7-progress-section">
      <div class="progress-info">
        <span>编制进度</span>
        <span class="progress-text">{{ completedCount }} / {{ totalCount }} ({{ progressPercent }}%)</span>
      </div>
      <el-progress :percentage="progressPercent" :stroke-width="8" :show-text="false" />
    </div>

    <!-- ═══ 底稿目录表格 ═══ -->
    <el-card shadow="never" class="l7-index-card">
      <template #header>
        <span class="card-title">致同会计师事务所 / 其他非流动负债底稿</span>
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
        <el-table-column label="进度/状态" width="140" align="center">
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
    <details class="l7-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li>其他非流动负债为<strong>负债类贷方科目</strong>：期末 = 期初 + 贷方（增加）− 借方（减少）</li>
        <li>科目编码：2801 其他非流动负债</li>
        <li>L7属于L筹资循环最简标准负债底稿，无复杂计算引擎</li>
        <li>明细表按项目列示，需与审定表合计交叉核对</li>
        <li>附注披露根据企业类型（上市/国企）自动切换模板</li>
        <li>调整分录需保持借贷平衡，通过EventBus同步更新审定表</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * L7TabIndex — L7 其他非流动负债底稿目录
 *
 * 8 行 sheet 目录列表 + 进度条。
 * 点击行 emit navigate 事件（由 GtL7OtherNoncurrentLiabilities 监听切换 sheetName）。
 * 引导区 4 步：审定表 → 明细 → 检查表 → 调整+附注。
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
 * 8 行 sheet 目录（底稿目录自身作为第1行展示）。
 * 进度条默认 0%，后续集成时根据 checklist_responses 数据填充。
 */
const sheetRows = computed<SheetRow[]>(() => [
  {
    seq: 1,
    name: '底稿目录',
    code: '目录',
    sheetKey: '底稿目录',
    progress: 100,
  },
  {
    seq: 2,
    name: '其他非流动负债实质性程序表',
    code: 'L7A',
    sheetKey: '其他非流动负债实质性程序表L7A',
    progress: 0,
  },
  {
    seq: 3,
    name: '审定表',
    code: 'L7-1',
    sheetKey: '审定表L7-1',
    progress: 0,
  },
  {
    seq: 4,
    name: '附注披露信息核对（上市公司）',
    code: '附注上市',
    sheetKey: '附注披露信息（上市公司）',
    progress: 0,
  },
  {
    seq: 5,
    name: '附注披露信息核对（国企）',
    code: '附注国企',
    sheetKey: '附注披露信息（国企）',
    progress: 0,
  },
  {
    seq: 6,
    name: '明细表',
    code: 'L7-2',
    sheetKey: '明细表L7-2',
    progress: 0,
  },
  {
    seq: 7,
    name: '调整分录汇总',
    code: 'L7-3',
    sheetKey: '调整分录汇总L7-3',
    progress: 0,
  },
  {
    seq: 8,
    name: '其他非流动负债检查表',
    code: 'L7-4',
    sheetKey: '其他非流动负债检查表L7-4',
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
.l7-tab-index {
  padding: 12px;
  font-size: var(--wp-font-size, 13px);
}

/* ─── 项目信息区 ─── */
.l7-project-info {
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
.l7-guide {
  background: linear-gradient(135deg, #e8f4fd 0%, #d6eaf8 100%);
  border: 1px solid #b3d9f2;
  border-radius: 8px;
  padding: 14px 20px;
  margin-bottom: 16px;
}

.l7-guide-header {
  display: flex;
  align-items: center;
  gap: 6px;
  font-weight: 500;
  color: #1a73e8;
  margin-bottom: 10px;
  font-size: var(--wp-font-size, 13px);
}

.l7-guide-steps {
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
.l7-progress-section {
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
.l7-index-card {
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
.l7-details-tip {
  margin-top: 12px;
  padding: 12px 16px;
  background: #fafafa;
  border: 1px solid #ebeef5;
  border-radius: 6px;
  font-size: var(--wp-font-size, 13px);
  color: #606266;
}

.l7-details-tip summary {
  cursor: pointer;
  font-weight: 500;
  color: #303133;
  margin-bottom: 8px;
}

.l7-details-tip ul {
  padding-left: 20px;
  margin: 8px 0 0;
  line-height: 1.8;
}
</style>
