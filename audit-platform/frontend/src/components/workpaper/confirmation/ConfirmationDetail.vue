<template>
  <div class="confirmation-detail">
    <div v-if="!row" class="confirmation-detail__empty">
      <span class="confirmation-detail__empty-hint">👆 点击上方表格中的行查看/编辑详情</span>
    </div>
    <el-collapse v-else v-model="activeStages" class="confirmation-detail__collapse">
      <!-- Stage 1: 基本信息 -->
      <el-collapse-item title="基本信息" name="basic">
        <el-form label-width="100px" size="small">
          <el-form-item label="被询证单位">
            <el-input
              :model-value="row.entity_name"
              :disabled="readonly"
              @update:model-value="(v) => emitUpdate('entity_name', v)"
            />
          </el-form-item>
          <el-form-item label="地址">
            <el-input
              :model-value="row.entity_address"
              :disabled="readonly"
              @update:model-value="(v) => emitUpdate('entity_address', v)"
            />
          </el-form-item>
          <el-form-item label="联系人">
            <el-input
              :model-value="row.contact_person"
              :disabled="readonly"
              @update:model-value="(v) => emitUpdate('contact_person', v)"
            />
          </el-form-item>
          <el-form-item label="联系电话">
            <el-input
              :model-value="row.contact_phone"
              :disabled="readonly"
              @update:model-value="(v) => emitUpdate('contact_phone', v)"
            />
          </el-form-item>
          <el-form-item label="科目">
            <el-select
              :model-value="row.account_type"
              :disabled="readonly"
              @update:model-value="(v) => emitUpdate('account_type', v)"
              placeholder="请选择或输入"
              filterable
              allow-create
              default-first-option
            >
              <el-option
                v-for="opt in getDictOptions('confirmation_account_type')"
                :key="opt"
                :label="opt"
                :value="opt"
              />
            </el-select>
          </el-form-item>
          <el-form-item label="币种">
            <el-select
              :model-value="row.currency || 'CNY'"
              :disabled="readonly"
              @update:model-value="(v) => emitUpdate('currency', v)"
              placeholder="CNY"
              filterable
              allow-create
              default-first-option
            >
              <el-option v-for="opt in ['CNY', 'USD', 'EUR', 'HKD', 'GBP', 'JPY']" :key="opt" :label="opt" :value="opt" />
            </el-select>
          </el-form-item>
        </el-form>
      </el-collapse-item>

      <!-- Stage 2: 函证信息 -->
      <el-collapse-item title="函证信息" name="confirmation">
        <el-form label-width="100px" size="small">
          <el-form-item label="函证方式">
            <el-select
              :model-value="row.confirmation_method"
              :disabled="readonly"
              @update:model-value="(v) => emitUpdate('confirmation_method', v)"
              placeholder="请选择"
            >
              <el-option
                v-for="opt in getDictOptions('confirmation_method')"
                :key="opt"
                :label="opt"
                :value="opt"
              />
            </el-select>
          </el-form-item>
          <el-form-item label="发函日期">
            <el-date-picker
              :model-value="row.send_date"
              :disabled="readonly"
              type="date"
              value-format="YYYY-MM-DD"
              @update:model-value="(v) => emitUpdate('send_date', v)"
              placeholder="选择日期"
            />
          </el-form-item>
          <el-form-item label="函证金额">
            <el-input-number
              :model-value="row.amount"
              :disabled="readonly"
              :precision="2"
              :controls="false"
              @update:model-value="(v) => emitUpdate('amount', v)"
            />
          </el-form-item>
        </el-form>
      </el-collapse-item>

      <!-- Stage 3: 回函信息 (visible only when is_replied) -->
      <el-collapse-item v-show="row.is_replied" title="回函信息" name="reply">
        <el-form label-width="100px" size="small">
          <el-form-item label="回函日期">
            <el-date-picker
              :model-value="row.reply_date"
              :disabled="readonly"
              type="date"
              value-format="YYYY-MM-DD"
              @update:model-value="(v) => emitUpdate('reply_date', v)"
              placeholder="选择日期"
            />
          </el-form-item>
          <el-form-item label="回函方式">
            <el-select
              :model-value="row.reply_method"
              :disabled="readonly"
              @update:model-value="(v) => emitUpdate('reply_method', v)"
              placeholder="请选择"
            >
              <el-option
                v-for="opt in getDictOptions('confirmation_reply_method')"
                :key="opt"
                :label="opt"
                :value="opt"
              />
            </el-select>
          </el-form-item>
          <el-form-item label="回函金额">
            <el-input-number
              :model-value="row.reply_amount"
              :disabled="readonly"
              :precision="2"
              :controls="false"
              @update:model-value="(v) => emitUpdate('reply_amount', v)"
            />
          </el-form-item>
          <el-form-item label="相符情况">
            <el-select
              :model-value="row.match_status"
              :disabled="readonly"
              @update:model-value="(v) => emitUpdate('match_status', v)"
              placeholder="请选择"
            >
              <el-option
                v-for="opt in getDictOptions('confirmation_match')"
                :key="opt"
                :label="opt"
                :value="opt"
              />
            </el-select>
          </el-form-item>
        </el-form>
      </el-collapse-item>

      <!-- Stage 4: 确认金额 -->
      <el-collapse-item title="确认金额" name="confirmed">
        <el-form label-width="100px" size="small">
          <el-form-item label="可确认金额">
            <div class="confirmation-detail__amount-row">
              <span class="confirmation-detail__amount-display">
                {{ row.confirmed_amount != null ? row.confirmed_amount.toLocaleString() + '元' : '0元' }}
              </span>
              <el-tooltip placement="top" :content="confirmedAmountFormula">
                <el-tag size="small" type="info" class="confirmation-detail__formula-tag">fx 公式</el-tag>
              </el-tooltip>
            </div>
          </el-form-item>
          <el-form-item label="差异金额">
            <div class="confirmation-detail__amount-row">
              <span class="confirmation-detail__amount-display">
                {{ row.difference != null ? row.difference.toLocaleString() + '元' : '0元' }}
              </span>
              <el-tooltip placement="top" content="差异 = 函证金额 - 回函金额（相符时为0）">
                <el-tag size="small" type="info" class="confirmation-detail__formula-tag">fx 公式</el-tag>
              </el-tooltip>
            </div>
          </el-form-item>
          <el-form-item label="差异索引">
            <div class="confirmation-detail__ref-row">
              <el-input
                :model-value="row.diff_ref_index"
                :disabled="readonly"
                @update:model-value="(v) => emitUpdate('diff_ref_index', v)"
                placeholder="D0-4 索引"
                style="flex:1"
              />
              <el-button
                v-if="row.diff_ref_index"
                size="small"
                text
                type="primary"
                @click="$emit('jump-to-ref', row.diff_ref_index)"
              >跳转 →</el-button>
            </div>
          </el-form-item>
          <el-form-item label="替代索引">
            <div class="confirmation-detail__ref-row">
              <el-input
                :model-value="row.alt_ref_index"
                :disabled="readonly"
                @update:model-value="(v) => emitUpdate('alt_ref_index', v)"
                placeholder="D0-5/D0-6 索引"
                style="flex:1"
              />
              <el-button
                v-if="row.alt_ref_index"
                size="small"
                text
                type="primary"
                @click="$emit('jump-to-ref', row.alt_ref_index)"
              >跳转 →</el-button>
            </div>
          </el-form-item>
          <el-form-item label="备注">
            <el-input
              :model-value="row.remark"
              :disabled="readonly"
              type="textarea"
              :rows="2"
              @update:model-value="(v) => emitUpdate('remark', v)"
            />
          </el-form-item>
        </el-form>
      </el-collapse-item>
    </el-collapse>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import type { ConfirmationRow } from './confirmationTypes'

const props = defineProps<{
  row: ConfirmationRow | null
  readonly: boolean
  dictData: Record<string, any[]>
}>()

const emit = defineEmits<{
  (e: 'update', field: string, value: any): void
  (e: 'jump-to-ref', refCode: string): void
}>()

const activeStages = ref<string[]>(['basic', 'confirmation', 'reply', 'confirmed'])

/** 可确认金额的计算公式说明（根据当前行状态动态生成） */
const confirmedAmountFormula = computed(() => {
  const row = props.row
  if (!row) return '尚未选择行'
  if (row.match_status === '相符') return '相符 → 可确认金额 = 函证金额'
  if (row.match_status === '不符') return '不符 → 可确认金额 = 回函金额（差异待 D0-4 调节）'
  if (row.is_replied === '否' && row.confirmation_method === '消极式') return '消极式未回函 → 视同相符，可确认金额 = 函证金额'
  if (row.is_replied === '否') return '积极式未回函 → 需替代程序确认（D0-5/D0-6）'
  return '可确认金额 = 根据回函情况自动计算'
})

function emitUpdate(field: string, value: any) {
  if (!props.readonly) {
    emit('update', field, value)
  }
}

function getDictOptions(dictKey: string): string[] {
  const options = props.dictData?.[dictKey]
  if (!Array.isArray(options)) return []
  // Support both string[] and { label, value }[] formats
  return options.map((opt) => (typeof opt === 'string' ? opt : opt.label ?? opt.value ?? ''))
}
</script>

<style scoped>
.confirmation-detail__empty {
  padding: 12px 16px;
  text-align: center;
  border: 1px dashed #dcdfe6;
  border-radius: 4px;
  margin: 8px 0;
}
.confirmation-detail__empty-hint {
  font-size: 13px;
  color: #909399;
}

.confirmation-detail__collapse {
  padding: 0 8px;
}

.confirmation-detail__amount-display {
  font-weight: 600;
  color: var(--el-color-primary);
}

.confirmation-detail__amount-row {
  display: flex;
  align-items: center;
  gap: 8px;
}
.confirmation-detail__formula-tag {
  cursor: help;
  font-size: 11px;
}
.confirmation-detail__ref-row {
  display: flex;
  align-items: center;
  gap: 6px;
  width: 100%;
}
</style>
