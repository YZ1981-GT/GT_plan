<template>
  <div class="aud-screen">
    <header class="aud-header">
      <h1 class="aud-header__title">审定报表</h1>
      <span class="aud-header__note">按试算表审定数生成；调整分录批准后需重新生成</span>
    </header>

    <nav class="aud-tabs">
      <button
        v-for="item in TABS"
        :key="item.key"
        type="button"
        class="aud-tab"
        :class="{ 'aud-tab--active': tab === item.key }"
        @click="tab = item.key"
      >{{ item.label }}</button>
    </nav>

    <section class="aud-panel">
      <p v-if="!year" class="sheet-empty">{{ yearLoading ? '正在读取项目信息…' : '项目未设置审核年度，请先在项目信息里填写' }}</p>
      <template v-else>
        <div class="citar-notice" :class="{ 'citar-notice--plain': generated }">
          <span v-if="prerequisite">{{ prerequisite.message }}</span>
          <span v-else-if="!generated && !loading">审定报表尚未生成，下表只显示行次。</span>
          <span v-else>报表数据取自最近一次生成；试算表或调整分录有变化时请重新生成。</span>
          <button v-if="prerequisite?.segment" class="citar-btn" type="button" @click="goSegment(prerequisite.segment)">
            去{{ prerequisite.label }}
          </button>
          <button class="citar-btn citar-btn--primary" type="button" :disabled="generating" @click="generate">
            {{ generating ? '生成中…' : generated ? '重新生成' : '生成报表' }}
          </button>
        </div>

        <CitarReportTable
          :kind="tab"
          :rows="rows"
          :year="year"
          :entity-name="entityName"
          :loading="loading"
          :error="error"
        />
      </template>
    </section>
  </div>
</template>

<script setup lang="ts">
/**
 * 审定报表（CITAR 审定资产负债表 / 利润表版式）。
 * 读：GET /api/reports/{pid}/{year}/{type}（读已生成的 financial_report；未生成时返回金额为空的模板行次）
 * 生成：POST /api/reports/generate（平台既有前置条件：已导入账套、已映射、已重算试算表）
 */
import { computed, ref, watch } from 'vue'
import { getReport } from '@/services/auditPlatformApi'
import CitarReportTable, { type CitarReportRow } from '../components/CitarReportTable.vue'
import { useCitarProject } from '../useCitarProject'
import { useCitarReportGenerate } from '../useCitarReportGenerate'

defineOptions({ name: 'CitarAuditedReports' })

type TabKey = 'balance_sheet' | 'income_statement'
const TABS: { key: TabKey; label: string }[] = [
  { key: 'balance_sheet', label: '资产负债表' },
  { key: 'income_statement', label: '利润表' },
]

const { projectId, year, yearLoading, entityName, goSegment } = useCitarProject()
const { generating, prerequisite, generate: runGenerate } = useCitarReportGenerate(projectId, year)

const tab = ref<TabKey>('balance_sheet')
const rows = ref<CitarReportRow[]>([])
const loading = ref(false)
const error = ref('')

/** 未生成时后端返回模板行次、金额全空 */
const generated = computed(() =>
  rows.value.some(r => r.current_period_amount !== null || r.prior_period_amount !== null),
)

async function load() {
  if (!year.value) return
  loading.value = true
  error.value = ''
  try {
    rows.value = (await getReport(projectId.value, year.value, tab.value)) as CitarReportRow[]
  } catch (e: any) {
    rows.value = []
    error.value = e?.response?.status === 404 ? '报表格式未配置，无法显示' : e?.message || '读取审定报表失败'
  } finally {
    loading.value = false
  }
}

async function generate() {
  if (await runGenerate()) await load()
}

watch([projectId, year, tab], load, { immediate: true })
</script>

<style scoped src="../styles/audited.css"></style>
<style scoped src="../styles/citar-data.css"></style>

<style scoped>
.citar-notice--plain {
  border-color: #e4d8f3;
  background: var(--citar-c-fbf9fe);
  color: var(--citar-c-5c5c68);
}
</style>
