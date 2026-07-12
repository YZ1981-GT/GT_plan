<template>
  <div class="h1-tab-index">
    <!-- 顶部引导区 -->
    <div class="guide-area">
      <div class="guide-grid">
        <div class="guide-step"><span class="step-num">①</span> 审定表(H1-1)确认TB取数→三角勾稽→审定回写</div>
        <div class="guide-step"><span class="step-num">②</span> 明细表(H1-2)逐项登记→公式自动→交叉核对H1-1</div>
        <div class="guide-step"><span class="step-num">③</span> 检查表(H1-4~8)闲置/政策/增减/处置/权属/租赁</div>
        <div class="guide-step"><span class="step-num">④</span> 折旧(H1-12)+分配(H1-13)+减值(H1-14~15)</div>
        <div class="guide-step"><span class="step-num">⑤</span> 监盘(H1-9~11)计划/检查/小结</div>
        <div class="guide-step"><span class="step-num">⑥</span> 附注披露(H1-19/20)上市/国企版本</div>
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
        <el-table-column prop="code" label="编码" width="80" />
        <el-table-column prop="name" label="Sheet名称" min-width="220" />
        <el-table-column prop="purpose" label="用途说明" min-width="200" />
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
        <li>建议按序号顺序编制，H1-1→H1-2→检查→折旧→减值→附注</li>
        <li>H1-1审定表完成后自动回写TB，请确认科目1601/1602映射正确</li>
        <li>H1-12折旧测算有3个分支(不含减值/含减值/多次减值)，根据实际情况选一个</li>
        <li>附注有上市版/国企版，根据applicable_standards自动判断</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

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
  purpose: string
  completed: boolean
}

const sheets = computed<SheetEntry[]>(() => {
  const defs: Omit<SheetEntry, 'completed'>[] = [
    { seq: 1, code: 'H1', name: '底稿目录', purpose: '底稿结构导航与进度总览' },
    { seq: 2, code: 'H1-1', name: '审定表', purpose: '双区块(原值+折旧)三角勾稽+TB回写' },
    { seq: 3, code: 'H1-2', name: '明细表', purpose: '固定资产明细(54列4区段Tab)' },
    { seq: 4, code: 'H1-3', name: '调整分录', purpose: 'AJE/RJE录入+借贷平衡校验' },
    { seq: 5, code: 'H1-4', name: '闲置检查', purpose: '闲置资产登记+减值迹象判定' },
    { seq: 6, code: 'H1-5', name: '会计政策检查', purpose: 'CAS4六段落评价+折旧参数合理性' },
    { seq: 7, code: 'H1-6', name: '分析性程序', purpose: '结构分析+变动分析(8公式)' },
    { seq: 8, code: 'H1-7', name: '增加检查', purpose: '本期增加资产抽样检查+OCR+抽凭' },
    { seq: 9, code: 'H1-8', name: '减少检查', purpose: '处置/报废检查+损益计算+联动H10' },
    { seq: 10, code: 'H1-9', name: '监盘计划', purpose: '盘点范围/时间/人员/样本选取' },
    { seq: 11, code: 'H1-10', name: '盘点检查表', purpose: '实物盘点17列+盘盈盘亏登记' },
    { seq: 12, code: 'H1-11', name: '监盘小结', purpose: '仪表板+盘盈表+盘亏表+账实相符率' },
    { seq: 13, code: 'H1-12', name: '折旧测算', purpose: '3分支(不含减值/含减值/多次减值)' },
    { seq: 14, code: 'H1-13', name: '折旧分配', purpose: '制造/管理/销售费用分配+核对' },
    { seq: 15, code: 'H1-14', name: '减值测算', purpose: '迹象判断+可收回金额MAX选取' },
    { seq: 16, code: 'H1-15', name: '可收回金额', purpose: 'DCF模型+敏感性分析矩阵' },
    { seq: 17, code: 'H1-16', name: '房屋建筑物权属', purpose: '产权证核对(22列)+抵押统计' },
    { seq: 18, code: 'H1-17', name: '运输设备权属', purpose: '行驶证核对(18列)+年检状态' },
    { seq: 19, code: 'H1-18', name: '关联方交易', purpose: '关联方固定资产交易(15列)+价格差异' },
    { seq: 20, code: 'H1-19', name: '经营租出', purpose: '租赁详情(25列23公式)+收益率' },
    { seq: 21, code: 'H1-20', name: '融资租出', purpose: '5项分类判断+利息分摊(22列)' },
    { seq: 22, code: 'H1-disc-L', name: '附注-上市公司', purpose: '6子节+跨sheet取数+动态行' },
    { seq: 23, code: 'H1-disc-S', name: '附注-国企', purpose: '6子节+跨sheet取数+动态行' },
    { seq: 24, code: 'H1-3A', name: '调整分录汇总', purpose: '本底稿AJE/RJE汇总+推送A13' },
    { seq: 25, code: 'H1-6A', name: '分析备查', purpose: '异常变动追踪记录' },
    { seq: 26, code: 'H1A', name: '程序表', purpose: '审计程序清单(走a-program-console)' },
  ]
  return defs.map((d) => ({
    ...d,
    completed: _hasData(d.code),
  }))
})

const completedCount = computed(() => sheets.value.filter((s) => s.completed).length)
const completionPct = computed(() => Math.round((completedCount.value / sheets.value.length) * 100))

function _hasData(code: string): boolean {
  for (const [key] of props.allResponses) {
    if (key.startsWith(code)) return true
  }
  return false
}
</script>

<style scoped>
.h1-tab-index { padding: 16px; font-size: var(--wp-font-size, 13px); }
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
.compile-hint { margin-top: 12px; font-size: 12px; color: var(--el-text-color-secondary); }
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ul { padding-left: 20px; margin-top: 8px; }
</style>
