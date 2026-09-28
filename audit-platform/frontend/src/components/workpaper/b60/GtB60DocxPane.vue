<script setup lang="ts">
/**
 * GtB60DocxPane — B60 的 8 个 docx 子底稿双模式承载壳
 *
 * 统一封装「结构化视图 / 在线编辑」双模式：
 * - 结构化视图通过默认插槽承载专属结构化组件
 * - 在线编辑走 legacy `GtOnlyOfficeSheet`（本宿主**无受管 sheet**，见下方 legacyOoMode 注释）
 * - 无子底稿 wp 记录时在线编辑不可选（OnlyOffice 需 wp_id + sheet 才能拉配置）
 *
 * ⚠️ 文件头原先写着「切到在线编辑前先 GET onlyoffice-config『拉取成功』才显示」——
 *    该行为在 legacy `useB60DualMode` 删除后就不存在了（后续的 `usePilotBridgeAdapter`
 *    零 API 调用）。这句已按现状改写；`entry_source_facts` 的扫描器正是因为这段注释
 *    才必须剥注释后再判形态。
 *
 * Spec: b60-strategy-rework（直接修复）
 */
import { ref, computed } from 'vue'
import { defineAsyncComponent } from 'vue'
import ErrorBoundary from '@/components/ErrorBoundary.vue'

const GtOnlyOfficeSheet = defineAsyncComponent(() => import('../GtOnlyOfficeSheet.vue'))

const props = withDefaults(defineProps<{
  /** 承载 OnlyOffice 文档的 wp_id（子底稿无独立 wp 记录时为空，则仅结构化视图） */
  wpId: string
  projectId: string
  sheetName: string
  structuredLabel?: string
  /** 是否已有结构化视图（无则仅在线编辑，不显示切换） */
  hasStructured?: boolean
  readonly?: boolean
}>(), {
  structuredLabel: '结构化视图',
  hasStructured: true,
  readonly: false,
})

// 无 wp 记录则无法在线编辑（OnlyOffice 需 wp_id+sheet 拉配置）
const canOnline = computed(() => !!props.wpId)

// ═══ 为什么这 8 个 docx 子底稿**不接** sync bridge ═══════════════════════════
//
// manifest 里本宿主自己的 entry 是 `xlsx/b60/gt-b60-docx-pane`，字段逐条说明它无受管面：
//   · `independent_entry: false` + `parent_entry_id: "xlsx/b60/gt-b60-bundle"`
//   · `migration_state: "parent_duplicate"`（登记它只为盘清 OO 挂载点，不是独立迁移对象）
//   · `adapter_id: null` + `legacy_reasons: [..., "missing_adapter"]`
//   · `backend/data/workpaper_sync_contracts/` 下**没有**它的契约
// 而父 entry 的契约 `b60.hour_budget.json` 只声明一张受管 sheet `b601-managed`
// （`B60-1工时预算与控制表`）—— 与这 8 个 docx 子底稿无交集。
//
// 🔴 这里原来挂的是 `usePilotBridgeAdapter` 且**硬写了父 entry 的 id**：它不做任何
//    API 调用（`switchMode()` 只置 ref + 写 localStorage、`isOoAvailable` 硬编码
//    `ref(true)`），所以那面「在线编辑就绪」的绿 tag 是无条件亮的、entry_id 错配也
//    没有可见症状。换成本地 ref 后不再借用父 entry 身份，与 G7 的非受管 sheet 同范式。
const legacyOoMode = ref(false)
const currentMode = computed<'html' | 'onlyoffice'>(() =>
  legacyOoMode.value ? 'onlyoffice' : 'html',
)

const modeOptions = computed(() => [
  { label: props.structuredLabel, value: 'html' as const },
  { label: '在线编辑', value: 'onlyoffice' as const, disabled: !canOnline.value },
])

function onModeChange(val: string | number | boolean): void {
  if (val === 'onlyoffice' && !canOnline.value) return
  legacyOoMode.value = val === 'onlyoffice'
}

// OnlyOffice 就绪状态提示
const ooStatus = computed(() => {
  if (!canOnline.value) return { type: 'info' as const, text: '在线编辑需先生成该子底稿' }
  return { type: 'info' as const, text: '在线编辑独立于结构化视图（本子底稿无受管 sheet）' }
})

// 无结构化视图时直接强制在线编辑；无 wpId 时强制结构化
const effectiveMode = computed(() => {
  if (!props.hasStructured) return 'onlyoffice'
  if (!canOnline.value) return 'html'
  return currentMode.value
})
</script>

<template>
  <div class="gt-b60-docx-pane">
    <div class="pane-mode-bar">
      <el-segmented
        v-if="hasStructured"
        :model-value="currentMode"
        :options="modeOptions"
        @change="onModeChange"
      />
      <el-tag :type="ooStatus.type" size="small" effect="light" class="oo-status-tag">
        {{ ooStatus.text }}
      </el-tag>
    </div>

    <!-- 结构化视图 -->
    <div v-if="effectiveMode === 'html'" class="pane-structured">
      <slot />
    </div>

    <!-- 在线编辑（拉取成功后才渲染） -->
    <ErrorBoundary v-else>
      <GtOnlyOfficeSheet
        :wp-id="props.wpId"
        :sheet-name="props.sheetName"
        :project-id="props.projectId"
        :readonly="props.readonly"
      />
    </ErrorBoundary>
  </div>
</template>

<style scoped>
.gt-b60-docx-pane {
  display: flex;
  flex-direction: column;
  gap: 12px;
  font-size: 13px;
}

.pane-mode-bar {
  display: flex;
  align-items: center;
  gap: 12px;
}

.oo-status-tag {
  flex-shrink: 0;
}

.pane-structured {
  min-height: 200px;
}
</style>
