<template>
  <div
    v-if="state.visible"
    ref="rootRef"
    class="src-card"
    role="tooltip"
    data-cell-source-card
    :style="position"
    @mouseenter="emit('enter')"
    @mouseleave="emit('leave')"
  >
    <header class="src-card__head">
      <span class="src-card__kind" :class="`src-card__kind--${kind}`">{{ KIND_LABELS[kind] }}</span>
      <span v-if="label" class="src-card__label">{{ label }}</span>
      <span v-if="shownValue !== ''" class="src-card__value">{{ shownValue }}</span>
    </header>

    <p v-if="state.loading && !src" class="src-card__muted">正在读取数据来源…</p>
    <p v-else-if="state.error && !src" class="src-card__issue">{{ state.error }}</p>

    <template v-if="src">
      <p class="src-card__title">{{ src.title }}</p>

      <div v-if="src.manual" class="src-card__manual">
        <div>手工值 <b>{{ amount(src.manual.value) }}</b>，自动值 {{ amount(src.manual.auto) || '空' }}<template v-if="manualGap">（差 {{ manualGap }}）</template></div>
        <div v-if="src.manual.by_name || src.manual.at" class="src-card__muted">
          {{ [src.manual.by_name, fmtTime(src.manual.at)].filter(Boolean).join(' · ') }}{{ src.manual.note ? `（${src.manual.note}）` : '' }}
        </div>
        <div v-if="src.items.length" class="src-card__muted">以下为自动值的构成</div>
      </div>

      <ul v-if="counted.length" class="src-card__items">
        <li v-for="(it, i) in counted" :key="i" class="src-card__item">
          <span class="src-card__sign">{{ signText(it.sign) }}</span>
          <span class="src-card__name">
            <button v-if="it.link" type="button" class="src-card__link" @click="emit('open', it.link)">{{ it.label }}</button>
            <template v-else>{{ it.label }}</template>
            <span v-if="it.detail" class="src-card__detail">{{ it.detail }}</span>
          </span>
          <span class="src-card__amount">{{ amount(it.amount) }}</span>
        </li>
      </ul>
      <p v-if="src.more" class="src-card__muted">另有 {{ src.more }} 项未列出（已计入合计）</p>

      <div v-if="src.linear && counted.length > 1" class="src-card__total" :class="{ 'src-card__total--bad': src.diff }">
        合计 {{ amount(src.total) }}
        <template v-if="src.diff">，与格值差 {{ amount(src.diff) }}</template>
        <template v-else>＝ 格值</template>
      </div>
      <p v-else-if="src.linear && src.diff" class="src-card__issue">构成合计 {{ amount(src.total) }}，与格值差 {{ amount(src.diff) }}</p>

      <p v-for="n in src.notes" :key="n" class="src-card__note">{{ n }}</p>
      <ul v-if="excluded.length" class="src-card__items src-card__items--excluded">
        <li v-for="(it, i) in excluded" :key="i" class="src-card__item">
          <span class="src-card__sign" />
          <span class="src-card__name">
            <button v-if="it.link" type="button" class="src-card__link" @click="emit('open', it.link)">{{ it.label }}</button>
            <template v-else>{{ it.label }}</template>
            <span v-if="it.detail" class="src-card__detail">{{ it.detail }}</span>
          </span>
          <span class="src-card__amount">{{ amount(it.amount) }}</span>
        </li>
      </ul>
      <p v-if="src.issue" class="src-card__issue">{{ src.issue }}</p>
      <details v-if="src.rule_text" class="src-card__rule">
        <summary>样表取数规则</summary>
        <p>{{ src.rule_text }}</p>
      </details>
      <p v-if="src.hint" class="src-card__hint">{{ src.hint }}</p>
    </template>
  </div>
</template>

<script setup lang="ts">
/**
 * 单元格来源卡片（spec citar-cell-source-hover R1）：纯展示，位置由锚点格子算（position: fixed，视口内翻转）。
 * 不 Teleport：--citar-* / --tw-* 变量只在页面根下生效，挂在页面里才取得到；颜色都给了回退值。
 * 链接点击经 open 事件交回页面（跳页、离开前确认由页面处理）。
 */
import { computed, nextTick, ref, watch } from 'vue'
import { KIND_LABELS, signText, type CellSourceItem, type CellSourceLink } from '../cellSource'
import type { CellSourceCardState } from '../useCellSourceHover'
import { fmtMoney } from '../useCitarProject'

const props = defineProps<{
  state: CellSourceCardState
  /** 格子名称（表 · 行 · 列），页面给 */
  label?: string
}>()

const emit = defineEmits<{ open: [link: CellSourceLink]; enter: []; leave: [] }>()

const rootRef = ref<HTMLElement | null>(null)
const placed = ref<{ left: number; top: number } | null>(null)

const src = computed(() => props.state.source)
const kind = computed(() => src.value?.kind ?? 'none')
const counted = computed<CellSourceItem[]>(() => (src.value?.items ?? []).filter(i => Number(i.sign ?? 1) !== 0))
const excluded = computed<CellSourceItem[]>(() => (src.value?.items ?? []).filter(i => Number(i.sign ?? 1) === 0))

/** 数字按会计格式，文字原样 */
function amount(v: string | null | undefined): string {
  if (v === null || v === undefined || v === '') return ''
  return Number.isFinite(Number(v)) ? fmtMoney(v, '0.00') : v
}

const shownValue = computed(() => amount(src.value?.manual?.value ?? src.value?.value ?? null))

const manualGap = computed(() => {
  const m = src.value?.manual
  if (!m) return ''
  const a = Number(m.value ?? 0)
  const b = Number(m.auto ?? 0)
  if (!Number.isFinite(a) || !Number.isFinite(b) || Math.abs(a - b) < 0.005) return ''
  return fmtMoney(a - b, '0.00')
})

function fmtTime(at: string | null | undefined): string {
  if (!at) return ''
  const d = new Date(at)
  if (Number.isNaN(d.getTime())) return at
  const p = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`
}

const GAP = 6
const MARGIN = 8

/** 先放在格子下方；渲染后量高度，下方放不下翻到上方，右侧溢出左移 */
watch(() => [props.state.visible, props.state.anchor, props.state.source, props.state.loading], async () => {
  const a = props.state.anchor
  if (!props.state.visible || !a) {
    placed.value = null
    return
  }
  placed.value = { left: a.left, top: a.bottom + GAP }
  await nextTick()
  const el = rootRef.value
  if (!el) return
  const w = el.offsetWidth
  const h = el.offsetHeight
  const vw = window.innerWidth
  const vh = window.innerHeight
  const left = Math.max(MARGIN, Math.min(a.left, vw - w - MARGIN))
  let top = a.bottom + GAP
  if (top + h > vh - MARGIN && a.top - GAP - h >= MARGIN) top = a.top - GAP - h
  placed.value = { left, top: Math.max(MARGIN, top) }
}, { immediate: true })

const position = computed(() => placed.value ? { left: `${placed.value.left}px`, top: `${placed.value.top}px` } : undefined)
</script>

<style scoped>
.src-card {
  position: fixed;
  z-index: 3000;
  width: 420px;
  max-width: calc(100vw - 16px);
  max-height: 60vh;
  overflow-y: auto;
  padding: 10px 12px;
  border: 1px solid var(--citar-c-d7c3ee, #d7c3ee);
  border-radius: 8px;
  background: #fff;
  box-shadow: 0 6px 24px rgba(76, 18, 115, 0.16);
  font-size: 12px;
  line-height: 1.6;
  color: #2b2b33;
  text-align: left;
  white-space: normal;
}

.src-card__head {
  display: flex;
  align-items: baseline;
  gap: 8px;
  margin-bottom: 4px;
}

.src-card__kind {
  flex: 0 0 auto;
  padding: 0 6px;
  border-radius: 4px;
  background: #f1e7fb;
  color: #5b2a86;
  font-size: 11px;
}

.src-card__kind--rule { background: #e3f5ee; color: #0b6e4f; }
.src-card__kind--manual { background: #f6efff; color: #6e0ba6; }
.src-card__kind--import { background: #eef3fb; color: #2a4f86; }
.src-card__kind--adjustment { background: #fdf0dc; color: #8a5300; }

.src-card__label {
  flex: 1 1 auto;
  min-width: 0;
  overflow: hidden;
  font-weight: 700;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.src-card__value {
  flex: 0 0 auto;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
}

.src-card__title {
  margin: 0 0 6px;
  overflow-wrap: anywhere;
  color: #4c1273;
}

.src-card__manual {
  margin-bottom: 6px;
  padding: 4px 8px;
  border-radius: 4px;
  background: #f6efff;
}

.src-card__items {
  margin: 0;
  padding: 0;
  list-style: none;
}

.src-card__items--excluded {
  opacity: 0.8;
}

.src-card__item {
  display: flex;
  align-items: baseline;
  gap: 6px;
  padding: 2px 0;
  border-bottom: 1px dashed #eee;
}

.src-card__sign {
  flex: 0 0 34px;
  color: #6b6b76;
  text-align: center;
}

.src-card__name {
  flex: 1 1 auto;
  min-width: 0;
  overflow-wrap: anywhere;
}

.src-card__detail {
  display: block;
  color: #8a8a96;
  font-size: 11px;
}

.src-card__amount {
  flex: 0 0 auto;
  font-variant-numeric: tabular-nums;
}

.src-card__link {
  padding: 0;
  border: none;
  background: none;
  font: inherit;
  color: #6e0ba6;
  text-align: left;
  cursor: pointer;
}

.src-card__link:hover {
  text-decoration: underline;
}

.src-card__total {
  margin-top: 4px;
  font-weight: 700;
  text-align: right;
  color: #0b6e4f;
}

.src-card__total--bad,
.src-card__issue {
  color: #a3262a;
}

.src-card__note,
.src-card__issue,
.src-card__hint,
.src-card__muted {
  margin: 4px 0 0;
}

.src-card__note {
  color: #5c5c68;
}

.src-card__muted {
  color: #8a8a96;
}

.src-card__hint {
  padding-top: 4px;
  border-top: 1px solid #f0eaf7;
  color: #6e0ba6;
}

.src-card__rule {
  margin-top: 4px;
  color: #5c5c68;
}

.src-card__rule summary {
  cursor: pointer;
  color: #6e0ba6;
}

.src-card__rule p {
  margin: 4px 0 0;
}
</style>
