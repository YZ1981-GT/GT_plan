<!--
  本项目「公式待确认」弹窗 + 顶栏角标（spec formula-global-settings-sync，design §11，R5）。
  - 进入项目即拉取；有待确认事项时自动弹出，同一会话同一项目只自动弹一次（「稍后处理」后角标常驻）；
  - 切换项目时丢弃上一个项目晚到的响应，弹窗随之关闭；
  - 每条给出原因（冲突 / 管理员暂缓）与三方对比：原定义 / 新定义（来自全局设置、公式模板或其他项目）/ 本项目当前；
  - 逐条或批量：采用新定义 / 保留本项目 / 手工修改；处理需本项目编辑权限（只读成员可看不可处理）。
-->
<template>
  <span v-if="projectId && count > 0" class="gt-fps-anchor">
    <el-tooltip :content="`有 ${count} 处公式待确认`" placement="bottom">
      <button type="button" class="gt-fps-badge" data-testid="formula-pending-badge"
        :aria-label="`公式待确认 ${count} 处`" @click="openDialog">
        <el-badge :value="count" :max="99" type="danger"><span class="gt-fps-icon">ƒx</span></el-badge>
      </button>
    </el-tooltip>
  </span>
  <el-dialog v-model="visible" title="公式待确认" width="min(1240px, 96vw)" append-to-body destroy-on-close
    data-testid="formula-pending-dialog">
    <el-alert type="warning" :closable="false" show-icon class="gt-fps-gap"
      title="全局设置或公式模板有更新，与本项目改过的公式不一致（或管理员暂缓应用）。请逐条确认；选「稍后处理」可先关闭，角标会一直提醒。" />
    <div class="gt-fps-bar">
      <span class="gt-fps-muted">共 {{ count }} 处，已选择处理 {{ chosenCount }} 处</span>
      <span class="gt-fps-spacer" />
      <el-button size="small" data-testid="fps-all-adopt" @click="setAll('adopt')">全部采用新定义</el-button>
      <el-button size="small" data-testid="fps-all-keep" @click="setAll('keep')">全部保留本项目</el-button>
    </div>
    <el-table v-loading="loading" :data="items" size="small" border max-height="460" row-key="id">
      <el-table-column label="公式位" min-width="180" show-overflow-tooltip>
        <template #default="{ row }">
          <div>{{ row.slot_label }}</div>
          <el-tag size="small" effect="plain" type="info">{{ domainLabel(row.domain) }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="原因" width="130">
        <template #default="{ row }">
          <el-tag size="small" :type="row.reason === 'conflict' ? 'danger' : 'warning'">{{ row.reason_label }}</el-tag>
          <div class="gt-fps-muted">来自{{ row.upstream_origin_label }}</div>
        </template>
      </el-table-column>
      <el-table-column label="原定义（基线）" min-width="150">
        <template #default="{ row }"><code class="gt-fps-code">{{ row.base_formula || '（空）' }}</code></template>
      </el-table-column>
      <el-table-column label="新定义" min-width="150">
        <template #default="{ row }">
          <el-tag v-if="row.upstream_deleted" size="small" type="danger">已删除</el-tag>
          <code v-else class="gt-fps-code gt-fps-new">{{ row.upstream_formula }}</code>
        </template>
      </el-table-column>
      <el-table-column label="本项目当前" min-width="150">
        <template #default="{ row }"><code class="gt-fps-code gt-fps-local">{{ row.local_formula || '（空）' }}</code></template>
      </el-table-column>
      <!-- 三个选项按钮约 320px：列宽不够时最后一个会被裁掉（实测 1080px 弹窗里「手工修改」看不全） -->
      <el-table-column label="处理" min-width="330">
        <template #default="{ row }">
          <el-radio-group :model-value="choices[row.id] || ''" size="small"
            @update:model-value="(v: string | number | boolean | undefined) => setChoice(row, v as ResolutionChoice)">
            <el-radio-button value="adopt">采用新定义</el-radio-button>
            <el-radio-button value="keep">保留本项目</el-radio-button>
            <el-radio-button value="custom">手工修改</el-radio-button>
          </el-radio-group>
          <div v-if="choices[row.id] === 'custom'" class="gt-fps-custom">
            <el-input v-for="f in editableFields(row)" :key="f" v-model="custom[row.id][f]" size="small"
              :placeholder="fieldLabel(f)">
              <template #prepend>{{ fieldLabel(f) }}</template>
            </el-input>
          </div>
        </template>
      </el-table-column>
    </el-table>
    <template #footer>
      <el-button data-testid="fps-later" @click="visible = false">稍后处理</el-button>
      <el-button type="primary" :loading="submitting" :disabled="!chosenCount" data-testid="fps-submit"
        @click="onSubmit">确认处理（{{ chosenCount }}）</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import {
  FIELD_LABELS, errorCodeOf, formulaErrorText, formulaSettingsApi,
  type FormulaDomainInfo, type PendingItem, type Resolution, type ResolutionChoice,
} from '@/composables/formula/useFormulaSettings'

defineOptions({ name: 'FormulaPendingSyncDialog' })

const props = defineProps<{ projectId: string }>()
const emit = defineEmits<{ resolved: [domains: string[]] }>()

const SHOWN_KEY = 'gt:formula-pending-shown:'
/** sessionStorage 不可用（隐私模式等）时的会话内兜底 */
const shownFallback = new Set<string>()

const items = ref<PendingItem[]>([])
const visible = ref(false)
const loading = ref(false)
const submitting = ref(false)
const choices = reactive<Record<string, ResolutionChoice | ''>>({})
const custom = reactive<Record<string, Record<string, string>>>({})
const domains = ref<Record<string, FormulaDomainInfo>>({})
let loadSeq = 0

const count = computed(() => items.value.length)
const chosenCount = computed(() => items.value.filter((i) => choices[i.id]).length)

function alreadyShown(pid: string): boolean {
  try { return sessionStorage.getItem(SHOWN_KEY + pid) === '1' } catch { return shownFallback.has(pid) }
}
function markShown(pid: string) {
  shownFallback.add(pid)
  try { sessionStorage.setItem(SHOWN_KEY + pid, '1') } catch { /* 会话内兜底已记 */ }
}

function resetChoices() {
  for (const k of Object.keys(choices)) delete choices[k]
  for (const k of Object.keys(custom)) delete custom[k]
}

/** 拉取本项目待确认；`autoOpen` = 进入项目时的自动弹出（会话内每项目一次）。 */
async function reload(autoOpen = false) {
  const pid = props.projectId
  const seq = ++loadSeq
  if (!pid) { items.value = []; return }
  loading.value = true
  try {
    const data = await formulaSettingsApi.pending(pid)
    if (seq !== loadSeq || pid !== props.projectId) return // 晚到：已切到别的项目
    items.value = data?.items || []
    const alive = new Set(items.value.map((i) => i.id))
    for (const k of Object.keys(choices)) if (!alive.has(k)) { delete choices[k]; delete custom[k] }
    if (autoOpen && items.value.length && !alreadyShown(pid)) {
      markShown(pid)
      openDialog()
    }
  } catch {
    if (seq === loadSeq) items.value = [] // 拉取失败不打扰（角标不显示）
  } finally {
    if (seq === loadSeq) loading.value = false
  }
}

async function ensureDomains() {
  if (Object.keys(domains.value).length) return
  try {
    const data = await formulaSettingsApi.domains()
    domains.value = Object.fromEntries((data?.domains || []).map((d) => [d.key, d]))
  } catch { /* 无域信息时按定义字段兜底 */ }
}

function openDialog() {
  visible.value = true
  void ensureDomains()
}

function domainLabel(key: string): string {
  return domains.value[key]?.label || key
}
function fieldLabel(f: string): string {
  return FIELD_LABELS[f] || f
}
function editableFields(row: PendingItem): string[] {
  const exec = domains.value[row.domain]?.exec_fields
  if (exec?.length) return exec
  return Object.keys(row.local_definition || row.upstream_definition || { formula: '' })
}

function setChoice(row: PendingItem, v: ResolutionChoice) {
  choices[row.id] = v
  if (v === 'custom' && !custom[row.id]) {
    const src = { ...(row.upstream_definition || {}), ...(row.local_definition || {}) }
    custom[row.id] = Object.fromEntries(editableFields(row).map((f) => [f, src[f] == null ? '' : String(src[f])]))
  }
}
function setAll(v: ResolutionChoice) {
  for (const it of items.value) choices[it.id] = v
}

function buildResolutions(): Resolution[] {
  return items.value.filter((i) => choices[i.id]).map((i) => {
    const choice = choices[i.id] as ResolutionChoice
    const r: Resolution = { item_id: i.id, choice, upstream_version: i.upstream_version }
    if (choice === 'custom') r.custom_definition = { ...(i.local_definition || {}), ...custom[i.id] }
    return r
  })
}

async function onSubmit() {
  const pid = props.projectId
  const resolutions = buildResolutions()
  if (!pid || !resolutions.length || submitting.value) return
  submitting.value = true
  try {
    await formulaSettingsApi.resolve(pid, resolutions)
    const done = new Set(resolutions.map((r) => r.item_id))
    const touched = [...new Set(items.value.filter((i) => done.has(i.id)).map((i) => i.domain))]
    ElMessage.success(`已处理 ${resolutions.length} 处，相关报表 / 附注会按新定义重算`)
    resetChoices()
    await reload()
    emit('resolved', touched)
    if (!items.value.length) visible.value = false
  } catch (e: any) {
    if (errorCodeOf(e) === 'FORMULA_SYNC_ITEM_STALE') {
      ElMessage.warning('有事项已被新的发布更新，已刷新列表，请重新确认')
      await reload()
    } else if ((e?.response?.status || e?.status) === 403) {
      ElMessage.warning('只读成员可以查看，处理需要本项目的编辑权限')
    } else {
      ElMessage.error(formulaErrorText(e, '处理待确认失败'))
    }
  } finally {
    submitting.value = false
  }
}

watch(() => props.projectId, (pid) => {
  visible.value = false
  items.value = []
  resetChoices()
  if (pid) void reload(true)
}, { immediate: true })

defineExpose({ reload, openDialog, count })
</script>

<style scoped>
.gt-fps-anchor { display: inline-flex; }
.gt-fps-badge {
  cursor: pointer; width: 34px; height: 34px; display: inline-flex; align-items: center; justify-content: center;
  border-radius: 8px; border: none; background: transparent; padding: 0; font-family: inherit;
  color: rgba(255, 255, 255, 0.9); font-size: var(--gt-font-size-sm); transition: background 0.15s ease;
}
.gt-fps-badge:hover { background: rgba(255, 255, 255, 0.12); }
.gt-fps-icon { font-style: italic; font-weight: 600; }
.gt-fps-gap { margin-bottom: 8px; }
.gt-fps-bar { display: flex; align-items: center; gap: 6px; margin-bottom: 6px; }
.gt-fps-spacer { flex: 1; }
.gt-fps-muted { font-size: var(--gt-font-size-xs); color: var(--gt-color-text-tertiary); }
.gt-fps-code { font-size: var(--gt-font-size-xs); word-break: break-all; white-space: normal; }
.gt-fps-new { color: var(--gt-color-primary); }
.gt-fps-local { color: var(--gt-color-warning); }
.gt-fps-custom { display: flex; flex-direction: column; gap: 4px; margin-top: 6px; }
</style>
