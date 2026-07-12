<template>
  <div class="m6-tab-index">
    <!-- ═══ 项目信息区 ═══ -->
    <el-card shadow="never" class="m6-project-info">
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
    <div class="m6-equity-badge">
      <el-icon><WarningFilled /></el-icon>
      <span>未分配利润为权益类贷方科目（期末 = 期初 + 贷方 − 借方），是利润分配结转的枢纽：期末 = 期初 + 本年净利润 − 提取盈余公积 − 分配股利</span>
    </div>

    <!-- ═══ 蓝色渐变操作引导区 ═══ -->
    <div class="m6-guide">
      <div class="m6-guide-header">
        <el-icon><InfoFilled /></el-icon>
        <span>操作步骤引导</span>
      </div>
      <div class="m6-guide-steps">
        <div class="step-item">
          <span class="step-num">①</span>
          <span class="step-text">填写明细表（M6-2）完成利润分配结转公式链逐行勾稽</span>
        </div>
        <div class="step-item">
          <span class="step-num">②</span>
          <span class="step-text">确认审定表（M6-1）验证未分配利润余额（与明细表交叉验证）</span>
        </div>
        <div class="step-item">
          <span class="step-num">③</span>
          <span class="step-text">核对M5盈余公积计提 + M1股利分配联动一致</span>
        </div>
        <div class="step-item">
          <span class="step-num">④</span>
          <span class="step-text">完成检查表（M6-4）+ 调整分录（M6-3）+ 附注披露</span>
        </div>
      </div>
    </div>

    <!-- ═══ 总体进度 ═══ -->
    <div class="m6-progress-section">
      <div class="progress-info">
        <span>编制进度</span>
        <span class="progress-text">{{ completedCount }} / {{ totalCount }} ({{ progressPercent }}%)</span>
      </div>
      <el-progress :percentage="progressPercent" :stroke-width="8" :show-text="false" />
    </div>

    <!-- ═══ 底稿目录表格 ═══ -->
    <el-card shadow="never" class="m6-index-card">
      <template #header>
        <span class="card-title">致同会计师事务所 / 未分配利润底稿</span>
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

    <!-- ═══ 底稿结构说明 ═══ -->
    <div class="m6-structure-note">
      <span class="structure-label">底稿结构：</span>
      <span>共 8 个有效sheet（底稿目录 / M6A实质性程序表 / 审定表M6-1 / 附注(上市/国企) / 明细表M6-2 / 调整M6-3 / 检查表M6-4）</span>
    </div>

    <!-- ═══ 编制提示（折叠） ═══ -->
    <details class="m6-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li>未分配利润（4104）为<strong>权益类贷方科目</strong>：期末 = 期初 + 贷方（净利润转入）− 借方（分配支出）</li>
        <li>核心公式链：<strong>期末未分配利润 = 期初 + 本年净利润 − 提取法定盈余公积 − 提取任意盈余公积 − 应付股利</strong></li>
        <li>M6是M股东权益循环的<strong>利润分配结转枢纽</strong>：上游接收本年利润，下游驱动M5盈余公积计提与M1股利分配</li>
        <li>M6-2明细表逐行列示利润分配过程（含前期差错更正、会计政策变更调整年初）</li>
        <li>联动核对：M6记录的提取盈余公积 = M5实际计提额；M6记录的应付股利 = M1实际宣告额</li>
        <li>明细表合计需与审定表M6-1交叉验证</li>
        <li>调整分录需保持借贷平衡，通过 EventBus 同步更新审定表</li>
        <li>附注披露根据企业类型（上市公司/国有企业）自动切换模板</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * M6TabIndex — M6 未分配利润底稿目录
 *
 * 8 行 sheet 目录列表（序号 | 内容 | 索引号 | 备注）。
 * 点击行 emit navigate 事件（由 GtM6RetainedEarnings 监听切换 sheetName）。
 * 引导区 4 步：明细(分配结转) → 审定表 → M5/M1联动核对 → 检查表+调整+附注。
 * 醒目标注"未分配利润为权益类贷方科目，利润分配结转枢纽"。
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
 * 8 行 sheet 目录（对应源模板 M6 未分配利润底稿目录）。
 * sheetKey 与源xlsx tab名一致。
 * 进度条默认 0%，后续集成时根据 checklist_responses 数据填充。
 */
const sheetRows = computed<SheetRow[]>(() => [
  {
    seq: 1,
    name: '未分配利润实质性程序表',
    indexCode: 'M6A',
    sheetKey: '未分配利润实质性程序表 M6A ',
    remark: '',
    progress: 0,
  },
  {
    seq: 2,
    name: '审定表',
    indexCode: 'M6-1',
    sheetKey: '审定表M6-1',
    remark: '权益类贷方',
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
    name: '明细表（利润分配结转）',
    indexCode: 'M6-2',
    sheetKey: '明细表M6-2',
    remark: '核心公式链',
    progress: 0,
  },
  {
    seq: 6,
    name: '调整分录汇总',
    indexCode: 'M6-3',
    sheetKey: '调整分录汇总M6-3',
    remark: '',
    progress: 0,
  },
  {
    seq: 7,
    name: '未分配利润检查表',
    indexCode: 'M6-4',
    sheetKey: '未分配利润检查表M6-4',
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

// ─── 项目信息（简单版：默认占位，后续集成时从 render-config project_context 填充） ──

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
</script>

<style scoped>
.m6-tab-index {
  padding: 12px;
  font-size: var(--wp-font-size, 13px);
}

/* ─── 项目信息区 ─── */
.m6-project-info {
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
.m6-equity-badge {
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

.m6-equity-badge .el-icon {
  font-size: 16px;
  color: #43a047;
  flex-shrink: 0;
}

/* ─── 蓝色渐变引导区 ─── */
.m6-guide {
  background: linear-gradient(135deg, #e8f4fd 0%, #d6eaf8 100%);
  border: 1px solid #b3d9f2;
  border-radius: 8px;
  padding: 14px 20px;
  margin-bottom: 16px;
}

.m6-guide-header {
  display: flex;
  align-items: center;
  gap: 6px;
  font-weight: 500;
  color: #1a73e8;
  margin-bottom: 10px;
  font-size: var(--wp-font-size, 13px);
}

.m6-guide-steps {
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
.m6-progress-section {
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
.m6-index-card {
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

/* ─── 底稿结构说明 ─── */
.m6-structure-note {
  margin-bottom: 12px;
  padding: 8px 12px;
  background: #fafafa;
  border: 1px solid #ebeef5;
  border-radius: 4px;
  font-size: 12px;
  color: #606266;
}

.structure-label {
  font-weight: 500;
  color: #303133;
}

/* ─── 编制提示折叠 ─── */
.m6-details-tip {
  margin-top: 12px;
  padding: 12px 16px;
  background: #fafafa;
  border: 1px solid #ebeef5;
  border-radius: 6px;
  font-size: var(--wp-font-size, 13px);
  color: #606266;
}

.m6-details-tip summary {
  cursor: pointer;
  font-weight: 500;
  color: #303133;
  margin-bottom: 8px;
}

.m6-details-tip ul {
  padding-left: 20px;
  margin: 8px 0 0;
  line-height: 1.8;
}
</style>
