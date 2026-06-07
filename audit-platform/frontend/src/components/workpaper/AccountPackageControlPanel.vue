<!--
  AccountPackageControlPanel.vue — 程序状态控制台

  spec workpaper-account-package-d1-d2-pilot Task 4.1 / 5.1
  展示各程序的执行状态（已完成/进行中/未开始/不适用），支持更新。

  Validates: Requirements 2.3, 5.1
-->
<template>
  <div class="gt-control-panel">
    <h4 class="gt-control-panel__title">程序状态</h4>
    <div class="gt-control-panel__list">
      <div
        v-for="status in programStatuses"
        :key="status.program_code"
        class="gt-control-panel__item"
      >
        <div class="gt-control-panel__item-main">
          <span class="gt-control-panel__code">{{ status.program_code }}</span>
          <el-tag
            :type="statusTagType(status.status)"
            size="small"
            effect="light"
          >
            {{ statusLabel(status.status) }}
          </el-tag>
          <el-tag
            v-if="!status.applicable"
            type="info"
            size="small"
            effect="plain"
          >
            不适用
          </el-tag>
        </div>
        <div class="gt-control-panel__item-actions">
          <el-dropdown trigger="click" @command="(cmd: string) => handleCommand(status.program_code, cmd)">
            <el-button size="small" text>
              操作 <el-icon><arrow-down /></el-icon>
            </el-button>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="in_progress">标记进行中</el-dropdown-item>
                <el-dropdown-item command="completed">标记已完成</el-dropdown-item>
                <el-dropdown-item command="not_applicable">标记不适用</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
      </div>
      <div v-if="programStatuses.length === 0" class="gt-control-panel__empty">
        暂无程序状态记录
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ArrowDown } from '@element-plus/icons-vue'
import type { ProgramStatus, ProgramStatusUpdate } from '@/composables/useAccountPackage'

defineProps<{
  projectId: string
  packageId: string
  programStatuses: ProgramStatus[]
}>()

const emit = defineEmits<{
  'update-status': [programCode: string, update: ProgramStatusUpdate]
}>()

function statusTagType(status: string): '' | 'success' | 'warning' | 'info' | 'danger' {
  switch (status) {
    case 'completed': return 'success'
    case 'in_progress': return 'warning'
    case 'not_started': return 'info'
    case 'not_applicable': return 'info'
    default: return ''
  }
}

function statusLabel(status: string): string {
  switch (status) {
    case 'completed': return '已完成'
    case 'in_progress': return '进行中'
    case 'not_started': return '未开始'
    case 'not_applicable': return '不适用'
    default: return status
  }
}

function handleCommand(programCode: string, command: string) {
  if (command === 'not_applicable') {
    emit('update-status', programCode, {
      applicable: false,
      status: 'not_applicable',
      not_applicable_reason: '用户标记不适用',
    })
  } else {
    emit('update-status', programCode, { status: command })
  }
}
</script>

<style scoped>
.gt-control-panel {
  margin: 16px 0;
  border: 1px solid var(--gt-color-border-purple, #e8e4f0);
  border-radius: 8px;
  padding: 16px;
}

.gt-control-panel__title {
  margin: 0 0 12px;
  font-size: 14px;
  font-weight: 600;
  color: var(--gt-color-primary, #4b2d77);
}

.gt-control-panel__list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.gt-control-panel__item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 12px;
  border-radius: 4px;
  background: var(--gt-color-primary-bg, #f4f0fa);
}

.gt-control-panel__item-main {
  display: flex;
  align-items: center;
  gap: 8px;
}

.gt-control-panel__code {
  font-weight: 500;
  font-size: 13px;
  min-width: 80px;
}

.gt-control-panel__empty {
  text-align: center;
  color: var(--gt-color-text-secondary, #6e6e73);
  padding: 12px;
  font-size: 13px;
}
</style>
