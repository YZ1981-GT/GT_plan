<template>
  <div class="i2-tab-index">
    <!-- 顶部引导区 -->
    <div class="guide-area">
      <div class="guide-grid">
        <div class="guide-step"><span class="step-num">①</span> 审定表(I2-1)确认TB取数→期末=期初+借-贷(1717)→审定回写</div>
        <div class="guide-step"><span class="step-num">②</span> 明细表(I2-2)61列4区段→按项目追踪资本化金额</div>
        <div class="guide-step"><span class="step-num">③</span> CAS6五条件(I2-6)逐项目资本化时点判断（核心！）</div>
        <div class="guide-step"><span class="step-num">④</span> 检查表(I2-8~12)材料/人员/工时/委外/针对性逐项核验</div>
        <div class="guide-step"><span class="step-num">⑤</span> 截止测试(I2-13/14)双向截止→期末±5天跨期检查</div>
        <div class="guide-step"><span class="step-num">⑥</span> I6↔I2双向联动：费用化+资本化=研发总额校验</div>
      </div>
    </div>

    <!-- 统计摘要卡片 -->
    <div class="stats-summary">
      <div class="stat-item stat-completed">
        <span class="stat-value">{{ stats.completed }}</span>
        <span class="stat-label">已完成</span>
      </div>
      <div class="stat-item stat-inprogress">
        <span class="stat-value">{{ stats.inProgress }}</span>
        <span class="stat-label">进行中</span>
      </div>
      <div class="stat-item stat-pending">
        <span class="stat-value">{{ stats.pending }}</span>
        <span class="stat-label">未开始</span>
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
          <span>底稿目录（共 {{ sheetCount }} 个Sheet）</span>
          <span class="completion-text">完成度 {{ stats.completed }}/{{ sheetCount }}</span>
        </div>
      </template>
      <el-progress :percentage="completionPct" :stroke-width="8" class="completion-bar" />

      <!-- 按分组渲染 -->
      <div v-for="group in groupedSheets" :key="group.label" class="sheet-group">
        <div class="group-header" :style="{ borderLeftColor: group.color }">
          {{ group.label }}（{{ group.items.length }}）
        </div>
        <el-table :data="group.items" stripe size="small" class="index-table" @row-click="handleNavigate">
          <el-table-column prop="seq" label="#" width="42" align="center" />
          <el-table-column prop="code" label="编码" width="80" />
          <el-table-column prop="name" label="名称" min-width="220">
            <template #default="{ row }">
              <span class="sheet-link">{{ row.name }}</span>
              <span v-if="row.tag" class="sheet-tag">{{ row.tag }}</span>
            </template>
          </el-table-column>
          <el-table-column label="状态" width="80" align="center">
            <template #default="{ row }">
              <el-tag :type="statusTagType(row.status)" size="small">{{ row.status }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="进度" width="130" align="center">
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
          <el-table-column label="" width="60" align="center">
            <template #default="{ row }">
              <el-button type="primary" link size="small" @click.stop="handleNavigate(row)">进入</el-button>
            </template>
          </el-table-column>
        </el-table>
      </div>
    </el-card>

    <!-- 编制提示 -->
    <details class="compile-hint">
      <summary>编制提示</summary>
      <ul>
        <li>建议编制顺序：审定表→明细表→CAS6五条件→检查表→截止测试→减值→附注</li>
        <li>审定表完成后自动回写TB科目1717(开发支出)，资产类期末=期初+借方-贷方</li>
        <li>I2-6 CAS6五条件是审计重点：①技术可行性②完成意图③使用或出售能力④未来经济利益⑤资源充足</li>
        <li>I6↔I2双向联动：研发费用(I6费用化)+开发支出(I2资本化)=研发总额</li>
        <li>I2审定表"本期减少-转无形资产"列联动I1增加检查</li>
        <li>I2-7研发项目构成73列拆为5区段Tab(基础/材料/人工/折旧摊销/其他)</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * I2TabIndex.vue — I2 开发支出底稿目录
 * 21个sheet目录导航 + 5分组(核心/检查/截止/减值/附注) + 三态状态 + 进度条
 * Spec: Task 4.1 | Requirements: 1.1-1.10
 */
import { computed } from 'vue'

const props = defineProps<{
  sheetName: string
  wpId: string
  projectId: string
  allResponses?: Map<string, any>
}>()

const emit = defineEmits<{
  (e: 'navigate-sheet', sheetName: string): void
}>()

type SheetStatus = '未开始' | '进行中' | '已完成'

interface SheetDef {
  seq: number; code: string; name: string; tag?: string
  sheetName: string; group: string; fields: string[]
}
type SheetEntry = SheetDef & { status: SheetStatus; progress: number }

const SHEET_DEFS: SheetDef[] = [
  // 核心组
  { seq: 1, code: 'Tab_Index', name: '底稿目录', sheetName: 'Tab_Index 底稿目录', group: '核心', fields: [] },
  { seq: 2, code: 'I2A', name: '开发支出实质性程序表', sheetName: 'Procedure_Table_I2A 实质性程序表', group: '核心', fields: ['I2A-'] },
  { seq: 3, code: 'I2-1', name: '审定表', tag: '61公式', sheetName: 'Adjudication_I2_1 审定表', group: '核心', fields: ['I2-1-'] },
  { seq: 4, code: 'I2-2', name: '明细表', tag: '61列', sheetName: 'Detail_I2_2 明细表', group: '核心', fields: ['I2-2-'] },
  { seq: 5, code: 'I2-3', name: '调整分录汇总', sheetName: 'Adjustment_I2_3 调整分录', group: '核心', fields: ['I2-3-'] },
  { seq: 6, code: 'I2-5', name: '实质性分析', tag: '31公式', sheetName: 'Analysis_I2_5 实质性分析', group: '核心', fields: ['I2-5-'] },
  // 检查组
  { seq: 7, code: 'I2-4', name: '会计政策检查', sheetName: 'Policy_Check_I2_4 会计政策检查', group: '检查', fields: ['I2-4-'] },
  { seq: 8, code: 'I2-6', name: '研发项目资本化时点判断', tag: 'CAS6核心', sheetName: 'Capitalization_I2_6 资本化时点判断', group: '检查', fields: ['I2-6-'] },
  { seq: 9, code: 'I2-7', name: '研发项目构成明细表', tag: '73列', sheetName: 'Project_Detail_I2_7 项目构成', group: '检查', fields: ['I2-7-'] },
  { seq: 10, code: 'I2-8', name: '研发材料投入检查表', sheetName: 'Material_Check_I2_8 材料投入', group: '检查', fields: ['I2-8-'] },
  { seq: 11, code: 'I2-9', name: '研发人员认定检查表', sheetName: 'Staff_Check_I2_9 人员认定', group: '检查', fields: ['I2-9-'] },
  { seq: 12, code: 'I2-10', name: '研发人员工时检查表', sheetName: 'WorkHour_Check_I2_10 工时检查', group: '检查', fields: ['I2-10-'] },
  { seq: 13, code: 'I2-11', name: '委外研发检查表', sheetName: 'Outsource_Check_I2_11 委外研发', group: '检查', fields: ['I2-11-'] },
  { seq: 14, code: 'I2-12', name: '针对性检查表', sheetName: 'Targeted_Check_I2_12 针对性检查', group: '检查', fields: ['I2-12-'] },
  // 截止组
  { seq: 15, code: 'I2-13', name: '截止性测试（账到单据）', sheetName: 'Cutoff_Forward_I2_13 截止账到单据', group: '截止', fields: ['I2-13-'] },
  { seq: 16, code: 'I2-14', name: '截止性测试（单据到账）', sheetName: 'Cutoff_Backward_I2_14 截止单据到账', group: '截止', fields: ['I2-14-'] },
  // 减值组
  { seq: 17, code: 'I2-15', name: '减值准备测试表', sheetName: 'Impairment_I2_15 减值测试', group: '减值', fields: ['I2-15-'] },
  { seq: 18, code: 'I2-16', name: '可收回金额测试', sheetName: 'Recoverable_I2_16 可收回金额', group: '减值', fields: ['I2-16-'] },
  // 附注组
  { seq: 19, code: '附注-L', name: '附注（上市公司）', sheetName: 'Disclosure_Listed 附注上市', group: '附注', fields: ['I2-disc-L-'] },
  { seq: 20, code: '附注-S', name: '附注（国企）', sheetName: 'Disclosure_SOE 附注国企', group: '附注', fields: ['I2-disc-S-'] },
]

const GROUP_META: { label: string; color: string }[] = [
  { label: '核心', color: '#409eff' },
  { label: '检查', color: '#e6a23c' },
  { label: '截止', color: '#f56c6c' },
  { label: '减值', color: '#909399' },
  { label: '附注', color: '#67c23a' },
]

const sheetCount = SHEET_DEFS.length

/** Determine per-sheet status from checklist_responses */
function getSheetStatus(fields: string[]): { status: SheetStatus; progress: number } {
  if (fields.length === 0) return { status: '未开始', progress: 0 }
  const responses = props.allResponses
  if (!responses || responses.size === 0) return { status: '未开始', progress: 0 }

  let totalFields = 0
  let filledFields = 0

  for (const [key, value] of responses) {
    for (const prefix of fields) {
      if (key.startsWith(prefix)) {
        totalFields++
        if (value !== null && value !== undefined && value !== '') filledFields++
      }
    }
  }

  if (totalFields === 0) return { status: '未开始', progress: 0 }
  const progress = Math.round((filledFields / totalFields) * 100)
  if (progress >= 90) return { status: '已完成', progress: 100 }
  if (filledFields > 0) return { status: '进行中', progress }
  return { status: '未开始', progress: 0 }
}

const sheets = computed<SheetEntry[]>(() => {
  return SHEET_DEFS.map((def) => {
    const { status, progress } = getSheetStatus(def.fields)
    return { ...def, status, progress }
  })
})

const groupedSheets = computed(() => {
  return GROUP_META.map((g) => ({
    ...g,
    items: sheets.value.filter((s) => s.group === g.label),
  }))
})

const stats = computed(() => {
  const list = sheets.value
  return {
    completed: list.filter((s) => s.status === '已完成').length,
    inProgress: list.filter((s) => s.status === '进行中').length,
    pending: list.filter((s) => s.status === '未开始').length,
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
    case '已完成': return 'success'
    case '进行中': return 'warning'
    case '未开始': return 'info'
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
.i2-tab-index { padding: 16px; font-size: var(--wp-font-size, 13px); }

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

/* 分组目录 */
.sheet-group { margin-bottom: 12px; }
.group-header {
  font-size: var(--wp-font-size, 13px); font-weight: 600; padding: 6px 12px;
  border-left: 3px solid #409eff; background: #fafbfc;
  margin-bottom: 4px; border-radius: 2px;
}
.index-card { margin-bottom: 16px; }
.section-title { display: flex; align-items: center; justify-content: space-between; }
.completion-text { font-size: 12px; color: var(--el-text-color-secondary); }
.completion-bar { margin-bottom: 12px; }
.index-table { font-size: var(--wp-font-size, 13px); cursor: pointer; }
.sheet-link { color: var(--el-color-primary); }
.sheet-link:hover { text-decoration: underline; }
.sheet-tag {
  margin-left: 6px; font-size: 11px; padding: 1px 5px;
  background: #ecf5ff; color: #409eff; border-radius: 3px;
}

/* 编制提示 */
.compile-hint { margin-top: 12px; font-size: 12px; color: var(--el-text-color-secondary); }
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ul { padding-left: 20px; margin-top: 8px; }
</style>
