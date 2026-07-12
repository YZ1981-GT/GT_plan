<template>
  <div class="h8-tab-lease-identification">
    <!-- 方法论上下文 -->
    <div class="methodology-context">
      <p>CAS21第4-13条：租赁识别三要素——①已识别资产 ②取得控制权（主导使用+获得利益）③供应商无实质替换权。每份租赁合同逐项判断。</p>
    </div>

    <!-- 索引 + 行数 -->
    <div class="h8-tab-toolbar">
      <GtIndexChip value="wp:H8-4" />
      <el-tag size="small" type="info">共 {{ records.length }} 份合同</el-tag>
    </div>

    <!-- 顶部统计 -->
    <div class="stats-bar">
      <el-tag type="info" size="small">合同总数：{{ records.length }}</el-tag>
      <el-tag type="success" size="small">已完成：{{ completedCount }}</el-tag>
      <el-tag type="primary" size="small">识别为租赁：{{ leaseCount }}</el-tag>
      <div class="stats-actions">
        <el-button v-if="!isReadonly" size="small" type="primary" @click="handleAddRecord">+ 新增合同判断</el-button>
        <el-button size="small" type="primary" plain @click="$emit('open-ai', 'lease-identification')">AI 辅助</el-button>
        <el-button size="small" @click="$emit('open-review', 'lease-identification')">复核</el-button>
      </div>
    </div>

    <!-- 合同列表（段落型渲染） -->
    <div v-if="records.length === 0" class="empty-state">
      <el-empty description="暂无租赁识别记录，请点击“+ 新增合同判断”开始" />
    </div>

    <div v-for="record in records" :key="record.recordId" class="identification-card">
      <el-card shadow="never">
        <template #header>
          <div class="card-header">
            <span class="contract-label">合同号：{{ record.contractNo }}</span>
            <div class="card-actions">
              <el-tag v-if="record.finalConclusion" :type="record.finalConclusion === '是' ? 'success' : record.finalConclusion === '否' ? 'danger' : 'info'" size="small">
                {{ record.finalConclusion === '是' ? '属于租赁' : record.finalConclusion === '否' ? '不属于租赁' : '不适用' }}
              </el-tag>
              <el-button v-if="!isReadonly" type="danger" link size="small" @click="handleDeleteRecord(record.recordId)">删除</el-button>
            </div>
          </div>
        </template>

        <!-- 逐项判断 -->
        <div class="items-grid">
          <div v-for="item in record.items" :key="item.itemId" class="judgment-item">
            <div class="item-header">
              <el-tag :type="getCategoryType(item.category)" size="small" class="category-tag">
                {{ getCategoryLabel(item.category) }}
              </el-tag>
              <span class="item-label">{{ item.label }}</span>
            </div>
            <div class="item-body">
              <el-radio-group
                :model-value="item.conclusion"
                :disabled="isReadonly"
                size="small"
                @change="(v: string | number | boolean | undefined) => handleUpdateItem(record.recordId, item.itemId, 'conclusion', String(v))"
              >
                <el-radio-button value="是">是</el-radio-button>
                <el-radio-button value="否">否</el-radio-button>
                <el-radio-button value="不适用">不适用</el-radio-button>
              </el-radio-group>
              <el-input
                v-if="!isReadonly"
                v-model="item.explanation" size="small" placeholder="说明（可选）"
                class="item-explanation"
                @change="handleUpdateItem(record.recordId, item.itemId, 'explanation', item.explanation)"
              />
              <span v-else-if="item.explanation" class="explanation-text">{{ item.explanation }}</span>
            </div>
          </div>
        </div>

        <!-- 最终结论 -->
        <div class="final-conclusion">
          <span class="conclusion-label">最终结论：</span>
          <el-radio-group
            :model-value="record.finalConclusion"
            :disabled="isReadonly"
            size="small"
            @change="(v: string | number | boolean | undefined) => handleUpdateConclusion(record.recordId, String(v) as '是' | '否' | '不适用')"
          >
            <el-radio-button value="是">属于租赁</el-radio-button>
            <el-radio-button value="否">不属于租赁</el-radio-button>
            <el-radio-button value="不适用">不适用</el-radio-button>
          </el-radio-group>
        </div>

        <!-- 审计说明 -->
        <el-input
          v-if="!isReadonly"
          type="textarea" :autosize="{ minRows: 2 }" v-model="record.auditNote"
          placeholder="审计说明..." class="audit-note"
          @change="handleUpdateNote(record.recordId, record.auditNote)"
        />
        <p v-else-if="record.auditNote" class="note-display">{{ record.auditNote }}</p>
      </el-card>
    </div>

    <!-- 编制提示 -->
    <details class="compile-hint">
      <summary>编制提示</summary>
      <ul>
        <li>租赁识别三要素（CAS21第4-13条）须全部满足才构成租赁：</li>
        <li>① 已识别资产：合同标的为特定可识别资产（明确指定或隐含指定）</li>
        <li>② 控制权：承租人在使用期内主导资产使用并获得几乎全部经济利益</li>
        <li>③ 替换权：供应商不具有实质性资产替换权</li>
        <li>三要素齐备→属于租赁（确认使用权资产）；否则不属于租赁</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * H8TabLeaseIdentification.vue — H8-4 租赁识别（段落型90行10列）
 * CAS21租赁三要素判断：已识别资产+控制权+实质替换权
 * Spec: Task 4.4 | Requirements: 4.1, 4.4, 4.5
 */
import { toRef } from 'vue'
import { ElMessageBox } from 'element-plus'
import { useH8LeaseIdentification } from '../../composables/useH8LeaseIdentification'
import GtIndexChip from '../../GtIndexChip.vue'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const emit = defineEmits<{
  (e: 'save', itemId: string, value: any): void
  (e: 'open-ai', section: string): void
  (e: 'open-review', section: string): void
}>()

const {
  records, completedCount, leaseCount,
  addRecord, deleteRecord, updateItem, updateConclusion, updateNote,
} = useH8LeaseIdentification({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  allResponses: toRef(props, 'allResponses'),
  onSave: (itemId, value) => emit('save', itemId, value),
})

function getCategoryLabel(cat: string): string {
  const map: Record<string, string> = { identifiedAsset: '已识别资产', controlRight: '控制权', substitutionRight: '替换权' }
  return map[cat] ?? cat
}

function getCategoryType(cat: string): 'primary' | 'success' | 'warning' {
  const map: Record<string, 'primary' | 'success' | 'warning'> = { identifiedAsset: 'primary', controlRight: 'success', substitutionRight: 'warning' }
  return map[cat] ?? 'primary'
}

async function handleAddRecord() {
  const { value } = await ElMessageBox.prompt('请输入租赁合同号', '新增租赁识别判断', {
    confirmButtonText: '确认', cancelButtonText: '取消', inputPlaceholder: '如：ZL-2024-001',
  })
  if (value) addRecord(value)
}

function handleDeleteRecord(recordId: string) { deleteRecord(recordId) }
function handleUpdateItem(recordId: string, itemId: string, field: 'conclusion' | 'explanation', value: string) {
  updateItem(recordId, itemId, field, value)
}
function handleUpdateConclusion(recordId: string, conclusion: '是' | '否' | '不适用') {
  updateConclusion(recordId, conclusion)
}
function handleUpdateNote(recordId: string, note: string) {
  updateNote(recordId, note)
}
</script>

<style scoped>
.h8-tab-lease-identification { padding: 16px; font-size: var(--wp-font-size, 13px); }

.methodology-context {
  background: #fffbeb; border-left: 4px solid #f59e0b; padding: 10px 14px;
  border-radius: 0 6px 6px 0; margin-bottom: 16px; font-size: 12px; color: #92400e;
}

.h8-tab-toolbar { display: flex; align-items: center; gap: 8px; margin-bottom: 12px; }

.compile-hint { margin-top: 12px; font-size: 12px; color: var(--el-text-color-secondary); }
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ul { padding-left: 20px; margin-top: 8px; }

.stats-bar {
  display: flex; align-items: center; gap: 10px; margin-bottom: 16px; flex-wrap: wrap;
}
.stats-actions { margin-left: auto; display: flex; gap: 6px; }

.empty-state { padding: 40px 0; }

.identification-card { margin-bottom: 16px; }
.card-header { display: flex; align-items: center; justify-content: space-between; }
.contract-label { font-weight: 600; }
.card-actions { display: flex; align-items: center; gap: 8px; }

.items-grid { display: flex; flex-direction: column; gap: 12px; margin-bottom: 16px; }
.judgment-item { border: 1px solid var(--el-border-color-lighter); border-radius: 6px; padding: 10px 12px; }
.item-header { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
.category-tag { flex-shrink: 0; }
.item-label { font-size: var(--wp-font-size, 13px); }
.item-body { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
.item-explanation { flex: 1; min-width: 200px; }
.explanation-text { font-size: 12px; color: var(--el-text-color-secondary); }

.final-conclusion { display: flex; align-items: center; gap: 12px; margin-bottom: 12px; padding-top: 12px; border-top: 1px solid var(--el-border-color-lighter); }
.conclusion-label { font-weight: 600; flex-shrink: 0; }

.audit-note { margin-top: 8px; }
.note-display { font-size: 12px; color: var(--el-text-color-secondary); margin-top: 8px; }
</style>
