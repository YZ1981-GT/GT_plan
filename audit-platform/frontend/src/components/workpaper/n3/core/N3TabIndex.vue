<template>
  <div class="n3-tab-index">
    <!-- ═══ 顶部标识头 ═══ -->
    <div class="n3-header-bar">
      <span class="header-code">底稿编码 N3</span>
      <span class="header-sep">|</span>
      <span class="header-subject">科目 2901 递延所得税负债</span>
      <span class="header-sep">|</span>
      <span class="header-direction">负债类 / 贷方</span>
    </div>

    <!-- ═══ 负债类贷方科目醒目标注 ═══ -->
    <div class="n3-liability-badge">
      <el-icon><WarningFilled /></el-icon>
      <span>递延所得税负债为负债类贷方科目（期末 = 期初 + 贷方 − 借方），核心：应纳税暂时性差异 × 适用税率，与N1递延所得税资产同源对应</span>
    </div>

    <!-- ═══ 蓝色渐变操作引导区 ═══ -->
    <div class="n3-guide">
      <div class="n3-guide-header">
        <el-icon><InfoFilled /></el-icon>
        <span>操作步骤引导</span>
      </div>
      <div class="n3-guide-steps">
        <div class="step-item">
          <span class="step-num">①</span>
          <span class="step-text">完成审计程序表（N3A）确认审计方案</span>
        </div>
        <div class="step-item">
          <span class="step-num">②</span>
          <span class="step-text">填写审定表（N3-1）确认各差异项目期末余额（负债类：期初+贷−借）</span>
        </div>
        <div class="step-item">
          <span class="step-num">③</span>
          <span class="step-text">录入明细表（N3-2）按应纳税暂时性差异项目逐项核对递延税负债</span>
        </div>
        <div class="step-item">
          <span class="step-num">④</span>
          <span class="step-text">录入调整分录（N3-3）+ 生成附注披露信息</span>
        </div>
      </div>
    </div>

    <!-- ═══ 总体进度 ═══ -->
    <div class="n3-progress-section">
      <div class="progress-info">
        <span>编制进度</span>
        <span class="progress-text">{{ completedCount }} / {{ effectiveTotal }} ({{ progressPercent }}%)</span>
      </div>
      <el-progress :percentage="progressPercent" :stroke-width="8" :show-text="false" />
    </div>

    <!-- ═══ 底稿目录表格 ═══ -->
    <el-card shadow="never" class="n3-index-card">
      <template #header>
        <span class="card-title">致同会计师事务所 / 递延所得税负债底稿</span>
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
            <span :class="row.skip ? 'sheet-name-skip' : 'sheet-name-link'">{{ row.name }}</span>
            <el-tag v-if="row.isCore" size="small" type="danger" class="core-tag">核心</el-tag>
            <el-tag v-if="row.skip" size="small" type="info" class="skip-tag">系统占位</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="索引号" width="100" align="center">
          <template #default="{ row }">
            <GtIndexChip v-if="row.code" :value="row.code" />
            <span v-else class="no-index">—</span>
          </template>
        </el-table-column>
        <el-table-column label="进度" width="140" align="center">
          <template #default="{ row }">
            <template v-if="!row.skip">
              <el-progress
                :percentage="row.progress"
                :stroke-width="6"
                :show-text="false"
                :color="getProgressColor(row.progress)"
                style="width: 80px; display: inline-block"
              />
              <span class="progress-label">{{ row.progress }}%</span>
            </template>
            <span v-else class="skip-label">—</span>
          </template>
        </el-table-column>
        <el-table-column label="联动" width="80" align="center">
          <template #default="{ row }">
            <span v-if="row.linkageStatus === 'matched'" class="linkage-badge linkage-ok">✓</span>
            <span v-else-if="row.linkageStatus === 'diff'" class="linkage-badge linkage-warn">⚠</span>
            <span v-else class="linkage-badge linkage-na">—</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="80" align="center">
          <template #default="{ row }">
            <el-button
              v-if="!row.skip"
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
    <details class="n3-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li>递延所得税负债（2901）为<strong>负债类贷方科目</strong>：期末 = 期初 + 本期贷方（确认增加）− 本期借方（转回减少）</li>
        <li>核心公式：递延所得税负债 = 应纳税暂时性差异 × 适用税率</li>
        <li>应纳税暂时性差异产生：资产账面价值 > 计税基础 或 负债账面价值 &lt; 计税基础</li>
        <li>不确认递延所得税负债的特殊项：商誉初始确认 / 长期股权投资拟长期持有</li>
        <li>与N1递延所得税资产同源对应：同一纳税主体可抵销后净额列示，不同主体分列</li>
        <li>递延所得税负债本期变动额联动N5递延所得税费用核对（通过EventBus 'deferred-tax:liability-updated'）</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * N3TabIndex — N3 递延所得税负债底稿目录
 *
 * 6 行 sheet 目录（1 行系统占位 GT_Custom 标记 skip）。
 * 有效 sheet 5 个，进度条展示 n/5 完成度。
 * 联动状态列：从 useN3CrossSheet 获取 N3-1↔N3-2 勾稽状态。
 * 点击行 emit navigate 事件（由 GtN3DeferredTaxLiabilities 监听切换 sheetName）。
 *
 * Requirements: 1.2
 */
import { computed } from 'vue'
import { InfoFilled, WarningFilled } from '@element-plus/icons-vue'
import GtIndexChip from '@/components/workpaper/GtIndexChip.vue'
import { useN3CrossSheet } from '../../composables/useN3CrossSheet'

// ─── Props / Emits ───────────────────────────────────────────────────────────

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly?: boolean
}>()

const emit = defineEmits<{
  (e: 'navigate', sheetCode: string): void
}>()

// ─── CrossSheet 联动 ─────────────────────────────────────────────────────────

const allResponsesRef = computed(() => props.allResponses)
const { adjudicationVsDetail } = useN3CrossSheet(allResponsesRef)

// ─── Types ───────────────────────────────────────────────────────────────────

type LinkageStatus = 'matched' | 'diff' | 'none'

interface SheetRow {
  seq: number
  name: string
  code: string
  sheetKey: string
  progress: number
  isCore: boolean
  skip: boolean
  linkageStatus: LinkageStatus
}

// ─── Sheet 目录行定义（6行，1行 skip） ──────────────────────────────────────

const sheetRows = computed<SheetRow[]>(() => {
  const hasData = props.allResponses.size > 0
  const detailMatch = adjudicationVsDetail.value.isMatch

  // N3-1审定表与N3-2明细勾稽
  const n3_1Linkage: LinkageStatus =
    detailMatch ? 'matched' : (hasData ? 'diff' : 'none')

  const n3_2Linkage: LinkageStatus =
    detailMatch ? 'matched' : (hasData ? 'diff' : 'none')

  return [
    { seq: 1, name: '递延所得税负债审计程序表', code: 'N3A', sheetKey: '递延所得税负债审计程序表的N3A', progress: getSheetProgress('N3A'), isCore: false, skip: false, linkageStatus: 'none' },
    { seq: 2, name: '递延所得税负债审定表', code: 'N3-1', sheetKey: '递延所得税负债审定表N3-1', progress: getSheetProgress('N3-1'), isCore: true, skip: false, linkageStatus: n3_1Linkage },
    { seq: 3, name: '递延所得税负债明细表', code: 'N3-2', sheetKey: '递延所得税负债明细表N3-2', progress: getSheetProgress('N3-2'), isCore: true, skip: false, linkageStatus: n3_2Linkage },
    { seq: 4, name: '调整分录汇总表', code: 'N3-3', sheetKey: '调整分录汇总表N3-3', progress: getSheetProgress('N3-3'), isCore: false, skip: false, linkageStatus: 'none' },
    { seq: 5, name: '附注披露信息', code: '', sheetKey: '附注', progress: getSheetProgress('附注'), isCore: false, skip: false, linkageStatus: 'none' },
    { seq: 6, name: 'GT_Custom（系统占位）', code: '', sheetKey: 'GT_Custom', progress: 0, isCore: false, skip: true, linkageStatus: 'none' },
  ]
})

// ─── 进度计算 ────────────────────────────────────────────────────────────────

/**
 * 根据 allResponses 中的数据判断 sheet 进度
 * 简单策略：有相关 item_id 数据 → 100%，否则 0%
 */
function getSheetProgress(code: string): number {
  if (props.allResponses.size === 0) return 0

  const prefixMap: Record<string, string> = {
    'N3A': 'N3A-',
    'N3-1': 'N3-1-',
    'N3-2': 'N3-2-',
    'N3-3': 'N3-3-',
    '附注': 'N3-disclosure-',
  }

  const prefix = prefixMap[code]
  if (!prefix) return 0

  // 统计该 sheet 前缀下有多少有效响应
  let filled = 0
  let total = 0
  for (const [key] of props.allResponses) {
    if (key.startsWith(prefix)) {
      total++
      const val = props.allResponses.get(key)
      if (val?.conclusion != null && val.conclusion !== '' && val.conclusion !== '0') {
        filled++
      }
    }
  }

  if (total === 0) return 0
  return Math.round((filled / total) * 100)
}

const effectiveSheets = computed(() => sheetRows.value.filter(r => !r.skip))
const effectiveTotal = computed(() => effectiveSheets.value.length)
const completedCount = computed(() => effectiveSheets.value.filter(r => r.progress >= 100).length)
const progressPercent = computed(() => {
  if (effectiveTotal.value === 0) return 0
  const avg = effectiveSheets.value.reduce((s, r) => s + r.progress, 0) / effectiveTotal.value
  return Math.round(avg)
})

// ─── 交互 ────────────────────────────────────────────────────────────────────

function handleRowClick(row: SheetRow) {
  if (row.skip) return
  if (props.isReadonly && row.progress === 0) return
  emit('navigate', row.sheetKey)
}

function handleNavigate(row: SheetRow) {
  emit('navigate', row.sheetKey)
}

function getRowClassName({ row }: { row: SheetRow }): string {
  if (row.skip) return 'skip-row'
  if (row.progress >= 100) return 'completed-row'
  return ''
}

function getProgressColor(percent: number): string {
  if (percent >= 100) return '#67c23a'
  if (percent >= 50) return '#409eff'
  return '#e6e8eb'
}
</script>

<style scoped>
.n3-tab-index {
  padding: 12px;
  font-size: var(--wp-font-size, 13px);
}

/* ─── 顶部标识头 ─── */
.n3-header-bar {
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

/* ─── 负债类贷方科目醒目标注 ─── */
.n3-liability-badge {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 16px;
  margin-bottom: 16px;
  background: linear-gradient(135deg, #fce4ec 0%, #f8bbd0 100%);
  border: 1px solid #f48fb1;
  border-left: 4px solid #e91e63;
  border-radius: 6px;
  font-size: var(--wp-font-size, 13px);
  font-weight: 500;
  color: #880e4f;
}

.n3-liability-badge .el-icon {
  font-size: 16px;
  color: #e91e63;
  flex-shrink: 0;
}

/* ─── 蓝色渐变引导区 ─── */
.n3-guide {
  background: linear-gradient(135deg, #e8f4fd 0%, #d6eaf8 100%);
  border: 1px solid #b3d9f2;
  border-radius: 8px;
  padding: 14px 20px;
  margin-bottom: 16px;
}

.n3-guide-header {
  display: flex;
  align-items: center;
  gap: 6px;
  font-weight: 500;
  color: #1a73e8;
  margin-bottom: 10px;
  font-size: var(--wp-font-size, 13px);
}

.n3-guide-steps {
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
.n3-progress-section {
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
.n3-index-card {
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

.sheet-name-skip {
  color: #c0c4cc;
  font-size: var(--wp-font-size, 13px);
  text-decoration: line-through;
}

.no-index {
  color: #c0c4cc;
}

.core-tag {
  margin-left: 8px;
  font-size: 11px;
  vertical-align: middle;
}

.skip-tag {
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

.skip-label {
  font-size: 12px;
  color: #c0c4cc;
  font-style: italic;
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

:deep(.skip-row) {
  background-color: #f9f9f9 !important;
  opacity: 0.6;
}

:deep(.skip-row:hover) {
  cursor: not-allowed !important;
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
.n3-details-tip {
  margin-top: 12px;
  padding: 12px 16px;
  background: #fafafa;
  border: 1px solid #ebeef5;
  border-radius: 6px;
  font-size: var(--wp-font-size, 13px);
  color: #606266;
}

.n3-details-tip summary {
  cursor: pointer;
  font-weight: 500;
  color: #303133;
  margin-bottom: 8px;
}

.n3-details-tip ul {
  padding-left: 20px;
  margin: 8px 0 0;
  line-height: 1.8;
}
</style>
