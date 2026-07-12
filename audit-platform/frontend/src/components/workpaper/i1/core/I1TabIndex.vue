<template>
  <div class="i1-tab-index">
    <!-- 顶部引导区 -->
    <div class="guide-area">
      <div class="guide-grid">
        <div class="guide-step"><span class="step-num">①</span> 审定表(I1)确认TB取数→三科目三角勾稽→审定回写(1701+1702+1703)</div>
        <div class="guide-step"><span class="step-num">②</span> 明细表(I1-2)逐项登记56列→4区段Tab→交叉核对审定表</div>
        <div class="guide-step"><span class="step-num">③</span> 检查表(I1-4~8)政策/增加/减少/寿命/权属逐项核验</div>
        <div class="guide-step"><span class="step-num">④</span> 摊销(I1-9~11)分配分析+分支选择器(含/不含减值)</div>
        <div class="guide-step"><span class="step-num">⑤</span> 减值(I1-12~13)减值测试+DCF可收回金额模型</div>
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
        <li>建议按序号顺序编制：审定表→明细表→调整分录→检查表→摊销→减值→附注</li>
        <li>审定表完成后自动回写TB科目1701(无形资产)/1702(累计摊销)/1703(减值准备)</li>
        <li>公式方向：1701为资产类(期末=期初+借-贷)；1702/1703为备抵类(期末=期初+贷-借)</li>
        <li>I1-10/I1-11摊销测算有2个分支(不含减值/含减值)，根据是否存在减值选择</li>
        <li>I1-5增加检查可接收I2开发支出的资本化转入联动</li>
        <li>附注有上市版/国企版，根据projectContext.business_category自动判断</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * I1TabIndex.vue — I1 无形资产底稿目录（进度条+18行+统计摘要）
 * 18个sheet目录导航 + 三态状态(未编制/编制中/已复核) + 进度条 + 点击导航
 * Spec: Task 4.1 | Requirements: 1.1-1.10
 */
import { computed } from 'vue'

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
}

/** 18 sheets from the I1 intangible assets workpaper */
const SHEET_DEFS: { seq: number; code: string; name: string; sheetName: string; fields: string[] }[] = [
  { seq: 1, code: 'Tab_Index', name: '底稿目录', sheetName: 'Tab_Index 底稿目录', fields: [] },
  { seq: 2, code: 'I1A', name: '实质性程序表', sheetName: 'Procedure_Table_I1A 实质性程序表', fields: ['I1A-'] },
  { seq: 3, code: 'I1', name: '审定表', sheetName: 'Adjudication_I1 审定表', fields: ['I1-adj-', 'I1-tb-'] },
  { seq: 4, code: 'I1-2', name: '明细表', sheetName: 'Detail_I1_2 明细表', fields: ['I1-2-'] },
  { seq: 5, code: 'I1-3', name: '调整分录', sheetName: 'Adjustment_I1_3 调整分录', fields: ['I1-3-'] },
  { seq: 6, code: 'I1-4', name: '政策检查', sheetName: 'Policy_Check_I1_4 政策检查', fields: ['I1-4-'] },
  { seq: 7, code: 'I1-5', name: '增加检查', sheetName: 'Addition_Check_I1_5 增加检查', fields: ['I1-5-'] },
  { seq: 8, code: 'I1-6', name: '减少明细', sheetName: 'Disposal_Check_I1_6 减少明细', fields: ['I1-6-'] },
  { seq: 9, code: 'I1-7', name: '使用寿命检查', sheetName: 'UsefulLife_Check_I1_7 使用寿命检查', fields: ['I1-7-'] },
  { seq: 10, code: 'I1-8', name: '权属检查', sheetName: 'Title_Check_I1_8 权属检查', fields: ['I1-8-'] },
  { seq: 11, code: 'I1-9', name: '摊销分配', sheetName: 'Amortization_Alloc_I1_9 摊销分配', fields: ['I1-9-'] },
  { seq: 12, code: 'I1-10', name: '摊销不含减值', sheetName: 'Amortization_NoImpair_I1_10 摊销不含减值', fields: ['I1-10-'] },
  { seq: 13, code: 'I1-11', name: '摊销含减值', sheetName: 'Amortization_WithImpair_I1_11 摊销含减值', fields: ['I1-11-'] },
  { seq: 14, code: 'I1-12', name: '减值测试', sheetName: 'Impairment_Test_I1_12 减值测试', fields: ['I1-12-'] },
  { seq: 15, code: 'I1-13', name: '可收回金额', sheetName: 'Recoverable_Test_I1_13 可收回金额', fields: ['I1-13-'] },
  { seq: 16, code: 'I1-disc-L', name: '附注上市', sheetName: 'Disclosure_Listed 附注上市', fields: ['I1-disc-L-'] },
  { seq: 17, code: 'I1-disc-S', name: '附注国企', sheetName: 'Disclosure_SOE 附注国企', fields: ['I1-disc-S-'] },
  { seq: 18, code: 'I1-spare', name: '备用/空白', sheetName: '备用', fields: [] },
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
.i1-tab-index { padding: 16px; font-size: var(--wp-font-size, 13px); }

/* 引导区 */
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

/* 编制提示 */
.compile-hint { margin-top: 12px; font-size: 12px; color: var(--el-text-color-secondary); }
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ul { padding-left: 20px; margin-top: 8px; }
</style>
