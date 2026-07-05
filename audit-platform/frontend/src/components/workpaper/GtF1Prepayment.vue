<template>
  <div class="f1-prepayment">
    <!-- 加载状态 -->
    <div v-if="isLoading" class="loading-container">
      <el-skeleton :rows="8" animated />
    </div>

    <template v-else>
      <!-- 顶部工具栏：双模式切换 -->
      <div class="f1-header-toolbar">
        <el-segmented
          v-model="dualMode.currentMode.value"
          :options="dualMode.modeOptions.value"
          size="small"
          @change="dualMode.onModeChange"
        />
        <el-button size="small" @click="versionToolbar.openVersionHistory()">版本历史</el-button>
        <el-tooltip v-if="dualMode.ooHealthy.value === false" content="OnlyOffice服务不可用" placement="top">
          <el-tag size="small" type="warning">OO不可用</el-tag>
        </el-tooltip>
      </div>

      <!-- OnlyOffice 模式 -->
      <template v-if="dualMode.currentMode.value === 'onlyoffice' && dualMode.ooConfig.value">
        <GtOnlyOfficeSheet
          :config="dualMode.ooConfig.value"
          @document-ready="dualMode.onDocumentReady"
        />
      </template>

      <!-- HTML 结构化视图 -->
      <template v-else>
        <el-tabs v-model="activeTab" type="border-card" class="f1-tabs">
          <!-- Tab 1: F1A 程序表 -->
          <el-tab-pane name="procedure" label="F1A 程序表" lazy>
            <F1TabProcedure
              v-if="activeTab === 'procedure'"
              :wp-id="wpIdRef"
              :project-id="projectIdRef"
              :html-data="htmlData"
              :is-readonly="isReadonly"
            />
          </el-tab-pane>

          <!-- Tab 2: F1-1 审定表 -->
          <el-tab-pane name="adjudication" label="F1-1 审定表" lazy>
            <F1TabAdjudication
              v-if="activeTab === 'adjudication'"
              :all-responses="allResponses"
              :wp-id="wpIdRef"
              :project-id="projectIdRef"
              :is-readonly="isReadonly"
              :save-immediate="saveImmediate"
              :debounced-save="debouncedSave"
              :cross-sheet="crossSheet"
            />
          </el-tab-pane>

          <!-- Tab 3: F1-2 明细表 -->
          <el-tab-pane name="detail" label="F1-2 明细表" lazy>
            <F1TabDetail
              v-if="activeTab === 'detail'"
              :all-responses="allResponses"
              :wp-id="wpIdRef"
              :project-id="projectIdRef"
              :is-readonly="isReadonly"
              :save-immediate="saveImmediate"
              :debounced-save="debouncedSave"
            />
          </el-tab-pane>

          <!-- Tab 4: F1-3 调整分录 -->
          <el-tab-pane name="adjustment" label="F1-3 调整分录" lazy>
            <F1TabAdjustment
              v-if="activeTab === 'adjustment'"
              :all-responses="allResponses"
              :wp-id="wpIdRef"
              :project-id="projectIdRef"
              :is-readonly="isReadonly"
              :save-immediate="saveImmediate"
              :debounced-save="debouncedSave"
            />
          </el-tab-pane>

          <!-- Tab 5: F1-4 分析表 -->
          <el-tab-pane name="analysis" label="F1-4 分析表" lazy>
            <F1TabAnalysis
              v-if="activeTab === 'analysis'"
              :all-responses="allResponses"
              :wp-id="wpIdRef"
              :project-id="projectIdRef"
              :is-readonly="isReadonly"
              :save-immediate="saveImmediate"
              :debounced-save="debouncedSave"
              :cross-sheet="crossSheet"
            />
          </el-tab-pane>

          <!-- Tab 6: F1-5 长期检查 -->
          <el-tab-pane name="longterm" label="F1-5 长期检查" lazy>
            <F1TabLongTerm
              v-if="activeTab === 'longterm'"
              :all-responses="allResponses"
              :wp-id="wpIdRef"
              :project-id="projectIdRef"
              :is-readonly="isReadonly"
              :save-immediate="saveImmediate"
              :debounced-save="debouncedSave"
              :cross-sheet="crossSheet"
            />
          </el-tab-pane>

          <!-- Tab 7: F1-6 关联方 -->
          <el-tab-pane name="related-party" label="F1-6 关联方" lazy>
            <F1TabRelatedParty
              v-if="activeTab === 'related-party'"
              :all-responses="allResponses"
              :wp-id="wpIdRef"
              :project-id="projectIdRef"
              :is-readonly="isReadonly"
              :save-immediate="saveImmediate"
              :debounced-save="debouncedSave"
              :cross-sheet="crossSheet"
            />
          </el-tab-pane>

          <!-- Tab 8: F1-7 综合检查 -->
          <el-tab-pane name="comprehensive-check" label="F1-7 综合检查" lazy>
            <F1TabComprehensiveCheck
              v-if="activeTab === 'comprehensive-check'"
              :all-responses="allResponses"
              :wp-id="wpIdRef"
              :project-id="projectIdRef"
              :is-readonly="isReadonly"
              :save-immediate="saveImmediate"
              :debounced-save="debouncedSave"
            />
          </el-tab-pane>

          <!-- Tab 9: 附注 -->
          <el-tab-pane name="disclosure" label="附注" lazy>
            <div v-if="activeTab === 'disclosure'" class="disclosure-container">
              <el-segmented
                v-model="disclosureVariant"
                :options="disclosureOptions"
                size="small"
                style="margin-bottom: 12px"
              />
              <F1TabDisclosureListed
                v-if="disclosureVariant === 'listed'"
                :all-responses="allResponses"
                :wp-id="wpIdRef"
                :project-id="projectIdRef"
                :is-readonly="isReadonly"
                :save-immediate="saveImmediate"
                :debounced-save="debouncedSave"
                :cross-sheet="crossSheet"
              />
              <F1TabDisclosureSoe
                v-if="disclosureVariant === 'soe'"
                :all-responses="allResponses"
                :wp-id="wpIdRef"
                :project-id="projectIdRef"
                :is-readonly="isReadonly"
                :save-immediate="saveImmediate"
                :debounced-save="debouncedSave"
                :cross-sheet="crossSheet"
              />
            </div>
          </el-tab-pane>

          <!-- Tab 10: 函证程序 -->
          <el-tab-pane name="confirmation-procedure" label="函证程序" lazy>
            <F1TabConfirmationProcedure
              v-if="activeTab === 'confirmation-procedure'"
              :wp-id="wpIdRef"
              :project-id="projectIdRef"
              :is-readonly="isReadonly"
            />
          </el-tab-pane>

        </el-tabs>
      </template>

      <GtWpVersionTrail
        ref="versionTrailRef"
        :workpaper-id="props.wpId"
        :project-id="props.projectId"
      />
    </template>
  </div>
</template>

<script setup lang="ts">
/**
 * GtF1Prepayment.vue — F1 预付账款底稿主入口
 *
 * el-tabs 10个tab-pane：F1A程序表 → F1-1审定表 → F1-2明细表 → F1-3调整分录
 * → F1-4分析表 → F1-5长期检查 → F1-6关联方 → F1-7综合检查 → 附注
 *
 * 科目覆盖：1123 预付账款（贷方科目/负债类）
 * selfLoad: 当 htmlData prop 为 null 时自行调 render-config 加载数据。
 */
import { ref, computed, onMounted, provide, defineAsyncComponent } from 'vue'
import http from '@/utils/http'
import { useF1FormData } from './composables/useF1FormData'
import { useF1CrossSheet } from './composables/useF1CrossSheet'
import { useF1DualMode } from './composables/useF1DualMode'
import { useWorkpaperVersionToolbar } from './composables/useWorkpaperVersionToolbar'

// ─── Async sub-components ────────────────────────────────────────────────────

const F1TabAdjudication = defineAsyncComponent(() => import('./f1/F1TabAdjudication.vue'))
const F1TabDetail = defineAsyncComponent(() => import('./f1/F1TabDetail.vue'))
const F1TabAdjustment = defineAsyncComponent(() => import('./f1/F1TabAdjustment.vue'))
const F1TabAnalysis = defineAsyncComponent(() => import('./f1/F1TabAnalysis.vue'))
const F1TabLongTerm = defineAsyncComponent(() => import('./f1/F1TabLongTerm.vue'))
const F1TabRelatedParty = defineAsyncComponent(() => import('./f1/F1TabRelatedParty.vue'))
const F1TabConfirmationProcedure = defineAsyncComponent(() => import('./f1/F1TabConfirmationProcedure.vue'))
const F1TabComprehensiveCheck = defineAsyncComponent(() => import('./f1/F1TabComprehensiveCheck.vue'))
const F1TabDisclosureListed = defineAsyncComponent(() => import('./f1/F1TabDisclosureListed.vue'))
const F1TabDisclosureSoe = defineAsyncComponent(() => import('./f1/F1TabDisclosureSoe.vue'))
const GtOnlyOfficeSheet = defineAsyncComponent(() => import('./GtOnlyOfficeSheet.vue'))
const GtWpVersionTrail = defineAsyncComponent(() => import('./version-trail/GtWpVersionTrail.vue'))

const F1TabProcedure = defineAsyncComponent(() => import('./f1/F1TabProcedure.vue'))

// ─── Props / Emits ───────────────────────────────────────────────────────────

const props = defineProps<{
  wpId: string
  projectId: string
  wpCode?: string
  year?: number
  htmlData?: any
  readonly?: boolean
}>()

defineEmits<{
  (e: 'save'): void
  (e: 'completed'): void
}>()

// ─── State ───────────────────────────────────────────────────────────────────

const isLoading = ref(true)
const activeTab = ref('adjudication')
const disclosureVariant = ref<'listed' | 'soe'>('listed')
const applicableStandards = ref('')

const isReadonly = computed(() => !!props.readonly)
const wpIdRef = computed(() => props.wpId)
const projectIdRef = computed(() => props.projectId)

/** 附注切换选项：根据 applicable_standards 自动判断 */
const disclosureOptions = computed(() => {
  const std = applicableStandards.value.toLowerCase()
  const opts: Array<{ label: string; value: string; disabled?: boolean }> = []
  const showListed = std.includes('listed') || !std
  const showSoe = std.includes('soe') || !std
  if (showListed) opts.push({ label: '上市公司', value: 'listed' })
  if (showSoe) opts.push({ label: '国企', value: 'soe' })
  if (opts.length === 0) {
    opts.push({ label: '上市公司', value: 'listed' })
    opts.push({ label: '国企', value: 'soe' })
  }
  return opts
})

// ─── useF1FormData ───────────────────────────────────────────────────────────

const {
  allResponses,
  loadAll,
  saveImmediate: rawSaveImmediate,
  debouncedSave,
} = useF1FormData({
  wpId: wpIdRef,
  projectId: projectIdRef,
})

const versionToolbar = useWorkpaperVersionToolbar({ wpId: wpIdRef, projectId: projectIdRef })
const { versionTrailRef } = versionToolbar
const saveImmediate = versionToolbar.wrapSaveImmediate(rawSaveImmediate)

// ─── useF1CrossSheet ─────────────────────────────────────────────────────────

const crossSheet = useF1CrossSheet({ allResponses })

// ─── useF1DualMode ───────────────────────────────────────────────────────────

const dualMode = useF1DualMode({ wpId: wpIdRef, activeTab })

// ─── Provide openReviewDialog ────────────────────────────────────────────────

function openReviewDialog(sectionId: string): void {
  console.log('[F1] openReviewDialog:', sectionId)
}

provide('openReviewDialog', openReviewDialog)
provide('reloadWorkpaperData', loadAll)

// ─── selfLoad ────────────────────────────────────────────────────────────────

async function selfLoad() {
  if (props.htmlData) {
    // 从 props 提供的数据初始化（render-config已返回）
    if (props.htmlData.applicable_standards || props.htmlData.project_context?.applicable_standards) {
      applicableStandards.value = props.htmlData.applicable_standards || props.htmlData.project_context?.applicable_standards || ''
    }
    await loadAll()
    isLoading.value = false
    return
  }

  // 当 htmlData 为空时（bundle 内嵌场景），自行加载
  try {
    const res = await http.get(
      `/api/workpapers/${props.wpId}/render-config`,
      { params: { force_component_type: 'f1-prepayment' }, _silent: true } as any,
    )
    const renderData = res.data?.data ?? res.data
    if (renderData?.sheets?.[0]?.html_data?.project_context) {
      applicableStandards.value = renderData.sheets[0].html_data.project_context.applicable_standards || ''
    }
  } catch (err) {
    console.warn('[GtF1Prepayment] selfLoad render-config failed:', err)
  }

  await loadAll()
  isLoading.value = false
}

// ─── Lifecycle ───────────────────────────────────────────────────────────────

onMounted(async () => {
  await selfLoad()
  // 非阻塞检查 OO 健康状态
  dualMode.checkOOHealth()
})
</script>

<style scoped>
.f1-prepayment {
  padding: 12px;
}

.loading-container {
  padding: 24px;
}

.f1-header-toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
  padding: 8px 12px;
  background: #f5f7fa;
  border-radius: 6px;
}

.f1-tabs {
  min-height: 400px;
}

.disclosure-container {
  padding: 8px 0;
}
</style>
