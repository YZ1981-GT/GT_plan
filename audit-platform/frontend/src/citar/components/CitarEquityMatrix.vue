<template>
  <div class="sheet-scroll">
    <table class="sheet-table ra-matrix">
      <thead>
        <tr>
          <th class="ra-matrix__name">项　目</th>
          <th v-for="c in EQUITY_COLUMNS" :key="c.key">{{ c.label }}</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="r in rows" :key="r.row_code" :class="rowClass(r)">
          <td class="ra-matrix__name" :style="indentStyle(r)">{{ r.row_name }}</td>
          <td v-for="c in EQUITY_COLUMNS" :key="c.key" class="is-numeric">{{ fmtMoney(equityCell(r, c.key)) }}</td>
        </tr>
      </tbody>
    </table>
  </div>
  <p class="ra-footnote">本年金额。各列取报表生成时的权益矩阵；没有矩阵的行只在「所有者权益合计」列显示本行金额，其余列留空。</p>
</template>

<script setup lang="ts">
/** 所有者权益变动表矩阵（列 = 权益项目，行 = 变动原因）。数据见 useCitarReportAnalysis.equityCell。 */
import { fmtMoney } from '../useCitarProject'
import { EQUITY_COLUMNS, equityCell, type ReportRow } from '../useCitarReportAnalysis'

defineProps<{ rows: ReportRow[] }>()

function rowClass(r: ReportRow) {
  return !r.indent_level ? 'level-group' : ''
}

function indentStyle(r: ReportRow) {
  return { paddingLeft: `${10 + (r.indent_level || 0) * 12}px` }
}
</script>

<style scoped src="../styles/unaudited.css"></style>
<style scoped src="../styles/report-analysis.css"></style>
