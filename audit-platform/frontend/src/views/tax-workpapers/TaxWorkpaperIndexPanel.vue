<template>
  <div class="tw-screen">
    <header class="tw-header">
      <span class="tw-header__code">索引</span>
      <h1 class="tw-header__title">税务底稿索引</h1>
      <span class="tw-header__note">{{ SHOWN_TAX_WORKPAPER_SHEETS.length }} 张 · 有 {{ presentCount }} · 无 {{ absentCount }}</span>
    </header>

    <div class="tw-toolbar">
      <button type="button" class="tw-button" :class="{ 'tw-button--on': hideAbsent }" @click="emit('toggle-hide')">
        {{ hideAbsent ? '显示全部底稿' : '隐藏标记为无的底稿' }}
      </button>

      <!-- 刷子：选中后在勾选列按住拖动连续涂写，159 张逐个点不现实 -->
      <span class="tw-brush">
        <span class="tw-brush__label">批量涂写</span>
        <button
          v-for="b in BRUSHES"
          :key="b.value"
          type="button"
          class="tw-brush__btn"
          :class="{ 'tw-brush__btn--on': brush === b.value }"
          @click="brush = brush === b.value ? null : b.value"
        >{{ b.label }}</button>
      </span>

      <span class="tw-toolbar__hint">
        {{ brush === null ? '点第三列切换：空白 → √ → ×。选刷子后可按住拖动连刷' : '在第三列按住向下拖动，经过的格子统一涂写' }}
      </span>
    </div>

    <section class="tw-panel">
      <div class="tw-index-scroll">
        <table class="tw-index" :class="{ 'tw-index--painting': brush !== null }">
          <thead>
            <tr>
              <th class="tw-index__code">索引号</th>
              <th>项目名称</th>
              <th class="tw-index__mark">有（√）<br />无（×）</th>
            </tr>
          </thead>
          <tbody>
            <template v-for="group in SHOWN_TAX_WORKPAPER_INDEX" :key="group.title">
              <!-- 分类行：不给勾选格，给整类批量按钮（按类粗刷再微调最省事） -->
              <tr class="tw-index__group">
                <td colspan="3">
                  {{ group.title }}
                  <span class="tw-index__count">{{ group.sheets.length }} 张</span>
                  <span class="tw-group-actions">
                    <button type="button" title="本类全标为有" @click="setGroup(group.sheets, 'present')">全√</button>
                    <button type="button" title="本类全标为无" @click="setGroup(group.sheets, 'absent')">全×</button>
                    <button type="button" title="清除本类标记" @click="setGroup(group.sheets, undefined)">清空</button>
                  </span>
                </td>
              </tr>
              <tr v-for="sheet in group.sheets" :key="sheet.code" class="tw-index__row">
                <td class="tw-index__code tw-index__link" @click="emit('open', sheet.code)">{{ sheet.code }}</td>
                <td class="tw-index__link" @click="emit('open', sheet.code)">{{ sheet.name }}</td>
                <!-- 勾选格：按下即涂、拖入也涂，不触发跳转 -->
                <td
                  class="tw-index__mark"
                  @mousedown.prevent="onCellDown(sheet.code)"
                  @mouseenter="painting && paint(sheet.code)"
                >
                  <span v-if="marks[sheet.code] === 'present'" class="tw-mark tw-mark--present">√</span>
                  <span v-else-if="marks[sheet.code] === 'absent'" class="tw-mark tw-mark--absent">×</span>
                  <span v-else class="tw-mark tw-mark--blank" />
                </td>
              </tr>
            </template>
          </tbody>
        </table>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
/**
 * 税务底稿索引页（移植自 CITAR WorkpaperIndexScreen）。
 * 列底稿页显示的全部表（含标为「无」的）：「无」的隐藏只作用于目录栏与页签，在这里藏掉就没法改回来了。
 * 不在底稿页显示的表（taxWorkpaperIndex 的 SHOWN_SHEET_CODES 之外）这里也不列。
 */
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { SHOWN_TAX_WORKPAPER_INDEX, SHOWN_TAX_WORKPAPER_SHEETS, isTaxWorkpaperShown, type TaxWorkpaperSheet } from './taxWorkpaperIndex'
import type { TaxWorkpaperMark, TaxWorkpaperMarkMap } from './taxWorkpaperMarks'

/** null = 单击模式（点一下循环三态） */
type Brush = TaxWorkpaperMark | 'clear' | null

const BRUSHES: { value: Exclude<Brush, null>; label: string }[] = [
  { value: 'present', label: '√ 有' },
  { value: 'absent', label: '× 无' },
  { value: 'clear', label: '清空' },
]

const props = defineProps<{
  marks: TaxWorkpaperMarkMap
  hideAbsent: boolean
}>()

const emit = defineEmits<{
  (e: 'open', code: string): void
  (e: 'toggle-mark', code: string): void
  (e: 'toggle-hide'): void
  /** mark 为 undefined 表示清除 */
  (e: 'set-marks', codes: string[], mark: TaxWorkpaperMark | undefined): void
}>()

const brush = ref<Brush>(null)
const painting = ref(false)

/** 只数显示的表：隐藏表以前打过的标记不计入 */
const countMarks = (mark: TaxWorkpaperMark) =>
  Object.keys(props.marks).filter(code => props.marks[code] === mark && isTaxWorkpaperShown(code)).length
const presentCount = computed(() => countMarks('present'))
const absentCount = computed(() => countMarks('absent'))

function paint(code: string) {
  if (brush.value === null) return
  emit('set-marks', [code], brush.value === 'clear' ? undefined : brush.value)
}

function onCellDown(code: string) {
  if (brush.value === null) {
    emit('toggle-mark', code)
    return
  }
  painting.value = true
  paint(code)
}

function setGroup(sheets: TaxWorkpaperSheet[], mark: TaxWorkpaperMark | undefined) {
  emit('set-marks', sheets.map(s => s.code), mark)
}

// 松开鼠标即结束拖动，即使松在表格外
function stopPainting() {
  painting.value = false
}
watch(painting, (on) => {
  if (on) window.addEventListener('mouseup', stopPainting)
  else window.removeEventListener('mouseup', stopPainting)
})
onBeforeUnmount(() => window.removeEventListener('mouseup', stopPainting))
</script>

<style scoped src="./taxWorkpaperScreen.css"></style>

<style scoped>
.tw-toolbar__hint {
  margin-left: 12px;
  font-size: var(--gt-font-size-xs);
  color: var(--tw-text-hint);
}

.tw-brush {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  margin-left: 14px;
  padding-left: 14px;
  border-left: 1px solid var(--tw-line-accent);
}

.tw-brush__label {
  margin-right: 2px;
  font-size: var(--gt-font-size-xs);
  color: var(--tw-text-muted);
}

.tw-brush__btn {
  padding: 5px 10px;
  border: 1px solid var(--tw-line-accent-strong);
  border-radius: 4px;
  background: var(--tw-surface);
  font: inherit;
  font-size: var(--gt-font-size-xs);
  color: var(--tw-accent-deep);
  cursor: pointer;
}

.tw-brush__btn:hover {
  background: var(--tw-accent-hover);
}

.tw-brush__btn--on {
  border-color: var(--tw-accent);
  background: var(--tw-accent);
  color: var(--tw-on-accent);
  font-weight: 700;
}

.tw-index-scroll {
  overflow-x: auto;
}

.tw-index {
  width: 100%;
  border-collapse: collapse;
  font-size: var(--gt-font-size-sm);
}

.tw-index thead th {
  position: sticky;
  top: 0;
  padding: 9px 12px;
  border-bottom: 1px solid var(--tw-line-accent-strong);
  background: var(--tw-th-bg);
  color: var(--tw-accent-deep);
  font-weight: 700;
  text-align: left;
}

.tw-index__code {
  width: 130px;
  white-space: nowrap;
}

.tw-index__group td {
  padding: 8px 12px;
  border-top: 1px solid var(--tw-line-accent);
  border-bottom: 1px solid var(--tw-line-accent);
  background: var(--tw-subnav-bg);
  color: var(--tw-accent-deep);
  font-weight: 700;
}

.tw-index__count {
  margin-left: 10px;
  font-size: var(--gt-font-size-xs);
  font-weight: 400;
  color: var(--tw-text-hint);
}

.tw-index__row td {
  padding: 7px 12px;
  border-bottom: 1px solid var(--tw-line-soft);
  color: var(--tw-text);
}

.tw-index__row:hover td {
  background: var(--tw-accent-hover);
  color: var(--tw-accent);
}

.tw-index__link {
  cursor: pointer;
}

.tw-index__mark {
  width: 86px;
  text-align: center;
  cursor: pointer;
  user-select: none;
}

.tw-index--painting .tw-index__mark {
  cursor: crosshair;
}

.tw-index thead .tw-index__mark {
  text-align: center;
  cursor: default;
  font-size: var(--gt-font-size-xs);
  line-height: 1.5;
}

.tw-mark {
  display: inline-block;
  min-width: 20px;
  font-size: var(--gt-font-size-base);
  font-weight: 700;
}

.tw-mark--present {
  color: var(--tw-mark-present);
}

.tw-mark--absent {
  color: var(--tw-mark-absent);
}

/* 空白态也要有点击区域 */
.tw-mark--blank::before {
  content: '·';
  color: var(--tw-line-strong);
}

.tw-group-actions {
  display: inline-flex;
  gap: 4px;
  margin-left: 14px;
}

.tw-group-actions button {
  padding: 2px 8px;
  border: 1px solid var(--tw-line-accent-strong);
  border-radius: 3px;
  background: var(--tw-surface);
  font: inherit;
  font-size: var(--gt-font-size-xs);
  font-weight: 400;
  color: var(--tw-accent);
  cursor: pointer;
  opacity: 0.55;
}

.tw-group-actions button:hover {
  border-color: var(--tw-accent);
  background: var(--tw-accent);
  color: var(--tw-on-accent);
}

/* 批量按钮平时半透明，悬停分类行才显眼 */
.tw-index__group:hover .tw-group-actions button {
  opacity: 1;
}
</style>
