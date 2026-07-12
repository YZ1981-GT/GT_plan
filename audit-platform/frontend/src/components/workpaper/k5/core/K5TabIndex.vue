<template>
  <div class="k5-tab-index">
    <!-- ═══ 总体进度 ═══ -->
    <div class="k5-progress-section">
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
    <div class="k5-guide">
      <div class="k5-guide-header">
        <el-icon><InfoFilled /></el-icon>
        <span>操作步骤引导</span>
      </div>
      <div class="k5-guide-steps">
        <div class="step-item">
          <span class="step-num">①</span>
          <span class="step-text">填写明细表（K5-2）识别或有事项、判断可能性、计量最佳估计数</span>
        </div>
        <div class="step-item">
          <span class="step-num">②</span>
          <span class="step-text">完成各专项检查（K5-4质保/K5-5弃置/K5-6诉讼）→ 回连审定表</span>
        </div>
        <div class="step-item">
          <span class="step-num">③</span>
          <span class="step-text">填写审定表（K5-1）确认预计负债余额 → TB回写2701</span>
        </div>
        <div class="step-item">
          <span class="step-num">④</span>
          <span class="step-text">完成综合检查（K5-7）+ 附注披露 → 审计结论</span>
        </div>
      </div>
    </div>

    <!-- ═══ 跨底稿引用 ═══ -->
    <div class="k5-cross-refs">
      <span class="cross-refs-label">关联底稿：</span>
      <GtIndexChip value="K5A" :context-project-id="props.projectId" />
      <GtIndexChip value="A13" :context-project-id="props.projectId" />
      <GtIndexChip value="B50" :context-project-id="props.projectId" />
    </div>

    <!-- ═══ 核心组 ═══ -->
    <el-card shadow="never" class="k5-group-card group-core">
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

    <!-- ═══ 专项检查组 ═══ -->
    <el-card shadow="never" class="k5-group-card group-contingency">
      <template #header>
        <span class="group-title">或有事项专项检查</span>
        <el-tag size="small" type="warning" effect="light">{{ groupProgress('contingency') }}</el-tag>
      </template>
      <el-table
        :data="contingencySheets"
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
    <el-card shadow="never" class="k5-group-card group-disclosure">
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
    <details class="k5-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li>预计负债为<strong>负债类贷方科目</strong>（2701）：期末 = 期初 + 计提 − 转销/冲回</li>
        <li>审定数 = 未审数 + AJE + RJE</li>
        <li>CAS13或有事项三级可能性：很可能(>50%)→确认预计负债；可能(≤50%)→披露或有负债；极小可能→不处理</li>
        <li>最佳估计数计量：单一最可能金额 / 区间中值(上+下)/2 / 期望值加权Σ(金额×概率)</li>
        <li>涉及时间价值重大时（如弃置费用）按现值折现</li>
        <li>三角勾稽：各专项检查表期末 vs K5-1审定表对应类型行</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * K5TabIndex.vue — K5 预计负债底稿目录（10 sheet进度表）
 *
 * 10个有效sheet分3组（核心/或有事项专项检查/附注）展示进度。
 * 点击行 emit navigate-sheet 事件切换 sheetName。
 * GtIndexChip 跨底稿跳转（A13/B50/K5A）
 *
 * Spec: .kiro/specs/k5-provisions/ | Task: 4.1, 6.3
 * Requirements: 1.2, 8.4
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
  description: string; group: 'core' | 'contingency' | 'disclosure'; progress: number
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
  { seq: 1, name: '预计负债实质性程序表', code: 'K5A', sheetKey: '预计负债实质性程序表K5A', description: '实质性程序清单与执行情况', group: 'core', progress: calcSheetProgress('K5-K5A-', 5) },
  { seq: 2, name: '审定表', code: 'K5-1', sheetKey: '审定表K5-1', description: '负债类25行审定（108公式）+TB回写2701', group: 'core', progress: calcSheetProgress('K5-1-', 10) },
  { seq: 3, name: '明细表', code: 'K5-2', sheetKey: '明细表K5-2', description: '42行23列3区段+或有事项判断+色标', group: 'core', progress: calcSheetProgress('K5-2-', 6) },
  { seq: 4, name: '调整分录汇总', code: 'K5-3', sheetKey: '调整分录汇总K5-3', description: 'AJE/RJE管理（借贷平衡）', group: 'core', progress: calcSheetProgress('K5-3-', 4) },
  { seq: 5, name: '产品质量保修检查', code: 'K5-4', sheetKey: '产品质量保修检查表K5-4', description: '质保测算（收入×保修率）+回连K5-1', group: 'contingency', progress: calcSheetProgress('K5-4-', 4) },
  { seq: 6, name: '弃置费用检查', code: 'K5-5', sheetKey: '弃置费用检查表K5-5', description: '现值折现(future/(1+rate)^years)+利息调整', group: 'contingency', progress: calcSheetProgress('K5-5-', 4) },
  { seq: 7, name: '未决诉讼检查', code: 'K5-6', sheetKey: '未决诉讼检查表K5-6', description: '律师函联动+可能性判断+预计损失', group: 'contingency', progress: calcSheetProgress('K5-6-', 4) },
  { seq: 8, name: '预计负债综合检查', code: 'K5-7', sheetKey: '预计负债检查表K5-7', description: '10项逐项合规/不合规/不适用判断', group: 'contingency', progress: calcSheetProgress('K5-7-', 4) },
  { seq: 9, name: '附注披露信息（上市公司）', code: '附注上市', sheetKey: '附注披露信息（上市公司）', description: '预计负债+或有负债附注披露', group: 'disclosure', progress: calcSheetProgress('K5-disclosure-listed-', 5) },
  { seq: 10, name: '附注披露信息（国企）', code: '附注国企', sheetKey: '附注披露信息（国企）', description: '国企版附注披露', group: 'disclosure', progress: calcSheetProgress('K5-disclosure-soe-', 5) },
])

const coreSheets = computed(() => allSheets.value.filter(s => s.group === 'core'))
const contingencySheets = computed(() => allSheets.value.filter(s => s.group === 'contingency'))
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
.k5-tab-index { padding: 12px; font-size: var(--wp-font-size, 13px); }
.k5-progress-section { margin-bottom: 16px; padding: 14px 16px; background: #f5f7fa; border-radius: 8px; }
.progress-info { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; font-size: var(--wp-font-size, 13px); color: #606266; }
.progress-text { font-weight: 600; color: #303133; }
.progress-stats { display: flex; gap: 8px; margin-top: 10px; }
.k5-guide { background: linear-gradient(135deg, #e8f4fd 0%, #d6eaf8 100%); border: 1px solid #b3d9f2; border-radius: 8px; padding: 14px 20px; margin-bottom: 16px; }
.k5-guide-header { display: flex; align-items: center; gap: 6px; font-weight: 500; color: #1a73e8; margin-bottom: 10px; font-size: var(--wp-font-size, 13px); }
.k5-guide-steps { display: grid; grid-template-columns: repeat(2, 1fr); gap: 8px 24px; }
.step-item { display: flex; align-items: center; gap: 8px; font-size: var(--wp-font-size, 13px); color: #374151; }
.step-num { display: inline-flex; align-items: center; justify-content: center; width: 22px; height: 22px; border-radius: 50%; background: #1a73e8; color: #fff; font-size: 11px; font-weight: 600; flex-shrink: 0; }
.k5-group-card { margin-bottom: 14px; }
.k5-group-card :deep(.el-card__header) { display: flex; align-items: center; justify-content: space-between; padding: 10px 16px; }
.group-title { font-size: 14px; font-weight: 600; color: #303133; }
.group-core :deep(.el-card__header) { background: linear-gradient(90deg, #f0faf0 0%, #f8fdf8 100%); }
.group-contingency :deep(.el-card__header) { background: linear-gradient(90deg, #fff7ed 0%, #fffbf5 100%); }
.group-disclosure :deep(.el-card__header) { background: linear-gradient(90deg, #fefce8 0%, #fefdf5 100%); }
.sheet-name-link { color: #1a73e8; cursor: pointer; font-size: var(--wp-font-size, 13px); }
.sheet-name-link:hover { text-decoration: underline; }
.progress-label { display: inline-block; margin-left: 8px; font-size: 12px; color: #909399; width: 36px; }
:deep(.completed-row) { background-color: #f0f9eb !important; }
:deep(.in-progress-row) { background-color: #fdf6ec !important; }
:deep(.el-table) { font-size: var(--wp-font-size, 13px); }
:deep(.el-table .el-table__row) { cursor: pointer; }
:deep(.el-table .el-table__row:hover) { background-color: #ecf5ff !important; }
.k5-details-tip { margin-top: 12px; padding: 12px 16px; background: #fafafa; border: 1px solid #ebeef5; border-radius: 6px; font-size: var(--wp-font-size, 13px); color: #606266; }
.k5-details-tip summary { cursor: pointer; font-weight: 500; color: #303133; margin-bottom: 8px; }
.k5-details-tip ul { padding-left: 20px; margin: 8px 0 0; line-height: 1.8; }
.k5-cross-refs { display: flex; align-items: center; gap: 8px; margin-bottom: 14px; padding: 8px 12px; background: #f5f7fa; border-radius: 6px; }
.cross-refs-label { font-size: var(--wp-font-size, 13px); color: #909399; }
</style>
