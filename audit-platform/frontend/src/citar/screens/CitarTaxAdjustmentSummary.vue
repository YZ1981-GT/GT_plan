<template>
  <div class="aud-screen">
    <header class="aud-header">
      <h1 class="aud-header__title">纳税调整汇总表</h1>
      <span class="aud-header__note">从二~五类税审底稿汇总纳税调整金额与免税、减计、加计审核确认额，并验算纳税调整后所得</span>
    </header>

    <section class="aud-panel">
      <p v-if="!year" class="sheet-empty">{{ yearLoading ? '正在读取项目信息…' : '项目未设置审核年度，请先在项目信息里填写' }}</p>
      <template v-else>
        <div class="citar-toolbar">
          <button class="citar-btn" type="button" :disabled="loading" @click="load">{{ loading ? '汇总中…' : '重新汇总' }}</button>
          <label class="citar-check"><input v-model="amountOnly" type="checkbox" /> 只看有金额的项</label>
          <span v-if="data" class="citar-toolbar__count">共 {{ data.items.length }} 项，其中有金额 {{ amountCount }} 项</span>
          <span class="citar-toolbar__hint">底稿或申报表改动后点「重新汇总」；点调整底稿位置打开该底稿并定位到格子</span>
        </div>

        <div v-for="n in data?.notices ?? []" :key="n" class="citar-notice">{{ n }}</div>
        <p v-if="loading && !data" class="sheet-empty">正在汇总纳税调整…</p>
        <p v-else-if="error" class="sheet-empty">{{ error }}</p>

        <template v-if="data">
          <table class="sheet-table">
            <thead>
              <tr>
                <th class="tas-col-seq">序号</th>
                <th>涉税调整项目</th>
                <th>调整账载科目</th>
                <th class="tas-col-dir">调整方向</th>
                <th class="tas-col-amount">调整金额</th>
                <th class="tas-col-loc">调整底稿位置</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(item, i) in shownItems" :key="item.index" :class="{ 'tas-zero': isZero(item), 'tas-excluded': item.excluded }">
                <td class="is-numeric">{{ i + 1 }}</td>
                <td :title="item.source">
                  {{ item.name }}
                  <span v-if="item.excluded" class="tas-tag" title="现阶段暂未包含境外所得部分，不计入下方验算">暂未计入</span>
                </td>
                <td>{{ item.account }}</td>
                <td class="tas-dir">{{ item.direction || '—' }}</td>
                <td class="is-numeric">{{ fmt(item.amount) }}</td>
                <td>
                  <a v-if="canOpen(item)" class="tas-link" href="#" :title="locTitle(item)" @click.prevent="openLocation(item)">{{ item.location?.code }}</a>
                  <span v-else :title="locTitle(item)">{{ item.location?.code ?? '—' }}</span>
                </td>
              </tr>
              <tr v-if="!shownItems.length">
                <td colspan="6" class="tas-empty">本年度二~五类底稿暂无纳税调整</td>
              </tr>
            </tbody>
          </table>

          <h2 class="tas-subtitle">纳税调整所得计算验证</h2>
          <table class="sheet-table tas-check">
            <tbody>
              <tr v-for="row in checkRows" :key="row.label" :class="row.cls">
                <td class="tas-check__op">{{ row.op }}</td>
                <td :title="row.hint">{{ row.label }}</td>
                <td class="is-numeric">{{ row.text ?? fmt(row.value) }}</td>
              </tr>
            </tbody>
          </table>
          <p class="tas-footnote">备注：现阶段暂未包含境外所得部分。</p>
        </template>
      </template>
    </section>
  </div>
</template>

<script setup lang="ts">
/**
 * 纳税调整汇总表（CITAR 税审底稿 · 纳税调整汇总表）：后端 GET /tax-workpapers/adjustment-summary 按规则汇总，只读。
 * - 二类（综合利润类）：底稿审核调整额，按对利润总额的影响记调增 / 调减；三类：申报表 A105000 各明细行（附表逐项）；
 *   五类：5-01-01 审核确认额，汇总成免税 / 减计 / 加计三行（名称统一「免税、减计收入及加计扣除」）；
 *   境外所得税纳税调整只列出、标「暂未计入」，不进验算。
 * - 没有金额的项也显示（用户 2026-11-05），可勾「只看有金额的项」；序号按当前显示的行重排。
 * - 调整底稿位置：点开税审底稿（或汇算申报表）并定位到格子；底稿目录里不显示的表只显示编号。
 */
import { computed, ref, watch } from 'vue'
import { savePendingTaxLocate, TAX_DOMAIN_SEGMENT } from '../cellSource'
import { useCitarProject } from '../useCitarProject'
import { isTaxWorkpaperShown } from '@/views/tax-workpapers/taxWorkpaperIndex'
import { fetchTaxAdjustmentSummary, type TaxAdjustmentItem, type TaxAdjustmentSummary } from '@/views/tax-workpapers/taxWorkpaperApi'

defineOptions({ name: 'CitarTaxAdjustmentSummary' })

const { projectId, year, yearLoading, goSegment } = useCitarProject()
const data = ref<TaxAdjustmentSummary | null>(null)
const loading = ref(false)
const error = ref('')
/** 默认没有金额的项也显示（用户 2026-11-05）；勾上只看有金额的 */
const amountOnly = ref(false)

const isZero = (item: TaxAdjustmentItem) => Math.abs(Number(item.amount) || 0) < 0.005
const amountCount = computed(() => (data.value?.items ?? []).filter(i => !isZero(i)).length)
const shownItems = computed(() => (data.value?.items ?? []).filter(i => !amountOnly.value || !isZero(i)))

let seq = 0
async function load() {
  if (!year.value) return
  const mine = ++seq
  loading.value = true
  error.value = ''
  try {
    const res = await fetchTaxAdjustmentSummary(projectId.value, year.value)
    if (mine === seq) data.value = res
  } catch (e: any) {
    if (mine === seq) error.value = e?.response?.data?.detail || e?.message || '汇总纳税调整失败'
  } finally {
    if (mine === seq) loading.value = false
  }
}

const MONEY = new Intl.NumberFormat('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
function fmt(v: string | null | undefined): string {
  const n = Number(v)
  return v == null || !Number.isFinite(n) ? '' : MONEY.format(n)
}

function canOpen(item: TaxAdjustmentItem): boolean {
  const loc = item.location
  if (!loc) return false
  return loc.domain === 'tax_return' || isTaxWorkpaperShown(loc.code)
}

function locTitle(item: TaxAdjustmentItem): string {
  const loc = item.location
  if (!loc) return item.source
  const where = `${loc.sheet} ${loc.ref}`
  return canOpen(item) ? `打开 ${where}` : `${where}（该底稿不在底稿目录中显示）`
}

function openLocation(item: TaxAdjustmentItem) {
  const loc = item.location
  if (!loc) return
  savePendingTaxLocate(projectId.value, { domain: loc.domain, code: loc.code, sheet: loc.sheet, ref: loc.ref })
  goSegment(TAX_DOMAIN_SEGMENT[loc.domain])
}

interface CheckRow { op: string; label: string; value?: string; text?: string; hint?: string; cls?: string }

const checkRows = computed<CheckRow[]>(() => {
  const c = data.value?.check
  if (!c) return []
  const line = (k: string) => `申报表 A100000 第 ${c.lines[k]} 行`
  const excluded = '暂未包含'
  const rows: CheckRow[] = [
    { op: '', label: '利润总额：', value: c.profit, hint: `${line('profit')} ${fmt(c.profit_declared)}，扣除上表综合利润类审核调整的影响` },
    { op: '减', label: '境外所得：', text: excluded, hint: `${line('foreign')} ${fmt(c.foreign)}，现阶段不计入`, cls: 'tas-muted' },
    { op: '加', label: '本期调增金额合计：', value: c.increase },
    { op: '减', label: '本期调减金额合计：', value: c.decrease },
    { op: '减', label: '本期免税金额合计：', value: c.exempt },
    { op: '减', label: '本期减计金额合计：', value: c.reduce },
    { op: '减', label: '本期加计金额合计：', value: c.plus },
    { op: '加', label: '境外应税所得抵减境内亏损：', text: excluded, hint: `${line('offset')} ${fmt(c.offset)}，现阶段不计入`, cls: 'tas-muted' },
    { op: '', label: '纳税调整后所得：', value: c.result, cls: 'level-total' },
  ]
  const same = Math.abs(Number(c.diff)) < 0.005
  rows.push({
    op: '',
    label: `与${line('result')}核对：`,
    text: same ? '一致' : `差 ${fmt(c.diff)}`,
    hint: `申报表纳税调整后所得 ${fmt(c.declared)}，剔除境外部分 ${fmt(c.declared_domestic)}`,
    cls: same ? 'tas-ok' : 'tas-warn',
  })
  return rows
})

watch([projectId, year], load, { immediate: true })
</script>

<style scoped src="../styles/audited.css"></style>
<style scoped src="../styles/unaudited.css"></style>
<style scoped src="../styles/citar-data.css"></style>

<style scoped>
.tas-col-seq { width: 56px; }
.tas-col-dir { width: 88px; }
.tas-col-amount { width: 150px; }
.tas-col-loc { width: 130px; }
.tas-dir { text-align: center; }
.tas-link { color: var(--citar-c-6e0ba6); text-decoration: underline; }
.tas-empty { text-align: center; color: var(--citar-c-5c5c68); }
.tas-zero td { color: var(--citar-c-5c5c68); }
.tas-excluded td { color: var(--citar-c-5c5c68); }
.tas-tag {
  margin-left: 6px;
  padding: 0 6px;
  border-radius: 3px;
  background: #f1f1f4;
  font-size: var(--citar-fs-11, 11px);
  color: var(--citar-c-5c5c68);
}
.tas-subtitle { margin: 24px 0 10px; font-size: var(--citar-fs-15, 15px); color: var(--citar-c-4c1273); }
.tas-check { max-width: 640px; }
.tas-check__op { width: 48px; text-align: center; }
.tas-muted td { color: var(--citar-c-5c5c68); }
.tas-ok td:last-child { color: #1d7a52; font-weight: 700; }
.tas-warn td:last-child { color: var(--citar-c-a3262a); font-weight: 700; }
.tas-footnote { margin: 10px 0 0; font-size: var(--citar-fs-13, 13px); color: var(--citar-c-5c5c68); }
</style>
