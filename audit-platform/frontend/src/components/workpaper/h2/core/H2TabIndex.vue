<template>
  <div class="h2-tab-index">
    <!-- 顶部引导区 -->
    <div class="guide-area">
      <div class="guide-grid">
        <div class="guide-step"><span class="step-num">①</span> 审定表(H2-1)确认TB取数→期初/期末审定→变动率比较</div>
        <div class="guide-step"><span class="step-num">②</span> 明细表(H2-2)逐项登记50列→三角勾稽含转固→交叉核对H2-1</div>
        <div class="guide-step"><span class="step-num">③</span> 分析表(H2-4)完工进度+资本化率+工期偏差→阈值预警</div>
        <div class="guide-step"><span class="step-num">④</span> 转固检查(H2-5)CAS4五条件判定→延迟高亮→联动H1</div>
        <div class="guide-step"><span class="step-num">⑤</span> 利息资本化(H2-10/11)无/有专门借款分支→加权计算</div>
        <div class="guide-step"><span class="step-num">⑥</span> 监盘(H2-12~14)计划+检查+小结 / 减值(H2-15~16)DCF模型</div>
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
        <el-table-column prop="purpose" label="用途说明" min-width="240" />
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
        <li>建议按序号顺序编制，H2-1→H2-2→H2-4分析→检查→利息→监盘→减值→附注</li>
        <li>H2-1审定表完成后自动回写TB科目1604，请确认科目映射正确</li>
        <li>H2-2明细表为50列宽表，已拆分为3区段Tab切换(基本/增减/竣工结转)</li>
        <li>H2-10/11利息资本化有2个分支(无/有专门借款)，根据实际情况选一个</li>
        <li>转固(H2-5)完成后自动联动H1固定资产底稿</li>
        <li>附注有上市版/国企版，根据applicable_standards自动判断</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * H2TabIndex.vue — H2 在建工程底稿目录
 * 21行进度条 + 完成状态 + 点击导航(emit navigate-sheet)
 * Spec: Task 4.1 | Requirements: 1.2
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
    { seq: 1, code: 'H2', name: '底稿目录', purpose: '底稿结构导航与进度总览', sheetName: 'H2 底稿目录' },
    { seq: 2, code: 'H2-1', name: '审定表', purpose: '12列审定(期初/期末/变动率)+TB取数+差异', sheetName: 'H2-1 审定表' },
    { seq: 3, code: 'H2-2', name: '明细表', purpose: '50列宽表(3区段Tab)+三角勾稽含转固', sheetName: 'H2-2 明细表' },
    { seq: 4, code: 'H2-3', name: '调整分录', purpose: 'AJE/RJE录入+借贷平衡校验+推送A13', sheetName: 'H2-3 调整分录' },
    { seq: 5, code: 'H2-4', name: '分析表', purpose: '完工进度+资本化率+工期偏差+阈值预警', sheetName: 'H2-4 分析表' },
    { seq: 6, code: 'H2-5', name: '转固时点检查', purpose: 'CAS4五条件判定+延迟高亮+联动H1', sheetName: 'H2-5 转固时点检查' },
    { seq: 7, code: 'H2-6', name: '审核记录', purpose: '签章式审核+工程筛选+AI结论', sheetName: 'H2-6 审核记录' },
    { seq: 8, code: 'H2-7', name: '造价比较', purpose: '16列(14公式)+超支红色高亮', sheetName: 'H2-7 造价比较' },
    { seq: 9, code: 'H2-8', name: '增加检查', purpose: '抽样参数+明细+OCR📎+抽凭引擎', sheetName: 'H2-8 增加检查' },
    { seq: 10, code: 'H2-9', name: '减少检查', purpose: '抽样参数+明细+损失分类+抽凭', sheetName: 'H2-9 减少检查' },
    { seq: 11, code: 'H2-10', name: '利息资本化(无专门借款)', purpose: '加权资本化率+累计支出加权+资本化金额', sheetName: 'H2-10 利息资本化无专门借款' },
    { seq: 12, code: 'H2-11', name: '利息资本化(有专门借款)', purpose: '专门借款+一般借款补充+合计', sheetName: 'H2-11 利息资本化有专门借款' },
    { seq: 13, code: 'H2-12', name: '监盘计划', purpose: '基本信息+工程选取+时间安排', sheetName: 'H2-12 监盘计划' },
    { seq: 14, code: 'H2-13', name: '盘点检查', purpose: '盘点检查表+停工红色高亮+导入导出', sheetName: 'H2-13 盘点检查' },
    { seq: 15, code: 'H2-14', name: '监盘小结', purpose: '踏勘总体+异常清单+结论', sheetName: 'H2-14 监盘小结' },
    { seq: 16, code: 'H2-15', name: '减值测算', purpose: '减值迹象6项+测算表+GtIndexChip', sheetName: 'H2-15 减值测算' },
    { seq: 17, code: 'H2-16', name: '可收回金额', purpose: 'DCF模型+假设+现金流预测+敏感性矩阵', sheetName: 'H2-16 可收回金额' },
    { seq: 18, code: 'H2-17', name: '关联交易', purpose: '15列+价格差异率>10%红色+合计行', sheetName: 'H2-17 关联交易' },
    { seq: 19, code: 'H2-disc-L', name: '附注-上市公司', purpose: '多子节卡片+跨sheet取数+动态行', sheetName: 'H2-disc-L 附注上市' },
    { seq: 20, code: 'H2-disc-S', name: '附注-国企', purpose: '多子节卡片+跨sheet取数+动态行', sheetName: 'H2-disc-S 附注国企' },
    { seq: 21, code: 'H2A', name: '程序表', purpose: '审计程序清单(走a-program-console)', sheetName: 'H2A 程序表' },
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
    if (key.startsWith(code)) return true
  }
  return false
}

function handleNavigate(row: SheetEntry) {
  emit('navigate-sheet', row.sheetName)
}
</script>

<style scoped>
.h2-tab-index { padding: 16px; font-size: 13px; }
.guide-area {
  background: linear-gradient(135deg, #e8f4fd 0%, #d4ecfb 100%);
  border-radius: 8px; padding: 16px; margin-bottom: 16px;
}
.guide-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
.guide-step { display: flex; align-items: center; gap: 6px; font-size: 13px; }
.step-num { font-weight: 700; color: var(--el-color-primary); min-width: 20px; }
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
