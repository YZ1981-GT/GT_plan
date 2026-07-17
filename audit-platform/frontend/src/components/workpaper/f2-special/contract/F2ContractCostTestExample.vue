<template>
  <div class="f2-cost-test-example" :class="{ compact }">
    <el-alert v-if="!compact" type="warning" :closable="false" show-icon class="example-banner">
      <template #title>编制参考示例（只读）</template>
      <p>
        本页为致同源模板「合同履约成本测试（示例）」结构化展示，<strong>非项目底稿</strong>。
        请在
        <el-tag size="small" type="info">F2-55A 实质性程序</el-tag>
        /
        <el-tag size="small" type="info">F2-56 检查表</el-tag>
        等实际底稿中参照执行；展开各底稿顶部的「编制参考示例」可边填边对照。
      </p>
    </el-alert>

    <header class="sheet-header">
      <div>
        <h3>{{ title }}</h3>
        <span class="code">参照示例</span>
      </div>
      <div class="meta-row">
        <span>被审计单位：ABC公司（示例）</span>
        <span>截止日：20XX年12月31日</span>
      </div>
    </header>

    <section class="section-block">
      <div class="section-label">一、审计目标</div>
      <ol class="objective-list">
        <li v-for="(obj, i) in objectives" :key="i">{{ obj }}</li>
      </ol>
    </section>

    <section class="section-block">
      <div class="section-label">二、审计过程</div>

      <h4 class="sub-title">（一）履约成本资本化判断</h4>
      <div class="table-scroll">
        <table class="matrix-table">
          <thead>
            <tr>
              <th class="sticky col-item">合同履约成本构成</th>
              <th>合同履约成本金额</th>
              <th>是否按履约成本资本化</th>
              <th>索引</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(row, i) in capRows" :key="i">
              <td class="sticky col-item">{{ row.component }}</td>
              <td class="num">{{ fmt(row.amount) }}</td>
              <td :class="{ 'cap-yes': row.capitalized === '是' }">{{ row.capitalized }}</td>
              <td>{{ row.indexRef || '—' }}</td>
            </tr>
            <tr class="row-total">
              <td class="sticky col-item">合计</td>
              <td class="num">{{ fmt(capTotal) }}</td>
              <td colspan="2" />
            </tr>
          </tbody>
        </table>
      </div>
      <p class="hint">资本化判断为「是」的项目，进入下表摊销测试。</p>

      <h4 class="sub-title">（二）摊销测试</h4>
      <div class="table-scroll">
        <table class="matrix-table wide">
          <thead>
            <tr>
              <th rowspan="2" class="sticky col-item">合同履约成本构成</th>
              <th rowspan="2">初始金额</th>
              <th rowspan="2">本期前已摊<br>销月份</th>
              <th rowspan="2">累计应摊<br>销月份</th>
              <th rowspan="2">摊销期限<br>（月）</th>
              <th rowspan="2" class="calc-col">测试本期<br>摊销金额</th>
              <th rowspan="2">账面本期<br>摊销金额</th>
              <th rowspan="2" class="calc-col">本期摊销<br>差异</th>
              <th rowspan="2" class="calc-col">累计应<br>摊销额</th>
              <th rowspan="2">账面累计<br>摊销额</th>
              <th rowspan="2" class="calc-col">累计摊销<br>差异</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(row, i) in amortRows" :key="i">
              <td class="sticky col-item">{{ row.component }}</td>
              <td class="num">{{ fmt(row.initialAmount) }}</td>
              <td class="num">{{ row.monthsBefore }}</td>
              <td class="num">{{ row.cumulativeMonths }}</td>
              <td class="num">{{ row.amortTerm }}</td>
              <td class="num calc calc-col">{{ fmt(row.testedPeriodAmort) }}</td>
              <td class="num">{{ fmt(row.bookPeriodAmort) }}</td>
              <td class="num calc calc-col" :class="{ 'diff-warn': Math.abs(row.periodVariance) > 0.01 }">
                {{ fmtSigned(row.periodVariance) }}
              </td>
              <td class="num calc calc-col">{{ fmt(row.cumulativeShouldAmort) }}</td>
              <td class="num">{{ fmt(row.bookCumulative) }}</td>
              <td class="num calc calc-col" :class="{ 'diff-warn': Math.abs(row.cumulativeVariance) > 0.01 }">
                {{ fmtSigned(row.cumulativeVariance) }}
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <section class="section-block formula-box">
      <div class="section-label">公式说明</div>
      <ul class="formula-list">
        <li v-for="f in formulas" :key="f.no">
          <span class="f-no">{{ f.no }}</span>
          <strong>{{ f.label }}：</strong>{{ f.formula }}
        </li>
      </ul>
    </section>

    <section class="section-block">
      <div class="section-label">三、审计说明（示例）</div>
      <div class="sample-note">
        经测试，资本化判断与设计服务、数据中心测试相关合同条款一致；摊销测算与账面记录基本一致，未见重大异常。
        （以上为示例文字，实际项目请替换为本公司结论。）
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

withDefaults(defineProps<{ compact?: boolean }>(), { compact: false })
import {
  F2_CONTRACT_COST_TEST_EXAMPLE_TITLE,
  F2_CONTRACT_COST_TEST_OBJECTIVES,
  F2_CONTRACT_COST_TEST_FORMULAS,
  CAPITALIZATION_EXAMPLE_ROWS,
  AMORTIZATION_EXAMPLE_ROWS,
  enrichAmortizationRows,
  sumCapitalization,
} from './f2ContractCostTestExampleData'

const title = F2_CONTRACT_COST_TEST_EXAMPLE_TITLE
const objectives = F2_CONTRACT_COST_TEST_OBJECTIVES
const formulas = F2_CONTRACT_COST_TEST_FORMULAS
const capRows = CAPITALIZATION_EXAMPLE_ROWS
const capTotal = sumCapitalization(capRows)

const amortRows = computed(() => enrichAmortizationRows(AMORTIZATION_EXAMPLE_ROWS))

function fmt(v: number): string {
  if (!Number.isFinite(v) || v === 0) return '—'
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function fmtSigned(v: number): string {
  if (!Number.isFinite(v) || v === 0) return '—'
  const s = v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
  return v > 0 ? s : `(${s.replace('-', '')})`
}
</script>

<style scoped>
.f2-cost-test-example {
  --gt-purple: #4b2d77;
  padding: 12px 16px;
  font-size: 13px;
}
.example-banner { margin-bottom: 14px; }
.example-banner p { margin: 6px 0 0; line-height: 1.6; font-size: 13px; }
.sheet-header { margin-bottom: 14px; }
.sheet-header h3 { margin: 0; font-size: 16px; display: inline; }
.code { font-size: 12px; color: #909399; margin-left: 8px; }
.meta-row { display: flex; gap: 16px; flex-wrap: wrap; margin-top: 6px; font-size: 12px; color: #606266; }

.section-block { margin-bottom: 16px; }
.section-label {
  font-size: 13px;
  font-weight: 600;
  color: var(--gt-purple);
  margin-bottom: 8px;
  padding-left: 8px;
  border-left: 3px solid var(--gt-purple);
}
.sub-title { font-size: 13px; font-weight: 600; margin: 12px 0 8px; color: #303133; }
.objective-list { margin: 0; padding-left: 1.4em; line-height: 1.7; }
.hint { font-size: 12px; color: #909399; margin: 6px 0 12px; }

.table-scroll { overflow-x: auto; margin-bottom: 8px; }
.matrix-table {
  width: 100%;
  border-collapse: separate;
  border-spacing: 0;
  font-size: 11px;
  min-width: 520px;
}
.matrix-table.wide { min-width: 1100px; }
.matrix-table th,
.matrix-table td {
  border: 1px solid #d4c8e0;
  padding: 6px 8px;
  text-align: center;
  vertical-align: middle;
  background: #fff;
}
.matrix-table thead th {
  background: var(--gt-purple);
  color: #fff;
  font-weight: 600;
  white-space: nowrap;
  font-size: 10px;
  line-height: 1.3;
}
.matrix-table th.calc-col { background: #6b4d8f; }
.sticky { position: sticky; left: 0; z-index: 2; background: #faf8fc !important; }
.col-item { min-width: 120px; text-align: left !important; }
.num { text-align: right !important; font-variant-numeric: tabular-nums; }
.calc { color: #4b2d77; font-weight: 500; background: #faf8fc !important; }
.cap-yes { color: #67c23a; font-weight: 600; }
.row-total td { background: #f0ebf5 !important; font-weight: 600; }
.diff-warn { color: #c45656; font-weight: 600; }

.formula-box { background: #fdf6ec; border-radius: 6px; padding: 12px 14px; border-left: 4px solid #e6a23c; }
.formula-list { margin: 0; padding-left: 0; list-style: none; }
.formula-list li { margin: 6px 0; font-size: 12px; line-height: 1.6; color: #5c4b28; }
.f-no { display: inline-block; min-width: 24px; font-weight: 700; color: #b88230; }

.sample-note {
  padding: 10px 12px;
  background: #f5f7fa;
  border-radius: 4px;
  font-size: 13px;
  line-height: 1.7;
  color: #606266;
}
.f2-cost-test-example.compact .sheet-header,
.f2-cost-test-example.compact .formula-box,
.f2-cost-test-example.compact .section-block:last-child {
  display: none;
}
.f2-cost-test-example.compact { padding: 0; }
</style>
