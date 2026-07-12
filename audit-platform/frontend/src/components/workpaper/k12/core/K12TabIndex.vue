<template>
  <div class="k12-tab-index">
    <!-- ═══ 总体进度 ═══ -->
    <div class="k12-progress-section">
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
    <div class="k12-guide">
      <div class="k12-guide-header">
        <el-icon><InfoFilled /></el-icon>
        <span>操作步骤引导</span>
      </div>
      <div class="k12-guide-steps">
        <div class="step-item">
          <span class="step-num">①</span>
          <span class="step-text">填写明细表（K12-2）逐笔登记营业外收入明细</span>
        </div>
        <div class="step-item">
          <span class="step-num">②</span>
          <span class="step-text">填写审定表（K12-1）确认发生额 → TB回写6301</span>
        </div>
        <div class="step-item">
          <span class="step-num">③</span>
          <span class="step-text">录入调整分录（K12-3）管理AJE/RJE → 联动A13</span>
        </div>
        <div class="step-item">
          <span class="step-num">④</span>
          <span class="step-text">完成检查表（K12-4）核实分类正确性与合规性</span>
        </div>
      </div>
    </div>

    <!-- ═══ 跨底稿引用 ═══ -->
    <div class="k12-cross-refs">
      <span class="cross-refs-label">关联底稿：</span>
      <GtIndexChip value="K12A" :context-project-id="props.projectId" />
      <GtIndexChip value="K10" :context-project-id="props.projectId" />
      <GtIndexChip value="A13" :context-project-id="props.projectId" />
    </div>

    <!-- ═══ 底稿目录表 ═══ -->
    <el-card shadow="never" class="k12-group-card">
      <template #header>
        <span class="group-title">底稿目录</span>
        <el-tag size="small" type="success" effect="light">{{ completedCount }}/{{ totalCount }}</el-tag>
      </template>
      <el-table
        :data="allSheets"
        border
        size="small"
        highlight-current-row
        style="width: 100%"
        :row-class-name="getRowClassName"
        @row-click="handleRowClick"
      >
        <el-table-column prop="seq" label="序号" width="56" align="center" />
        <el-table-column prop="name" label="内容" min-width="240">
          <template #default="{ row }">
            <span class="sheet-name-link">{{ row.name }}</span>
          </template>
        </el-table-column>
        <el-table-column label="索引号" width="100" align="center">
          <template #default="{ row }">
            <GtIndexChip :value="row.code" :context-project-id="props.projectId" />
          </template>
        </el-table-column>
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

    <!-- ═══ 编制提示 ═══ -->
    <details class="compile-hint">
      <summary>📋 编制提示</summary>
      <ul>
        <li>K12为损益类科目（6301），取本期贷方发生额累计（贷方=收入增加），非期末余额</li>
        <li>营业外收入指与日常活动无关的利得：政府补助/债务重组利得/资产盘盈/罚款收入/捐赠利得等</li>
        <li>与日常活动相关的其他收益（6117）属K10底稿，注意分类正确性</li>
        <li>审定数=未审数+AJE+RJE；调整分录联动A13</li>
        <li>附注按来源分别披露营业外收入金额</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * K12TabIndex.vue — K12 营业外收入底稿目录
 *
 * Spec: .kiro/specs/k12-non-operating-income/ | Task: 4.1
 * Requirements: 1.2
 *
 * 功能：
 * - 底稿目录组件（shows 7 sheets with progress）
 * - GtIndexChip跳转每个sheet
 * - emit('navigate-sheet', sheetName) for navigation
 * - Read-only display (no editable fields)
 */
import { computed, type Ref } from 'vue'
import { defineAsyncComponent } from 'vue'
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
  seq: number
  name: string
  code: string
  sheetKey: string
  progress: number
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

// ─── 7 sheets 列表 ──────────────────────────────────────────────────────────

const allSheets = computed<SheetRow[]>(() => [
  { seq: 1, name: '实质性程序表 K12A', code: 'K12A', sheetKey: '实质性程序表 K12A', progress: calcSheetProgress('K12-K12A-', 5) },
  { seq: 2, name: '审定表 K12-1', code: 'K12-1', sheetKey: '审定表K12-1', progress: calcSheetProgress('K12-1-', 10) },
  { seq: 3, name: '附注披露信息（上市公司）', code: '附注上市', sheetKey: '附注披露信息（上市公司）', progress: calcSheetProgress('K12-disclosure-listed-', 5) },
  { seq: 4, name: '附注披露信息（国企）', code: '附注国企', sheetKey: '附注披露信息（国企）', progress: calcSheetProgress('K12-disclosure-soe-', 5) },
  { seq: 5, name: '明细表 K12-2', code: 'K12-2', sheetKey: '明细表K12-2', progress: calcSheetProgress('K12-2-', 8) },
  { seq: 6, name: '调整分录汇总 K12-3', code: 'K12-3', sheetKey: '调整分录汇总K12-3', progress: calcSheetProgress('K12-3-', 4) },
  { seq: 7, name: '营业外收入检查表 K12-4', code: 'K12-4', sheetKey: '营业外收入检查表K12-4', progress: calcSheetProgress('K12-4-', 6) },
])

// ─── 进度计算 ────────────────────────────────────────────────────────────────

const totalCount = computed(() => allSheets.value.length)
const completedCount = computed(() => allSheets.value.filter(r => r.progress >= 100).length)
const inProgressCount = computed(() => allSheets.value.filter(r => r.progress > 0 && r.progress < 100).length)
const notStartedCount = computed(() => allSheets.value.filter(r => r.progress === 0).length)
const progressPercent = computed(() => {
  if (totalCount.value === 0) return 0
  return Math.round(allSheets.value.reduce((s, r) => s + r.progress, 0) / totalCount.value)
})

// ─── 交互 ────────────────────────────────────────────────────────────────────

function handleRowClick(row: SheetRow): void {
  emit('navigate-sheet', row.sheetKey)
}

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
.k12-tab-index { padding: 12px; font-size: var(--wp-font-size, 13px); }

.k12-progress-section {
  margin-bottom: 16px;
  padding: 12px 16px;
  background: #fafafa;
  border-radius: 8px;
}
.progress-info {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
  font-size: 14px;
  font-weight: 500;
}
.progress-text { color: #606266; font-size: 12px; }
.progress-stats { display: flex; gap: 8px; margin-top: 8px; }

.k12-guide {
  margin-bottom: 16px;
  padding: 14px 18px;
  background: linear-gradient(135deg, #e8f4fd 0%, #d1ecf9 100%);
  border-radius: 8px;
  border-left: 4px solid #409eff;
}
.k12-guide-header {
  display: flex;
  align-items: center;
  gap: 6px;
  font-weight: 600;
  color: #303133;
  margin-bottom: 10px;
}
.k12-guide-steps { display: grid; grid-template-columns: 1fr 1fr; gap: 6px 16px; }
.step-item { display: flex; align-items: flex-start; gap: 6px; }
.step-num { color: #409eff; font-weight: 700; min-width: 18px; }
.step-text { color: #606266; line-height: 1.5; }

.k12-cross-refs {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
  margin-bottom: 16px;
  padding: 8px 12px;
  background: #f5f7fa;
  border-radius: 6px;
}
.cross-refs-label { color: #909399; font-size: 12px; white-space: nowrap; }

.k12-group-card { margin-bottom: 16px; }
.k12-group-card :deep(.el-card__header) {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 16px;
}
.group-title { font-weight: 600; font-size: 14px; }
.sheet-name-link { color: #409eff; cursor: pointer; }
.sheet-name-link:hover { text-decoration: underline; }
.progress-label { margin-left: 6px; font-size: 11px; color: #909399; }

:deep(.completed-row) { background-color: #f0f9eb !important; }
:deep(.in-progress-row) { background-color: #fdf6ec !important; }

.compile-hint {
  margin-top: 12px;
  padding: 10px 14px;
  background: #fafafa;
  border-radius: 6px;
  font-size: 12px;
  color: #606266;
}
.compile-hint summary {
  cursor: pointer;
  font-weight: 500;
  margin-bottom: 6px;
}
.compile-hint ul { padding-left: 20px; margin: 0; line-height: 1.8; }
</style>
