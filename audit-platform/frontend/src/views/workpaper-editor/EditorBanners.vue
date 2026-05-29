<template>
  <!-- 归档横幅 -->
  <ArchivedBanner />

  <!-- AI 内容 pending 顶部 banner -->
  <AiContentPendingBanner :project-id="projectId" />

  <!-- 跨模块冲突 banner -->
  <ConflictBanner :project-id="projectId" @view="conflictPanelVisible = true" />
  <ConflictResolutionPanel
    v-model="conflictPanelVisible"
    :project-id="projectId"
    @resolved="onConflictResolved"
  />

  <!-- 数字信任度面板 -->
  <TrustScorePanel ref="trustScorePanelRef" :project-id="projectId" />

  <!-- 可解释状态机面板 -->
  <StatusMachinePanel ref="smPanelRef" module="workpaper" :instance-id="wpId" />

  <!-- 编辑锁提示 -->
  <el-alert
    v-if="editLock?.locked?.value && !editLock?.isMine?.value"
    type="warning"
    :closable="false"
    style="margin-bottom: 8px"
  >
    {{ editLock?.lockedBy?.value || '其他用户' }} 正在编辑，当前为只读模式
  </el-alert>

  <!-- 前置状态横幅 -->
  <el-alert
    v-if="prerequisiteBanner && showPrereqBanner"
    :type="prerequisiteBanner.type"
    :closable="false"
    class="gt-prereq-banner"
  >
    <template #default>
      <div class="gt-prereq-banner-content">
        <span>{{ prerequisiteBanner.message }}</span>
        <el-button
          v-if="prerequisiteBanner.type !== 'success'"
          text
          size="small"
          @click="$emit('jump-to-prereq')"
        >去完成 →</el-button>
      </div>
    </template>
  </el-alert>

  <!-- Stale 影响范围横条 -->
  <div v-if="showStaleImpactPanel && staleImpact.totalAffected.value > 0" class="gt-stale-impact-bar">
    <div class="gt-stale-impact-bar__head">
      <span class="gt-stale-impact-bar__title">
        ⚠ 本次保存影响 <strong>{{ staleImpact.totalAffected.value }}</strong> 个下游对象
      </span>
      <el-button text size="small" @click="$emit('update:showStaleImpactPanel', false)">收起</el-button>
    </div>
    <div class="gt-stale-impact-bar__list">
      <el-tag
        v-for="(item, idx) in staleImpact.affected.value.slice(0, 12)"
        :key="`stale-${idx}`"
        size="small"
        :type="staleImpactTagType(item)"
        class="gt-stale-impact-bar__tag"
        @click="$emit('stale-item-click', item)"
      >
        {{ formatStaleItem(item) }}
      </el-tag>
      <span v-if="staleImpact.affected.value.length > 12" class="gt-stale-impact-bar__more">
        +{{ staleImpact.affected.value.length - 12 }} 个
      </span>
    </div>
  </div>
</template>

<script setup lang="ts">
/**
 * EditorBanners — 底稿编辑器顶部横幅区
 *
 * 包含：归档 / AI pending / 冲突调解 / 信任度 / 状态机 / 编辑锁 / 前置状态 / stale 影响
 */
import { ref, computed } from 'vue'
import type { CycleTypeFlags } from '@/composables/useCycleType'
import type { StaleAffectedItem } from '@/composables/useStaleImpact'
import type { WorkpaperDetail } from '@/services/workpaperApi'
import ArchivedBanner from '@/components/common/ArchivedBanner.vue'
import AiContentPendingBanner from '@/components/ai/AiContentPendingBanner.vue'
import ConflictBanner from '@/components/conflict/ConflictBanner.vue'
import ConflictResolutionPanel from '@/components/conflict/ConflictResolutionPanel.vue'
import TrustScorePanel from '@/components/trust/TrustScorePanel.vue'
import StatusMachinePanel from '@/components/status_machine/StatusMachinePanel.vue'

// ─── Props & Emits ───────────────────────────────────────────────────────────

interface EditingLockAPI {
  locked: { value: boolean }
  isMine: { value: boolean }
  lockedBy: { value: string | null }
}

interface PrerequisiteBannerData {
  type: 'success' | 'warning' | 'error' | 'info'
  message: string
}

interface StaleImpactAPI {
  affected: { value: StaleAffectedItem[] }
  totalAffected: { value: number }
}

const props = defineProps<{
  projectId: string
  wpId: string
  wpDetail: WorkpaperDetail | null
  cycleType: CycleTypeFlags
  editLock: EditingLockAPI | null
  prerequisiteBanner: PrerequisiteBannerData | null
  staleImpact: StaleImpactAPI
  showStaleImpactPanel: boolean
}>()

defineEmits<{
  'conflict-resolved': [id: string, resolution: string]
  'stale-item-click': [item: StaleAffectedItem]
  'jump-to-prereq': []
  'update:showStaleImpactPanel': [val: boolean]
}>()

// ─── Internal State ──────────────────────────────────────────────────────────

const conflictPanelVisible = ref(false)
const trustScorePanelRef = ref()
const smPanelRef = ref()

// ─── Computed ────────────────────────────────────────────────────────────────

/** 前置状态横幅仅在 E1/D/F/G/H/I/K/L/M/N 循环显示 */
const showPrereqBanner = computed(() => {
  const wpCode = props.wpDetail?.wp_code || ''
  const ct = props.cycleType
  return wpCode.startsWith('E1')
    || ct.isDCycle.value || ct.isFCycle.value || ct.isHCycle.value
    || ct.isICycle.value || ct.isGCycle.value || ct.isKCycle.value
    || ct.isLCycle.value || ct.isMCycle.value || ct.isNCycle.value
})

// ─── Helpers ─────────────────────────────────────────────────────────────────

function onConflictResolved(id: string, resolution: string) {
  // 调解后 banner 自动从列表移除；保留 hook 供后续扩展
  void id
  void resolution
}

function formatStaleItem(item: StaleAffectedItem): string {
  if (item.target_module) {
    const code = item.note_section_code || item.report_row_code || ''
    const moduleName = item.target_module === 'disclosure_notes' ? '附注'
      : item.target_module === 'audit_report' ? '审计报告'
      : item.target_module === 'financial_report' ? '财务报表'
      : item.target_module === 'trial_balance' ? '试算表'
      : item.target_module === 'adjustments' ? '调整分录'
      : item.target_module === 'misstatements' ? '错报'
      : item.target_module
    return code ? `${moduleName}.${code}` : moduleName
  }
  const wp = item.wp_code || '?'
  const cell = item.cell ? `.${item.cell}` : ''
  const sheet = item.sheet ? `[${item.sheet.slice(0, 12)}]` : ''
  return `${wp}${sheet}${cell}`
}

function staleImpactTagType(item: StaleAffectedItem): 'success' | 'warning' | 'danger' | 'info' {
  if (item.severity === 'blocking' || item.severity === 'required') return 'danger'
  if (item.severity === 'warning') return 'warning'
  if (item.severity === 'info') return 'info'
  return 'warning'
}
</script>
