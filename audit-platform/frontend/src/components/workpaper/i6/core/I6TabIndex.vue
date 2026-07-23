<template>
  <div class="i6-tab-index">
    <!-- 顶部蓝色渐变引导区 -->
    <div class="guide-area">
      <div class="guide-grid">
        <div class="guide-step"><span class="step-num">①</span> 审定表(I6-1)确认TB取数(6602发生额)→损益类审定→I2联动VR-I6-01</div>
        <div class="guide-step"><span class="step-num">②</span> 明细表(I6-2)月度12列横向矩阵→异常月份±30%红色标记</div>
        <div class="guide-step"><span class="step-num">③</span> 调整分录(I6-3)AJE/RJE录入→借贷平衡→推送A13</div>
        <div class="guide-step"><span class="step-num">④</span> 针对性检查(I6-4)抽凭核对1~5项，检查比例联动I6-2</div>
        <div class="guide-step"><span class="step-num">⑤</span> 截止测试(I6-5/I6-6)双向截止→跨期红色高亮</div>
        <div class="guide-step"><span class="step-num">⑥</span> 附注披露：按准则显示上市/国企版本</div>
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
          <span>I6 研发费用（底稿目录，共 {{ sheets.length }} 个Sheet）</span>
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
        <li>建议按序号顺序编制：程序表→审定表→明细表→调整→针对性检查→截止测试→附注</li>
        <li>科目6602研发费用（损益类/借方科目）：取发生额非余额！</li>
        <li>I6↔I2双向联动：费用化(I6)+资本化(I2)=研发总额(VR-I6-01)</li>
        <li>月度明细表65列(基础+12月+合计)，异常月份(±30%)自动标红</li>
        <li>截止测试双向：I6-5(账→单据) / I6-6(单据→账)</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * I6TabIndex.vue — I6 研发费用底稿目录（11 sheet + 进度 + 导航）
 *
 * 列出所有11个sheet，显示完成状态，点击跳转。
 * 科目6602研发费用（损益类/借方科目），取发生额非余额！
 *
 * Spec: .kiro/specs/i6-research-development-expense/
 * Task: 4.1
 */
import { computed } from 'vue'
import GtIndexChip from '@/components/workpaper/GtIndexChip.vue'
import { resolveI6DisclosureVisibility } from '../../composables/i6ApplicableSheets'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
  applicableStandards?: string[]
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

const SHEET_DEFS: {
  seq: number; code: string; name: string; sheetName: string; fields: string[]; crossRef?: string
  disclosureVariant?: 'listed' | 'soe'
}[] = [
  { seq: 1, code: '目录', name: '研发费用（底稿目录）', sheetName: '底稿目录', fields: [] },
  { seq: 2, code: 'I6A', name: '研发费用实质性程序表', sheetName: 'I6A', fields: ['I6A-'] },
  { seq: 3, code: 'I6-1', name: '研发费用审定表（损益类发生额）', sheetName: 'I6-1', fields: ['I6-1-'] },
  { seq: 4, code: 'I6-2', name: '研发费用明细表（月度12列）', sheetName: 'I6-2', fields: ['I6-2-'] },
  { seq: 5, code: 'I6-3', name: '研发费用调整分录', sheetName: 'I6-3', fields: ['I6-3-'], crossRef: 'A13' },
  { seq: 6, code: 'I6-4', name: '针对性检查表（抽凭核对）', sheetName: 'I6-4', fields: ['I6-4-'] },
  { seq: 7, code: 'I6-5', name: '截止测试（账→单据）', sheetName: 'I6-5', fields: ['I6-5-'], crossRef: 'I6-6' },
  { seq: 8, code: 'I6-6', name: '截止测试（单据→账）', sheetName: 'I6-6', fields: ['I6-6-'], crossRef: 'I6-5' },
  { seq: 9, code: '附注(上市)', name: '附注-上市公司', sheetName: '附注上市', fields: ['I6-disc-L-', 'I6-disc-listed-'], disclosureVariant: 'listed' },
  { seq: 10, code: '附注(国企)', name: '附注-国有企业', sheetName: '附注国企', fields: ['I6-disc-S-', 'I6-disc-soe-'], disclosureVariant: 'soe' },
  { seq: 11, code: 'I6-全', name: '底稿全览(OO)', sheetName: 'Full_Workbook', fields: [] },
]

function _parseRows(key: string): any[] {
  const raw = props.allResponses.get(key)?.remark
  if (!raw) return []
  try { const p = JSON.parse(raw); return Array.isArray(p) ? p : [] } catch { return [] }
}

function _getCutoffSheetProgress(code: 'I6-5' | 'I6-6'): { status: SheetStatus; progress: number } {
  const progressKey = `${code}-completion-progress`
  const stored = props.allResponses.get(progressKey)?.remark
  if (stored != null && stored !== '') {
    const progress = Math.min(100, Number(stored) || 0)
    const ok = props.allResponses.get(`${code}-completion-ok`)?.remark === 'Y'
    return { progress, status: ok ? '已复核' : progress >= 90 ? '编制中' : '编制中' }
  }
  const rows = _parseRows(`${code}-rows`)
  const hasConclusion = Boolean(props.allResponses.get(`${code}-audit-conclusion`)?.remark)
  if (rows.length === 0) return { status: '未编制', progress: 0 }
  const progress = hasConclusion ? 90 : Math.min(75, 25 + rows.length * 5)
  return { status: '编制中', progress }
}

function _getSheetStatus(fields: string[], code?: string): { status: SheetStatus; progress: number } {
  if (code === 'I6-5' || code === 'I6-6') return _getCutoffSheetProgress(code)
  if (fields.length === 0) return { status: '未编制', progress: 0 }
  let totalFields = 0
  let filledFields = 0
  let hasReview = false
  for (const [key, value] of props.allResponses) {
    for (const prefix of fields) {
      if (key.startsWith(prefix)) {
        totalFields++
        if (value !== null && value !== undefined && value !== '') filledFields++
        if (key.includes('-review') && value) hasReview = true
      }
    }
  }
  if (totalFields === 0) return { status: '未编制', progress: 0 }
  const progress = Math.round((filledFields / totalFields) * 100)
  if (hasReview && progress >= 90) return { status: '已复核', progress: 100 }
  if (filledFields > 0) return { status: '编制中', progress }
  return { status: '未编制', progress: 0 }
}

const disclosureVis = computed(() => resolveI6DisclosureVisibility(props.applicableStandards))

const sheets = computed<SheetEntry[]>(() => {
  return SHEET_DEFS
    .filter((def) => !def.disclosureVariant || disclosureVis.value[def.disclosureVariant])
    .map((def, idx) => {
      const { status, progress } = _getSheetStatus(def.fields, def.code)
      return {
        seq: idx + 1,
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
  return Math.round(sheets.value.reduce((sum, s) => sum + s.progress, 0) / total)
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
.i6-tab-index { padding: 16px; font-size: var(--wp-font-size, 13px); }
.guide-area { background: linear-gradient(135deg, #e8f4fd 0%, #d4ecfb 100%); border-radius: 8px; padding: 16px; margin-bottom: 16px; }
.guide-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
.guide-step { display: flex; align-items: center; gap: 6px; font-size: var(--wp-font-size, 13px); }
.step-num { font-weight: 700; color: var(--el-color-primary); min-width: 20px; }
.stats-summary { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-bottom: 16px; }
.stat-item { display: flex; flex-direction: column; align-items: center; padding: 12px 8px; border-radius: 8px; background: #f5f7fa; }
.stat-value { font-size: 24px; font-weight: 700; line-height: 1.2; }
.stat-label { font-size: 12px; color: var(--el-text-color-secondary); margin-top: 4px; }
.stat-completed .stat-value { color: #67c23a; }
.stat-inprogress .stat-value { color: #e6a23c; }
.stat-pending .stat-value { color: #909399; }
.stat-total .stat-value { color: var(--el-color-primary); }
.section-title { display: flex; align-items: center; justify-content: space-between; }
.completion-text { font-size: 12px; color: var(--el-text-color-secondary); }
.completion-bar { margin-bottom: 12px; }
.index-card { margin-bottom: 16px; }
.index-table { font-size: var(--wp-font-size, 13px); cursor: pointer; }
.sheet-link { color: var(--el-color-primary); }
.sheet-link:hover { text-decoration: underline; }
.cross-ref-chip { margin-left: 6px; }
.compile-hint { margin-top: 12px; font-size: 12px; color: var(--el-text-color-secondary); }
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ul { padding-left: 20px; margin-top: 8px; }
.compile-hint li { margin-bottom: 4px; }
</style>
