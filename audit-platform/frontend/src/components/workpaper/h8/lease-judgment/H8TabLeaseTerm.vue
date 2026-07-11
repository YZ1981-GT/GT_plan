<template>
  <div class="h8-tab-lease-term">
    <!-- 方法论上下文 -->
    <div class="methodology-context">
      <p>CAS21第14-17条：租赁期 = 不可撤销期 + 合理确定行使的续租选择权期 - 合理确定行使的终止选择权期。需逐合同判断续租/终止选择权是否合理确定行使。</p>
    </div>

    <!-- 索引 + 行数 -->
    <div class="h8-tab-toolbar">
      <GtIndexChip value="wp:H8-5" />
      <el-tag size="small" type="info">共 {{ records.length }} 份合同</el-tag>
    </div>

    <!-- 顶部统计 -->
    <div class="stats-bar">
      <el-tag type="info" size="small">合同总数：{{ records.length }}</el-tag>
      <el-tag type="success" size="small">已完成：{{ completedCount }}</el-tag>
      <el-tag type="primary" size="small">平均租赁期：{{ avgLeaseTerm }}月</el-tag>
      <div class="stats-actions">
        <el-button v-if="!isReadonly" size="small" type="primary" @click="handleAddRecord">+ 新增合同</el-button>
        <el-button size="small" type="primary" plain @click="$emit('open-ai', 'lease-term')">AI 辅助</el-button>
        <el-button size="small" @click="$emit('open-review', 'lease-term')">复核</el-button>
      </div>
    </div>

    <!-- 空状态 -->
    <div v-if="records.length === 0" class="empty-state">
      <el-empty description="暂无租赁期确定记录" />
    </div>

    <!-- 每份合同的租赁期确定卡片 -->
    <div v-for="record in records" :key="record.recordId" class="term-card">
      <el-card shadow="never">
        <template #header>
          <div class="card-header">
            <span class="contract-label">合同号：{{ record.contractNo }}</span>
            <div class="card-actions">
              <el-tag type="primary" size="small">最终租赁期：{{ record.finalLeaseTerm }}月</el-tag>
              <el-button v-if="!isReadonly" type="danger" link size="small" @click="handleDeleteRecord(record.recordId)">删除</el-button>
            </div>
          </div>
        </template>

        <!-- 不可撤销期 -->
        <el-form :inline="true" size="small" label-position="left" class="term-form">
          <el-form-item label="不可撤销租赁期（月）">
            <el-input-number
              :model-value="record.nonCancellableTerm"
              :controls="false" :min="0"
              :disabled="isReadonly"
              @change="(v: number | undefined) => handleUpdate(record.recordId, 'nonCancellableTerm', v)"
            />
          </el-form-item>
        </el-form>

        <!-- 续租选择权 -->
        <div class="option-section">
          <div class="option-header">
            <span class="option-title">续租选择权</span>
          </div>
          <el-form :inline="true" size="small" class="term-form">
            <el-form-item label="续租期限（月）">
              <el-input-number
                :model-value="record.renewalOptionTerm"
                :controls="false" :min="0"
                :disabled="isReadonly"
                @change="(v: number | undefined) => handleUpdate(record.recordId, 'renewalOptionTerm', v)"
              />
            </el-form-item>
            <el-form-item label="是否合理确定行使">
              <el-radio-group
                :model-value="record.isRenewalReasonablyCertain"
                :disabled="isReadonly"
                @change="(v: string | number | boolean | undefined) => handleUpdate(record.recordId, 'isRenewalReasonablyCertain', v)"
              >
                <el-radio-button value="是">是</el-radio-button>
                <el-radio-button value="否">否</el-radio-button>
              </el-radio-group>
            </el-form-item>
          </el-form>
        </div>

        <!-- 终止选择权 -->
        <div class="option-section">
          <div class="option-header">
            <span class="option-title">终止选择权</span>
          </div>
          <el-form :inline="true" size="small" class="term-form">
            <el-form-item label="终止期限（月）">
              <el-input-number
                :model-value="record.terminationOptionTerm"
                :controls="false" :min="0"
                :disabled="isReadonly"
                @change="(v: number | undefined) => handleUpdate(record.recordId, 'terminationOptionTerm', v)"
              />
            </el-form-item>
            <el-form-item label="是否合理确定行使">
              <el-radio-group
                :model-value="record.isTerminationReasonablyCertain"
                :disabled="isReadonly"
                @change="(v: string | number | boolean | undefined) => handleUpdate(record.recordId, 'isTerminationReasonablyCertain', v)"
              >
                <el-radio-button value="是">是</el-radio-button>
                <el-radio-button value="否">否</el-radio-button>
              </el-radio-group>
            </el-form-item>
          </el-form>
        </div>

        <!-- 计算结果 -->
        <div class="calc-result">
          <span class="formula-display">
            租赁期 = {{ record.nonCancellableTerm }}
            {{ record.isRenewalReasonablyCertain === '是' ? ` + ${record.renewalOptionTerm}` : '' }}
            {{ record.isTerminationReasonablyCertain === '是' ? ` - ${record.terminationOptionTerm}` : '' }}
            = <strong>{{ record.finalLeaseTerm }}月</strong>
          </span>
        </div>

        <!-- 说明与结论 -->
        <el-form size="small" label-position="top" class="term-form">
          <el-form-item label="判断说明">
            <el-input type="textarea" :autosize="{ minRows: 2 }"
              :model-value="record.explanation"
              :readonly="isReadonly"
              placeholder="续租/终止选择权判断依据..."
              @change="(v: string | number) => handleUpdate(record.recordId, 'explanation', v)"
            />
          </el-form-item>
          <el-form-item label="结论">
            <el-radio-group
              :model-value="record.conclusion"
              :disabled="isReadonly"
              @change="(v: string | number | boolean | undefined) => handleUpdate(record.recordId, 'conclusion', v)"
            >
              <el-radio-button value="是">是</el-radio-button>
              <el-radio-button value="否">否</el-radio-button>
              <el-radio-button value="不适用">不适用</el-radio-button>
            </el-radio-group>
          </el-form-item>
        </el-form>
      </el-card>
    </div>

    <!-- 编制提示 -->
    <details class="compile-hint">
      <summary>编制提示</summary>
      <ul>
        <li>租赁期 = 不可撤销期 + 合理确定续租期 - 合理确定终止期（CAS21第14-17条）</li>
        <li>续租选择权：仅当"合理确定行使"时才计入租赁期</li>
        <li>终止选择权：仅当"合理确定行使"时才从租赁期扣减</li>
        <li>合理确定的判断应考虑经济诱因、租赁改良、迁移成本、业务重要性等</li>
        <li>租赁期直接影响 H8-6 计量与 H8-8 折旧期的确定</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * H8TabLeaseTerm.vue — H8-5 租赁期确定（段落型52行8列）
 * CAS21租赁期 = 不可撤销期 + 合理确定续租 - 合理确定终止
 * Spec: Task 4.4 | Requirements: 4.2, 4.4
 */
import { toRef } from 'vue'
import { ElMessageBox } from 'element-plus'
import { useH8LeaseTerm } from '../../composables/useH8LeaseTerm'
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
  records, completedCount, avgLeaseTerm,
  addRecord, deleteRecord, updateField,
} = useH8LeaseTerm({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  allResponses: toRef(props, 'allResponses'),
  onSave: (itemId, value) => emit('save', itemId, value),
})

async function handleAddRecord() {
  const { value } = await ElMessageBox.prompt('请输入租赁合同号', '新增租赁期确定', {
    confirmButtonText: '确认', cancelButtonText: '取消', inputPlaceholder: '如：ZL-2024-001',
  })
  if (value) addRecord(value)
}

function handleDeleteRecord(recordId: string) { deleteRecord(recordId) }
function handleUpdate(recordId: string, field: string, value: any) { updateField(recordId, field, value) }
</script>

<style scoped>
.h8-tab-lease-term { padding: 16px; font-size: 13px; }

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
.term-card { margin-bottom: 16px; }
.card-header { display: flex; align-items: center; justify-content: space-between; }
.contract-label { font-weight: 600; }
.card-actions { display: flex; align-items: center; gap: 8px; }

.term-form { margin-bottom: 8px; }

.option-section {
  border: 1px solid var(--el-border-color-lighter); border-radius: 6px;
  padding: 10px 12px; margin-bottom: 12px;
}
.option-header { margin-bottom: 8px; }
.option-title { font-weight: 600; font-size: 13px; }

.calc-result {
  background: #f0f9ff; border-radius: 6px; padding: 10px 14px; margin-bottom: 12px;
}
.formula-display { font-size: 13px; color: var(--el-color-primary); }
</style>
