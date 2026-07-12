<template>
  <div class="n1-tab-index">
    <!-- ═══ 顶部标识头 ═══ -->
    <div class="n1-header-bar">
      <span class="header-code">底稿编码 N1</span>
      <span class="header-sep">|</span>
      <span class="header-subject">科目 1811 递延所得税资产</span>
      <span class="header-sep">|</span>
      <span class="header-direction">资产类 / 借方</span>
    </div>

    <!-- ═══ 资产类借方科目醒目标注 ═══ -->
    <div class="n1-asset-badge">
      <el-icon><WarningFilled /></el-icon>
      <span>递延所得税资产为资产类借方科目（期末 = 期初 + 借方 − 贷方），核心引擎：可抵扣暂时性差异 × 适用税率</span>
    </div>

    <!-- ═══ 蓝色渐变操作引导区 ═══ -->
    <div class="n1-guide">
      <div class="n1-guide-header">
        <el-icon><InfoFilled /></el-icon>
        <span>操作步骤引导</span>
      </div>
      <div class="n1-guide-steps">
        <div class="step-item">
          <span class="step-num">①</span>
          <span class="step-text">填写审定表（N1-1）确认递延所得税资产期末余额（资产类：期初+借方−贷方）</span>
        </div>
        <div class="step-item">
          <span class="step-num">②</span>
          <span class="step-text">录入明细（N1-2）按暂时性差异项目逐项列示确认额</span>
        </div>
        <div class="step-item">
          <span class="step-num">③</span>
          <span class="step-text">完成测算表（N1-4）暂时性差异×税率 + 亏损检查（N1-5）充足性判断</span>
        </div>
        <div class="step-item">
          <span class="step-num">④</span>
          <span class="step-text">调整分录（N1-3）+ 附注披露 + 核对N3递延税负债/N5递延税费用</span>
        </div>
      </div>
    </div>

    <!-- ═══ 总体进度 ═══ -->
    <div class="n1-progress-section">
      <div class="progress-info">
        <span>编制进度</span>
        <span class="progress-text">{{ completedCount }} / {{ totalCount }} ({{ progressPercent }}%)</span>
      </div>
      <el-progress :percentage="progressPercent" :stroke-width="8" :show-text="false" />
    </div>

    <!-- ═══ 底稿目录表格 ═══ -->
    <el-card shadow="never" class="n1-index-card">
      <template #header>
        <span class="card-title">致同会计师事务所 / 递延所得税资产底稿</span>
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
            <span class="sheet-name-link">{{ row.name }}</span>
            <el-tag v-if="row.isCore" size="small" type="danger" class="core-tag">核心</el-tag>
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
        <el-table-column label="联动状态" width="100" align="center">
          <template #default="{ row }">
            <span v-if="row.linkageStatus === 'matched'" class="linkage-badge linkage-ok">✓</span>
            <span v-else-if="row.linkageStatus === 'diff'" class="linkage-badge linkage-warn">⚠</span>
            <span v-else class="linkage-badge linkage-na">—</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- ═══ 编制提示（折叠） ═══ -->
    <details class="n1-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li>递延所得税资产（1811）为<strong>资产类借方科目</strong>：期末 = 期初 + 本期借方 − 本期贷方</li>
        <li>核心公式：递延所得税资产 = 可抵扣暂时性差异 × 适用税率</li>
        <li>可弥补亏损确认：可确认额 = min(未弥补亏损, 预计未来应纳税所得额) × 税率</li>
        <li>N1-4测算表同源产出递延税资产（归N1）和递延税负债（归N3），不能抵销的分列</li>
        <li>递延税资产本期变动额（期末−期初）供N5-8递延所得税费用核对</li>
        <li>弥补期限：一般企业5年，高新/科技型中小企业10年</li>
        <li>审定数变化后回写 trial_balance 科目1811期末余额</li>
        <li>调整分录需保持借贷平衡，通过 EventBus 同步更新审定表</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * N1TabIndex — N1 递延所得税资产底稿目录
 *
 * 8 行 sheet 目录（序号 | 内容 | 索引号 | 进度 | 联动状态）。
 * 点击行 emit navigate 事件（由 GtN1DeferredTaxAssets 监听切换 sheetName）。
 * 引导区 4 步：审定表(资产类期末) → 明细(暂时性差异) → 测算+亏损 → 调整+附注+联动N3/N5。
 * 醒目标注"递延所得税资产为资产类借方科目"。
 * 联动状态列：从 useN1CrossSheet 获取各sheet勾稽状态。
 *
 * Requirements: 1.2
 */
import { computed, ref } from 'vue'
import { InfoFilled, WarningFilled } from '@element-plus/icons-vue'
import { useN1CrossSheet } from '../../composables/useN1CrossSheet'
import type { ChecklistResponse } from '../../composables/useN1FormData'

// ─── Props / Emits ───────────────────────────────────────────────────────────

const props = defineProps<{
  wpId: string
  projectId: string
  isReadonly: boolean
}>()

const emit = defineEmits<{
  (e: 'navigate', sheetName: string): void
}>()

// ─── CrossSheet 联动（占位 Map，后续集成时注入真实 allResponses） ──────────

const allResponses = ref<Map<string, ChecklistResponse>>(new Map())
const { adjudicationVsDetail, adjudicationVsCalcTable } = useN1CrossSheet(allResponses)

// ─── Sheet 目录行定义 ────────────────────────────────────────────────────────

type LinkageStatus = 'matched' | 'diff' | 'none'

interface SheetRow {
  seq: number
  name: string
  code: string
  /** sheetName（传给父组件用于 v-if 分发） */
  sheetKey: string
  progress: number
  /** 是否核心sheet */
  isCore: boolean
  /** 联动状态 */
  linkageStatus: LinkageStatus
}

/**
 * 8 行 sheet 目录（对应源模板 N1 递延所得税资产底稿）。
 * 进度条默认 0%，后续集成时根据 checklist_responses 数据填充。
 * 联动状态从 useN1CrossSheet 获取（审定↔明细、审定↔测算勾稽）。
 */
const sheetRows = computed<SheetRow[]>(() => {
  // 联动状态：N1-1需要同时与N1-2和N1-4勾稽
  const n1_1Linkage: LinkageStatus =
    adjudicationVsDetail.value.isMatch && adjudicationVsCalcTable.value.isMatch
      ? 'matched'
      : (allResponses.value.size > 0 ? 'diff' : 'none')

  const n1_2Linkage: LinkageStatus =
    adjudicationVsDetail.value.isMatch
      ? 'matched'
      : (allResponses.value.size > 0 ? 'diff' : 'none')

  const n1_4Linkage: LinkageStatus =
    adjudicationVsCalcTable.value.isMatch
      ? 'matched'
      : (allResponses.value.size > 0 ? 'diff' : 'none')

  return [
    {
      seq: 1,
      name: '递延所得税资产审计程序表',
      code: 'N1A',
      sheetKey: '递延所得税资产审计程序表N1A',
      progress: 0,
      isCore: false,
      linkageStatus: 'none',
    },
    {
      seq: 2,
      name: '递延所得税资产审定表',
      code: 'N1-1',
      sheetKey: '审定表N1-1',
      progress: 0,
      isCore: true,
      linkageStatus: n1_1Linkage,
    },
    {
      seq: 3,
      name: '附注披露信息（上市公司）',
      code: '',
      sheetKey: '附注披露信息（上市公司）',
      progress: 0,
      isCore: false,
      linkageStatus: 'none',
    },
    {
      seq: 4,
      name: '附注披露信息（国企）',
      code: '',
      sheetKey: '附注披露信息（国企）',
      progress: 0,
      isCore: false,
      linkageStatus: 'none',
    },
    {
      seq: 5,
      name: '递延所得税资产明细表',
      code: 'N1-2',
      sheetKey: '明细表N1-2',
      progress: 0,
      isCore: true,
      linkageStatus: n1_2Linkage,
    },
    {
      seq: 6,
      name: '调整分录汇总',
      code: 'N1-3',
      sheetKey: '调整分录汇总N1-3',
      progress: 0,
      isCore: false,
      linkageStatus: 'none',
    },
    {
      seq: 7,
      name: '递延所得税资产（负债）测算表',
      code: 'N1-4',
      sheetKey: '测算表N1-4',
      progress: 0,
      isCore: true,
      linkageStatus: n1_4Linkage,
    },
    {
      seq: 8,
      name: '可用以后年度税前利润弥补的亏损检查表',
      code: 'N1-5',
      sheetKey: '亏损检查表N1-5',
      progress: 0,
      isCore: false,
      linkageStatus: 'none',
    },
  ]
})

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
.n1-tab-index {
  padding: 12px;
  font-size: var(--wp-font-size, 13px);
}

/* ─── 顶部标识头 ─── */
.n1-header-bar {
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

/* ─── 资产类借方科目醒目标注 ─── */
.n1-asset-badge {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 16px;
  margin-bottom: 16px;
  background: linear-gradient(135deg, #fff3e0 0%, #ffe0b2 100%);
  border: 1px solid #ffb74d;
  border-left: 4px solid #f57c00;
  border-radius: 6px;
  font-size: var(--wp-font-size, 13px);
  font-weight: 500;
  color: #e65100;
}

.n1-asset-badge .el-icon {
  font-size: 16px;
  color: #f57c00;
  flex-shrink: 0;
}

/* ─── 蓝色渐变引导区 ─── */
.n1-guide {
  background: linear-gradient(135deg, #e8f4fd 0%, #d6eaf8 100%);
  border: 1px solid #b3d9f2;
  border-radius: 8px;
  padding: 14px 20px;
  margin-bottom: 16px;
}

.n1-guide-header {
  display: flex;
  align-items: center;
  gap: 6px;
  font-weight: 500;
  color: #1a73e8;
  margin-bottom: 10px;
  font-size: var(--wp-font-size, 13px);
}

.n1-guide-steps {
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
.n1-progress-section {
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
.n1-index-card {
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

.core-tag {
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
.n1-details-tip {
  margin-top: 12px;
  padding: 12px 16px;
  background: #fafafa;
  border: 1px solid #ebeef5;
  border-radius: 6px;
  font-size: var(--wp-font-size, 13px);
  color: #606266;
}

.n1-details-tip summary {
  cursor: pointer;
  font-weight: 500;
  color: #303133;
  margin-bottom: 8px;
}

.n1-details-tip ul {
  padding-left: 20px;
  margin: 8px 0 0;
  line-height: 1.8;
}
</style>
