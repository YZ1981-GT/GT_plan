<!--
  WorkpaperTrimDialog — 底稿裁剪确认弹窗

  按循环分组展示模板列表，根据业务分类自动预选，用户可覆盖。
  确认后 emit selected 列表。

  Requirements: 3.1, 3.2, 3.3, 3.4
-->
<template>
  <el-dialog
    :model-value="modelValue"
    title="确认生成底稿范围"
    width="720px"
    @update:model-value="$emit('update:modelValue', $event)"
  >
    <div class="wp-trim-dialog">
      <el-alert
        v-if="loadError"
        type="error"
        :title="loadError"
        :closable="false"
        show-icon
        class="wp-trim-dialog__alert"
      />
      <el-alert
        v-else-if="trimmedCount > 0"
        type="info"
        :title="`${trimmedCount} 个底稿已在程序裁剪中标为不执行，不会生成；如需编制请先在程序裁剪中恢复执行`"
        :closable="false"
        show-icon
        class="wp-trim-dialog__alert"
      />
      <!-- 工具栏 -->
      <div class="wp-trim-dialog__toolbar">
        <el-button size="small" @click="selectAll">全选</el-button>
        <el-button size="small" @click="deselectAll">全不选</el-button>
        <span class="wp-trim-dialog__count">
          已选 {{ selectedCodes.length }} / {{ allTemplates.length }}
        </span>
      </div>

      <!-- 树形按循环分组 -->
      <el-tree
        ref="treeRef"
        :data="treeData"
        show-checkbox
        node-key="id"
        :default-checked-keys="defaultChecked"
        :props="{ label: 'label', children: 'children', disabled: 'disabled' }"
        @check="onCheck"
      />
    </div>

    <template #footer>
      <el-button @click="$emit('update:modelValue', false)">取消</el-button>
      <el-button type="primary" @click="onConfirm">
        确认生成（{{ selectedCodes.length }} 项）
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import { api } from '@/services/apiProxy'

interface TemplateItem {
  wp_code: string
  wp_name: string
  cycle: string
  applicable: boolean
  applicable_reason?: string
  /** 已在程序裁剪中标为不执行（后端保留范围判定，子表 / 程序表跟随科目） */
  trimmed?: boolean
  /** 决定它的程序行编码（如 H3-2 跟随 H3） */
  trimmed_by?: string | null
}

interface TreeNode {
  id: string
  label: string
  children?: TreeNode[]
  disabled?: boolean
}

const props = defineProps<{
  modelValue: boolean
  projectId: string
}>()

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  confirm: [selectedCodes: string[]]
}>()

const treeRef = ref<any>(null)
const allTemplates = ref<TemplateItem[]>([])
const selectedCodes = ref<string[]>([])
const loadError = ref('')

/** 可生成 = 未被程序裁剪；默认再按业务分类预选 */
const selectable = computed(() => allTemplates.value.filter((t) => !t.trimmed))
const trimmedCount = computed(() => allTemplates.value.length - selectable.value.length)

function trimLabel(t: TemplateItem): string {
  if (!t.trimmed) return ''
  return t.trimmed_by && t.trimmed_by !== t.wp_code
    ? `（已裁剪：跟随 ${t.trimmed_by}）`
    : '（已裁剪）'
}

// 循环名称映射
const CYCLE_NAMES: Record<string, string> = {
  A: '完成阶段', B: '计划了解', C: '控制测试',
  D: '销售收入', E: '货币资金', F: '采购存货',
  G: '投资', H: '固定资产', I: '无形资产',
  J: '职工薪酬', K: '管理费用', L: '筹资',
  M: '股东权益', N: '税费', S: '专项',
}

// 构建树形数据
const treeData = computed<TreeNode[]>(() => {
  const groups: Record<string, TemplateItem[]> = {}
  for (const t of allTemplates.value) {
    const cycle = t.cycle || t.wp_code?.[0] || '其他'
    if (!groups[cycle]) groups[cycle] = []
    groups[cycle].push(t)
  }

  return Object.entries(groups).map(([cycle, items]) => ({
    id: `__group__:${cycle}`,
    label: `${cycle} ${CYCLE_NAMES[cycle] || ''}（${items.length}）`,
    children: items.map((t) => ({
      id: t.wp_code,
      label: `${t.wp_code} ${t.wp_name}${trimLabel(t)}${t.applicable ? '' : ' ⚠️' + (t.applicable_reason || '')}`,
      disabled: !!t.trimmed,
    })),
  }))
})

// 默认预选：applicable=true 且未被程序裁剪的
const defaultChecked = computed(() =>
  selectable.value.filter((t) => t.applicable).map((t) => t.wp_code),
)

async function loadTemplates() {
  loadError.value = ''
  try {
    // 失败原因在弹窗里显示（_silent：不让全局拦截器再弹一次）
    const list = await api.get<TemplateItem[]>(
      '/api/workpapers/template-list',
      { params: { project_id: props.projectId }, _silent: true } as any,
    )
    allTemplates.value = list
    selectedCodes.value = list.filter((t) => t.applicable && !t.trimmed).map((t) => t.wp_code)
  } catch (e: any) {
    allTemplates.value = []
    selectedCodes.value = []
    const detail = e?.response?.data?.detail
    loadError.value = `模板列表加载失败：${detail?.message || (typeof detail === 'string' ? detail : '') || '请稍后重试'}`
  }
}

function selectAll() {
  const codes = selectable.value.map((t) => t.wp_code)
  treeRef.value?.setCheckedKeys(codes)
  selectedCodes.value = codes
}

function deselectAll() {
  treeRef.value?.setCheckedKeys([])
  selectedCodes.value = []
}

function onCheck() {
  const checked = treeRef.value?.getCheckedKeys(true) || []
  // 过滤掉组节点 key
  selectedCodes.value = checked.filter((k: string) => !k.startsWith('__group__:'))
}

function onConfirm() {
  emit('confirm', selectedCodes.value)
  emit('update:modelValue', false)
}

watch(() => props.modelValue, (v) => {
  if (v) loadTemplates()
})

onMounted(() => {
  if (props.modelValue) loadTemplates()
})
</script>

<style scoped>
.wp-trim-dialog__toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
}

.wp-trim-dialog__alert {
  margin-bottom: 12px;
}

.wp-trim-dialog__count {
  margin-left: auto;
  font-size: var(--wp-font-size, 13px);
  color: #909399;
}
</style>
