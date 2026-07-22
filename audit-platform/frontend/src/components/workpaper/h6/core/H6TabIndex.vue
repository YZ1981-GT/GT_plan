<template>
  <div class="h6-tab-index">
    <!-- 过渡科目状态指示 -->
    <div
      class="transit-status-indicator"
      :class="transitAccountStatus.isZero ? 'status-green' : 'status-red'"
    >
      <span v-if="transitAccountStatus.isZero">✓ 所有清理已结转</span>
      <span v-else>⚠ 存在未结转项目，余额：{{ transitAccountStatus.balance }}元</span>
    </div>

    <!-- 顶部引导区 -->
    <div class="guide-area">
      <div class="guide-grid">
        <div class="guide-step"><span class="step-num">①</span> 程序表(H6A)确认审计程序清单</div>
        <div class="guide-step"><span class="step-num">②</span> 审定表(H6-1)：从H6-2回填→核对期初/期末审定与变动率→过渡科目1606期末应为0→报表核对</div>
        <div class="guide-step"><span class="step-num">③</span> 明细表(H6-2)逐项登记清理项目→联动H1/H10</div>
        <div class="guide-step"><span class="step-num">④</span> 调整分录(H6-3)→借贷平衡→推送A13</div>
        <div class="guide-step"><span class="step-num">⑤</span> 检查表(H6-4)凭证级测试清理样本+检查比例</div>
        <div class="guide-step"><span class="step-num">⑥</span> 附注披露→上市/国企从H6-1/H6-2取数并同步附注「固定资产清理」</div>
      </div>
    </div>

    <!-- 底稿目录表 -->
    <el-card shadow="never" class="index-card">
      <template #header>
        <div class="section-title">
          <span>底稿目录（共 {{ sheets.length }} 个Sheet）</span>
          <span class="completion-text">完成度 {{ completedCount }}/{{ sheets.length }}</span>
        </div>
      </template>
      <el-progress :percentage="completionPct" :stroke-width="8" class="completion-bar" />
      <el-table :data="sheets" stripe size="small" class="index-table" @row-click="handleNavigate">
        <el-table-column prop="seq" label="序号" width="50" align="center" />
        <el-table-column prop="code" label="底稿编码" width="90" />
        <el-table-column prop="name" label="底稿名称" min-width="220">
          <template #default="{ row }">
            <span class="sheet-link">{{ row.name }}</span>
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

    <!-- 编制提示 -->
    <details class="compile-hint">
      <summary>编制提示</summary>
      <ul>
        <li>建议按序号顺序编制：H6A程序表→H6-1审定→H6-2明细→H6-3调整→H6-4检查→附注</li>
        <li>H6-1审定表完成后自动回写TB科目1606（过渡科目借方：期末=期初+借-贷，期末应为0）</li>
        <li>H6-2明细表支持动态行新增，清理状态选项：清理中/已完成/已结转</li>
        <li>H6-2可通过GtIndexChip跳转H1-8减少检查和H10资产处置损益对应行</li>
        <li>H6-4检查表为凭证级实质性测试：从H6-2带入样本，核对净值/清理损益/结转分摊与检查比例</li>
        <li>附注上市/国企版对齐源xlsx：汇总+清理明细；「同步到附注」推送五、15/八、22「固定资产清理」子表（与H1浅合并）</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * H6TabIndex.vue — H6 固定资产清理底稿目录
 * 8行sheet列表+进度条+过渡科目状态指示
 * Spec: Task 4.1 | Requirements: 1.2, 6.1
 */
import { computed } from 'vue'
import GtIndexChip from '../../GtIndexChip.vue'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
  transitAccountStatus: { isZero: boolean; balance: number }
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
}

const sheets = computed<SheetEntry[]>(() => {
  const defs: Omit<SheetEntry, 'completed'>[] = [
    { seq: 1, code: 'H6', name: '底稿目录', sheetName: '底稿目录' },
    { seq: 2, code: 'H6A', name: '程序表 H6A', sheetName: '固定资产清理实质性程序表H6A' },
    { seq: 3, code: 'H6-1', name: '审定表 H6-1', sheetName: '审定表H6-1' },
    { seq: 4, code: 'H6-disc-L', name: '附注（上市公司）', sheetName: '附注披露信息（上市公司）' },
    { seq: 5, code: 'H6-disc-S', name: '附注（国有企业）', sheetName: '附注披露信息（国有企业）' },
    { seq: 6, code: 'H6-2', name: '明细表 H6-2', sheetName: '明细表H6-2' },
    { seq: 7, code: 'H6-3', name: '调整分录 H6-3', sheetName: '调整分录汇总H6-3' },
    { seq: 8, code: 'H6-4', name: '检查表 H6-4', sheetName: '检查表H6-4' },
  ]
  return defs.map(d => ({
    ...d,
    completed: _hasData(d.code),
  }))
})

const completedCount = computed(() => sheets.value.filter(s => s.completed).length)
const completionPct = computed(() => Math.round((completedCount.value / sheets.value.length) * 100))

function _hasData(code: string): boolean {
  for (const [key] of props.allResponses) {
    // item_id前缀格式："H6-{sheet编号}-{field}"
    // 对于 'H6' 目录本身，匹配以 'H6-' 开头的任意key
    // 对于 'H6A'，匹配 'H6A-' 开头
    // 对于 'H6-N'，匹配 'H6-N-' 开头
    // 对于 'H6-disc-L'/'H6-disc-S'，精确匹配前缀
    if (code === 'H6') {
      if (key.startsWith('H6-')) return true
    } else if (key.startsWith(`${code}-`)) {
      return true
    }
  }
  return false
}

function handleNavigate(row: SheetEntry) {
  emit('navigate-sheet', row.sheetName)
}
</script>

<style scoped>
.h6-tab-index { padding: 16px; font-size: var(--wp-font-size, 13px); }

.transit-status-indicator {
  display: flex;
  align-items: center;
  padding: 10px 16px;
  font-size: var(--wp-font-size, 13px);
  font-weight: 600;
  border-radius: 6px;
  margin-bottom: 16px;
}
.transit-status-indicator.status-green {
  background: #f0f9eb;
  color: #67c23a;
  border: 1px solid #c2e7b0;
}
.transit-status-indicator.status-red {
  background: #fef0f0;
  color: #f56c6c;
  border: 1px solid #fbc4c4;
}

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
