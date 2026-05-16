<!--
  TemplateLibraryMgmt.vue — 全局模板库管理主页面 [template-library-coordination Sprint 2.5]

  D2 ADR：白色简洁工具栏（不用 GtPageHeader 紫色渐变）
  D7 ADR：admin/partner 显示编辑按钮，其他角色只读（v-permission）
  D16 ADR：所有数字（主编码总数/公式覆盖率等）从 API 动态取，不硬编码

  6 Tab 导航：底稿模板 / 公式管理 / 审计报告模板 / 附注模板 / 编码体系 / 报表配置
  顶部统计摘要：主编码总数 / 公式覆盖率 / 种子加载状态 / 版本标识
-->
<template>
  <div class="gt-tlm gt-fade-in">
    <!-- 顶部白色简洁工具栏（D2 ADR） -->
    <div class="gt-tlm-header">
      <div class="gt-tlm-header-left">
        <h2 class="gt-tlm-title">模板库管理</h2>
        <span class="gt-tlm-version-tag">{{ versionLabel }}</span>
      </div>
      <div class="gt-tlm-header-actions">
        <el-button size="small" @click="versionDialogVisible = true" round>
          <el-icon style="margin-right: 4px"><Clock /></el-icon>版本历史
        </el-button>
        <el-button size="small" :loading="summaryLoading" @click="refreshSummary" round>
          <el-icon style="margin-right: 4px"><Refresh /></el-icon>刷新
        </el-button>
      </div>
    </div>

    <!-- 顶部全局统计摘要（动态数据，不硬编码） -->
    <div class="gt-tlm-summary">
      <div class="gt-tlm-stat">
        <span class="gt-tlm-stat-label">主编码总数</span>
        <span class="gt-tlm-stat-value gt-amt">
          {{ summaryLoading ? '—' : (templateCount ?? '—') }}
        </span>
      </div>
      <div class="gt-tlm-stat">
        <span class="gt-tlm-stat-label">公式覆盖率</span>
        <span class="gt-tlm-stat-value gt-amt" :class="coverageColorClass">
          {{ formulaCoveragePct === null ? '—' : `${formulaCoveragePct}%` }}
        </span>
      </div>
      <div class="gt-tlm-stat">
        <span class="gt-tlm-stat-label">种子加载</span>
        <span class="gt-tlm-stat-value">
          <el-tag v-if="seedLoadedCount === null" size="small" type="info">加载中</el-tag>
          <el-tag
            v-else
            size="small"
            :type="seedAllLoaded ? 'success' : (seedLoadedCount === 0 ? 'danger' : 'warning')"
          >
            {{ seedLoadedCount }} / {{ seedTotal }}
          </el-tag>
        </span>
      </div>
      <div class="gt-tlm-stat">
        <span class="gt-tlm-stat-label">版本</span>
        <span class="gt-tlm-stat-value gt-tlm-stat-version">{{ versionLabel }}</span>
      </div>
    </div>

    <!-- 种子加载面板（折叠区，admin/partner 可执行加载操作） -->
    <el-collapse v-model="seedPanelExpanded" class="gt-tlm-seed-collapse">
      <el-collapse-item name="seed">
        <template #title>
          <span class="gt-tlm-seed-title">
            <el-icon><Upload /></el-icon>
            种子数据管理
            <el-tag
              v-if="seedLoadedCount !== null"
              size="small"
              :type="seedAllLoaded ? 'success' : (seedLoadedCount === 0 ? 'danger' : 'warning')"
              effect="plain"
              round
              style="margin-left: 8px"
            >
              {{ seedLoadedCount }} / {{ seedTotal }}
            </el-tag>
          </span>
        </template>
        <SeedLoaderPanel ref="seedLoaderRef" @refresh="refreshSummary" />
      </el-collapse-item>
    </el-collapse>

    <!-- 6 Tab 主体 -->
    <div class="gt-tlm-body">
      <el-tabs v-model="activeTab" tab-position="left" class="gt-tlm-tabs">
        <el-tab-pane name="wp-template" label="底稿模板">
          <template #label>
            <span class="gt-tlm-tab-label">
              <el-icon><Folder /></el-icon>底稿模板
            </span>
          </template>
          <WpTemplateTab
            v-if="activeTab === 'wp-template'"
            :project-id="currentProjectId"
            @select="onWpTemplateSelect"
          />
        </el-tab-pane>

        <el-tab-pane name="formula" label="公式管理">
          <template #label>
            <span class="gt-tlm-tab-label">
              <el-icon><DataAnalysis /></el-icon>公式管理
            </span>
          </template>
          <FormulaTab v-if="activeTab === 'formula'" />
        </el-tab-pane>

        <el-tab-pane name="audit-report" label="审计报告模板">
          <template #label>
            <span class="gt-tlm-tab-label">
              <el-icon><Document /></el-icon>审计报告模板
            </span>
          </template>
          <AuditReportTab v-if="activeTab === 'audit-report'" />
        </el-tab-pane>

        <el-tab-pane name="note-template" label="附注模板">
          <template #label>
            <span class="gt-tlm-tab-label">
              <el-icon><Reading /></el-icon>附注模板
            </span>
          </template>
          <NoteTemplateTab v-if="activeTab === 'note-template'" />
        </el-tab-pane>

        <el-tab-pane name="gt-coding" label="编码体系">
          <template #label>
            <span class="gt-tlm-tab-label">
              <el-icon><Grid /></el-icon>编码体系
            </span>
          </template>
          <GtCodingTab
            v-if="activeTab === 'gt-coding'"
            :project-id="currentProjectId"
          />
        </el-tab-pane>

        <el-tab-pane name="report-config" label="报表配置">
          <template #label>
            <span class="gt-tlm-tab-label">
              <el-icon><Tickets /></el-icon>报表配置
            </span>
          </template>
          <ReportConfigTab v-if="activeTab === 'report-config'" />
        </el-tab-pane>

        <!-- Sprint 6 Task 6.7：枚举字典 + 自定义查询，总计 8 Tab -->
        <el-tab-pane name="enum-dict" label="枚举字典">
          <template #label>
            <span class="gt-tlm-tab-label">
              <el-icon><CollectionTag /></el-icon>枚举字典
            </span>
          </template>
          <EnumDictTab v-if="activeTab === 'enum-dict'" />
        </el-tab-pane>

        <el-tab-pane name="custom-query" label="自定义查询">
          <template #label>
            <span class="gt-tlm-tab-label">
              <el-icon><Search /></el-icon>自定义查询
            </span>
          </template>
          <CustomQueryTab v-if="activeTab === 'custom-query'" />
        </el-tab-pane>
      </el-tabs>
    </div>

    <!-- 选中底稿模板时的右侧详情面板 -->
    <el-drawer
      v-model="detailDrawerVisible"
      :title="`底稿详情 - ${selectedWpCode}`"
      direction="rtl"
      size="55%"
    >
      <WpTemplateDetail
        v-if="selectedWpCode"
        :wp-code="selectedWpCode"
        :project-id="currentProjectId"
      />
    </el-drawer>

    <!-- 版本历史对话框（Sprint 5 Task 5.2） -->
    <VersionHistoryDialog
      v-model="versionDialogVisible"
      :version-info="cachedVersionInfo"
      :file-count="templateCount"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { Folder, DataAnalysis, Document, Reading, Grid, Tickets, Refresh, Upload, Clock, CollectionTag, Search } from '@element-plus/icons-vue'
import { api } from '@/services/apiProxy'
import { templateLibraryMgmt as P_tlm, workpapers as P_wp } from '@/services/apiPaths'
import { handleApiError } from '@/utils/errorHandler'
import WpTemplateTab from '@/components/template-library/WpTemplateTab.vue'
import FormulaTab from '@/components/template-library/FormulaTab.vue'
import AuditReportTab from '@/components/template-library/AuditReportTab.vue'
import NoteTemplateTab from '@/components/template-library/NoteTemplateTab.vue'
import GtCodingTab from '@/components/template-library/GtCodingTab.vue'
import ReportConfigTab from '@/components/template-library/ReportConfigTab.vue'
import EnumDictTab from '@/components/template-library/EnumDictTab.vue'
import CustomQueryTab from '@/components/template-library/CustomQueryTab.vue'
import SeedLoaderPanel from '@/components/template-library/SeedLoaderPanel.vue'
import WpTemplateDetail from '@/components/template-library/WpTemplateDetail.vue'
import VersionHistoryDialog from '@/components/template-library/VersionHistoryDialog.vue'

const route = useRoute()

// 当前项目 ID（可选 — 模板库管理是全局页面，但 /list 端点需要 pid）
const currentProjectId = computed(() => (route.params.projectId as string) || (route.query.project_id as string) || '')

const activeTab = ref<'wp-template' | 'formula' | 'audit-report' | 'note-template' | 'gt-coding' | 'report-config' | 'enum-dict' | 'custom-query'>('wp-template')

// ─── 顶部统计摘要状态 ───
const summaryLoading = ref(false)
const templateCount = ref<number | null>(null)
const formulaCoveragePct = ref<number | null>(null)
const seedLoadedCount = ref<number | null>(null)
const seedTotal = ref(0)
const versionLabel = ref('致同 2025 修订版')

const seedAllLoaded = computed(() => {
  return seedLoadedCount.value !== null
    && seedTotal.value > 0
    && seedLoadedCount.value === seedTotal.value
})

const coverageColorClass = computed(() => {
  const v = formulaCoveragePct.value
  if (v === null) return ''
  if (v >= 80) return 'gt-tlm-cov--green'
  if (v >= 40) return 'gt-tlm-cov--yellow'
  return 'gt-tlm-cov--red'
})

// ─── 详情面板 ───
const detailDrawerVisible = ref(false)
const selectedWpCode = ref('')

// ─── 版本历史对话框（Task 5.2） ───
const versionDialogVisible = ref(false)
interface CachedVersionInfo {
  version: string
  release_date: string
  last_seed_loads: Array<{
    seed_name: string
    loaded_at: string
    loaded_by?: string | null
    record_count: number
    inserted: number
    updated: number
    status: string
  }>
}
const cachedVersionInfo = ref<CachedVersionInfo | null>(null)

// ─── 种子加载面板（折叠状态） ───
const seedPanelExpanded = ref<string[]>([])
const seedLoaderRef = ref<InstanceType<typeof SeedLoaderPanel> | null>(null)

function onWpTemplateSelect(wpCode: string) {
  selectedWpCode.value = wpCode
  detailDrawerVisible.value = true
}

// ─── 数据加载 ───

async function loadTemplateCount() {
  if (!currentProjectId.value) {
    templateCount.value = null
    return
  }
  try {
    const data = await api.get(P_wp.templateList(currentProjectId.value))
    const items = Array.isArray(data) ? data : (data?.items || [])
    templateCount.value = items.length
  } catch {
    templateCount.value = null
  }
}

async function loadFormulaCoverage() {
  try {
    const data = await api.get(P_tlm.formulaCoverage)
    // 后端 FormulaCoverageResponse 含 prefill_coverage[] 和 report_formula_coverage[]
    // 顶部摘要展示"全局公式覆盖率"= 预填充覆盖率 + 报表公式覆盖率 加权平均（简单平均近似）
    const prefill = (data?.prefill_coverage || []) as Array<{ total_templates: number; templates_with_formula: number }>
    const reports = (data?.report_formula_coverage || []) as Array<{ total_rows: number; rows_with_formula: number }>
    const totalTemplates = prefill.reduce((s, c) => s + (c.total_templates || 0), 0)
    const withFormula = prefill.reduce((s, c) => s + (c.templates_with_formula || 0), 0)
    const totalRows = reports.reduce((s, c) => s + (c.total_rows || 0), 0)
    const rowsWithFormula = reports.reduce((s, c) => s + (c.rows_with_formula || 0), 0)
    const denom = totalTemplates + totalRows
    if (denom > 0) {
      formulaCoveragePct.value = Math.round(((withFormula + rowsWithFormula) / denom) * 1000) / 10
    } else {
      formulaCoveragePct.value = 0
    }
  } catch {
    formulaCoveragePct.value = null
  }
}

async function loadSeedStatus() {
  try {
    const data = await api.get(P_tlm.seedStatus)
    const seeds = (data?.seeds || []) as Array<{ status: string }>
    seedTotal.value = seeds.length
    seedLoadedCount.value = seeds.filter(s => s.status === 'loaded').length
  } catch {
    seedLoadedCount.value = null
    seedTotal.value = 0
  }
}

async function loadVersionInfo() {
  try {
    const data = await api.get<CachedVersionInfo & { version_label?: string }>(P_tlm.versionInfo)
    if (data) {
      cachedVersionInfo.value = {
        version: data.version || '致同 2025 修订版',
        release_date: data.release_date || '',
        last_seed_loads: data.last_seed_loads || [],
      }
      // 兼容旧字段名 version_label
      if (data.version_label) versionLabel.value = data.version_label
      else if (data.version) versionLabel.value = data.version
    }
  } catch {
    /* 静默，使用默认值 */
  }
}

async function refreshSummary() {
  summaryLoading.value = true
  try {
    await Promise.all([
      loadTemplateCount(),
      loadFormulaCoverage(),
      loadSeedStatus(),
      loadVersionInfo(),
    ])
  } catch (e: any) {
    handleApiError(e, '加载模板库摘要')
  } finally {
    summaryLoading.value = false
  }
}

onMounted(() => {
  refreshSummary()
})
</script>

<style scoped>
.gt-tlm {
  height: 100%;
  display: flex;
  flex-direction: column;
  padding: var(--gt-space-3, 12px);
  overflow: hidden;
  background: var(--gt-color-bg, #f5f5f7);
}

/* D2 ADR：白色简洁工具栏，不用紫色渐变 */
.gt-tlm-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  background: var(--gt-color-bg-white);
  border-radius: 8px;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.04);
  margin-bottom: 12px;
}
.gt-tlm-header-left { display: flex; align-items: center; gap: 12px; }
.gt-tlm-title { margin: 0; font-size: var(--gt-font-size-md); font-weight: 700; color: var(--gt-color-primary); }
.gt-tlm-version-tag {
  font-size: var(--gt-font-size-xs); padding: 2px 8px; border-radius: 12px;
  background: var(--gt-color-primary-bg); color: var(--gt-color-primary); font-weight: 500;
}
.gt-tlm-header-actions { display: flex; gap: 8px; }

/* 顶部统计摘要 */
.gt-tlm-summary {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 12px;
  margin-bottom: 12px;
}
.gt-tlm-stat {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 12px 16px;
  background: var(--gt-color-bg-white);
  border-radius: 8px;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.04);
  border-left: 3px solid #4b2d77;
}
.gt-tlm-stat-label { font-size: var(--gt-font-size-xs); color: var(--gt-color-info); }
.gt-tlm-stat-value { font-size: 20px /* allow-px: special */; font-weight: 700; color: var(--gt-color-text-primary); }
.gt-tlm-stat-version { font-size: var(--gt-font-size-sm); font-weight: 500; color: var(--gt-color-primary); }
/* D8 ADR：数字列统一 .gt-amt — Arial Narrow + nowrap + tabular-nums */
.gt-amt {
  font-family: 'Arial Narrow', Arial, sans-serif;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}
.gt-tlm-cov--green { color: var(--gt-color-success); }
.gt-tlm-cov--yellow { color: var(--gt-color-wheat); }
.gt-tlm-cov--red { color: var(--gt-color-coral); }

/* 主体 Tab 区 */
.gt-tlm-body {
  flex: 1;
  display: flex;
  background: var(--gt-color-bg-white);
  border-radius: 8px;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.04);
  overflow: hidden;
  min-height: 0;
}
.gt-tlm-tabs {
  flex: 1;
  display: flex;
  width: 100%;
  height: 100%;
}
.gt-tlm-tabs :deep(.el-tabs__header) {
  width: 160px;
  flex-shrink: 0;
  border-right: 1px solid #e4e7ed;
  background: var(--gt-color-bg);
  margin: 0;
}
.gt-tlm-tabs :deep(.el-tabs__nav-wrap) { padding: 8px 0; }
.gt-tlm-tabs :deep(.el-tabs__item) {
  height: 40px;
  line-height: 40px;
  padding: 0 16px !important;
  text-align: left;
  justify-content: flex-start !important;
}
.gt-tlm-tabs :deep(.el-tabs__active-bar) { width: 3px !important; }
.gt-tlm-tabs :deep(.el-tabs__content) {
  flex: 1;
  height: 100%;
  overflow: auto;
  padding: 16px;
}
.gt-tlm-tab-label {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: var(--gt-font-size-sm);
}

.gt-tlm-pending {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 300px;
}

/* 种子加载面板折叠区 */
.gt-tlm-seed-collapse {
  margin-bottom: 12px;
  background: var(--gt-color-bg-white);
  border-radius: 8px;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.04);
  border: none;
}
.gt-tlm-seed-collapse :deep(.el-collapse-item__header) {
  padding: 0 16px;
  background: var(--gt-color-bg-white);
  border-bottom: 1px solid #ebeef5;
  font-weight: 600;
}
.gt-tlm-seed-collapse :deep(.el-collapse-item__wrap) {
  background: var(--gt-color-bg);
  border-bottom: none;
}
.gt-tlm-seed-collapse :deep(.el-collapse-item__content) {
  padding: 12px 16px;
}
.gt-tlm-seed-title {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: var(--gt-font-size-sm);
  color: var(--gt-color-primary);
}

.gt-tlm-detail { padding: 16px; }
.gt-tlm-detail p { margin: 8px 0; font-size: var(--gt-font-size-sm); }
</style>
