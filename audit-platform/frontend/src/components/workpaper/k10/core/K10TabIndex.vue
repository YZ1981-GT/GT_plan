<template>
  <div class="k10-tab-index">
    <!-- ═══ 总体进度 ═══ -->
    <div class="k10-progress-section">
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
    <div class="k10-guide">
      <div class="k10-guide-header">
        <el-icon><InfoFilled /></el-icon>
        <span>操作步骤引导</span>
      </div>
      <div class="k10-guide-steps">
        <div class="step-item">
          <span class="step-num">①</span>
          <span class="step-text">填写明细表（K10-2）逐笔登记其他收益补助项目明细</span>
        </div>
        <div class="step-item">
          <span class="step-num">②</span>
          <span class="step-text">填写审定表（K10-1）确认发生额 → TB回写6117</span>
        </div>
        <div class="step-item">
          <span class="step-num">③</span>
          <span class="step-text">录入调整分录（K10-3）管理AJE/RJE → 联动A13</span>
        </div>
        <div class="step-item">
          <span class="step-num">④</span>
          <span class="step-text">完成政府补助核对（K10-4）与K7递延收益分摊一致性校验</span>
        </div>
        <div class="step-item">
          <span class="step-num">⑤</span>
          <span class="step-text">完成应收补助检查（K10-5）确认收款权利及确认时点</span>
        </div>
        <div class="step-item">
          <span class="step-num">⑥</span>
          <span class="step-text">完成综合检查（K10-6）核实分类正确性与合规性</span>
        </div>
      </div>
    </div>

    <!-- ═══ 跨底稿引用 ═══ -->
    <div class="k10-cross-refs">
      <span class="cross-refs-label">关联底稿：</span>
      <GtIndexChip value="K10A" :context-project-id="props.projectId" />
      <GtIndexChip value="K7" :context-project-id="props.projectId" />
      <GtIndexChip value="A13" :context-project-id="props.projectId" />
      <GtIndexChip value="TB" :context-project-id="props.projectId" />
    </div>

    <!-- ═══ 底稿目录表 ═══ -->
    <el-card shadow="never" class="k10-group-card">
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
        <el-table-column prop="name" label="内容" min-width="260">
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
        <li>K10为损益类科目（6117其他收益），取本期贷方发生额累计（贷方=收益增加），非期末余额</li>
        <li>其他收益指与日常活动相关的政府补助（即征即退/财政贴息/研发补助/稳岗补贴等）</li>
        <li>与日常活动无关的政府补助计入营业外收入（6301），属K12底稿</li>
        <li>政府补助核对（K10-4）：直接计入+递延分摊 → 与K7递延收益(2401)本期分摊一致性校验</li>
        <li>审定数=未审数+AJE+RJE；调整分录联动A13</li>
        <li>附注按补助类型分别披露其他收益金额</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * K10TabIndex.vue — K10 其他收益底稿目录
 *
 * Spec: .kiro/specs/k10-other-income/ | Task: 4.1
 * Requirements: 1.2
 *
 * 功能：
 * - 底稿目录组件（shows 10 sheets with progress）
 * - GtIndexChip跳转每个sheet
 * - emit('navigate-sheet', sheetName) for navigation
 * - 蓝色渐变引导区（6步骤）
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

// ─── 10 sheets 列表 ──────────────────────────────────────────────────────────

const allSheets = computed<SheetRow[]>(() => [
  { seq: 1, name: '底稿目录', code: 'K10', sheetKey: '底稿目录', progress: 100 },
  { seq: 2, name: '实质性程序表 K10A', code: 'K10A', sheetKey: 'K10A(程序表)', progress: calcSheetProgress('K10-K10A-', 5) },
  { seq: 3, name: '审定表 K10-1', code: 'K10-1', sheetKey: 'K10-1(审定表)', progress: calcSheetProgress('K10-1-', 10) },
  { seq: 4, name: '明细表 K10-2', code: 'K10-2', sheetKey: 'K10-2(明细表)', progress: calcSheetProgress('K10-2-', 8) },
  { seq: 5, name: '调整分录汇总 K10-3', code: 'K10-3', sheetKey: 'K10-3(调整分录)', progress: calcSheetProgress('K10-3-', 4) },
  { seq: 6, name: '政府补助核对表 K10-4', code: 'K10-4', sheetKey: 'K10-4(政府补助核对)', progress: calcSheetProgress('K10-4-', 6) },
  { seq: 7, name: '应收政府补助检查表 K10-5', code: 'K10-5', sheetKey: 'K10-5(应收补助检查)', progress: calcSheetProgress('K10-5-', 5) },
  { seq: 8, name: '其他收益检查表 K10-6', code: 'K10-6', sheetKey: 'K10-6(其他收益检查)', progress: calcSheetProgress('K10-6-', 6) },
  { seq: 9, name: '附注披露信息（上市公司）', code: '附注上市', sheetKey: '附注(上市)', progress: calcSheetProgress('K10-disclosure-listed-', 5) },
  { seq: 10, name: '附注披露信息（国企）', code: '附注国企', sheetKey: '附注(国企)', progress: calcSheetProgress('K10-disclosure-soe-', 5) },
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
.k10-tab-index { padding: 12px; font-size: var(--wp-font-size, 13px); }

.k10-progress-section {
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

.k10-guide {
  margin-bottom: 16px;
  padding: 14px 18px;
  background: linear-gradient(135deg, #e8f4fd 0%, #d1ecf9 100%);
  border-radius: 8px;
  border-left: 4px solid #409eff;
}
.k10-guide-header {
  display: flex;
  align-items: center;
  gap: 6px;
  font-weight: 600;
  color: #303133;
  margin-bottom: 10px;
}
.k10-guide-steps { display: grid; grid-template-columns: 1fr 1fr; gap: 6px 16px; }
.step-item { display: flex; align-items: flex-start; gap: 6px; }
.step-num { color: #409eff; font-weight: 700; min-width: 18px; }
.step-text { color: #606266; line-height: 1.5; }

.k10-cross-refs {
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

.k10-group-card { margin-bottom: 16px; }
.k10-group-card :deep(.el-card__header) {
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
