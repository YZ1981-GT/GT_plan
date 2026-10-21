<!--
  冲突三方对比 + 逐条 / 批量决策（spec formula-global-settings-sync，design §11，R3.2 / R4.1 / R7.3 / R13.3）。
  管理员发布、模板发布、订阅 / 退订、应用到指定项目共用：只列分类为「冲突」的条目，
  每条给出 原定义（本项目基线）/ 新定义 / 本项目当前，处理方式由调用方给出（文案随场景不同）。
  决策以 `{条目 key → 处理}` 回传，与后端 Decisions.conflict_choices 同口径。
-->
<template>
  <div class="gt-fct" data-testid="formula-conflict-table">
    <div class="gt-fct-bar">
      <span class="gt-fct-count">冲突 <b>{{ conflicts.length }}</b> 处</span>
      <template v-if="conflicts.length && !readonly">
        <span class="gt-fct-hint">批量：</span>
        <el-button v-for="c in choices" :key="c.value" size="small" :data-testid="`fct-all-${c.value}`" @click="setAll(c.value)">
          全部{{ c.label }}
        </el-button>
      </template>
    </div>
    <el-table :data="conflicts" size="small" border max-height="360" row-key="key" empty-text="没有冲突">
      <el-table-column v-if="showProject" prop="project_name" label="项目" min-width="130" show-overflow-tooltip />
      <el-table-column prop="label" label="公式位" min-width="150" show-overflow-tooltip />
      <el-table-column :label="baseLabel" min-width="150">
        <template #default="{ row }"><code class="gt-fct-code">{{ row.base_formula || '（空）' }}</code></template>
      </el-table-column>
      <el-table-column :label="newLabel" min-width="150">
        <template #default="{ row }"><code class="gt-fct-code gt-fct-new">{{ row.new_formula || '（空）' }}</code></template>
      </el-table-column>
      <el-table-column :label="localLabel" min-width="150">
        <template #default="{ row }"><code class="gt-fct-code gt-fct-local">{{ row.local_formula || '（空）' }}</code></template>
      </el-table-column>
      <el-table-column label="处理" :width="choiceWidth">
        <template #default="{ row }">
          <el-radio-group :model-value="choiceOf(row.key)" size="small" :disabled="readonly"
            @update:model-value="(v: string | number | boolean | undefined) => setOne(row.key, v as ConflictChoice)">
            <el-radio-button v-for="c in choices" :key="c.value" :value="c.value">{{ c.label }}</el-radio-button>
          </el-radio-group>
        </template>
      </el-table-column>
    </el-table>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { isConflict, type ConflictChoice, type PlanItem } from '@/composables/formula/useFormulaSettings'

defineOptions({ name: 'FormulaConflictTable' })

const props = withDefaults(defineProps<{
  items: PlanItem[]
  /** 冲突决策 `{条目 key → 处理}`；未出现的条目按 defaultChoice 处理 */
  modelValue: Record<string, ConflictChoice>
  choices: ReadonlyArray<{ value: ConflictChoice; label: string }>
  defaultChoice?: ConflictChoice
  showProject?: boolean
  readonly?: boolean
  baseLabel?: string
  newLabel?: string
  localLabel?: string
}>(), {
  defaultChoice: 'ask',
  showProject: true,
  readonly: false,
  baseLabel: '原定义（基线）',
  newLabel: '新定义',
  localLabel: '本项目当前',
})

const emit = defineEmits<{ 'update:modelValue': [value: Record<string, ConflictChoice>] }>()

const conflicts = computed(() => props.items.filter(isConflict))
/** 按选项文字长度估宽（每字约 14px + 按钮内边距），定宽 92/项时「保留项目」会被挤到第二行裁掉（浏览器实测） */
const choiceWidth = computed(() => Math.max(150, 32 + props.choices.reduce((w, c) => w + c.label.length * 14 + 28, 0)))

function choiceOf(key: string): ConflictChoice {
  return props.modelValue[key] ?? props.defaultChoice
}

function setOne(key: string, value: ConflictChoice) {
  emit('update:modelValue', { ...props.modelValue, [key]: value })
}

function setAll(value: ConflictChoice) {
  const next: Record<string, ConflictChoice> = { ...props.modelValue }
  for (const it of conflicts.value) next[it.key] = value
  emit('update:modelValue', next)
}
</script>

<style scoped>
.gt-fct-bar { display: flex; align-items: center; gap: 6px; margin-bottom: 6px; flex-wrap: wrap; }
.gt-fct-count { font-size: var(--gt-font-size-sm); color: var(--gt-color-text-secondary); margin-right: 8px; }
.gt-fct-hint { font-size: var(--gt-font-size-xs); color: var(--gt-color-text-tertiary); }
.gt-fct-code { font-size: var(--gt-font-size-xs); word-break: break-all; white-space: normal; }
.gt-fct-new { color: var(--gt-color-primary); }
.gt-fct-local { color: var(--gt-color-warning); }
</style>
