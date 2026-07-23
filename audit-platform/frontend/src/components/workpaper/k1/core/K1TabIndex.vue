<template>
  <div class="k1-tab-index">
    <!-- ═══ 总体进度 ═══ -->
    <div class="k1-progress-section">
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
    <div class="k1-guide">
      <div class="k1-guide-header">
        <el-icon><InfoFilled /></el-icon>
        <span>操作步骤引导</span>
      </div>
      <div class="k1-guide-steps">
        <div class="step-item">
          <span class="step-num">①</span>
          <span class="step-text">填写审定表（K1-1）确认其他应收款及坏账余额</span>
        </div>
        <div class="step-item">
          <span class="step-num">②</span>
          <span class="step-text">录入明细表（K1-2）按对象+账龄列示</span>
        </div>
        <div class="step-item">
          <span class="step-num">③</span>
          <span class="step-text">ECL三阶段划分（K1-7）+ 坏账测算（K1-8）</span>
        </div>
        <div class="step-item">
          <span class="step-num">④</span>
          <span class="step-text">完成检查表（K1-5/K1-9~K1-12）及附注披露</span>
        </div>
      </div>
    </div>

    <!-- ═══ 跨表勾稽仪表盘 ═══ -->
    <el-card v-if="crossAlerts.length" shadow="never" class="k1-cross-dashboard">
      <template #header>
        <div class="cross-dash-header">
          <span class="group-title">跨表勾稽</span>
          <el-tag :type="crossOpenCount ? 'warning' : 'success'" size="small">
            {{ crossOpenCount ? `${crossOpenCount} 项待处理` : '全部平衡' }}
          </el-tag>
        </div>
      </template>
      <div class="cross-alert-list">
        <el-alert
          v-for="a in crossAlerts"
          :key="a.id"
          :type="a.severity === 'error' ? 'error' : a.severity === 'warning' ? 'warning' : 'info'"
          :closable="false"
          class="cross-item"
        >
          <template #title>{{ a.title }}</template>
          <div class="cross-item-body">
            <span>{{ a.detail }}</span>
            <el-button size="small" link type="primary" @click="emit('navigate-sheet', a.targetSheet)">前往 →</el-button>
          </div>
        </el-alert>
      </div>
    </el-card>

    <!-- ═══ 底稿目录表格（分组） ═══ -->
    <!-- 核心组 core: K1A ~ K1-4 -->
    <el-card shadow="never" class="k1-group-card group-core">
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

    <!-- 减值组 impairment: K1-6 ~ K1-8 -->
    <el-card shadow="never" class="k1-group-card group-impairment">
      <template #header>
        <span class="group-title">减值与ECL</span>
        <el-tag size="small" type="warning" effect="light">{{ groupProgress('impairment') }}</el-tag>
      </template>
      <el-table
        :data="impairmentSheets"
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

    <!-- 检查组 inspection: K1-5, K1-9 ~ K1-12 -->
    <el-card shadow="never" class="k1-group-card group-inspection">
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
    <el-card shadow="never" class="k1-group-card group-disclosure">
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
    <details class="k1-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li>其他应收款为<strong>资产类借方科目</strong>（1221）：期末 = 期初 + 借方 − 贷方</li>
        <li>坏账准备为<strong>资产备抵类贷方科目</strong>：期末 = 期初 + 贷方 − 借方</li>
        <li>账面净值 = 其他应收款 − 坏账准备</li>
        <li>ECL 三阶段：Stage1（12个月ECL）/ Stage2（整个存续期）/ Stage3（已减值）</li>
        <li>坏账测算公式：ECL = EAD × PD × LGD；账龄损失 = 余额 × 预期损失率</li>
        <li>K1-8 测算结果应与 K1-3 企业计提交叉验证</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * K1TabIndex.vue — K1 其他应收款底稿目录（16行进度条）
 *
 * 16 个 sheet 分 4 组（核心/减值/检查/附注）展示进度条。
 * 点击行 emit navigate-sheet 事件（由 GtK1OtherReceivables 监听切换 sheetName）。
 * 从 allResponses 计算各 sheet 完成度。
 *
 * Requirements: 1.2
 */
import { computed, toRef } from 'vue'
import { InfoFilled } from '@element-plus/icons-vue'
import { calcK1SheetProgress } from '../../composables/k1SheetProgress'
import { useK1IndexCrossCheck } from '../../composables/k1IndexCrossCheck'

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

const allResponsesRef = toRef(props, 'allResponses')
const { alerts: crossAlerts, openCount: crossOpenCount } = useK1IndexCrossCheck(allResponsesRef)

// ─── Sheet 行定义 ─────────────────────────────────────────────────────────────

interface SheetRow {
  seq: number
  name: string
  code: string
  sheetKey: string
  description: string
  group: 'core' | 'impairment' | 'inspection' | 'disclosure'
  progress: number
}

/**
 * 根据实际 storage key 前缀计算各 sheet 完成度。
 */
function sheetProgress(code: string): number {
  return calcK1SheetProgress(props.allResponses, code)
}

/** 16 个 sheet 的完整列表 */
const allSheets = computed<SheetRow[]>(() => [
  // ─── 核心 core ───
  {
    seq: 1,
    name: '其他应收款实质性程序表',
    code: 'K1A',
    sheetKey: '其他应收款实质性程序表K1A',
    description: '实质性程序清单与执行情况',
    group: 'core',
    progress: sheetProgress('K1A'),
  },
  {
    seq: 2,
    name: '审定表',
    code: 'K1-1',
    sheetKey: '审定表K1-1',
    description: '双区块审定（其他应收款+坏账准备），47公式',
    group: 'core',
    progress: sheetProgress('K1-1'),
  },
  {
    seq: 3,
    name: '明细表',
    code: 'K1-2',
    sheetKey: '明细表K1-2',
    description: '按对象+账龄列示（36列3区段Tab）',
    group: 'core',
    progress: sheetProgress('K1-2'),
  },
  {
    seq: 4,
    name: '坏账准备明细表',
    code: 'K1-3',
    sheetKey: '坏账准备明细表K1-3',
    description: '计提/转回/核销管理，21公式',
    group: 'core',
    progress: sheetProgress('K1-3'),
  },
  {
    seq: 5,
    name: '调整分录汇总',
    code: 'K1-4',
    sheetKey: '调整分录汇总K1-4',
    description: 'AJE/RJE管理（借贷平衡校验）',
    group: 'core',
    progress: sheetProgress('K1-4'),
  },
  // ─── 减值 impairment ───
  {
    seq: 6,
    name: '信用减值损失会计政策检查',
    code: 'K1-6',
    sheetKey: '信用减值损失会计政策检查K1-6',
    description: 'ECL模型选择/账龄组合/预期损失率依据',
    group: 'impairment',
    progress: sheetProgress('K1-6'),
  },
  {
    seq: 7,
    name: '三阶段划分检查表',
    code: 'K1-7',
    sheetKey: '三阶段划分检查表K1-7',
    description: 'ECL Stage1/2/3 划分（63行）',
    group: 'impairment',
    progress: sheetProgress('K1-7'),
  },
  {
    seq: 8,
    name: '坏账准备测算',
    code: 'K1-8',
    sheetKey: '坏账准备测算K1-8',
    description: '账龄+迁徙率+ECL测算（62行，11公式）',
    group: 'impairment',
    progress: sheetProgress('K1-8'),
  },
  // ─── 检查 inspection ───
  {
    seq: 9,
    name: '大额其他应收款情况分析表',
    code: 'K1-5',
    sheetKey: '大额其他应收款情况分析表K1-5',
    description: '重点款项分析（9公式），金额降序',
    group: 'inspection',
    progress: sheetProgress('K1-5'),
  },
  {
    seq: 10,
    name: '坏账准备转回(收回)核销检查表',
    code: 'K1-9',
    sheetKey: '坏账准备转回(收回)核销检查表K1-9',
    description: '审批依据+凭证+合规判断',
    group: 'inspection',
    progress: sheetProgress('K1-9'),
  },
  {
    seq: 11,
    name: '长期未收回款项检查表',
    code: 'K1-10',
    sheetKey: '长期未收回款项检查表K1-10',
    description: '账龄+收回措施+可回收性评估',
    group: 'inspection',
    progress: sheetProgress('K1-10'),
  },
  {
    seq: 12,
    name: '关联方及交易检查表',
    code: 'K1-11',
    sheetKey: '关联方及交易检查表K1-11',
    description: '关联交易公允性+披露充分性',
    group: 'inspection',
    progress: sheetProgress('K1-11'),
  },
  {
    seq: 13,
    name: '其他应收款检查表',
    code: 'K1-12',
    sheetKey: '其他应收款检查表K1-12',
    description: '综合检查（合规/不合规/不适用）',
    group: 'inspection',
    progress: sheetProgress('K1-12'),
  },
  // ─── 附注 disclosure ───
  {
    seq: 14,
    name: '附注披露信息（上市公司）',
    code: '附注上市',
    sheetKey: '附注披露信息（上市公司）',
    description: '上市公司其他应收款附注（166行12列）',
    group: 'disclosure',
    progress: sheetProgress('附注上市'),
  },
  {
    seq: 15,
    name: '附注披露信息（国企）',
    code: '附注国企',
    sheetKey: '附注披露信息（国企）',
    description: '国有企业其他应收款附注（130行10列）',
    group: 'disclosure',
    progress: sheetProgress('附注国企'),
  },
  {
    seq: 16,
    name: '底稿目录',
    code: 'K1',
    sheetKey: '底稿目录',
    description: '当前页面（底稿目录+进度统计）',
    group: 'disclosure',
    progress: 100,
  },
])

// ─── 分组 ─────────────────────────────────────────────────────────────────────

const coreSheets = computed(() => allSheets.value.filter(s => s.group === 'core'))
const impairmentSheets = computed(() => allSheets.value.filter(s => s.group === 'impairment'))
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
  // 底稿目录自身不需要跳转
  if (row.code === 'K1') return
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
.k1-tab-index {
  padding: 12px;
  font-size: var(--wp-font-size, 13px);
}

.k1-cross-dashboard { margin-bottom: 14px; }
.cross-dash-header { display: flex; align-items: center; justify-content: space-between; width: 100%; }
.cross-alert-list { display: flex; flex-direction: column; gap: 8px; }
.cross-item-body { display: flex; align-items: center; justify-content: space-between; gap: 12px; font-size: 12px; }
.cross-item { margin: 0; }

/* ─── 进度统计区 ─── */
.k1-progress-section {
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
.k1-guide {
  background: linear-gradient(135deg, #e8f4fd 0%, #d6eaf8 100%);
  border: 1px solid #b3d9f2;
  border-radius: 8px;
  padding: 14px 20px;
  margin-bottom: 16px;
}

.k1-guide-header {
  display: flex;
  align-items: center;
  gap: 6px;
  font-weight: 500;
  color: #1a73e8;
  margin-bottom: 10px;
  font-size: var(--wp-font-size, 13px);
}

.k1-guide-steps {
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
.k1-group-card {
  margin-bottom: 14px;
}

.k1-group-card :deep(.el-card__header) {
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

.group-impairment :deep(.el-card__header) {
  background: linear-gradient(90deg, #eff6ff 0%, #f8fbff 100%);
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
.k1-details-tip {
  margin-top: 12px;
  padding: 12px 16px;
  background: #fafafa;
  border: 1px solid #ebeef5;
  border-radius: 6px;
  font-size: var(--wp-font-size, 13px);
  color: #606266;
}

.k1-details-tip summary {
  cursor: pointer;
  font-weight: 500;
  color: #303133;
  margin-bottom: 8px;
}

.k1-details-tip ul {
  padding-left: 20px;
  margin: 8px 0 0;
  line-height: 1.8;
}
</style>
