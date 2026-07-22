<template>
  <div class="h2-tab-index">
    <!-- C7 前置摘要 -->
    <el-alert
      v-if="c7Hint"
      :type="c7Hint.type"
      :closable="false"
      show-icon
      class="c7-index-alert"
      :title="c7Hint.title"
    />

    <!-- 顶部引导区 -->
    <div class="guide-area">
      <div class="guide-grid">
        <div class="guide-step"><span class="step-num">①</span> 审定表(H2-1)确认原值/减值/净值→期初/期末审定→变动率≥30%说明→TB核对</div>
        <div class="guide-step"><span class="step-num">②</span> 明细表(H2-2)未审→调整→审定+利息子列+减值净值→交叉核对H2-1</div>
        <div class="guide-step"><span class="step-num">③</span> 分析表(H2-4)指标YoY+动态插行+工程进度/资本化/工期→阈值预警</div>
        <div class="guide-step"><span class="step-num">④</span> 转固检查(H2-5)挂账该转未转+已转时点→CAS4→联动H1</div>
        <div class="guide-step"><span class="step-num">⑤</span> 利息资本化(H2-10/11)无/有专门借款分支→加权计算（互斥）</div>
        <div class="guide-step"><span class="step-num">⑥</span> 监盘(H2-12~14)计划+检查+小结 / 减值(H2-15~16)DCF模型</div>
      </div>
    </div>

    <!-- 底稿目录表 -->
    <el-card shadow="never" class="index-card">
      <template #header>
        <div class="section-title">
          <span>底稿目录（适用 {{ progress.applicable }} / 共 {{ sheets.length }}）</span>
          <span class="completion-text">完成度 {{ progress.completed }}/{{ progress.applicable }}（{{ progress.pct }}%）</span>
        </div>
      </template>
      <el-progress :percentage="progress.pct" :stroke-width="8" class="completion-bar" />
      <el-table :data="sheets" stripe size="small" class="index-table" @row-click="handleNavigate">
        <el-table-column prop="seq" label="序号" width="50" align="center" />
        <el-table-column prop="code" label="编码" width="80" />
        <el-table-column prop="name" label="Sheet名称" min-width="200">
          <template #default="{ row }">
            <span class="sheet-link" :class="{ 'is-na': row.status === 'na' }">{{ row.name }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="purpose" label="用途说明" min-width="240" />
        <el-table-column label="状态" width="110" align="center">
          <template #default="{ row }">
            <el-tag :type="statusTagType(row.status)" size="small">
              {{ statusLabel(row.status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="说明" min-width="160">
          <template #default="{ row }">
            <span class="status-reason">{{ row.reason || '' }}</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 编制提示 -->
    <details class="compile-hint">
      <summary>编制提示</summary>
      <ul>
        <li>完成度分母为「适用」sheet（已排除 N/A）；H2-10/11 互斥，选一支后另一支标为不适用</li>
        <li>减值迹象&lt;2 项时 H2-16 可标 N/A；迹象≥2 项时 H2-16 为强制门禁，未完成则 H2-15/16 均待编制</li>
        <li>关键表（H2-1/2/5/15）需填审计结论才算完成；门禁阻断时不可用「未见异常」类减值结论</li>
        <li>H2-1审定表完成后自动回写TB科目1604，请确认科目映射正确</li>
        <li>转固(H2-5)完成后自动联动H1固定资产底稿；C7 控制失效时须扩大实质性程序</li>
        <li>附注有上市版/国企版，按项目 applicable_standards 自动判断适用版本（目录不适用项标 N/A）</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * H2TabIndex.vue — H2 在建工程底稿目录
 * 完成度 / 适用性 N/A（利息分支互斥、减值迹象、附注版本）
 * Spec: Task 4.1 | Requirements: 1.2
 */
import { computed, inject, type Ref } from 'vue'
import {
  resolveH2SheetStatus,
  summarizeH2IndexProgress,
  type H2SheetStatus,
} from '../../composables/h2IndexCompletion'
import type { H2C7PrerequisiteState } from '../../composables/useH2C7Prerequisite'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const emit = defineEmits<{
  (e: 'navigate-sheet', sheetName: string): void
}>()

const c7Injected = inject<Ref<H2C7PrerequisiteState> | undefined>('h2C7Prerequisite', undefined)

interface SheetEntry {
  seq: number
  code: string
  name: string
  purpose: string
  status: H2SheetStatus
  reason?: string
  sheetName: string
}

const SHEET_DEFS: Omit<SheetEntry, 'status' | 'reason'>[] = [
  { seq: 1, code: 'H2', name: '底稿目录', purpose: '底稿结构导航与进度总览', sheetName: 'H2 底稿目录' },
  { seq: 2, code: 'H2-1', name: '审定表', purpose: '原值/减值/净值+12列审定+TB核对+变动率≥30%', sheetName: 'H2-1 审定表' },
  { seq: 3, code: 'H2-2', name: '明细表', purpose: '未审→调整→审定+利息资本化+减值净值，勾稽H2-1', sheetName: 'H2-2 明细表' },
  { seq: 4, code: 'H2-3', name: '调整分录', purpose: 'Excel列结构+模块双向同步+1604回写H2-1+推送A13', sheetName: 'H2-3 调整分录' },
  { seq: 5, code: 'H2-4', name: '分析表', purpose: '指标YoY分析+动态插行/AI建议+工程进度/资本化/工期预警', sheetName: 'H2-4 分析表' },
  { seq: 6, code: 'H2-5', name: '转固时点检查', purpose: '双表：挂账该转未转+已转时点/CAS4+联动H1', sheetName: 'H2-5 转固时点检查' },
  { seq: 7, code: 'H2-6', name: '审核记录', purpose: '按工程核查(1-9节)+多项目汇总+弹窗填报', sheetName: 'H2-6 审核记录' },
  { seq: 8, code: 'H2-7', name: '造价比较', purpose: '单方造价vs可比价+现金流勾稽(|差异率|>15%高亮)', sheetName: 'H2-7 造价比较' },
  { seq: 9, code: 'H2-8', name: '增加检查', purpose: '按出包/自营/设备切换证据+关联方预埋(供H2-17)+OCR', sheetName: 'H2-8 增加检查' },
  { seq: 10, code: 'H2-9', name: '减少检查', purpose: '转固/其他减少+审批验收证据+检查比例勾稽H2-2+关联方预埋', sheetName: 'H2-9 减少检查' },
  { seq: 11, code: 'H2-10', name: '利息资本化(无专门借款)', purpose: '年加权利率+月度半月平均支出×月利率；与H2-11互斥', sheetName: 'H2-10 利息资本化无专门借款' },
  { seq: 12, code: 'H2-11', name: '利息资本化(有专门借款)', purpose: '专门借款−闲置收益+一般借款补充；可从H2-10带入', sheetName: 'H2-11 利息资本化有专门借款' },
  { seq: 13, code: 'H2-12', name: '监盘计划', purpose: '风险→了解→胜任→安排(范围/抽盘/双向抽查)→结论', sheetName: 'H2-12 监盘计划' },
  { seq: 14, code: 'H2-13', name: '盘点检查', purpose: '致同结构+双向抽盘三数量+进度/转固/停工+H2-15联动', sheetName: 'H2-13 盘点检查' },
  { seq: 15, code: 'H2-14', name: '监盘小结', purpose: '了解→盘前→人员/时间→逐项踏勘→总体核对→异常→结论', sheetName: 'H2-14 监盘小结' },
  { seq: 16, code: 'H2-15', name: '减值测算', purpose: 'CAS8六项迹象+按工程测算(③④⑤⑥⑦⑧)+H2-13/16联动', sheetName: 'H2-15 减值测算' },
  { seq: 17, code: 'H2-16', name: '可收回金额', purpose: '多工程组+公允/DCF/WACC+回写校验；上游H2-13/2容错', sheetName: 'H2-16 可收回金额' },
  { seq: 18, code: 'H2-17', name: '关联交易', purpose: '购售双表+工程服务+H8/9带入+A7勾稽', sheetName: 'H2-17 关联交易' },
  { seq: 19, code: 'H2-disc-L', name: '附注-上市公司', purpose: '多子节卡片+跨sheet取数+动态行', sheetName: 'H2-disc-L 附注上市' },
  { seq: 20, code: 'H2-disc-S', name: '附注-国企', purpose: '多子节卡片+跨sheet取数+动态行', sheetName: 'H2-disc-S 附注国企' },
  { seq: 21, code: 'H2A', name: '程序表', purpose: '审计程序清单(走a-program-console)+C7前置', sheetName: 'H2A 程序表' },
]

const sheets = computed<SheetEntry[]>(() => {
  return SHEET_DEFS.map((d) => {
    const { status, reason } = resolveH2SheetStatus(d.code, props.allResponses)
    return { ...d, status, reason }
  })
})

const progress = computed(() =>
  summarizeH2IndexProgress(
    SHEET_DEFS.map((d) => d.code),
    props.allResponses,
  ),
)

const c7Hint = computed(() => {
  const s = c7Injected?.value
  if (!s) return null
  if (s.needsExtended) {
    return { type: 'error' as const, title: 'C7 控制失效：请扩大实质性程序并在 H2A 记录应对' }
  }
  if (s.completed) {
    return { type: 'success' as const, title: `C7 前置已完成（${s.conclusion || '已记录'}）` }
  }
  return { type: 'info' as const, title: 'C7 控制测试前置未完成' }
})

function statusLabel(status: H2SheetStatus): string {
  if (status === 'completed') return '已完成'
  if (status === 'na') return '不适用'
  return '待编制'
}

function statusTagType(status: H2SheetStatus): 'success' | 'info' | 'warning' {
  if (status === 'completed') return 'success'
  if (status === 'na') return 'info'
  return 'warning'
}

function handleNavigate(row: SheetEntry) {
  emit('navigate-sheet', row.sheetName)
}
</script>

<style scoped>
.h2-tab-index { padding: 16px; font-size: var(--wp-font-size, 13px); }
.c7-index-alert { margin-bottom: 12px; }
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
.sheet-link.is-na { color: var(--el-text-color-secondary); text-decoration: line-through; }
.status-reason { font-size: 12px; color: var(--el-text-color-secondary); }
.compile-hint { margin-top: 12px; font-size: 12px; color: var(--el-text-color-secondary); }
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ul { padding-left: 20px; margin-top: 8px; }
</style>
