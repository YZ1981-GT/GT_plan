<template>
  <div class="h8-tab-index">
    <!-- H9联动状态指示 -->
    <div
      class="h9-linkage-indicator"
      :class="h9LinkageStatus === 'consistent' ? 'status-green' : h9LinkageStatus === 'unknown' ? 'status-gray' : 'status-red'"
    >
      <span v-if="h9LinkageStatus === 'consistent'">✓ H8与H9联动一致（CAS21：H8=H9+直接费用-激励）</span>
      <span v-else-if="h9LinkageStatus === 'unknown'">⏳ H9租赁负债数据未加载，暂无法校验</span>
      <span v-else>⚠ H8与H9联动不一致，请检查</span>
    </div>

    <!-- 顶部引导区 -->
    <div class="guide-area">
      <div class="guide-grid">
        <div class="guide-step"><span class="step-num">①</span> 程序表(H8A)确认审计程序清单</div>
        <div class="guide-step"><span class="step-num">②</span> 审定表(H8-1)确认TB取数→科目1901+累计折旧</div>
        <div class="guide-step"><span class="step-num">③</span> 明细表(H8-2)逐笔租赁合同登记→初始计量=H9+直接-激励</div>
        <div class="guide-step"><span class="step-num">④</span> 调整分录(H8-3)→借贷平衡→推送A13</div>
        <div class="guide-step"><span class="step-num">⑤</span> 租赁判断(H8-4/5/7)识别+期限+变更三表</div>
        <div class="guide-step"><span class="step-num">⑥</span> 计量(H8-6)按年/按月分支+折旧(H8-8)双分支</div>
        <div class="guide-step"><span class="step-num">⑦</span> 减值(H8-10/11)+减少检查(H8-12)→H9终止同步</div>
        <div class="guide-step"><span class="step-num">⑧</span> 简化处理(H8-13)+关联交易(H8-14)+附注</div>
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
        <el-table-column prop="code" label="底稿编码" width="100" />
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

    <!-- 编制提示 -->
    <details class="compile-hint">
      <summary>编制提示</summary>
      <ul>
        <li>CAS21核心：使用权资产=租赁负债初始确认+初始直接费用-租赁激励</li>
        <li>H8-6初始及后续计量有2个分支：按年计量(59行)和按月计量(361行)</li>
        <li>H8-8折旧测算有2个分支：不含减值(62公式)和含减值(86公式)</li>
        <li>H8-1审定表完成后自动回写TB科目1901+累计折旧</li>
        <li>H8-12减少检查(租赁终止)会同步通知H9终止确认</li>
        <li>H8-13简化处理检查：短期(≤12月)/低价值(≤4万)租赁可豁免确认使用权资产</li>
        <li>建议先完成H9租赁负债，再编制H8使用权资产（数据联动）</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * H8TabIndex.vue — H8 使用权资产底稿目录
 * 20行sheet列表 + 进度条 + H9联动状态指示
 * Spec: Task 4.1 | Requirements: 1.2
 */
import { computed } from 'vue'
import GtIndexChip from '../../GtIndexChip.vue'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
  h9LinkageStatus?: 'consistent' | 'inconsistent' | 'unknown'
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

const sheets = computed<SheetEntry[]>(() => {
  const defs: Omit<SheetEntry, 'completed'>[] = [
    { seq: 1, code: 'H8', name: '底稿目录', sheetName: '底稿目录' },
    { seq: 2, code: 'H8A', name: '使用权资产实质性程序表 H8A', sheetName: '使用权资产实质性程序表H8A', tag: '程序表', tagType: 'info' },
    { seq: 3, code: 'H8-1', name: '审定表 H8-1（原值+累计折旧）', sheetName: '审定表H8-1', tag: '审定表', tagType: 'primary' },
    { seq: 4, code: 'H8-disc-L', name: '附注披露信息（上市公司）', sheetName: '附注披露信息（上市公司）', tag: '附注', tagType: 'success' },
    { seq: 5, code: 'H8-disc-S', name: '附注披露信息（国有企业）', sheetName: '附注披露信息（国有企业）', tag: '附注', tagType: 'success' },
    { seq: 6, code: 'H8-2', name: '明细表 H8-2（58列4区段）', sheetName: '明细表H8-2', tag: '明细', tagType: 'primary' },
    { seq: 7, code: 'H8-3', name: '调整分录汇总 H8-3', sheetName: '调整分录汇总H8-3' },
    { seq: 8, code: 'H8-4', name: '租赁的识别 H8-4', sheetName: '租赁的识别H8-4', tag: '判断', tagType: 'warning' },
    { seq: 9, code: 'H8-5', name: '租赁期的确定 H8-5', sheetName: '租赁期的确定H8-5', tag: '判断', tagType: 'warning' },
    { seq: 10, code: 'H8-6', name: '初始及后续计量 H8-6（按年/按月）', sheetName: '使用权资产初始及后续计量H8-6', tag: '分支', tagType: 'danger' },
    { seq: 11, code: 'H8-7', name: '租赁变更 H8-7', sheetName: '租赁变更H8-7', tag: '判断', tagType: 'warning' },
    { seq: 12, code: 'H8-8', name: '折旧测算表 H8-8（双分支）', sheetName: '折旧测算表H8-8', tag: '分支', tagType: 'danger' },
    { seq: 13, code: 'H8-9', name: '折旧分配分析表 H8-9', sheetName: '折旧分配分析表H8-9' },
    { seq: 14, code: 'H8-10', name: '减值测算表 H8-10', sheetName: '减值测算表H8-10' },
    { seq: 15, code: 'H8-11', name: '可收回金额测试表 H8-11', sheetName: '可收回金额测试表H8-11' },
    { seq: 16, code: 'H8-12', name: '减少检查表 H8-12（租赁终止）', sheetName: '减少检查表H8-12' },
    { seq: 17, code: 'H8-13', name: '简化处理检查表 H8-13', sheetName: '简化处理的租赁检查表H8-13' },
    { seq: 18, code: 'H8-14', name: '关联交易检查表 H8-14', sheetName: '关联交易检查表H8-14' },
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
    if (code === 'H8' && key.startsWith('H8-')) return true
    if (key.startsWith(`${code}-`)) return true
  }
  return false
}

function handleNavigate(row: SheetEntry) {
  emit('navigate-sheet', row.sheetName)
}
</script>

<style scoped>
.h8-tab-index { padding: 16px; font-size: var(--wp-font-size, 13px); }

.h9-linkage-indicator {
  display: flex; align-items: center; padding: 10px 16px;
  font-size: var(--wp-font-size, 13px); font-weight: 600; border-radius: 6px; margin-bottom: 16px;
}
.h9-linkage-indicator.status-green { background: #f0f9eb; color: #67c23a; border: 1px solid #c2e7b0; }
.h9-linkage-indicator.status-red { background: #fef0f0; color: #f56c6c; border: 1px solid #fbc4c4; }
.h9-linkage-indicator.status-gray { background: #f5f7fa; color: #909399; border: 1px solid #dcdfe6; }

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
