<template>
  <div class="i5-tab-index">
    <!-- 顶部蓝色渐变引导区 -->
    <div class="guide-area">
      <div class="guide-grid">
        <div class="guide-step"><span class="step-num">①</span> 审定表(I5-1)确认TB取数→期末=期初+增加-减少→审定回写(1911)</div>
        <div class="guide-step"><span class="step-num">②</span> 明细表(I5-2)逐项追踪→26列3区段Tab(基础|金额|检查)</div>
        <div class="guide-step"><span class="step-num">③</span> 调整分录(I5-3)AJE/RJE录入→借贷平衡→推送A13</div>
        <div class="guide-step"><span class="step-num">④</span> 针对性检查(I5-4)分类正确性/期限适当性/可回收性评估</div>
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

    <!-- 底稿目录表 -->
    <el-card shadow="never" class="index-card">
      <template #header>
        <div class="section-title">
          <span>I5 其他非流动资产（底稿目录，共 {{ sheets.length }} 个Sheet）</span>
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
        <li>建议按序号顺序编制：程序表→审定表→明细表→调整分录→针对性检查→附注</li>
        <li>科目1911其他非流动资产（借方/资产类）：期末=期初+增加-减少</li>
        <li>审定数=未审数+AJE+RJE，审定表完成后自动回写TB科目1911</li>
        <li>针对性检查：分类正确性(应否归入其他科目)/期限适当性(是否仍为非流动)/可回收性评估</li>
        <li>附注有上市版/国企版，根据projectContext.business_category自动判断</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * I5TabIndex.vue — I5 其他非流动资产底稿目录（9 sheet + 进度 + 导航）
 *
 * 列出所有9个sheet，显示完成状态，点击跳转。
 * 科目1911其他非流动资产（借方/资产类）。
 *
 * Spec: .kiro/specs/i5-other-noncurrent-assets/
 * Task: 4.1
 * Requirements: Glossary Tab_Index
 */
import { computed } from 'vue'
import GtIndexChip from '@/components/workpaper/GtIndexChip.vue'

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

/** 9 sheets from the I5 其他非流动资产 workpaper */
const SHEET_DEFS: { seq: number; code: string; name: string; sheetName: string; fields: string[]; crossRef?: string }[] = [
  { seq: 1, code: '目录', name: '其他非流动资产（底稿目录）', sheetName: 'Tab_Index 底稿目录', fields: [] },
  { seq: 2, code: 'I5A', name: '其他非流动资产实质性程序表', sheetName: 'Procedure_Table_I5A 其他非流动资产实质性程序表', fields: ['I5A-'] },
  { seq: 3, code: 'I5-1', name: '其他非流动资产审定表', sheetName: 'Adjudication_I5_1 审定表', fields: ['I5-adj-'] },
  { seq: 4, code: 'I5-2', name: '其他非流动资产明细表', sheetName: 'Detail_I5_2 明细表', fields: ['I5-2-'] },
  { seq: 5, code: 'I5-3', name: '其他非流动资产调整分录', sheetName: 'Adjustment_I5_3 调整分录汇总', fields: ['I5-3-'], crossRef: 'A13' },
  { seq: 6, code: 'I5-4', name: '其他非流动资产针对性检查', sheetName: 'Targeted_Check_I5_4 针对性检查表', fields: ['I5-4-'] },
  { seq: 7, code: '附注(上市)', name: '附注-上市公司', sheetName: 'Disclosure_Listed 附注上市', fields: ['I5-disc-L-'] },
  { seq: 8, code: '附注(国企)', name: '附注-国有企业', sheetName: 'Disclosure_SOE 附注国企', fields: ['I5-disc-S-'] },
  { seq: 9, code: 'I5-全', name: '底稿全览(OO)', sheetName: 'Full_Workbook', fields: [] },
]

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
</script>

<style scoped>
.i5-tab-index { padding: 16px; font-size: var(--wp-font-size, 13px); }

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
