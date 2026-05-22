<template>
  <div class="gt-review-chain-config">
    <h4 class="gt-rcc-title">复核链配置</h4>
    <p class="gt-rcc-desc">配置项目复核流程的层级数和各层级角色分配</p>

    <!-- 禁用提示 -->
    <el-alert
      v-if="disabled"
      type="warning"
      :closable="false"
      show-icon
      class="gt-rcc-alert"
    >
      <template #title>
        当前有进行中的复核，无法修改配置
      </template>
    </el-alert>

    <!-- 层级数选择 -->
    <div class="gt-rcc-field">
      <label class="gt-rcc-label">复核层级数</label>
      <el-tooltip
        :disabled="!disabled"
        content="存在进行中复核时无法修改"
        placement="top"
      >
        <el-select
          v-model="localLevels"
          :disabled="disabled || saving"
          style="width: 200px"
          placeholder="选择层级数"
        >
          <el-option :value="2" label="2 级复核" />
          <el-option :value="3" label="3 级复核" />
          <el-option :value="4" label="4 级复核" />
        </el-select>
      </el-tooltip>
    </div>

    <!-- 各层级角色分配 -->
    <div class="gt-rcc-roles">
      <div
        v-for="level in localLevels"
        :key="level"
        class="gt-rcc-role-row"
      >
        <label class="gt-rcc-role-label">L{{ level }} 复核人</label>
        <el-select
          v-model="localRoles[`L${level}`]"
          :disabled="disabled || saving"
          style="width: 240px"
          placeholder="选择角色"
          filterable
        >
          <el-option
            v-for="member in projectMembers"
            :key="member.value"
            :value="member.value"
            :label="member.label"
          />
        </el-select>
      </div>
    </div>

    <!-- 保存按钮 -->
    <div class="gt-rcc-actions">
      <el-button
        type="primary"
        :disabled="disabled || !isValid"
        :loading="saving"
        @click="handleSave"
      >
        保存配置
      </el-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import http from '@/utils/http'

export interface ReviewConfig {
  levels: 2 | 3 | 4
  level_roles: Record<string, string>
}

interface Props {
  projectId: string
  currentConfig: ReviewConfig | null
  disabled?: boolean
}

interface Emits {
  (e: 'saved', config: ReviewConfig): void
}

const props = withDefaults(defineProps<Props>(), {
  disabled: false,
})

const emit = defineEmits<Emits>()

// Local state
const localLevels = ref<number>(props.currentConfig?.levels ?? 2)
const localRoles = ref<Record<string, string>>(
  props.currentConfig?.level_roles
    ? { ...props.currentConfig.level_roles }
    : { L1: 'manager', L2: 'partner' }
)
const saving = ref(false)

// Project members for role selection
interface MemberOption {
  value: string
  label: string
}

const projectMembers = ref<MemberOption[]>([
  { value: 'manager', label: '项目经理' },
  { value: 'partner', label: '签字合伙人' },
  { value: 'auditor', label: '审计助理' },
  { value: 'eqcr', label: 'EQCR 独立复核' },
  { value: 'qc', label: '质控人员' },
])

// Validation
const isValid = computed(() => {
  for (let i = 1; i <= localLevels.value; i++) {
    if (!localRoles.value[`L${i}`]) return false
  }
  return true
})

// Watch config changes from parent
watch(
  () => props.currentConfig,
  (newConfig) => {
    if (newConfig) {
      localLevels.value = newConfig.levels
      localRoles.value = { ...newConfig.level_roles }
    }
  },
  { deep: true }
)

// When levels change, ensure roles dict has all required keys
watch(localLevels, (newLevels) => {
  for (let i = 1; i <= newLevels; i++) {
    if (!localRoles.value[`L${i}`]) {
      // Set defaults for new levels
      if (i === 1) localRoles.value[`L${i}`] = 'manager'
      else if (i === 2) localRoles.value[`L${i}`] = 'partner'
      else if (i === 3) localRoles.value[`L${i}`] = 'eqcr'
      else if (i === 4) localRoles.value[`L${i}`] = 'qc'
    }
  }
})

// Save handler
async function handleSave() {
  if (!isValid.value) {
    ElMessage.warning('请为每个层级分配角色')
    return
  }

  saving.value = true
  try {
    // Build level_roles with only the required levels
    const levelRoles: Record<string, string> = {}
    for (let i = 1; i <= localLevels.value; i++) {
      levelRoles[`L${i}`] = localRoles.value[`L${i}`]
    }

    const payload = {
      levels: localLevels.value,
      level_roles: levelRoles,
    }

    await http.put(`/api/projects/${props.projectId}/review-config`, payload)

    const savedConfig: ReviewConfig = {
      levels: localLevels.value as 2 | 3 | 4,
      level_roles: levelRoles,
    }

    emit('saved', savedConfig)
    ElMessage.success('复核链配置已保存')
  } catch (err: any) {
    const status = err?.response?.status
    if (status === 409) {
      ElMessage.error('存在进行中的复核，无法修改配置')
    } else if (status === 422) {
      ElMessage.error(err?.response?.data?.detail || '配置验证失败')
    } else {
      ElMessage.error(err?.response?.data?.detail || '保存失败')
    }
  } finally {
    saving.value = false
  }
}
</script>

<style scoped>
.gt-review-chain-config {
  padding: 16px;
}
.gt-rcc-title {
  font-size: var(--gt-font-size-base, 14px);
  font-weight: 600;
  margin: 0 0 4px;
}
.gt-rcc-desc {
  font-size: var(--gt-font-size-xs, 12px);
  color: var(--gt-color-text-secondary, #909399);
  margin: 0 0 16px;
}
.gt-rcc-alert {
  margin-bottom: 16px;
}
.gt-rcc-field {
  margin-bottom: 16px;
}
.gt-rcc-label {
  display: block;
  font-size: var(--gt-font-size-sm, 13px);
  font-weight: 500;
  margin-bottom: 6px;
  color: var(--gt-color-text, #303133);
}
.gt-rcc-roles {
  display: flex;
  flex-direction: column;
  gap: 12px;
  margin-bottom: 20px;
}
.gt-rcc-role-row {
  display: flex;
  align-items: center;
  gap: 12px;
}
.gt-rcc-role-label {
  font-size: var(--gt-font-size-sm, 13px);
  color: var(--gt-color-text, #303133);
  min-width: 80px;
}
.gt-rcc-actions {
  padding-top: 8px;
  border-top: 1px solid var(--gt-color-border-light, #ebeef5);
}
</style>
