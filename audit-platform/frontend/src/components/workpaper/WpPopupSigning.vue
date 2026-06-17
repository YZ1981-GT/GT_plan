<script setup lang="ts">
/**
 * WpPopupSigning — A1-11 业务报告签发流转控制表
 *
 * 签字审批链（7行角色 × 签字人姓名 + 日期）
 * 数据保存到 checklist_responses
 */
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '@/services/apiProxy'

const props = defineProps<{
  wpCode: string
  wpId?: string
  projectId?: string
}>()

const emit = defineEmits<{
  (e: 'save'): void
  (e: 'completed'): void
}>()

const SIGNERS = [
  { id: 'A1-11-sign-pm', role: '项目负责经理', required: true },
  { id: 'A1-11-sign-partner', role: '项目合伙人', required: true },
  { id: 'A1-11-sign-qc-partner', role: '项目质量复核合伙人（如适用）', required: false },
  { id: 'A1-11-sign-qc', role: '质量控制复核人', required: true },
  { id: 'A1-11-sign-it', role: 'IT专家', required: false },
  { id: 'A1-11-sign-tax', role: '税务专家', required: false },
  { id: 'A1-11-sign-translator', role: '报告翻译复核人', required: false },
]

interface SignerState { name: string; date: string }
const signerStates = ref<Record<string, SignerState>>({})
const loading = ref(false)
const saveTimer = ref<ReturnType<typeof setTimeout> | null>(null)

const isCompleted = computed(() =>
  SIGNERS.filter(s => s.required).every(s => signerStates.value[s.id]?.name)
)

function initStates() {
  for (const s of SIGNERS) {
    if (!signerStates.value[s.id]) {
      signerStates.value[s.id] = { name: '', date: '' }
    }
  }
}

async function loadData() {
  if (!props.wpId) return
  loading.value = true
  try {
    const res = await api.get(`/api/workpapers/${props.wpId}/checklist-responses`)
    const list = Array.isArray(res) ? res : (res?.data ?? [])
    for (const r of list) {
      if (r.item_id?.startsWith('A1-11-sign-')) {
        signerStates.value[r.item_id] = { name: r.conclusion || '', date: r.remark || '' }
      }
    }
  } catch { /* ignore */ }
  finally { loading.value = false }
}

function scheduleSave() {
  if (saveTimer.value) clearTimeout(saveTimer.value)
  saveTimer.value = setTimeout(doSave, 2000)
}

async function doSave() {
  if (!props.wpId || !props.projectId) return
  const items = SIGNERS.map(s => ({
    item_id: s.id,
    conclusion: signerStates.value[s.id]?.name || null,
    remark: signerStates.value[s.id]?.date || null,
    wp_ref: null,
  }))
  try {
    await api.put(`/api/workpapers/${props.wpId}/checklist-responses`, { project_id: props.projectId, items })
    emit('save')
    if (isCompleted.value) emit('completed')
  } catch (err: any) {
    if (err?.message !== 'canceled' && err?.code !== 'ERR_CANCELED') ElMessage.error('保存失败')
  }
}

function updateName(id: string, val: string) { signerStates.value[id].name = val; scheduleSave() }
function updateDate(id: string, val: string) { signerStates.value[id].date = val; scheduleSave() }

onMounted(() => { initStates(); loadData() })
onBeforeUnmount(() => { if (saveTimer.value) { clearTimeout(saveTimer.value); doSave() } })
</script>

<template>
  <div class="wp-popup-signing" v-loading="loading">
    <div class="signing-table">
      <div class="signing-table__header">
        <span class="col-role">审批角色</span>
        <span class="col-name">签字人</span>
        <span class="col-date">日期</span>
      </div>
      <div
        v-for="signer in SIGNERS"
        :key="signer.id"
        class="signing-row"
        :class="{ 'is-signed': signerStates[signer.id]?.name, 'is-required': signer.required }"
      >
        <span class="col-role">
          {{ signer.role }}
          <span v-if="signer.required" class="required-mark">*</span>
        </span>
        <span class="col-name">
          <el-input
            :model-value="signerStates[signer.id]?.name || ''"
            size="small"
            placeholder="签字人姓名"
            @input="(val: string) => updateName(signer.id, val)"
          />
        </span>
        <span class="col-date">
          <el-input
            :model-value="signerStates[signer.id]?.date || ''"
            size="small"
            placeholder="年 月 日"
            @input="(val: string) => updateDate(signer.id, val)"
          />
        </span>
      </div>
    </div>
    <div class="signing-hint">
      <p>* 为必填审批人，全部必填人员签字后视为完成。</p>
    </div>
  </div>
</template>

<style scoped>
.wp-popup-signing { padding: 8px 0; }

.signing-table__header {
  display: flex;
  align-items: center;
  padding: 8px 0;
  border-bottom: 2px solid #4b2d77;
  font-weight: 500;
  font-size: 12px;
  color: #4b2d77;
}

.signing-row {
  display: flex;
  align-items: center;
  padding: 10px 0;
  border-bottom: 1px solid #ebeef5;
  transition: background 0.2s;
}

.signing-row.is-signed { background: #f4f0fa; }

.col-role { width: 200px; min-width: 200px; font-size: 13px; color: #303133; }
.col-name { width: 160px; min-width: 160px; padding: 0 8px; }
.col-date { flex: 1; padding: 0 8px; }

.required-mark { color: #e6424a; font-weight: 700; margin-left: 2px; }

.signing-hint {
  margin-top: 12px;
  font-size: 12px;
  color: #909399;
  font-style: italic;
}
</style>
