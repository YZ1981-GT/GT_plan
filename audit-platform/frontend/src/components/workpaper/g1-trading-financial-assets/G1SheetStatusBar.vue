<template>
  <section class="g1-status-panel" data-testid="g1-sheet-status">
    <header class="status-head">
      <h4>G 循环编制进度</h4>
      <p>闸门就绪 / 勾稽状态（基于已保存 checklist）</p>
    </header>
    <div class="status-grid">
      <div v-for="s in items" :key="s.code" class="status-card" :class="s.tone">
        <div class="code">{{ s.code }}</div>
        <div class="label">{{ s.label }}</div>
        <div class="flags">
          <el-tag v-if="s.gate != null" size="small" :type="s.gate ? 'success' : 'warning'" effect="plain">
            闸门 {{ s.gate ? '就绪' : '待办' }}
          </el-tag>
          <el-tag v-if="s.balance != null" size="small" :type="s.balance ? 'success' : 'danger'" effect="plain">
            勾稽 {{ s.balance ? '平' : '差' }}
          </el-tag>
          <el-tag v-if="s.gate == null && s.balance == null" size="small" type="info" effect="plain">
            {{ s.hint || '—' }}
          </el-tag>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { ChecklistResponse } from '../composables/useF1FormData'
import { DEFAULT_G1_GATES } from '../composables/useG1Detail'
import { DEFAULT_G1_INCOME_GATES } from '../composables/useG1IncomeCalc'
import { DEFAULT_G1_FV_GATES } from '../composables/useG1FairValueTest'
import { loadGatesJson } from '../composables/g1CrossHelpers'
import { parseNum } from '../composables/useG1TraFinFormulaEngine'

const props = defineProps<{
  allResponses: Map<string, ChecklistResponse>
}>()

function parseJson<T>(raw: string | undefined | null, fallback: T): T {
  if (!raw) return fallback
  try {
    return JSON.parse(raw) as T
  } catch {
    return fallback
  }
}

const items = computed(() => {
  const map = props.allResponses
  const g2 = loadGatesJson(map, 'G1-2-gates', DEFAULT_G1_GATES)
  const g2Ready =
    g2.inclusionReviewed &&
    g2.fraudRiskAssessed &&
    (!g2.fraudRiskFlag || !!String(g2.fraudResponse || '').trim())

  const g5 = loadGatesJson(map, 'G1-5-gates', DEFAULT_G1_INCOME_GATES)
  const g5Ready = g5.sampleCovered && g5.basisConfirmed && g5.accruedBoundaryNoted
  const recon = parseJson(map.get('G1-5-book-recon')?.conclusion, {
    bookInvestmentIncome: 0,
    bookAccruedInterest: 0,
  })
  const interestRows = parseJson<Array<{ interestSubtotal?: number }>>(
    map.get('G1-5-interest-rows')?.conclusion,
    [],
  )
  const interestTotal = interestRows.reduce((s, r) => s + parseNum(r.interestSubtotal), 0)
  const bookTotal = parseNum(recon.bookInvestmentIncome) + parseNum(recon.bookAccruedInterest)
  const g5Bal = Math.abs(interestTotal - bookTotal) < 0.01 || (!interestTotal && !bookTotal)

  const g6 = loadGatesJson(map, 'G1-6-gates', DEFAULT_G1_FV_GATES)
  const g6Rows = parseJson<Array<{ activeDiff?: number; bookValue?: number; testedValue?: number }>>(
    map.get('G1-6-rows')?.conclusion,
    [],
  )
  const g6HasL3 = g6Rows.some((r: any) => Number(r.fvLevel) === 3)
  const g6Ready =
    g6.levelPolicyReviewed &&
    g6.quoteSourceVerified &&
    (!g6HasL3 || g6.level3AssumptionsNoted)
  const g6Diff = g6Rows.reduce((s, r) => {
    if (r.activeDiff != null) return s + parseNum(r.activeDiff)
    return s + (parseNum(r.testedValue) - parseNum(r.bookValue))
  }, 0)
  const g6Bal = Math.abs(g6Diff) < 0.01 || g6Rows.length === 0

  const g1Has = !!map.get('G1-1-rows')?.remark
  const g2Has = !!map.get('G1-2-rows')?.conclusion
  const g4Has = !!map.get('G1-4-rows')?.conclusion

  return [
    {
      code: 'G1-1',
      label: '审定表',
      gate: null as boolean | null,
      balance: null as boolean | null,
      hint: g1Has ? '已有数据' : '未填',
      tone: g1Has ? 'ok' : 'idle',
    },
    {
      code: 'G1-2',
      label: '明细表',
      gate: g2Has ? g2Ready : null,
      balance: null,
      hint: g2Has ? undefined : '未填',
      tone: g2Has && g2Ready ? 'ok' : g2Has ? 'warn' : 'idle',
    },
    {
      code: 'G1-4',
      label: '结存表',
      gate: null,
      balance: null,
      hint: g4Has ? '已有数据' : '未填',
      tone: g4Has ? 'ok' : 'idle',
    },
    {
      code: 'G1-5',
      label: '收益测算',
      gate: g5Ready,
      balance: g5Bal,
      tone: g5Ready && g5Bal ? 'ok' : 'warn',
    },
    {
      code: 'G1-6',
      label: '公允测试',
      gate: g6Ready,
      balance: g6Bal,
      tone: g6Ready && g6Bal ? 'ok' : 'warn',
    },
  ]
})
</script>

<style scoped>
.g1-status-panel {
  margin: 12px 0 16px;
  padding: 12px 14px;
  border: 1px solid #e8ecf2;
  border-radius: 8px;
  background: #fafbfc;
}
.status-head h4 {
  margin: 0;
  font-size: 13px;
  font-weight: 600;
  color: #1f2a37;
}
.status-head p {
  margin: 2px 0 10px;
  font-size: 12px;
  color: #86909c;
}
.status-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
  gap: 8px;
}
.status-card {
  border: 1px solid #e4e7ed;
  border-radius: 6px;
  padding: 8px 10px;
  background: #fff;
}
.status-card.ok { border-color: #c6e8d4; background: #f0f9f4; }
.status-card.warn { border-color: #f0d9b8; background: #fff8f0; }
.status-card.idle { opacity: 0.85; }
.code { font-weight: 700; font-size: 12px; color: #303133; }
.label { font-size: 12px; color: #606266; margin: 2px 0 6px; }
.flags { display: flex; flex-wrap: wrap; gap: 4px; }
</style>
