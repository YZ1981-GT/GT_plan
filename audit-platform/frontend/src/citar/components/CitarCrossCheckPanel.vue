<template>
  <div>
    <div class="citar-toolbar">
      <span class="citar-toolbar__count">{{ summary }}</span>
      <button class="citar-btn" type="button" :disabled="loading" @click="load">{{ loading ? '核对中…' : '重新核对' }}</button>
      <span class="citar-toolbar__hint">按审定报表核对；报表重新生成后请重新核对</span>
    </div>

    <p v-if="loading && !rows.length" class="sheet-empty">正在核对…</p>
    <p v-else-if="error" class="sheet-empty">{{ error }}</p>
    <p v-else-if="noResult" class="sheet-empty">审定报表尚未生成，没有可核对的数据。请先在「资产负债表」标签生成报表。</p>
    <table v-else class="sheet-table">
      <thead>
        <tr><th class="ra-col-seq">#</th><th>核对项</th><th>参与比较的数</th><th class="ra-col-status">结果</th></tr>
      </thead>
      <tbody>
        <tr v-for="(r, i) in rows" :key="r.formula_id">
          <td class="is-numeric">{{ i + 1 }}</td>
          <td>{{ r.description }}</td>
          <td>
            <span v-for="v in r.values" :key="v.key" class="ra-kv">
              {{ v.label }}<b>{{ v.amount === null ? '—' : fmtMoney(v.amount, '0.00') }}</b>
            </span>
          </td>
          <td class="citar-center">
            <span class="citar-tag" :class="r.passed ? 'citar-tag--approved' : 'citar-tag--rejected'">
              {{ r.passed ? '通过' : '不通过' }}
            </span>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<script setup lang="ts">
/**
 * 跨表核对：GET /api/projects/{pid}/formula/report-cross-check（公式管理表间审核同一入口，
 * 内置 7 条勾稽 + 用户规则）。每次执行会记一条运行留痕，故只在进入本页与点「重新核对」时执行。
 */
import { computed, ref, watch } from 'vue'
import { fmtMoney } from '../useCitarProject'
import { errorText, fetchCrossCheck, type CrossCheckRow } from '../useCitarReportAnalysis'

const props = defineProps<{ projectId: string; year: number }>()

const rows = ref<CrossCheckRow[]>([])
const noResult = ref(false)
const loading = ref(false)
const error = ref('')

const summary = computed(() => {
  if (!rows.value.length) return ''
  const failed = rows.value.filter(r => !r.passed).length
  return failed ? `${rows.value.length} 项核对，${failed} 项不通过` : `${rows.value.length} 项核对全部通过`
})

async function load() {
  loading.value = true
  error.value = ''
  try {
    const res = await fetchCrossCheck(props.projectId, props.year)
    rows.value = res.rows
    noResult.value = res.noResult
  } catch (e: any) {
    rows.value = []
    error.value = errorText(e, '跨表核对执行失败')
  } finally {
    loading.value = false
  }
}

watch([() => props.projectId, () => props.year], load, { immediate: true })
</script>

<style scoped src="../styles/unaudited.css"></style>
<style scoped src="../styles/citar-data.css"></style>
<style scoped src="../styles/report-analysis.css"></style>
