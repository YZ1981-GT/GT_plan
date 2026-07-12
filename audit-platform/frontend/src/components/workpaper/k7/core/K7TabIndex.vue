<template>
  <div class="k7-tab-index">
    <!-- ═══ 总体进度 ═══ -->
    <div class="k7-progress-section">
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
    <div class="k7-guide">
      <div class="k7-guide-header">
        <el-icon><InfoFilled /></el-icon>
        <span>操作步骤引导</span>
      </div>
      <div class="k7-guide-steps">
        <div class="step-item">
          <span class="step-num">①</span>
          <span class="step-text">填写明细表（K7-2）登记各项政府补助收到/分摊明细</span>
        </div>
        <div class="step-item">
          <span class="step-num">②</span>
          <span class="step-text">完成分摊测算（K7-4）复核分摊金额合理性 → 差异标记</span>
        </div>
        <div class="step-item">
          <span class="step-num">③</span>
          <span class="step-text">填写审定表（K7-1）确认递延收益余额 → TB回写2401</span>
        </div>
        <div class="step-item">
          <span class="step-num">④</span>
          <span class="step-text">完成检查（K7-5）+ 附注披露 → 审计结论</span>
        </div>
      </div>
    </div>

    <!-- ═══ 跨底稿引用 ═══ -->
    <div class="k7-cross-refs">
      <span class="cross-refs-label">关联底稿：</span>
      <GtIndexChip value="K7A" :context-project-id="props.projectId" />
      <GtIndexChip value="K10" :context-project-id="props.projectId" />
      <GtIndexChip value="K12" :context-project-id="props.projectId" />
      <GtIndexChip value="A13" :context-project-id="props.projectId" />
    </div>

    <!-- ═══ 核心组 ═══ -->
    <el-card shadow="never" class="k7-group-card group-core">
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

    <!-- ═══ 分摊测算+检查组 ═══ -->
    <el-card shadow="never" class="k7-group-card group-amort">
      <template #header>
        <span class="group-title">分摊测算与检查</span>
        <el-tag size="small" type="warning" effect="light">{{ groupProgress('amort') }}</el-tag>
      </template>
      <el-table
        :data="amortSheets"
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
    <el-card shadow="never" class="k7-group-card group-disclosure">
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
    <details class="k7-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li>递延收益为<strong>负债类贷方科目</strong>（2401）：期末 = 期初 + 收到(增加) − 分摊(减少)</li>
        <li>审定数 = 未审数 + AJE + RJE</li>
        <li>CAS16政府补助：与资产相关→按资产使用寿命直线分摊；与收益相关→分期或一次性计入损益</li>
        <li>分摊去向：与日常活动相关→其他收益(K10)；与日常活动无关→营业外收入(K12)</li>
        <li>三角勾稽：审定表合计 vs 明细表期末合计；明细分摊 vs 测算分摊</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * K7TabIndex.vue — K7 递延收益底稿目录（9 sheet进度表）
 *
 * 9个功能sheet分3组（核心/分摊测算与检查/附注）展示进度。
 * 点击行 emit navigate-sheet 事件切换 sheetName。
 * GtIndexChip 跨底稿跳转（K7A/K10/K12/A13）
 *
 * Spec: .kiro/specs/k7-deferred-income/ | Task: 4.1
 * Requirements: 1.1-1.10
 */
import { computed, defineAsyncComponent, type Ref } from 'vue'
import { InfoFilled } from '@element-plus/icons-vue'

const GtIndexChip = defineAsyncComponent(() => import('../../GtIndexChip.vue'))

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any> | Ref<Map<string, any>>
  isReadonly: boolean
}>()

const emit = defineEmits<{
  (e: 'navigate-sheet', sheetName: string): void
}>()

// ─── Sheet Row 定义 ──────────────────────────────────────────────────────────

interface SheetRow {
  seq: number; name: string; code: string; sheetKey: string
  description: string; group: 'core' | 'amort' | 'disclosure'; progress: number
}

function getResponses(): Map<string, any> {
  const r = props.allResponses
  if (r instanceof Map) return r
  return (r as any)?.value ?? new Map()
}

function calcSheetProgress(prefix: string, expectedFields: number): number {
  const responses = getResponses()
  if (!responses || responses.size === 0) return 0
  let count = 0
  for (const key of responses.keys()) {
    if (key.startsWith(prefix)) count++
  }
  if (count === 0) return 0
  if (count >= expectedFields) return 100
  return Math.min(Math.round((count / expectedFields) * 100), 99)
}

const allSheets = computed<SheetRow[]>(() => [
  { seq: 1, name: '递延收益实质性程序表', code: 'K7A', sheetKey: '实质性程序表K7A', description: '实质性程序清单与执行情况', group: 'core', progress: calcSheetProgress('K7A-', 5) },
  { seq: 2, name: '审定表', code: 'K7-1', sheetKey: '审定表K7-1', description: '负债类54行审定（49公式）+TB回写2401', group: 'core', progress: calcSheetProgress('K7-1-', 10) },
  { seq: 3, name: '明细表', code: 'K7-2', sheetKey: '明细表K7-2', description: '32列3区段+补助项目明细+41行', group: 'core', progress: calcSheetProgress('K7-2-', 6) },
  { seq: 4, name: '调整分录汇总', code: 'K7-3', sheetKey: '调整分录汇总K7-3', description: 'AJE/RJE管理（借贷平衡）', group: 'core', progress: calcSheetProgress('K7-3-', 4) },
  { seq: 5, name: '分摊测算表', code: 'K7-4', sheetKey: '测算表K7-4', description: '23公式+政府补助直线分摊+差异标记', group: 'amort', progress: calcSheetProgress('K7-4-', 6) },
  { seq: 6, name: '递延收益检查表', code: 'K7-5', sheetKey: '递延收益检查表K7-5', description: '5项逐项合规/不合规/不适用判断+抽凭', group: 'amort', progress: calcSheetProgress('K7-5-', 4) },
  { seq: 7, name: '附注披露信息（上市公司）', code: '附注上市', sheetKey: '附注披露信息（上市公司）', description: '18×11递延收益附注（按相关类型）', group: 'disclosure', progress: calcSheetProgress('K7-disclosure-listed-', 5) },
  { seq: 8, name: '附注披露信息（国企）', code: '附注国企', sheetKey: '附注披露信息（国有企业）', description: '18×10国企版附注披露', group: 'disclosure', progress: calcSheetProgress('K7-disclosure-soe-', 5) },
])

const coreSheets = computed(() => allSheets.value.filter(s => s.group === 'core'))
const amortSheets = computed(() => allSheets.value.filter(s => s.group === 'amort'))
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
.k7-tab-index { padding: 12px; font-size: var(--wp-font-size, 13px); }
.k7-progress-section { margin-bottom: 16px; padding: 14px 16px; background: #f5f7fa; border-radius: 8px; }
.progress-info { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; font-size: var(--wp-font-size, 13px); color: #606266; }
.progress-text { font-weight: 600; color: #303133; }
.progress-stats { display: flex; gap: 8px; margin-top: 10px; }
.k7-guide { background: linear-gradient(135deg, #e8f4fd 0%, #d6eaf8 100%); border: 1px solid #b3d9f2; border-radius: 8px; padding: 14px 20px; margin-bottom: 16px; }
.k7-guide-header { display: flex; align-items: center; gap: 6px; font-weight: 500; color: #1a73e8; margin-bottom: 10px; font-size: var(--wp-font-size, 13px); }
.k7-guide-steps { display: grid; grid-template-columns: repeat(2, 1fr); gap: 8px 24px; }
.step-item { display: flex; align-items: center; gap: 8px; font-size: var(--wp-font-size, 13px); color: #374151; }
.step-num { display: inline-flex; align-items: center; justify-content: center; width: 22px; height: 22px; border-radius: 50%; background: #1a73e8; color: #fff; font-size: 11px; font-weight: 600; flex-shrink: 0; }
.k7-group-card { margin-bottom: 14px; }
.k7-group-card :deep(.el-card__header) { display: flex; align-items: center; justify-content: space-between; padding: 10px 16px; }
.group-title { font-size: 14px; font-weight: 600; color: #303133; }
.group-core :deep(.el-card__header) { background: linear-gradient(90deg, #f0faf0 0%, #f8fdf8 100%); }
.group-amort :deep(.el-card__header) { background: linear-gradient(90deg, #fff7ed 0%, #fffbf5 100%); }
.group-disclosure :deep(.el-card__header) { background: linear-gradient(90deg, #fefce8 0%, #fefdf5 100%); }
.sheet-name-link { color: #1a73e8; cursor: pointer; font-size: var(--wp-font-size, 13px); }
.sheet-name-link:hover { text-decoration: underline; }
.progress-label { display: inline-block; margin-left: 8px; font-size: 12px; color: #909399; width: 36px; }
:deep(.completed-row) { background-color: #f0f9eb !important; }
:deep(.in-progress-row) { background-color: #fdf6ec !important; }
:deep(.el-table) { font-size: var(--wp-font-size, 13px); }
:deep(.el-table .el-table__row) { cursor: pointer; }
:deep(.el-table .el-table__row:hover) { background-color: #ecf5ff !important; }
.k7-details-tip { margin-top: 12px; padding: 12px 16px; background: #fafafa; border: 1px solid #ebeef5; border-radius: 6px; font-size: var(--wp-font-size, 13px); color: #606266; }
.k7-details-tip summary { cursor: pointer; font-weight: 500; color: #303133; margin-bottom: 8px; }
.k7-details-tip ul { padding-left: 20px; margin: 8px 0 0; line-height: 1.8; }
.k7-cross-refs { display: flex; align-items: center; gap: 8px; margin-bottom: 14px; padding: 8px 12px; background: #f5f7fa; border-radius: 6px; }
.cross-refs-label { font-size: var(--wp-font-size, 13px); color: #909399; }
</style>
