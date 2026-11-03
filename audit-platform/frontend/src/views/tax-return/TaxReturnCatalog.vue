<template>
  <nav class="tw-catalog" aria-label="申报表目录">
    <div class="tw-catalog__caption">
      <span>申报表表单</span>
      <label class="tr-catalog__toggle"><input v-model="showUnfiled" type="checkbox" /> 显示未填报</label>
    </div>

    <button
      type="button"
      class="tw-catalog__sheet tw-catalog__sheet--index"
      :class="{ 'tw-catalog__sheet--active': activeCode === TAX_RETURN_INDEX.cover.code }"
      @click="emit('open', TAX_RETURN_INDEX.cover.code)"
    >
      <span class="tw-catalog__sheet-code">封面</span>{{ TAX_RETURN_INDEX.cover.name }}
    </button>

    <div
      v-for="form in shownForms"
      :key="form.code"
      class="tr-catalog__row"
      :class="{ 'tr-catalog__row--unfiled': !filed[form.code], 'tr-catalog__row--active': activeCode === form.code }"
    >
      <input
        type="checkbox"
        class="tr-catalog__check"
        :checked="filed[form.code]"
        :disabled="readonly || saving"
        :title="filed[form.code] ? '已勾选填报（取消后导出时隐藏此表）' : '未填报（勾选后导出时包含此表）'"
        :aria-label="`${form.code} 是否填报`"
        @change="toggle(form.code, ($event.target as HTMLInputElement).checked)"
      />
      <button type="button" class="tw-catalog__sheet tr-catalog__sheet" @click="emit('open', form.code)">
        <span class="tw-catalog__sheet-code">{{ form.code }}</span>{{ form.name }}
      </button>
    </div>
  </nav>
</template>

<script setup lang="ts">
/**
 * 汇算申报表目录：按样表「表单」页列出全部表，勾选「是否填报」即保存（存为表单页 C 列的 √ / □）。
 * 未填报的表默认不列出（「显示未填报」可展开），导出时隐藏。
 */
import { computed, ref } from 'vue'
import { TAX_RETURN_INDEX } from './taxReturnSheets'

const props = defineProps<{
  activeCode: string
  /** 编号 → 是否填报（已合并样表默认与本项目保存值） */
  filed: Record<string, boolean>
  readonly: boolean
  saving: boolean
}>()

const emit = defineEmits<{
  (e: 'open', code: string): void
  (e: 'toggle', code: string, filed: boolean): void
}>()

const showUnfiled = ref(false)

/** 当前打开的表即使未填报也留在目录里 */
const shownForms = computed(() =>
  TAX_RETURN_INDEX.forms.filter(f => showUnfiled.value || props.filed[f.code] || f.code === props.activeCode),
)

function toggle(code: string, value: boolean) {
  emit('toggle', code, value)
}
</script>

<style scoped src="../tax-workpapers/taxWorkpaperCatalog.css"></style>

<style scoped>
.tw-catalog__caption {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.tr-catalog__toggle {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-weight: 400;
  color: var(--tw-text-muted);
  cursor: pointer;
}

.tr-catalog__row {
  display: flex;
  align-items: flex-start;
  border-left: 3px solid transparent;
  background: var(--tw-surface);
}

.tr-catalog__sheet {
  flex: 1 1 auto;
  padding-left: 8px;
  border-left: none;
  background: transparent;
}

.tr-catalog__check {
  flex: 0 0 auto;
  margin: 9px 0 0 10px;
  accent-color: var(--tw-accent);
}

.tr-catalog__row--active {
  border-left-color: var(--tw-accent);
  background: var(--tw-accent-soft);
}

.tr-catalog__row--unfiled .tr-catalog__sheet {
  color: var(--tw-text-faint);
}

.tr-catalog__row--active .tr-catalog__sheet {
  color: var(--tw-accent);
  font-weight: 700;
}
</style>
