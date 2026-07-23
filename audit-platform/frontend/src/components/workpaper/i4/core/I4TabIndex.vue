<template>
  <div class="i4-tab-index">
    <!-- 顶部蓝色渐变引导区（建议顺序与编制校验一致） -->
    <div class="guide-area">
      <div class="guide-grid">
        <div class="guide-step"><span class="step-num">①</span> 明细表(I4-2)滚转编制→未审/调整/审定→摊销与基础信息</div>
        <div class="guide-step"><span class="step-num">②</span> 审定表(I4-1)自明细带入→三角勾稽→TB回写(1801)</div>
        <div class="guide-step"><span class="step-num">③</span> 调整分录(I4-3)AJE/RJE录入→借贷平衡→推送A13</div>
        <div class="guide-step"><span class="step-num">④</span> 摊销政策检查(I4-4)表A/B/C + CAS + 同业/租赁交叉</div>
        <div class="guide-step"><span class="step-num">⑤</span> 针对性检查(I4-5)抽凭核对1~5 + 覆盖率闸门 + 与I4-4交叉</div>
        <div class="guide-step"><span class="step-num">⑥</span> 摊销测算(I4-6/I4-7)二选一：直线法 vs 工作量法 → 回写审定</div>
      </div>
    </div>

    <!-- 统计摘要卡片 -->
    <div class="stats-summary">
      <div class="stat-item stat-completed">
        <span class="stat-value">{{ stats.completed }}</span>
        <span class="stat-label">已复核</span>
      </div>
      <div class="stat-item stat-inprogress">
        <span class="stat-value">{{ stats.inProgress }}</span>
        <span class="stat-label">编制中</span>
      </div>
      <div class="stat-item stat-pending">
        <span class="stat-value">{{ stats.pending }}</span>
        <span class="stat-label">未编制</span>
      </div>
      <div class="stat-item stat-total">
        <span class="stat-value">{{ completionPct }}%</span>
        <span class="stat-label">总进度</span>
      </div>
    </div>

    <!-- 编制校验汇总 -->
    <el-card v-if="prepIssues.length" shadow="never" class="prep-card">
      <template #header>
        <div class="section-title">
          <span>编制校验汇总</span>
          <el-tag size="small" :type="prepErrorCount ? 'danger' : 'warning'">
            {{ prepIssues.length }} 项待处理
          </el-tag>
        </div>
      </template>
      <p class="prep-order">建议顺序：I4-2 → I4-1 带入 → I4-3 → I4-4 → I4-5 → I4-6/7 → 附注</p>
      <ul class="prep-list">
        <li v-for="(issue, idx) in prepIssues" :key="idx">
          <el-tag
            size="small"
            :type="issue.level === 'error' ? 'danger' : 'warning'"
            class="prep-code"
            @click="handleNavigateByCode(issue.code)"
          >{{ issue.code }}</el-tag>
          {{ issue.message }}
        </li>
      </ul>
    </el-card>
    <el-alert
      v-else
      type="success"
      :closable="false"
      show-icon
      title="编制校验：暂无跨表阻断/告警项"
      class="prep-ok"
    />

    <!-- 底稿目录表 -->
    <el-card shadow="never" class="index-card">
      <template #header>
        <div class="section-title">
          <span>底稿目录（共 {{ sheets.length }} 个Sheet）</span>
          <span class="completion-text">完成度 {{ stats.completed + stats.inProgress }}/{{ sheets.length }}</span>
        </div>
      </template>
      <el-progress :percentage="completionPct" :stroke-width="8" class="completion-bar" />
      <el-table :data="sheets" stripe size="small" class="index-table" @row-click="handleNavigate">
        <el-table-column prop="seq" label="序号" width="50" align="center" />
        <el-table-column prop="code" label="底稿编码" width="100" />
        <el-table-column prop="name" label="名称" min-width="200">
          <template #default="{ row }">
            <span class="sheet-link">{{ row.name }}</span>
            <GtIndexChip v-if="row.crossRef" :value="row.crossRef" class="cross-ref-chip" />
          </template>
        </el-table-column>
        <el-table-column label="状态" width="90" align="center">
          <template #default="{ row }">
            <el-tag :type="statusTagType(row.status)" size="small">
              {{ row.status }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="进度" width="140" align="center">
          <template #default="{ row }">
            <el-progress
              :percentage="row.progress"
              :stroke-width="6"
              :color="progressColor(row.progress)"
              :show-text="true"
              :text-inside="false"
            />
          </template>
        </el-table-column>
        <el-table-column label="操作" width="80" align="center">
          <template #default="{ row }">
            <el-button type="primary" link size="small" @click.stop="handleNavigate(row)">
              进入
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 编制提示 -->
    <details class="compile-hint">
      <summary>编制提示</summary>
      <ul>
        <li>建议顺序：程序表 → I4-2 明细 → I4-1 审定带入 → I4-3 调整 → I4-4 政策 → I4-5 抽凭 → I4-6/7 测算 → 附注</li>
        <li>科目1801长期待摊费用（借方/资产类）：期末=期初+增−摊−减</li>
        <li>I4-2 为滚转明细（未审滚动 | 调整与审定 | 摊销信息 | 基础信息），非旧版 25 列分区</li>
        <li>审定表完成后可回写 TB 科目 1801</li>
        <li>摊销测算 I4-6/I4-7 二选一；两表同时有数据时目录会告警并以 I4-6 为准</li>
        <li>附注有上市版/国企版，根据 projectContext.business_category 判断</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * I4TabIndex.vue — I4 长期待摊费用底稿目录（12 sheet + 进度 + 导航）
 *
 * 列出所有12个sheet，显示完成状态，点击跳转。
 * 科目1801长期待摊费用（借方/资产类）。
 *
 * Spec（归档）: .kiro/specs/_archive/05-business-features/i4-long-term-prepaid/
 * Task: 4.1
 * Requirements: Glossary Tab_Index
 */
import { computed } from 'vue'
import GtIndexChip from '@/components/workpaper/GtIndexChip.vue'
import { buildI4ConsistencyDashboard } from '../../composables/i4ConsistencyModel'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const emit = defineEmits<{
  (e: 'navigate-sheet', sheetName: string): void
}>()

type SheetStatus = '未编制' | '编制中' | '已复核'

interface SheetEntry {
  seq: number
  code: string
  name: string
  status: SheetStatus
  progress: number
  sheetName: string
  crossRef?: string
}

/** 12 sheets from the I4 长期待摊费用 workpaper */
const SHEET_DEFS: { seq: number; code: string; name: string; sheetName: string; fields: string[]; crossRef?: string }[] = [
  { seq: 1, code: 'I4A', name: '长期待摊费用实质性程序表', sheetName: 'Procedure_Table_I4A 长期待摊费用实质性程序表', fields: ['I4A-'] },
  { seq: 2, code: 'I4-1', name: '审定表', sheetName: 'Adjudication_I4_1 审定表', fields: ['I4-adj-'] },
  { seq: 3, code: 'I4-2', name: '明细表（滚转四区段）', sheetName: 'Detail_I4_2 明细表', fields: ['I4-2-'] },
  { seq: 4, code: 'I4-3', name: '调整分录汇总', sheetName: 'Adjustment_I4_3 调整分录汇总', fields: ['I4-3-'], crossRef: 'A13' },
  { seq: 5, code: 'I4-4', name: '摊销政策检查表（表A/B/C）', sheetName: 'Policy_Check_I4_4 摊销政策检查表', fields: ['I4-4-'] },
  { seq: 6, code: 'I4-5', name: '针对性检查表（抽凭）', sheetName: 'Targeted_Check_I4_5 针对性检查表', fields: ['I4-5-'] },
  { seq: 7, code: 'I4-6', name: '摊销测算-直线法', sheetName: 'Amortization_Straight_I4_6 摊销测算直线法', fields: ['I4-6-'], crossRef: 'I4-7' },
  { seq: 8, code: 'I4-7', name: '摊销测算-工作量法', sheetName: 'Amortization_Units_I4_7 摊销测算工作量法', fields: ['I4-7-'], crossRef: 'I4-6' },
  { seq: 9, code: '附注(上市)', name: '附注上市公司版', sheetName: 'Disclosure_Listed 附注上市', fields: ['I4-disc-L-', 'I4-disc-listed-'] },
  { seq: 10, code: '附注(国企)', name: '附注国企版', sheetName: 'Disclosure_SOE 附注国企', fields: ['I4-disc-S-', 'I4-disc-soe-'] },
  { seq: 11, code: '目录', name: '底稿目录', sheetName: 'Tab_Index 底稿目录', fields: [] },
  { seq: 12, code: 'I4-全', name: '底稿全览(OO)', sheetName: 'Full_Workbook', fields: [] },
]

const consistency = computed(() => buildI4ConsistencyDashboard(props.allResponses))
const prepIssues = computed(() => consistency.value.issues)
const prepErrorCount = computed(() => consistency.value.errorCount)

/** Determine per-sheet status from checklist_responses */
function _getSheetStatus(fields: string[]): { status: SheetStatus; progress: number } {
  if (fields.length === 0) return { status: '未编制', progress: 0 }

  let totalFields = 0
  let filledFields = 0
  let hasReview = false

  for (const [key, value] of props.allResponses) {
    for (const prefix of fields) {
      if (key.startsWith(prefix)) {
        totalFields++
        if (value !== null && value !== undefined && value !== '') {
          filledFields++
        }
        if (key.includes('-review') && value) {
          hasReview = true
        }
      }
    }
  }

  if (totalFields === 0) return { status: '未编制', progress: 0 }

  const progress = Math.round((filledFields / totalFields) * 100)

  if (hasReview && progress >= 90) return { status: '已复核', progress: 100 }
  if (filledFields > 0) return { status: '编制中', progress }
  return { status: '未编制', progress: 0 }
}

const sheets = computed<SheetEntry[]>(() => {
  return SHEET_DEFS.map((def) => {
    const { status, progress } = _getSheetStatus(def.fields)
    return {
      seq: def.seq,
      code: def.code,
      name: def.name,
      status,
      progress,
      sheetName: def.sheetName,
      crossRef: def.crossRef,
    }
  })
})

const stats = computed(() => {
  const list = sheets.value
  return {
    completed: list.filter((s) => s.status === '已复核').length,
    inProgress: list.filter((s) => s.status === '编制中').length,
    pending: list.filter((s) => s.status === '未编制').length,
  }
})

const completionPct = computed(() => {
  const total = sheets.value.length
  if (total === 0) return 0
  const progressSum = sheets.value.reduce((sum, s) => sum + s.progress, 0)
  return Math.round(progressSum / total)
})

function statusTagType(status: SheetStatus): 'success' | 'warning' | 'info' {
  switch (status) {
    case '已复核': return 'success'
    case '编制中': return 'warning'
    case '未编制': return 'info'
  }
}

function progressColor(pct: number): string {
  if (pct >= 90) return '#67c23a'
  if (pct >= 50) return '#e6a23c'
  return '#909399'
}

function handleNavigate(row: SheetEntry) {
  emit('navigate-sheet', row.sheetName)
}

function handleNavigateByCode(code: string) {
  const found = sheets.value.find((s) => s.code === code || s.code.startsWith(code) || s.name.includes(code))
  if (found) emit('navigate-sheet', found.sheetName)
  else if (code.includes('附注')) emit('navigate-sheet', 'Disclosure_Listed 附注上市')
  else emit('navigate-sheet', code)
}
</script>

<style scoped>
.i4-tab-index { padding: 16px; font-size: var(--wp-font-size, 13px); }

/* 蓝色渐变引导区 */
.guide-area {
  background: linear-gradient(135deg, #e8f4fd 0%, #d4ecfb 100%);
  border-radius: 8px; padding: 16px; margin-bottom: 16px;
}
.guide-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
.guide-step { display: flex; align-items: center; gap: 6px; font-size: var(--wp-font-size, 13px); }
.step-num { font-weight: 700; color: var(--el-color-primary); min-width: 20px; }

/* 统计摘要 */
.stats-summary {
  display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px;
  margin-bottom: 16px;
}
.stat-item {
  display: flex; flex-direction: column; align-items: center;
  padding: 12px 8px; border-radius: 8px; background: #f5f7fa;
}
.stat-value { font-size: 24px; font-weight: 700; line-height: 1.2; }
.stat-label { font-size: 12px; color: var(--el-text-color-secondary); margin-top: 4px; }
.stat-completed .stat-value { color: #67c23a; }
.stat-inprogress .stat-value { color: #e6a23c; }
.stat-pending .stat-value { color: #909399; }
.stat-total .stat-value { color: var(--el-color-primary); }

/* 编制校验 */
.prep-card { margin-bottom: 16px; }
.prep-ok { margin-bottom: 16px; }
.prep-order { margin: 0 0 8px; font-size: 12px; color: var(--el-text-color-secondary); }
.prep-list { margin: 0; padding-left: 4px; list-style: none; line-height: 1.9; }
.prep-code { margin-right: 8px; cursor: pointer; }

/* 目录卡片 */
.section-title { display: flex; align-items: center; justify-content: space-between; }
.completion-text { font-size: 12px; color: var(--el-text-color-secondary); }
.completion-bar { margin-bottom: 12px; }
.index-card { margin-bottom: 16px; }
.index-table { font-size: var(--wp-font-size, 13px); cursor: pointer; }
.sheet-link { color: var(--el-color-primary); }
.sheet-link:hover { text-decoration: underline; }
.cross-ref-chip { margin-left: 6px; }

/* 编制提示 */
.compile-hint { margin-top: 12px; font-size: 12px; color: var(--el-text-color-secondary); }
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ul { padding-left: 20px; margin-top: 8px; }
.compile-hint li { margin-bottom: 4px; }
</style>
