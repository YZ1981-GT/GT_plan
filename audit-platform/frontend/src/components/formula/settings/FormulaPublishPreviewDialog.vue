<!--
  发布前影响预览 + 决策（spec formula-global-settings-sync，design §11，R3 / R4.1 / R7.3 / R13.4）。
  全局发布、全局候选审核、模板发布新版本、设为全局、应用到指定项目共用：
  - 变更清单（原 → 新、版本号；版本不一致时禁止提交）；
  - 分类计数 + 受影响项目；逐项目「本次应用 / 暂缓」（冻结项目不可应用，可批量）；
  - 冲突三方对比 + 逐条 / 批量处理（默认交项目确认）；决策键只用服务端条目 key（含域，需求 8.4）；
  - 提交由调用方的 `submit` 执行（返回 true 才关窗），本组件不直接发请求。
-->
<template>
  <el-dialog v-model="visible" :title="title" width="min(1240px, 96vw)" append-to-body destroy-on-close
    data-testid="formula-publish-preview">
    <div v-loading="loading" class="gt-fpp">
      <template v-if="preview">
        <el-alert v-if="hint" type="info" :closable="false" show-icon class="gt-fpp-gap" :title="hint" />
        <el-alert v-if="versionProblems.length" type="error" :closable="false" show-icon class="gt-fpp-gap"
          :title="`${versionProblems.length} 个公式位已被他人修改或缺少版本号，请关闭后刷新再编辑`" />

        <section v-if="changes.length" class="gt-fpp-gap">
          <div class="gt-fpp-h">变更内容（{{ changes.length }}）</div>
          <el-table :data="changes" size="small" border max-height="200">
            <el-table-column prop="label" label="公式位" min-width="180" show-overflow-tooltip />
            <el-table-column label="原定义" min-width="170">
              <template #default="{ row }"><code class="gt-fpp-code">{{ row.old ? definitionText(row.old) : '（无）' }}</code></template>
            </el-table-column>
            <el-table-column label="新定义" min-width="170">
              <template #default="{ row }">
                <el-tag v-if="row.deleted" size="small" type="danger">删除</el-tag>
                <code v-else class="gt-fpp-code gt-fpp-new">{{ definitionText(row.new) }}</code>
              </template>
            </el-table-column>
            <!-- 模板发布 / 设为全局的变更行没有逐公式位版本（模板版本在标题里）：整列都是「— → —」时不显示 -->
            <el-table-column v-if="hasSlotVersions" label="版本" width="90" align="center">
              <template #default="{ row }">{{ row.old_version ?? '—' }} → {{ row.new_version ?? '—' }}</template>
            </el-table-column>
          </el-table>
        </section>

        <section class="gt-fpp-gap">
          <div class="gt-fpp-h">影响范围</div>
          <div class="gt-fpp-counts">
            <el-tag v-for="c in countTags" :key="c.key" size="small" :type="c.key === 'conflict' ? 'danger' : 'info'" effect="plain">
              {{ c.label }} {{ c.value }}
            </el-tag>
            <span class="gt-fpp-muted">受影响项目 {{ affectedCount }} 个</span>
          </div>
        </section>

        <section v-if="allowDefer && !readonlyDecisions && projects.length" class="gt-fpp-gap">
          <div class="gt-fpp-h">
            逐项目处理
            <el-button size="small" link type="primary" @click="setAllProjects('apply')">全部应用</el-button>
            <el-button size="small" link @click="setAllProjects('defer')">全部暂缓</el-button>
          </div>
          <el-table :data="projects" size="small" border max-height="220" row-key="project_id">
            <el-table-column prop="name" label="项目" min-width="200" show-overflow-tooltip />
            <el-table-column label="冲突" width="70" align="center">
              <template #default="{ row }">{{ row.counts.conflict || 0 }}</template>
            </el-table-column>
            <el-table-column label="自动跟随" width="80" align="center">
              <template #default="{ row }">{{ row.counts.follow || 0 }}</template>
            </el-table-column>
            <el-table-column label="直接生效" width="80" align="center">
              <template #default="{ row }">{{ row.counts.inherit || 0 }}</template>
            </el-table-column>
            <el-table-column label="本次处理" width="190">
              <template #default="{ row }">
                <el-tag v-if="row.frozen" size="small" type="info">已归档，保持旧定义</el-tag>
                <el-radio-group v-else :model-value="projectChoice(row.project_id)" size="small"
                  @update:model-value="(v: string | number | boolean | undefined) => setProject(row.project_id, v as ProjectChoice)">
                  <el-radio-button value="apply">本次应用</el-radio-button>
                  <el-radio-button value="defer">暂缓</el-radio-button>
                </el-radio-group>
              </template>
            </el-table-column>
          </el-table>
          <div class="gt-fpp-muted gt-fpp-tip">暂缓：项目先固定在旧定义，并收到待确认提醒，由项目自行决定何时采用。</div>
        </section>

        <section class="gt-fpp-gap">
          <FormulaConflictTable v-model="conflictChoices" :items="preview.items || []" :choices="conflictOptions"
            :default-choice="defaultConflict" :show-project="showProject" :base-label="baseLabel" :new-label="newLabel"
            :local-label="localLabel" :readonly="readonlyDecisions" />
        </section>

        <el-input v-if="showNote" v-model="note" type="textarea" :rows="2" maxlength="2000" show-word-limit
          placeholder="变更说明（选填，记入发布记录与审计）" />
      </template>
      <el-empty v-else-if="!loading" description="暂无预览" />
    </div>
    <template #footer>
      <el-button @click="visible = false">取消</el-button>
      <el-button type="primary" :loading="submitting" :disabled="!preview || versionProblems.length > 0"
        data-testid="formula-publish-submit" @click="onSubmit">{{ submitText }}</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import FormulaConflictTable from './FormulaConflictTable.vue'
import {
  CATEGORY_LABELS, CATEGORY_ORDER, definitionText,
  type ConflictChoice, type Decisions, type ProjectChoice, type SyncPreview,
} from '@/composables/formula/useFormulaSettings'

defineOptions({ name: 'FormulaPublishPreviewDialog' })

const props = withDefaults(defineProps<{
  modelValue: boolean
  preview: SyncPreview | null
  loading?: boolean
  title?: string
  /** 顶部说明（如退订保留的条数） */
  hint?: string
  submitText?: string
  /** 执行提交；返回 true 表示成功并关窗 */
  submit: (payload: { decisions: Decisions; note: string }) => Promise<boolean>
  /** 冲突处理选项（文案随场景：采用新全局 / 采用模板 / 采用来源项目 …） */
  conflictOptions?: ReadonlyArray<{ value: ConflictChoice; label: string }>
  defaultConflict?: ConflictChoice
  allowDefer?: boolean
  /** 只看影响不做决策（如提交全局候选：由管理员审核时再决定） */
  readonlyDecisions?: boolean
  showNote?: boolean
  showProject?: boolean
  baseLabel?: string
  newLabel?: string
  localLabel?: string
}>(), {
  loading: false,
  title: '发布前影响预览',
  hint: '',
  submitText: '确认发布',
  conflictOptions: () => [
    { value: 'adopt', label: '采用新定义' },
    { value: 'keep', label: '保留项目' },
    { value: 'ask', label: '交项目确认' },
  ],
  defaultConflict: 'ask',
  allowDefer: true,
  readonlyDecisions: false,
  showNote: true,
  showProject: true,
  baseLabel: '原定义（基线）',
  newLabel: '新定义',
  localLabel: '项目当前',
})

const emit = defineEmits<{ 'update:modelValue': [value: boolean] }>()

const visible = computed({
  get: () => props.modelValue,
  set: (v: boolean) => emit('update:modelValue', v),
})

const conflictChoices = ref<Record<string, ConflictChoice>>({})
const projectChoices = ref<Record<string, ProjectChoice>>({})
const note = ref('')
const submitting = ref(false)

// 每次换一份预览都从默认开始（避免上一次的勾选串到这一次）
watch(() => props.preview, () => {
  conflictChoices.value = {}
  projectChoices.value = {}
  note.value = ''
})

const changes = computed(() => props.preview?.changes || [])
const hasSlotVersions = computed(() => changes.value.some((r: any) => r.old_version != null || r.new_version != null))
const versionProblems = computed(() => props.preview?.version_problems || [])
const projects = computed(() => props.preview?.summary?.projects || [])
const counts = computed<Record<string, number>>(() => props.preview?.summary?.counts || props.preview?.counts || {})
const countTags = computed(() => CATEGORY_ORDER
  .filter((k) => (counts.value[k] || 0) > 0)
  .map((k) => ({ key: k, label: CATEGORY_LABELS[k], value: counts.value[k] })))
const affectedCount = computed(() => props.preview?.summary?.affected_project_count
  ?? new Set((props.preview?.items || []).map((i) => i.project_id)).size)

function projectChoice(pid: string): ProjectChoice {
  return projectChoices.value[pid] ?? 'apply'
}
function setProject(pid: string, v: ProjectChoice) {
  projectChoices.value = { ...projectChoices.value, [pid]: v }
}
function setAllProjects(v: ProjectChoice) {
  const next: Record<string, ProjectChoice> = {}
  for (const p of projects.value) if (!p.frozen) next[p.project_id] = v
  projectChoices.value = next
}

async function onSubmit() {
  if (!props.preview || submitting.value) return
  submitting.value = true
  try {
    const ok = await props.submit({
      decisions: {
        project_choices: props.allowDefer && !props.readonlyDecisions ? { ...projectChoices.value } : {},
        // 键 = 服务端条目 key 原样（FormulaConflictTable 只认它）
        conflict_choices: props.readonlyDecisions ? {} : { ...conflictChoices.value },
        default_conflict: props.defaultConflict,
      },
      note: note.value.trim(),
    })
    if (ok) visible.value = false
  } finally {
    submitting.value = false
  }
}
</script>

<style scoped>
.gt-fpp { min-height: 120px; }
.gt-fpp-gap { margin-bottom: 12px; }
.gt-fpp-h { font-size: var(--gt-font-size-sm); font-weight: 600; margin-bottom: 6px; display: flex; align-items: center; gap: 8px; }
.gt-fpp-counts { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
.gt-fpp-muted { font-size: var(--gt-font-size-xs); color: var(--gt-color-text-tertiary); }
.gt-fpp-tip { margin-top: 4px; }
.gt-fpp-code { font-size: var(--gt-font-size-xs); word-break: break-all; white-space: normal; }
.gt-fpp-new { color: var(--gt-color-primary); }
</style>
