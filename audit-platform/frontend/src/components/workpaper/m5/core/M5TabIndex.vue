<template>
  <div class="m5-tab-index">
    <!-- ═══ 项目信息区 ═══ -->
    <el-card shadow="never" class="m5-project-info">
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
    <div class="m5-equity-badge">
      <el-icon><WarningFilled /></el-icon>
      <span>盈余公积为权益类贷方科目（期末 = 期初 + 贷方 − 借方），含法定盈余公积 + 任意盈余公积双区块</span>
    </div>

    <!-- ═══ 蓝色渐变操作引导区 ═══ -->
    <div class="m5-guide">
      <div class="m5-guide-header">
        <el-icon><InfoFilled /></el-icon>
        <span>操作步骤引导</span>
      </div>
      <div class="m5-guide-steps">
        <div class="step-item">
          <span class="step-num">①</span>
          <span class="step-text">填写审定表（M5-1）确认盈余公积余额（双区块：法定 + 任意）</span>
        </div>
        <div class="step-item">
          <span class="step-num">②</span>
          <span class="step-text">录入明细（M5-2）按法定/任意分类列示增减变动</span>
        </div>
        <div class="step-item">
          <span class="step-num">③</span>
          <span class="step-text">完成计提检查（M5-4）验证法定10%计提 + 注册资本50%上限</span>
        </div>
        <div class="step-item">
          <span class="step-num">④</span>
          <span class="step-text">完成检查表（M5-5）+ 调整分录（M5-3）+ 附注披露</span>
        </div>
      </div>
    </div>

    <!-- ═══ 总体进度 ═══ -->
    <div class="m5-progress-section">
      <div class="progress-info">
        <span>编制进度</span>
        <span class="progress-text">{{ completedCount }} / {{ totalCount }} ({{ progressPercent }}%)</span>
      </div>
      <el-progress :percentage="progressPercent" :stroke-width="8" :show-text="false" />
    </div>

    <!-- ═══ 底稿目录表格 ═══ -->
    <el-card shadow="never" class="m5-index-card">
      <template #header>
        <span class="card-title">致同会计师事务所 / 盈余公积底稿</span>
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
    <details class="m5-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li>盈余公积（4101）为<strong>权益类贷方科目</strong>：期末 = 期初 + 贷方（计提增加）− 借方（转增/弥补减少）</li>
        <li>盈余公积分<strong>法定盈余公积</strong>与<strong>任意盈余公积</strong>两大类，审定表与明细表均分双区块</li>
        <li>法定盈余公积按净利润（弥补以前年度亏损后）的<strong>10%</strong>计提，累计达注册资本<strong>50%</strong>时可不再计提</li>
        <li>计提基数来源于M6未分配利润底稿（净利润/弥补亏损后余额），需确保M6先行完成</li>
        <li>任意盈余公积由股东大会决议确定计提比例，无法定上限</li>
        <li>M5-4计提检查表核对：应计提=计提基数×10%，与账面计提对比出差异</li>
        <li>明细表合计需与审定表交叉验证</li>
        <li>调整分录需保持借贷平衡，通过 EventBus 同步更新审定表</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * M5TabIndex — M5 盈余公积底稿目录
 *
 * 8 行 sheet 目录列表（序号 | 内容 | 索引号 | 备注）。
 * 点击行 emit navigate 事件（由 GtM5SurplusReserve 监听切换 sheetName）。
 * 引导区 4 步：审定表(双区块) → 明细(法定+任意) → 计提检查(10%+50%) → 检查表+调整+附注。
 * 醒目标注"盈余公积为权益类贷方科目"。
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
  remark: string
  progress: number
}

/**
 * 8 行 sheet 目录（对应源模板 M5 底稿目录）。
 * 进度条默认 0%，后续集成时根据 checklist_responses 数据填充。
 */
const sheetRows = computed<SheetRow[]>(() => [
  {
    seq: 1,
    name: '盈余公积实质性程序表',
    indexCode: 'M5A',
    sheetKey: '盈余公积实质性程序表 M5A',
    remark: '',
    progress: 0,
  },
  {
    seq: 2,
    name: '审定表',
    indexCode: 'M5-1',
    sheetKey: '审定表M5-1',
    remark: '',
    progress: 0,
  },
  {
    seq: 3,
    name: '附注披露信息（上市公司）',
    indexCode: '',
    sheetKey: '附注披露信息（上市公司）',
    remark: '',
    progress: 0,
  },
  {
    seq: 4,
    name: '附注披露信息（国有企业）',
    indexCode: '',
    sheetKey: '附注披露信息（国有企业）',
    remark: '',
    progress: 0,
  },
  {
    seq: 5,
    name: '明细表',
    indexCode: 'M5-2',
    sheetKey: '明细表M5-2',
    remark: '',
    progress: 0,
  },
  {
    seq: 6,
    name: '调整分录汇总',
    indexCode: 'M5-3',
    sheetKey: '调整分录汇总M5-3',
    remark: '',
    progress: 0,
  },
  {
    seq: 7,
    name: '盈余公积计提检查表',
    indexCode: 'M5-4',
    sheetKey: '盈余公积计提检查表M5-4',
    remark: '',
    progress: 0,
  },
  {
    seq: 8,
    name: '盈余公积检查表',
    indexCode: 'M5-5',
    sheetKey: '盈余公积检查表M5-5',
    remark: '',
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
.m5-tab-index {
  padding: 12px;
  font-size: var(--wp-font-size, 13px);
}

/* ─── 项目信息区 ─── */
.m5-project-info {
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
.m5-equity-badge {
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

.m5-equity-badge .el-icon {
  font-size: 16px;
  color: #43a047;
  flex-shrink: 0;
}

/* ─── 蓝色渐变引导区 ─── */
.m5-guide {
  background: linear-gradient(135deg, #e8f4fd 0%, #d6eaf8 100%);
  border: 1px solid #b3d9f2;
  border-radius: 8px;
  padding: 14px 20px;
  margin-bottom: 16px;
}

.m5-guide-header {
  display: flex;
  align-items: center;
  gap: 6px;
  font-weight: 500;
  color: #1a73e8;
  margin-bottom: 10px;
  font-size: var(--wp-font-size, 13px);
}

.m5-guide-steps {
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
.m5-progress-section {
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
.m5-index-card {
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
.m5-details-tip {
  margin-top: 12px;
  padding: 12px 16px;
  background: #fafafa;
  border: 1px solid #ebeef5;
  border-radius: 6px;
  font-size: var(--wp-font-size, 13px);
  color: #606266;
}

.m5-details-tip summary {
  cursor: pointer;
  font-weight: 500;
  color: #303133;
  margin-bottom: 8px;
}

.m5-details-tip ul {
  padding-left: 20px;
  margin: 8px 0 0;
  line-height: 1.8;
}
</style>
