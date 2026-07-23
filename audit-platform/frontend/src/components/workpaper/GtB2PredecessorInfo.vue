<script setup lang="ts">
/**
 * GtB2PredecessorInfo — B2 前任沟通基础信息录入
 *
 * 录入"前任会计师事务所名称 + 项目组联系方式"，保存到项目级
 * checklist_responses(item_id=B2-predecessor-info, remark=JSON)。
 * 后端 _prefill_word_template 打开 B2 系列信函时据此填充中文【】占位符
 * 及信函尾部联系方式区。
 *
 * ⚠️ 需在打开信函前录入，否则信函占位符保留待手填。
 */
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '@/services/apiProxy'

const props = defineProps<{
  wpId: string
  projectId?: string
  readonly?: boolean
}>()

const ITEM_ID = 'B2-predecessor-info'

interface PredecessorInfo {
  firmName: string
  contactPerson: string
  contactPhone: string
  fax: string
  address: string
  zipCode: string
}

const form = ref<PredecessorInfo>({
  firmName: '',
  contactPerson: '',
  contactPhone: '',
  fax: '',
  address: '',
  zipCode: '',
})

const loading = ref(false)
const saving = ref(false)

async function load() {
  if (!props.wpId) return
  loading.value = true
  try {
    const res = await api.get(`/api/workpapers/${props.wpId}/checklist-responses`)
    const list: any[] = Array.isArray(res) ? res : (res?.data ?? [])
    const row = list.find((r) => r.item_id === ITEM_ID)
    if (row?.remark) {
      try {
        const parsed = JSON.parse(row.remark)
        if (parsed && typeof parsed === 'object') {
          form.value = { ...form.value, ...parsed }
        }
      } catch { /* ignore malformed */ }
    }
  } catch {
    /* 无数据时保持空表单 */
  } finally {
    loading.value = false
  }
}

async function save() {
  if (props.readonly || !props.wpId) return
  saving.value = true
  try {
    await api.put(`/api/workpapers/${props.wpId}/checklist-responses`, {
      project_id: props.projectId || undefined,
      items: [{ item_id: ITEM_ID, conclusion: null, remark: JSON.stringify(form.value) }],
    })
    ElMessage.success('前任沟通基础信息已保存')
  } catch {
    ElMessage.error('保存失败，请重试')
  } finally {
    saving.value = false
  }
}

onMounted(load)
</script>

<template>
  <div class="gt-b2-pred" v-loading="loading">
    <el-alert
      type="warning"
      :closable="false"
      show-icon
      class="gt-b2-pred__tip"
    >
      <template #title>
        请在打开 B2 系列沟通函（B2-1/3/6/8/11/12）<b>之前</b>录入本信息。
        系统将据此自动填充信函中的「被审计单位名称 / 前任会计师事务所名称 / 联系方式」等占位符；
        若未录入，信函占位符将保留待手工填写。
      </template>
    </el-alert>

    <el-card shadow="never" class="gt-b2-pred__card">
      <template #header>
        <span class="gt-b2-pred__title">前任沟通基础信息</span>
      </template>

      <el-form label-width="130px" :disabled="readonly">
        <el-form-item label="前任会计师事务所名称" required>
          <el-input
            v-model="form.firmName"
            placeholder="如：XX会计师事务所（特殊普通合伙）"
            clearable
          />
        </el-form-item>

        <el-divider content-position="left">项目组联系方式（填入信函尾部）</el-divider>

        <el-form-item label="联系人">
          <el-input v-model="form.contactPerson" placeholder="项目组联系人姓名" clearable />
        </el-form-item>
        <el-form-item label="联系电话">
          <el-input v-model="form.contactPhone" placeholder="固话或手机" clearable />
        </el-form-item>
        <el-form-item label="传真">
          <el-input v-model="form.fax" clearable />
        </el-form-item>
        <el-form-item label="地址">
          <el-input v-model="form.address" clearable />
        </el-form-item>
        <el-form-item label="邮编">
          <el-input v-model="form.zipCode" clearable />
        </el-form-item>

        <el-form-item v-if="!readonly">
          <el-button type="primary" :loading="saving" @click="save">保存基础信息</el-button>
        </el-form-item>
      </el-form>
    </el-card>
  </div>
</template>

<style scoped>
.gt-b2-pred { padding: 4px; }
.gt-b2-pred__tip { margin-bottom: 12px; }
.gt-b2-pred__card { max-width: 640px; }
.gt-b2-pred__title { font-weight: 600; color: var(--gt-color-primary, #4b2d77); }
</style>
