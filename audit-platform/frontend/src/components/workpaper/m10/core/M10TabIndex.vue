<template>
  <div class="m10-tab-index">
    <!-- ═══ 项目信息区 ═══ -->
    <el-card shadow="never" class="m10-project-info">
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

    <!-- ═══ 权益类贷方科目醒目标注 ═══ -->
    <div class="m10-equity-badge">
      <el-icon><WarningFilled /></el-icon>
      <span>其他权益工具为权益类贷方科目（期末 = 期初 + 贷方 − 借方），含永续债/优先股等金融工具（CAS37负债权益区分判定）</span>
    </div>

    <!-- ═══ 蓝色渐变操作引导区 ═══ -->
    <div class="m10-guide">
      <div class="m10-guide-header">
        <el-icon><InfoFilled /></el-icon>
        <span>操作步骤引导</span>
      </div>
      <div class="m10-guide-steps">
        <div class="step-item">
          <span class="step-num">①</span>
          <span class="step-text">填写审定表（M10-1）确认其他权益工具余额（按工具类型：永续债/优先股分类）</span>
        </div>
        <div class="step-item">
          <span class="step-num">②</span>
          <span class="step-text">录入明细（M10-2）按工具逐项列示发行/赎回/利息变动</span>
        </div>
        <div class="step-item">
          <span class="step-num">③</span>
          <span class="step-text">完成CAS37负债与权益区分（M10-4）逐条判定分类准确性</span>
        </div>
        <div class="step-item">
          <span class="step-num">④</span>
          <span class="step-text">完成检查表（M10-5）+ 调整分录（M10-3）+ 附注披露</span>
        </div>
      </div>
    </div>

    <!-- ═══ 总体进度 ═══ -->
    <div class="m10-progress-section">
      <div class="progress-info">
        <span>编制进度</span>
        <span class="progress-text">{{ completedCount }} / {{ totalCount }} ({{ progressPercent }}%)</span>
      </div>
      <el-progress :percentage="progressPercent" :stroke-width="8" :show-text="false" />
    </div>

    <!-- ═══ 底稿目录表格 ═══ -->
    <el-card shadow="never" class="m10-index-card">
      <template #header>
        <span class="card-title">致同会计师事务所 / 其他权益工具底稿</span>
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
        <el-table-column label="索引号" width="120" align="center">
          <template #default="{ row }">
            <GtIndexChip v-if="row.indexCode" :value="row.indexCode" />
            <span v-else class="no-index">—</span>
          </template>
        </el-table-column>
        <el-table-column prop="remark" label="备注" min-width="120" />
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
    <details class="m10-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li>其他权益工具（4003）为<strong>权益类贷方科目</strong>：期末 = 期初 + 贷方（发行增加）− 借方（赎回/转换减少）</li>
        <li>主要包括<strong>永续债</strong>和<strong>优先股</strong>等混合金融工具</li>
        <li>核心判定：按<strong>CAS37《金融工具列报》</strong>判定是否存在交付现金/金融资产的合同义务</li>
        <li>无合同义务→权益工具（计入M10 4003科目）；有合同义务→金融负债（计入负债科目）</li>
        <li>M10-4负债与权益区分检查表为本底稿最核心程序，逐条判定分类准确性</li>
        <li>明细表合计需与审定表交叉验证，权益+负债金额须等于工具总额</li>
        <li>调整分录需保持借贷平衡，通过 EventBus 同步更新审定表</li>
        <li>附注根据企业类型自动切换（上市公司/国有企业）</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * M10TabIndex — M10 其他权益工具底稿目录
 *
 * 10 行 sheet 目录列表（序号 | 内容 | 索引号 | 备注）。
 * 点击行 emit navigate 事件（由 GtM10OtherEquityInstruments 监听切换 sheetName）。
 * 引导区 4 步：审定表(按工具类型) → 明细(永续债/优先股) → CAS37区分检查 → 检查表+调整+附注。
 * 醒目标注"其他权益工具为权益类贷方科目"。
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
  sheetKey: string
  remark: string
  progress: number
}

/**
 * 10 行 sheet 目录（对应源模板 M10 底稿目录 active_sheets）。
 * 进度条默认 0%，后续集成时根据 checklist_responses 数据填充。
 */
const sheetRows = computed<SheetRow[]>(() => [
  {
    seq: 1,
    name: '其他权益工具实质性程序表',
    indexCode: 'M10A',
    sheetKey: '其他权益工具实质性程序表 M10A',
    remark: '',
    progress: 0,
  },
  {
    seq: 2,
    name: '其他权益工具审定表',
    indexCode: 'M10-1',
    sheetKey: '审定表M10-1',
    remark: '',
    progress: 0,
  },
  {
    seq: 3,
    name: '附注披露信息（上市公司）',
    indexCode: '',
    sheetKey: '附注披露信息核对（上市公司）',
    remark: '无需打印',
    progress: 0,
  },
  {
    seq: 4,
    name: '附注披露信息（国有企业）',
    indexCode: '',
    sheetKey: '附注披露信息核对（国企）',
    remark: '无需打印',
    progress: 0,
  },
  {
    seq: 5,
    name: '其他权益工具明细表',
    indexCode: 'M10-2',
    sheetKey: '明细表M10-2',
    remark: '',
    progress: 0,
  },
  {
    seq: 6,
    name: '调整分录汇总',
    indexCode: 'M10-3',
    sheetKey: '调整分录汇总M10-3',
    remark: '',
    progress: 0,
  },
  {
    seq: 7,
    name: '负债与权益区分检查表',
    indexCode: 'M10-4',
    sheetKey: '负债与权益区分检查表M10-4',
    remark: 'CAS37核心',
    progress: 0,
  },
  {
    seq: 8,
    name: '其他权益工具检查表',
    indexCode: 'M10-5',
    sheetKey: '其他权益工具检查表M10-5',
    remark: '',
    progress: 0,
  },
  {
    seq: 9,
    name: 'GT自定义底稿',
    indexCode: '',
    sheetKey: 'GT_Custom',
    remark: '自定义',
    progress: 0,
  },
  {
    seq: 10,
    name: '其他权益工具实质性程序表（修订前）',
    indexCode: 'Q10A',
    sheetKey: '其他权益工具实质性程序表 Q10A (修订前)',
    remark: '已停用',
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
</script>

<style scoped>
.m10-tab-index {
  padding: 12px;
  font-size: var(--wp-font-size, 13px);
}

/* ─── 项目信息区 ─── */
.m10-project-info {
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
.m10-equity-badge {
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

.m10-equity-badge .el-icon {
  font-size: 16px;
  color: #43a047;
  flex-shrink: 0;
}

/* ─── 蓝色渐变引导区 ─── */
.m10-guide {
  background: linear-gradient(135deg, #e8f4fd 0%, #d6eaf8 100%);
  border: 1px solid #b3d9f2;
  border-radius: 8px;
  padding: 14px 20px;
  margin-bottom: 16px;
}

.m10-guide-header {
  display: flex;
  align-items: center;
  gap: 6px;
  font-weight: 500;
  color: #1a73e8;
  margin-bottom: 10px;
  font-size: var(--wp-font-size, 13px);
}

.m10-guide-steps {
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
.m10-progress-section {
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
.m10-index-card {
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
.m10-details-tip {
  margin-top: 12px;
  padding: 12px 16px;
  background: #fafafa;
  border: 1px solid #ebeef5;
  border-radius: 6px;
  font-size: var(--wp-font-size, 13px);
  color: #606266;
}

.m10-details-tip summary {
  cursor: pointer;
  font-weight: 500;
  color: #303133;
  margin-bottom: 8px;
}

.m10-details-tip ul {
  padding-left: 20px;
  margin: 8px 0 0;
  line-height: 1.8;
}
</style>
