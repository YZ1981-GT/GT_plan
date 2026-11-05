<template>
  <section class="tw-params" aria-label="底稿表头信息">
    <header class="tw-params__head">
      <h2 class="tw-params__title">表头信息</h2>
      <span class="tw-params__hint">全部底稿的被审核单位、期间、编制人、复核人等取自这里；未填的默认取项目信息</span>
      <button v-if="canManualEdit" type="button" class="tw-button" @click="open = !open">{{ open ? '收起' : '编辑' }}</button>
    </header>

    <p v-if="!year" class="tw-params__empty">项目未设置审核年度，无法编辑表头信息。</p>
    <p v-else-if="error" class="tw-params__empty">{{ error }}</p>
    <div v-else-if="open && canManualEdit && params.length" class="tw-params__form">
      <label v-for="p in params" :key="p.ref" class="tw-params__field">
        <span class="tw-params__label">{{ p.label }}</span>
        <select v-if="p.options.length" v-model="form[p.ref]" :disabled="saving">
          <option value="">（未选择）</option>
          <option v-for="o in p.options" :key="o" :value="o">{{ o }}</option>
        </select>
        <input v-else v-model="form[p.ref]" type="text" :placeholder="p.default_value ?? ''" :disabled="saving" />
      </label>
      <div class="tw-params__actions">
        <button type="button" class="tw-button tw-button--primary" :disabled="saving || !changed" @click="save">
          {{ saving ? '保存中…' : '保存表头信息' }}
        </button>
      </div>
    </div>
    <p v-else-if="(!open || !canManualEdit) && summary" class="tw-params__summary">{{ summary }}</p>
  </section>
</template>

<script setup lang="ts">
/**
 * 税审底稿表头参数（样表「填写参数（无需打印）」页 B1~B15）。
 * 留空 = 取默认（被审核单位 = 客户名称、法定代表人 = 项目信息、期间 = 审核年度 + 「年度」）。
 */
import { computed, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { handleApiError } from '@/utils/errorHandler'
import { fetchTaxParams, saveTaxParams, type TaxParam } from './taxWorkpaperApi'
import { useManualEditPermission } from '@/composables/useManualEditPermission'

const props = defineProps<{ projectId: string; year: number | null }>()
const { canManualEdit } = useManualEditPermission()

const open = ref(false)
const params = ref<TaxParam[]>([])
const version = ref(0)
const form = ref<Record<string, string>>({})
const saving = ref(false)
const error = ref('')

function savedText(p: TaxParam): string {
  return p.saved && p.value !== null && p.value !== undefined ? String(p.value) : ''
}

const changed = computed(() => params.value.some(p => (form.value[p.ref] ?? '') !== savedText(p)))
const summary = computed(() => {
  const pick = (label: string) => params.value.find(p => p.label === label)?.value
  const parts = [pick('被审核单位'), pick('期间'), pick('底稿编制人') && `编制人 ${pick('底稿编制人')}`, pick('底稿复核人') && `复核人 ${pick('底稿复核人')}`]
  return parts.filter(Boolean).join(' · ')
})

function apply(data: { version: number; params: TaxParam[] }) {
  params.value = data.params
  version.value = data.version
  form.value = Object.fromEntries(data.params.map(p => [p.ref, savedText(p)]))
}

async function load() {
  error.value = ''
  if (!props.year || !props.projectId) return
  try {
    apply(await fetchTaxParams(props.projectId, props.year))
  } catch (e: any) {
    error.value = e?.response?.data?.detail || e?.message || '读取表头信息失败'
  }
}

async function save() {
  if (!props.year) return
  saving.value = true
  try {
    // 只提交填了的项；清空的项不提交即回到默认
    const values: Record<string, string> = {}
    for (const p of params.value) {
      const v = (form.value[p.ref] ?? '').trim()
      if (v) values[p.ref] = v
    }
    apply(await saveTaxParams(props.projectId, props.year, version.value, values))
    ElMessage.success('表头信息已保存')
  } catch (e: any) {
    if (e?.response?.status === 409) {
      ElMessage.warning('表头信息已被他人修改，已重新读取')
      await load()
    } else {
      handleApiError(e, '保存表头信息')
    }
  } finally {
    saving.value = false
  }
}

watch(() => [props.projectId, props.year], load, { immediate: true })
</script>

<style scoped src="./taxWorkpaperScreen.css"></style>

<style scoped>
.tw-params {
  margin-top: 16px;
  padding: 14px 20px;
  background: var(--tw-surface);
  border: 1px solid var(--tw-line);
  border-radius: 10px;
}

.tw-params__head {
  display: flex;
  align-items: center;
  gap: 12px;
}

.tw-params__title {
  margin: 0;
  font-size: var(--gt-font-size-base);
  font-weight: 700;
  color: var(--tw-accent-deep);
}

.tw-params__hint {
  flex: 1;
  font-size: var(--gt-font-size-xs);
  color: var(--tw-text-muted);
}

.tw-params__summary,
.tw-params__empty {
  margin: 8px 0 0;
  font-size: var(--gt-font-size-sm);
  color: var(--tw-text-muted);
}

.tw-params__form {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 10px 20px;
  margin-top: 12px;
}

.tw-params__field {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: var(--gt-font-size-sm);
}

.tw-params__label {
  flex: 0 0 150px;
  color: var(--tw-text);
}

.tw-params__field input,
.tw-params__field select {
  flex: 1;
  min-width: 0;
  height: 30px;
  padding: 0 8px;
  border: 1px solid var(--tw-line-strong);
  border-radius: 4px;
  font: inherit;
  color: var(--tw-text);
  background: var(--tw-surface);
}

.tw-params__actions {
  grid-column: 1 / -1;
}
</style>
