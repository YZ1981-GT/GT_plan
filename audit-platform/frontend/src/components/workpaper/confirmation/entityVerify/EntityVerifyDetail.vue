<template>
  <div class="entity-verify-detail">
    <div v-if="!row" class="entity-verify-detail__empty">
      <el-empty description="请选择一行查看详情" />
    </div>
    <el-collapse v-else v-model="activeStages" class="entity-verify-detail__collapse">
      <!-- Stage 1: 基本信息 -->
      <el-collapse-item title="基本信息" name="basic">
        <el-form label-width="90px" size="small" class="entity-verify-detail__form">
          <el-row :gutter="16">
            <el-col :span="12">
              <el-form-item label="被询证单位">
                <el-input :model-value="row.entity_name" :disabled="readonly" @update:model-value="(v) => emitUpdate('entity_name', v)" />
              </el-form-item>
            </el-col>
            <el-col :span="12">
              <el-form-item label="科目">
                <el-select :model-value="row.account_type" :disabled="readonly" @update:model-value="(v) => emitUpdate('account_type', v)" placeholder="请选择" filterable allow-create>
                  <el-option v-for="opt in getDictOptions('confirmation_account_type')" :key="opt" :label="opt" :value="opt" />
                </el-select>
              </el-form-item>
            </el-col>
            <el-col :span="12">
              <el-form-item label="地址">
                <el-input :model-value="row.entity_address" :disabled="readonly" @update:model-value="(v) => emitUpdate('entity_address', v)" />
              </el-form-item>
            </el-col>
            <el-col :span="12">
              <el-form-item label="联系人">
                <el-input :model-value="row.contact_person" :disabled="readonly" @update:model-value="(v) => emitUpdate('contact_person', v)" />
              </el-form-item>
            </el-col>
            <el-col :span="12">
              <el-form-item label="联系电话">
                <el-input :model-value="row.contact_phone" :disabled="readonly" @update:model-value="(v) => emitUpdate('contact_phone', v)" />
              </el-form-item>
            </el-col>
          </el-row>
        </el-form>
      </el-collapse-item>

      <!-- Stage 2: 企查查核对 -->
      <el-collapse-item title="企查查核对" name="qcc">
        <el-form label-width="90px" size="small" class="entity-verify-detail__form">
          <el-row :gutter="16">
            <el-col :span="12">
              <el-form-item label="企查查名称">
                <el-input :model-value="row.qcc_entity_name" :disabled="readonly" @update:model-value="(v) => emitUpdate('qcc_entity_name', v)" />
              </el-form-item>
            </el-col>
            <el-col :span="12">
              <el-form-item>
                <template #label><span>企查查地址</span><FieldHintIcon field="qcc_address" /></template>
                <el-input :model-value="row.qcc_address" :disabled="readonly" @update:model-value="(v) => emitUpdate('qcc_address', v)" />
              </el-form-item>
            </el-col>
            <el-col :span="12">
              <el-form-item label="企查查联系人">
                <el-input :model-value="row.qcc_contact" :disabled="readonly" @update:model-value="(v) => emitUpdate('qcc_contact', v)" />
              </el-form-item>
            </el-col>
            <el-col :span="12">
              <el-form-item label="企查查电话">
                <el-input :model-value="row.qcc_phone" :disabled="readonly" @update:model-value="(v) => emitUpdate('qcc_phone', v)" />
              </el-form-item>
            </el-col>
            <el-col :span="12">
              <el-form-item label="名称一致性">
                <el-select :model-value="row.name_match" :disabled="readonly" @update:model-value="(v) => emitUpdate('name_match', v)" placeholder="请选择">
                  <el-option label="一致" value="consistent" /><el-option label="不一致" value="inconsistent" /><el-option label="待核实" value="pending" />
                </el-select>
              </el-form-item>
            </el-col>
            <el-col :span="12">
              <el-form-item label="地址一致性">
                <el-select :model-value="row.address_match" :disabled="readonly" @update:model-value="(v) => emitUpdate('address_match', v)" placeholder="请选择">
                  <el-option label="一致" value="consistent" /><el-option label="不一致" value="inconsistent" /><el-option label="待核实" value="pending" />
                </el-select>
              </el-form-item>
            </el-col>
            <el-col :span="12">
              <el-form-item label="联系人一致性">
                <el-select :model-value="row.contact_match" :disabled="readonly" @update:model-value="(v) => emitUpdate('contact_match', v)" placeholder="请选择">
                  <el-option label="一致" value="consistent" /><el-option label="不一致" value="inconsistent" /><el-option label="待核实" value="pending" />
                </el-select>
              </el-form-item>
            </el-col>
            <el-col :span="12">
              <el-form-item label="电话一致性">
                <el-select :model-value="row.phone_match" :disabled="readonly" @update:model-value="(v) => emitUpdate('phone_match', v)" placeholder="请选择">
                  <el-option label="一致" value="consistent" /><el-option label="不一致" value="inconsistent" /><el-option label="待核实" value="pending" />
                </el-select>
              </el-form-item>
            </el-col>
          </el-row>
          <!-- Conditional: address mismatch verify fields -->
          <template v-if="row.address_match === 'inconsistent'">
            <el-row :gutter="16">
              <el-col :span="12">
                <el-form-item label="地址核实结果">
                  <el-input :model-value="row.address_verify_result" :disabled="readonly" @update:model-value="(v) => emitUpdate('address_verify_result', v)" />
                </el-form-item>
              </el-col>
              <el-col :span="12">
                <el-form-item label="核实备注">
                  <el-input :model-value="row.address_verify_note" :disabled="readonly" type="textarea" :rows="2" @update:model-value="(v) => emitUpdate('address_verify_note', v)" />
                </el-form-item>
              </el-col>
            </el-row>
          </template>
        </el-form>
      </el-collapse-item>

      <!-- Stage 3: 发函信息 -->
      <el-collapse-item title="发函信息" name="send">
        <el-form label-width="90px" size="small" class="entity-verify-detail__form">
          <el-row :gutter="16">
            <el-col :span="12">
              <el-form-item label="发函日期">
                <el-date-picker :model-value="row.first_send_date" :disabled="readonly" type="date" value-format="YYYY-MM-DD" @update:model-value="(v) => emitUpdate('first_send_date', v)" placeholder="选择日期" />
              </el-form-item>
            </el-col>
            <el-col :span="12">
              <el-form-item label="发函方式">
                <el-select :model-value="row.first_send_method" :disabled="readonly" @update:model-value="(v) => emitUpdate('first_send_method', v)" placeholder="请选择">
                  <el-option label="挂号信" value="挂号信" /><el-option label="快递" value="快递" /><el-option label="当面递交" value="当面递交" /><el-option label="电子邮件" value="电子邮件" />
                </el-select>
              </el-form-item>
            </el-col>
            <el-col :span="12">
              <el-form-item label="发函结果">
                <el-select :model-value="row.first_result" :disabled="readonly" @update:model-value="(v) => emitUpdate('first_result', v)" placeholder="请选择">
                  <el-option label="送抵" value="送抵" /><el-option label="退回" value="退回" />
                </el-select>
              </el-form-item>
            </el-col>
            <el-col :span="12">
              <el-form-item label="二次发函">
                <el-switch :model-value="row.is_second_send" :disabled="readonly" @update:model-value="(v) => emitUpdate('is_second_send', v)" />
              </el-form-item>
            </el-col>
          </el-row>
          <!-- Conditional: show return fields when first_result === '退回' -->
          <el-row v-if="row.first_result === '退回'" :gutter="16">
            <el-col :span="12">
              <el-form-item>
                <template #label><span>退回原因</span><FieldHintIcon field="return_reason" /></template>
                <el-input :model-value="row.return_reason" :disabled="readonly" @update:model-value="(v) => emitUpdate('return_reason', v)" placeholder="请填写退回原因" />
              </el-form-item>
            </el-col>
            <el-col :span="12">
              <el-form-item>
                <template #label><span>原因合理性</span><FieldHintIcon field="reason_reasonable" /></template>
                <el-select :model-value="row.reason_reasonable" :disabled="readonly" @update:model-value="(v) => emitUpdate('reason_reasonable', v)" placeholder="请选择">
                  <el-option label="合理" value="合理" /><el-option label="不合理" value="不合理" />
                </el-select>
              </el-form-item>
            </el-col>
          </el-row>
        </el-form>
      </el-collapse-item>

      <!-- Stage 4: 二次发函 (conditional) -->
      <el-collapse-item v-show="row.is_second_send" title="二次发函" name="second_send">
        <el-form label-width="90px" size="small" class="entity-verify-detail__form">
          <el-row :gutter="16">
            <el-col :span="12">
              <el-form-item label="发函日期">
                <el-date-picker :model-value="row.second_send_date" :disabled="readonly" type="date" value-format="YYYY-MM-DD" @update:model-value="(v) => emitUpdate('second_send_date', v)" placeholder="选择日期" />
              </el-form-item>
            </el-col>
            <el-col :span="12">
              <el-form-item label="发函方式">
                <el-select :model-value="row.second_send_method" :disabled="readonly" @update:model-value="(v) => emitUpdate('second_send_method', v)" placeholder="请选择">
                  <el-option label="挂号信" value="挂号信" /><el-option label="快递" value="快递" /><el-option label="当面递交" value="当面递交" /><el-option label="电子邮件" value="电子邮件" />
                </el-select>
              </el-form-item>
            </el-col>
            <el-col :span="12">
              <el-form-item>
                <template #label><span>发函结果</span><FieldHintIcon field="second_result" /></template>
                <el-select :model-value="row.second_result" :disabled="readonly" @update:model-value="(v) => emitUpdate('second_result', v)" placeholder="请选择">
                  <el-option label="送抵" value="送抵" /><el-option label="退回" value="退回" />
                </el-select>
              </el-form-item>
            </el-col>
            <el-col v-if="row.second_result === '退回'" :span="12">
              <el-form-item label="退回原因">
                <el-input :model-value="row.second_return_reason" :disabled="readonly" @update:model-value="(v) => emitUpdate('second_return_reason', v)" />
              </el-form-item>
            </el-col>
          </el-row>
        </el-form>
      </el-collapse-item>

      <!-- Stage 5: 回函/电子函证 -->
      <el-collapse-item title="回函/电子函证" name="reply">
        <el-form label-width="90px" size="small" class="entity-verify-detail__form">
          <el-row :gutter="16">
            <el-col :span="12">
              <el-form-item>
                <template #label><span>回函方式</span><FieldHintIcon v-if="row.is_electronic" field="reply_method" /></template>
                <el-select :model-value="row.reply_method" :disabled="readonly" @update:model-value="(v) => emitUpdate('reply_method', v)" placeholder="请选择">
                  <el-option label="原件寄回" value="原件寄回" /><el-option label="传真" value="传真" /><el-option label="电子邮件" value="电子邮件" /><el-option label="电子函证平台" value="电子函证平台" /><el-option label="当面确认" value="当面确认" />
                </el-select>
              </el-form-item>
            </el-col>
            <el-col :span="12">
              <el-form-item label="回函日期">
                <el-date-picker :model-value="row.reply_date" :disabled="readonly" type="date" value-format="YYYY-MM-DD" @update:model-value="(v) => emitUpdate('reply_date', v)" placeholder="选择日期" />
              </el-form-item>
            </el-col>
            <el-col :span="12">
              <el-form-item label="电子函证">
                <el-switch :model-value="row.is_electronic" :disabled="readonly" @update:model-value="(v) => emitUpdate('is_electronic', v)" />
              </el-form-item>
            </el-col>
            <el-col v-if="row.is_electronic" :span="12">
              <el-form-item label="电子平台">
                <el-input :model-value="row.electronic_platform" :disabled="readonly" @update:model-value="(v) => emitUpdate('electronic_platform', v)" placeholder="如：确函宝、e-确认" />
              </el-form-item>
            </el-col>
          </el-row>
          <el-row v-if="row.is_electronic" :gutter="16">
            <el-col :span="24">
              <el-form-item label="可靠性备注">
                <el-input :model-value="row.electronic_verify_note" :disabled="readonly" type="textarea" :rows="2" @update:model-value="(v) => emitUpdate('electronic_verify_note', v)" placeholder="评估电子回函可靠性" />
              </el-form-item>
            </el-col>
          </el-row>
        </el-form>
      </el-collapse-item>
    </el-collapse>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import type { EntityVerifyRow } from './entityVerifyTypes'
import FieldHintIcon from './FieldHintIcon.vue'

const props = defineProps<{
  row: EntityVerifyRow | null
  readonly: boolean
  dictData: Record<string, any[]>
}>()

const emit = defineEmits<{
  (e: 'update', field: string, value: any): void
}>()

const activeStages = ref<string[]>(['basic', 'qcc', 'send', 'reply'])

function emitUpdate(field: string, value: any) {
  if (!props.readonly) {
    emit('update', field, value)
  }
}

function getDictOptions(dictKey: string): string[] {
  const options = props.dictData?.[dictKey]
  if (!Array.isArray(options)) return []
  return options.map((opt) => (typeof opt === 'string' ? opt : opt.label ?? opt.value ?? ''))
}
</script>

<style scoped>
.entity-verify-detail__empty {
  padding: 40px 0;
  text-align: center;
}

.entity-verify-detail__collapse {
  padding: 0 8px;
}
</style>
