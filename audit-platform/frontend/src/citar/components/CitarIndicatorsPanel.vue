<template>
  <div>
    <div class="citar-toolbar">
      <div class="ra-seg" role="group" aria-label="财务指标">
        <button
          v-for="s in SECTIONS"
          :key="s.key"
          type="button"
          class="ra-seg__btn"
          :class="{ 'ra-seg__btn--active': section === s.key }"
          @click="section = s.key"
        >{{ s.label }}</button>
      </div>
      <div v-if="section === 'ratios'" class="ra-seg" role="group" aria-label="数据口径">
        <button
          v-for="m in MODES"
          :key="m.key"
          type="button"
          class="ra-seg__btn"
          :class="{ 'ra-seg__btn--active': mode === m.key }"
          @click="mode = m.key"
        >{{ m.label }}</button>
      </div>
      <span class="citar-toolbar__hint">{{ HINTS[section] }}</span>
    </div>

    <p v-if="loading" class="sheet-empty">正在读取…</p>
    <p v-else-if="error" class="sheet-empty">{{ error }}</p>

    <!-- 财务比率 -->
    <table v-else-if="section === 'ratios'" class="sheet-table">
      <thead><tr><th>指标</th><th>数值</th><th>分子</th><th>分母</th><th>说明</th></tr></thead>
      <tbody>
        <tr v-for="r in ratios" :key="r.name">
          <td>{{ r.name }}</td>
          <td class="is-numeric" :class="{ 'ra-alert': r.abnormal }">{{ r.value == null ? '—' : `${Number(r.value).toFixed(2)}${r.unit}` }}</td>
          <td><span class="ra-kv">{{ r.numerator?.label }}<b>{{ fig(r.numerator) }}</b></span></td>
          <td><span class="ra-kv">{{ r.denominator?.label }}<b>{{ fig(r.denominator) }}</b></span></td>
          <td class="ra-note">{{ r.note || (r.abnormal ? '偏离常见区间，请关注' : '') }}</td>
        </tr>
      </tbody>
    </table>

    <!-- 期初核对 -->
    <template v-else-if="section === 'opening'">
      <div v-if="opening && !opening.has_prior" class="citar-notice">{{ opening.reason || '没有上年项目' }}，无法核对期初。</div>
      <template v-else-if="opening">
        <div class="citar-notice" :class="{ 'ra-notice--ok': opening.reconciled }">
          {{ opening.reconciled ? '期初数与上年审定数一致' : `${opening.differences.length} 个科目期初数与上年审定数不一致` }}
          （{{ opening.matched }} / {{ opening.total_accounts }} 个科目一致）
        </div>
        <table v-if="opening.differences.length" class="sheet-table">
          <thead><tr><th>科目编码</th><th>科目名称</th><th>本年期初</th><th>上年审定</th><th>差异</th><th>说明</th></tr></thead>
          <tbody>
            <tr v-for="d in opening.differences" :key="d.account_code">
              <td>{{ d.account_code }}</td>
              <td>{{ d.account_name }}</td>
              <td class="is-numeric">{{ fmtMoney(d.current_opening) }}</td>
              <td class="is-numeric">{{ fmtMoney(d.prior_audited) }}</td>
              <td class="is-numeric ra-alert">{{ fmtMoney(d.difference) }}</td>
              <td>{{ d.note }}</td>
            </tr>
          </tbody>
        </table>
      </template>
    </template>

    <!-- 试算全景 -->
    <template v-else>
      <div v-if="balance" class="citar-notice" :class="{ 'ra-notice--ok': balance.balanced }">
        {{ balance.balanced
          ? `${balance.account_count} 个科目的审定数均由未审数与已记录的调整构成`
          : `${balance.unexplained.length} 个科目的审定数有说不清来源的差额（「其他调整」列），请核对` }}
      </div>
      <div class="sheet-scroll">
        <table class="sheet-table">
          <thead>
            <tr><th>科目编码</th><th>科目名称</th><th>未审数</th><th>AJE</th><th>RJE</th><th>底稿调整</th><th>其他调整</th><th>审定数</th></tr>
          </thead>
          <tbody>
            <tr v-for="r in fullTb" :key="r.account_code">
              <td>{{ r.account_code }}</td>
              <td>{{ r.account_name }}</td>
              <td class="is-numeric">{{ fmtMoney(r.unadjusted) }}</td>
              <td class="is-numeric">{{ fmtMoney(r.aje_adjustment) }}</td>
              <td class="is-numeric">{{ fmtMoney(r.rje_adjustment) }}</td>
              <td class="is-numeric">{{ fmtMoney(r.wp_adjustment) }}</td>
              <td class="is-numeric" :class="{ 'ra-alert': !r.balance_ok }">{{ fmtMoney(r.other_adjustment) }}</td>
              <td class="is-numeric">{{ fmtMoney(r.audited) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <p v-if="!fullTb.length" class="sheet-empty">本年度试算表还没有数据。</p>
    </template>
  </div>
</template>

<script setup lang="ts">
/**
 * 财务指标（旧报表页「分析」标签的三个子页）：财务比率 / 期初核对 / 试算全景。
 * 端点见 apiPaths.reports.analysis（项目只读成员可用）。
 */
import { ref, watch } from 'vue'
import { api } from '@/services/apiProxy'
import { reports as P_rpt } from '@/services/apiPaths'
import { fmtMoney } from '../useCitarProject'
import { errorText, silent, toNumber } from '../useCitarReportAnalysis'

type Section = 'ratios' | 'opening' | 'full_tb'

const props = defineProps<{ projectId: string; year: number }>()

const SECTIONS: { key: Section; label: string }[] = [
  { key: 'ratios', label: '财务比率' },
  { key: 'opening', label: '期初核对' },
  { key: 'full_tb', label: '试算全景' },
]
const MODES = [
  { key: 'audited', label: '审定' },
  { key: 'unadjusted', label: '未审' },
] as const
const HINTS: Record<Section, string> = {
  ratios: '周转率与净资产收益率的分母取期初期末平均；对应 A2-1 / A2-2 分析性程序',
  opening: '本年试算表期初数 vs 上年项目审定数（上年项目按企业代码与审计年度查找）',
  full_tb: '审定数 = 未审数 + AJE + RJE + 底稿调整；「其他调整」非 0 表示审定数有说不清来源的差额',
}

const section = ref<Section>('ratios')
const mode = ref<'audited' | 'unadjusted'>('audited')
const loading = ref(false)
const error = ref('')
const ratios = ref<any[]>([])
const opening = ref<any>(null)
const balance = ref<any>(null)
const fullTb = ref<any[]>([])

function fig(f: any): string {
  if (!f) return ''
  const n = toNumber(f.amount)
  return n === null ? '—' : fmtMoney(n, '0.00')
}

/** 只有最新一次读取写回页面：快速切换时，同参数的旧请求会被 GET 去重取消，晚到的错误不得盖住新结果 */
let loadSeq = 0

async function load() {
  const seq = ++loadSeq
  loading.value = true
  error.value = ''
  const pid = props.projectId
  const y = props.year
  try {
    if (section.value === 'ratios') {
      const data = await api.get(P_rpt.analysis.ratios(pid, y), { params: { mode: mode.value }, ...silent })
      if (seq !== loadSeq) return
      ratios.value = Array.isArray(data) ? data : []
    } else if (section.value === 'opening') {
      const data = await api.get(P_rpt.analysis.openingReconcile(pid, y), silent)
      if (seq !== loadSeq) return
      opening.value = data
    } else {
      const [view, check] = await Promise.all([
        api.get(P_rpt.analysis.fullTb(pid, y), silent),
        api.get(P_rpt.analysis.balanceCheck(pid, y), silent),
      ])
      if (seq !== loadSeq) return
      fullTb.value = Array.isArray(view) ? view : []
      balance.value = check
    }
  } catch (e: any) {
    if (seq !== loadSeq) return
    error.value = errorText(e, '读取失败')
  } finally {
    if (seq === loadSeq) loading.value = false
  }
}

watch([() => props.projectId, () => props.year, section, mode], load, { immediate: true })
</script>

<style scoped src="../styles/unaudited.css"></style>
<style scoped src="../styles/citar-data.css"></style>
<style scoped src="../styles/report-analysis.css"></style>
