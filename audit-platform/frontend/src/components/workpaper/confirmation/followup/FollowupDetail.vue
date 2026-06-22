<template>
  <div class="followup-detail">
    <template v-if="!row">
      <el-empty description="请选择一条记录" :image-size="80" />
    </template>
    <template v-else>
      <div class="followup-detail__layout">
        <!-- Left: Form fields -->
        <div class="followup-detail__form">
          <!-- Section 1: 基本信息 -->
          <div class="followup-detail__section">
            <h4 class="followup-detail__section-title">基本信息</h4>
            <el-form :model="row" label-width="100px" size="small" :disabled="readonly">
              <el-form-item label="函证索引号">
                <el-input :model-value="row.confirm_index" @update:model-value="update('confirm_index', $event)" />
              </el-form-item>
              <el-form-item label="被函证单位">
                <el-input :model-value="row.entity_name" @update:model-value="update('entity_name', $event)" />
              </el-form-item>
              <el-form-item label="单位地址">
                <el-input :model-value="row.entity_address" @update:model-value="update('entity_address', $event)" />
              </el-form-item>
              <el-form-item label="跟函人员">
                <el-input :model-value="row.followup_person" @update:model-value="update('followup_person', $event)" />
              </el-form-item>
              <el-form-item label="跟函日期">
                <el-date-picker
                  :model-value="row.followup_date"
                  type="date"
                  value-format="YYYY-MM-DD"
                  @update:model-value="update('followup_date', $event)"
                />
              </el-form-item>
            </el-form>
          </div>

          <!-- Section 2: 确认场景 -->
          <div class="followup-detail__section">
            <h4 class="followup-detail__section-title">确认场景</h4>
            <el-form :model="row" label-width="100px" size="small" :disabled="readonly">
              <el-form-item label="场景选择">
                <el-radio-group :model-value="row.scenario" @update:model-value="update('scenario', $event)">
                  <el-radio value="immediate">现场即时确认</el-radio>
                  <el-radio value="later_follow">无法即时确认留函</el-radio>
                </el-radio-group>
              </el-form-item>
            </el-form>
          </div>

          <!-- Section 3: 现场确认字段（immediate） -->
          <div v-if="row.scenario === 'immediate'" class="followup-detail__section">
            <h4 class="followup-detail__section-title">现场确认</h4>
            <el-form :model="row" label-width="100px" size="small" :disabled="readonly">
              <el-form-item label="确认地点">
                <el-input :model-value="row.confirm_location" @update:model-value="update('confirm_location', $event)" />
              </el-form-item>
              <el-form-item label="确认时间">
                <el-input :model-value="row.confirm_time" @update:model-value="update('confirm_time', $event)" />
              </el-form-item>
              <el-form-item label="联系人">
                <el-input :model-value="row.confirm_contact" @update:model-value="update('confirm_contact', $event)" />
              </el-form-item>
              <el-form-item label="身份已验证">
                <el-select :model-value="row.confirm_identity_verified" @update:model-value="update('confirm_identity_verified', $event)">
                  <el-option value="是" label="是" />
                  <el-option value="否" label="否" />
                  <el-option value="不适用" label="不适用" />
                </el-select>
              </el-form-item>
            </el-form>
          </div>

          <!-- Section 4: 留函跟踪字段（later_follow） -->
          <div v-if="row.scenario === 'later_follow'" class="followup-detail__section">
            <h4 class="followup-detail__section-title">留函跟踪</h4>
            <el-form :model="row" label-width="110px" size="small" :disabled="readonly">
              <el-form-item label="留函日期">
                <el-date-picker
                  :model-value="row.leave_date"
                  type="date"
                  value-format="YYYY-MM-DD"
                  @update:model-value="update('leave_date', $event)"
                />
              </el-form-item>
              <el-form-item label="留函联系人">
                <el-input :model-value="row.leave_contact" @update:model-value="update('leave_contact', $event)" />
              </el-form-item>
              <el-form-item label="致电日期">
                <el-date-picker
                  :model-value="row.follow_call_date"
                  type="date"
                  value-format="YYYY-MM-DD"
                  @update:model-value="update('follow_call_date', $event)"
                />
              </el-form-item>
              <el-form-item label="致电号码">
                <el-input
                  :model-value="row.follow_call_phone"
                  @update:model-value="update('follow_call_phone', $event)"
                  placeholder="须取自独立公开来源"
                />
              </el-form-item>
              <el-form-item label="致电结果">
                <el-input
                  type="textarea"
                  :rows="2"
                  :model-value="row.follow_call_result"
                  @update:model-value="update('follow_call_result', $event)"
                />
              </el-form-item>
            </el-form>
          </div>

          <!-- Section 5: 三项控制检查 -->
          <div class="followup-detail__section">
            <h4 class="followup-detail__section-title">三项控制检查</h4>
            <el-form :model="row" label-width="140px" size="small" :disabled="readonly">
              <el-form-item label="了解处理流程">
                <el-select :model-value="row.control_process" @update:model-value="update('control_process', $event)">
                  <el-option value="yes" label="是" />
                  <el-option value="no" label="否" />
                  <el-option value="na" label="不适用" />
                </el-select>
              </el-form-item>
              <el-form-item label="确认身份权限">
                <el-select :model-value="row.control_identity" @update:model-value="update('control_identity', $event)">
                  <el-option value="yes" label="是" />
                  <el-option value="no" label="否" />
                  <el-option value="na" label="不适用" />
                </el-select>
              </el-form-item>
              <el-form-item label="按正常流程处理">
                <el-select :model-value="row.control_normal_flow" @update:model-value="update('control_normal_flow', $event)">
                  <el-option value="yes" label="是" />
                  <el-option value="no" label="否" />
                  <el-option value="na" label="不适用" />
                </el-select>
              </el-form-item>
              <el-form-item label="证据描述">
                <el-input
                  type="textarea"
                  :rows="2"
                  :model-value="row.control_evidence"
                  @update:model-value="update('control_evidence', $event)"
                />
              </el-form-item>
              <el-form-item label="控制结论">
                <el-tag
                  v-if="row.control_conclusion"
                  :type="conclusionTagType(row.control_conclusion)"
                  size="small"
                >
                  {{ conclusionLabel(row.control_conclusion) }}
                </el-tag>
                <span v-else class="followup-detail__empty">自动派生</span>
              </el-form-item>
            </el-form>
          </div>

          <!-- Section 6: 签名 -->
          <div class="followup-detail__section">
            <h4 class="followup-detail__section-title">签名</h4>
            <el-form :model="row" label-width="100px" size="small" :disabled="readonly">
              <el-form-item label="签名人">
                <el-input :model-value="row.sign_person" @update:model-value="update('sign_person', $event)" />
              </el-form-item>
              <el-form-item label="签名日期">
                <el-date-picker
                  :model-value="row.sign_date"
                  type="date"
                  value-format="YYYY-MM-DD"
                  @update:model-value="update('sign_date', $event)"
                />
              </el-form-item>
              <el-form-item label="签名状态">
                <el-switch
                  :model-value="row.sign_status === 'signed'"
                  active-text="已签"
                  inactive-text="未签"
                  @change="update('sign_status', $event ? 'signed' : 'unsigned')"
                />
              </el-form-item>
            </el-form>
          </div>

          <!-- Section: 回函收回补记（条件展开） -->
          <div class="followup-detail__section">
            <h4 class="followup-detail__section-title">回函收回补记</h4>
            <el-form :model="row" label-width="100px" size="small" :disabled="readonly">
              <el-form-item label="已收回">
                <el-switch
                  :model-value="row.later_received"
                  @change="update('later_received', $event)"
                />
              </el-form-item>
              <template v-if="row.later_received">
                <el-form-item label="收回日期">
                  <el-date-picker
                    :model-value="row.received_date"
                    type="date"
                    value-format="YYYY-MM-DD"
                    @update:model-value="update('received_date', $event)"
                  />
                </el-form-item>
                <el-form-item label="收回办公室">
                  <el-input :model-value="row.received_office" @update:model-value="update('received_office', $event)" />
                </el-form-item>
                <el-form-item label="函证索引号">
                  <el-input :model-value="row.received_confirm_index" @update:model-value="update('received_confirm_index', $event)" />
                </el-form-item>
              </template>
            </el-form>
          </div>
        </div>

        <!-- Right: Memo preview -->
        <div class="followup-detail__memo">
          <slot name="memo-preview" />
        </div>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import type { FollowupRow } from './followupTypes'

defineProps<{
  row: FollowupRow | null
  readonly: boolean
  dictData?: Record<string, any[]>
}>()

const emit = defineEmits<{
  (e: 'update', field: string, value: any): void
}>()

function update(field: string, value: any) {
  emit('update', field, value)
}

function conclusionTagType(conclusion: string): '' | 'success' | 'danger' | 'info' {
  if (conclusion === 'pass') return 'success'
  if (conclusion === 'fail') return 'danger'
  return 'info'
}

function conclusionLabel(conclusion: string): string {
  if (conclusion === 'pass') return '通过'
  if (conclusion === 'fail') return '未通过'
  return '未完成'
}
</script>

<style scoped>
.followup-detail__layout {
  display: grid;
  grid-template-columns: 1fr 380px;
  gap: 16px;
}

.followup-detail__form {
  overflow-y: auto;
  max-height: calc(100vh - 200px);
}

.followup-detail__memo {
  position: sticky;
  top: 0;
  align-self: start;
}

.followup-detail__section {
  margin-bottom: 16px;
  padding: 12px;
  background: #fafafa;
  border-radius: 6px;
}

.followup-detail__section-title {
  margin: 0 0 12px;
  font-size: 14px;
  font-weight: 600;
  color: #303133;
}

.followup-detail__empty {
  color: #c0c4cc;
  font-size: 12px;
}

@media (max-width: 1200px) {
  .followup-detail__layout {
    grid-template-columns: 1fr;
  }
}
</style>
