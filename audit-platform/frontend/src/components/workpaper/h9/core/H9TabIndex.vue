<template>
  <div class="h9-tab-index" data-testid="h9-tab-index">
    <!-- E1 标准加法式增强：目录卡 + 结论看板 + 本循环 grid -->
    <GtCycleDirExtras
      wp-code="H9"
      cycle-letter="H"
      :wp-id="props.wpId"
      :project-id="props.projectId"
      :all-responses="props.allResponses"
      :sheets="dirSheets"
      @navigate="onDirNavigate"
      @open-handbook="openHandbook"
    />
    <H9PreparationHandbookDialog v-model="handbookVisible" :initial-tab="handbookTab" />

    <div
      class="h8-linkage-indicator"
      :class="linkageClass"
      data-testid="h9-h8-linkage"
    >
      <span v-if="linkageKind === 'consistent'">✓ H9与H8联动一致（CAS21：H9初始 ≈ H8 − 直接费用 + 激励）</span>
      <span v-else-if="linkageKind === 'unknown'">⏳ H8使用权资产数据未加载，暂无法校验</span>
      <span v-else>⚠ {{ linkageMessage || 'H9与H8联动不一致，请检查' }}</span>
    </div>

    <div class="guide-area">
      <div class="guide-grid">
        <div class="guide-step"><span class="step-num">①</span> 程序表(H9A)确认租赁负债审计程序</div>
        <div class="guide-step"><span class="step-num">②</span> 明细表(H9-2)按合同登记→利息/偿还/重分类</div>
        <div class="guide-step"><span class="step-num">③</span> 未确认融资费用(H9-3)与H9-2勾稽</div>
        <div class="guide-step"><span class="step-num">④</span> 审定表(H9-1)原值+未确认融资费用→净值→TB</div>
        <div class="guide-step"><span class="step-num">⑤</span> 摊销表按实际利率法复核利息</div>
        <div class="guide-step"><span class="step-num">⑥</span> 调整分录(H9-4)→推送调整模块</div>
        <div class="guide-step"><span class="step-num">⑦</span> 附注披露(上市/国企)←审定/明细取数→同步附注</div>
        <div class="guide-step"><span class="step-num">⑧</span> 与H8使用权资产初始计量双向勾稽</div>
      </div>
    </div>

    <el-card shadow="never" class="index-card">
      <template #header>
        <div class="section-title">
          <span>底稿目录（共 {{ sheets.length }} 项）</span>
          <span class="completion-text">完成度 {{ completedCount }}/{{ sheets.length }}</span>
        </div>
      </template>
      <el-progress :percentage="completionPct" :stroke-width="8" class="completion-bar" />
      <el-table
        :data="sheets"
        stripe
        size="small"
        class="index-table"
        data-testid="h9-index-table"
        @row-click="handleNavigate"
      >
        <el-table-column prop="seq" label="序号" width="50" align="center" />
        <el-table-column prop="code" label="底稿编码" width="110" />
        <el-table-column prop="name" label="底稿名称" min-width="260">
          <template #default="{ row }">
            <span class="sheet-link">{{ row.name }}</span>
          </template>
        </el-table-column>
        <el-table-column label="类型" width="80" align="center">
          <template #default="{ row }">
            <el-tag v-if="row.tag" :type="row.tagType" size="small">{{ row.tag }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="90" align="center">
          <template #default="{ row }">
            <el-tag :type="row.completed ? 'success' : 'info'" size="small">
              {{ row.completed ? '已完成' : '待编制' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="70" align="center">
          <template #default="{ row }">
            <GtIndexChip :value="row.code" @click.stop="handleNavigate(row)" />
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <details class="compile-hint">
      <summary>编制提示</summary>
      <ul>
        <li>负债贷方科目：期末 = 期初 − 偿还 + 利息；未确认融资费用为借方备抵</li>
        <li>净值 = 租赁负债原值 − 未确认融资费用；列报再扣减一年内到期部分</li>
        <li>附注上市「五、47」/国企「八、52」：从 H9-1/H9-2 取数后「同步到附注」</li>
        <li>摊销表为前端计算视图（非 xlsx 原生 sheet），基于 H9-2 利率与期限生成</li>
        <li>建议与 H8 成对编制：H9 初始确认 ↔ H8 入账值（+直接费用 − 激励）</li>
        <li>H8-12 终止确认会同步结清对应 H9-2 合同行</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * H9TabIndex — 租赁负债底稿目录
 * 对齐源 xlsx 目录 + 披露/摊销/关联衍生视图
 */
import { computed, ref, defineAsyncComponent } from 'vue'
import GtIndexChip from '../../GtIndexChip.vue'
import GtCycleDirExtras from '../../GtCycleDirExtras.vue'

const H9PreparationHandbookDialog = defineAsyncComponent(() => import('../H9PreparationHandbookDialog.vue'))

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
  h8LinkageStatus?: { isConsistent: boolean; diff: number; message: string }
}>()

const emit = defineEmits<{
  (e: 'navigate-sheet', sheetName: string): void
}>()

interface SheetEntry {
  seq: number
  code: string
  name: string
  completed: boolean
  sheetName: string
  tag?: string
  tagType?: 'primary' | 'success' | 'warning' | 'danger' | 'info'
}

const DATA_KEY_PREFIX: Record<string, string[]> = {
  H9: ['H9-'],
  H9A: ['H9A-'],
  'H9-1': ['H9-1-'],
  'H9-disc-L': ['H9-disc-listed-'],
  'H9-disc-S': ['H9-disc-soe-'],
  'H9-2': ['H9-2-'],
  'H9-3': ['H9-3-'],
  'H9-4': ['H9-4-'],
  摊销表: ['H9-amort-', 'H9-2-'],
  'H9-6': ['H9-6-', 'H9-2-'],
}

const sheets = computed<SheetEntry[]>(() => {
  const defs: Omit<SheetEntry, 'completed'>[] = [
    { seq: 1, code: 'H9', name: '底稿目录', sheetName: '底稿目录' },
    { seq: 2, code: 'H9A', name: '租赁负债实质性程序表 H9A', sheetName: '租赁负债实质性程序表H9A', tag: '程序表', tagType: 'info' },
    { seq: 3, code: 'H9-1', name: '审定表 H9-1（原值+未确认融资费用）', sheetName: '审定表H9-1', tag: '审定表', tagType: 'primary' },
    { seq: 4, code: 'H9-disc-L', name: '附注披露信息（上市公司）', sheetName: '附注披露信息（上市公司）', tag: '附注', tagType: 'success' },
    { seq: 5, code: 'H9-disc-S', name: '附注披露信息（国企）', sheetName: '附注披露信息（国企）', tag: '附注', tagType: 'success' },
    { seq: 6, code: 'H9-2', name: '租赁负债明细表 H9-2', sheetName: '租赁负债明细表H9-2', tag: '明细', tagType: 'primary' },
    { seq: 7, code: 'H9-3', name: '未确认融资费用明细表 H9-3', sheetName: '未确认融资费用明细表H9-3', tag: '明细', tagType: 'primary' },
    { seq: 8, code: 'H9-4', name: '调整分录汇总 H9-4', sheetName: '调整分录汇总H9-4', tag: '联动', tagType: 'warning' },
    { seq: 9, code: '摊销表', name: '摊销表（实际利率法·计算视图）', sheetName: '摊销表', tag: '计算', tagType: 'danger' },
    { seq: 10, code: 'H9-6', name: '关联方检查（筛选视图）', sheetName: 'H9-6', tag: '检查', tagType: 'warning' },
  ]
  return defs.map((d) => ({
    ...d,
    completed: _hasData(d.code),
  }))
})

const completedCount = computed(() => sheets.value.filter((s) => s.completed).length)
const completionPct = computed(() => Math.round((completedCount.value / sheets.value.length) * 100))

const linkageKind = computed<'consistent' | 'inconsistent' | 'unknown'>(() => {
  const s = props.h8LinkageStatus
  if (!s) return 'unknown'
  if (!s.isConsistent && /未加载/.test(s.message || '')) return 'unknown'
  return s.isConsistent ? 'consistent' : 'inconsistent'
})

const linkageClass = computed(() => {
  if (linkageKind.value === 'consistent') return 'status-green'
  if (linkageKind.value === 'unknown') return 'status-gray'
  return 'status-red'
})

const linkageMessage = computed(() => props.h8LinkageStatus?.message || '')

function _remarkNonEmpty(raw: unknown): boolean {
  if (raw == null) return false
  const s = typeof raw === 'string' ? raw.trim() : JSON.stringify(raw)
  if (!s || s === '[]' || s === '{}' || s === 'null') return false
  return true
}

function _hasData(code: string): boolean {
  const prefixes = DATA_KEY_PREFIX[code] || [`${code}-`]
  for (const [key, item] of props.allResponses) {
    if (!prefixes.some((p) => key.startsWith(p) || key === p.replace(/-$/, ''))) continue
    if (_remarkNonEmpty(item?.remark ?? item?.conclusion ?? item)) return true
  }
  return false
}

function handleNavigate(row: SheetEntry) {
  emit('navigate-sheet', row.sheetName)
}

// ─── E1 标准加法式增强：目录卡 + 结论看板 + 本循环 grid（GtCycleDirExtras） ───
const dirSheets = computed(() =>
  sheets.value.map((s) => ({ code: s.code, navValue: s.sheetName, name: s.name })),
)
function onDirNavigate(navValue: string) {
  emit('navigate-sheet', navValue)
}
const handbookVisible = ref(false)
const handbookTab = ref<'preparation' | 'usage'>('preparation')
function openHandbook(tab: 'preparation' | 'usage') {
  handbookTab.value = tab
  handbookVisible.value = true
}
</script>

<style scoped>
.h9-tab-index { padding: 16px; font-size: var(--wp-font-size, 13px); }

.h8-linkage-indicator {
  display: flex; align-items: center; padding: 10px 16px;
  font-size: var(--wp-font-size, 13px); font-weight: 600; border-radius: 6px; margin-bottom: 16px;
}
.h8-linkage-indicator.status-green { background: #f0f9eb; color: #67c23a; border: 1px solid #c2e7b0; }
.h8-linkage-indicator.status-red { background: #fef0f0; color: #f56c6c; border: 1px solid #fbc4c4; }
.h8-linkage-indicator.status-gray { background: #f5f7fa; color: #909399; border: 1px solid #dcdfe6; }

.guide-area {
  background: linear-gradient(135deg, #e8f4fd 0%, #d4ecfb 100%);
  border-radius: 8px; padding: 16px; margin-bottom: 16px;
}
.guide-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
.guide-step { display: flex; align-items: center; gap: 6px; font-size: var(--wp-font-size, 13px); }
.step-num { font-weight: 700; color: var(--el-color-primary); min-width: 20px; }

.section-title { display: flex; align-items: center; justify-content: space-between; }
.completion-text { font-size: 12px; color: var(--el-text-color-secondary); }
.completion-bar { margin-bottom: 12px; }
.index-card { margin-bottom: 16px; }
.index-table { font-size: var(--wp-font-size, 13px); cursor: pointer; }
.sheet-link { color: var(--el-color-primary); }
.sheet-link:hover { text-decoration: underline; }

.compile-hint { margin-top: 12px; font-size: 12px; color: var(--el-text-color-secondary); }
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ul { padding-left: 20px; margin-top: 8px; }
</style>
