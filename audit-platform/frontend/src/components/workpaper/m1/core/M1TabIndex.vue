<template>
  <div class="m1-tab-index">
    <!-- ═══ 项目信息区 ═══ -->
    <el-card shadow="never" class="m1-project-info">
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
    <div class="m1-guide">
      <div class="m1-guide-header">
        <el-icon><InfoFilled /></el-icon>
        <span>操作步骤引导</span>
      </div>
      <div class="m1-guide-steps">
        <div class="step-item">
          <span class="step-num">①</span>
          <span class="step-text">填写审定表（M1-1）确认应付股利科目余额（贷方/负债类）</span>
        </div>
        <div class="step-item">
          <span class="step-num">②</span>
          <span class="step-text">录入明细（M1-2）按股东列示各项应付股利</span>
        </div>
        <div class="step-item">
          <span class="step-num">③</span>
          <span class="step-text">外币汇率测算（M1-4）+ 股利测算核对（M1-5，接收M6）</span>
        </div>
        <div class="step-item">
          <span class="step-num">④</span>
          <span class="step-text">完成检查表（M1-6）+ 调整分录（M1-3）+ 附注披露</span>
        </div>
      </div>
    </div>

    <!-- ═══ 总体进度 ═══ -->
    <div class="m1-progress-section">
      <div class="progress-info">
        <span>编制进度</span>
        <span class="progress-text">{{ completedCount }} / {{ totalCount }} ({{ progressPercent }}%)</span>
      </div>
      <el-progress :percentage="progressPercent" :stroke-width="8" :show-text="false" />
    </div>

    <!-- ═══ 底稿目录表格 ═══ -->
    <el-card shadow="never" class="m1-index-card">
      <template #header>
        <span class="card-title">致同会计师事务所 / 应付股利（利润）底稿</span>
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
        <el-table-column prop="code" label="编码" width="80" align="center" />
        <el-table-column prop="name" label="名称" min-width="240">
          <template #default="{ row }">
            <span class="sheet-name-link">{{ row.name }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="type" label="类型" width="80" align="center">
          <template #default="{ row }">
            <el-tag :type="getTypeTagType(row.type)" size="small" effect="plain">
              {{ row.type }}
            </el-tag>
          </template>
        </el-table-column>
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
    <details class="m1-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li>应付股利为<strong>负债类贷方科目</strong>：期末 = 期初 + 贷方（宣告分配）− 借方（实际支付）</li>
        <li>科目编码：2232 应付股利</li>
        <li>M1-4外币汇率测算：对境外股东的应付股利按期末汇率折算本位币</li>
        <li>M1-5股利测算：接收M6利润分配的分配股利，验证宣告准确性</li>
        <li>明细表按股东列示，需与审定表合计交叉核对</li>
        <li>附注披露根据企业类型（上市公司/国有企业）自动切换模板</li>
        <li>调整分录需保持借贷平衡，通过EventBus同步更新审定表</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * M1TabIndex — M1 应付股利（利润）底稿目录
 *
 * 10 行 sheet 目录列表 + 进度条。
 * 点击行 emit navigate 事件（由 GtM1DividendsPayable 监听切换 sheetName）。
 * 引导区 4 步：审定表 → 明细 → 外币/股利测算 → 检查表+调整+附注。
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
  code: string
  name: string
  type: string
  /** sheetName（传给父组件用于 v-if 分发） */
  sheetKey: string
  progress: number
}

/**
 * 10 行 sheet 目录（底稿目录自身作为第1行展示）。
 * 进度条默认 0%，后续集成时根据 checklist_responses 数据填充。
 */
const sheetRows = computed<SheetRow[]>(() => [
  {
    seq: 1,
    code: 'M1',
    name: '底稿目录',
    type: '目录',
    sheetKey: '底稿目录',
    progress: 100,
  },
  {
    seq: 2,
    code: 'M1A',
    name: '应付股利实质性程序表',
    type: '程序表',
    sheetKey: '应付股利实质性程序表M1A',
    progress: 0,
  },
  {
    seq: 3,
    code: 'M1-1',
    name: '审定表',
    type: '核心',
    sheetKey: '审定表M1-1',
    progress: 0,
  },
  {
    seq: 4,
    code: 'M1-2',
    name: '明细表',
    type: '核心',
    sheetKey: '明细表M1-2',
    progress: 0,
  },
  {
    seq: 5,
    code: 'M1-3',
    name: '调整分录汇总',
    type: '核心',
    sheetKey: '调整分录汇总M1-3',
    progress: 0,
  },
  {
    seq: 6,
    code: 'M1-4',
    name: '外币汇率测算表',
    type: '计算',
    sheetKey: '外币汇率测算表M1-4',
    progress: 0,
  },
  {
    seq: 7,
    code: 'M1-5',
    name: '应付股利测算表',
    type: '计算',
    sheetKey: '应付股利测算表M1-5',
    progress: 0,
  },
  {
    seq: 8,
    code: 'M1-6',
    name: '应付股利检查表',
    type: '检查',
    sheetKey: '应付股利检查表M1-6',
    progress: 0,
  },
  {
    seq: 9,
    code: '-',
    name: '附注披露信息（上市公司）',
    type: '附注',
    sheetKey: '附注披露信息（上市公司）',
    progress: 0,
  },
  {
    seq: 10,
    code: '-',
    name: '附注披露信息（国有企业）',
    type: '附注',
    sheetKey: '附注披露信息（国有企业）',
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

function getTypeTagType(type: string): '' | 'success' | 'warning' | 'info' | 'danger' {
  switch (type) {
    case '目录': return 'info'
    case '程序表': return ''
    case '核心': return 'success'
    case '计算': return 'warning'
    case '检查': return 'danger'
    case '附注': return 'info'
    default: return 'info'
  }
}
</script>

<style scoped>
.m1-tab-index {
  padding: 12px;
  font-size: var(--wp-font-size, 13px);
}

/* ─── 项目信息区 ─── */
.m1-project-info {
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
.m1-guide {
  background: linear-gradient(135deg, #e8f4fd 0%, #d6eaf8 100%);
  border: 1px solid #b3d9f2;
  border-radius: 8px;
  padding: 14px 20px;
  margin-bottom: 16px;
}

.m1-guide-header {
  display: flex;
  align-items: center;
  gap: 6px;
  font-weight: 500;
  color: #1a73e8;
  margin-bottom: 10px;
  font-size: var(--wp-font-size, 13px);
}

.m1-guide-steps {
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
.m1-progress-section {
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
.m1-index-card {
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
.m1-details-tip {
  margin-top: 12px;
  padding: 12px 16px;
  background: #fafafa;
  border: 1px solid #ebeef5;
  border-radius: 6px;
  font-size: var(--wp-font-size, 13px);
  color: #606266;
}

.m1-details-tip summary {
  cursor: pointer;
  font-weight: 500;
  color: #303133;
  margin-bottom: 8px;
}

.m1-details-tip ul {
  padding-left: 20px;
  margin: 8px 0 0;
  line-height: 1.8;
}
</style>
