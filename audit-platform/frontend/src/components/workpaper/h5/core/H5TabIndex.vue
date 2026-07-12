<template>
  <div class="h5-tab-index">
    <!-- 顶部引导区 -->
    <div class="guide-area">
      <div class="guide-grid">
        <div class="guide-step"><span class="step-num">①</span> 审定表(H5-1)确认TB取数→三角勾稽→审定回写</div>
        <div class="guide-step"><span class="step-num">②</span> 明细表(H5-2)逐项登记→公式自动→交叉核对H5-1</div>
        <div class="guide-step"><span class="step-num">③</span> 检查表(H5-4~8)闲置/政策/增加(勘探资本化)/减少(联动H10)/权属(采矿权)</div>
        <div class="guide-step"><span class="step-num">④</span> 折耗(H5-12分支选择)+分配(H5-13)+减值(H5-14~15)</div>
        <div class="guide-step"><span class="step-num">⑤</span> 监盘(H5-9~11)计划/检查/小结</div>
        <div class="guide-step"><span class="step-num">⑥</span> 附注披露(H5-disc)上市/国企版本</div>
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
      <el-table :data="sheets" stripe size="small" class="index-table">
        <el-table-column prop="seq" label="序号" width="50" align="center" />
        <el-table-column prop="code" label="索引号" width="80" />
        <el-table-column prop="name" label="底稿名称" min-width="200" />
        <el-table-column prop="preparer" label="编制" width="80" align="center">
          <template #default="{ row }">
            <span class="preparer-cell">{{ row.preparer || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="reviewer" label="复核" width="80" align="center">
          <template #default="{ row }">
            <span class="reviewer-cell">{{ row.reviewer || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="90" align="center">
          <template #default="{ row }">
            <el-tag :type="row.statusType" size="small">
              {{ row.statusLabel }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="100" align="center">
          <template #default="{ row }">
            <GtIndexChip :value="row.code" :validate="false" @click="handleNavigate(row)" />
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 编制提示 -->
    <details class="compile-hint">
      <summary>编制提示</summary>
      <ul>
        <li>本底稿仅适用于石油天然气/采矿行业项目（oil_gas/mining）</li>
        <li>建议按序号顺序编制，H5-1→H5-2→检查→折耗→减值→附注</li>
        <li>H5-1审定表完成后自动回写TB，请确认科目1631/1632映射正确</li>
        <li>H5-12折耗测算有2个分支(不含减值/含减值)，根据实际情况选一个</li>
        <li>折耗核心方法为单位产量法（折耗=可折耗金额×当期产量÷预计可采储量）</li>
        <li>附注有上市版/国企版，根据applicable_standards自动判断</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
import { computed, defineAsyncComponent } from 'vue'

const GtIndexChip = defineAsyncComponent(() => import('../../GtIndexChip.vue'))

const emit = defineEmits<{
  'navigate-sheet': [sheetName: string]
}>()

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

interface SheetEntry {
  seq: number
  code: string
  name: string
  preparer: string
  reviewer: string
  statusType: 'success' | 'warning' | 'info'
  statusLabel: string
}

const sheetDefs: { seq: number; code: string; name: string }[] = [
  { seq: 1, code: 'H5', name: '底稿目录' },
  { seq: 2, code: 'H5-1', name: '审定表' },
  { seq: 3, code: 'H5-2', name: '明细表' },
  { seq: 4, code: 'H5-3', name: '调整分录' },
  { seq: 5, code: 'H5-4', name: '闲置检查' },
  { seq: 6, code: 'H5-5', name: '会计政策检查（CAS27）' },
  { seq: 7, code: 'H5-6', name: '分析性程序' },
  { seq: 8, code: 'H5-7', name: '增加检查（勘探资本化）' },
  { seq: 9, code: 'H5-8', name: '减少检查（联动H10）' },
  { seq: 10, code: 'H5-9', name: '监盘计划' },
  { seq: 11, code: 'H5-10', name: '盘点检查表' },
  { seq: 12, code: 'H5-11', name: '监盘小结' },
  { seq: 13, code: 'H5-12', name: '折耗测算表' },
  { seq: 14, code: 'H5-13', name: '折耗分配分析表' },
  { seq: 15, code: 'H5-14', name: '减值测算表' },
  { seq: 16, code: 'H5-15', name: '可收回金额测试表' },
  { seq: 17, code: 'H5-16', name: '权属检查（采矿权）' },
  { seq: 18, code: 'H5-17', name: '关联交易检查' },
  { seq: 19, code: 'H5-18', name: '经营租出' },
  { seq: 20, code: 'H5-19', name: '融资租出' },
  { seq: 21, code: 'H5-disc-L', name: '附注-上市公司' },
  { seq: 22, code: 'H5-disc-S', name: '附注-国企' },
  { seq: 23, code: 'H5-3A', name: '调整分录汇总' },
  { seq: 24, code: 'H5A', name: '程序表' },
]

const sheets = computed<SheetEntry[]>(() => {
  return sheetDefs.map((d) => {
    const status = _getStatus(d.code)
    return {
      ...d,
      preparer: _getPreparer(d.code),
      reviewer: _getReviewer(d.code),
      statusType: status.type,
      statusLabel: status.label,
    }
  })
})

const completedCount = computed(() => sheets.value.filter((s) => s.statusType === 'success').length)
const completionPct = computed(() => Math.round((completedCount.value / sheets.value.length) * 100))

function _hasData(code: string): boolean {
  for (const [key] of props.allResponses) {
    if (key.startsWith(code)) return true
  }
  return false
}

function _getStatus(code: string): { type: 'success' | 'warning' | 'info'; label: string } {
  if (!_hasData(code)) return { type: 'info', label: '待编制' }
  const conclusionKey = `${code}-conclusion`
  if (props.allResponses.has(conclusionKey)) return { type: 'success', label: '已完成' }
  return { type: 'warning', label: '编制中' }
}

function _getPreparer(code: string): string {
  const key = `${code}-preparer`
  const val = props.allResponses.get(key)
  return val?.remark || val?.conclusion || ''
}

function _getReviewer(code: string): string {
  const key = `${code}-reviewer`
  const val = props.allResponses.get(key)
  return val?.remark || val?.conclusion || ''
}

function handleNavigate(row: SheetEntry) {
  emit('navigate-sheet', row.code)
}
</script>

<style scoped>
.h5-tab-index { padding: 16px; font-size: var(--wp-font-size, 13px); }
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
.index-table { font-size: var(--wp-font-size, 13px); }
.preparer-cell, .reviewer-cell { font-size: 12px; color: var(--el-text-color-regular); }
.compile-hint { margin-top: 12px; font-size: 12px; color: var(--el-text-color-secondary); }
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ul { padding-left: 20px; margin-top: 8px; }
</style>
