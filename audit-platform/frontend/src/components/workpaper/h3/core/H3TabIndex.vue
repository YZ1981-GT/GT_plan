<template>
  <div class="h3-tab-index">
    <!-- 顶部引导区 -->
    <div class="guide-area">
      <div class="guide-grid">
        <div class="guide-step"><span class="step-num">①</span> 审定表(H3-1)根据计量模式选择成本/公允→TB回写1503(+1504)</div>
        <div class="guide-step"><span class="step-num">②</span> 明细表(H3-2)逐项登记→区段Tab切换→交叉核对H3-1</div>
        <div class="guide-step"><span class="step-num">③</span> 会计政策(H3-4)CAS3五段落→计量模式恰当性评价</div>
        <div class="guide-step"><span class="step-num">④</span> 增减检查(H3-5)+互转(H3-6)三方向→联动H1/H2</div>
        <div class="guide-step"><span class="step-num">⑤</span> 折旧(H3-7仅成本)+公允复核(H3-8)+减值(H3-10/11)</div>
        <div class="guide-step"><span class="step-num">⑥</span> 盘点(H3-9)+产权(H3-12)+关联(H3-13)+租金(H3-14)+附注</div>
      </div>
    </div>

    <!-- 计量模式标识 -->
    <el-alert
      :title="`当前计量模式：${measurementModel === 'cost' ? '成本模式' : '公允价值模式'}`"
      :type="measurementModel === 'cost' ? 'info' : 'warning'"
      :closable="false"
      show-icon
      class="mode-alert"
    />

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
        <el-table-column prop="purpose" label="用途说明" min-width="240" />
        <el-table-column label="模式" width="100" align="center">
          <template #default="{ row }">
            <el-tag v-if="row.modeTag" :type="row.modeTag === '成本' ? 'info' : 'warning'" size="small">
              {{ row.modeTag }}
            </el-tag>
            <span v-else style="color:var(--el-text-color-placeholder)">通用</span>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="90" align="center">
          <template #default="{ row }">
            <el-tag :type="row.completed ? 'success' : 'info'" size="small">
              {{ row.completed ? '已完成' : '待编制' }}
            </el-tag>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 编制提示 -->
    <details class="compile-hint">
      <summary>编制提示</summary>
      <ul>
        <li>建议按序号顺序编制，H3-1审定→H3-2明细→H3-4政策→H3-5增减→H3-6互转→折旧/公允→盘点→附注</li>
        <li>计量模式在主入口顶部选择，切换后部分sheet自动隐藏/显示对应版本</li>
        <li>H3-7折旧测算仅成本模式可用；H3-8公允复核两种模式均可编制</li>
        <li>H3-6互转完成后自动联动H1固定资产、H2在建工程底稿</li>
        <li>附注有上市版/国企版，根据applicable_standards自动判断</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * H3TabIndex.vue — H3 投资性房地产底稿目录
 * 22行进度条 + 完成状态 + 计量模式标识 + 点击导航
 * Spec: Task 4.1 | Requirements: 1
 */
import { computed } from 'vue'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  measurementModel: 'cost' | 'fair_value'
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
  modeTag: string
  completed: boolean
  sheetName: string
}

const sheets = computed<SheetEntry[]>(() => {
  const defs: Omit<SheetEntry, 'completed'>[] = [
    { seq: 1, code: 'H3', name: '底稿目录', purpose: '底稿结构导航与进度总览', modeTag: '', sheetName: 'H3 底稿目录' },
    { seq: 2, code: 'H3-1', name: '审定表', purpose: '审定汇总(双区块/单区块)+TB回写+三角勾稽', modeTag: props.measurementModel === 'cost' ? '成本' : '公允', sheetName: 'H3-1 审定表' },
    { seq: 3, code: 'H3-2', name: '明细表', purpose: '资产明细宽表(区段Tab)+合计+交叉验证', modeTag: props.measurementModel === 'cost' ? '成本' : '公允', sheetName: 'H3-2 明细表' },
    { seq: 4, code: 'H3-3', name: '调整分录', purpose: 'AJE/RJE录入+借贷平衡+推送A13', modeTag: '', sheetName: 'H3-3 调整分录' },
    { seq: 5, code: 'H3-4', name: '会计政策检查', purpose: 'CAS3五段落+计量模式恰当性', modeTag: '', sheetName: 'H3-4 会计政策检查' },
    { seq: 6, code: 'H3-5', name: '增减检查', purpose: '逐笔增减核对+抽凭+OCR', modeTag: props.measurementModel === 'cost' ? '成本' : '公允', sheetName: 'H3-5 增减检查' },
    { seq: 7, code: 'H3-6', name: '互转审核', purpose: '自用↔投资↔在建三方向(25公式)+联动H1/H2', modeTag: '', sheetName: 'H3-6 互转审核' },
    { seq: 8, code: 'H3-7', name: '折旧测算', purpose: '直线法+含/不含减值分支(42/62公式)', modeTag: '成本', sheetName: 'H3-7 折旧测算' },
    { seq: 9, code: 'H3-8', name: '公允价值复核', purpose: '评估师+方法+复核15公式+假设挑战', modeTag: '公允', sheetName: 'H3-8 公允价值复核' },
    { seq: 10, code: 'H3-9', name: '盘点检查', purpose: '13列+空置高亮+汇总', modeTag: '', sheetName: 'H3-9 盘点检查' },
    { seq: 11, code: 'H3-10', name: '减值测算', purpose: '减值迹象+测算表(仅成本)', modeTag: '成本', sheetName: 'H3-10 减值测算' },
    { seq: 12, code: 'H3-11', name: '可收回金额', purpose: 'DCF模型+敏感性矩阵(仅成本)', modeTag: '成本', sheetName: 'H3-11 可收回金额' },
    { seq: 13, code: 'H3-12', name: '产权核对', purpose: '16列+产权异常红色+面积差异黄色', modeTag: '', sheetName: 'H3-12 产权核对' },
    { seq: 14, code: 'H3-13', name: '关联交易', purpose: '11列+差异率>10%红色+合计', modeTag: '', sheetName: 'H3-13 关联交易' },
    { seq: 15, code: 'H3-14', name: '租金收入', purpose: '合同/月度12列/到期+空置高亮+到期预警', modeTag: '', sheetName: 'H3-14 租金收入' },
    { seq: 16, code: 'H3-disc-L', name: '附注-上市公司', purpose: '多子节卡片+动态行+合计', modeTag: '', sheetName: 'H3-disc-L 附注上市' },
    { seq: 17, code: 'H3-disc-S', name: '附注-国企', purpose: '多子节卡片+动态行+合计', modeTag: '', sheetName: 'H3-disc-S 附注国企' },
    { seq: 18, code: 'H3A', name: '程序表', purpose: '审计程序清单(走a-program-console)', modeTag: '', sheetName: 'H3A 程序表' },
  ]
  return defs.map(d => ({ ...d, completed: _hasData(d.code) }))
})

const completedCount = computed(() => sheets.value.filter(s => s.completed).length)
const completionPct = computed(() => Math.round((completedCount.value / sheets.value.length) * 100))

function _hasData(code: string): boolean {
  for (const [key] of props.allResponses) {
    if (key.startsWith(code)) return true
  }
  return false
}

function handleNavigate(row: SheetEntry) {
  emit('navigate-sheet', row.sheetName)
}
</script>

<style scoped>
.h3-tab-index { padding: 16px; font-size: 13px; }
.guide-area {
  background: linear-gradient(135deg, #e8f4fd 0%, #d4ecfb 100%);
  border-radius: 8px; padding: 16px; margin-bottom: 16px;
}
.guide-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
.guide-step { display: flex; align-items: center; gap: 6px; font-size: 13px; }
.step-num { font-weight: 700; color: var(--el-color-primary); min-width: 20px; }
.mode-alert { margin-bottom: 16px; }
.section-title { display: flex; align-items: center; justify-content: space-between; }
.completion-text { font-size: 12px; color: var(--el-text-color-secondary); }
.completion-bar { margin-bottom: 12px; }
.index-card { margin-bottom: 16px; }
.index-table { font-size: 13px; cursor: pointer; }
.sheet-link { color: var(--el-color-primary); }
.sheet-link:hover { text-decoration: underline; }
.compile-hint { margin-top: 12px; font-size: 12px; color: var(--el-text-color-secondary); }
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ul { padding-left: 20px; margin-top: 8px; }
</style>
