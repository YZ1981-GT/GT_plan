<template>
  <div class="tw-screen">
    <header class="tw-header">
      <span class="tw-header__code">{{ code === TAX_RETURN_INDEX.cover.code ? '封面' : code }}</span>
      <h1 class="tw-header__title">{{ taxReturnName(code) }}</h1>
      <span class="tw-header__note">数据与税审底稿同一计算模型：底稿改动后申报表随之更新</span>
    </header>

    <div class="tw-toolbar">
      <button type="button" class="tw-button" :disabled="!dirty || saving" @click="discard">放弃修改</button>
      <button type="button" class="tw-button tw-button--primary" :disabled="!dirty || saving || !year" @click="save">
        {{ saving ? '保存中…' : '保存' }}
      </button>
      <button type="button" class="tw-button" :disabled="loadingValues || !year" @click="loadValues">重新计算</button>
      <button type="button" class="tw-button" :disabled="exporting || !year" @click="emit('export')">
        {{ exporting ? '导出中…' : '导出申报表（Excel）' }}
      </button>
      <span v-if="dirty" class="tw-toolbar__hint">有 {{ draftCount }} 处未保存的修改</span>
      <span v-if="!filed" class="tw-toolbar__hint">本表未勾选填报，导出时隐藏</span>
    </div>

    <div v-if="definition && result" class="tw-legend" aria-label="单元格说明">
      <span class="tw-legend__item tw-legend__item--formula">公式计算（取自底稿）</span>
      <span class="tw-legend__item tw-legend__item--input">手工修改</span>
      <span class="tw-legend__tip">点击任一金额格可修改；改过公式格后该格不再随底稿更新，编辑时可「恢复自动值」</span>
    </div>
    <div v-if="!canManualEdit" class="tw-alert">{{ MANUAL_EDIT_DENIED_TIP }}；手填格照常可填。</div>

    <div v-if="valuesError" class="tw-alert tw-alert--error">{{ valuesError }}</div>
    <div v-for="n in result?.notices ?? []" :key="n" class="tw-alert">{{ n }}</div>

    <section class="tw-panel">
      <div v-if="definition" class="tw-scroll" :class="{ 'tw-scroll--loading': loadingValues }">
        <TaxWorkpaperGrid
          v-for="part in definition.parts"
          :key="part.source"
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
      </div>
      <div v-else class="tw-pending">
        <p class="tw-pending__title">{{ loadState === 'error' ? '申报表加载失败，请刷新重试' : loadState === 'missing' ? '该表结构未生成' : '正在加载申报表…' }}</p>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
/**
 * 汇算申报表单表页：结构来自 sheets/<编号>.json，值来自后端（税审底稿同一计算模型）。
 * 手填格（如 A000000 投资方比例）点击即改，保存带版本号。
 */
import { ref, shallowRef, watch } from 'vue'
import TaxWorkpaperGrid from '@/views/tax-workpapers/TaxWorkpaperGrid.vue'
import type { TaxWorkpaperSheetDefinition } from '@/views/tax-workpapers/taxWorkpaperSheets'
import { useTaxSheetEditor } from '@/views/tax-workpapers/useTaxSheetEditor'
import { fetchTaxReturnSheet, saveTaxReturnSheet } from './taxReturnApi'
import { TAX_RETURN_INDEX, loadTaxReturnSheet, taxReturnName } from './taxReturnSheets'
import { MANUAL_EDIT_DENIED_TIP, useManualEditPermission } from '@/composables/useManualEditPermission'

const props = defineProps<{
  code: string
  projectId: string
  year: number | null
  filed: boolean
  exporting: boolean
}>()

const emit = defineEmits<{ (e: 'export'): void }>()
const { canManualEdit } = useManualEditPermission()

const definition = shallowRef<TaxWorkpaperSheetDefinition>()
const loadState = ref<'loading' | 'ready' | 'missing' | 'error'>('loading')

const {
  result, loadingValues, valuesError, drafts, saving, draftCount, dirty,
  partValues, loadValues, reset, setDraft, restore, restoredOf, save, discard,
} = useTaxSheetEditor({
  projectId: () => props.projectId,
  year: () => props.year,
  code: () => props.code,
  fetch: fetchTaxReturnSheet,
  save: saveTaxReturnSheet,
  label: '申报表',
})

watch(
  () => props.code,
  async (code) => {
    definition.value = undefined
    reset()
    loadState.value = 'loading'
    try {
      const loaded = await loadTaxReturnSheet(code)
      if (code !== props.code) return
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

defineExpose({ dirty })
</script>

<style scoped src="../tax-workpapers/taxWorkpaperScreen.css"></style>

<style scoped>
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

.tw-scroll {
  overflow-x: auto;
}

.tw-scroll--loading {
  opacity: 0.6;
}
</style>
