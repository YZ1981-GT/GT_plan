<template>
  <div class="i3-tab-index">
    <!-- 顶部引导区 -->
    <div class="guide-area">
      <div class="guide-grid">
        <div class="guide-step"><span class="step-num">①</span> 审定表(I3-1)确认TB取数→商誉不摊销→审定回写(1711)</div>
        <div class="guide-step"><span class="step-num">②</span> 明细表(I3-2)按被投资单位逐项→30列3区段Tab</div>
        <div class="guide-step"><span class="step-num">③</span> 入账测算(I3-4)合并成本-净资产公允=商誉</div>
        <div class="guide-step"><span class="step-num">④</span> 减值测试(I3-6)按CGU测试→先冲商誉再分摊</div>
        <div class="guide-step"><span class="step-num">⑤</span> DCF测算(I3-7)折现现金流→可收回金额→敏感性分析</div>
        <div class="guide-step"><span class="step-num">⑥</span> 附注披露(上市/国企)自动取数+AI辅助生成</div>
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
        <li>建议按序号顺序编制：程序表→审定表→明细表→调整分录→入账测算→检查→减值→DCF→复核→附注</li>
        <li>商誉核心规则：<strong>不摊销！</strong>仅年度减值测试，期末=期初+新并购-减值</li>
        <li>审定表完成后自动回写TB科目1711(商誉，资产类：期末=期初+借-贷)</li>
        <li>"本期增加"仅来自新并购（正常情况为0），非零时需特别关注</li>
        <li>"本期减少"仅来自减值，商誉减值不可转回！</li>
        <li>减值分摊规则：先冲商誉（至零为止），剩余按比例分摊至资产组其他资产</li>
        <li>I3-7 DCF可收回金额为100行×16列超大表，建议逐CGU填报</li>
        <li>附注有上市版/国企版，根据projectContext.business_category自动判断</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * I3TabIndex.vue — I3 商誉底稿目录（进度条+11行+统计摘要+交叉引用）
 * 11个sheet目录导航 + 三态状态(未编制/编制中/已复核) + 进度条 + 点击导航
 * GtIndexChip 标注跨表引用（I3-6→I3-7 DCF跳转等）
 *
 * 商誉核心特殊：不摊销！仅年度减值测试 + DCF/CGU + 先冲商誉再分摊
 *
 * Spec: .kiro/specs/i3-goodwill/ Task 4.1
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

/** 11 sheets from the I3 goodwill workpaper */
const SHEET_DEFS: { seq: number; code: string; name: string; sheetName: string; fields: string[]; crossRef?: string }[] = [
  { seq: 1, code: 'I3A', name: '商誉实质性程序表', sheetName: 'Procedure_Table_I3A 商誉实质性程序表', fields: ['I3A-'] },
  { seq: 2, code: 'I3-1', name: '审定表', sheetName: 'Adjudication_I3_1 审定表', fields: ['I3-1-', 'I3-adj-', 'I3-tb-'] },
  { seq: 3, code: 'I3-2', name: '明细表（30列）', sheetName: 'Detail_I3_2 明细表', fields: ['I3-2-'] },
  { seq: 4, code: 'I3-3', name: '调整分录汇总', sheetName: 'Adjustment_I3_3 调整分录汇总', fields: ['I3-3-'] },
  { seq: 5, code: 'I3-4', name: '入账价值测算表', sheetName: 'InitialValue_I3_4 入账价值测算表', fields: ['I3-4-'] },
  { seq: 6, code: 'I3-5', name: '针对性检查表', sheetName: 'Targeted_Check_I3_5 针对性检查表', fields: ['I3-5-'] },
  { seq: 7, code: 'I3-6', name: '商誉减值测试', sheetName: 'Impairment_Test_I3_6 商誉减值测试', fields: ['I3-6-'], crossRef: 'I3-7' },
  { seq: 8, code: 'I3-7', name: '可收回金额测试（DCF）', sheetName: 'Recoverable_Test_I3_7 可收回金额测试', fields: ['I3-7-'], crossRef: 'I3-6' },
  { seq: 9, code: 'I3-8', name: '复核公司减值测试过程', sheetName: 'Review_Process_I3_8 复核公司减值测试过程', fields: ['I3-8-'] },
  { seq: 10, code: '附注(上市)', name: '商誉附注上市版', sheetName: 'Disclosure_Listed 附注上市', fields: ['I3-disc-L-'] },
  { seq: 11, code: '附注(国企)', name: '商誉附注国企版', sheetName: 'Disclosure_SOE 附注国企', fields: ['I3-disc-S-'] },
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
.i3-tab-index { padding: 16px; font-size: 13px; }

/* 引导区 */
.guide-area {
  background: linear-gradient(135deg, #e8f4fd 0%, #d4ecfb 100%);
  border-radius: 8px; padding: 16px; margin-bottom: 16px;
}
.guide-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
.guide-step { display: flex; align-items: center; gap: 6px; font-size: 13px; }
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
.index-table { font-size: 13px; cursor: pointer; }
.sheet-link { color: var(--el-color-primary); }
.sheet-link:hover { text-decoration: underline; }
.cross-ref-chip { margin-left: 6px; }

/* 编制提示 */
.compile-hint { margin-top: 12px; font-size: 12px; color: var(--el-text-color-secondary); }
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ul { padding-left: 20px; margin-top: 8px; }
.compile-hint li { margin-bottom: 4px; }
</style>
