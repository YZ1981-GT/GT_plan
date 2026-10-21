<template>
  <el-dialog
    :model-value="modelValue"
    title="采纳到…"
    width="520px"
    append-to-body
    :close-on-click-modal="false"
    @update:model-value="(v: boolean) => emit('update:modelValue', v)"
    @open="onOpen"
  >
    <el-alert type="info" :closable="false" show-icon class="chat-adopt-target__intro">
      采纳不会直接改写文件：内容进入所选项目的「AI 生成内容待确认」，在目标页面确认后才生效。
    </el-alert>

    <el-form label-position="top" class="chat-adopt-target__form" @submit.prevent>
      <el-form-item label="项目" required>
        <el-select
          v-model="projectId"
          data-testid="adopt-project"
          filterable
          placeholder="选择项目"
          :disabled="projectLocked"
          :loading="loadingProjects"
          style="width: 100%"
          @change="onProjectChange"
        >
          <el-option v-for="p in projects" :key="p.id" :label="p.label" :value="p.id" />
        </el-select>
        <div v-if="projectLocked" class="chat-adopt-target__hint">
          这段对话属于该项目，只能采纳到本项目
        </div>
      </el-form-item>

      <el-form-item label="采纳到" required>
        <el-radio-group v-model="kind" data-testid="adopt-kind" @change="reloadFiles">
          <el-radio-button value="workpaper">底稿</el-radio-button>
          <el-radio-button value="note">附注章节</el-radio-button>
        </el-radio-group>
      </el-form-item>

      <el-form-item :label="kind === 'workpaper' ? '底稿' : '附注章节'" required>
        <el-select
          v-model="fileId"
          data-testid="adopt-file"
          filterable
          :placeholder="kind === 'workpaper' ? '选择底稿' : '选择附注章节'"
          :disabled="!projectId"
          :loading="loadingFiles"
          style="width: 100%"
        >
          <el-option v-for="f in files" :key="f.id" :label="f.label" :value="f.id" />
        </el-select>
        <div v-if="filesHint" class="chat-adopt-target__hint" role="status">{{ filesHint }}</div>
      </el-form-item>

      <el-form-item label="目标位置（可选）">
        <el-input
          v-model="targetCell"
          data-testid="adopt-cell"
          maxlength="120"
          show-word-limit
          placeholder="如单元格 D12、段落名称，可不填"
        />
      </el-form-item>
    </el-form>

    <el-alert
      v-if="errorText"
      type="error"
      :closable="false"
      show-icon
      :title="errorText"
      role="alert"
    />

    <template #footer>
      <el-button @click="emit('update:modelValue', false)">取消</el-button>
      <el-button
        type="primary"
        data-testid="adopt-submit"
        :disabled="!canSubmit"
        :loading="submitting"
        @click="onSubmit"
      >
        采纳
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
/**
 * ChatAdoptTargetDialog — 当前宿主不能直接采纳时，让用户选定采纳目标
 *
 * 全局知识 / 报表 / 知识库页面里的 AI 回复没有可回写的业务实例（2026-10-20 实测：
 * 项目列表页点「采纳」恒「资源不存在或不可访问」）。这里按「项目 → 底稿 / 附注章节 →
 * 可选位置」选择，提交由父组件传入的 `submit`（`usePlatformAiChat.adoptContent(id, target)`）。
 * 失败在对话框内显示原因、保持打开可重试；成功关闭并通知父组件目标名称。
 *
 * Feature: ai-chat-adopt-and-note-target-picker / R1
 */
import { computed, ref } from 'vue'
import type { AiHostRef } from '@/composables/useAiHostContext'
import type { AdoptTarget } from '@/composables/usePlatformAiChat'
import {
  buildAdoptTargetHost,
  loadFileOptions,
  loadProjectOptions,
  type AdoptTargetKind,
  type FileOption,
  type ProjectOption,
} from './chatTargetOptions'

const props = defineProps<{
  modelValue: boolean
  /** 消息所在会话的宿主（有项目时锁定该项目） */
  sourceHost: AiHostRef | null
  submit: (target: AdoptTarget) => Promise<{ success: boolean; message?: string }>
}>()

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  /** 采纳已提交；参数为目标的展示名（「项目 / 底稿」） */
  done: [label: string]
}>()

const projects = ref<ProjectOption[]>([])
const projectId = ref<string>('')
const kind = ref<AdoptTargetKind>('workpaper')
const files = ref<FileOption[]>([])
const fileId = ref<string>('')
const targetCell = ref('')
const filesHint = ref('')
const errorText = ref('')
const loadingProjects = ref(false)
const loadingFiles = ref(false)
const submitting = ref(false)
/** 加载序号：项目 / 类型连续切换时只采纳最后一次结果 */
let filesEpoch = 0

const projectLocked = computed(() => !!props.sourceHost?.projectId)
const canSubmit = computed(() => !!projectId.value && !!fileId.value && !submitting.value)

function currentProject(): ProjectOption | undefined {
  return projects.value.find((p) => p.id === projectId.value)
}

async function onOpen() {
  errorText.value = ''
  targetCell.value = ''
  fileId.value = ''
  files.value = []
  filesHint.value = ''
  loadingProjects.value = true
  try {
    projects.value = await loadProjectOptions()
  } catch {
    projects.value = []
    errorText.value = '项目列表加载失败，请稍后重试'
  } finally {
    loadingProjects.value = false
  }
  const locked = props.sourceHost?.projectId
  if (locked) {
    projectId.value = locked
    if (!currentProject()) {
      errorText.value = '你不是该项目成员或项目不存在，无法采纳到本项目'
      return
    }
  } else if (!currentProject()) {
    projectId.value = ''
  }
  if (projectId.value) await reloadFiles()
}

async function onProjectChange() {
  fileId.value = ''
  await reloadFiles()
}

async function reloadFiles() {
  fileId.value = ''
  files.value = []
  filesHint.value = ''
  const project = currentProject()
  if (!project) return
  const epoch = ++filesEpoch
  loadingFiles.value = true
  try {
    const { options, hint } = await loadFileOptions(kind.value, project)
    if (epoch !== filesEpoch) return
    files.value = options
    filesHint.value = hint
  } catch {
    if (epoch !== filesEpoch) return
    filesHint.value = kind.value === 'workpaper' ? '底稿列表加载失败，请稍后重试' : '附注目录加载失败，请稍后重试'
  } finally {
    if (epoch === filesEpoch) loadingFiles.value = false
  }
}

async function onSubmit() {
  errorText.value = ''
  const host = buildAdoptTargetHost(kind.value, fileId.value, projectId.value)
  if (!host) {
    errorText.value = '所选目标无效，请重新选择'
    return
  }
  submitting.value = true
  try {
    const result = await props.submit({ host, targetCell: targetCell.value.trim() || null })
    if (!result.success) {
      errorText.value = result.message || '采纳提交失败，请稍后重试'
      return
    }
    const file = files.value.find((f) => f.id === fileId.value)
    const label = [currentProject()?.label, file?.label].filter(Boolean).join(' / ')
    emit('done', label)
    emit('update:modelValue', false)
  } finally {
    submitting.value = false
  }
}
</script>

<style scoped>
.chat-adopt-target__intro {
  margin-bottom: 12px;
}

.chat-adopt-target__hint {
  margin-top: 4px;
  font-size: 12px;
  line-height: 1.5;
  color: var(--el-text-color-secondary, #909399);
}
</style>
