<template>
  <section class="import-card ijd">
    <header class="ijd__head">
      <h2 class="ijd__title">导入记录</h2>
      <template v-if="view">
        <span class="citar-tag" :class="view.job.status === IMPORT_JOB_STATUS.COMPLETED ? 'citar-tag--approved' : 'citar-tag--draft'">{{ view.job.status_label }}</span>
        <span class="ijd__meta">{{ metaText }}</span>
      </template>
      <span class="ijd__actions">
        <button class="citar-btn" type="button" @click="emit('back')">返回账务查询</button>
        <button class="citar-btn citar-btn--primary" type="button" @click="emit('new-import')">开始新的导入</button>
      </span>
    </header>

    <p v-if="loading" class="sheet-empty">正在读取导入记录…</p>
    <p v-else-if="error" class="sheet-empty">{{ error }}</p>
    <template v-else-if="view">
      <p class="ijd__dataset">
        <template v-if="view.dataset">
          生成的数据集：<b>{{ view.dataset.status_label }}</b>
          <span v-for="r in view.dataset.records" :key="r.label" class="ijd__count">{{ r.label }} {{ r.count }} 行</span>
        </template>
        <template v-else>这次导入没有生成数据集。</template>
      </p>
      <p v-if="!view.file_retained" class="ijd__note">原文件已在导入后清理，下面是导入时确认的列映射（原表头 → 字段）。</p>
      <p v-if="!view.has_mapping_record" class="sheet-empty">这次导入没有保存列映射记录（旧导入或迁移来的数据）。</p>

      <div v-for="sh in view.sheets" :key="`${sh.file}|${sh.sheet}`" class="ijd__sheet">
        <h3 class="ijd__sheet-title">
          {{ sh.file }} · {{ sh.sheet }}
          <span class="citar-tag citar-tag--type">{{ sh.table_label }}</span>
          <span class="ijd__by">{{ sh.confirmed_by_user ? '用户确认' : '自动识别' }}</span>
        </h3>
        <table class="sheet-table ijd__table">
          <thead>
            <tr><th class="ijd__col-letter">列</th><th>原表头</th><th>映射为</th></tr>
          </thead>
          <tbody>
            <tr
              v-for="c in sh.columns"
              :key="`${c.locate}|${c.field}`"
              :data-locate="c.locate"
              :class="{ 'citar-located': isLocated(c.locate) }"
            >
              <td class="ijd__col-letter">{{ c.column_letter }}</td>
              <td>{{ c.header }}</td>
              <td>{{ c.field_label }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </template>
  </section>
</template>

<script setup lang="ts">
/**
 * 导入记录详情（只读，spec citar-cell-source-hover R9）：账务查询来源卡片点「文件 · sheet ·「表头」」跳来，
 * 按 ?locate=（后端给的定位键）高亮那一列的映射行。原文件导入后即清理，这里只有导入时确认的映射。
 */
import { computed, ref, toRef, watch } from 'vue'
import { api } from '@/services/apiProxy'
import { ledger as P_ledger } from '@/services/apiPaths'
import { IMPORT_JOB_STATUS } from '@/constants/statusEnum'
import { fmtDate } from '@/utils/formatters'
import { useCitarRowLocate } from '../useCitarRowLocate'

export interface ImportJobColumn {
  column_index: number | null
  column_letter: string
  header: string
  field: string
  field_label: string
  locate: string
}
export interface ImportJobSheet {
  file: string
  sheet: string
  table_type: string
  table_label: string
  confirmed_by_user: boolean
  columns: ImportJobColumn[]
}
export interface ImportJobView {
  job: { id: string; year: number; status: string; status_label: string; created_at: string | null; completed_at: string | null; created_by_name: string | null }
  dataset: { id: string; status: string; status_label: string; is_current: boolean; records: { label: string; count: number }[] } | null
  file_retained: boolean
  has_mapping_record: boolean
  sheets: ImportJobSheet[]
}

const props = defineProps<{ projectId: string; jobId: string; locate?: string }>()
const emit = defineEmits<{ (e: 'back'): void; (e: 'new-import'): void }>()

const view = ref<ImportJobView | null>(null)
const loading = ref(false)
const error = ref('')
const { isLocated, apply } = useCitarRowLocate(toRef(props, 'locate'))

const metaText = computed(() => {
  const j = view.value?.job
  if (!j) return ''
  return [j.created_at ? `${fmtDate(j.created_at)} 导入` : '', j.created_by_name ? `导入人 ${j.created_by_name}` : '', `${j.year} 年度`]
    .filter(Boolean).join(' · ')
})

async function load() {
  loading.value = true
  error.value = ''
  view.value = null
  try {
    view.value = (await api.get(P_ledger.import.jobMappings(props.projectId, props.jobId), { _silent: true } as any)) as ImportJobView
  } catch (e: any) {
    error.value = e?.response?.status === 404 ? '没有找到这次导入的记录（可能已被删除，或不属于本项目）' : '读取导入记录失败，请稍后重试'
  } finally {
    loading.value = false
  }
  const v = view.value
  if (v) {
    void apply(
      key => v.sheets.some(sh => sh.columns.some(c => c.locate === key)),
      undefined,
      '这次导入的映射里没有这一列（映射记录可能不完整）',
    )
  }
}

watch(() => [props.projectId, props.jobId], load, { immediate: true })
</script>

<style scoped src="../styles/unaudited.css"></style>
<style scoped src="../styles/citar-data.css"></style>
<style scoped src="../styles/data-import.css"></style>
<style scoped>
.ijd__head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px;
}

.ijd__title {
  margin: 0;
  font-size: var(--citar-fs-16);
  color: var(--citar-c-4c1273);
}

.ijd__meta,
.ijd__by {
  font-size: var(--citar-fs-13);
  color: var(--citar-c-8c8c96);
}

.ijd__actions {
  display: flex;
  gap: 8px;
  margin-left: auto;
}

.ijd__dataset {
  margin: 14px 0 0;
  font-size: var(--citar-fs-13);
  color: var(--citar-c-5c5c68);
}

.ijd__count {
  margin-left: 14px;
}

.ijd__note {
  margin: 8px 0 0;
  font-size: var(--citar-fs-12);
  color: var(--citar-c-8c8c96);
}

.ijd__sheet {
  margin-top: 18px;
}

.ijd__sheet-title {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0 0 8px;
  font-size: var(--citar-fs-14);
  color: var(--citar-c-3f3f4a);
}

.ijd__table {
  table-layout: fixed;
}

.ijd__col-letter {
  width: 56px;
  text-align: center;
}
</style>
