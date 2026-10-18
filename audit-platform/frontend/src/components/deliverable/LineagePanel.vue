<!--
  LineagePanel.vue — 出品物溯源面板

  Spec:    deliverable-lineage-and-writeback Task 5.2/5.3/10.1
  Design:  前端设计「Lineage_Panel 组件」
  Reqs:    3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 4.5, 5.5, 11.4

  功能：
    - 展示当前章节的数据来源清单（来源类型/标识/编辑状态）
    - OnlyOffice 书签 → section_code → 调 trace 端点
    - 跨层跳转（复用 LinkageContract.route）
    - 无锚点降级提示（旧版本出品物）
    - 复用 useLinkageTraceDrawer 抽屉状态，不新建并行面板
    - stale 章节提示"源数据已变更"+ "刷新本章节"/"刷新所有过期"按钮
      （按后端能力标志显示；按返回结果提示已刷新 / 跳过原因，落了新版本 emit refreshed 让编辑器切换 ——
       spec deliverable-trio-generation-accuracy Task 16b）
    - 终态出品物只读：signed/confirmed/archived 禁用刷新按钮
    - SSE LINKAGE_STALE_CHANGED 实时更新 stale 徽标

  UI 规范：全中文化（技术术语保留英文）+ GT 紫令牌
-->
<template>
  <div class="lineage-panel">
    <!-- 面板头部 -->
    <div class="lineage-panel__header">
      <span class="lineage-panel__title">数据溯源</span>
      <el-button
        v-if="currentSectionCode && !lineageUnsupported"
        text
        size="small"
        class="lineage-panel__refresh-btn"
        :loading="loading"
        @click="refresh"
      >
        刷新
      </el-button>
    </div>

    <!-- US-8：不支持溯源的交付件（财务报表）—— 不显示章节 UI，改给穿透指引 -->
    <div v-if="lineageUnsupported" class="lineage-panel__no-anchor">
      <el-icon class="lineage-panel__no-anchor-icon"><InfoFilled /></el-icon>
      <span>{{ lineageUnsupportedMessage }}</span>
    </div>

    <!-- 手动章节溯源（章节列表来自后端 section-states，不依赖 OnlyOffice；允许手动输入兜底旧交付物） -->
    <div v-if="!lineageUnsupported && !noAnchorAvailable" class="lineage-panel__manual">
      <el-select
        v-model="manualInput"
        filterable
        allow-create
        clearable
        default-first-option
        size="small"
        placeholder="选择或输入章节号溯源"
        class="lineage-panel__manual-select"
        @change="onManualTrace"
      >
        <el-option
          v-for="opt in sectionOptions"
          :key="opt.code"
          :value="opt.code"
          :label="opt.code"
        >
          <span class="lineage-panel__opt-code">{{ opt.code }}</span>
          <el-tag
            v-if="opt.isStale"
            size="small"
            type="warning"
            effect="light"
            class="lineage-panel__opt-stale"
          >
            已变更
          </el-tag>
        </el-option>
      </el-select>
      <el-button
        size="small"
        :loading="loading"
        class="lineage-panel__manual-btn"
        @click="onManualTrace"
      >
        溯源
      </el-button>
    </div>

    <!-- 无锚点降级提示（需求 3.5） -->
    <div v-if="!lineageUnsupported && noAnchorAvailable" class="lineage-panel__no-anchor">
      <el-icon class="lineage-panel__no-anchor-icon"><InfoFilled /></el-icon>
      <span>该出品物版本不支持溯源，请重新生成</span>
    </div>

    <!-- 未选中章节（提示用户输入章节号） -->
    <div v-else-if="!lineageUnsupported && !currentSectionCode && !noAnchorAvailable" class="lineage-panel__hint">
      <el-icon><Document /></el-icon>
      <span>请在上方输入章节号后点「溯源」，查看该章节的数据来源</span>
    </div>

    <!-- 加载中 -->
    <div v-else-if="loading" class="lineage-panel__loading">
      <el-skeleton :rows="3" animated />
    </div>

    <!-- 错误提示 -->
    <div v-else-if="error" class="lineage-panel__error">
      <el-alert :title="error" type="warning" :closable="false" show-icon />
    </div>

    <!-- 溯源结果列表 -->
    <div v-else class="lineage-panel__content">
      <!-- 当前章节信息 -->
      <div class="lineage-panel__section-info">
        <span class="lineage-panel__section-label">当前章节</span>
        <span class="lineage-panel__section-code">{{ currentSectionCode }}</span>
        <el-tag
          v-if="sectionState?.is_stale"
          type="warning"
          size="small"
          class="lineage-panel__stale-badge"
        >
          源数据已变更
        </el-tag>
      </div>

      <!-- 刷新操作栏（需求 4.5/5.5/11.4；按后端能力标志门控） -->
      <div v-if="currentSectionCode && supportsSectionRefresh" class="lineage-panel__refresh-toolbar">
        <el-tooltip
          :content="terminalStateTooltip"
          :disabled="!isTerminalState"
          placement="top"
        >
          <span class="lineage-panel__refresh-btn-wrapper">
            <el-button
              size="small"
              type="primary"
              plain
              :disabled="isTerminalState || refreshingSingle"
              :loading="refreshingSingle"
              class="lineage-panel__action-btn"
              @click="onRefreshSection"
            >
              刷新本章节
            </el-button>
          </span>
        </el-tooltip>
        <el-tooltip
          :content="terminalStateTooltip"
          :disabled="!isTerminalState"
          placement="top"
        >
          <span class="lineage-panel__refresh-btn-wrapper">
            <el-button
              size="small"
              type="warning"
              plain
              :disabled="isTerminalState || refreshingAll"
              :loading="refreshingAll"
              class="lineage-panel__action-btn"
              @click="onRefreshAllStale"
            >
              刷新所有过期
            </el-button>
          </span>
        </el-tooltip>
      </div>
      <div v-else-if="currentSectionCode" class="lineage-panel__refresh-unsupported">
        该类型交付件不支持按章节刷新；源数据变更后请整份重新生成。
      </div>

      <!-- 来源列表 -->
      <div v-if="contracts.length > 0" class="lineage-panel__sources">
        <div
          v-for="(contract, idx) in contracts"
          :key="idx"
          class="lineage-panel__source-item"
          @click="onNavigate(contract)"
        >
          <div class="lineage-panel__source-header">
            <el-tag
              :type="getSourceTagType(contract.target_type)"
              size="small"
              class="lineage-panel__source-type"
            >
              {{ getTypeLabel(contract.target_type) }}
            </el-tag>
            <el-tag
              v-if="contract.status === 'stale'"
              type="warning"
              size="small"
              effect="light"
            >
              已过期
            </el-tag>
            <el-tag
              v-else-if="contract.status === 'conflict'"
              type="danger"
              size="small"
              effect="light"
            >
              冲突
            </el-tag>
          </div>
          <div class="lineage-panel__source-body">
            <span class="lineage-panel__source-id">{{ contract.basis || contract.target_id }}</span>
            <el-icon class="lineage-panel__source-jump"><Right /></el-icon>
          </div>
        </div>
      </div>

      <!-- 无来源 -->
      <div v-else class="lineage-panel__empty">
        <span>暂无关联数据来源</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, h, ref, watch, onMounted, onUnmounted } from 'vue'
import { InfoFilled, Document, Right } from '@element-plus/icons-vue'
import { ElMessageBox, ElMessage } from 'element-plus'
import type { LinkageContract, TargetType } from '@/types/linkageContract'
import {
  UNSAVED_EDITS_MESSAGE,
  overwritePrompt,
  sectionRefreshPrompt,
  staleRefreshPrompt,
  summarizeRefresh,
  type DeliverableRefreshResult,
  type RefreshNotice,
} from './deliverableRefreshNotice'
import {
  useDeliverableLineage,
  anchorNameFromSectionCode,
} from '@/composables/useDeliverableLineage'
import { subscribeProjectEvent } from '@/services/sse/projectEventStream'
import { api } from '@/services/apiProxy'

/** 终态状态列表（signed/confirmed/archived）— 需求 11.4 */
const TERMINAL_STATUSES = ['signed', 'confirmed', 'archived'] as const

/** 刷新端点调用方自管提示：静默全局拦截（否则先弹一次通用错误；5xx 还会自动重发两次，刷新要重新导出整份附注） */
const SILENT = { _silent: true } as any

const props = withDefaults(
  defineProps<{
  projectId: string
  wordExportTaskId: string
  /** 是否明确无锚点（旧版本出品物，由父组件判定） */
  hasNoAnchors?: boolean
  /** 出品物当前状态（用于终态检测，需求 11.4） */
  deliverableStatus?: string
  /** 项目年度（刷新接口所需） */
  year?: number
  /**
   * 能力标志（后端 deliverable_capabilities 下发，前端只消费）：不支持章节刷新的交付件（报告正文 / 报表）
   * 不显示刷新按钮。缺省 false —— 原先该 prop 未声明，报告正文也显示刷新按钮、点了才报 400。
   */
  supportsSectionRefresh?: boolean
  /**
   * 溯源能力（US-8，后端下发）：财务报表恒 false。false 时**不请求** /section-states，
   * 面板只显示「报表按行取数、去报表页穿透」说明——避免空下拉 + 「请重新生成」误导。
   * 缺省 true：兼容旧后端（字段缺失时按支持处理，与原行为一致，不吞掉附注/报告正文的溯源）。
   */
  supportsLineage?: boolean
  /** 在线编辑本次会话已有修改、尚未保存回交付件 ⇒ 拒绝刷新（保存时会覆盖刷新结果） */
  editorHasUnsavedEdits?: boolean
  }>(),
  {
    // 🔴 Boolean prop 默认必须显式给 true：Vue 的 Boolean prop 转换规则会把「未传」
    // 的 boolean prop 转成 false（而非 undefined），若不给默认，父组件没传 supportsLineage
    // 时 `props.supportsLineage === false` 恒真 ⇒ 附注/报告正文的溯源会被整个吞掉、
    // 面板恒显「报表按行取数」。缺省按 true = 兼容旧后端（字段缺失时按支持处理）。
    supportsLineage: true,
  },
)

const emit = defineEmits<{
  /** 刷新落了新版本（编辑器据此切到新版本） */
  refreshed: [versionNo: number]
}>()

const wordExportTaskIdRef = computed(() => props.wordExportTaskId)
const projectIdRef = computed(() => props.projectId)

const {
  currentSectionCode,
  contracts,
  sectionState,
  loading,
  error,
  traceFromAnchor,
  traceSection,
  navigateToSource,
  clearSection,
} = useDeliverableLineage(wordExportTaskIdRef, projectIdRef)

/** 是否为无锚点状态（旧版本出品物，需求 3.5） */
const noAnchorAvailable = ref(false)

/**
 * US-8：该交付件不支持章节溯源（财务报表恒 false）。缺省按 true（兼容旧后端）。
 * 为 true 时整个溯源 UI 用说明文案替代，且不请求 /section-states。
 */
const lineageUnsupported = computed(() => props.supportsLineage === false)

/** US-8：不支持溯源时的说明文案（指明正确穿透路径，不留「请重新生成」误导）。 */
const lineageUnsupportedMessage = computed(
  () => '财务报表按报表行取数，没有章节溯源；数字来源请在「财务报表」页穿透查看',
)

/** 手动溯源输入（章节号，如「五、1」） */
const manualInput = ref('')

/** 章节下拉候选（来自后端 section-states，含 stale 标记） */
interface SectionOption {
  code: string
  isStale: boolean
}
const sectionOptions = ref<SectionOption[]>([])

/**
 * 加载本交付物的章节列表（section-states 端点），供手动溯源下拉选择。
 * 后端权威、与 OnlyOffice 无关；fail-open：拿不到时下拉为空，仍可手动输入章节号（allow-create）。
 * 返回是否取到（「刷新所有过期」据此判断过期节数是否可信：取不到不能当成「没有过期章节」）。
 */
async function loadSections(): Promise<boolean> {
  // US-8：不支持溯源的交付件（财务报表）不请求 /section-states ——
  // 该端点对报表任务恒返回 0 行章节状态，拉了只会得到空下拉 + 误导性「请重新生成」。
  if (lineageUnsupported.value) return false
  if (!props.projectId || !props.wordExportTaskId) return false
  try {
    const url = `/api/projects/${props.projectId}/deliverables/${props.wordExportTaskId}/section-states`
    const data = await api.get<{ sections: Array<{ section_code: string; is_stale: boolean }> }>(url)
    sectionOptions.value = (data?.sections || [])
      .filter((s) => s.section_code)
      .map((s) => ({ code: s.section_code, isStale: !!s.is_stale }))
    return Array.isArray(data?.sections)
  } catch {
    sectionOptions.value = []
    return false
  }
}

/**
 * 手动章节溯源：审计师输入/选择章节号后直接调 trace 端点（后端按 section_code 查询，
 * 不依赖 OnlyOffice 连接器/书签，必然可用）。currentSectionCode 是 composable 返回的
 * 响应式 ref，设置 .value 即驱动「当前章节」展示与刷新工具栏。
 */
async function onManualTrace(): Promise<void> {
  const code = manualInput.value.trim()
  if (!code) return
  noAnchorAvailable.value = false
  currentSectionCode.value = code
  await traceSection(code)
}

/** 终态检测（需求 11.4） */
const isTerminalState = computed(() => {
  if (!props.deliverableStatus) return false
  return TERMINAL_STATUSES.includes(props.deliverableStatus as any)
})

/** 终态时悬浮提示文案 */
const terminalStateTooltip = '该出品物已签字/确认/归档，不可回填或刷新'

/** 刷新加载状态 */
const refreshingSingle = ref(false)
const refreshingAll = ref(false)

// 如果父组件明确标记无锚点
watch(
  () => props.hasNoAnchors,
  (val) => {
    if (val) {
      noAnchorAvailable.value = true
      clearSection()
    }
  },
  { immediate: true },
)

/**
 * 来源类型 → 中文标签（需求 3.6）
 */
function getTypeLabel(type: TargetType | string): string {
  const map: Record<string, string> = {
    note: '附注',
    report: '报表',
    trial_balance: '审定表',
    adjustment: '调整分录',
    workpaper: '底稿',
    ledger: '序时账',
    audit_sheet: '审计表',
    attachment: '附件',
    ai: 'AI',
  }
  return map[type] || type
}

/**
 * 来源类型 → el-tag type
 */
function getSourceTagType(type: TargetType | string): 'primary' | 'success' | 'warning' | 'danger' | 'info' {
  switch (type) {
    case 'note': return 'primary'
    case 'report': return 'success'
    case 'trial_balance': return 'warning'
    case 'adjustment': return 'danger'
    default: return 'info'
  }
}

/**
 * 跨层跳转（需求 3.3）
 * 复用 LinkageContract.route 经 vue-router 导航
 */
async function onNavigate(contract: LinkageContract): Promise<void> {
  await navigateToSource(contract)
}

/**
 * 刷新当前章节溯源数据
 */
function refresh(): void {
  if (currentSectionCode.value) {
    traceSection(currentSectionCode.value)
  }
}

/** 弹确认框；用户取消返回 false */
async function confirmed(message: string, title: string, confirmButtonText: string): Promise<boolean> {
  try {
    await ElMessageBox.confirm(message, title, { confirmButtonText, cancelButtonText: '取消', type: 'warning' })
    return true
  } catch {
    return false
  }
}

/**
 * 在线编辑本次会话已有修改 ⇒ 不刷新：OnlyOffice 关闭编辑器后才回存为新版本，刷新以修改前的版本为底，
 * 之后回存的版本又会覆盖刷新结果（回调不比对版本，见 design §7.3）。
 */
function blockedByUnsavedEdits(): boolean {
  if (!props.editorHasUnsavedEdits) return false
  ElMessageBox.alert(UNSAVED_EDITS_MESSAGE, '请先保存在线编辑', {
    confirmButtonText: '我知道了',
    type: 'warning',
  }).catch(() => {})
  return true
}

/**
 * 调刷新端点：先不带确认（后端按生成时记录的块哈希检测人工修改），检测到人工修改再二次确认后带确认重发
 * （需求 5.5 / 5.7：只在会覆盖人工编辑时提示）。用户取消返回 null。
 */
async function postRefresh(
  endpoint: 'refresh-section' | 'refresh-stale',
  body: Record<string, unknown>,
): Promise<DeliverableRefreshResult | null> {
  const url = `/api/projects/${props.projectId}/deliverables/${props.wordExportTaskId}/${endpoint}`
  const year = props.year || new Date().getFullYear()
  let res = await api.post<DeliverableRefreshResult>(url, { ...body, year, confirm_overwrite: false }, SILENT)
  if (res?.requires_confirm) {
    const pending = res.pending_confirm_sections || []
    if (!(await confirmed(overwritePrompt(pending), '覆盖手动修改', '覆盖并刷新'))) return null
    res = await api.post<DeliverableRefreshResult>(url, { ...body, year, confirm_overwrite: true }, SILENT)
  }
  return res
}

/** 刷新结果提示：成功 / 无需刷新用轻提示；有跳过原因或提醒逐条列出（内联样式：弹窗挂在 body 下，scoped 样式匹配不到） */
function showRefreshNotice(notice: RefreshNotice): void {
  if (notice.kind === 'success') {
    ElMessage.success(notice.lines.join('；'))
    return
  }
  if (notice.kind === 'info') {
    ElMessage.info(notice.lines.join('；'))
    return
  }
  const body = h(
    'div',
    { style: 'max-height: 50vh; overflow-y: auto; line-height: 1.6' },
    notice.lines.map((line) => h('p', { style: 'margin: 0 0 6px' }, `• ${line}`)),
  )
  ElMessageBox.alert(body, notice.title, { confirmButtonText: '我知道了', type: 'warning' }).catch(() => {})
}

/** 刷新完成：提示结果；落了新版本 ⇒ 通知编辑器切换，并重取章节状态（过期标记已清） */
function afterRefresh(res: DeliverableRefreshResult | null): void {
  if (res === null) return
  showRefreshNotice(summarizeRefresh(res))
  if (typeof res.version_no === 'number' && res.refreshed?.length) {
    emit('refreshed', res.version_no)
  }
  refresh()
  void loadSections()
}

function showRefreshError(e: any, fallback: string): void {
  const status = e?.response?.status
  const detail = e?.response?.data?.message || e?.response?.data?.detail
  if (status === 403) {
    ElMessage.error('权限不足：需要编辑权限')
  } else if (status === 409) {
    ElMessage.warning(detail || '该出品物已终态，不可刷新')
  } else {
    ElMessage.error(detail || e?.message || fallback)
  }
}

/**
 * "刷新本章节"按钮回调 —— POST .../refresh-section
 * 刷新 = 按最新源数据同口径重新导出，把该节整块换进已保存的最新版本，另存为新版本（spec deliverable-trio-generation-accuracy §7）。
 */
async function onRefreshSection(): Promise<void> {
  const code = currentSectionCode.value
  if (!code || isTerminalState.value || blockedByUnsavedEdits()) return
  if (!(await confirmed(sectionRefreshPrompt(code), '确认刷新本章节', '确认刷新'))) return

  refreshingSingle.value = true
  try {
    afterRefresh(await postRefresh('refresh-section', { section_code: code }))
  } catch (e: any) {
    showRefreshError(e, '刷新失败')
  } finally {
    refreshingSingle.value = false
  }
}

/**
 * "刷新所有过期"按钮回调 —— POST .../refresh-stale（全部过期章节一次重新导出、只落一个新版本）
 */
async function onRefreshAllStale(): Promise<void> {
  if (isTerminalState.value || blockedByUnsavedEdits()) return
  // 先取最新章节状态：确认框写明节数；确实没有过期章节就不打扰（取不到时交给后端判断）
  const loaded = await loadSections()
  const staleCount = loaded ? sectionOptions.value.filter((o) => o.isStale).length : null
  if (staleCount === 0) {
    ElMessage.info('当前没有过期章节，无需刷新')
    return
  }
  if (!(await confirmed(staleRefreshPrompt(staleCount), '确认刷新所有过期章节', '确认刷新'))) return

  refreshingAll.value = true
  try {
    afterRefresh(await postRefresh('refresh-stale', {}))
  } catch (e: any) {
    showRefreshError(e, '批量刷新失败')
  } finally {
    refreshingAll.value = false
  }
}

/**
 * SSE LINKAGE_STALE_CHANGED 实时监听（需求 4.5）
 * 当上游数据变更级联标记章节 stale 时，后端推 SSE 事件，前端实时更新徽标。
 *
 * 迁移到项目事件流单例总线（frontend-sse-connection-consolidation）：订阅共享的、经
 * Authorization header 鉴权的连接（每项目一条），断线重连/退避由总线统一负责。
 * 🔴 附带修复：原 `useSSEReconnect` 用 native EventSource 无 token → 端点鉴权后恒 401 降级，
 * 实时徽标其实从未生效；迁移后 LINKAGE_STALE_CHANGED 首次真正送达。
 */
const _lineageSub = subscribeProjectEvent(
  props.projectId,
  'LINKAGE_STALE_CHANGED',
  () => {
    // 当前章节可能变 stale → 刷新溯源徽标 + 刷新下拉 stale 标记
    if (currentSectionCode.value) {
      traceSection(currentSectionCode.value)
    }
    loadSections()
  },
)

onMounted(loadSections)
function closeSSE(): void {
  _lineageSub.close()
}
onUnmounted(closeSSE)

/**
 * 供父组件调用：从 OnlyOffice 获取的书签名触发溯源
 */
function onBookmarkDetected(anchorName: string): void {
  if (!anchorName) {
    // 无法解析锚点
    if (props.hasNoAnchors) {
      noAnchorAvailable.value = true
    }
    clearSection()
    return
  }
  noAnchorAvailable.value = false
  // 优先与已加载的权威章节列表精确匹配：避免 anchor→section_code 逆映射对多分隔符
  // 章节（如「五、12·1」→ sec_五_12_1 → 无法还原·）失真，并天然忽略非本文档的杂散 Tag。
  const match = sectionOptions.value.find(
    (o) => anchorNameFromSectionCode(o.code) === anchorName,
  )
  if (match) {
    currentSectionCode.value = match.code
    manualInput.value = match.code // 同步下拉，反映当前光标所在章节
    traceSection(match.code)
    return
  }
  // 回退：未加载章节列表或未匹配到 → 逆映射解析（单顿号章节可靠）
  traceFromAnchor(anchorName)
}

/**
 * 供父组件调用：当检测到文档无任何 sec_ 书签时标记降级
 */
function setNoAnchors(): void {
  noAnchorAvailable.value = true
  clearSection()
}

// 暴露给父组件
defineExpose({
  onBookmarkDetected,
  setNoAnchors,
  traceSection,
  refresh,
  onRefreshSection,
  onRefreshAllStale,
  isTerminalState,
  closeSSE,
})
</script>

<style scoped>
.lineage-panel {
  display: flex;
  flex-direction: column;
  height: 100%;
  font-size: 13px;
  color: var(--el-text-color-primary);
}

.lineage-panel__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  border-bottom: 1px solid var(--gt-color-border-purple-light, #d8b8ee);
  background: var(--gt-color-primary-bg, #f4f0fa);
}

.lineage-panel__title {
  font-size: 14px;
  font-weight: 600;
  color: var(--gt-color-primary, #4b2d77);
}

.lineage-panel__refresh-btn {
  color: var(--gt-color-primary, #4b2d77);
}

.lineage-panel__manual {
  display: flex;
  gap: 8px;
  align-items: center;
  padding: 10px 16px;
  border-bottom: 1px solid var(--el-border-color-lighter);
}

.lineage-panel__manual-select {
  flex: 1;
  min-width: 0;
}

.lineage-panel__manual-btn {
  flex-shrink: 0;
}

.lineage-panel__opt-code {
  font-variant-numeric: tabular-nums;
}

.lineage-panel__opt-stale {
  margin-left: 8px;
}

.lineage-panel__no-anchor {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 32px 16px;
  text-align: center;
  color: var(--el-text-color-secondary);
  gap: 8px;
}

.lineage-panel__no-anchor-icon {
  font-size: 24px;
  color: var(--el-color-warning);
}

.lineage-panel__hint {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 32px 16px;
  text-align: center;
  color: var(--el-text-color-secondary);
  gap: 8px;
}

.lineage-panel__loading {
  padding: 16px;
}

.lineage-panel__error {
  padding: 16px;
}

.lineage-panel__content {
  flex: 1;
  overflow-y: auto;
  padding: 12px 16px;
}

.lineage-panel__section-info {
  display: flex;
  align-items: center;
  gap: 8px;
  padding-bottom: 12px;
  border-bottom: 1px solid var(--el-border-color-lighter);
  margin-bottom: 12px;
}

.lineage-panel__section-label {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.lineage-panel__section-code {
  font-weight: 600;
  color: var(--gt-color-primary, #4b2d77);
}

.lineage-panel__stale-badge {
  margin-left: auto;
}

.lineage-panel__refresh-toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 0 12px;
  border-bottom: 1px solid var(--el-border-color-lighter);
  margin-bottom: 12px;
}

.lineage-panel__refresh-btn-wrapper {
  display: inline-flex;
}

.lineage-panel__refresh-unsupported {
  padding: 8px 0 12px;
  margin-bottom: 12px;
  border-bottom: 1px solid var(--el-border-color-lighter);
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.lineage-panel__action-btn {
  font-size: 12px;
}

.lineage-panel__action-btn:not(.is-disabled) {
  --el-button-text-color: var(--gt-color-primary, #4b2d77);
  --el-button-border-color: var(--gt-color-border-purple-light, #d8b8ee);
  --el-button-bg-color: var(--gt-color-primary-bg, #f4f0fa);
}

.lineage-panel__action-btn:not(.is-disabled):hover {
  --el-button-hover-text-color: var(--gt-color-primary, #4b2d77);
  --el-button-hover-border-color: var(--gt-color-primary, #4b2d77);
  --el-button-hover-bg-color: var(--gt-color-primary-bg, #f4f0fa);
}

.lineage-panel__sources {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.lineage-panel__source-item {
  padding: 10px 12px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.2s;
}

.lineage-panel__source-item:hover {
  border-color: var(--gt-color-primary, #4b2d77);
  background: var(--gt-color-primary-bg, #f4f0fa);
  box-shadow: 0 1px 4px rgba(75, 45, 119, 0.08);
}

.lineage-panel__source-header {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 4px;
}

.lineage-panel__source-type {
  font-size: 11px;
}

.lineage-panel__source-body {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.lineage-panel__source-id {
  font-size: 13px;
  color: var(--el-text-color-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  flex: 1;
}

.lineage-panel__source-jump {
  color: var(--gt-color-primary, #4b2d77);
  font-size: 14px;
  flex-shrink: 0;
}

.lineage-panel__empty {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
  color: var(--el-text-color-secondary);
}
</style>
