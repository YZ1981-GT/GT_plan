<template>
  <div class="h4-tab-index">
    <!-- 顶部引导区 -->
    <div class="guide-area">
      <div class="guide-grid">
        <div class="guide-step"><span class="step-num">①</span> 审定表(H4-1)确认TB取数→期初/期末审定→资产类借方科目1605</div>
        <div class="guide-step"><span class="step-num">②</span> 明细表(H4-2)逐项登记67列→3区段Tab→交叉核对H4-1</div>
        <div class="guide-step"><span class="step-num">③</span> 增加/减少检查(H4-4/5)抽凭+OCR→联动H2在建工程</div>
        <div class="guide-step"><span class="step-num">④</span> 盘点(H4-6)实物核对→减值(H4-7/8)DCF+可收回金额</div>
        <div class="guide-step"><span class="step-num">⑤</span> 关联交易(H4-9)价差率>10%预警→非公允识别</div>
        <div class="guide-step"><span class="step-num">⑥</span> 附注披露→上市/国企双版本自动取数</div>
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
        <el-table-column prop="code" label="编码" width="80" />
        <el-table-column prop="name" label="Sheet名称" min-width="200">
          <template #default="{ row }">
            <span class="sheet-link">{{ row.name }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="purpose" label="用途说明" min-width="260" />
        <el-table-column label="状态" width="90" align="center">
          <template #default="{ row }">
            <el-tag :type="row.completed ? 'success' : 'info'" size="small">
              {{ row.completed ? '已完成' : '待编制' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="跳转" width="70" align="center">
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
        <li>建议按序号顺序编制：H4A程序表→H4-1审定→H4-2明细→检查→盘点→减值→附注</li>
        <li>H4-1审定表完成后自动回写TB科目1605（资产类借方：期末=期初+借方-贷方）</li>
        <li>H4-2明细表为67列宽表，已拆分为3区段Tab切换(基础/入库/出库)</li>
        <li>H4-5减少检查中"领用出库"可通过GtIndexChip跳转H2在建工程对应行</li>
        <li>H4-7/H4-8减值测算以OnlyOffice渲染为主，支持双模式切换</li>
        <li>附注有上市版/国企版，根据applicable_standards自动判断</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * H4TabIndex.vue — H4 工程物资底稿目录
 * 13行sheet列表+进度条+GtIndexChip跳转
 * Spec: Task 4.1 | Requirements: 1.2
 */
import { computed } from 'vue'
import GtIndexChip from '../../GtIndexChip.vue'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const emit = defineEmits<{
  (e: 'navigate-sheet', sheetName: string): void
}>()

interface SheetEntry {
  seq: number
  code: string
  name: string
  purpose: string
  completed: boolean
  sheetName: string
}

const sheets = computed<SheetEntry[]>(() => {
  const defs: Omit<SheetEntry, 'completed'>[] = [
    { seq: 1, code: 'H4', name: '底稿目录', purpose: '底稿结构导航与进度总览', sheetName: '底稿目录' },
    { seq: 2, code: 'H4A', name: '工程物资实质性程序表H4A', purpose: '审计程序清单(走a-program-console)', sheetName: '工程物资实质性程序表H4A' },
    { seq: 3, code: 'H4-1', name: '审定表H4-1', purpose: '51公式+TB取数科目1605+审定数回写+三角勾稽', sheetName: '审定表H4-1' },
    { seq: 4, code: 'H4-disc-L', name: '附注披露信息（上市公司）', purpose: '嵌套表+EventBus subscribe+跨sheet取数', sheetName: '附注披露信息（上市公司）' },
    { seq: 5, code: 'H4-disc-S', name: '附注披露信息（国有企业）', purpose: '嵌套表+EventBus subscribe+跨sheet取数', sheetName: '附注披露信息（国有企业）' },
    { seq: 6, code: 'H4-2', name: '明细表H4-2', purpose: '67列3区段Tab+动态行+合计行+导入导出', sheetName: '明细表H4-2' },
    { seq: 7, code: 'H4-3', name: '调整分录汇总H4-3', purpose: '10列+借贷平衡+EventBus推送A13', sheetName: '调整分录汇总H4-3' },
    { seq: 8, code: 'H4-4', name: '增加检查表H4-4', purpose: '19列+抽凭+OCR+差异计算+统计摘要', sheetName: '增加检查表H4-4' },
    { seq: 9, code: 'H4-5', name: '减少检查表H4-5', purpose: '29列2区块+联动H2在建工程+抽凭', sheetName: '减少检查表H4-5' },
    { seq: 10, code: 'H4-6', name: '盘点检查表H4-6', purpose: '12列+差异自动计算+差异高亮', sheetName: '盘点检查表H4-6' },
    { seq: 11, code: 'H4-7', name: '减值测算表H4-7', purpose: 'OO为主+31行31列15公式+双模式切换', sheetName: '减值测算表H4-7' },
    { seq: 12, code: 'H4-8', name: '可收回金额测试表H4-8', purpose: 'OO为主+58行28列12公式+DCF测试', sheetName: '可收回金额测试表H4-8' },
    { seq: 13, code: 'H4-9', name: '关联交易检查表H4-9', purpose: '16列+价差率>10%红色预警+统计摘要', sheetName: '关联交易检查表H4-9' },
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
    // item_id前缀格式："H4-{sheet编号}-{field}"
    // 对于 'H4' 目录本身，匹配以 'H4-' 开头的任意key（表示有任何sheet数据）
    // 对于 'H4A'，匹配 'H4A-' 开头
    // 对于 'H4-N'，匹配 'H4-N-' 开头
    // 对于 'H4-disc-L'/'H4-disc-S'，精确匹配前缀
    if (code === 'H4') {
      if (key.startsWith('H4-')) return true
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
.h4-tab-index { padding: 16px; font-size: var(--wp-font-size, 13px); }
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
