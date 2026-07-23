<template>
  <div class="k11-tab-index">
    <!-- ═══ 总体进度 ═══ -->
    <div class="k11-progress-section">
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
    <div class="k11-guide">
      <div class="k11-guide-header">
        <el-icon><InfoFilled /></el-icon>
        <span>操作步骤引导</span>
      </div>
      <div class="k11-guide-steps">
        <div class="step-item">
          <span class="step-num">①</span>
          <span class="step-text">填写明细表（K11-2）登记各类资产减值损失明细并与源底稿核对</span>
        </div>
        <div class="step-item">
          <span class="step-num">②</span>
          <span class="step-text">填写审定表（K11-1）确认减值损失发生额 → TB回写6701</span>
        </div>
        <div class="step-item">
          <span class="step-num">③</span>
          <span class="step-text">录入调整分录（K11-3）管理AJE/RJE → 联动A13</span>
        </div>
        <div class="step-item">
          <span class="step-num">④</span>
          <span class="step-text">填写附注披露 → 确认减值损失披露完整性</span>
        </div>
      </div>
    </div>

    <!-- ═══ 减值来源汇总仪表板 ═══ -->
    <el-card shadow="never" class="k11-impairment-dashboard">
      <template #header>
        <span class="group-title">减值来源汇总状态</span>
        <el-tag size="small" effect="light" :type="allSourcesReconciled ? 'success' : 'warning'">
          {{ reconciledCount }}/{{ impairmentSources.length }} 已核对
        </el-tag>
      </template>
      <el-table :data="impairmentSources" border size="small" style="width: 100%">
        <el-table-column label="减值来源" min-width="160">
          <template #default="{ row }">
            <GtIndexChip :value="row.wpCode" :context-project-id="props.projectId" />
            <span style="margin-left: 6px">{{ row.label }}</span>
          </template>
        </el-table-column>
        <el-table-column label="资产类别" min-width="120" prop="category" />
        <el-table-column label="减值计提状态" width="120" align="center">
          <template #default="{ row }">
            <el-tag :type="row.status === 'done' ? 'success' : row.status === 'partial' ? 'warning' : 'info'" size="small">
              {{ row.status === 'done' ? '已编制' : row.status === 'partial' ? '编制中' : '未编制' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="核对差异" width="110" align="right">
          <template #default="{ row }">
            <span :class="{ 'diff-abnormal': row.diff !== 0 }">{{ fmtAmt(row.diff) }}</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- ═══ 跨底稿引用 ═══ -->
    <div class="k11-cross-refs">
      <span class="cross-refs-label">关联底稿：</span>
      <GtIndexChip value="K11A" :context-project-id="props.projectId" />
      <GtIndexChip value="F2" :context-project-id="props.projectId" />
      <GtIndexChip value="H1" :context-project-id="props.projectId" />
      <GtIndexChip value="I1" :context-project-id="props.projectId" />
      <GtIndexChip value="I3" :context-project-id="props.projectId" />
      <GtIndexChip value="A13" :context-project-id="props.projectId" />
    </div>

    <!-- ═══ 底稿架构与编制流程（4阶段泳道，对齐D4范式） ═══ -->
    <el-card shadow="never" class="k11-arch-card">
      <template #header>
        <span class="group-title">底稿架构与编制流程</span>
        <el-tag size="small" type="primary" effect="light">{{ completedCount }}/{{ totalCount }}</el-tag>
      </template>
      <GtBArchitectureTree
        :html-data="{ navigation_rows: navigationRows }"
        :active-sheet="''"
        :project-id="props.projectId"
        @navigate="(s: string) => emit('navigate-sheet', s)"
      />
    </el-card>

    <!-- ═══ 编制提示 ═══ -->
    <details class="compile-hint">
      <summary>📋 编制提示</summary>
      <ul>
        <li>K11为损益类科目（6701），取本期发生额（借方=减值增加），非期末余额</li>
        <li>各类资产减值损失需与源底稿（F2存货/H1固定资产/I1无形资产/I3商誉）交叉核对</li>
        <li>商誉减值损失一经确认不得转回（CAS8）</li>
        <li>附注按资产类别分别披露减值损失金额</li>
        <li>调整分录回写K11-1审定表 + 发布adjustment:created → A13</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * K11TabIndex.vue — 底稿目录（含减值来源汇总状态）
 *
 * Spec: .kiro/specs/k11-asset-impairment-loss/ | Task: 4.1
 * Requirements: 1.2
 *
 * 功能：
 * - 底稿目录组件（shows sheet list with completion status）
 * - 减值来源汇总仪表板（展示各来源底稿F2/H1/I1/I3等的减值计提状态）
 * - GtIndexChip跳转每个sheet
 * - el-card包裹每个section
 * - emit('navigate-sheet', sheetName) for navigation
 */
import { computed, type Ref } from 'vue'
import { defineAsyncComponent } from 'vue'
import { InfoFilled } from '@element-plus/icons-vue'

const GtIndexChip = defineAsyncComponent(() => import('../../GtIndexChip.vue'))
const GtBArchitectureTree = defineAsyncComponent(() => import('../../GtBArchitectureTree.vue'))

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
  description: string
  group: 'core' | 'disclosure'
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
  // ─── 核心组 ───
  { seq: 1, name: '实质性程序表', code: 'K11A', sheetKey: '实质性程序表 K11A', description: '资产减值损失实质性程序清单与执行情况', group: 'core', progress: calcSheetProgress('K11-K11A-', 5) },
  { seq: 2, name: '审定表', code: 'K11-1', sheetKey: '审定表K11-1', description: '损益类6701审定（发生额！37行12列）+TB回写', group: 'core', progress: calcSheetProgress('K11-1-', 10) },
  { seq: 3, name: '明细表', code: 'K11-2', sheetKey: '明细表K11-2', description: '18列2区段+按资产类别减值明细+50行', group: 'core', progress: calcSheetProgress('K11-2-', 8) },
  { seq: 4, name: '调整分录汇总', code: 'K11-3', sheetKey: '调整分录汇总K11-3', description: 'AJE/RJE管理（借贷平衡）→联动A13', group: 'core', progress: calcSheetProgress('K11-3-', 4) },
  // ─── 附注组 ───
  { seq: 5, name: '附注披露信息（上市公司）', code: '附注上市', sheetKey: '附注披露信息（上市公司）', description: '按资产类别披露减值损失（项目/本期/上期发生额，18项 canonical）', group: 'disclosure', progress: calcSheetProgress('K11-disclosure-listed-', 5) },
  { seq: 6, name: '附注披露信息（国企）', code: '附注国企', sheetKey: '附注披露信息（国企）', description: '国企版减值损失附注披露（项目/本期/上期发生额，18项 canonical）', group: 'disclosure', progress: calcSheetProgress('K11-disclosure-soe-', 5) },
  { seq: 7, name: '底稿目录', code: 'K11', sheetKey: '底稿目录', description: '当前页面（底稿目录+减值来源汇总）', group: 'core', progress: 100 },
])

// ─── GtBArchitectureTree navigation_rows（4阶段泳道数据源） ───────────────────
const CT_BY_CODE: Record<string, string> = {
  'K11A': 'a-program-console',
  'K11-1': 'd-form-table',
  'K11-2': 'd-form-table',
  'K11-3': 'd-form-table',
  '附注上市': 'c-note-table',
  '附注国企': 'c-note-table',
}
const navigationRows = computed(() =>
  allSheets.value
    .filter(s => s.code !== 'K11') // 排除底稿目录（当前页）
    .map(s => ({
      content: s.sheetKey,
      index_ref: s.code,
      component_type: CT_BY_CODE[s.code] || 'd-form-table',
      status: s.progress >= 100 ? 'completed' : s.progress > 0 ? 'in_progress' : 'pending',
    })),
)

// ─── 进度计算 ────────────────────────────────────────────────────────────────

const totalCount = computed(() => allSheets.value.length)
const completedCount = computed(() => allSheets.value.filter(r => r.progress >= 100).length)
const inProgressCount = computed(() => allSheets.value.filter(r => r.progress > 0 && r.progress < 100).length)
const notStartedCount = computed(() => allSheets.value.filter(r => r.progress === 0).length)
const progressPercent = computed(() => {
  if (totalCount.value === 0) return 0
  return Math.round(allSheets.value.reduce((s, r) => s + r.progress, 0) / totalCount.value)
})

// ─── 减值来源汇总仪表板 ─────────────────────────────────────────────────────

interface ImpairmentSource {
  wpCode: string
  label: string
  category: string
  status: 'done' | 'partial' | 'not_started'
  diff: number
}

/** 兜底硬编码来源（K11-1 尚无数据时展示） */
const FALLBACK_SOURCES: Array<{ wpCode: string; label: string; category: string }> = [
  { wpCode: 'F2', label: '存货跌价准备', category: '存货' },
  { wpCode: 'H1', label: '固定资产减值', category: '固定资产' },
  { wpCode: 'I1', label: '无形资产减值', category: '无形资产' },
  { wpCode: 'I3', label: '商誉减值', category: '商誉' },
  { wpCode: 'H2', label: '在建工程减值', category: '在建工程' },
  { wpCode: 'G7', label: '长期股权投资减值', category: '长期股权投资' },
]

/**
 * 减值来源仪表板 —— 优先从 K11-1 审定表行动态派生（对齐 18 类 canonical）。
 * 取有 sourceWp 的行，按 sourceWp 去重（同一来源底稿汇总一行）；
 * K11-1 尚无数据时回退硬编码 6 源。
 */
const impairmentSources = computed<ImpairmentSource[]>(() => {
  const responses = getResponses()
  const item = responses.get('K11-1-rows')
  const raw = item?.remark ?? item?.conclusion
  let derived: Array<{ wpCode: string; label: string; category: string }> = []
  if (raw) {
    try {
      const arr = typeof raw === 'string' ? JSON.parse(raw) : raw
      if (Array.isArray(arr)) {
        const seen = new Set<string>()
        for (const r of arr) {
          const code = String(r?.sourceWp || '').trim()
          if (!code || seen.has(code)) continue
          seen.add(code)
          const name = String(r?.projectName || code)
          derived.push({ wpCode: code, label: name, category: name.replace(/减值损失$/, '') })
        }
      }
    } catch { /* fallthrough to fallback */ }
  }
  const list = derived.length > 0 ? derived : FALLBACK_SOURCES
  return list.map(s => ({
    wpCode: s.wpCode,
    label: s.label,
    category: s.category,
    status: getSourceStatus(responses, s.wpCode),
    diff: getSourceDiff(responses, s.wpCode),
  }))
})

const reconciledCount = computed(() => impairmentSources.value.filter(s => s.status === 'done' && s.diff === 0).length)
const allSourcesReconciled = computed(() => reconciledCount.value === impairmentSources.value.length)

function getSourceStatus(responses: Map<string, any>, code: string): 'done' | 'partial' | 'not_started' {
  const key = `K11-source-${code}-status`
  const val = responses.get(key)?.remark ?? responses.get(key)?.value
  if (val === 'done') return 'done'
  if (val === 'partial') return 'partial'
  // 如果审定表有该来源行数据，视为编制中
  const amountKey = `K11-1-source-${code}-amount`
  if (responses.has(amountKey)) return 'partial'
  return 'not_started'
}

function getSourceDiff(responses: Map<string, any>, code: string): number {
  // P2 修复：原读从不写入的 `K11-source-{code}-diff` 键 → 核对差异恒 0。
  // 改从 K11-2 明细行按来源底稿计算：Σ(本期发生额 − 源底稿计提金额)。
  const item = responses.get('K11-2-detail-rows')
  const raw = item?.remark ?? item?.conclusion
  if (!raw) return 0
  try {
    const detailRows = typeof raw === 'string' ? JSON.parse(raw) : raw
    if (!Array.isArray(detailRows)) return 0
    let diff = 0
    for (const r of detailRows) {
      if (String(r?.sourceWp || '') !== code) continue
      const occ = Number(
        r?.currentOccurrence ?? ((Number(r?.currentProvision) || 0) - (Number(r?.currentReversal) || 0)),
      )
      diff += occ - (Number(r?.sourceAmount) || 0)
    }
    return diff
  } catch {
    return 0
  }
}

// ─── 交互 ────────────────────────────────────────────────────────────────────

function fmtAmt(v: number | null | undefined): string {
  if (v == null || v === 0) return '-'
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.k11-tab-index { padding: 12px; font-size: var(--wp-font-size, 13px); }

.k11-progress-section {
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

.k11-guide {
  margin-bottom: 16px;
  padding: 14px 18px;
  background: linear-gradient(135deg, #e8f4fd 0%, #d1ecf9 100%);
  border-radius: 8px;
  border-left: 4px solid #409eff;
}
.k11-guide-header {
  display: flex;
  align-items: center;
  gap: 6px;
  font-weight: 600;
  color: #303133;
  margin-bottom: 10px;
}
.k11-guide-steps { display: grid; grid-template-columns: 1fr 1fr; gap: 6px 16px; }
.step-item { display: flex; align-items: flex-start; gap: 6px; }
.step-num { color: #409eff; font-weight: 700; min-width: 18px; }
.step-text { color: #606266; line-height: 1.5; }

.k11-impairment-dashboard { margin-bottom: 16px; }
.diff-abnormal { color: #f56c6c; font-weight: 600; }

.k11-cross-refs {
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

.k11-group-card { margin-bottom: 16px; }
.k11-group-card :deep(.el-card__header) {
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
