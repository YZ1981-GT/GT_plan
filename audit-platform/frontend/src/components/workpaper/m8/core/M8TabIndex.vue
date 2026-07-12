<template>
  <div class="m8-tab-index">
    <!-- ━━━ 项目信息区 ━━━ -->
    <el-card shadow="never" class="m8-project-info">
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

    <!-- ━━━ 权益类贷方科目醒目标注 ━━━ -->
    <div class="m8-equity-badge">
      <el-icon><WarningFilled /></el-icon>
      <span>一般风险准备为权益类贷方科目（期末 = 期初 + 贷方 − 借方），从净利润中计提时贷方增加，转回/使用时借方减少</span>
    </div>

    <!-- ━━━ 金融企业行业守卫适用性状态 ━━━ -->
    <div class="m8-industry-guard-status" :class="isFinancial ? 'applicable' : 'not-applicable'">
      <el-icon v-if="isFinancial"><CircleCheckFilled /></el-icon>
      <el-icon v-else><CircleCloseFilled /></el-icon>
      <span v-if="isFinancial">金融企业行业守卫：<strong>适用</strong>（当前为金融/银行/证券/保险类企业）</span>
      <span v-else>金融企业行业守卫：<strong>不适用</strong>（一般风险准备仅适用金融企业）</span>
    </div>

    <!-- ━━━ 蓝色渐变操作引导区 ━━━ -->
    <div class="m8-guide">
      <div class="m8-guide-header">
        <el-icon><InfoFilled /></el-icon>
        <span>操作步骤引导</span>
      </div>
      <div class="m8-guide-steps">
        <div class="step-item">
          <span class="step-num">①</span>
          <span class="step-text">填写审定表（M8-1）确认一般风险准备余额（权益类贷方，计提+转回）</span>
        </div>
        <div class="step-item">
          <span class="step-num">②</span>
          <span class="step-text">录入明细（M8-2）按计提/转回分区核对</span>
        </div>
        <div class="step-item">
          <span class="step-num">③</span>
          <span class="step-text">完成风险资产计提测试（M8-4）验证按风险资产1.5%计提合规性</span>
        </div>
        <div class="step-item">
          <span class="step-num">④</span>
          <span class="step-text">完成调整分录（M8-3）及附注披露</span>
        </div>
      </div>
    </div>

    <!-- ━━━ 总体进度 ━━━ -->
    <div class="m8-progress-section">
      <div class="progress-info">
        <span>编制进度</span>
        <span class="progress-text">{{ completedCount }} / {{ totalCount }} ({{ progressPercent }}%)</span>
      </div>
      <el-progress :percentage="progressPercent" :stroke-width="8" :show-text="false" />
    </div>

    <!-- ━━━ 底稿目录表格 ━━━ -->
    <el-card shadow="never" class="m8-index-card">
      <template #header>
        <span class="card-title">致同会计师事务所 / 一般风险准备底稿</span>
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
        <el-table-column label="适用性" width="100" align="center">
          <template #default="{ row }">
            <el-icon v-if="row.applicable" class="status-icon applicable"><CircleCheckFilled /></el-icon>
            <el-icon v-else class="status-icon not-applicable"><CircleCloseFilled /></el-icon>
          </template>
        </el-table-column>
        <el-table-column label="备注" width="120" align="center">
          <template #default="{ row }">
            <span v-if="row.remark" class="remark-text">{{ row.remark }}</span>
            <span v-else class="no-index">—</span>
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

    <!-- ━━━ 编制提示（折叠） ━━━ -->
    <details class="m8-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li>一般风险准备（4104）为<strong>权益类贷方科目</strong>：期末 = 期初 + 贷方（计提增加） − 借方（使用减少）</li>
        <li>一般风险准备<strong>仅适用金融企业</strong>（银行/证券/保险/信托/基金/期货/金融租赁）</li>
        <li>金融企业一般风险准备原则上不低于<strong>风险资产期末余额的1.5%</strong></li>
        <li>M8-4 测试表将风险资产×计提比例与账面对比，验证计提是否充足</li>
        <li>明细表合计需与审定表交叉验证</li>
        <li>调整分录需保持借贷平衡，通过EventBus同步更新审定表</li>
        <li>附注披露根据企业类型（上市/国企）自动切换模板</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * M8TabIndex — M8 一般风险准备底稿目录
 *
 * 7 行 sheet 目录列表（序号 | 内容 | 索引号 | 适用性 | 备注 | 操作）。
 * 点击行 emit navigate 事件（由 GtM8GeneralRiskReserve 监听切换 sheetName）。
 * 引导区 4 步：审定表(权益类贷方) → 明细(计提/转回) → 风险资产计提测试 → 调整+附注。
 * 醒目标注"一般风险准备为权益类贷方科目"。
 * 金融企业行业守卫适用性状态显示。
 *
 * Requirements: 1.2, 5.3
 */
import { computed, ref, onMounted } from 'vue'
import { CircleCheckFilled, CircleCloseFilled, InfoFilled, WarningFilled } from '@element-plus/icons-vue'
import GtIndexChip from '@/components/workpaper/GtIndexChip.vue'
import { useM8CrossSheet } from '@/components/workpaper/composables/useM8CrossSheet'
import { api } from '@/services/apiProxy'

// ─── Props / Emits ───────────────────────────────────────────────────────────
const props = defineProps<{
  wpId: string
  projectId: string
  isReadonly: boolean
}>()

const emit = defineEmits<{
  (e: 'navigate', sheetName: string): void
}>()

// ─── 行业守卫（isFinancialEntity from useM8CrossSheet） ──────────────────────
// 加载 checklist_responses 获取 M8-industry-guard 持久化状态
const allResponses = ref<Map<string, any>>(new Map())
const projectInfoRef = ref<any>(null)
const { isFinancialEntity } = useM8CrossSheet(allResponses, projectInfoRef)
const isFinancial = computed(() => isFinancialEntity.value)

// 加载行业守卫持久化状态
async function loadIndustryGuardStatus() {
  if (!props.wpId) return
  try {
    const res = await api.get(`/api/workpapers/${props.wpId}/checklist-responses`, { _silent: true } as any)
    const responses: any[] = Array.isArray(res) ? res : (res as any)?.data ?? []
    const map = new Map<string, any>()
    for (const r of responses) {
      if (r.item_id?.startsWith('M8-')) {
        map.set(r.item_id, { item_id: r.item_id, conclusion: r.conclusion ?? null, remark: r.remark ?? null })
      }
    }
    allResponses.value = map
  } catch { /* 加载失败不阻塞，默认适用 */ }
}

// 尝试从 render-config 获取 project_info
async function loadProjectInfo() {
  if (!props.wpId) return
  try {
    const res = await api.get(
      `/api/workpapers/${props.wpId}/render-config?force_component_type=m8-general-risk-reserve`,
      { _silent: true } as any,
    )
    const data = (res as any)?.data ?? res
    const firstSheet = data?.sheets?.[0]?.html_data
    projectInfoRef.value = firstSheet?.project_info || data?.project_info || null
  } catch { /* silent */ }
}

onMounted(async () => {
  await Promise.all([loadIndustryGuardStatus(), loadProjectInfo()])
})

// ─── Sheet 目录行定义 ──────────────────────────────────────────────────────────
interface SheetRow {
  seq: number
  name: string
  indexCode: string
  /** sheetName（传给父组件用于 v-if 分发） */
  sheetKey: string
  /** 金融企业行业守卫适用性 */
  applicable: boolean
  /** 备注（如"无需打印"） */
  remark: string
  progress: number
}

/**
 * 7 行 sheet 目录（对应源模板 M8 一般风险准备底稿目录）。
 * 进度条默认0%，后续集成时根据 checklist_responses 数据填充。
 */
const sheetRows = computed<SheetRow[]>(() => [
  {
    seq: 1,
    name: '一般风险准备实质性程序表',
    indexCode: 'M8A',
    sheetKey: '一般风险准备实质性程序表M8A',
    applicable: isFinancial.value,
    remark: '',
    progress: 0,
  },
  {
    seq: 2,
    name: '审定表',
    indexCode: 'M8-1',
    sheetKey: '审定表M8-1',
    applicable: isFinancial.value,
    remark: '',
    progress: 0,
  },
  {
    seq: 3,
    name: '附注披露信息（上市公司）',
    indexCode: '',
    sheetKey: '附注披露信息（上市公司）',
    applicable: isFinancial.value,
    remark: '无需打印',
    progress: 0,
  },
  {
    seq: 4,
    name: '附注披露信息（国企）',
    indexCode: '',
    sheetKey: '附注披露信息（国企）',
    applicable: isFinancial.value,
    remark: '无需打印',
    progress: 0,
  },
  {
    seq: 5,
    name: '明细表',
    indexCode: 'M8-2',
    sheetKey: '明细表M8-2',
    applicable: isFinancial.value,
    remark: '',
    progress: 0,
  },
  {
    seq: 6,
    name: '调整分录汇总',
    indexCode: 'M8-3',
    sheetKey: '调整分录汇总M8-3',
    applicable: isFinancial.value,
    remark: '',
    progress: 0,
  },
  {
    seq: 7,
    name: '一般风险准备测试表',
    indexCode: 'M8-4',
    sheetKey: '一般风险准备测试表M8-4',
    applicable: isFinancial.value,
    remark: '',
    progress: 0,
  },
])

// ─── 进度计算 ──────────────────────────────────────────────────────────────────
const totalCount = computed(() => sheetRows.value.length)

const completedCount = computed(() =>
  sheetRows.value.filter(r => r.progress >= 100).length,
)

const progressPercent = computed(() => {
  if (totalCount.value === 0) return 0
  const avgProgress = sheetRows.value.reduce((sum, r) => sum + r.progress, 0) / totalCount.value
  return Math.round(avgProgress)
})

// ─── 项目信息（简单版：默认占位，后续集成时从 render-config 填充） ──────────────
const projectInfo = computed(() => ({
  clientName: '',
  cutoffDate: '',
  preparer: '',
  prepareDate: '',
  reviewer: '',
  reviewDate: '',
}))

// ─── 交互 ──────────────────────────────────────────────────────────────────────
function handleRowClick(row: SheetRow) {
  if (props.isReadonly && row.progress === 0) return
  emit('navigate', row.sheetKey)
}

function handleNavigate(row: SheetRow) {
  emit('navigate', row.sheetKey)
}

function getRowClassName({ row }: { row: SheetRow }): string {
  if (!row.applicable) return 'not-applicable-row'
  return row.progress >= 100 ? 'completed-row' : ''
}
</script>

<style scoped>
.m8-tab-index {
  padding: 12px;
  font-size: var(--wp-font-size, 13px);
}

/* ─── 项目信息区 ─── */
.m8-project-info {
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
.m8-equity-badge {
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

.m8-equity-badge .el-icon {
  font-size: 16px;
  color: #43a047;
  flex-shrink: 0;
}

/* ─── 金融企业行业守卫适用性状态 ─── */
.m8-industry-guard-status {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 16px;
  margin-bottom: 16px;
  border-radius: 6px;
  font-size: var(--wp-font-size, 13px);
  font-weight: 500;
}

.m8-industry-guard-status.applicable {
  background: linear-gradient(135deg, #e8f5e9 0%, #f1f8e9 100%);
  border: 1px solid #a5d6a7;
  border-left: 4px solid #4caf50;
  color: #2e7d32;
}

.m8-industry-guard-status.applicable .el-icon {
  font-size: 18px;
  color: #4caf50;
}

.m8-industry-guard-status.not-applicable {
  background: linear-gradient(135deg, #fbe9e7 0%, #ffebee 100%);
  border: 1px solid #ef9a9a;
  border-left: 4px solid #e53935;
  color: #c62828;
}

.m8-industry-guard-status.not-applicable .el-icon {
  font-size: 18px;
  color: #e53935;
}

/* ─── 蓝色渐变引导区 ─── */
.m8-guide {
  background: linear-gradient(135deg, #e8f4fd 0%, #d6eaf8 100%);
  border: 1px solid #b3d9f2;
  border-radius: 8px;
  padding: 14px 20px;
  margin-bottom: 16px;
}

.m8-guide-header {
  display: flex;
  align-items: center;
  gap: 6px;
  font-weight: 500;
  color: #1a73e8;
  margin-bottom: 10px;
  font-size: var(--wp-font-size, 13px);
}

.m8-guide-steps {
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
.m8-progress-section {
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
.m8-index-card {
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

.remark-text {
  color: #909399;
  font-size: 12px;
}

.status-icon {
  font-size: 18px;
}

.status-icon.applicable {
  color: #4caf50;
}

.status-icon.not-applicable {
  color: #e53935;
}

:deep(.completed-row) {
  background-color: #f0f9eb !important;
}

:deep(.not-applicable-row) {
  background-color: #fafafa !important;
  color: #c0c4cc;
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
.m8-details-tip {
  margin-top: 12px;
  padding: 12px 16px;
  background: #fafafa;
  border: 1px solid #ebeef5;
  border-radius: 6px;
  font-size: var(--wp-font-size, 13px);
  color: #606266;
}

.m8-details-tip summary {
  cursor: pointer;
  font-weight: 500;
  color: #303133;
  margin-bottom: 8px;
}

.m8-details-tip ul {
  padding-left: 20px;
  margin: 8px 0 0;
  line-height: 1.8;
}
</style>
