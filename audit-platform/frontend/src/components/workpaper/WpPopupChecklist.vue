<script setup lang="ts">
/**
 * WpPopupChecklist — A1-12 重大事项决定程序的履行情况核查表
 *
 * - 14 条适用性判断列表：每条有 description(只读) + 是否适用(el-select) + 索引号(el-input)
 * - 头部：业务分类标记 + 是否首次承接
 * - 底部：重大业务咨询/分歧事项 自由文本区
 * - 根据 business_category 自动提示适用性
 * - Debounce 2s 自动保存
 */
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '@/services/apiProxy'

const props = defineProps<{
  wpCode: string
  wpId?: string
  projectId?: string
  projectInfo?: Record<string, any>
}>()

const emit = defineEmits<{
  (e: 'save'): void
  (e: 'completed'): void
}>()

// 14 条需提交专业技术委员会讨论的情形
const CHECKLIST_ITEMS = [
  { id: 'A1-12-001', seq: 1, description: '首次承接后的境内上市公司审计' },
  { id: 'A1-12-002', seq: 2, description: '首次承接的新三板挂牌公司审计' },
  { id: 'A1-12-003', seq: 3, description: '首次承接的大型国有企业审计' },
  { id: 'A1-12-004', seq: 4, description: '预计出具非标准审计报告' },
  { id: 'A1-12-005', seq: 5, description: '涉及重大关联方交易' },
  { id: 'A1-12-006', seq: 6, description: '持续经营重大不确定性' },
  { id: 'A1-12-007', seq: 7, description: '前后任注册会计师存在分歧' },
  { id: 'A1-12-008', seq: 8, description: '审计过程中发现重大舞弊' },
  { id: 'A1-12-009', seq: 9, description: '审计范围受到重大限制' },
  { id: 'A1-12-010', seq: 10, description: '需使用专家工作' },
  { id: 'A1-12-011', seq: 11, description: '会计政策重大变更' },
  { id: 'A1-12-012', seq: 12, description: '涉及重大法律诉讼' },
  { id: 'A1-12-013', seq: 13, description: '集团审计涉及组成部分重大事项' },
  { id: 'A1-12-014', seq: 14, description: '其他需提交讨论的重大事项' },
]

interface ItemState {
  conclusion: string | null  // 'Y' / 'N' / 'NA'
  wpRef: string             // 索引号
}

const itemStates = ref<Record<string, ItemState>>({})
const freeText = ref('')
const isFirstEngagement = ref(false)
const loading = ref(false)
const saveTimer = ref<ReturnType<typeof setTimeout> | null>(null)

const businessCategory = computed(() => props.projectInfo?.business_category || '')

// C类非特定情形显示提示
const showNotApplicableHint = computed(() => {
  return businessCategory.value === 'C'
})

function initStates() {
  for (const item of CHECKLIST_ITEMS) {
    if (!itemStates.value[item.id]) {
      itemStates.value[item.id] = { conclusion: null, wpRef: '' }
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
      if (r.item_id?.startsWith('A1-12-') && r.item_id !== 'A1-12-text') {
        itemStates.value[r.item_id] = {
          conclusion: r.conclusion || null,
          wpRef: r.wp_ref || '',
        }
      }
      if (r.item_id === 'A1-12-text') {
        freeText.value = r.remark || ''
      }
      if (r.item_id === 'A1-12-header') {
        isFirstEngagement.value = r.conclusion === 'Y'
      }
    }
  } catch { /* ignore load errors */ }
  finally { loading.value = false }
}

function scheduleSave() {
  if (saveTimer.value) clearTimeout(saveTimer.value)
  saveTimer.value = setTimeout(doSave, 2000)
}

async function doSave() {
  if (!props.wpId || !props.projectId) return
  const items: any[] = CHECKLIST_ITEMS.map(item => ({
    item_id: item.id,
    conclusion: itemStates.value[item.id]?.conclusion || null,
    remark: null,
    wp_ref: itemStates.value[item.id]?.wpRef || null,
  }))
  // Free text area
  items.push({
    item_id: 'A1-12-text',
    conclusion: null,
    remark: freeText.value || null,
    wp_ref: null,
  })
  // Header info (first engagement)
  items.push({
    item_id: 'A1-12-header',
    conclusion: isFirstEngagement.value ? 'Y' : 'N',
    remark: null,
    wp_ref: null,
  })
  try {
    await api.put(`/api/workpapers/${props.wpId}/checklist-responses`, {
      project_id: props.projectId,
      items,
    })
    emit('save')
    // Check if all completed
    const allDone = CHECKLIST_ITEMS.every(item => itemStates.value[item.id]?.conclusion)
    if (allDone) emit('completed')
  } catch (err: any) {
    const msg = err?.message || ''
    if (msg !== 'canceled' && err?.code !== 'ERR_CANCELED') {
      ElMessage.error('保存失败')
    }
  }
}

function updateConclusion(id: string, val: string) {
  itemStates.value[id].conclusion = val || null
  scheduleSave()
}

function updateWpRef(id: string, val: string) {
  itemStates.value[id].wpRef = val
  scheduleSave()
}

function updateFreeText(val: string) {
  freeText.value = val
  scheduleSave()
}

function updateFirstEngagement(val: boolean) {
  isFirstEngagement.value = val
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
  <div class="wp-popup-checklist" v-loading="loading">
    <!-- 头部：业务分类 + 是否首次承接 -->
    <div class="checklist-header">
      <div class="header-field">
        <span class="header-label">业务分类：</span>
        <el-tag
          :type="businessCategory === 'A' ? 'danger' : businessCategory === 'B' ? 'warning' : 'info'"
          size="small"
        >
          {{ businessCategory || '未设定' }}类
        </el-tag>
      </div>
      <div class="header-field">
        <span class="header-label">是否首次承接：</span>
        <el-switch
          :model-value="isFirstEngagement"
          active-text="是"
          inactive-text="否"
          @change="(val: boolean) => updateFirstEngagement(val)"
        />
      </div>
    </div>

    <!-- C类提示 -->
    <el-alert
      v-if="showNotApplicableHint"
      type="warning"
      :closable="false"
      show-icon
      class="checklist-alert"
    >
      <template #title>
        本项目为C类业务，如不存在需提交专业技术委员会讨论的特定情形，本表不适用
      </template>
    </el-alert>

    <!-- 14 条核查列表 -->
    <div class="checklist-section-title">一、需提交专业技术委员会讨论的情形</div>
    <el-table :data="CHECKLIST_ITEMS" border size="small" class="checklist-table">
      <el-table-column label="序号" width="50" align="center">
        <template #default="{ row }">{{ row.seq }}</template>
      </el-table-column>
      <el-table-column label="情形描述" min-width="280">
        <template #default="{ row }">{{ row.description }}</template>
      </el-table-column>
      <el-table-column label="是否适用" width="120" align="center">
        <template #default="{ row }">
          <el-select
            :model-value="itemStates[row.id]?.conclusion || ''"
            size="small"
            placeholder="请选择"
            style="width: 90px"
            @change="(val: string) => updateConclusion(row.id, val)"
          >
            <el-option label="是" value="Y" />
            <el-option label="否" value="N" />
            <el-option label="不适用" value="NA" />
          </el-select>
        </template>
      </el-table-column>
      <el-table-column label="索引号" width="120" align="center">
        <template #default="{ row }">
          <el-input
            :model-value="itemStates[row.id]?.wpRef || ''"
            size="small"
            placeholder="索引号"
            @input="(val: string) => updateWpRef(row.id, val)"
          />
        </template>
      </el-table-column>
    </el-table>

    <!-- 底部自由文本区 -->
    <div class="checklist-section-title" style="margin-top: 16px">
      二、提交讨论的重大业务咨询或分歧事项
    </div>
    <el-input
      :model-value="freeText"
      type="textarea"
      :rows="4"
      placeholder="如有重大业务咨询或分歧事项，请在此填写..."
      @input="updateFreeText"
    />

    <!-- 底部注释说明 -->
    <div class="checklist-footer-note">
      注：本表仅适用于审计业务。适用于A、B类业务以及执行A、B类复核流程的C类业务，以及存在专业分歧需专委会审核的C类业务。
    </div>
  </div>
</template>

<style scoped>
.wp-popup-checklist {
  padding: 8px 0;
}

.checklist-header {
  display: flex;
  align-items: center;
  gap: 24px;
  padding: 12px 16px;
  background-color: #f4f0fa;
  border-radius: 6px;
  margin-bottom: 12px;
}

.header-field {
  display: flex;
  align-items: center;
  gap: 8px;
}

.header-label {
  font-size: 13px;
  color: #606266;
}

.checklist-alert {
  margin-bottom: 12px;
}

.checklist-section-title {
  font-size: 14px;
  font-weight: 600;
  color: #4b2d77;
  margin-bottom: 8px;
}

.checklist-table {
  margin-bottom: 0;
}

.checklist-footer-note {
  margin-top: 12px;
  padding: 8px 12px;
  font-size: 12px;
  color: #909399;
  background-color: #f5f7fa;
  border-radius: 4px;
  line-height: 1.6;
}
</style>
