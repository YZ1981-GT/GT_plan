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
            <el-form :model="row" label-width="90px" size="small" :disabled="readonly">
              <el-row :gutter="16">
                <el-col :span="12">
                  <el-form-item label="函证索引号">
                    <el-input :model-value="row.confirm_index" @update:model-value="update('confirm_index', $event)" />
                  </el-form-item>
                </el-col>
                <el-col :span="12">
                  <el-form-item label="被函证单位">
                    <el-input :model-value="row.entity_name" @update:model-value="update('entity_name', $event)" />
                  </el-form-item>
                </el-col>
                <el-col :span="12">
                  <el-form-item label="单位地址">
                    <el-input :model-value="row.entity_address" @update:model-value="update('entity_address', $event)" />
                  </el-form-item>
                </el-col>
                <el-col :span="12">
                  <el-form-item label="跟函人员">
                    <el-input :model-value="row.followup_person" @update:model-value="update('followup_person', $event)" />
                  </el-form-item>
                </el-col>
                <el-col :span="12">
                  <el-form-item label="跟函日期">
                    <el-date-picker :model-value="row.followup_date" type="date" value-format="YYYY-MM-DD" @update:model-value="update('followup_date', $event)" />
                  </el-form-item>
                </el-col>
              </el-row>
            </el-form>
          </div>

          <!-- Section 2: 确认场景 -->
          <div class="followup-detail__section">
            <h4 class="followup-detail__section-title">确认场景</h4>
            <el-form :model="row" label-width="90px" size="small" :disabled="readonly">
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
            <el-form :model="row" label-width="90px" size="small" :disabled="readonly">
              <el-row :gutter="16">
                <el-col :span="12">
                  <el-form-item label="确认地点">
                    <el-input :model-value="row.confirm_location" @update:model-value="update('confirm_location', $event)" />
                  </el-form-item>
                </el-col>
                <el-col :span="12">
                  <el-form-item label="确认时间">
                    <el-input :model-value="row.confirm_time" @update:model-value="update('confirm_time', $event)" />
                  </el-form-item>
                </el-col>
                <el-col :span="12">
                  <el-form-item label="联系人">
                    <el-input :model-value="row.confirm_contact" @update:model-value="update('confirm_contact', $event)" />
                  </el-form-item>
                </el-col>
                <el-col :span="12">
                  <el-form-item label="身份已验证">
                    <el-select :model-value="row.confirm_identity_verified" @update:model-value="update('confirm_identity_verified', $event)">
                      <el-option value="是" label="是" />
                      <el-option value="否" label="否" />
                      <el-option value="不适用" label="不适用" />
                    </el-select>
                  </el-form-item>
                </el-col>
              </el-row>
            </el-form>
          </div>

          <!-- Section 4: 留函跟踪字段（later_follow） -->
          <div v-if="row.scenario === 'later_follow'" class="followup-detail__section">
            <h4 class="followup-detail__section-title">留函跟踪</h4>
            <el-form :model="row" label-width="90px" size="small" :disabled="readonly">
              <el-row :gutter="16">
                <el-col :span="12">
                  <el-form-item label="留函日期">
                    <el-date-picker :model-value="row.leave_date" type="date" value-format="YYYY-MM-DD" @update:model-value="update('leave_date', $event)" />
                  </el-form-item>
                </el-col>
                <el-col :span="12">
                  <el-form-item label="留函联系人">
                    <el-input :model-value="row.leave_contact" @update:model-value="update('leave_contact', $event)" />
                  </el-form-item>
                </el-col>
                <el-col :span="12">
                  <el-form-item label="致电日期">
                    <el-date-picker :model-value="row.follow_call_date" type="date" value-format="YYYY-MM-DD" @update:model-value="update('follow_call_date', $event)" />
                  </el-form-item>
                </el-col>
                <el-col :span="12">
                  <el-form-item label="致电号码">
                    <el-input :model-value="row.follow_call_phone" @update:model-value="update('follow_call_phone', $event)" placeholder="须取自独立公开来源" />
                  </el-form-item>
                </el-col>
                <el-col :span="24">
                  <el-form-item label="致电结果">
                    <el-input type="textarea" :rows="2" :model-value="row.follow_call_result" @update:model-value="update('follow_call_result', $event)" />
                  </el-form-item>
                </el-col>
              </el-row>
            </el-form>
          </div>

          <!-- Section 5: 三项控制检查 -->
          <div class="followup-detail__section">
            <h4 class="followup-detail__section-title">
              三项控制检查
              <el-tooltip content="跟函时需验证对方处理函证回复的三项控制要素，用于评估回函可靠性" placement="top">
                <el-icon style="margin-left:4px;color:#909399;cursor:help"><QuestionFilled /></el-icon>
              </el-tooltip>
            </h4>
            <el-form :model="row" label-width="140px" size="small" :disabled="readonly">
              <el-form-item>
                <template #label>
                  <el-tooltip content="是否了解了对方单位处理函证回复的内部流程（收函→核对→签章→寄回）" placement="top">
                    <span style="cursor:help;border-bottom:1px dashed #909399">了解处理流程</span>
                  </el-tooltip>
                </template>
                <el-select :model-value="row.control_process" @update:model-value="update('control_process', $event)">
                  <el-option value="yes" label="是" />
                  <el-option value="no" label="否" />
                  <el-option value="na" label="不适用" />
                </el-select>
              </el-form-item>
              <el-form-item>
                <template #label>
                  <el-tooltip content="是否核实了回复人的身份及其是否有权代表公司确认函证内容" placement="top">
                    <span style="cursor:help;border-bottom:1px dashed #909399">确认身份权限</span>
                  </el-tooltip>
                </template>
                <el-select :model-value="row.control_identity" @update:model-value="update('control_identity', $event)">
                  <el-option value="yes" label="是" />
                  <el-option value="no" label="否" />
                  <el-option value="na" label="不适用" />
                </el-select>
              </el-form-item>
              <el-form-item>
                <template #label>
                  <el-tooltip content="观察到对方是否按正常业务流程处理了回函（非临时指派、非异常加急操作）" placement="top">
                    <span style="cursor:help;border-bottom:1px dashed #909399">按正常流程处理</span>
                  </el-tooltip>
                </template>
                <el-select :model-value="row.control_normal_flow" @update:model-value="update('control_normal_flow', $event)">
                  <el-option value="yes" label="是" />
                  <el-option value="no" label="否" />
                  <el-option value="na" label="不适用" />
                </el-select>
              </el-form-item>
              <el-form-item label="证据描述">
                <div style="display:flex;gap:6px;align-items:flex-start;width:100%">
                  <el-input
                    type="textarea"
                    :rows="2"
                    :model-value="row.control_evidence"
                    @update:model-value="update('control_evidence', $event)"
                    placeholder="记录观察到的控制执行证据（如：接收人核对后在回执上签字盖章）"
                    style="flex:1"
                  />
                  <el-button
                    v-if="!readonly"
                    size="small"
                    type="primary"
                    plain
                    :loading="aiEvidenceLoading"
                    @click="handleAiEvidence"
                    style="flex-shrink:0;margin-top:2px"
                  >
                    AI填充
                  </el-button>
                </div>
              </el-form-item>
              <el-form-item label="控制结论">
                <el-tag
                  v-if="row.control_conclusion"
                  :type="conclusionTagType(row.control_conclusion)"
                  size="small"
                >
                  {{ conclusionLabel(row.control_conclusion) }}
                </el-tag>
                <span v-else class="followup-detail__empty">自动派生（三项全"是"→通过）</span>
              </el-form-item>
            </el-form>
          </div>

          <!-- Section 6: 签名 -->
          <div class="followup-detail__section">
            <h4 class="followup-detail__section-title">签名</h4>
            <el-form :model="row" label-width="90px" size="small" :disabled="readonly">
              <el-row :gutter="16">
                <el-col :span="12">
                  <el-form-item label="签名人">
                    <el-input :model-value="row.sign_person" @update:model-value="update('sign_person', $event)" />
                  </el-form-item>
                </el-col>
                <el-col :span="12">
                  <el-form-item label="签名日期">
                    <el-date-picker :model-value="row.sign_date" type="date" value-format="YYYY-MM-DD" @update:model-value="update('sign_date', $event)" />
                  </el-form-item>
                </el-col>
                <el-col :span="12">
                  <el-form-item label="签名状态">
                    <el-switch :model-value="row.sign_status === 'signed'" active-text="已签" inactive-text="未签" @change="update('sign_status', $event ? 'signed' : 'unsigned')" />
                  </el-form-item>
                </el-col>
              </el-row>
            </el-form>
          </div>

          <!-- Section: 回函收回补记（条件展开） -->
          <div class="followup-detail__section">
            <h4 class="followup-detail__section-title">回函收回补记</h4>
            <el-form :model="row" label-width="90px" size="small" :disabled="readonly">
              <el-row :gutter="16">
                <el-col :span="12">
                  <el-form-item label="已收回">
                    <el-switch :model-value="row.later_received" @change="update('later_received', $event)" />
                  </el-form-item>
                </el-col>
              </el-row>
              <el-row v-if="row.later_received" :gutter="16">
                <el-col :span="12">
                  <el-form-item label="收回日期">
                    <el-date-picker :model-value="row.received_date" type="date" value-format="YYYY-MM-DD" @update:model-value="update('received_date', $event)" />
                  </el-form-item>
                </el-col>
                <el-col :span="12">
                  <el-form-item label="收回办公室">
                    <el-input :model-value="row.received_office" @update:model-value="update('received_office', $event)" />
                  </el-form-item>
                </el-col>
                <el-col :span="12">
                  <el-form-item label="函证索引号">
                    <el-input :model-value="row.received_confirm_index" @update:model-value="update('received_confirm_index', $event)" />
                  </el-form-item>
                </el-col>
              </el-row>
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
import { ref } from 'vue'
import { QuestionFilled } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import type { FollowupRow } from './followupTypes'

const props = defineProps<{
  row: FollowupRow | null
  readonly: boolean
  dictData?: Record<string, any[]>
}>()

const emit = defineEmits<{
  (e: 'update', field: string, value: any): void
}>()

const aiEvidenceLoading = ref(false)

function update(field: string, value: any) {
  emit('update', field, value)
}

function handleAiEvidence() {
  if (!props.row) return

  aiEvidenceLoading.value = true
  try {
    const row = props.row
    const entity = row.entity_name || '被函证单位'
    const contact = row.confirm_contact || row.leave_contact || '联系人'
    const process = row.control_process === 'yes' ? '已了解' : '未了解'
    const identity = row.control_identity === 'yes' ? '已确认' : '未确认'
    const normalFlow = row.control_normal_flow === 'yes' ? '正常' : '异常'

    let evidence = ''
    if (row.scenario === 'immediate') {
      evidence = `本人到达${entity}后，${process}其内部函证回复流程。`
        + `经核实，回复人${contact}${identity}具备签署权限。`
        + `观察到对方按${normalFlow}业务流程处理了回函事宜`
        + (normalFlow === '正常' ? '，接收人核对金额后在回执上签字盖章。' : '，存在异常情况需进一步关注。')
    } else {
      evidence = `本人将询证函留置于${contact}处后，`
        + `${process}其内部收函处理机制。`
        + `后续致电跟踪时，${identity}对方身份及处理权限，`
        + `对方表示${normalFlow === '正常' ? '已按正常流程处理并寄回回函' : '处理过程存在异常，需关注回函可靠性'}。`
    }

    emit('update', 'control_evidence', evidence)
    ElMessage.success('已生成证据描述（仅供参考，请根据实际情况修改）')
  } catch (e: any) {
    ElMessage.error('生成失败：' + (e?.message || '未知错误'))
  } finally {
    aiEvidenceLoading.value = false
  }
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
