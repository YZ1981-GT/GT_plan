<!--
  ProjectContextBar — 项目上下文信息条 [P1-1]
  [platform-context-permission-foundation P1-1]

  紧凑型信息条，展示当前项目核心上下文字段：
  - 项目名称
  - 审计年度（支持切换）
  - 适用准则
  - 审计范围（单体/合并）
  - 项目状态（badge）
  - 当前用户在项目中的职责

  集成到 GtPageShell 的 context slot 或高频页面头部。
  数据来源：useProjectStore().currentProjectContext

  用法：
    <ProjectContextBar />
    <ProjectContextBar :show-year-switcher="true" />
-->
<template>
  <div class="gt-context-bar" v-if="ctx.projectId">
    <!-- 项目名称 -->
    <div class="gt-context-bar__item">
      <span class="gt-context-bar__label">项目</span>
      <span class="gt-context-bar__value gt-context-bar__value--name">
        {{ ctx.projectName || '—' }}
      </span>
    </div>

    <!-- 审计年度（可切换） -->
    <div class="gt-context-bar__item">
      <span class="gt-context-bar__label">年度</span>
      <el-select
        v-if="showYearSwitcher"
        v-model="selectedYear"
        class="gt-context-bar__year-select"
        size="small"
        @change="onYearChange"
      >
        <el-option
          v-for="y in yearOptions"
          :key="y"
          :label="`${y}`"
          :value="y"
        />
      </el-select>
      <span v-else class="gt-context-bar__value">{{ ctx.year }}</span>
    </div>

    <!-- 适用准则 -->
    <div class="gt-context-bar__item">
      <span class="gt-context-bar__label">准则</span>
      <span class="gt-context-bar__value">{{ standardLabel }}</span>
    </div>

    <!-- 审计范围 -->
    <div class="gt-context-bar__item">
      <span class="gt-context-bar__label">范围</span>
      <span class="gt-context-bar__value">{{ scopeLabel }}</span>
    </div>

    <!-- 项目状态 -->
    <div class="gt-context-bar__item">
      <span class="gt-context-bar__label">状态</span>
      <el-tag
        :type="statusType"
        size="small"
        class="gt-context-bar__tag"
        effect="light"
      >
        {{ statusLabel }}
      </el-tag>
    </div>

    <!-- 当前职责 -->
    <div class="gt-context-bar__item" v-if="ctx.roleInProject">
      <span class="gt-context-bar__label">职责</span>
      <el-tag size="small" effect="plain" class="gt-context-bar__tag gt-context-bar__tag--role">
        {{ roleLabel }}
      </el-tag>
    </div>

    <!-- 只读/归档提示 -->
    <div class="gt-context-bar__readonly" v-if="isReadonly">
      <el-icon><Lock /></el-icon>
      <span>{{ readonlyHint }}</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { Lock } from '@element-plus/icons-vue'
import { useProjectStore } from '@/stores/project'
import { useDictStore } from '@/stores/dict'

defineOptions({ name: 'ProjectContextBar' })

const props = withDefaults(
  defineProps<{
    /** 是否显示年度切换下拉 */
    showYearSwitcher?: boolean
  }>(),
  { showYearSwitcher: true },
)

const emit = defineEmits<{
  (e: 'year-change', year: number): void
}>()

const projectStore = useProjectStore()
const dictStore = useDictStore()

const ctx = computed(() => projectStore.currentProjectContext)
const yearOptions = computed(() => projectStore.yearOptions)

const selectedYear = ref(ctx.value.year)
watch(() => ctx.value.year, (v) => { selectedYear.value = v })

function onYearChange(year: number) {
  projectStore.setCurrentYear(year, { reload: true })
  emit('year-change', year)
}

// ─── 准则映射 ───
const standardLabel = computed(() => {
  const map: Record<string, string> = {
    soe: '国企准则',
    listed: '上市公司准则',
    private: '民营准则',
  }
  return map[ctx.value.applicableStandard] || ctx.value.applicableStandard || '—'
})

// ─── 审计范围映射 ───
const scopeLabel = computed(() => {
  return ctx.value.auditScope === 'consolidated' ? '合并' : '单体'
})

// ─── 项目状态映射（优先使用 dictStore，fallback 本地映射） ───
const statusLabel = computed(() => {
  const v = ctx.value.projectStatus
  const fromDict = dictStore.label('project_status', v)
  if (fromDict && fromDict !== v) return fromDict
  const map: Record<string, string> = {
    draft: '草稿', created: '已创建', planning: '计划中',
    active: '执行中', execution: '执行中', signed: '已签发',
    archived: '已归档', completion: '已完成', reporting: '报告',
  }
  return map[v] || v || '—'
})

const statusType = computed(() => {
  const v = ctx.value.projectStatus
  const fromDict = dictStore.type('project_status', v)
  if (fromDict && fromDict !== 'info') return fromDict
  const map: Record<string, string> = {
    draft: 'info', created: 'info', planning: 'warning',
    active: '', execution: '', signed: 'success',
    archived: 'info', completion: 'success', reporting: '',
  }
  return (map[v] || 'info') as any
})

// ─── 项目角色映射 ───
const roleLabel = computed(() => {
  const map: Record<string, string> = {
    preparer: '编制人',
    reviewer: '复核人',
    manager: '项目经理',
    partner: '签字合伙人',
    eqcr: '独立复核',
    admin: '管理员',
    auditor: '审计助理',
  }
  return map[ctx.value.roleInProject || ''] || ctx.value.roleInProject || '—'
})

// ─── 只读状态 ───
const isReadonly = computed(() => {
  return ['signed', 'archived'].includes(ctx.value.projectStatus)
})

const readonlyHint = computed(() => {
  if (ctx.value.projectStatus === 'archived') return '已归档，数据只读'
  if (ctx.value.projectStatus === 'signed') return '已签发，数据只读'
  return ''
})
</script>

<style scoped>
.gt-context-bar {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 8px 16px;
  font-size: var(--gt-font-size-sm, 13px);
  flex-wrap: wrap;
  min-height: 36px;
}

.gt-context-bar__item {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  white-space: nowrap;
}

.gt-context-bar__label {
  color: var(--gt-color-text-secondary, #606266);
  font-size: 12px;
}

.gt-context-bar__value {
  color: var(--gt-color-text-primary, #303133);
  font-weight: 500;
}

.gt-context-bar__value--name {
  max-width: 180px;
  overflow: hidden;
  text-overflow: ellipsis;
}

.gt-context-bar__year-select {
  width: 80px;
}

.gt-context-bar__year-select :deep(.el-input__inner) {
  height: 24px;
  font-size: 12px;
}

.gt-context-bar__tag {
  border-color: var(--gt-color-border-purple-light, #d8b8ee);
}

.gt-context-bar__tag--role {
  color: var(--gt-color-primary, #4b2d77);
  border-color: var(--gt-color-border-purple-light, #d8b8ee);
  background: var(--gt-color-primary-bg, #f4f0fa);
}

.gt-context-bar__readonly {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  margin-left: auto;
  color: var(--el-color-warning, #e6a23c);
  font-size: 12px;
  font-weight: 500;
}
</style>
