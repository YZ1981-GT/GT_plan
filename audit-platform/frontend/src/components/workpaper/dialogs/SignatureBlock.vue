<template>
  <div class="gt-sig-block">
    <span v-if="signed && signature" class="gt-sig-info">
      ✅ 已签字：{{ signature.signer_name || roleLabel }} · {{ signature.signed_at?.slice(0, 19) || '' }}
    </span>
    <el-button
      v-else
      size="small"
      type="primary"
      plain
      :loading="loading"
      :disabled="readonly"
      @click="onSign"
    >✍️ {{ roleLabel }} 签字</el-button>
  </div>
</template>

<script setup lang="ts">
/**
 * SignatureBlock — 签字接入 signature_service（Sprint 2 Task 2.27 + 2.28）
 *
 * 调用 POST /api/signatures/sign 创建签字记录，object_type='workpaper_sheet'。
 * 签字成功后 emit eventBus 'signature:created'，触发 useProcedureStatus 刷新。
 */
import { ref, computed, onMounted, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { eventBus } from '@/utils/eventBus'
import { api } from '@/services/apiProxy'
import { confirmSign } from '@/utils/confirm'

interface Props {
  projectId: string
  objectType: string
  objectId: string
  /** 签字角色: 'auditor' | 'cashier' | 'manager' 等 */
  role: string
  /** 是否已签 */
  signed?: boolean
  readonly?: boolean
}
const props = withDefaults(defineProps<Props>(), { signed: false, readonly: false })
const emit = defineEmits<{ signed: [signature: any] }>()

const loading = ref(false)
const signature = ref<any>(null)

const roleLabel = computed(() => {
  switch (props.role) {
    case 'auditor':
      return '审计员'
    case 'cashier':
      return '出纳'
    case 'manager':
      return '项目经理'
    case 'partner':
      return '合伙人'
    default:
      return '签字人'
  }
})

async function onSign() {
  try {
    await confirmSign(`${roleLabel.value}签字`, {
      userName: roleLabel.value,
      projectName: props.objectId.split(':')[0] || '',
    })
  } catch {
    return
  }
  loading.value = true
  try {
    const payload = {
      object_type: props.objectType,
      object_id: props.objectId,
      role: props.role,
    }
    const data: any = await api.post('/api/signatures/sign', payload)
    signature.value = data
    emit('signed', data)
    ElMessage.success(`${roleLabel.value} 已签字`)
    // E1 Sprint 2 Task 2.29: 签字状态联动 procedure_status
    eventBus.emit('signature:created', {
      projectId: props.projectId,
      objectType: props.objectType,
      objectId: props.objectId,
      signerId: data?.signer_id || data?.signer || '',
    })
  } catch (err: any) {
    ElMessage.error('签字失败：' + (err?.message || '请稍后重试'))
  } finally {
    loading.value = false
  }
}

async function loadSignature() {
  try {
    const data: any = await api.get(`/api/signatures/${props.objectType}/${props.objectId}`)
    const list = Array.isArray(data) ? data : data?.items || []
    signature.value = list.find((s: any) => s.role === props.role) || null
  } catch {
    signature.value = null
  }
}

onMounted(loadSignature)
watch(() => [props.objectType, props.objectId, props.role], loadSignature)
</script>

<style scoped>
.gt-sig-block {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}
.gt-sig-info {
  color: var(--gt-color-success, #67c23a);
  font-size: 12px;
}
</style>
