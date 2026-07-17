<script setup lang="ts">
/**
 * EvidenceGovernanceCenter — 附件·OCR·AI·证据链治理中心（路由 /projects/:projectId/evidence-governance）
 *
 * Spec: attachment-ocr-ai-evidence-governance-hardening
 * 把已实现但未挂载的治理组件/composable 收敛为一个项目级可达界面，逐一接入后端真实端点：
 *  - 证据关系（EvidenceRef + 影响路径 + 关系抽屉）
 *  - OCR 治理（时间线 + 差异确认 + 原子写回）
 *  - 引用定位（Citation locate/validate）
 *  - AI 门禁（confirm/revise/reject + FormalOutput preflight/finalize）
 *  - 复核证据（bind/close/reopen + 完成阻断）
 *  - 归档清单（preflight/build/verify）
 *  - 法定保全（create/scope/release + purge 四条件）
 *  - 治理指标（全局可观测性）
 *
 * UI 只展示与触发后端治理门禁，不弱化任何规则。
 */
import { ref, computed, watch } from 'vue'
import { useRoute } from 'vue-router'
import { storeToRefs } from 'pinia'
import { useProjectStore } from '@/stores/project'
import { useRoleContextStore } from '@/stores/roleContext'
import { useAuthStore } from '@/stores/auth'
import EvidenceRefsTab from '@/components/evidence-governance/EvidenceRefsTab.vue'
import OcrGovernanceTab from '@/components/evidence-governance/OcrGovernanceTab.vue'
import CitationTab from '@/components/evidence-governance/CitationTab.vue'
import AiGateTab from '@/components/evidence-governance/AiGateTab.vue'
import ReviewEvidenceTab from '@/components/evidence-governance/ReviewEvidenceTab.vue'
import ArchiveManifestTab from '@/components/evidence-governance/ArchiveManifestTab.vue'
import LegalHoldTab from '@/components/evidence-governance/LegalHoldTab.vue'
import MetricsTab from '@/components/evidence-governance/MetricsTab.vue'

const route = useRoute()
const projectStore = useProjectStore()
const roleStore = useRoleContextStore()
const authStore = useAuthStore()
const { year, clientName } = storeToRefs(projectStore)

const projectId = computed(() => route.params.projectId as string)
/** 角色：优先项目角色，回退系统/有效角色 */
const role = computed(
  () =>
    roleStore.currentProjectRole?.role ||
    roleStore.effectiveRole ||
    (authStore.user?.role as string) ||
    'readonly',
)

const activeTab = ref('refs')

// 项目角色确保加载（DefaultLayout 亦会加载，此处兜底）
watch(
  projectId,
  (pid) => {
    if (pid) roleStore.loadProjectRole(pid)
  },
  { immediate: true },
)
</script>

<template>
  <div class="evidence-governance-center">
    <div class="page-header">
      <div class="header-info">
        <h2 class="page-title">证据链治理中心</h2>
        <div class="header-meta">
          <el-tag v-if="clientName" type="info" size="small">{{ clientName }}</el-tag>
          <el-tag type="info" size="small">{{ year }} 年度</el-tag>
          <el-tag size="small">当前角色：{{ role }}</el-tag>
        </div>
      </div>
    </div>

    <el-alert
      type="info"
      :closable="false"
      show-icon
      title="附件·OCR·AI·证据链治理：所有操作直连后端治理门禁（项目隔离 / 版本不可变 / 人工确认硬门禁 / stale 传播 / 归档验签 / 法定保全）。"
      style="margin-bottom: 12px"
    />

    <el-tabs v-model="activeTab" type="border-card" class="gov-tabs">
      <el-tab-pane label="证据关系" name="refs" lazy>
        <EvidenceRefsTab :project-id="projectId" :year="year" />
      </el-tab-pane>
      <el-tab-pane label="OCR 治理" name="ocr" lazy>
        <OcrGovernanceTab :project-id="projectId" :year="year" :role="role" />
      </el-tab-pane>
      <el-tab-pane label="引用定位" name="citation" lazy>
        <CitationTab :project-id="projectId" :year="year" />
      </el-tab-pane>
      <el-tab-pane label="AI 门禁" name="ai" lazy>
        <AiGateTab :project-id="projectId" :year="year" :role="role" />
      </el-tab-pane>
      <el-tab-pane label="复核证据" name="review" lazy>
        <ReviewEvidenceTab :project-id="projectId" :year="year" />
      </el-tab-pane>
      <el-tab-pane label="归档清单" name="archive" lazy>
        <ArchiveManifestTab :project-id="projectId" :year="year" />
      </el-tab-pane>
      <el-tab-pane label="法定保全" name="hold" lazy>
        <LegalHoldTab :project-id="projectId" :year="year" />
      </el-tab-pane>
      <el-tab-pane label="治理指标" name="metrics" lazy>
        <MetricsTab />
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<style scoped>
.evidence-governance-center {
  padding: 16px 20px;
}
.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}
.page-title {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}
.header-meta {
  display: flex;
  gap: 8px;
  margin-top: 6px;
}
.gov-tabs :deep(.el-tabs__content) {
  padding: 16px;
}
</style>
