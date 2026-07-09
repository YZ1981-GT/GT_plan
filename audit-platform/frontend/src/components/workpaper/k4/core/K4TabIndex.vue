<template>
  <div class="k4-tab-index">
    <!-- ═══ 总体进度 ═══ -->
    <div class="k4-progress-section">
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
    <div class="k4-guide">
      <div class="k4-guide-header">
        <el-icon><InfoFilled /></el-icon>
        <span>操作步骤引导</span>
      </div>
      <div class="k4-guide-steps">
        <div class="step-item">
          <span class="step-num">①</span>
          <span class="step-text">填写审定表（K4-1）确认其他流动负债余额（负债类，期末=期初+贷-借）</span>
        </div>
        <div class="step-item">
          <span class="step-num">②</span>
          <span class="step-text">录入明细表（K4-2）按项目逐笔列示</span>
        </div>
        <div class="step-item">
          <span class="step-num">③</span>
          <span class="step-text">管理调整分录（K4-3）+ 完成检查表（K4-4）</span>
        </div>
        <div class="step-item">
          <span class="step-num">④</span>
          <span class="step-text">完善附注披露（上市/国企版本）并确认审定回写TB</span>
        </div>
      </div>
    </div>

    <!-- ═══ 底稿目录表格（分组） ═══ -->
    <!-- 核心组 core -->
    <el-card shadow="never" class="k4-group-card group-core">
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
        <el-table-column prop="name" label="底稿名称" min-width="200">
          <template #default="{ row }">
            <span class="sheet-name-link">{{ row.name }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="code" label="索引号" width="80" align="center" />
        <el-table-column prop="description" label="简要说明" min-width="240" />
        <el-table-column label="完成进度" width="150" align="center">
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

    <!-- 检查组 inspection -->
    <el-card shadow="never" class="k4-group-card group-inspection">
      <template #header>
        <span class="group-title">检查与调整</span>
        <el-tag size="small" type="warning" effect="light">{{ groupProgress('inspection') }}</el-tag>
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
        <el-table-column prop="name" label="底稿名称" min-width="200">
          <template #default="{ row }">
            <span class="sheet-name-link">{{ row.name }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="code" label="索引号" width="80" align="center" />
        <el-table-column prop="description" label="简要说明" min-width="240" />
        <el-table-column label="完成进度" width="150" align="center">
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
    <el-card shadow="never" class="k4-group-card group-disclosure">
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
        <el-table-column prop="name" label="底稿名称" min-width="200">
          <template #default="{ row }">
            <span class="sheet-name-link">{{ row.name }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="code" label="索引号" width="80" align="center" />
        <el-table-column prop="description" label="简要说明" min-width="240" />
        <el-table-column label="完成进度" width="150" align="center">
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
    <details class="k4-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li>其他流动负债为<strong>负债类贷方科目</strong>（2245）：期末 = 期初 + 贷方 − 借方</li>
        <li>审定数 = 未审数 + AJE + RJE</li>
        <li>审计重点为<strong>完整性认定</strong>（负债易少计）→ 反向截止测试（期后偿付倒查未入账负债）</li>
        <li>三角勾稽：期末 = 期初 + 增加（贷方） − 减少（借方），差额须为0</li>
        <li>明细表合计应与审定表审定数一致（交叉验证）</li>
        <li>科目包含：预提费用、待转销项税额、代扣代缴、短期融资等</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * K4TabIndex.vue — K4 其他流动负债底稿目录（8 sheet进度表）
 *
 * 8 个有效 sheet 分 3 组（核心/检查调整/附注）展示进度条。
 * 点击行 emit navigate-sheet 事件（由 GtK4OtherCurrentLiabilities 监听切换 sheetName）。
 * 从 allResponses 计算各 sheet 完成度。
 *
 * Spec: .kiro/specs/k4-other-current-liabilities/ | Task: 4.1
 * Requirements: 1.2
 */
import { computed } from 'vue'
import { InfoFilled } from '@element-plus/icons-vue'

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
  description: string
  group: 'core' | 'inspection' | 'disclosure'
  progress: number
}

/**
 * 根据 allResponses 中以指定前缀存储的字段数计算完成度。
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

/** 8 个有效 sheet 的完整列表 */
const allSheets = computed<SheetRow[]>(() => [
  // ─── 核心 core ───
  {
    seq: 1,
    name: '其他流动负债实质性程序表',
    code: 'K4A',
    sheetKey: '其他流动负债实质性程序表K4A',
    description: '实质性程序清单与执行情况',
    group: 'core',
    progress: calcSheetProgress('K4-K4A-', 5),
  },
  {
    seq: 2,
    name: '审定表',
    code: 'K4-1',
    sheetKey: '审定表K4-1',
    description: '负债类审定（21行14列72公式），TB回写2245',
    group: 'core',
    progress: calcSheetProgress('K4-1-', 10),
  },
  {
    seq: 3,
    name: '明细表',
    code: 'K4-2',
    sheetKey: '明细表K4-2',
    description: '按项目列示（18列2区段Tab）',
    group: 'core',
    progress: calcSheetProgress('K4-2-', 6),
  },
  // ─── 检查调整 inspection ───
  {
    seq: 4,
    name: '调整分录汇总',
    code: 'K4-3',
    sheetKey: '调整分录汇总K4-3',
    description: 'AJE/RJE管理（借贷平衡校验）',
    group: 'inspection',
    progress: calcSheetProgress('K4-3-', 4),
  },
  {
    seq: 5,
    name: '其他流动负债检查表',
    code: 'K4-4',
    sheetKey: '其他流动负债检查表K4-4',
    description: '分类正确性/流动性/完整性/合规性逐项检查',
    group: 'inspection',
    progress: calcSheetProgress('K4-4-', 4),
  },
  // ─── 附注 disclosure ───
  {
    seq: 6,
    name: '附注披露信息（上市公司）',
    code: '附注上市',
    sheetKey: '附注披露信息（上市公司）',
    description: '上市公司其他流动负债附注（41行12列）',
    group: 'disclosure',
    progress: calcSheetProgress('K4-disclosure-listed-', 5),
  },
  {
    seq: 7,
    name: '附注披露信息（国企）',
    code: '附注国企',
    sheetKey: '附注披露信息（国企）',
    description: '国企其他流动负债附注（14行12列）',
    group: 'disclosure',
    progress: calcSheetProgress('K4-disclosure-soe-', 5),
  },
  {
    seq: 8,
    name: '底稿目录',
    code: 'K4',
    sheetKey: '底稿目录',
    description: '当前页面（底稿目录+进度统计）',
    group: 'disclosure',
    progress: 100,
  },
])

// ─── 分组 ─────────────────────────────────────────────────────────────────────

const coreSheets = computed(() => allSheets.value.filter(s => s.group === 'core'))
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
  if (row.code === 'K4') return // 当前页面不跳转
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
.k4-tab-index {
  padding: 12px;
  font-size: 13px;
}

/* ─── 进度统计区 ─── */
.k4-progress-section {
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
.k4-guide {
  background: linear-gradient(135deg, #e8f4fd 0%, #d6eaf8 100%);
  border: 1px solid #b3d9f2;
  border-radius: 8px;
  padding: 14px 20px;
  margin-bottom: 16px;
}

.k4-guide-header {
  display: flex;
  align-items: center;
  gap: 6px;
  font-weight: 500;
  color: #1a73e8;
  margin-bottom: 10px;
  font-size: 13px;
}

.k4-guide-steps {
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
.k4-group-card {
  margin-bottom: 14px;
}

.k4-group-card :deep(.el-card__header) {
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

.group-inspection :deep(.el-card__header) {
  background: linear-gradient(90deg, #faf5ff 0%, #fdf9ff 100%);
}

.group-disclosure :deep(.el-card__header) {
  background: linear-gradient(90deg, #fefce8 0%, #fefdf5 100%);
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
.k4-details-tip {
  margin-top: 12px;
  padding: 12px 16px;
  background: #fafafa;
  border: 1px solid #ebeef5;
  border-radius: 6px;
  font-size: 13px;
  color: #606266;
}

.k4-details-tip summary {
  cursor: pointer;
  font-weight: 500;
  color: #303133;
  margin-bottom: 8px;
}

.k4-details-tip ul {
  padding-left: 20px;
  margin: 8px 0 0;
  line-height: 1.8;
}
</style>
