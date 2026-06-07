<!--
  AccountPackageView.vue — 科目工作包入口首页（D1/D2 共用）

  spec workpaper-account-package-d1-d2-pilot Task 4.1 / 5.1
  Validates: Requirements 1.2, 2.1, 3.1
-->
<template>
  <div class="gt-account-package-view">
    <!-- 加载态 -->
    <div v-if="loading" class="gt-account-package-view__loading">
      <el-skeleton :rows="6" animated />
    </div>

    <!-- 错误态 -->
    <div v-else-if="error" class="gt-account-package-view__error">
      <el-alert :title="error" type="error" show-icon :closable="false" />
    </div>

    <!-- 主内容 -->
    <template v-else-if="detail">
      <!-- 顶部标题栏 -->
      <div class="gt-account-package-view__header">
        <div class="gt-account-package-view__title-row">
          <h2 class="gt-account-package-view__title">
            {{ detail.account_name }}（{{ detail.primary_wp_code }}）
          </h2>
          <el-tag
            v-if="detail.mapping_status === 'pending_inventory_reconciliation'"
            type="warning"
            effect="light"
            size="small"
          >
            映射待确认
          </el-tag>
          <el-tag v-else type="success" effect="light" size="small">
            已确认
          </el-tag>
        </div>
        <div class="gt-account-package-view__meta">
          <span>科目代码：{{ detail.account_code }}</span>
          <span>循环：{{ detail.cycle }}</span>
          <span>Sheet 数量：{{ detail.sheets.length }}</span>
        </div>
      </div>

      <!-- 缺失卡片提示 -->
      <div v-if="hasMissingSources" class="gt-account-package-view__missing">
        <el-alert type="warning" :closable="false" show-icon>
          <template #title>部分数据源缺失（工作包仍可使用）</template>
          <div class="gt-account-package-view__missing-list">
            <div
              v-for="(item, idx) in missingSourceCards"
              :key="idx"
              class="gt-account-package-view__missing-item"
            >
              <span class="gt-account-package-view__missing-name">{{ item.sheet_name }}</span>
              <span class="gt-account-package-view__missing-reason">{{ item.reason }}</span>
            </div>
          </div>
        </el-alert>
      </div>

      <!-- sheet_type 分组导航 -->
      <AccountPackageSheetNav
        :groups="sheetGroups"
        :active-sheet="activeSheet"
        @select="handleSheetSelect"
      />

      <!-- 字段来源面板（审定表时显示） -->
      <AccountPackageFieldSource
        v-if="activeSheetType === 'audit_sheet'"
        :package-id="packageId"
        :primary-wp-code="detail.primary_wp_code"
      />

      <!-- 摘要卡片区 -->
      <div class="gt-account-package-view__cards">
        <!-- 函证摘要卡片 -->
        <AccountPackageEvidenceCard
          v-if="detail.external_cards.includes('confirmation_summary')"
          type="confirmation_summary"
          :package-id="packageId"
          :project-id="projectId"
        />

        <!-- 调整影响卡片 -->
        <AccountPackageEvidenceCard
          v-if="detail.external_cards.includes('adjustment_impact')"
          type="adjustment_impact"
          :package-id="packageId"
          :project-id="projectId"
        />
      </div>

      <!-- 程序状态控制台 -->
      <AccountPackageControlPanel
        :project-id="projectId"
        :package-id="packageId"
        :program-statuses="programStatuses"
        @update-status="handleStatusUpdate"
      />

      <!-- 结论入口 -->
      <AccountPackageConclusionEntry
        :package-id="packageId"
        :primary-wp-code="detail.primary_wp_code"
        :has-conclusion-sheet="hasConclusionSheet"
      />

      <!-- D1 附注来源链路 -->
      <div
        v-if="detail.primary_wp_code === 'D1' && hasDisclosureSheet"
        class="gt-account-package-view__disclosure-links"
      >
        <h4>附注来源链路</h4>
        <div class="gt-account-package-view__disclosure-sources">
          <div
            v-for="src in disclosureSources"
            :key="src.sheet_name"
            class="gt-account-package-view__disclosure-source"
          >
            <span class="gt-account-package-view__disclosure-icon">📎</span>
            <span>{{ src.sheet_name }} → C-D1-disclosure</span>
            <el-tag size="small" effect="plain">{{ src.description }}</el-tag>
          </div>
        </div>
      </div>

      <!-- D2 坏账与 ECL 分组 -->
      <div
        v-if="detail.primary_wp_code === 'D2' && badDebtEclSheets.length > 0"
        class="gt-account-package-view__ecl-group"
      >
        <h4>坏账与 ECL</h4>
        <div class="gt-account-package-view__ecl-list">
          <div
            v-for="sheet in badDebtEclSheets"
            :key="sheet.sheet_name"
            class="gt-account-package-view__ecl-item"
            @click="handleSheetSelect(sheet.sheet_name)"
          >
            <span class="gt-account-package-view__ecl-icon">⚠️</span>
            <span>{{ sheet.sheet_name }}</span>
          </div>
        </div>
      </div>

      <!-- D2 stale 提示 -->
      <div
        v-if="summary?.stale_summary?.has_stale"
        class="gt-account-package-view__stale"
      >
        <el-alert type="warning" :closable="false" show-icon>
          <template #title>下游数据已过期</template>
          <span>调整保存后，报表/附注数据需要刷新</span>
        </el-alert>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { useRoute } from 'vue-router'
import {
  useAccountPackage,
  D1_DISCLOSURE_SOURCES,
  getBadDebtEclGroup,
} from '@/composables/useAccountPackage'
import AccountPackageSheetNav from '@/components/workpaper/AccountPackageSheetNav.vue'
import AccountPackageFieldSource from '@/components/workpaper/AccountPackageFieldSource.vue'
import AccountPackageControlPanel from '@/components/workpaper/AccountPackageControlPanel.vue'
import AccountPackageEvidenceCard from '@/components/workpaper/AccountPackageEvidenceCard.vue'
import AccountPackageConclusionEntry from '@/components/workpaper/AccountPackageConclusionEntry.vue'

const route = useRoute()
const projectId = ref(route.params.projectId as string)
const packageId = ref(route.params.packageId as string)

const {
  detail,
  summary,
  programStatuses,
  loading,
  error,
  sheetGroups,
  missingSourceCards,
  hasMissingSources,
  fetchDetail,
  fetchSummary,
  fetchProgramStatuses,
  updateProgramStatus,
} = useAccountPackage(projectId)

const activeSheet = ref('')

const activeSheetType = computed(() => {
  if (!detail.value || !activeSheet.value) return ''
  const sheet = detail.value.sheets.find((s) => s.sheet_name === activeSheet.value)
  return sheet?.sheet_type ?? ''
})

const hasConclusionSheet = computed(() => {
  return detail.value?.sheets.some((s) => s.sheet_type === 'conclusion') ?? false
})

const hasDisclosureSheet = computed(() => {
  return detail.value?.sheets.some((s) => s.sheet_type === 'disclosure') ?? false
})

const disclosureSources = computed(() => {
  if (detail.value?.primary_wp_code !== 'D1') return []
  return D1_DISCLOSURE_SOURCES
})

const badDebtEclSheets = computed(() => {
  if (!detail.value || detail.value.primary_wp_code !== 'D2') return []
  return getBadDebtEclGroup(detail.value.sheets)
})

function handleSheetSelect(sheetName: string) {
  activeSheet.value = sheetName
}

async function handleStatusUpdate(programCode: string, update: any) {
  await updateProgramStatus(packageId.value, programCode, update)
}

onMounted(async () => {
  await fetchDetail(packageId.value)
  await fetchSummary(packageId.value)
  await fetchProgramStatuses(packageId.value)
})

watch(
  () => route.params.packageId,
  async (newId) => {
    if (newId && newId !== packageId.value) {
      packageId.value = newId as string
      await fetchDetail(packageId.value)
      await fetchSummary(packageId.value)
      await fetchProgramStatuses(packageId.value)
    }
  }
)
</script>

<style scoped>
.gt-account-package-view {
  padding: 24px;
  max-width: 1200px;
  margin: 0 auto;
}

.gt-account-package-view__header {
  margin-bottom: 20px;
}

.gt-account-package-view__title-row {
  display: flex;
  align-items: center;
  gap: 12px;
}

.gt-account-package-view__title {
  font-size: 20px;
  font-weight: 600;
  color: var(--gt-color-primary, #4b2d77);
  margin: 0;
}

.gt-account-package-view__meta {
  display: flex;
  gap: 16px;
  margin-top: 8px;
  font-size: 13px;
  color: var(--gt-color-text-secondary, #6e6e73);
}

.gt-account-package-view__missing {
  margin-bottom: 16px;
}

.gt-account-package-view__missing-list {
  margin-top: 8px;
}

.gt-account-package-view__missing-item {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  padding: 2px 0;
}

.gt-account-package-view__missing-name {
  font-weight: 500;
}

.gt-account-package-view__missing-reason {
  color: var(--gt-color-text-secondary, #6e6e73);
}

.gt-account-package-view__cards {
  display: flex;
  gap: 16px;
  flex-wrap: wrap;
  margin: 16px 0;
}

.gt-account-package-view__disclosure-links {
  margin-top: 20px;
  padding: 16px;
  border: 1px solid var(--gt-color-border-purple, #e8e4f0);
  border-radius: 8px;
  background: var(--gt-color-primary-bg, #f4f0fa);
}

.gt-account-package-view__disclosure-links h4 {
  margin: 0 0 12px;
  color: var(--gt-color-primary, #4b2d77);
  font-size: 14px;
}

.gt-account-package-view__disclosure-sources {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.gt-account-package-view__disclosure-source {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
}

.gt-account-package-view__ecl-group {
  margin-top: 20px;
  padding: 16px;
  border: 1px solid var(--gt-color-border-purple, #e8e4f0);
  border-radius: 8px;
}

.gt-account-package-view__ecl-group h4 {
  margin: 0 0 12px;
  color: var(--gt-color-primary, #4b2d77);
  font-size: 14px;
}

.gt-account-package-view__ecl-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.gt-account-package-view__ecl-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 10px;
  border-radius: 4px;
  cursor: pointer;
  font-size: 13px;
  transition: background 0.2s;
}

.gt-account-package-view__ecl-item:hover {
  background: var(--gt-color-primary-bg, #f4f0fa);
}

.gt-account-package-view__stale {
  margin-top: 16px;
}

.gt-account-package-view__loading,
.gt-account-package-view__error {
  padding: 40px 0;
}
</style>
