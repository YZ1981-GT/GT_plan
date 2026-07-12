<template>
  <div class="k6-tab-index">
    <!-- ═══ 总体进度 ═══ -->
    <div class="k6-progress-section">
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
    <div class="k6-guide">
      <div class="k6-guide-header">
        <el-icon><InfoFilled /></el-icon>
        <span>操作步骤引导</span>
      </div>
      <div class="k6-guide-steps">
        <div class="step-item">
          <span class="step-num">①</span>
          <span class="step-text">CAS42五条件初始确认（K6-4）→ 判断是否满足持有待售分类</span>
        </div>
        <div class="step-item">
          <span class="step-num">②</span>
          <span class="step-text">填写明细表（K6-2）→ 逐项登记处置组/资产基本信息</span>
        </div>
        <div class="step-item">
          <span class="step-num">③</span>
          <span class="step-text">减值测试（K6-5/K6-6）→ 孰低法计量 + 处置组分摊</span>
        </div>
        <div class="step-item">
          <span class="step-num">④</span>
          <span class="step-text">审定表（K6-1）→ 确认审定额 → TB回写(1481+2605) → 附注披露</span>
        </div>
      </div>
    </div>

    <!-- ═══ 跨底稿引用 ═══ -->
    <div class="k6-cross-refs">
      <span class="cross-refs-label">关联底稿：</span>
      <GtIndexChip value="K6A" :context-project-id="props.projectId" />
      <GtIndexChip value="A13" :context-project-id="props.projectId" />
      <GtIndexChip value="B50" :context-project-id="props.projectId" />
    </div>

    <!-- ═══ 核心组 ═══ -->
    <el-card shadow="never" class="k6-group-card group-core">
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
        <el-table-column prop="description" label="简要说明" min-width="260" />
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

    <!-- ═══ 减值测试组 ═══ -->
    <el-card shadow="never" class="k6-group-card group-impairment">
      <template #header>
        <span class="group-title">CAS42分类 + 减值测试</span>
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
        <el-table-column prop="description" label="简要说明" min-width="260" />
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

    <!-- ═══ 附注组 ═══ -->
    <el-card shadow="never" class="k6-group-card group-disclosure">
      <template #header>
        <span class="group-title">附注披露</span>
        <el-tag size="small" effect="light">{{ groupProgress('disclosure') }}</el-tag>
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
        <el-table-column prop="description" label="简要说明" min-width="260" />
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
    <details class="k6-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li>持有待售资产为<strong>资产类借方科目</strong>（1481）：期末 = 期初 + 增加 − 减少 − 减值</li>
        <li>持有待售负债为<strong>负债类贷方科目</strong>（2605）：期末 = 期初 + 增加 − 减少</li>
        <li>审定数 = 未审数 + AJE + RJE</li>
        <li>CAS42五条件全部满足方可分类为持有待售：①可立即出售 ②已作出决议 ③已签不可撤销协议 ④预计1年内完成 ⑤售价合理不太可能变更</li>
        <li>减值孰低法：账面价值 与 公允价值减出售费用净额 取低者，超出部分计提减值</li>
        <li>处置组减值：先抵减商誉，再按账面比例分摊至组内非流动资产</li>
        <li>不再满足持有待售条件时：按较低者计量（可收回金额 vs 假设未分类账面）</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * K6TabIndex.vue — K6 持有待售资产和负债 底稿目录（11 sheet进度表）
 *
 * 11个有效sheet分3组（核心/CAS42分类+减值/附注）展示进度。
 * 点击行 emit navigate-sheet 事件切换 sheetName。
 * GtIndexChip 跨底稿跳转（A13/B50/K6A）
 *
 * Spec: .kiro/specs/k6-held-for-sale/ | Task: 4.1
 * Requirements: 1.2
 */
import { computed, defineAsyncComponent } from 'vue'
import { InfoFilled } from '@element-plus/icons-vue'

const GtIndexChip = defineAsyncComponent(() => import('../../GtIndexChip.vue'))

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const emit = defineEmits<{
  (e: 'navigate-sheet', sheetName: string): void
}>()

// ─── Sheet Row 定义 ──────────────────────────────────────────────────────────

interface SheetRow {
  seq: number; name: string; code: string; sheetKey: string
  description: string; group: 'core' | 'impairment' | 'disclosure'; progress: number
}

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

const allSheets = computed<SheetRow[]>(() => [
  { seq: 1, name: '持有待售实质性程序表', code: 'K6A', sheetKey: '持有待售实质性程序表K6A', description: '实质性程序清单与执行情况', group: 'core', progress: calcSheetProgress('K6-K6A-', 5) },
  { seq: 2, name: '审定表', code: 'K6-1', sheetKey: '审定表K6-1', description: '资产+负债双区块22行×14列（45公式）+TB回写', group: 'core', progress: calcSheetProgress('K6-1-', 10) },
  { seq: 3, name: '明细表', code: 'K6-2', sheetKey: '明细表K6-2', description: '处置组/资产逐项追踪15列（12公式）+动态行', group: 'core', progress: calcSheetProgress('K6-2-', 6) },
  { seq: 4, name: '调整分录汇总', code: 'K6-3', sheetKey: '调整分录汇总K6-3', description: 'AJE/RJE管理（借贷平衡）', group: 'core', progress: calcSheetProgress('K6-3-', 4) },
  { seq: 5, name: '初始确认检查表', code: 'K6-4', sheetKey: '初始确认检查表K6-4', description: 'CAS42五条件分类判断（核对清单）', group: 'impairment', progress: calcSheetProgress('K6-4-', 5) },
  { seq: 6, name: '减值准备测试表', code: 'K6-5', sheetKey: '减值准备测试表K6-5', description: '后续计量孰低法23行×14列（16公式）', group: 'impairment', progress: calcSheetProgress('K6-5-', 5) },
  { seq: 7, name: '处置组减值测试表', code: 'K6-6', sheetKey: '处置组减值测试表K6-6', description: '处置组整体减值分摊55行×11列（13公式）', group: 'impairment', progress: calcSheetProgress('K6-6-', 5) },
  { seq: 8, name: '不再满足持有待售检查表', code: 'K6-7', sheetKey: '检查表K6-7', description: '不再满足条件→较低者计量+重分类处理', group: 'impairment', progress: calcSheetProgress('K6-7-', 4) },
  { seq: 9, name: '附注披露信息（上市公司）', code: '附注上市', sheetKey: '附注披露信息（上市公司）', description: '持有待售分类+减值披露79×11', group: 'disclosure', progress: calcSheetProgress('K6-disclosure-listed-', 5) },
  { seq: 10, name: '附注披露信息（国企）', code: '附注国企', sheetKey: '附注披露信息（国企）', description: '国企版附注披露61×8', group: 'disclosure', progress: calcSheetProgress('K6-disclosure-soe-', 5) },
  { seq: 11, name: '持有待售实质性程序表（OnlyOffice）', code: 'K6-OO', sheetKey: 'K6-OO-fallback', description: 'OnlyOffice降级模式', group: 'disclosure', progress: 0 },
])

const coreSheets = computed(() => allSheets.value.filter(s => s.group === 'core'))
const impairmentSheets = computed(() => allSheets.value.filter(s => s.group === 'impairment'))
const disclosureSheets = computed(() => allSheets.value.filter(s => s.group === 'disclosure'))

const totalCount = computed(() => allSheets.value.length)
const completedCount = computed(() => allSheets.value.filter(r => r.progress >= 100).length)
const inProgressCount = computed(() => allSheets.value.filter(r => r.progress > 0 && r.progress < 100).length)
const notStartedCount = computed(() => allSheets.value.filter(r => r.progress === 0).length)
const progressPercent = computed(() => {
  if (totalCount.value === 0) return 0
  return Math.round(allSheets.value.reduce((s, r) => s + r.progress, 0) / totalCount.value)
})

function groupProgress(group: string): string {
  const sheets = allSheets.value.filter(s => s.group === group)
  return `${sheets.filter(s => s.progress >= 100).length}/${sheets.length}`
}

function handleRowClick(row: SheetRow) { emit('navigate-sheet', row.sheetKey) }

function getRowClassName({ row }: { row: SheetRow }): string {
  if (row.progress >= 100) return 'completed-row'
  if (row.progress > 0) return 'in-progress-row'
  return ''
}

function getProgressColor(p: number): string {
  if (p >= 100) return '#67c23a'
  if (p >= 50) return '#409eff'
  if (p > 0) return '#e6a23c'
  return '#e6e8eb'
}
</script>

<style scoped>
.k6-tab-index { padding: 12px; font-size: var(--wp-font-size, 13px); }
.k6-progress-section { margin-bottom: 16px; padding: 14px 16px; background: #f5f7fa; border-radius: 8px; }
.progress-info { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; font-size: var(--wp-font-size, 13px); color: #606266; }
.progress-text { font-weight: 600; color: #303133; }
.progress-stats { display: flex; gap: 8px; margin-top: 10px; }
.k6-guide { background: linear-gradient(135deg, #e8f4fd 0%, #d6eaf8 100%); border: 1px solid #b3d9f2; border-radius: 8px; padding: 14px 20px; margin-bottom: 16px; }
.k6-guide-header { display: flex; align-items: center; gap: 6px; font-weight: 500; color: #1a73e8; margin-bottom: 10px; font-size: var(--wp-font-size, 13px); }
.k6-guide-steps { display: grid; grid-template-columns: repeat(2, 1fr); gap: 8px 24px; }
.step-item { display: flex; align-items: center; gap: 8px; font-size: var(--wp-font-size, 13px); color: #374151; }
.step-num { display: inline-flex; align-items: center; justify-content: center; width: 22px; height: 22px; border-radius: 50%; background: #1a73e8; color: #fff; font-size: 11px; font-weight: 600; flex-shrink: 0; }
.k6-group-card { margin-bottom: 14px; }
.k6-group-card :deep(.el-card__header) { display: flex; align-items: center; justify-content: space-between; padding: 10px 16px; }
.group-title { font-size: 14px; font-weight: 600; color: #303133; }
.group-core :deep(.el-card__header) { background: linear-gradient(90deg, #f0faf0 0%, #f8fdf8 100%); }
.group-impairment :deep(.el-card__header) { background: linear-gradient(90deg, #fff7ed 0%, #fffbf5 100%); }
.group-disclosure :deep(.el-card__header) { background: linear-gradient(90deg, #fefce8 0%, #fefdf5 100%); }
.sheet-name-link { color: #1a73e8; cursor: pointer; font-size: var(--wp-font-size, 13px); }
.sheet-name-link:hover { text-decoration: underline; }
.progress-label { display: inline-block; margin-left: 8px; font-size: 12px; color: #909399; width: 36px; }
:deep(.completed-row) { background-color: #f0f9eb !important; }
:deep(.in-progress-row) { background-color: #fdf6ec !important; }
:deep(.el-table) { font-size: var(--wp-font-size, 13px); }
:deep(.el-table .el-table__row) { cursor: pointer; }
:deep(.el-table .el-table__row:hover) { background-color: #ecf5ff !important; }
.k6-details-tip { margin-top: 12px; padding: 12px 16px; background: #fafafa; border: 1px solid #ebeef5; border-radius: 6px; font-size: var(--wp-font-size, 13px); color: #606266; }
.k6-details-tip summary { cursor: pointer; font-weight: 500; color: #303133; margin-bottom: 8px; }
.k6-details-tip ul { padding-left: 20px; margin: 8px 0 0; line-height: 1.8; }
.k6-cross-refs { display: flex; align-items: center; gap: 8px; margin-bottom: 14px; padding: 8px 12px; background: #f5f7fa; border-radius: 6px; }
.cross-refs-label { font-size: var(--wp-font-size, 13px); color: #909399; }
</style>
