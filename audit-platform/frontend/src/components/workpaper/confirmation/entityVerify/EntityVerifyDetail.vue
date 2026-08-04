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
            <!--
              源模板 X0-2 的「被审计单位提供的被函证单位信息」块含邮编与邮箱/传真两列
              （E6/H6）——改造前平台只在企查查侧有这两列，提供侧无落笔位置。
              spec: h0-confirmation-source-fidelity-and-linkage R8.2
            -->
            <el-col :span="12">
              <el-form-item label="邮编">
                <el-input :model-value="row.provided_zipcode" :disabled="readonly" @update:model-value="(v) => emitUpdate('provided_zipcode', v)" />
              </el-form-item>
            </el-col>
            <el-col :span="12">
              <el-form-item label="邮箱/传真">
                <el-input :model-value="row.provided_email_fax" :disabled="readonly" @update:model-value="(v) => emitUpdate('provided_email_fax', v)" />
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
            <el-col :span="12">
              <el-form-item label="邮编">
                <el-input :model-value="row.qcc_zipcode" :disabled="readonly" @update:model-value="(v) => emitUpdate('qcc_zipcode', v)" />
              </el-form-item>
            </el-col>
            <el-col :span="12">
              <el-form-item label="邮箱/传真">
                <el-input :model-value="row.qcc_email_fax" :disabled="readonly" @update:model-value="(v) => emitUpdate('qcc_email_fax', v)" />
              </el-form-item>
            </el-col>
            <el-col :span="12">
              <el-form-item label="不一致说明合理">
                <el-select :model-value="row.qcc_inconsistent_reasonable" :disabled="readonly" @update:model-value="(v) => emitUpdate('qcc_inconsistent_reasonable', v)" placeholder="请选择" clearable>
                  <el-option label="合理" value="合理" /><el-option label="不合理" value="不合理" /><el-option label="不适用" value="不适用" />
                </el-select>
              </el-form-item>
            </el-col>
            <el-col :span="12">
              <el-form-item label="支持文件索引">
                <el-input :model-value="row.qcc_support_index" :disabled="readonly" @update:model-value="(v) => emitUpdate('qcc_support_index', v)" />
              </el-form-item>
            </el-col>
            <el-col :span="24">
              <el-form-item label="企查查备注">
                <el-input :model-value="row.qcc_remark" :disabled="readonly" type="textarea" :rows="2" @update:model-value="(v) => emitUpdate('qcc_remark', v)" />
              </el-form-item>
            </el-col>
          </el-row>
          <!-- Conditional: address mismatch verify fields -->
          <template v-if="row.address_match === 'inconsistent'">
            <el-row :gutter="16">
              <el-col :span="12">
                <!--
                  源模板 X0-2!L7 数据验证给了 6 个固定核实方式（发票/合同地址核实、
                  电话核实、官网/公告查询、地图查询、邮件确认、其他方式）——
                  改造前是自由文本，审计师各写各的，无法按方式统计。
                  `allow-create` 保留自由输入（历史值仍可显示）。
                  spec: h0-confirmation-source-fidelity-and-linkage R8.3 / R7.5
                -->
                <el-form-item label="地址核实方式">
                  <el-select
                    :model-value="row.address_verify_result"
                    :disabled="readonly"
                    filterable
                    allow-create
                    default-first-option
                    clearable
                    placeholder="请选择核实方式"
                    @update:model-value="(v: any) => emitUpdate('address_verify_result', v)"
                  >
                    <el-option v-for="opt in addrVerifyOptions" :key="opt" :label="opt" :value="opt" />
                  </el-select>
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

          <!--
            第二次发函的被函证单位信息（源模板 X0-2 AF6:AK6 六列）。
            第一次被退回后重新核实到的地址/邮编/联系人/电话/传真 + 是否核查一致；
            改造前平台无这六列落笔位置。
            spec: h0-confirmation-source-fidelity-and-linkage R8.1 / R8.5
          -->
          <div class="entity-verify-detail__subhead">第二次发函的被函证单位信息（重新核实）</div>
          <el-row :gutter="16">
            <el-col :span="12">
              <el-form-item label="地址">
                <el-input :model-value="row.second_entity_address" :disabled="readonly" @update:model-value="(v) => emitUpdate('second_entity_address', v)" />
              </el-form-item>
            </el-col>
            <el-col :span="12">
              <el-form-item label="邮编">
                <el-input :model-value="row.second_entity_zipcode" :disabled="readonly" @update:model-value="(v) => emitUpdate('second_entity_zipcode', v)" />
              </el-form-item>
            </el-col>
            <el-col :span="12">
              <el-form-item label="联系人">
                <el-input :model-value="row.second_contact_person" :disabled="readonly" @update:model-value="(v) => emitUpdate('second_contact_person', v)" />
              </el-form-item>
            </el-col>
            <el-col :span="12">
              <el-form-item label="联系电话">
                <el-input :model-value="row.second_contact_phone" :disabled="readonly" @update:model-value="(v) => emitUpdate('second_contact_phone', v)" />
              </el-form-item>
            </el-col>
            <el-col :span="12">
              <el-form-item label="传真">
                <el-input :model-value="row.second_fax" :disabled="readonly" @update:model-value="(v) => emitUpdate('second_fax', v)" />
              </el-form-item>
            </el-col>
            <el-col :span="12">
              <el-form-item label="信息核查一致">
                <el-select :model-value="row.second_info_verified" :disabled="readonly" clearable placeholder="请选择" @update:model-value="(v: any) => emitUpdate('second_info_verified', v)">
                  <el-option label="是" value="是" /><el-option label="否" value="否" />
                </el-select>
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

      <!-- Stage 6: 回函核实（X0-2 回函核对记录块） -->
      <el-collapse-item title="回函核实" name="reply_verify">
        <el-form label-width="90px" size="small" class="entity-verify-detail__form">
          <el-alert
            type="info"
            :closable="false"
            show-icon
            class="entity-verify-detail__x07-note"
          >回函方式/是否原件/是否直接接收 以「回函可靠性核对（X0-7）」为唯一录入位置，此处只读引用。</el-alert>
          <el-row :gutter="16">
            <el-col :span="12">
              <el-form-item label="是否原件">
                <el-select :model-value="row.is_original" disabled placeholder="详见 X0-7">
                  <el-option label="是" value="是" /><el-option label="否" value="否" /><el-option label="不适用" value="不适用" />
                </el-select>
              </el-form-item>
            </el-col>
            <el-col :span="12">
              <el-form-item label="直接收到">
                <el-select :model-value="row.direct_received" disabled placeholder="详见 X0-7">
                  <el-option label="是" value="是" /><el-option label="否" value="否" /><el-option label="不适用" value="不适用" />
                </el-select>
              </el-form-item>
            </el-col>
            <el-col :span="12">
              <el-form-item label="回函发出地址">
                <el-input :model-value="row.reply_from_addr" :disabled="readonly" @update:model-value="(v) => emitUpdate('reply_from_addr', v)" />
              </el-form-item>
            </el-col>
            <el-col :span="12">
              <el-form-item label="回函寄件人">
                <el-input :model-value="row.reply_sender" :disabled="readonly" @update:model-value="(v) => emitUpdate('reply_sender', v)" />
              </el-form-item>
            </el-col>
            <el-col :span="12">
              <el-form-item label="回函电话">
                <el-input :model-value="row.reply_phone" :disabled="readonly" @update:model-value="(v) => emitUpdate('reply_phone', v)" />
              </el-form-item>
            </el-col>
            <el-col :span="12">
              <el-form-item label="单位名一致">
                <el-select :model-value="row.reply_name_match" :disabled="readonly" @update:model-value="(v) => emitUpdate('reply_name_match', v)" placeholder="请选择" clearable>
                  <el-option label="一致" value="consistent" /><el-option label="不一致" value="inconsistent" /><el-option label="不适用" value="pending" />
                </el-select>
              </el-form-item>
            </el-col>
            <el-col :span="12">
              <el-form-item label="地址一致">
                <el-select :model-value="row.reply_addr_match" :disabled="readonly" @update:model-value="(v) => emitUpdate('reply_addr_match', v)" placeholder="请选择" clearable>
                  <el-option label="一致" value="consistent" /><el-option label="不一致" value="inconsistent" /><el-option label="不适用" value="pending" />
                </el-select>
              </el-form-item>
            </el-col>
            <el-col :span="12">
              <el-form-item label="电话一致">
                <el-select :model-value="row.reply_phone_match" :disabled="readonly" @update:model-value="(v) => emitUpdate('reply_phone_match', v)" placeholder="请选择" clearable>
                  <el-option label="一致" value="consistent" /><el-option label="不一致" value="inconsistent" /><el-option label="不适用" value="pending" />
                </el-select>
              </el-form-item>
            </el-col>
            <el-col :span="24">
              <el-form-item :required="hasReplyInconsistency">
                <template #label>
                  <span :class="{ 'entity-verify-detail__required-label': hasReplyInconsistency }">不一致说明</span>
                </template>
                <el-input
                  :model-value="row.reply_inconsistent_note"
                  :disabled="readonly"
                  type="textarea"
                  :rows="2"
                  :placeholder="hasReplyInconsistency ? '存在不一致项，请填写说明' : '如有不一致请说明'"
                  @update:model-value="(v) => emitUpdate('reply_inconsistent_note', v)"
                />
              </el-form-item>
            </el-col>
            <el-col :span="12">
              <el-form-item label="核实证据索引">
                <el-input :model-value="row.verify_evidence_index" :disabled="readonly" @update:model-value="(v) => emitUpdate('verify_evidence_index', v)" />
              </el-form-item>
            </el-col>
            <el-col :span="12">
              <el-form-item label="跟函控制索引">
                <el-input :model-value="row.followup_control_index" :disabled="readonly" @update:model-value="(v) => emitUpdate('followup_control_index', v)" />
              </el-form-item>
            </el-col>
          </el-row>
        </el-form>
      </el-collapse-item>
    </el-collapse>

    <!--
      源模板 X0-2 C25/C26 两条审计说明（电子函证方式的核对豁免与记录要求）——
      只读方法论上下文，就地展示避免审计师对电子函证做无谓的地址核对。
      spec: h0-confirmation-source-fidelity-and-linkage R8.6
    -->
    <div class="entity-verify-detail__src-hint">
      <div class="entity-verify-detail__src-hint-title">审计说明（源模板）</div>
      <p v-for="(t, i) in SOURCE_AUDIT_NOTES" :key="i">{{ t }}</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import type { EntityVerifyRow } from './entityVerifyTypes'
import FieldHintIcon from './FieldHintIcon.vue'
import { CONFIRMATION_DICTS, fallbackOptions } from '../coordination/confirmationDicts'

/**
 * 地址不一致的核实方式 —— 源模板 X0-2!L7 数据验证 6 项，单一真源在
 * `CONFIRMATION_DICT_FALLBACK`（六枢纽同构）。
 * spec: h0-confirmation-source-fidelity-and-linkage R7.5 / R8.3
 */
const addrVerifyOptions = fallbackOptions(CONFIRMATION_DICTS.ADDR_VERIFY)

/** 源模板 X0-2 C25/C26 两条审计说明（逐字，只读方法论上下文） */
const SOURCE_AUDIT_NOTES = [
  '1.采用电子函证方式的无需核对发函地址信息，无需核对回函发出地址、回函寄件人信息等；',
  '2.采用电子函证方式的应记录并检查回函能够证明电子地址或身份的信息，关注被审计单位、注册会计师和被询证者在电子询证函平台操作的具体时间、回函经办人（如适用）、意见反馈等信息（如适用）',
]

const props = defineProps<{
  row: EntityVerifyRow | null
  readonly: boolean
  dictData: Record<string, any[]>
}>()

const emit = defineEmits<{
  (e: 'update', field: string, value: any): void
}>()

const activeStages = ref<string[]>(['basic', 'qcc', 'send', 'reply', 'reply_verify'])

/** 回函核实块三项一致性判定存在「不一致」时要求填说明（Property 7） */
const hasReplyInconsistency = computed(() => {
  const r = props.row
  if (!r) return false
  return [r.reply_name_match, r.reply_addr_match, r.reply_phone_match].includes('inconsistent')
})

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

.entity-verify-detail__x07-note {
  margin-bottom: 10px;
}

.entity-verify-detail__required-label::before {
  content: '*';
  color: var(--el-color-danger);
  margin-right: 4px;
}
.entity-verify-detail__subhead {
  font-size: 13px;
  font-weight: 500;
  color: var(--el-text-color-regular);
  margin: 4px 0 8px;
  padding-left: 6px;
  border-left: 3px solid var(--el-color-primary-light-5);
}
.entity-verify-detail__src-hint {
  margin-top: 12px;
  border-left: 3px solid #e6a23c;
  background: #fdf6ec;
  padding: 8px 12px;
  font-size: 12px;
  line-height: 1.65;
  color: var(--el-text-color-regular);
}
.entity-verify-detail__src-hint-title {
  font-weight: 500;
  margin-bottom: 3px;
}
.entity-verify-detail__src-hint p {
  margin: 0;
}
</style>
