<template>
  <!-- 审计导航图全屏对话框（默认全屏，支持拖拽调整） -->
  <el-dialog
    :model-value="visible"
    :fullscreen="auditNavFullscreen"
    :width="auditNavFullscreen ? '100%' : '85%'"
    :show-close="false"
    append-to-body
    class="gt-audit-nav-dialog"
    :close-on-click-modal="false"
    destroy-on-close
    @update:model-value="$emit('update:visible', $event)"
  >
    <template #header>
      <div class="gt-audit-nav-dialog__header">
        <div class="gt-audit-nav-dialog__title">
          <span class="gt-audit-nav-dialog__icon">🧭</span>
          <span>审计导航图</span>
          <span v-if="wpCode" class="gt-audit-nav-dialog__code">{{ wpCode }}</span>
        </div>
        <div class="gt-audit-nav-dialog__actions">
          <el-button size="small" text @click="auditNavFullscreen = !auditNavFullscreen">
            {{ auditNavFullscreen ? '⊟ 退出全屏' : '⊞ 全屏' }}
          </el-button>
          <el-button size="small" text @click="$emit('update:visible', false)">✕</el-button>
        </div>
      </div>
    </template>
    <div class="gt-audit-nav-dialog__body">
      <WorkpaperAuditNav
        v-if="visible"
        :project-id="projectId"
        :wp-id="wpId"
        :wp-code="wpCode || 'E1'"
      />
    </div>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import WorkpaperAuditNav from '@/components/workpaper/WorkpaperAuditNav.vue'

defineProps<{
  projectId: string
  wpId: string
  wpCode: string
  visible: boolean
}>()

defineEmits<{
  'update:visible': [val: boolean]
}>()

// 全屏切换状态（内部管理）
const auditNavFullscreen = ref(true)
</script>
