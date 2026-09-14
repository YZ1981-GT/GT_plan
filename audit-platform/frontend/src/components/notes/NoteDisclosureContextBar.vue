<template>
  <div class="disclosure-context-bar">
    <div class="disclosure-context-bar__item">
      <label class="disclosure-context-bar__label">单位</label>
      <el-select
        :model-value="currentEntity"
        placeholder="请选择单位"
        size="small"
        clearable
        @update:model-value="handleEntityChange"
      >
        <el-option
          v-for="entity in entities"
          :key="entity.id"
          :label="entity.name"
          :value="entity.id"
        >
          <span>{{ entity.name }}</span>
          <el-tag
            v-if="entity.type !== 'project'"
            size="small"
            class="disclosure-context-bar__entity-tag"
          >{{ entityTypeLabel(entity.type) }}</el-tag>
        </el-option>
      </el-select>
    </div>

    <div class="disclosure-context-bar__item">
      <label class="disclosure-context-bar__label">年度</label>
      <el-select
        :model-value="currentYear"
        placeholder="请选择年度"
        size="small"
        clearable
        @update:model-value="handleYearChange"
      >
        <el-option
          v-for="year in years"
          :key="year"
          :label="String(year)"
          :value="year"
        />
      </el-select>
    </div>

    <div class="disclosure-context-bar__item">
      <label class="disclosure-context-bar__label">科目/明细</label>
      <el-select
        :model-value="currentAccount"
        placeholder="请选择科目"
        size="small"
        clearable
        @update:model-value="handleAccountChange"
      >
        <el-option
          v-for="account in accounts"
          :key="account.code"
          :label="account.detail ? `${account.name} - ${account.detail}` : account.name"
          :value="account.code"
        />
      </el-select>
    </div>

    <div class="disclosure-context-bar__item">
      <label class="disclosure-context-bar__label">金额口径</label>
      <el-select
        :model-value="currentAmountRole"
        placeholder="请选择口径"
        size="small"
        clearable
        @update:model-value="handleAmountRoleChange"
      >
        <el-option
          v-for="role in amountRoles"
          :key="role"
          :label="amountRoleLabel(role)"
          :value="role"
        />
      </el-select>
    </div>
  </div>
</template>

<script setup lang="ts">
/**
 * NoteDisclosureContextBar — 数据披露四维上下文栏
 *
 * 在科目注释和关联方章节中按单位、年度、科目明细、金额口径快速切换。
 *
 * Validates: Requirements 2.1, 2.2, 2.3, 2.4
 */

export interface ContextEntity {
  id: string
  name: string
  type: 'project' | 'subsidiary' | 'related_party'
}

export interface ContextAccount {
  code: string
  name: string
  detail?: string
}

export interface ContextChangePayload {
  entity?: string
  year?: number
  account?: string
  amountRole?: string
}

interface Props {
  entities: ContextEntity[]
  years: number[]
  accounts: ContextAccount[]
  amountRoles: string[]
  currentEntity?: string
  currentYear?: number
  currentAccount?: string
  currentAmountRole?: string
}

const props = withDefaults(defineProps<Props>(), {
  currentEntity: undefined,
  currentYear: undefined,
  currentAccount: undefined,
  currentAmountRole: undefined,
})

const emit = defineEmits<{
  'context-change': [payload: ContextChangePayload]
}>()

function buildPayload(overrides: Partial<ContextChangePayload> = {}): ContextChangePayload {
  return {
    entity: props.currentEntity,
    year: props.currentYear,
    account: props.currentAccount,
    amountRole: props.currentAmountRole,
    ...overrides,
  }
}

function handleEntityChange(val: string | undefined) {
  emit('context-change', buildPayload({ entity: val }))
}

function handleYearChange(val: number | undefined) {
  emit('context-change', buildPayload({ year: val }))
}

function handleAccountChange(val: string | undefined) {
  emit('context-change', buildPayload({ account: val }))
}

function handleAmountRoleChange(val: string | undefined) {
  emit('context-change', buildPayload({ amountRole: val }))
}

function entityTypeLabel(type: string): string {
  const map: Record<string, string> = {
    project: '单体',
    subsidiary: '子公司',
    related_party: '关联方',
  }
  return map[type] || type
}

function amountRoleLabel(role: string): string {
  const map: Record<string, string> = {
    closing: '期末余额',
    opening: '期初余额',
    current: '本期发生',
    prior: '上期发生',
  }
  return map[role] || role
}
</script>

<style scoped>
.disclosure-context-bar {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 8px 16px;
  background: var(--gt-color-primary-bg, #f4f0fa);
  border-bottom: 1px solid var(--gt-color-border-purple-light, #d8b8ee);
  border-radius: 4px 4px 0 0;
}

.disclosure-context-bar__item {
  display: flex;
  align-items: center;
  gap: 6px;
}

.disclosure-context-bar__label {
  font-size: 13px;
  font-weight: 500;
  color: var(--gt-color-primary, #4b2d77);
  white-space: nowrap;
}

.disclosure-context-bar__entity-tag {
  margin-left: 6px;
}

:deep(.el-select) {
  width: 160px;
}
</style>
