<template>
  <el-dialog
    :model-value="modelValue"
    title="转存为笔记"
    width="520px"
    append-to-body
    :close-on-click-modal="false"
    @update:model-value="(v: boolean) => emit('update:modelValue', v)"
    @open="onOpen"
  >
    <template v-if="!saved">
      <p class="chat-note-save__lead">将选中的 {{ count }} 条 AI 回复保存为知识库笔记。</p>
      <el-form
        ref="formRef"
        :model="form"
        :rules="formRules"
        label-position="top"
        @submit.prevent
      >
        <el-form-item label="笔记名称" prop="name" required>
          <el-input
            v-model="form.name"
            data-testid="note-name"
            :maxlength="NOTE_NAME_MAX_LENGTH"
            show-word-limit
            placeholder="例如：存货监盘程序问答"
          />
        </el-form-item>

        <el-form-item label="保存位置" required>
          <div v-if="hostHasProject" class="chat-note-save__fixed" data-testid="note-fixed-location">
            本项目的「AI 对话笔记」文件夹（首次保存时自动创建）
          </div>
          <template v-else>
            <el-radio-group v-model="mode" data-testid="note-mode">
              <el-radio-button value="project">项目笔记</el-radio-button>
              <el-radio-button value="folder">知识库文件夹</el-radio-button>
            </el-radio-group>
            <el-select
              v-if="mode === 'project'"
              v-model="projectId"
              data-testid="note-project"
              filterable
              placeholder="选择项目"
              :loading="loading"
              class="chat-note-save__picker"
            >
              <el-option v-for="p in projects" :key="p.id" :label="p.label" :value="p.id" />
            </el-select>
            <el-tree-select
              v-else
              v-model="folderId"
              data-testid="note-folder"
              :data="folders"
              :props="FOLDER_TREE_PROPS"
              node-key="id"
              check-strictly
              filterable
              default-expand-all
              :render-after-expand="false"
              placeholder="选择有新建权限的文件夹"
              :loading="loading"
              class="chat-note-save__picker"
            />
            <div class="chat-note-save__hint">
              {{ mode === 'project'
                ? '保存到所选项目的「AI 对话笔记」文件夹（首次保存时自动创建），仅该项目成员可在知识库中查看'
                : '笔记继承所选文件夹的可见范围；灰色文件夹没有新建权限' }}
            </div>
          </template>
        </el-form-item>
      </el-form>
      <p class="chat-note-save__hint">同一位置已有同名笔记时会保存为新版本，原版本保留。</p>
      <el-alert
        v-if="errorText"
        type="error"
        :closable="false"
        show-icon
        :title="errorText"
        role="alert"
      />
    </template>

    <div v-else class="chat-note-save__done" role="status" data-testid="note-saved">
      <p class="chat-note-save__done-title">笔记已保存</p>
      <p>名称：{{ saved.name || form.name }}</p>
      <p>位置：{{ saved.location || plannedLocation }}</p>
      <p v-if="saved.replayed" class="chat-note-save__hint">这些回复此前已用相同名称保存过，未重复创建。</p>
    </div>

    <template #footer>
      <template v-if="!saved">
        <el-button @click="emit('update:modelValue', false)">取消</el-button>
        <el-button
          type="primary"
          data-testid="note-submit"
          :disabled="!canSubmit"
          :loading="submitting"
          @click="onSubmit"
        >
          保存
        </el-button>
      </template>
      <template v-else>
        <el-button v-if="saved.jumpRoute" data-testid="note-open" @click="openSaved">
          在知识库中查看
        </el-button>
        <el-button type="primary" @click="emit('update:modelValue', false)">完成</el-button>
      </template>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
/**
 * ChatNoteSaveDialog — 转存笔记前确认名称与保存位置
 *
 * - 当前宿主有项目：位置固定为本项目「AI 对话笔记」，只展示不让选（服务端也只允许本项目）；
 * - 当前宿主无项目（全局知识 / 无项目的知识库页面）：选「项目笔记」或「知识库文件夹」，
 *   文件夹只能选有新建权限的（树节点 `can_create=false` 禁选）；知识库文件夹页面默认选中当前文件夹。
 *
 * 2026-10-20 前：无项目页面直接提示「当前页面无项目上下文」，且请求体与后端契约不一致恒 422。
 *
 * Feature: ai-chat-adopt-and-note-target-picker / R3
 */
import { computed, reactive, ref } from 'vue'
import type { FormInstance, FormRules } from 'element-plus'
import type { AiHostRef } from '@/composables/useAiHostContext'
import {
  NOTE_NAME_MAX_LENGTH,
  type NoteCaptureResult,
  type NoteSaveRequest,
  type NoteSaveTarget,
} from '@/composables/useAiNoteCapture'
import { rules } from '@/utils/formRules'
import {
  findFolderPath,
  isCreatableFolder,
  loadFolderOptions,
  loadProjectOptions,
  type FolderOption,
  type ProjectOption,
} from './chatTargetOptions'

const props = defineProps<{
  modelValue: boolean
  host: AiHostRef | null
  /** 选中的回复条数 */
  count: number
  /** 上次失败时的名称与位置（重试时预填） */
  initial?: NoteSaveRequest | null
  submit: (request: NoteSaveRequest) => Promise<NoteCaptureResult>
}>()

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  saved: [result: NoteCaptureResult]
}>()

const FOLDER_TREE_PROPS = { label: 'name', children: 'children', disabled: 'disabled' }

const formRef = ref<FormInstance>()
const form = reactive({ name: '' })
const formRules: FormRules = {
  name: [
    rules.required('笔记名称'),
    { max: NOTE_NAME_MAX_LENGTH, message: `笔记名称不超过 ${NOTE_NAME_MAX_LENGTH} 字`, trigger: 'blur' },
  ],
}
const mode = ref<'project' | 'folder'>('project')
const projectId = ref('')
const folderId = ref('')
const projects = ref<ProjectOption[]>([])
const folders = ref<FolderOption[]>([])
const loading = ref(false)
const submitting = ref(false)
const errorText = ref('')
const saved = ref<NoteCaptureResult | null>(null)

const hostHasProject = computed(() => !!props.host?.projectId)

const target = computed<NoteSaveTarget | null>(() => {
  if (hostHasProject.value) return { kind: 'host_project' }
  if (mode.value === 'project') return projectId.value ? { kind: 'project', projectId: projectId.value } : null
  return isCreatableFolder(folders.value, folderId.value) ? { kind: 'folder', folderId: folderId.value } : null
})

const canSubmit = computed(() => !!form.name.trim() && !!target.value && !submitting.value)

/** 提交前对用户展示的计划位置（成功后以服务端回传的实际位置为准） */
const plannedLocation = computed(() => {
  if (hostHasProject.value) return '本项目 / AI 对话笔记'
  if (mode.value === 'project') {
    const p = projects.value.find((x) => x.id === projectId.value)
    return p ? `${p.label} / AI 对话笔记` : ''
  }
  return (findFolderPath(folders.value, folderId.value) || []).join(' / ')
})

async function onOpen() {
  saved.value = null
  errorText.value = ''
  const init = props.initial
  form.name = init?.name ?? ''
  formRef.value?.clearValidate()
  projectId.value = init?.target.kind === 'project' ? init.target.projectId : ''
  folderId.value = init?.target.kind === 'folder' ? init.target.folderId : ''
  if (hostHasProject.value) return
  const hostFolder = props.host?.type === 'knowledge_folder' ? props.host.id : null
  mode.value = init?.target.kind === 'folder' || (!init && hostFolder) ? 'folder' : 'project'
  loading.value = true
  try {
    const [p, f] = await Promise.all([loadProjectOptions(), loadFolderOptions()])
    projects.value = p
    folders.value = f
  } catch {
    errorText.value = '保存位置列表加载失败，请稍后重试'
  } finally {
    loading.value = false
  }
  if (!folderId.value && hostFolder && isCreatableFolder(folders.value, hostFolder)) {
    folderId.value = hostFolder
  }
}

async function onSubmit() {
  errorText.value = ''
  if (formRef.value) {
    const valid = await formRef.value.validate().then(() => true, () => false)
    if (!valid) return
  }
  if (!target.value) {
    errorText.value = '请选择笔记保存位置'
    return
  }
  submitting.value = true
  try {
    const result = await props.submit({ name: form.name.trim(), target: target.value })
    if (!result.success) {
      errorText.value = result.errorMessage || '笔记保存失败，请稍后重试'
      return
    }
    saved.value = result
    emit('saved', result)
  } finally {
    submitting.value = false
  }
}

/**
 * 用户点击后在新标签打开知识库深链（不自动弹窗）。
 *
 * 🔴 不能加 `noopener`：登录令牌在 sessionStorage，`noopener` 打开的标签页不继承它 ⇒
 * 新标签直接跳登录页（2026-10-21 浏览器实测）。只放行站内相对路径（服务端
 * `knowledge_jump_route` 生成的 `/knowledge?...`），不打开任何外部地址。
 */
function openSaved() {
  const route = saved.value?.jumpRoute
  if (route && /^\/(?!\/)/.test(route)) window.open(route, '_blank')
}
</script>

<style scoped>
.chat-note-save__lead {
  margin: 0 0 12px;
  font-size: 13px;
  color: var(--el-text-color-regular, #606266);
}

.chat-note-save__fixed {
  font-size: 13px;
  color: var(--el-text-color-primary, #303133);
}

.chat-note-save__picker {
  width: 100%;
  margin-top: 8px;
}

.chat-note-save__hint {
  margin: 4px 0 0;
  font-size: 12px;
  line-height: 1.5;
  color: var(--el-text-color-secondary, #909399);
}

.chat-note-save__done {
  font-size: 13px;
  line-height: 1.8;
}

.chat-note-save__done p {
  margin: 0;
}

.chat-note-save__done-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--el-color-success, #67c23a);
}
</style>
