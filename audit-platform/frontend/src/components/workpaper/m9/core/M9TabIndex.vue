<template>
  <div class="m9-tab-index">
    <!-- ═══ 项目信息区 ═══ -->
    <el-card shadow="never" class="m9-project-info">
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
        <div class="info-item">
          <span class="info-label">复核人</span>
          <span class="info-value">{{ projectInfo.reviewer || '—' }}</span>
        </div>
        <div class="info-item">
          <span class="info-label">复核日期</span>
          <span class="info-value">{{ projectInfo.reviewDate || '—' }}</span>
        </div>
      </div>
    </el-card>

    <!-- ═══ 权益类贷方科目醒目标注 ═══ -->
    <div class="m9-equity-badge">
      <el-icon><WarningFilled /></el-icon>
      <span>其他综合收益为权益类贷方科目（期末 = 期初 + 贷方 − 借方），OCI增加时贷方增加，减少/重分类进损益时借方减少；分"不可重分类"和"可重分类"两大类</span>
    </div>

    <!-- ═══ 蓝色渐变操作引导区 ═══ -->
    <div class="m9-guide">
      <div class="m9-guide-header">
        <el-icon><InfoFilled /></el-icon>
        <span>操作步骤引导</span>
      </div>
      <div class="m9-guide-steps">
        <div class="step-item">
          <span class="step-num">①</span>
          <span class="step-text">填写审定表（M9-1）确认OCI余额（双大类：不可/可重分类进损益）</span>
        </div>
        <div class="step-item">
          <span class="step-num">②</span>
          <span class="step-text">录入明细（M9-2）各OCI项目税前发生−所得税影响＝税后净额</span>
        </div>
        <div class="step-item">
          <span class="step-num">③</span>
          <span class="step-text">完成OCI核对（M9-4）验证G8公允变动/J2重计量/外币折算来源一致</span>
        </div>
        <div class="step-item">
          <span class="step-num">④</span>
          <span class="step-text">编制调整分录（M9-3）+ 完成附注披露</span>
        </div>
      </div>
    </div>

    <!-- ═══ 总体进度 ═══ -->
    <div class="m9-progress-section">
      <div class="progress-info">
        <span>编制进度</span>
        <span class="progress-text">{{ completedCount }} / {{ totalCount }} ({{ progressPercent }}%)</span>
      </div>
      <el-progress :percentage="progressPercent" :stroke-width="8" :show-text="false" />
    </div>

    <!-- ═══ 底稿目录表格 ═══ -->
    <el-card shadow="never" class="m9-index-card">
      <template #header>
        <span class="card-title">致同会计师事务所 / 其他综合收益底稿</span>
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
        <el-table-column prop="name" label="内容" min-width="300">
          <template #default="{ row }">
            <span class="sheet-name-link">{{ row.name }}</span>
          </template>
        </el-table-column>
        <el-table-column label="索引号" width="120" align="center">
          <template #default="{ row }">
            <GtIndexChip v-if="row.indexCode" :value="row.indexCode" />
            <span v-else class="no-index">—</span>
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
    <details class="m9-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li>其他综合收益（4103）为<strong>权益类贷方科目</strong>：期末 = 期初 + 贷方（OCI增加）− 借方（减少/重分类进损益）</li>
        <li>OCI分两大类：<strong>以后不能重分类进损益</strong>（G8其他权益工具投资公允变动、J2设定受益计划重计量）和<strong>以后能重分类进损益</strong>（其他债权投资公允变动、现金流量套期损益、外币财务报表折算差额）</li>
        <li>OCI各项目按<strong>税后净额列示</strong>：本期税前发生 − 所得税影响 = 税后净额</li>
        <li>M9-4核对表是核心：OCI汇聚多来源（G8/J2/外币折算），需验证来源金额与账面OCI增加一致</li>
        <li>审定表双大类合计需与明细表M9-2交叉验证</li>
        <li>调整分录需保持借贷平衡，通过EventBus同步更新审定表</li>
        <li>附注披露根据企业类型（上市/国企）自动切换模板，国企版67×21含20个公式</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * M9TabIndex — M9 其他综合收益底稿目录
 *
 * 9 行 sheet 目录列表（序号 | 内容 | 索引号 | 进度 | 操作）。
 * 点击行 emit navigate 事件（由 GtM9OtherComprehensiveIncome 监听切换 sheetName）。
 * 引导区 4 步：审定表(双大类) → 明细(税后净额) → OCI核对(G8/J2/外币) → 调整+附注。
 * 醒目标注"其他综合收益为权益类贷方科目"。
 *
 * Requirements: 1.2
 */
import { computed } from 'vue'
import { InfoFilled, WarningFilled } from '@element-plus/icons-vue'
import GtIndexChip from '@/components/workpaper/GtIndexChip.vue'

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
  /** sheetName（传给父组件用于 v-if 分发） */
  sheetKey: string
  progress: number
}

/**
 * 9 行 sheet 目录（对应源模板 M9 其他综合收益底稿目录）。
 * 进度条默认 0%，后续集成时根据 checklist_responses 数据填充。
 */
const sheetRows = computed<SheetRow[]>(() => [
  {
    seq: 1,
    name: '其他综合收益实质性程序表',
    indexCode: 'M9A',
    sheetKey: '其他综合收益实质性程序表M9A',
    progress: 0,
  },
  {
    seq: 2,
    name: '审定表（双大类：不可/可重分类进损益）',
    indexCode: 'M9-1',
    sheetKey: '审定表M9-1',
    progress: 0,
  },
  {
    seq: 3,
    name: '明细表（OCI分项 + 税后净额）',
    indexCode: 'M9-2',
    sheetKey: '明细表M9-2',
    progress: 0,
  },
  {
    seq: 4,
    name: '调整分录汇总',
    indexCode: 'M9-3',
    sheetKey: '调整分录汇总M9-3',
    progress: 0,
  },
  {
    seq: 5,
    name: 'OCI核对表（多来源核对：G8/J2/外币折算）',
    indexCode: 'M9-4',
    sheetKey: 'OCI核对表M9-4',
    progress: 0,
  },
  {
    seq: 6,
    name: '附注披露信息（上市公司）',
    indexCode: '',
    sheetKey: '附注披露信息（上市公司）',
    progress: 0,
  },
  {
    seq: 7,
    name: '附注披露信息（国有企业）',
    indexCode: '',
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
  cutoffDate: '',
  preparer: '',
  prepareDate: '',
  reviewer: '',
  reviewDate: '',
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
.m9-tab-index {
  padding: 12px;
  font-size: var(--wp-font-size, 13px);
}

/* ─── 项目信息区 ─── */
.m9-project-info {
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

/* ─── 权益类贷方科目醒目标注 ─── */
.m9-equity-badge {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 16px;
  margin-bottom: 16px;
  background: linear-gradient(135deg, #e8f5e9 0%, #c8e6c9 100%);
  border: 1px solid #81c784;
  border-left: 4px solid #43a047;
  border-radius: 6px;
  font-size: var(--wp-font-size, 13px);
  font-weight: 500;
  color: #2e7d32;
}

.m9-equity-badge .el-icon {
  font-size: 16px;
  color: #43a047;
  flex-shrink: 0;
}

/* ─── 蓝色渐变引导区 ─── */
.m9-guide {
  background: linear-gradient(135deg, #e8f4fd 0%, #d6eaf8 100%);
  border: 1px solid #b3d9f2;
  border-radius: 8px;
  padding: 14px 20px;
  margin-bottom: 16px;
}

.m9-guide-header {
  display: flex;
  align-items: center;
  gap: 6px;
  font-weight: 500;
  color: #1a73e8;
  margin-bottom: 10px;
  font-size: var(--wp-font-size, 13px);
}

.m9-guide-steps {
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
.m9-progress-section {
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
.m9-index-card {
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

.no-index {
  color: #c0c4cc;
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
.m9-details-tip {
  margin-top: 12px;
  padding: 12px 16px;
  background: #fafafa;
  border: 1px solid #ebeef5;
  border-radius: 6px;
  font-size: var(--wp-font-size, 13px);
  color: #606266;
}

.m9-details-tip summary {
  cursor: pointer;
  font-weight: 500;
  color: #303133;
  margin-bottom: 8px;
}

.m9-details-tip ul {
  padding-left: 20px;
  margin: 8px 0 0;
  line-height: 1.8;
}
</style>
