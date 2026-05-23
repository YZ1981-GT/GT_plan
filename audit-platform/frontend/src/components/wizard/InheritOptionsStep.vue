<template>
  <div class="gt-inherit-options-step">
    <h2 class="gt-step-title">继承配置</h2>
    <p class="gt-step-desc">勾选要从上年项目继承的配置项。默认值已按"基础配置易复用、人员/复核需重新配置"原则保守设置。</p>

    <el-alert
      v-if="!props.prevProjectId"
      type="warning"
      title="未选择上年项目"
      description="请先在基本信息步骤选择「基于上年项目创建」并指定要继承的项目"
      :closable="false"
      show-icon
      style="margin-bottom: 16px"
    />

    <el-form label-width="0" class="gt-inherit-form">
      <div class="gt-inherit-actions">
        <el-button size="small" @click="selectAll">全选</el-button>
        <el-button size="small" @click="clearAll">全清</el-button>
        <el-button size="small" type="primary" plain @click="resetDefault">恢复默认</el-button>
      </div>

      <div class="gt-inherit-grid">
        <div
          v-for="opt in INHERIT_OPTIONS"
          :key="opt.key"
          class="gt-inherit-card"
          :class="{ 'is-checked': options[opt.key] }"
        >
          <el-checkbox
            v-model="options[opt.key]"
            :data-test="`inherit-${opt.key}`"
            class="gt-inherit-checkbox"
          >
            <div class="gt-inherit-card-body">
              <div class="gt-inherit-card-title">
                <span class="gt-inherit-card-icon">{{ opt.icon }}</span>
                <span>{{ opt.label }}</span>
                <el-tag v-if="opt.defaultOn" size="small" type="success" effect="plain" style="margin-left: 6px">默认开启</el-tag>
                <el-tag v-else size="small" type="info" effect="plain" style="margin-left: 6px">默认关闭</el-tag>
              </div>
              <div class="gt-inherit-card-desc">{{ opt.desc }}</div>
            </div>
          </el-checkbox>
        </div>
      </div>

      <el-alert
        type="info"
        :closable="false"
        show-icon
        style="margin-top: 16px"
      >
        <template #title>
          <strong>已选 {{ checkedCount }} / 7 项</strong>
        </template>
        <div style="font-size: 12px; line-height: 1.6">
          人员分工 / 复核链 / 重要性默认不继承，避免新项目误用上年数据。如需复用，请勾选后再确认。
        </div>
      </el-alert>
    </el-form>
  </div>
</template>

<script setup lang="ts">
import { reactive, computed, watch } from 'vue'

export type InheritOptionKey =
  | 'inherit_chart'
  | 'inherit_mapping'
  | 'inherit_wp_template'
  | 'inherit_assignments'
  | 'inherit_review_chain'
  | 'inherit_vr_rules'
  | 'inherit_materiality'

export interface InheritOptions {
  inherit_chart: boolean
  inherit_mapping: boolean
  inherit_wp_template: boolean
  inherit_assignments: boolean
  inherit_review_chain: boolean
  inherit_vr_rules: boolean
  inherit_materiality: boolean
}

interface OptionMeta {
  key: InheritOptionKey
  label: string
  icon: string
  desc: string
  defaultOn: boolean
}

const INHERIT_OPTIONS: OptionMeta[] = [
  { key: 'inherit_chart', label: '科目表', icon: '📋', desc: '复制 AccountChart（标准 + 客户科目）', defaultOn: true },
  { key: 'inherit_mapping', label: '报表行次映射', icon: '🔗', desc: '复制科目映射 + 已确认的报表行次映射', defaultOn: true },
  { key: 'inherit_wp_template', label: '底稿模板配置', icon: '📑', desc: '继承程序实例 / 裁剪方案 / 附注模板配置', defaultOn: true },
  { key: 'inherit_assignments', label: '人员分工', icon: '👥', desc: '复制项目团队 + 委派（ProjectUser + ProjectAssignment）', defaultOn: false },
  { key: 'inherit_review_chain', label: '复核链配置', icon: '✅', desc: '复制 review_config（2-4 级复核链 + 角色映射）', defaultOn: false },
  { key: 'inherit_vr_rules', label: 'VR 规则', icon: '🛡', desc: '继承 scenario（normal/ipo/listed/transfer/...） + 外币标记', defaultOn: true },
  { key: 'inherit_materiality', label: '重要性水平', icon: '⚖', desc: '复制最近年度 Materiality（建议本年重新评估）', defaultOn: false },
]

const props = defineProps<{
  prevProjectId?: string | null
  modelValue?: Partial<InheritOptions>
}>()

const emit = defineEmits<{
  'update:modelValue': [val: InheritOptions]
}>()

function buildDefaults(): InheritOptions {
  const defaults = {} as InheritOptions
  for (const opt of INHERIT_OPTIONS) {
    defaults[opt.key] = opt.defaultOn
  }
  return defaults
}

const options = reactive<InheritOptions>({
  ...buildDefaults(),
  ...(props.modelValue || {}),
})

const checkedCount = computed(() => INHERIT_OPTIONS.filter(o => options[o.key]).length)

watch(options, (val) => {
  emit('update:modelValue', { ...val })
}, { deep: true })

function selectAll() {
  for (const opt of INHERIT_OPTIONS) {
    options[opt.key] = true
  }
}

function clearAll() {
  for (const opt of INHERIT_OPTIONS) {
    options[opt.key] = false
  }
}

function resetDefault() {
  for (const opt of INHERIT_OPTIONS) {
    options[opt.key] = opt.defaultOn
  }
}

function getOptions(): InheritOptions {
  return { ...options }
}

defineExpose({ getOptions, selectAll, clearAll, resetDefault })
</script>

<style scoped>
.gt-inherit-options-step {
  max-width: 960px;
  margin: 0 auto;
  padding: 0 16px;
}

.gt-step-title {
  color: var(--gt-color-primary);
  margin-bottom: 4px;
  font-size: var(--gt-font-size-xl);
  font-weight: 700;
}

.gt-step-desc {
  color: var(--gt-color-text-tertiary);
  margin-bottom: 20px;
  font-size: var(--gt-font-size-sm);
}

.gt-inherit-actions {
  display: flex;
  gap: 8px;
  margin-bottom: 14px;
}

.gt-inherit-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}

.gt-inherit-card {
  border: 1px solid var(--gt-color-border-light, #e6e8eb);
  border-radius: 8px;
  padding: 12px 14px;
  background: var(--gt-color-bg-white);
  transition: border-color 0.2s, background 0.2s;
}

.gt-inherit-card.is-checked {
  border-color: var(--gt-color-primary, #6f4cb1);
  background: var(--gt-color-primary-bg, #f6f1fb);
}

.gt-inherit-checkbox {
  width: 100%;
  align-items: flex-start;
}

.gt-inherit-checkbox :deep(.el-checkbox__label) {
  width: 100%;
}

.gt-inherit-card-body {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.gt-inherit-card-title {
  display: flex;
  align-items: center;
  gap: 6px;
  font-weight: 600;
  font-size: 14px;
}

.gt-inherit-card-icon {
  font-size: 16px;
}

.gt-inherit-card-desc {
  color: var(--gt-color-text-tertiary, #6b6f76);
  font-size: 12px;
  line-height: 1.5;
}

@media (max-width: 768px) {
  .gt-inherit-grid {
    grid-template-columns: 1fr;
  }
}
</style>
