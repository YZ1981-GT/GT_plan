<script setup lang="ts">
/**
 * WpPopupSigning — A1-11 业务报告签发流转控制表
 *
 * 签字审批链（按 business_category 区分）：
 * - 所有项目(B/C类): 项目经理 → 合伙人 (2 levels)
 * - A类项目: + 独立复核合伙人 + EQCR技术复核人 (4 levels)
 *
 * 每行: name(el-input) + signature(el-checkbox) + date(el-date-picker)
 * Data: checklist_responses item_id "A1-11-sign-pm", "A1-11-sign-partner",
 *       "A1-11-sign-irp", "A1-11-sign-eqcr"
 */
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '@/services/apiProxy'

const props = defineProps<{
  wpCode: string
  wpId?: string
  projectId?: string
  projectInfo?: Record<string, any>
  // GtWpRenderer 标准 props（兼容独立渲染模式）
  sheetName?: string
  schema?: Record<string, any>
  htmlData?: Record<string, any>
  readonly?: boolean
  year?: number
}>()

const emit = defineEmits<{
  (e: 'save'): void
  (e: 'completed'): void
}>()

interface SignRow {
  id: string
  role: string
  label: string
  onlyA: boolean
}

const ALL_SIGN_ROWS: SignRow[] = [
  { id: 'A1-11-sign-pm', role: 'pm', label: '项目经理', onlyA: false },
  { id: 'A1-11-sign-partner', role: 'partner', label: '合伙人', onlyA: false },
  { id: 'A1-11-sign-irp', role: 'irp', label: '独立复核合伙人', onlyA: true },
  { id: 'A1-11-sign-eqcr', role: 'eqcr', label: 'EQCR技术复核人', onlyA: true },
]

interface SignState {
  name: string
  signed: boolean
  date: string
}

const signStates = ref<Record<string, SignState>>({})
const loading = ref(false)
const saveTimer = ref<ReturnType<typeof setTimeout> | null>(null)

const businessCategory = computed(() => props.projectInfo?.business_category || '')
const isTypeA = computed(() => businessCategory.value === 'A')

const visibleRows = computed(() => {
  if (isTypeA.value) return ALL_SIGN_ROWS
  return ALL_SIGN_ROWS.filter(r => !r.onlyA)
})

function initStates() {
  for (const row of ALL_SIGN_ROWS) {
    if (!signStates.value[row.id]) {
      signStates.value[row.id] = { name: '', signed: false, date: '' }
    }
  }
}

async function loadData() {
  if (!props.wpId) return
  loading.value = true
  try {
    const res = await api.get(`/api/workpapers/${props.wpId}/checklist-responses`)
    const responses = Array.isArray(res) ? res : (res?.data ?? [])
    for (const r of responses) {
      if (r.item_id?.startsWith('A1-11-sign-')) {
        signStates.value[r.item_id] = {
          name: r.remark || '',
          signed: r.conclusion === 'Y',
          date: r.wp_ref || '',
        }
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
  const items = ALL_SIGN_ROWS.map(row => ({
    item_id: row.id,
    conclusion: signStates.value[row.id]?.signed ? 'Y' : null,
    remark: signStates.value[row.id]?.name || null,
    wp_ref: signStates.value[row.id]?.date || null,
  }))
  try {
    await api.put(`/api/workpapers/${props.wpId}/checklist-responses`, {
      project_id: props.projectId,
      items,
    })
    emit('save')
    // Check completion: required rows all signed
    const requiredRows = visibleRows.value
    const allDone = requiredRows.every(r => signStates.value[r.id]?.signed)
    if (allDone) emit('completed')
  } catch (err: any) {
    const msg = err?.message || ''
    if (msg !== 'canceled' && err?.code !== 'ERR_CANCELED') {
      ElMessage.error('保存失败')
    }
  }
}

function updateName(id: string, val: string) {
  signStates.value[id].name = val
  scheduleSave()
}

function updateSigned(id: string, val: boolean) {
  signStates.value[id].signed = val
  scheduleSave()
}

function updateDate(id: string, val: string) {
  signStates.value[id].date = val || ''
  scheduleSave()
}

onMounted(() => {
  initStates()
  loadData()
})

onBeforeUnmount(() => {
  if (saveTimer.value) {
    clearTimeout(saveTimer.value)
    doSave()
  }
})
</script>

<template>
  <div class="wp-popup-signing" v-loading="loading">
    <!-- 非A类提示 -->
    <el-alert
      v-if="!isTypeA"
      type="info"
      :closable="false"
      show-icon
      class="signing-alert"
    >
      <template #title>
        本项目为{{ businessCategory || 'B/C' }}类，仅需项目经理和合伙人签字
      </template>
    </el-alert>

    <!-- 签字表格 -->
    <el-table :data="visibleRows" border size="small" class="signing-table">
      <el-table-column label="审批人" width="140" align="center">
        <template #default="{ row }">
          <span class="role-label">{{ row.label }}</span>
        </template>
      </el-table-column>
      <el-table-column label="姓名" min-width="140">
        <template #default="{ row }">
          <el-input
            :model-value="signStates[row.id]?.name || ''"
            size="small"
            placeholder="请输入姓名"
            @input="(val: string) => updateName(row.id, val)"
          />
        </template>
      </el-table-column>
      <el-table-column label="签字" width="80" align="center">
        <template #default="{ row }">
          <el-checkbox
            :model-value="signStates[row.id]?.signed || false"
            @change="(val: boolean) => updateSigned(row.id, val)"
          >
            已签字
          </el-checkbox>
        </template>
      </el-table-column>
      <el-table-column label="日期" width="160" align="center">
        <template #default="{ row }">
          <el-date-picker
            :model-value="signStates[row.id]?.date || ''"
            type="date"
            size="small"
            placeholder="选择日期"
            value-format="YYYY-MM-DD"
            style="width: 130px"
            @update:model-value="(val: string) => updateDate(row.id, val)"
          />
        </template>
      </el-table-column>
    </el-table>
  </div>
</template>

<style scoped>
.wp-popup-signing {
  padding: 8px 0;
}

.signing-alert {
  margin-bottom: 12px;
}

.signing-table {
  width: 100%;
}

.role-label {
  font-size: 13px;
  font-weight: 500;
  color: #4b2d77;
}
</style>
