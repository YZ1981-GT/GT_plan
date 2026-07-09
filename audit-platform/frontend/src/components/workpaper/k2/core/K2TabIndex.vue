<template>
  <div class="k2-tab-index">
    <!-- ═══ 总体进度 ═══ -->
    <div class="k2-progress-section">
      <div class="progress-info">
        <span>编制进度</span>
        <span class="progress-text">{{ completedCount }} / {{ totalCount }} 已完成 ({{ progressPercent }}%)</span>
      </div>
      <el-progress :percentage="progressPercent" :stroke-width="8" :show-text="false" />
      <div class="progress-stats">
        <el-tag size="small" type="success">已完成 {{ completedCount }}</el-tag>
        <el-tag size="small" type="primary">进行中 {{ inProgressCount }}</el-tag>
        <el-tag size="small" type="info">未开始 {{ notStartedCount }}</el-tag>
      </div>
    </div>

    <!-- ═══ 蓝色渐变操作引导区 ═══ -->
    <div class="k2-guide">
      <div class="k2-guide-header">
        <el-icon><InfoFilled /></el-icon>
        <span>操作步骤引导</span>
      </div>
      <div class="k2-guide-steps">
        <div class="step-item">
          <span class="step-num">①</span>
          <span class="step-text">填写审定表（K2-1）确认其他流动资产各项余额</span>
        </div>
        <div class="step-item">
          <span class="step-num">②</span>
          <span class="step-text">录入明细表（K2-2）按项目逐项追踪增减变动</span>
        </div>
        <div class="step-item">
          <span class="step-num">③</span>
          <span class="step-text">管理合同取得成本（K2-4）+ 摊销测算（K2-5）</span>
        </div>
        <div class="step-item">
          <span class="step-num">④</span>
          <span class="step-text">完成检查表（K2-6）及附注披露信息</span>
        </div>
      </div>
    </div>

    <!-- ═══ 底稿目录表格（分组） ═══ -->
    <!-- 核心组 core: K2A ~ K2-3 -->
    <el-card shadow="never" class="k2-group-card group-core">
      <template #header>
        <span class="group-title">核心底稿</span>
        <el-tag size="small" type="success" effect="light">{{ groupProgress('core') }}</el-tag>
      </template>
      <el-table
        :data="coreSheets"
        border
        size="small"
        highlight-current-row
        style="width: 100%"
        :row-class-name="getRowClassName"
        @row-click="handleRowClick"
      >
        <el-table-column prop="seq" label="序号" width="56" align="center" />
        <el-table-column prop="code" label="底稿编号" width="90" align="center" />
        <el-table-column prop="name" label="底稿名称" min-width="200">
          <template #default="{ row }">
            <span class="sheet-name-link">{{ row.name }}</span>
          </template>
        </el-table-column>
        <el-table-column label="完成状态" width="150" align="center">
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

    <!-- 摊销组 amortization: K2-4, K2-5 -->
    <el-card shadow="never" class="k2-group-card group-amortization">
      <template #header>
        <span class="group-title">合同成本与摊销</span>
        <el-tag size="small" type="warning" effect="light">{{ groupProgress('amortization') }}</el-tag>
      </template>
      <el-table
        :data="amortizationSheets"
        border
        size="small"
        highlight-current-row
        style="width: 100%"
        :row-class-name="getRowClassName"
        @row-click="handleRowClick"
      >
        <el-table-column prop="seq" label="序号" width="56" align="center" />
        <el-table-column prop="code" label="底稿编号" width="90" align="center" />
        <el-table-column prop="name" label="底稿名称" min-width="200">
          <template #default="{ row }">
            <span class="sheet-name-link">{{ row.name }}</span>
          </template>
        </el-table-column>
        <el-table-column label="完成状态" width="150" align="center">
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

    <!-- 检查组 inspection: K2-6 -->
    <el-card shadow="never" class="k2-group-card group-inspection">
      <template #header>
        <span class="group-title">专项检查</span>
        <el-tag size="small" type="danger" effect="light">{{ groupProgress('inspection') }}</el-tag>
      </template>
      <el-table
        :data="inspectionSheets"
        border
        size="small"
        highlight-current-row
        style="width: 100%"
        :row-class-name="getRowClassName"
        @row-click="handleRowClick"
      >
        <el-table-column prop="seq" label="序号" width="56" align="center" />
        <el-table-column prop="code" label="底稿编号" width="90" align="center" />
        <el-table-column prop="name" label="底稿名称" min-width="200">
          <template #default="{ row }">
            <span class="sheet-name-link">{{ row.name }}</span>
          </template>
        </el-table-column>
        <el-table-column label="完成状态" width="150" align="center">
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

    <!-- 附注组 disclosure -->
    <el-card shadow="never" class="k2-group-card group-disclosure">
      <template #header>
        <span class="group-title">附注披露</span>
        <el-tag size="small" type="" effect="light">{{ groupProgress('disclosure') }}</el-tag>
      </template>
      <el-table
        :data="disclosureSheets"
        border
        size="small"
        highlight-current-row
        style="width: 100%"
        :row-class-name="getRowClassName"
        @row-click="handleRowClick"
      >
        <el-table-column prop="seq" label="序号" width="56" align="center" />
        <el-table-column prop="code" label="底稿编号" width="90" align="center" />
        <el-table-column prop="name" label="底稿名称" min-width="200">
          <template #default="{ row }">
            <span class="sheet-name-link">{{ row.name }}</span>
          </template>
        </el-table-column>
        <el-table-column label="完成状态" width="150" align="center">
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

    <!-- ═══ 跨底稿索引（GtIndexChip） ═══ -->
    <el-card shadow="never" class="k2-group-card group-cross-ref">
      <template #header>
        <span class="group-title">跨底稿索引</span>
      </template>
      <div class="cross-ref-chips">
        <div class="chip-row">
          <span class="chip-label">关联底稿：</span>
          <GtIndexChip value="K1" :context-project-id="props.projectId" context="K1其他应收款（关联科目）" />
          <GtIndexChip value="A13" :context-project-id="props.projectId" context="错报汇总（调整联动）" />
          <GtIndexChip value="B50" :context-project-id="props.projectId" context="风险评估（B50→K2程序）" />
        </div>
        <div class="chip-row">
          <span class="chip-label">附注联动：</span>
          <GtIndexChip value="K2-1" :prevent-navigate="true" :context-project-id="props.projectId" context="审定表→TB回写(1231)" @click="emit('navigate-sheet', '审定表K2-1')" />
          <GtIndexChip value="K2-4" :prevent-navigate="true" :context-project-id="props.projectId" context="合同取得成本→K2-5摊销测算" @click="emit('navigate-sheet', '合同取得成本明细表K2-4')" />
          <GtIndexChip value="K2-5" :prevent-navigate="true" :context-project-id="props.projectId" context="摊销测算←K2-4合同成本" @click="emit('navigate-sheet', '摊销测算表K2-5')" />
        </div>
      </div>
    </el-card>

    <!-- ═══ 编制提示（折叠） ═══ -->
    <details class="k2-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li>其他流动资产为<strong>资产类借方科目</strong>（1231）：期末 = 期初 + 借方 − 贷方</li>
        <li>合同取得成本摊销按 CAS14 判断资本化条件：增量成本 + 预期可收回 + 与合同直接相关</li>
        <li>直线法摊销 = 取得成本 / 摊销期总期数 × 本期期数</li>
        <li>进度法摊销 = 取得成本 × (本期履约进度 − 上期履约进度)</li>
        <li>摊余成本 = 取得成本 − 累计摊销</li>
        <li>K2-4 合同成本合计应与 K2-1 审定表合同取得成本一致</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * K2TabIndex.vue — K2 其他流动资产底稿目录
 *
 * 9 个 sheet 分 4 组（核心/摊销/检查/附注）展示进度条。
 * 点击行 emit navigate-sheet 事件（由 GtK2OtherCurrentAssets 监听切换 sheetName）。
 * 从 allResponses 计算各 sheet 完成度。
 *
 * Validates: Requirements 1.2
 */
import { computed } from 'vue'
import { InfoFilled } from '@element-plus/icons-vue'
import GtIndexChip from '../../GtIndexChip.vue'

// ─── Props / Emits ───────────────────────────────────────────────────────────

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const emit = defineEmits<{
  (e: 'navigate-sheet', sheetName: string): void
}>()

// ─── Sheet 行定义 ─────────────────────────────────────────────────────────────

interface SheetRow {
  seq: number
  name: string
  code: string
  sheetKey: string
  group: 'core' | 'amortization' | 'inspection' | 'disclosure'
  progress: number
}

/**
 * 根据 allResponses 中以指定前缀存储的字段数计算完成度。
 * 简单策略：有任何以前缀的响应即视为进行中(50%)，
 * 字段数 >= expectedFields 即完成(100%)。
 */
function calcSheetProgress(prefix: string, expectedFields: number): number {
  if (!props.allResponses || props.allResponses.size === 0) return 0
  let count = 0
  for (const key of props.allResponses.keys()) {
    if (key.startsWith(prefix)) count++
  }
  if (count === 0) return 0
  if (count >= expectedFields) return 100
  return Math.min(Math.round((count / expectedFields) * 100), 99)
}

/** 9 个 sheet 的完整列表（K2A + K2-1~K2-6 + 附注上市/国企） */
const allSheets = computed<SheetRow[]>(() => [
  // ─── 核心 core ───
  {
    seq: 1,
    name: '其他流动资产实质性程序表',
    code: 'K2A',
    sheetKey: '其他流动资产实质性程序表K2A',
    group: 'core',
    progress: calcSheetProgress('K2-K2A-', 5),
  },
  {
    seq: 2,
    name: '审定表',
    code: 'K2-1',
    sheetKey: '审定表K2-1',
    group: 'core',
    progress: calcSheetProgress('K2-K2-1-', 10),
  },
  {
    seq: 3,
    name: '明细表',
    code: 'K2-2',
    sheetKey: '明细表K2-2',
    group: 'core',
    progress: calcSheetProgress('K2-K2-2-', 8),
  },
  {
    seq: 4,
    name: '调整分录汇总',
    code: 'K2-3',
    sheetKey: '调整分录汇总K2-3',
    group: 'core',
    progress: calcSheetProgress('K2-K2-3-', 4),
  },
  // ─── 摊销 amortization ───
  {
    seq: 5,
    name: '合同取得成本明细表',
    code: 'K2-4',
    sheetKey: '合同取得成本明细表K2-4',
    group: 'amortization',
    progress: calcSheetProgress('K2-K2-4-', 8),
  },
  {
    seq: 6,
    name: '摊销测算表',
    code: 'K2-5',
    sheetKey: '摊销测算表K2-5',
    group: 'amortization',
    progress: calcSheetProgress('K2-K2-5-', 8),
  },
  // ─── 检查 inspection ───
  {
    seq: 7,
    name: '其他流动资产检查表',
    code: 'K2-6',
    sheetKey: '其他流动资产检查表K2-6',
    group: 'inspection',
    progress: calcSheetProgress('K2-K2-6-', 6),
  },
  // ─── 附注 disclosure ───
  {
    seq: 8,
    name: '附注披露信息（上市公司）',
    code: '附注上市',
    sheetKey: '附注披露信息（上市公司）',
    group: 'disclosure',
    progress: calcSheetProgress('K2-disclosure-listed-', 5),
  },
  {
    seq: 9,
    name: '附注披露信息（国企）',
    code: '附注国企',
    sheetKey: '附注披露信息（国企）',
    group: 'disclosure',
    progress: calcSheetProgress('K2-disclosure-soe-', 5),
  },
])

// ─── 分组 ─────────────────────────────────────────────────────────────────────

const coreSheets = computed(() => allSheets.value.filter(s => s.group === 'core'))
const amortizationSheets = computed(() => allSheets.value.filter(s => s.group === 'amortization'))
const inspectionSheets = computed(() => allSheets.value.filter(s => s.group === 'inspection'))
const disclosureSheets = computed(() => allSheets.value.filter(s => s.group === 'disclosure'))

// ─── 进度计算 ─────────────────────────────────────────────────────────────────

const totalCount = computed(() => allSheets.value.length)

const completedCount = computed(() =>
  allSheets.value.filter(r => r.progress >= 100).length,
)

const inProgressCount = computed(() =>
  allSheets.value.filter(r => r.progress > 0 && r.progress < 100).length,
)

const notStartedCount = computed(() =>
  allSheets.value.filter(r => r.progress === 0).length,
)

const progressPercent = computed(() => {
  if (totalCount.value === 0) return 0
  const avg = allSheets.value.reduce((sum, r) => sum + r.progress, 0) / totalCount.value
  return Math.round(avg)
})

function groupProgress(group: string): string {
  const sheets = allSheets.value.filter(s => s.group === group)
  const done = sheets.filter(s => s.progress >= 100).length
  return `${done}/${sheets.length}`
}

// ─── 交互 ────────────────────────────────────────────────────────────────────

function handleRowClick(row: SheetRow) {
  emit('navigate-sheet', row.sheetKey)
}

function getRowClassName({ row }: { row: SheetRow }): string {
  if (row.progress >= 100) return 'completed-row'
  if (row.progress > 0) return 'in-progress-row'
  return ''
}

function getProgressColor(percent: number): string {
  if (percent >= 100) return '#67c23a'
  if (percent >= 50) return '#409eff'
  if (percent > 0) return '#e6a23c'
  return '#e6e8eb'
}
</script>

<style scoped>
.k2-tab-index {
  padding: 12px;
  font-size: 13px;
}

/* ─── 进度统计区 ─── */
.k2-progress-section {
  margin-bottom: 16px;
  padding: 14px 16px;
  background: #f5f7fa;
  border-radius: 8px;
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

.progress-stats {
  display: flex;
  gap: 8px;
  margin-top: 10px;
}

/* ─── 蓝色渐变引导区 ─── */
.k2-guide {
  background: linear-gradient(135deg, #e8f4fd 0%, #d6eaf8 100%);
  border: 1px solid #b3d9f2;
  border-radius: 8px;
  padding: 14px 20px;
  margin-bottom: 16px;
}

.k2-guide-header {
  display: flex;
  align-items: center;
  gap: 6px;
  font-weight: 500;
  color: #1a73e8;
  margin-bottom: 10px;
  font-size: 13px;
}

.k2-guide-steps {
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

/* ─── 分组卡片 ─── */
.k2-group-card {
  margin-bottom: 14px;
}

.k2-group-card :deep(.el-card__header) {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 16px;
}

.group-title {
  font-size: 14px;
  font-weight: 600;
  color: #303133;
}

/* 分组配色 */
.group-core :deep(.el-card__header) {
  background: linear-gradient(90deg, #f0faf0 0%, #f8fdf8 100%);
}

.group-amortization :deep(.el-card__header) {
  background: linear-gradient(90deg, #eff6ff 0%, #f8fbff 100%);
}

.group-inspection :deep(.el-card__header) {
  background: linear-gradient(90deg, #faf5ff 0%, #fdf9ff 100%);
}

.group-disclosure :deep(.el-card__header) {
  background: linear-gradient(90deg, #fefce8 0%, #fefdf5 100%);
}

/* ─── 跨底稿索引 ─── */
.group-cross-ref :deep(.el-card__header) {
  background: linear-gradient(90deg, #f5f3ff 0%, #faf8ff 100%);
}

.cross-ref-chips {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 4px 0;
}

.chip-row {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.chip-label {
  font-size: 12px;
  color: #606266;
  min-width: 80px;
}

/* ─── 表格样式 ─── */
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
  width: 36px;
}

:deep(.completed-row) {
  background-color: #f0f9eb !important;
}

:deep(.in-progress-row) {
  background-color: #fdf6ec !important;
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
.k2-details-tip {
  margin-top: 12px;
  padding: 12px 16px;
  background: #fafafa;
  border: 1px solid #ebeef5;
  border-radius: 6px;
  font-size: 13px;
  color: #606266;
}

.k2-details-tip summary {
  cursor: pointer;
  font-weight: 500;
  color: #303133;
  margin-bottom: 8px;
}

.k2-details-tip ul {
  padding-left: 20px;
  margin: 8px 0 0;
  line-height: 1.8;
}
</style>
