<template>
  <div class="d3-prepaid-accounts">
    <!-- 加载状态 -->
    <div v-if="isLoading" class="loading-container">
      <el-skeleton :rows="8" animated />
    </div>

    <template v-else>
      <!-- 顶部工具栏：双模式切换 -->
      <div class="d3-header-toolbar">
        <el-segmented
          v-model="dualMode.currentMode.value"
          :options="dualMode.modeOptions.value"
          size="small"
          @change="dualMode.onModeChange"
        />
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
        <el-tabs v-model="activeTab" type="border-card" class="d3-tabs">
          <!-- Tab 1: D3A 程序表 -->
          <el-tab-pane name="procedure" label="D3A 程序表" lazy>
            <component :is="D3TabProcedure" v-if="activeTab === 'procedure'" />
          </el-tab-pane>

          <!-- Tab 2: D3-1 审定表 -->
          <el-tab-pane name="adjudication" label="D3-1 审定表" lazy>
            <D3TabAdjudication
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

          <!-- Tab 3: D3-2 明细表 -->
          <el-tab-pane name="detail" label="D3-2 明细表" lazy>
            <D3TabDetail
              v-if="activeTab === 'detail'"
              :all-responses="allResponses"
              :wp-id="wpIdRef"
              :project-id="projectIdRef"
              :is-readonly="isReadonly"
              :save-immediate="saveImmediate"
              :debounced-save="debouncedSave"
            />
          </el-tab-pane>

          <!-- Tab 4: D3-3 调整分录 -->
          <el-tab-pane name="adjustment" label="D3-3 调整分录" lazy>
            <D3TabAdjustment
              v-if="activeTab === 'adjustment'"
              :all-responses="allResponses"
              :wp-id="wpIdRef"
              :project-id="projectIdRef"
              :is-readonly="isReadonly"
              :save-immediate="saveImmediate"
              :debounced-save="debouncedSave"
            />
          </el-tab-pane>

          <!-- Tab 5: D3-4 分析表 -->
          <el-tab-pane name="analysis" label="D3-4 分析表" lazy>
            <D3TabAnalysis
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

          <!-- Tab 6: D3-5 长期检查 -->
          <el-tab-pane name="longterm" label="D3-5 长期检查" lazy>
            <D3TabLongTerm
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

          <!-- Tab 7: D3-6 关联方 -->
          <el-tab-pane name="related-party" label="D3-6 关联方" lazy>
            <D3TabRelatedParty
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

          <!-- Tab 8: D3-7 凭证检查 -->
          <el-tab-pane name="voucher-check" label="D3-7 凭证检查" lazy>
            <D3TabVoucherCheck
              v-if="activeTab === 'voucher-check'"
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
              <D3TabDisclosureListed
                v-if="disclosureVariant === 'listed'"
                :all-responses="allResponses"
                :wp-id="wpIdRef"
                :project-id="projectIdRef"
                :is-readonly="isReadonly"
                :save-immediate="saveImmediate"
                :debounced-save="debouncedSave"
                :cross-sheet="crossSheet"
              />
              <D3TabDisclosureSoe
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
        </el-tabs>
      </template>
    </template>
  </div>
</template>

<script setup lang="ts">
/**
 * GtD3PrepaidAccounts.vue — D3 预收账款底稿主入口
 *
 * el-tabs 9个tab-pane：D3A程序表 → D3-1审定表 → D3-2明细表 → D3-3调整分录
 * → D3-4分析表 → D3-5长期检查 → D3-6关联方 → D3-7凭证检查 → 附注
 *
 * 科目覆盖：2203 预收账款（贷方科目/负债类）
 * selfLoad: 当 htmlData prop 为 null 时自行调 render-config 加载数据。
 */
import { ref, computed, onMounted, provide, defineAsyncComponent } from 'vue'
import http from '@/utils/http'
import { useD3FormData } from './composables/useD3FormData'
import { useD3CrossSheet } from './composables/useD3CrossSheet'
import { useD3DualMode } from './composables/useD3DualMode'

// ─── Async sub-components ────────────────────────────────────────────────────

const D3TabAdjudication = defineAsyncComponent(() => import('./d3/D3TabAdjudication.vue'))
const D3TabDetail = defineAsyncComponent(() => import('./d3/D3TabDetail.vue'))
const D3TabAdjustment = defineAsyncComponent(() => import('./d3/D3TabAdjustment.vue'))
const D3TabAnalysis = defineAsyncComponent(() => import('./d3/D3TabAnalysis.vue'))
const D3TabLongTerm = defineAsyncComponent(() => import('./d3/D3TabLongTerm.vue'))
const D3TabRelatedParty = defineAsyncComponent(() => import('./d3/D3TabRelatedParty.vue'))
const D3TabVoucherCheck = defineAsyncComponent(() => import('./d3/D3TabVoucherCheck.vue'))
const D3TabDisclosureListed = defineAsyncComponent(() => import('./d3/D3TabDisclosureListed.vue'))
const D3TabDisclosureSoe = defineAsyncComponent(() => import('./d3/D3TabDisclosureSoe.vue'))
const GtOnlyOfficeSheet = defineAsyncComponent(() => import('./GtOnlyOfficeSheet.vue'))

// D3A 程序表复用 a-program-console 逻辑
const D3TabProcedure = defineAsyncComponent(() => import('./d3/D3TabAdjudication.vue')
  .then(() => ({ template: '<el-empty description="D3A 程序表（复用 a-program-console）" />' }) as any)
  .catch(() => ({ template: '<el-empty description="D3A 程序表加载中..." />' }) as any)
)

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

// ─── useD3FormData ───────────────────────────────────────────────────────────

const {
  allResponses,
  loadAll,
  saveImmediate,
  debouncedSave,
} = useD3FormData({
  wpId: wpIdRef,
  projectId: projectIdRef,
})

// ─── useD3CrossSheet ─────────────────────────────────────────────────────────

const crossSheet = useD3CrossSheet({ allResponses })

// ─── useD3DualMode ───────────────────────────────────────────────────────────

const dualMode = useD3DualMode({ wpId: wpIdRef, activeTab })

// ─── Provide openReviewDialog ────────────────────────────────────────────────

function openReviewDialog(sectionId: string): void {
  console.log('[D3] openReviewDialog:', sectionId)
}

provide('openReviewDialog', openReviewDialog)

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
      { params: { force_component_type: 'd3-prepaid-accounts' }, _silent: true } as any,
    )
    const renderData = res.data?.data ?? res.data
    if (renderData?.sheets?.[0]?.html_data?.project_context) {
      applicableStandards.value = renderData.sheets[0].html_data.project_context.applicable_standards || ''
    }
  } catch (err) {
    console.warn('[GtD3PrepaidAccounts] selfLoad render-config failed:', err)
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
.d3-prepaid-accounts {
  padding: 12px;
}

.loading-container {
  padding: 24px;
}

.d3-header-toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
  padding: 8px 12px;
  background: #f5f7fa;
  border-radius: 6px;
}

.d3-tabs {
  min-height: 400px;
}

.disclosure-container {
  padding: 8px 0;
}
</style>
