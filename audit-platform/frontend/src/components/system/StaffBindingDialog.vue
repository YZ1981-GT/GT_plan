<template>
  <el-dialog
    append-to-body
    :model-value="modelValue"
    :title="`绑定人员档案：${user?.username || ''}`"
    width="480px"
    @update:model-value="emit('update:modelValue', $event)"
    @open="onOpen"
    @closed="reset"
  >
    <p class="gt-staff-binding-hint">
      一个账号只能绑定一份人员档案。绑定后，该人员已有的项目委派对此账号生效，并补齐对应的项目成员。
    </p>
    <el-select
      :model-value="selectedStaff?.id || ''"
      filterable
      remote
      clearable
      reserve-keyword
      :remote-method="search"
      :loading="searching"
      placeholder="输入姓名或工号搜索未绑定的人员档案"
      no-data-text="没有可绑定的人员档案"
      style="width: 100%"
      @update:model-value="selectStaff"
    >
      <el-option
        v-for="item in options"
        :key="item.id"
        :value="item.id"
        :label="optionLabel(item)"
      />
    </el-select>
    <template #footer>
      <el-button @click="emit('update:modelValue', false)">取消</el-button>
      <el-button type="primary" :loading="saving" :disabled="!selectedStaff" @click="submit">
        确认绑定
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  bindStaffToUser,
  searchUnboundStaff,
  type StaffBindingResult,
  type UnboundStaffOption,
} from '@/services/staffBindingApi'

const props = defineProps<{
  modelValue: boolean
  user: { id: string; username: string } | null
}>()
const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  bound: [result: StaffBindingResult]
  /** 绑定被拒（档案或账号已被别处绑定、已停用 / 离职等）：父页面应重读绑定列表 */
  stale: []
}>()

const options = ref<UnboundStaffOption[]>([])
// 选中时记下档案本身：之后再搜索会替换候选列表，不能再从列表里反查。
const selectedStaff = ref<UnboundStaffOption | null>(null)
const searching = ref(false)
const saving = ref(false)
let searchSeq = 0

function optionLabel(item: UnboundStaffOption): string {
  const extras = [item.employee_no, item.department].filter(Boolean).join(' · ')
  return extras ? `${item.name}（${extras}）` : item.name
}

function selectStaff(id: string | undefined) {
  selectedStaff.value = options.value.find(item => item.id === id) || null
}

async function search(keyword: string) {
  const seq = ++searchSeq
  searching.value = true
  try {
    const items = await searchUnboundStaff(keyword || '')
    // 只采用最后一次输入的结果，避免慢请求覆盖新关键字。
    if (seq === searchSeq) options.value = items
  } catch {
    if (seq === searchSeq) options.value = []
  } finally {
    if (seq === searchSeq) searching.value = false
  }
}

function reset() {
  searchSeq += 1
  options.value = []
  selectedStaff.value = null
  searching.value = false
  saving.value = false
}

function onOpen() {
  // closed 事件要等关闭动画结束才发；打开时再清一次，不带上一个账号的选择。
  reset()
  void search('')
}

async function submit() {
  const user = props.user
  const staff = selectedStaff.value
  if (!user || !staff || saving.value) return
  try {
    await ElMessageBox.confirm(
      `确认把人员档案「${optionLabel(staff)}」绑定到账号「${user.username}」？`,
      '确认绑定人员档案',
      { type: 'warning', confirmButtonText: '确认绑定', cancelButtonText: '取消' },
    )
  } catch {
    return
  }
  saving.value = true
  try {
    const result = await bindStaffToUser(user.id, staff.id)
    const projects = result.project_count || 0
    ElMessage.success(projects ? `已绑定，该人员在 ${projects} 个项目的委派已生效` : '已绑定人员档案')
    emit('bound', result)
    emit('update:modelValue', false)
  } catch {
    // 失败原因（如档案已被其他账号绑定）由请求拦截器展示；候选与页面上的绑定状态可能已过期。
    selectedStaff.value = null
    void search('')
    emit('stale')
  } finally {
    saving.value = false
  }
}
</script>

<style scoped>
.gt-staff-binding-hint {
  margin: 0 0 12px;
  color: var(--el-text-color-secondary);
  font-size: 12px;
  line-height: 1.6;
}
</style>
