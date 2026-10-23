<script setup lang="ts">
/**
 * DisclosureNoteContentTools — 附注编辑器「上传附注文档 / 保存为内容模板 / 引用内容模板 / 导入上年附注」的弹窗宿主。
 *
 * 抽出原因：DisclosureEditor.vue 有 3300 行硬上限。四个入口在这里统一：
 * - 写入口门禁（R-20 / AC-6.3）：canWrite（只读 / 归档 / EQCR / 编辑锁）、附注编辑操作权限 `note:edit`、
 *   合并锁定三者任一不满足 ⇒ `available` 为假（编辑器据此隐藏菜单项），open() 也直接拒绝；后端仍独立 403 / 423；
 * - 当前章节有未保存修改时也拒绝：写入成功后编辑器会重载附注（未保存修改会被服务端内容覆盖），
 *   内容模板也只按已保存内容生成——都要求先保存；
 * - 同一时刻只挂一个弹窗（v-if + 异步组件），不预先创建编辑器实例；
 * - 写入成功统一上报，由编辑器作废全部章节缓存后强制刷新（R-19）。
 */
import { computed, defineAsyncComponent, onMounted, onUnmounted, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import type { ApplyResponse } from '@/composables/useNoteTextBatch'
import type { ContentTemplateItem, ContentTemplateVersion } from '@/composables/useNoteContentTemplate'
import type { PriorYearApplied } from './notePriorYearImport'
import type { AxiosRequestConfig } from 'axios'
import { api } from '@/services/apiProxy'
import { consolidation as P_consol } from '@/services/apiPaths'
import { eventBus } from '@/utils/eventBus'

const NoteDocUploadDialog = defineAsyncComponent(() => import('./NoteDocUploadDialog.vue'))
const NoteContentTemplateSaveDialog = defineAsyncComponent(() => import('./NoteContentTemplateSaveDialog.vue'))
const NoteContentTemplatePicker = defineAsyncComponent(() => import('./NoteContentTemplatePicker.vue'))
const NoteContentTemplateApplyDialog = defineAsyncComponent(() => import('./NoteContentTemplateApplyDialog.vue'))
const NotePriorYearImportDialog = defineAsyncComponent(() => import('./NotePriorYearImportDialog.vue'))

const props = defineProps<{ projectId: string; year: number; canWrite: boolean; hasUnsavedChanges?: boolean }>()
const emit = defineEmits<{ 'applied': [changedSections: string[]] }>()

const active = ref<'upload' | 'save' | 'pick' | 'prior-year' | null>(null)
const applyTarget = ref<{ template: ContentTemplateItem; version: ContentTemplateVersion } | null>(null)

// ── AC-6.3：合并锁定也要隐藏写入口（编辑器的 canEdit 只含归档与项目权限，不含合并锁）──
const consolLocked = ref(false)
/**
 * 必须关掉 http 的 GET 去重：同页的合并锁定横幅几乎同时发同一个 GET，去重会**取消先发的那一个**，
 * 横幅拿不到锁定态就不显示（浏览器实测：入口藏了、横幅却没出来）。静默：失败只当未锁定，不弹全局提示。
 */
const LOCK_REQUEST: AxiosRequestConfig & { _dedupe: boolean; _silent: boolean } = { _dedupe: false, _silent: true }
async function refreshLock() {
  if (!props.projectId) return
  try {
    const res = await api.get<{ locked?: boolean; data?: { locked?: boolean } }>(
      P_consol.lockStatus(props.projectId), LOCK_REQUEST)
    consolLocked.value = Boolean((res?.data ?? res)?.locked)
  } catch {
    consolLocked.value = false  // 查询失败不误报锁定（与锁定横幅同口径；后端仍独立 423）
  }
}
onMounted(refreshLock)
watch(() => props.projectId, refreshLock)
eventBus.on('consol-lock:detected', refreshLock)
onUnmounted(() => eventBus.off('consol-lock:detected', refreshLock))

/** 四个入口是否可用：编辑权限（canWrite 由父组件经 noteEdit 判定查询提供）+ 未合并锁定 */
const available = computed(() => props.canWrite && !consolLocked.value)

function open(kind: 'upload' | 'save' | 'apply' | 'prior-year'): boolean {
  if (!props.canWrite) {
    ElMessage.warning('当前无编辑权限（只读、已归档、合并锁定或 EQCR 复核中），不能批量写入附注')
    return false
  }

  if (consolLocked.value) {
    ElMessage.warning('项目已被合并锁定，不能批量写入附注')
    return false
  }
  if (props.hasUnsavedChanges) {
    ElMessage.warning(kind === 'save'
      ? '内容模板按已保存的附注内容生成，请先保存当前章节的修改'
      : '当前章节有未保存的修改，请先保存（批量写入完成后会重新加载附注内容，未保存的修改会丢失）')
    return false
  }
  active.value = kind === 'apply' ? 'pick' : kind
  return true
}

function close() {
  active.value = null
}

function onPicked(template: ContentTemplateItem, version: ContentTemplateVersion) {
  applyTarget.value = { template, version }
}

function onApplied(result: ApplyResponse) {
  applyTarget.value = null
  active.value = null
  emit('applied', (result.changed_notes ?? []).map(c => c.note_section))
}

function onPriorYearApplied(result: PriorYearApplied) {
  active.value = null
  emit('applied', result.changed_sections ?? [])
}

defineExpose({ open, available })
</script>

<template>
  <NoteDocUploadDialog v-if="active === 'upload'" :visible="true" :project-id="projectId" :year="year"
    @update:visible="(v: boolean) => !v && close()" @applied="onApplied" />
  <NoteContentTemplateSaveDialog v-if="active === 'save'" :visible="true" :project-id="projectId" :year="year"
    @update:visible="(v: boolean) => !v && close()" />
  <NoteContentTemplatePicker v-if="active === 'pick'" :visible="true" :project-id="projectId" :year="year"
    @update:visible="(v: boolean) => !v && close()" @select="onPicked" />
  <NoteContentTemplateApplyDialog v-if="applyTarget" :visible="true" :project-id="projectId" :year="year"
    :template="applyTarget.template" :version="applyTarget.version"
    @update:visible="(v: boolean) => !v && (applyTarget = null)" @applied="onApplied" />
  <NotePriorYearImportDialog v-if="active === 'prior-year'" :visible="true" :project-id="projectId" :year="year"
    @update:visible="(v: boolean) => !v && close()" @applied="onPriorYearApplied" />
</template>
