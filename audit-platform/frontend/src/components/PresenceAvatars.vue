<script setup lang="ts">
/**
 * PresenceAvatars — 在线成员头像列表 [enterprise-linkage 3.2]
 *
 * 显示当前视图在线成员头像，hover 显示姓名。
 */
import { computed, toRef } from 'vue'
import { usePresence, type OnlineMember } from '@/composables/usePresence'

const props = defineProps<{
  projectId: string
  viewName: string
}>()

const projectIdRef = toRef(props, 'projectId')
const { onlineMembers } = usePresence(projectIdRef, props.viewName)

/** 只显示当前视图的成员（排除自己可选，这里全部显示） */
const viewMembers = computed<OnlineMember[]>(() =>
  onlineMembers.value.filter(m => m.view === props.viewName)
)

function getInitials(name: string): string {
  return name ? name.slice(0, 1) : '?'
}

function getColor(userId: string): string {
  const colors = ['#409eff', '#67c23a', '#e6a23c', '#f56c6c', '#909399', '#8b5cf6']
  let hash = 0
  for (let i = 0; i < userId.length; i++) hash = (hash * 31 + userId.charCodeAt(i)) | 0
  return colors[Math.abs(hash) % colors.length]
}
</script>

<template>
  <div v-if="viewMembers.length > 0" class="presence-avatars">
    <el-tooltip
      v-for="member in viewMembers"
      :key="member.user_id"
      :content="member.user_name"
      placement="bottom"
    >
      <el-avatar
        :size="28"
        :src="member.avatar"
        :style="{ backgroundColor: getColor(member.user_id) }"
      >
        {{ getInitials(member.user_name) }}
      </el-avatar>
    </el-tooltip>
    <span class="presence-count">{{ viewMembers.length }} 人在线</span>
  </div>
</template>

<style scoped>
.presence-avatars {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  margin-left: 12px;
}
.presence-avatars .el-avatar {
  cursor: default;
  font-size: var(--gt-font-size-xs);
  border: 2px solid var(--gt-color-text-inverse);
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
}
.presence-avatars .el-avatar + .el-avatar {
  margin-left: -8px;
}
.presence-count {
  font-size: var(--gt-font-size-xs);
  color: var(--gt-color-info);
  margin-left: 6px;
}
</style>
