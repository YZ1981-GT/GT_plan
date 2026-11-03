<template>
  <div>
    <div class="sheet-caption">
      <h2 class="sheet-caption__title">{{ kind === 'balance_sheet' ? '资产负债表' : '利润表' }}</h2>
      <p class="sheet-caption__period">{{ periodText }}</p>
      <div class="sheet-caption__meta"><span>编制单位：{{ entityName }}</span><span>单位：人民币元</span></div>
    </div>

    <p v-if="loading" class="sheet-empty">正在读取报表…</p>
    <p v-else-if="error" class="sheet-empty">{{ error }}</p>

    <!-- 资产负债表：左资产、右负债和所有者权益（在「资产总计」行之后分栏） -->
    <div v-else-if="kind === 'balance_sheet' && sides.length === 2" class="balance-columns">
      <div v-for="side in sides" :key="side.heading" class="balance-columns__side">
        <p class="balance-columns__heading">{{ side.heading }}</p>
        <table class="sheet-table">
          <thead><tr><th>项　目</th><th>期末数</th><th>期初数</th></tr></thead>
          <tbody>
            <tr v-for="r in side.rows" :key="r.row_code" :class="rowClass(r)">
              <td :style="indentStyle(r)">{{ r.row_name }}</td>
              <td class="is-numeric">{{ fmtMoney(r.current_period_amount) }}</td>
              <td class="is-numeric">{{ fmtMoney(r.prior_period_amount) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <table v-else class="sheet-table">
      <thead>
        <tr>
          <th>项　目</th>
          <th>{{ kind === 'balance_sheet' ? '期末数' : '本期金额' }}</th>
          <th>{{ kind === 'balance_sheet' ? '期初数' : '上期金额' }}</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="r in rows" :key="r.row_code" :class="rowClass(r)">
          <td :style="indentStyle(r)">{{ r.row_name }}</td>
          <td class="is-numeric">{{ fmtMoney(r.current_period_amount) }}</td>
          <td class="is-numeric">{{ fmtMoney(r.prior_period_amount) }}</td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<script setup lang="ts">
/**
 * 资产负债表 / 利润表（CITAR 报表版式，数据来自平台 /api/reports）。
 * 行次、缩进、合计行都按平台报表配置返回的 indent_level / is_total_row 呈现。
 * 金额：null（未生成）留空，0 显示「-」—— 合计算成 0 要看得见，不能和「没数」混在一起。
 */
import { computed } from 'vue'
import { fmtMoney } from '../useCitarProject'

export interface CitarReportRow {
  row_code: string
  row_name: string
  current_period_amount: string | number | null
  prior_period_amount: string | number | null
  indent_level?: number | null
  is_total_row?: boolean | null
}

const props = defineProps<{
  kind: 'balance_sheet' | 'income_statement'
  rows: CitarReportRow[]
  year: number | null
  entityName: string
  loading?: boolean
  error?: string
}>()

const periodText = computed(() => {
  if (!props.year) return ''
  return props.kind === 'balance_sheet' ? `${props.year}年12月31日` : `${props.year}年度`
})

/** 资产总计之后（含）是负债和所有者权益；找不到就整表一栏 */
const sides = computed(() => {
  const idx = props.rows.findIndex(r => r.row_name.replace(/\s/g, '') === '资产总计')
  if (idx < 0 || idx === props.rows.length - 1) return []
  return [
    { heading: '资产', rows: props.rows.slice(0, idx + 1) },
    { heading: '负债和所有者权益', rows: props.rows.slice(idx + 1) },
  ]
})

function rowClass(r: CitarReportRow) {
  // 「资产总计」「负债和所有者权益总计」用总计底色，其余合计行用小计底色
  if (r.is_total_row) return /总计\s*$/.test(r.row_name) ? 'level-total' : 'level-subtotal'
  if (!r.indent_level) return 'level-group'
  return ''
}

/** 平台报表配置的缩进层级 → 首列左内边距（与 CITAR 原表的缩进步长一致） */
function indentStyle(r: CitarReportRow) {
  if (r.is_total_row) return undefined
  return { paddingLeft: `${10 + (r.indent_level || 0) * 12}px` }
}
</script>

<style scoped src="../styles/unaudited.css"></style>
