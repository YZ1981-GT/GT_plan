<template>
  <div class="unaudited-screen">
    <header class="unaudited-header">
      <h1 class="unaudited-header__title">报表分析</h1>
      <span class="unaudited-header__note">资产负债表、利润表的审定 / 未审 / 对比，及智能核对（跨表勾稽）、多年对比、变动分析、财务指标</span>
    </header>

    <nav class="unaudited-tabs">
      <template v-for="(item, index) in VISIBLE_TABS" :key="item.key">
        <!-- 报表与分析之间一道分隔 -->
        <span v-if="index > 0 && VISIBLE_TABS[index - 1].group !== item.group" class="unaudited-tabs__divider" />
        <button
          type="button"
          class="unaudited-tab"
          :class="{ 'unaudited-tab--active': tab === item.key }"
          @click="setTab(item.key)"
        >{{ item.label }}</button>
      </template>
    </nav>

    <section class="unaudited-panel">
      <p v-if="!year" class="sheet-empty">{{ yearLoading ? '正在读取项目信息…' : '项目未设置审核年度，请先在项目信息里填写' }}</p>
      <template v-else>
        <CitarStatementView
          v-if="statementKind"
          :kind="statementKind"
          :project-id="projectId"
          :year="year"
          :entity-name="entityName"
          @go="goSegment"
        />
        <CitarCrossCheckPanel v-else-if="tab === 'cross_check'" :project-id="projectId" :year="year" />
        <CitarMultiYearPanel v-else-if="tab === 'multi_year'" :project-id="projectId" :year="year" />
        <CitarTrendPanel v-else-if="tab === 'trend'" :project-id="projectId" :year="year" />
        <CitarIndicatorsPanel v-else :project-id="projectId" :year="year" />
      </template>
    </section>
  </div>
</template>

<script setup lang="ts">
/**
 * 报表分析（CITAR 版式）：旧「财务报表」页 9 个标签搬入（spec citar-report-analysis）。
 * 当前标签记在 ?tab=，刷新与返回不丢。
 */
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import CitarStatementView from '../components/CitarStatementView.vue'
import CitarCrossCheckPanel from '../components/CitarCrossCheckPanel.vue'
import CitarMultiYearPanel from '../components/CitarMultiYearPanel.vue'
import CitarTrendPanel from '../components/CitarTrendPanel.vue'
import CitarIndicatorsPanel from '../components/CitarIndicatorsPanel.vue'
import { useCitarProject } from '../useCitarProject'
import { VISIBLE_TABS, type StatementKind, type TabKey } from '../useCitarReportAnalysis'

defineOptions({ name: 'CitarReportAnalysis' })

const route = useRoute()
const router = useRouter()
const { projectId, year, yearLoading, entityName, goSegment } = useCitarProject()

const tab = ref<TabKey>(VISIBLE_TABS.some(t => t.key === route.query.tab) ? (route.query.tab as TabKey) : 'balance_sheet')

const statementKind = computed<StatementKind | null>(() =>
  VISIBLE_TABS.find(t => t.key === tab.value)?.group === 'report' ? (tab.value as StatementKind) : null,
)

function setTab(key: TabKey) {
  tab.value = key
  router.replace({ query: { ...route.query, tab: key } })
}
</script>

<style scoped src="../styles/unaudited.css"></style>
