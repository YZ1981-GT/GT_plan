<template>
  <!-- ═══ 阻断性横幅：常驻显眼不折叠 ═══ -->
  <ArchivedBanner />
  <ConsolLockedBanner />
  <el-alert
    v-if="editLock?.locked?.value && !editLock?.isMine?.value"
    type="warning"
    :closable="false"
    style="margin-bottom: 8px"
  >
    {{ editLock?.lockedBy?.value || '其他用户' }} 正在编辑，当前为只读模式
  </el-alert>

  <!-- ═══ 信息性横幅：折叠为摘要行 ═══ -->
  <div v-if="infoBannerCount > 0" class="gt-banner-collapse">
    <div v-if="!bannersExpanded" class="gt-banner-collapse__summary" @click="bannersExpanded = true">
      <span class="gt-banner-collapse__icon">⚠</span>
      <span class="gt-banner-collapse__text">{{ infoBannerCount }} 项待处理</span>
      <el-button text size="small" type="primary">展开</el-button>
    </div>
    <div v-else class="gt-banner-collapse__expanded">
      <div class="gt-banner-collapse__header">
        <span>信息横幅（{{ infoBannerCount }} 项）</span>
        <el-button text size="small" @click="bannersExpanded = false">收起</el-button>
      </div>
      <AiContentPendingBanner :project-id="projectId" />
      <ConflictBanner :project-id="projectId" @view="conflictPanelVisible = true" />
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
              text size="small"
              @click="$emit('jump-to-prereq')"
            >去完成 →</el-button>
          </div>
        </template>
      </el-alert>
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
    </div>
  </div>

  <ConflictResolutionPanel v-model="conflictPanelVisible" :project-id="projectId" @resolved="onConflictResolved" />
  <TrustScorePanel ref="trustScorePanelRef" :project-id="projectId" />
  <StatusMachinePanel ref="smPanelRef" module="workpaper" :instance-id="wpId" />
</template>

<script setup lang="ts">
/**
 * EditorBanners — 底稿编辑器顶部横幅区 [wp-frontend-ux-polish Task 2]
 * 阻断性（归档/编辑锁）：常驻显眼不折叠
 * 信息性（AI/冲突/前置状态/stale）：折叠为一行"⚠ N 项待处理" + 展开/收起
 */
import { ref, computed } from 'vue'
import type { CycleTypeFlags } from '@/composables/useCycleType'
import type { StaleAffectedItem } from '@/composables/useStaleImpact'
import type { WorkpaperDetail } from '@/services/workpaperApi'
import ArchivedBanner from '@/components/common/ArchivedBanner.vue'
import ConsolLockedBanner from '@/components/common/ConsolLockedBanner.vue'
import AiContentPendingBanner from '@/components/ai/AiContentPendingBanner.vue'
import ConflictBanner from '@/components/conflict/ConflictBanner.vue'
import ConflictResolutionPanel from '@/components/conflict/ConflictResolutionPanel.vue'
import TrustScorePanel from '@/components/trust/TrustScorePanel.vue'
import StatusMachinePanel from '@/components/status_machine/StatusMachinePanel.vue'

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

const bannersExpanded = ref(false)
const conflictPanelVisible = ref(false)
const trustScorePanelRef = ref()
const smPanelRef = ref()

const infoBannerCount = computed(() => {
  let count = 2 // AI pending + 冲突 banner 始终存在
  if (props.prerequisiteBanner && showPrereqBanner.value) count += 1
  if (props.showStaleImpactPanel && props.staleImpact.totalAffected.value > 0) count += 1
  return count
})

const showPrereqBanner = computed(() => {
  const wpCode = props.wpDetail?.wp_code || ''
  const ct = props.cycleType
  return wpCode.startsWith('E1')
    || ct.isDCycle.value || ct.isFCycle.value || ct.isHCycle.value
    || ct.isICycle.value || ct.isGCycle.value || ct.isKCycle.value
    || ct.isLCycle.value || ct.isMCycle.value || ct.isNCycle.value
})

function onConflictResolved(_id: string, _resolution: string) { /* noop */ }

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

<style scoped>
.gt-banner-collapse { margin-bottom: 8px; }
.gt-banner-collapse__summary { display: flex; align-items: center; gap: 8px; padding: 8px 12px; background: var(--el-color-warning-light-9); border: 1px solid var(--el-color-warning-light-5); border-radius: 4px; cursor: pointer; transition: background 0.2s; }
.gt-banner-collapse__summary:hover { background: var(--el-color-warning-light-8); }
.gt-banner-collapse__icon { font-size: 16px; }
.gt-banner-collapse__text { flex: 1; font-size: var(--gt-font-size-sm); color: var(--el-color-warning-dark-2); font-weight: 500; }
.gt-banner-collapse__expanded { border: 1px solid var(--el-color-warning-light-5); border-radius: 4px; padding: 8px; }
.gt-banner-collapse__header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; font-size: var(--gt-font-size-sm); color: var(--gt-color-text-secondary); }
.gt-prereq-banner { margin-bottom: 8px; }
.gt-prereq-banner-content { display: flex; align-items: center; gap: 8px; }
.gt-stale-impact-bar { margin-top: 8px; padding: 8px; background: var(--el-color-warning-light-9); border-radius: 4px; }
.gt-stale-impact-bar__head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px; }
.gt-stale-impact-bar__title { font-size: var(--gt-font-size-sm); }
.gt-stale-impact-bar__list { display: flex; flex-wrap: wrap; gap: 4px; }
.gt-stale-impact-bar__tag { cursor: pointer; }
.gt-stale-impact-bar__more { font-size: var(--gt-font-size-xs); color: var(--gt-color-text-tertiary); align-self: center; }
</style>
