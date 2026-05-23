<template>
  <div v-if="users.length > 0" class="presence-avatars">
    <el-tooltip
      v-for="user in visibleUsers"
      :key="user.user_id"
      :content="`${user.user_name}（${user.mode === 'edit' ? '编辑中' : '查看中'}）`"
      placement="bottom"
    >
      <div
        class="presence-avatar"
        :class="{ 'is-editing': user.mode === 'edit', 'is-viewing': user.mode === 'view' }"
      >
        <span class="presence-avatar-text">{{ user.user_name?.charAt(0) ?? '?' }}</span>
      </div>
    </el-tooltip>
    <div v-if="overflowCount > 0" class="presence-overflow">
      +{{ overflowCount }}
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

export interface PresenceUser {
  user_id: string
  user_name: string
  avatar?: string | null
  mode: 'edit' | 'view'
  last_seen?: number
}

const props = withDefaults(defineProps<{
  users: PresenceUser[]
  maxVisible?: number
}>(), {
  maxVisible: 5,
})

const visibleUsers = computed(() => props.users.slice(0, props.maxVisible))
const overflowCount = computed(() => Math.max(0, props.users.length - props.maxVisible))
</script>

<style scoped>
.presence-avatars {
  display: flex;
  align-items: center;
  gap: 4px;
}

.presence-avatar {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  font-weight: 600;
  color: #fff;
  background: var(--gt-color-info, #909399);
  border: 2px solid #e0e0e0;
  transition: border-color 0.2s;
}

.presence-avatar.is-editing {
  background: var(--gt-color-primary, #4b2d77);
  border-color: #67C23A;
}

.presence-avatar.is-viewing {
  background: var(--gt-color-info, #909399);
  border-color: #dcdfe6;
}

.presence-avatar-text {
  user-select: none;
}

.presence-overflow {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 11px;
  font-weight: 600;
  color: var(--gt-color-text-secondary, #909399);
  background: #f0f0f0;
  border: 2px solid #e0e0e0;
}
</style>
