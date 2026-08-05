<script setup lang="ts">
/**
 * GtE0SendListE05 — 应付银行承兑汇票发函记录表E0-5 专属 HTML 组件
 *
 * componentType: confirmation-send-list-e05
 */
import { ref, watch, onMounted } from 'vue'
import { SEND_LIST_SPECS } from './sendListSpec'
import { useSendListData } from './useSendListData'
import SendListTable from './SendListTable.vue'

const props = defineProps<{
  htmlData: any
  projectId: string
  wpId: string
  isReadonly?: boolean
}>()

const emit = defineEmits<{
  (e: 'save', sheetName: string, payload: any): void
}>()

const spec = SEND_LIST_SPECS.e05
const isReadonly = ref(props.isReadonly ?? false)
const htmlDataRef = ref(props.htmlData)

watch(() => props.htmlData, (v) => { htmlDataRef.value = v })
watch(() => props.isReadonly, (v) => { isReadonly.value = v ?? false })

const {
  rows, conclusion, visibleColumns, hasUnmappedCells,
  addRow, removeRow, moveRow, toggleColumn, buildPayload, loadFromHtmlData,
} = useSendListData(spec, { htmlData: htmlDataRef, isReadonly })

onMounted(() => { loadFromHtmlData(props.htmlData) })
watch(() => props.htmlData, (data) => { loadFromHtmlData(data) })

function handleSave() {
  emit('save', spec.sheetName, buildPayload())
}
</script>

<template>
  <div class="e0-send-list e0-send-list-e05">
    <el-alert v-if="hasUnmappedCells" type="info" :closable="false" show-icon style="margin-bottom: 12px">
      存在未识别的历史列数据，已保留
    </el-alert>

    <SendListTable
      :spec="spec" :rows="rows" :visible-columns="visibleColumns"
      :is-readonly="isReadonly"
      @add-row="addRow" @remove-row="removeRow"
      @move-row="moveRow" @toggle-column="toggleColumn" @save="handleSave"
    />

    <el-card shadow="never" style="margin-top: 16px">
      <template #header><span>审计说明</span></template>
      <el-input v-model="conclusion.audit_explanation" type="textarea"
        :autosize="{ minRows: 3 }" :disabled="isReadonly" placeholder="请填写审计说明" @blur="handleSave" />
    </el-card>

    <el-card shadow="never" style="margin-top: 12px">
      <template #header><span>审计结论</span></template>
      <el-input v-model="conclusion.overall_conclusion" type="textarea"
        :autosize="{ minRows: 3 }" :disabled="isReadonly" placeholder="请填写审计结论" @blur="handleSave" />
    </el-card>
  </div>
</template>

<style scoped>
.e0-send-list { font-size: 13px; }
</style>
