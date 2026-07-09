<template>
  <div class="m3-tab-index">
    <!-- ═══ 项目信息区 ═══ -->
    <el-card shadow="never" class="m3-project-info">
      <div class="info-grid">
        <div class="info-item">
          <span class="info-label">被审计单位</span>
          <span class="info-value">{{ projectInfo.clientName || '—' }}</span>
        </div>
        <div class="info-item">
          <span class="info-label">截止日</span>
          <span class="info-value">{{ projectInfo.cutoffDate || '—' }}</span>
        </div>
        <div class="info-item">
          <span class="info-label">编制人</span>
          <span class="info-value">{{ projectInfo.preparer || '—' }}</span>
        </div>
        <div class="info-item">
          <span class="info-label">编制日期</span>
          <span class="info-value">{{ projectInfo.prepareDate || '—' }}</span>
        </div>
      </div>
    </el-card>

    <!-- ═══ 权益备抵借方醒目标注 ═══ -->
    <div class="m3-contra-badge">
      <el-icon><WarningFilled /></el-icon>
      <span>库存股为权益备抵，借方余额（期末 = 期初 + 借方 − 贷方，与其他权益类方向相反）</span>
    </div>

    <!-- ═══ 蓝色渐变操作引导区 ═══ -->
    <div class="m3-guide">
      <div class="m3-guide-header">
        <el-icon><InfoFilled /></el-icon>
        <span>操作步骤引导</span>
      </div>
      <div class="m3-guide-steps">
        <div class="step-item">
          <span class="step-num">①</span>
          <span class="step-text">填写审定表（M3-1）确认库存股科目余额（借方/权益备抵类！）</span>
        </div>
        <div class="step-item">
          <span class="step-num">②</span>
          <span class="step-text">录入明细（M3-2）按回购批次列示库存股增减变动</span>
        </div>
        <div class="step-item">
          <span class="step-num">③</span>
          <span class="step-text">外币回购折算（M3-4）+ 回购/注销核对检查表（M3-5）</span>
        </div>
        <div class="step-item">
          <span class="step-num">④</span>
          <span class="step-text">完成调整分录（M3-3）+ 附注披露（上市公司）</span>
        </div>
      </div>
    </div>

    <!-- ═══ 总体进度 ═══ -->
    <div class="m3-progress-section">
      <div class="progress-info">
        <span>编制进度</span>
        <span class="progress-text">{{ completedCount }} / {{ totalCount }} ({{ progressPercent }}%)</span>
      </div>
      <el-progress :percentage="progressPercent" :stroke-width="8" :show-text="false" />
    </div>

    <!-- ═══ 底稿目录表格 ═══ -->
    <el-card shadow="never" class="m3-index-card">
      <template #header>
        <span class="card-title">致同会计师事务所 / 库存股底稿</span>
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
        <el-table-column prop="indexCode" label="索引号" width="80" align="center" />
        <el-table-column prop="remark" label="备注" min-width="120">
          <template #default="{ row }">
            <span class="remark-text">{{ row.remark || '' }}</span>
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
    <details class="m3-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li>库存股（4002）为<strong>权益备抵类借方科目</strong>：期末 = 期初 + 借方（回购）− 贷方（注销/再售）</li>
        <li>与 M2/M4/M5/M6 等权益类方向<strong>完全相反</strong>——回购在借方增加库存股，注销/再售在贷方减少库存股</li>
        <li>M3-2 明细表按回购批次列示，每批次记录：回购日期/股数/单价/金额 + 注销股数/期末余额</li>
        <li>M3-4 外币回购折算：境外回购以外币计价，按回购日汇率折算本位币</li>
        <li>M3-5 回购/注销核对：回购金额 = 股数 × 单价；注销冲减 = 实收资本(M2) + 资本公积(M4)</li>
        <li>注销冲减差额 ≠ 0 时需冲减盈余公积 / 未分配利润</li>
        <li>明细表合计需与审定表交叉验证</li>
        <li>调整分录需保持借贷平衡，通过 EventBus 同步更新审定表</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * M3TabIndex — M3 库存股底稿目录
 *
 * 8 行 sheet 目录列表（序号 | 内容 | 索引号 | 备注）+ 进度条。
 * 点击行 emit navigate 事件（由 GtM3TreasuryStock 监听切换 sheetName）。
 * 引导区 4 步：审定表 → 明细(按回购批次) → 外币回购/检查表 → 调整+附注。
 * 醒目标注"库存股为权益备抵，借方余额"。
 *
 * Requirements: 1.2
 */
import { computed } from 'vue'
import { InfoFilled, WarningFilled } from '@element-plus/icons-vue'

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
  indexCode: string
  remark: string
  /** sheetName（传给父组件用于 v-if 分发） */
  sheetKey: string
  progress: number
}

/**
 * 8 行 sheet 目录（对应源模板 M3 底稿目录）。
 * 进度条默认 0%，后续集成时根据 checklist_responses 数据填充。
 */
const sheetRows = computed<SheetRow[]>(() => [
  {
    seq: 1,
    name: '库存股实质性程序表',
    indexCode: 'M3A',
    remark: '程序表（复用）',
    sheetKey: '库存股实质性程序表 M3A',
    progress: 0,
  },
  {
    seq: 2,
    name: '审定表',
    indexCode: 'M3-1',
    remark: '权益备抵借方',
    sheetKey: '审定表M3-1',
    progress: 0,
  },
  {
    seq: 3,
    name: '附注披露信息（上市公司）',
    indexCode: 'M3-1',
    remark: '',
    sheetKey: '附注披露信息（上市公司）',
    progress: 0,
  },
  {
    seq: 4,
    name: '明细表',
    indexCode: 'M3-2',
    remark: '按回购批次列示',
    sheetKey: '明细表M3-2',
    progress: 0,
  },
  {
    seq: 5,
    name: '调整分录汇总',
    indexCode: 'M3-3',
    remark: '借贷平衡',
    sheetKey: '调整分录汇总M3-3',
    progress: 0,
  },
  {
    seq: 6,
    name: '外币投资汇率测算表',
    indexCode: 'M3-4',
    remark: '外币回购折算',
    sheetKey: '外币投资汇率测算表M3-4',
    progress: 0,
  },
  {
    seq: 7,
    name: '库存股检查表',
    indexCode: 'M3-5',
    remark: '回购/注销核对',
    sheetKey: '库存股检查表M3-5',
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
  cutoffDate: '',
  preparer: '',
  prepareDate: '',
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
.m3-tab-index {
  padding: 12px;
  font-size: 13px;
}

/* ─── 项目信息区 ─── */
.m3-project-info {
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

/* ─── 权益备抵借方醒目标注 ─── */
.m3-contra-badge {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 16px;
  margin-bottom: 16px;
  background: linear-gradient(135deg, #fef3cd 0%, #fdeeba 100%);
  border: 1px solid #f5c542;
  border-left: 4px solid #e6a817;
  border-radius: 6px;
  font-size: 13px;
  font-weight: 500;
  color: #856404;
}

.m3-contra-badge .el-icon {
  font-size: 16px;
  color: #e6a817;
  flex-shrink: 0;
}

/* ─── 蓝色渐变引导区 ─── */
.m3-guide {
  background: linear-gradient(135deg, #e8f4fd 0%, #d6eaf8 100%);
  border: 1px solid #b3d9f2;
  border-radius: 8px;
  padding: 14px 20px;
  margin-bottom: 16px;
}

.m3-guide-header {
  display: flex;
  align-items: center;
  gap: 6px;
  font-weight: 500;
  color: #1a73e8;
  margin-bottom: 10px;
  font-size: 13px;
}

.m3-guide-steps {
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
.m3-progress-section {
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
.m3-index-card {
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

.remark-text {
  font-size: 12px;
  color: #909399;
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
.m3-details-tip {
  margin-top: 12px;
  padding: 12px 16px;
  background: #fafafa;
  border: 1px solid #ebeef5;
  border-radius: 6px;
  font-size: 13px;
  color: #606266;
}

.m3-details-tip summary {
  cursor: pointer;
  font-weight: 500;
  color: #303133;
  margin-bottom: 8px;
}

.m3-details-tip ul {
  padding-left: 20px;
  margin: 8px 0 0;
  line-height: 1.8;
}
</style>
