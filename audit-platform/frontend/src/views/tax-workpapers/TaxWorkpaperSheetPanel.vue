<template>
  <div class="tw-screen">
    <!-- 编号不在索引里：是配置有误，不是表未植入，两者要分清 -->
    <div v-if="!sheet" class="tw-pending">
      <p class="tw-pending__title">索引中没有这个编号</p>
      <p class="tw-pending__hint">目录与 taxWorkpaperIndex 不一致，请检查配置。</p>
      <span class="tw-pending__code">{{ code }}</span>
    </div>

    <template v-else>
      <header class="tw-header">
        <span class="tw-header__code">{{ sheet.code }}</span>
        <h1 class="tw-header__title">{{ sheet.name }}</h1>
        <span v-if="group" class="tw-header__note">{{ group.title }}</span>
      </header>

      <!-- 同组切换：标签只显示编号（组内表名二十余字、最多 35 张，带名字排不开），表名放 title 悬停可见 -->
      <nav v-if="group && tabSheets.length > 1" class="tw-tabs" :aria-label="`${group.title} 表清单`">
        <button
          v-for="item in tabSheets"
          :key="item.code"
          type="button"
          class="tw-tab"
          :class="{ 'tw-tab--active': item.code === code }"
          :title="item.name"
          :aria-current="item.code === code ? 'page' : undefined"
          @click="openOther(item.code)"
        >
          {{ item.code }}
        </button>
      </nav>

      <div class="tw-toolbar">
        <button type="button" class="tw-button" disabled title="本期暂未开放">导入</button>
        <button type="button" class="tw-button" disabled title="本期暂未开放">导出</button>
        <button type="button" class="tw-button" :disabled="!dirty || saving" @click="discard">放弃修改</button>
        <button type="button" class="tw-button tw-button--primary" :disabled="!dirty || saving || !year" @click="save">
          {{ saving ? '保存中…' : '保存' }}
        </button>
        <button type="button" class="tw-button" :disabled="loadingValues || !year" @click="loadValues">{{ loadingValues ? '取数中…' : '智能取数' }}</button>
        <span v-if="dirty" class="tw-toolbar__hint">有 {{ draftCount }} 处未保存的修改</span>
      </div>

      <div v-if="definition && result" class="tw-legend" aria-label="单元格说明">
        <span class="tw-legend__item tw-legend__item--rule">智能取数</span>
        <span class="tw-legend__item tw-legend__item--confirm">取数待确认</span>
        <span class="tw-legend__item tw-legend__item--manual-rule">需人工填写</span>
        <span class="tw-legend__item tw-legend__item--input">手工修改</span>
        <span class="tw-legend__item tw-legend__item--formula">公式计算</span>
        <span class="tw-legend__tip">悬停单元格查看取数规则；取数格、公式格、预置数字都可点击修改，编辑时可「恢复自动值」</span>
      </div>
      <div v-if="!canManualEdit" class="tw-alert">{{ MANUAL_EDIT_DENIED_TIP }}；手填格与「需人工填写」的格子照常可填。</div>

      <div v-if="valuesError" class="tw-alert tw-alert--error">{{ valuesError }}</div>
      <div v-for="n in result?.notices ?? []" :key="n" class="tw-alert">{{ n }}</div>
      <details v-if="result && result.issues.length" class="tw-issues">
        <summary>{{ result.issues.length }} 个格子未取到数（点击查看原因）</summary>
        <ul>
          <li v-for="item in result.issues" :key="item.sheet + item.ref">
            <span class="tw-issues__ref">{{ item.ref }}</span>{{ item.message }}
          </li>
        </ul>
      </details>

      <section class="tw-panel">
        <div v-if="definition" class="tw-scroll" :class="{ 'tw-scroll--loading': loadingValues }">
          <template v-for="(part, partIndex) in definition.parts" :key="part.source">
            <h2 v-if="part.title" class="tw-part-title" :class="{ 'tw-part-title--gap': partIndex > 0 }">
              {{ part.title }}
            </h2>
            <TaxWorkpaperGrid
              :rows="part.rows"
              :values="partValues(part.source).values"
              :cells="partValues(part.source).cells"
              :drafts="drafts[part.source] ?? {}"
              :restored="restoredOf(part.source)"
              :readonly="!year || saving"
              :manual-edit="canManualEdit"
              @edit="(ref, value) => setDraft(part.source, ref, value)"
              @restore="(ref) => restore(part.source, ref)"
            />
          </template>
        </div>

        <div v-else-if="loadState === 'loading'" class="tw-pending">
          <p class="tw-pending__title">正在加载底稿…</p>
        </div>

        <div v-else-if="loadState === 'error'" class="tw-pending">
          <p class="tw-pending__title">底稿加载失败</p>
          <p class="tw-pending__hint">请刷新页面重试。</p>
          <span class="tw-pending__code">{{ sheet.code }}</span>
        </div>

        <div v-else class="tw-pending">
          <p class="tw-pending__title">该底稿待植入</p>
          <p class="tw-pending__hint">表格结构尚未录入，上传底稿样表后在此呈现。</p>
          <span class="tw-pending__code">{{ sheet.code }}</span>
        </div>
      </section>
    </template>
  </div>
</template>

<script setup lang="ts">
/**
 * 税务底稿单表页（移植自 CITAR WorkpaperScreen）。
 * 表结构来自 sheets/<编号>.json（懒加载）；值来自后端取数 + 公式计算（taxWorkpaperApi）。
 * 可填写格点击即改，修改先记草稿，点「保存」一次提交本表全部手工值（带版本号，冲突时提示刷新）。
 */
import { computed, ref, shallowRef, watch } from 'vue'
import TaxWorkpaperGrid from './TaxWorkpaperGrid.vue'
import { findTaxWorkpaperGroup, findTaxWorkpaperSheet, isTaxWorkpaperShown } from './taxWorkpaperIndex'
import { loadTaxWorkpaperSheet, type TaxWorkpaperSheetDefinition } from './taxWorkpaperSheets'
import { fetchTaxSheet, saveTaxSheet } from './taxWorkpaperApi'
import { useTaxSheetEditor } from './useTaxSheetEditor'
import { MANUAL_EDIT_DENIED_TIP, useManualEditPermission } from '@/composables/useManualEditPermission'

const props = defineProps<{
  code: string
  hiddenCodes: ReadonlySet<string>
  projectId: string
  year: number | null
}>()

const emit = defineEmits<{ (e: 'open', code: string): void }>()
const { canManualEdit } = useManualEditPermission()

const sheet = computed(() => findTaxWorkpaperSheet(props.code))
const group = computed(() => findTaxWorkpaperGroup(props.code))

/** 表格结构按编号懒加载；missing = 该编号尚未录入结构（显示「待植入」） */
const definition = shallowRef<TaxWorkpaperSheetDefinition>()
const loadState = ref<'loading' | 'ready' | 'missing' | 'error'>('loading')

/** 后端取数 + 计算结果、草稿与保存（与汇算申报表共用） */
const {
  result, loadingValues, valuesError, drafts, saving, draftCount, dirty,
  partValues, loadValues, reset, setDraft, restore, restoredOf, save, discard,
} = useTaxSheetEditor({
  projectId: () => props.projectId,
  year: () => props.year,
  code: () => props.code,
  fetch: fetchTaxSheet,
  save: saveTaxSheet,
  label: '底稿',
})

watch(
  () => props.code,
  async (code) => {
    definition.value = undefined
    reset()
    loadState.value = 'loading'
    try {
      const loaded = await loadTaxWorkpaperSheet(code)
      if (code !== props.code) return // 加载期间已切到别的表
      definition.value = loaded
      loadState.value = loaded ? 'ready' : 'missing'
    } catch {
      if (code === props.code) loadState.value = 'error'
    }
    if (code === props.code && definition.value) await loadValues()
  },
  { immediate: true },
)

watch(() => [props.projectId, props.year], () => {
  discard()
  if (definition.value) void loadValues()
})

/** 切表统一由父组件处理（有未保存修改时由父组件确认） */
function openOther(code: string) {
  if (code !== props.code) emit('open', code)
}

/** 父组件切表前读它判断是否需要确认 */
defineExpose({ dirty })

/** 页签：只列底稿页显示的表；当前表即使被标为「无」也留着 */
const tabSheets = computed(() =>
  (group.value?.sheets ?? []).filter(s =>
    isTaxWorkpaperShown(s.code) && (s.code === props.code || !props.hiddenCodes.has(s.code))),
)
</script>

<!-- 横幅 / 工具条 / 卡片 / 待植入提示与索引页共用；用 src 引入才会一并加作用域 -->
<style scoped src="./taxWorkpaperScreen.css"></style>

<style scoped>
.tw-tabs {
  display: flex;
  align-items: center;
  gap: 4px;
  margin-top: 18px;
  overflow-x: auto;
  overflow-y: hidden;
  border-bottom: 1px solid var(--tw-line-accent);
  scrollbar-width: thin;
}

.tw-tab {
  flex: 0 0 auto;
  padding: 9px 18px;
  border: none;
  border-bottom: 2px solid transparent;
  background: none;
  font: inherit;
  font-size: var(--gt-font-size-sm);
  color: var(--tw-text-muted);
  cursor: pointer;
  white-space: nowrap;
}

.tw-tab:hover {
  color: var(--tw-accent);
}

.tw-tab:focus-visible {
  outline: 2px solid var(--tw-accent);
  outline-offset: -2px;
}

.tw-tab--active {
  border-bottom-color: var(--tw-accent);
  color: var(--tw-accent);
  font-weight: 700;
}

.tw-toolbar__hint {
  font-size: var(--gt-font-size-xs);
  color: var(--tw-accent-deep);
}

.tw-legend {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px 14px;
  margin: 10px 0 0;
  font-size: var(--gt-font-size-xs);
  color: var(--tw-text-muted);
}

.tw-legend__item::before {
  content: "";
  display: inline-block;
  width: 12px;
  height: 12px;
  margin-right: 5px;
  vertical-align: -2px;
  border: 1px solid var(--tw-line-strong);
}

.tw-legend__item--rule::before { background: var(--tw-rule-auto-bg); }
.tw-legend__item--confirm::before { background: var(--tw-rule-confirm-bg); }
.tw-legend__item--manual-rule::before { background: var(--tw-rule-manual-bg); }
.tw-legend__item--input::before { background: var(--tw-manual-bg); }
.tw-legend__item--formula::before { background: var(--tw-formula-bg); }

.tw-alert {
  margin-top: 10px;
  padding: 8px 12px;
  border: 1px solid var(--tw-line-accent);
  background: var(--tw-accent-hover);
  font-size: var(--gt-font-size-sm);
  color: var(--tw-text);
}

.tw-alert--error {
  color: var(--tw-mark-absent);
}

.tw-issues {
  margin-top: 10px;
  font-size: var(--gt-font-size-sm);
  color: var(--tw-text-muted);
}

.tw-issues summary {
  cursor: pointer;
  color: var(--tw-accent-deep);
}

.tw-issues ul {
  max-height: 220px;
  margin: 6px 0 0;
  padding-left: 18px;
  overflow-y: auto;
}

.tw-issues__ref {
  display: inline-block;
  min-width: 56px;
  font-variant-numeric: tabular-nums;
  color: var(--tw-text);
}

/* 一个编号多段（如 1-01 封面 + 正文）时的段标题 */
.tw-part-title {
  margin: 0 0 10px;
  font-size: var(--gt-font-size-base);
  font-weight: 700;
  color: var(--tw-accent-deep);
}

.tw-part-title--gap {
  margin-top: 28px;
}

/* 横向滚动：底稿列数不可预知，宽表要能滚 */
.tw-scroll {
  overflow-x: auto;
}

.tw-scroll--loading {
  opacity: 0.6;
}
</style>
