<!--
  ArchivedBanner — 项目归档只读横幅
  当项目处于 archived 状态时，在视图顶部显示紫色横幅提示。
  admin/partner 角色可见「解除归档」按钮，点击触发 confirmDangerous 二次确认。

  用法：
    <ArchivedBanner />
    <!-- 无需 props，内部读取 useAuditContext -->
-->
<template>
  <div v-if="isArchived" class="archived-banner">
    <span class="archived-banner__text">
      🔒 📁 项目已归档（只读）
    </span>
    <el-button
      v-if="canUnarchive"
      class="archived-banner__btn"
      size="small"
      @click="handleUnarchive"
    >
      解除归档
    </el-button>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useAuditContext } from '@/composables/useAuditContext'
import { useRoleContextStore } from '@/stores/roleContext'
import { useProjectStore } from '@/stores/project'
import { confirmDangerous } from '@/utils/confirm'

const { isArchived } = useAuditContext()
const roleContextStore = useRoleContextStore()
const projectStore = useProjectStore()

/** admin/partner 角色可见解除归档按钮 */
const canUnarchive = computed(() => roleContextStore.isPartner)

const emit = defineEmits<{
  (e: 'unarchive'): void
}>()

async function handleUnarchive() {
  try {
    await confirmDangerous(
      `确定要解除「${projectStore.clientName || '该项目'}」的归档状态吗？解除后项目将恢复为可编辑状态。`,
      '解除归档确认',
    )
    emit('unarchive')
  } catch {
    // 用户取消，不做处理
  }
}
</script>

<style scoped>
.archived-banner {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 16px;
  width: 100%;
  height: 40px;
  padding: 8px 16px;
  background: linear-gradient(135deg, #4b2d77, #6b3fa0);
  color: #fff;
  font-size: 14px;
  box-sizing: border-box;
}

.archived-banner__text {
  display: flex;
  align-items: center;
  gap: 4px;
}

.archived-banner__btn {
  --el-button-bg-color: transparent;
  --el-button-border-color: #fff;
  --el-button-text-color: #fff;
  --el-button-hover-bg-color: rgba(255, 255, 255, 0.1);
  --el-button-hover-border-color: #fff;
  --el-button-hover-text-color: #fff;
  border: 1px solid #fff;
  color: #fff;
  background: transparent;
}
</style>
