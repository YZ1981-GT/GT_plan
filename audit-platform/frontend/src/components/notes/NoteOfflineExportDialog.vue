<template>
  <el-dialog
    v-model="visible"
    title="导出附注离线编辑包"
    width="600px"
    :close-on-click-modal="false"
  >
    <!-- 导出范围 -->
    <el-form label-width="100px">
      <el-form-item label="导出范围">
        <el-radio-group v-model="exportScope">
          <el-radio value="all">全部章节</el-radio>
          <el-radio value="with_data">仅有数据章节</el-radio>
          <el-radio value="custom">自定义勾选</el-radio>
        </el-radio-group>
      </el-form-item>

      <!-- 章节多选树 -->
      <el-form-item v-if="exportScope === 'custom'" label="选择章节">
        <el-tree
          ref="treeRef"
          :data="sectionTree"
          show-checkbox
          node-key="section_id"
          :default-checked-keys="defaultChecked"
          :props="{ label: 'title', children: 'children' }"
          style="max-height: 300px; overflow-y: auto; width: 100%"
        />
      </el-form-item>

      <!-- 导出内容选项 -->
      <el-form-item label="导出内容">
        <el-checkbox v-model="options.includeFormulas">包含公式表达式</el-checkbox>
        <el-checkbox v-model="options.includeProvenance">包含数据源溯源</el-checkbox>
      </el-form-item>

      <!-- 加密选项 -->
      <el-form-item label="文件加密">
        <el-switch v-model="options.encrypt" />
        <el-input
          v-if="options.encrypt"
          v-model="options.password"
          type="password"
          placeholder="设置密码（通过其他渠道告知接收方）"
          style="margin-top: 8px; width: 100%"
          show-password
        />
      </el-form-item>
    </el-form>

    <template #footer>
      <el-button @click="visible = false">取消</el-button>
      <el-button type="primary" :loading="exporting" @click="handleExport">
        导出
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '@/services/apiProxy'
import { handleApiError } from '@/utils/errorHandler'

interface Props {
  modelValue: boolean
  projectId: string
  year: number
  sections: Array<{ section_id: string; title: string; has_data?: boolean }>
}

const props = defineProps<Props>()
const emit = defineEmits<{ 'update:modelValue': [val: boolean] }>()

const visible = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v),
})

const treeRef = ref()
const exportScope = ref<'all' | 'with_data' | 'custom'>('all')
const exporting = ref(false)
const options = ref({
  includeFormulas: true,
  includeProvenance: true,
  encrypt: false,
  password: '',
})

const sectionTree = computed(() =>
  props.sections.map(s => ({ section_id: s.section_id, title: s.title }))
)

const defaultChecked = computed(() => props.sections.map(s => s.section_id))

async function handleExport() {
  exporting.value = true
  try {
    let sectionIds: string[] | undefined
    if (exportScope.value === 'custom' && treeRef.value) {
      sectionIds = treeRef.value.getCheckedKeys()
    } else if (exportScope.value === 'with_data') {
      sectionIds = props.sections.filter(s => s.has_data).map(s => s.section_id)
    }

    const resp = await api.post(
      `/api/disclosure-notes/${props.projectId}/${props.year}/offline-export`,
      {
        section_ids: sectionIds,
        include_formulas: options.value.includeFormulas,
        include_provenance: options.value.includeProvenance,
        password: options.value.encrypt ? options.value.password : undefined,
      },
      { responseType: 'blob' }
    )

    // Download file
    const blob = new Blob([resp as any], {
      type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `附注离线编辑包_${props.year}.xlsx`
    a.click()
    URL.revokeObjectURL(url)

    ElMessage.success('导出成功')
    visible.value = false
  } catch (e: any) {
    handleApiError(e, '导出')
  } finally {
    exporting.value = false
  }
}
</script>
