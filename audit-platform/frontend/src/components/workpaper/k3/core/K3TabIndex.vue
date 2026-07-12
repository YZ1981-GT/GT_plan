<template>
  <div class="k3-tab-index">
    <!-- ═══ 总体进度 ═══ -->
    <div class="k3-progress-section">
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
    <div class="k3-guide">
      <div class="k3-guide-header">
        <el-icon><InfoFilled /></el-icon>
        <span>操作步骤引导</span>
      </div>
      <div class="k3-guide-steps">
        <div class="step-item">
          <span class="step-num">①</span>
          <span class="step-text">填写审定表（K3-1）确认其他应付款余额（负债类，期末=期初+贷-借）</span>
        </div>
        <div class="step-item">
          <span class="step-num">②</span>
          <span class="step-text">录入明细表（K3-2）按对象+账龄列示</span>
        </div>
        <div class="step-item">
          <span class="step-num">③</span>
          <span class="step-text">大额分析（K3-4）+ 长期挂账检查（K3-5）</span>
        </div>
        <div class="step-item">
          <span class="step-num">④</span>
          <span class="step-text">完成关联方（K3-6）、综合检查（K3-7含反向截止）及附注披露</span>
        </div>
      </div>
    </div>

    <!-- ═══ 底稿目录表格（分组） ═══ -->
    <!-- 核心组 core: K3A ~ K3-3 -->
    <el-card shadow="never" class="k3-group-card group-core">
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

    <!-- 检查组 inspection: K3-4 ~ K3-7 -->
    <el-card shadow="never" class="k3-group-card group-inspection">
      <template #header>
        <span class="group-title">专项检查</span>
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
    <el-card shadow="never" class="k3-group-card group-disclosure">
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
    <details class="k3-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li>其他应付款为<strong>负债类贷方科目</strong>（2241）：期末 = 期初 + 贷方 − 借方</li>
        <li>审定数 = 未审数 + AJE + RJE</li>
        <li>审计重点为<strong>完整性认定</strong>（负债易少计）→ 反向截止测试（期后偿付倒查未入账负债）</li>
        <li>长期挂账（3年以上）需评估是否转营业外收入</li>
        <li>关联方往来需关注公允性与充分披露</li>
        <li>三角勾稽：期末 = 期初 + 增加（贷方） − 减少（借方），差额须为0</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * K3TabIndex.vue — K3 其他应付款底稿目录（11行进度条）
 *
 * 11 个 sheet 分 3 组（核心/检查/附注）展示进度条。
 * 点击行 emit navigate-sheet 事件（由 GtK3OtherPayables 监听切换 sheetName）。
 * 从 allResponses 计算各 sheet 完成度。
 *
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

/** 11 个 sheet 的完整列表 */
const allSheets = computed<SheetRow[]>(() => [
  // ─── 核心 core ───
  {
    seq: 1,
    name: '其他应付款实质性程序表',
    code: 'K3A',
    sheetKey: '其他应付款实质性程序表K3A',
    description: '实质性程序清单与执行情况',
    group: 'core',
    progress: calcSheetProgress('K3-K3A-', 5),
  },
  {
    seq: 2,
    name: '审定表',
    code: 'K3-1',
    sheetKey: '审定表K3-1',
    description: '负债类双区块审定（按性质+按账龄），50公式',
    group: 'core',
    progress: calcSheetProgress('K3-1-', 10),
  },
  {
    seq: 3,
    name: '明细表',
    code: 'K3-2',
    sheetKey: '明细表K3-2',
    description: '按对象+账龄列示（27列3区段Tab）',
    group: 'core',
    progress: calcSheetProgress('K3-2-', 8),
  },
  {
    seq: 4,
    name: '调整分录汇总',
    code: 'K3-3',
    sheetKey: '调整分录汇总K3-3',
    description: 'AJE/RJE管理（借贷平衡校验）',
    group: 'core',
    progress: calcSheetProgress('K3-3-', 4),
  },
  // ─── 检查 inspection ───
  {
    seq: 5,
    name: '大额其他应付款情况分析表',
    code: 'K3-4',
    sheetKey: '大额其他应付款情况分析表K3-4',
    description: '重点款项分析（8公式），金额降序',
    group: 'inspection',
    progress: calcSheetProgress('K3-4-', 5),
  },
  {
    seq: 6,
    name: '长期挂账检查表',
    code: 'K3-5',
    sheetKey: '长期挂账检查表K3-5',
    description: '3年以上未偿付款项检查，评估转销必要性',
    group: 'inspection',
    progress: calcSheetProgress('K3-5-', 4),
  },
  {
    seq: 7,
    name: '关联方及交易检查表',
    code: 'K3-6',
    sheetKey: '关联方及交易检查表K3-6',
    description: '关联交易公允性+披露充分性+资金占用',
    group: 'inspection',
    progress: calcSheetProgress('K3-6-', 4),
  },
  {
    seq: 8,
    name: '其他应付款检查表',
    code: 'K3-7',
    sheetKey: '其他应付款检查表K3-7',
    description: '综合检查（含反向截止测试/完整性认定）',
    group: 'inspection',
    progress: calcSheetProgress('K3-7-', 6),
  },
  // ─── 附注 disclosure ───
  {
    seq: 9,
    name: '附注披露信息（上市公司）',
    code: '附注上市',
    sheetKey: '附注披露信息（上市公司）',
    description: '上市公司其他应付款附注（按账龄/按性质）',
    group: 'disclosure',
    progress: calcSheetProgress('K3-disclosure-listed-', 5),
  },
  {
    seq: 10,
    name: '附注披露信息（国企）',
    code: '附注国企',
    sheetKey: '附注披露信息（国企）',
    description: '国有企业其他应付款附注（按账龄/按性质）',
    group: 'disclosure',
    progress: calcSheetProgress('K3-disclosure-soe-', 5),
  },
  {
    seq: 11,
    name: '底稿目录',
    code: 'K3',
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
  if (row.code === 'K3') return
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
.k3-tab-index {
  padding: 12px;
  font-size: var(--wp-font-size, 13px);
}

/* ─── 进度统计区 ─── */
.k3-progress-section {
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
  font-size: var(--wp-font-size, 13px);
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
.k3-guide {
  background: linear-gradient(135deg, #e8f4fd 0%, #d6eaf8 100%);
  border: 1px solid #b3d9f2;
  border-radius: 8px;
  padding: 14px 20px;
  margin-bottom: 16px;
}

.k3-guide-header {
  display: flex;
  align-items: center;
  gap: 6px;
  font-weight: 500;
  color: #1a73e8;
  margin-bottom: 10px;
  font-size: var(--wp-font-size, 13px);
}

.k3-guide-steps {
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

/* ─── 分组卡片 ─── */
.k3-group-card {
  margin-bottom: 14px;
}

.k3-group-card :deep(.el-card__header) {
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
  width: 36px;
}

:deep(.completed-row) {
  background-color: #f0f9eb !important;
}

:deep(.in-progress-row) {
  background-color: #fdf6ec !important;
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
.k3-details-tip {
  margin-top: 12px;
  padding: 12px 16px;
  background: #fafafa;
  border: 1px solid #ebeef5;
  border-radius: 6px;
  font-size: var(--wp-font-size, 13px);
  color: #606266;
}

.k3-details-tip summary {
  cursor: pointer;
  font-weight: 500;
  color: #303133;
  margin-bottom: 8px;
}

.k3-details-tip ul {
  padding-left: 20px;
  margin: 8px 0 0;
  line-height: 1.8;
}
</style>
