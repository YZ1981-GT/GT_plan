<template>
  <div v-if="company" class="diff-checklist-detail">
    <div class="diff-checklist-detail__title">
      <span>{{ company.entity_name || '请在左侧表格填写单位名称' }}</span>
      <el-tag :type="statusTagType(company.status)" size="small" effect="dark">
        {{ statusLabel(company.status) }}
      </el-tag>
      <span v-if="company.subject" class="diff-checklist-detail__subject">
        科目：{{ company.subject }}
      </span>
    </div>

    <!-- A-I 公式链结构化展示 -->
    <div class="diff-checklist-detail__formula">
      <!-- ═══ 对方（回函方）调节 ═══ -->
      <div class="diff-checklist-detail__section diff-checklist-detail__section--reply">
        <div class="diff-checklist-detail__section-title">对方（回函方）调节</div>

        <!-- A: 回函金额 -->
        <div class="diff-checklist-detail__step">
          <span class="diff-checklist-detail__label">
            A. 回函金额（对方确认余额）
            <el-tooltip content="来自回函确认的余额，即对方账面反映的金额" placement="top">
              <el-icon :size="12"><InfoFilled /></el-icon>
            </el-tooltip>
          </span>
          <el-input-number
            v-if="!readonly"
            :model-value="company.a_reply_amount"
            :controls="false"
            :precision="2"
            size="small"
            class="diff-checklist-detail__input"
            @change="(val: number) => $emit('update', company._row_id!, 'a_reply_amount', val)"
          />
          <span v-else class="diff-checklist-detail__value">{{ formatAmount(company.a_reply_amount) }}</span>
        </div>

        <!-- B: 对方已收我方未付 -->
        <DetailSubTable
          section="b"
          section-label="B. 加：对方已收我方未付（我方未达）"
          :rows="company.b_rows ?? []"
          :total="company.b_total ?? 0"
          :readonly="readonly"
          @add-row="$emit('add-sub-row', company._row_id!, 'b')"
          @delete-row="(rowId: string) => $emit('delete-sub-row', company._row_id!, 'b', rowId)"
          @update-row="(rowId: string, field: string, val: any) => $emit('update-sub-row', company._row_id!, 'b', rowId, field, val)"
        />

        <!-- C: 我方已付对方未收 -->
        <DetailSubTable
          section="c"
          section-label="C. 减：我方已付对方未收（对方未达）"
          :rows="company.c_rows ?? []"
          :total="company.c_total ?? 0"
          :readonly="readonly"
          @add-row="$emit('add-sub-row', company._row_id!, 'c')"
          @delete-row="(rowId: string) => $emit('delete-sub-row', company._row_id!, 'c', rowId)"
          @update-row="(rowId: string, field: string, val: any) => $emit('update-sub-row', company._row_id!, 'c', rowId, field, val)"
        />

        <!-- D: 调节后对方余额 -->
        <div class="diff-checklist-detail__step diff-checklist-detail__step--computed">
          <span class="diff-checklist-detail__label">
            D. 调节后对方余额 = A + B - C
            <el-tooltip content="自动计算：回函金额 + 对方已收我方未付 - 我方已付对方未收" placement="top">
              <el-icon :size="12"><InfoFilled /></el-icon>
            </el-tooltip>
          </span>
          <span class="diff-checklist-detail__value diff-checklist-detail__value--computed">
            {{ formatAmount(company.d_adjusted_reply) }}
          </span>
        </div>
      </div>

      <!-- ═══ 我方（账面方）调节 ═══ -->
      <div class="diff-checklist-detail__section diff-checklist-detail__section--book">
        <div class="diff-checklist-detail__section-title">我方（账面方）调节</div>

        <!-- E: 账面金额 -->
        <div class="diff-checklist-detail__step">
          <span class="diff-checklist-detail__label">
            E. 账面金额（我方账面余额）
            <el-tooltip content="来自我方账面记录的余额金额（即发函金额）" placement="top">
              <el-icon :size="12"><InfoFilled /></el-icon>
            </el-tooltip>
          </span>
          <el-input-number
            v-if="!readonly"
            :model-value="company.e_book_amount"
            :controls="false"
            :precision="2"
            size="small"
            class="diff-checklist-detail__input"
            @change="(val: number) => $emit('update', company._row_id!, 'e_book_amount', val)"
          />
          <span v-else class="diff-checklist-detail__value">{{ formatAmount(company.e_book_amount) }}</span>
        </div>

        <!-- F: 我方已收对方未付 -->
        <DetailSubTable
          section="f"
          section-label="F. 加：我方已收对方未付（对方未达）"
          :rows="company.f_rows ?? []"
          :total="company.f_total ?? 0"
          :readonly="readonly"
          @add-row="$emit('add-sub-row', company._row_id!, 'f')"
          @delete-row="(rowId: string) => $emit('delete-sub-row', company._row_id!, 'f', rowId)"
          @update-row="(rowId: string, field: string, val: any) => $emit('update-sub-row', company._row_id!, 'f', rowId, field, val)"
        />

        <!-- G: 对方已付我方未收 -->
        <DetailSubTable
          section="g"
          section-label="G. 减：对方已付我方未收（我方未达）"
          :rows="company.g_rows ?? []"
          :total="company.g_total ?? 0"
          :readonly="readonly"
          @add-row="$emit('add-sub-row', company._row_id!, 'g')"
          @delete-row="(rowId: string) => $emit('delete-sub-row', company._row_id!, 'g', rowId)"
          @update-row="(rowId: string, field: string, val: any) => $emit('update-sub-row', company._row_id!, 'g', rowId, field, val)"
        />

        <!-- H: 调节后我方余额 -->
        <div class="diff-checklist-detail__step diff-checklist-detail__step--computed">
          <span class="diff-checklist-detail__label">
            H. 调节后我方余额 = E + F - G
            <el-tooltip content="自动计算：账面金额 + 我方已收对方未付 - 对方已付我方未收" placement="top">
              <el-icon :size="12"><InfoFilled /></el-icon>
            </el-tooltip>
          </span>
          <span class="diff-checklist-detail__value diff-checklist-detail__value--computed">
            {{ formatAmount(company.h_adjusted_book) }}
          </span>
        </div>
      </div>

      <!-- ═══ 最终差异 ═══ -->
      <div
        :class="[
          'diff-checklist-detail__section',
          'diff-checklist-detail__section--result',
          { 'diff-checklist-detail__section--alert': (company.i_final_diff ?? 0) !== 0 },
        ]"
      >
        <div class="diff-checklist-detail__step diff-checklist-detail__step--final">
          <span class="diff-checklist-detail__label">
            I. 最终差异 = H - D
            <el-tooltip content="双向调节后差异：=0 表示已平衡，≠0 表示仍有未解释差异" placement="top">
              <el-icon :size="12"><InfoFilled /></el-icon>
            </el-tooltip>
          </span>
          <span
            :class="[
              'diff-checklist-detail__value',
              'diff-checklist-detail__value--final',
              { 'diff-checklist-detail__value--zero': (company.i_final_diff ?? 0) === 0 },
              { 'diff-checklist-detail__value--nonzero': (company.i_final_diff ?? 0) !== 0 },
            ]"
          >
            {{ formatAmount(company.i_final_diff) }}
          </span>
        </div>
      </div>

      <!-- 审计说明（逐公司） -->
      <div class="diff-checklist-detail__note">
        <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:4px">
          <span class="diff-checklist-detail__label">审计说明</span>
          <el-button
            v-if="!readonly"
            size="small"
            type="primary"
            plain
            @click="handleAiNote"
          >
            AI 生成
          </el-button>
        </div>
        <el-input
          v-if="!readonly"
          :model-value="company.audit_note"
          type="textarea"
          :autosize="{ minRows: 2, maxRows: 5 }"
          size="small"
          placeholder="记录差异原因分析及处理意见（点击 AI 生成可根据调节数据自动填写）"
          @change="(val: string) => $emit('update', company._row_id!, 'audit_note', val)"
        />
        <span v-else>{{ company.audit_note || '—' }}</span>
      </div>
    </div>
  </div>

  <!-- 未选中状态 -->
  <div v-else class="diff-checklist-detail diff-checklist-detail--empty">
    <el-empty description="请在左侧选择一家公司查看调节详情" :image-size="80" />
  </div>
</template>

<script setup lang="ts">
import { InfoFilled } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import type { DiffChecklistCompany } from './diffChecklistTypes'
import DetailSubTable from './DetailSubTable.vue'
import { useDisplayPrefsStore } from '@/stores/displayPrefs'

const props = defineProps<{
  company: DiffChecklistCompany | null
  readonly: boolean
}>()

const prefs = useDisplayPrefsStore()
const emit = defineEmits<{
  (e: 'update', companyId: string, field: string, value: any): void
  (e: 'add-sub-row', companyId: string, section: 'b' | 'c' | 'f' | 'g'): void
  (e: 'delete-sub-row', companyId: string, section: 'b' | 'c' | 'f' | 'g', rowId: string): void
  (e: 'update-sub-row', companyId: string, section: 'b' | 'c' | 'f' | 'g', rowId: string, field: string, value: any): void
}>()

function handleAiNote() {
  if (!props.company) return
  const c = props.company
  const entity = c.entity_name || '该公司'
  const a = c.a_reply_amount ?? 0
  const e = c.e_book_amount ?? 0
  const d = c.d_adjusted_reply ?? 0
  const h = c.h_adjusted_book ?? 0
  const i = c.i_final_diff ?? 0
  const bCount = (c.b_rows ?? []).length
  const cCount = (c.c_rows ?? []).length
  const fCount = (c.f_rows ?? []).length
  const gCount = (c.g_rows ?? []).length

  let note = ''
  if (i === 0) {
    note = `经双向调节，${entity}差异已完全消除。`
    + `回函金额 ${a.toLocaleString()} 元，账面金额 ${e.toLocaleString()} 元。`
    if (bCount + cCount + fCount + gCount > 0) {
      note += `共识别未达账项 ${bCount + cCount + fCount + gCount} 笔`
      + `（对方调节 ${bCount + cCount} 笔，我方调节 ${fCount + gCount} 笔），`
      + `调节后双方余额一致（D=${d.toLocaleString()}，H=${h.toLocaleString()}），差异为零。`
    } else {
      note += `双方账面一致，无需调节。`
    }
  } else {
    note = `${entity}经调节后仍存在差异 ${i.toLocaleString()} 元。`
    + `回函金额 ${a.toLocaleString()} 元，账面金额 ${e.toLocaleString()} 元。`
    + `调节后对方余额 D=${d.toLocaleString()} 元，我方余额 H=${h.toLocaleString()} 元。`
    + `差异原因待进一步核查，建议关注是否存在未识别的未达账项或记账错误。`
  }

  emit('update', c._row_id!, 'audit_note', note)
  ElMessage.success('已根据调节数据生成审计说明（仅供参考，请根据实际情况修改）')
}

function formatAmount(val?: number): string {
  if (val == null) return '—'
  return prefs.fmt(val)
}

function statusTagType(status?: string): string {
  if (status === 'balanced') return 'success'
  if (status === 'over_materiality') return 'danger'
  if (status === 'diff') return 'warning'
  return 'info'
}

function statusLabel(status?: string): string {
  if (status === 'balanced') return '已平衡'
  if (status === 'over_materiality') return '超重要性'
  if (status === 'diff') return '有差异'
  return '待调节'
}
</script>

<style scoped>
.diff-checklist-detail {
  padding: 12px;
}

.diff-checklist-detail--empty {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 100px;
  padding: 16px;
  color: #909399;
  font-size: 13px;
}

.diff-checklist-detail__title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 15px;
  font-weight: 600;
  margin-bottom: 12px;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--el-border-color-lighter);
}

.diff-checklist-detail__subject {
  font-size: 12px;
  font-weight: normal;
  color: var(--el-text-color-secondary);
}

.diff-checklist-detail__formula {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.diff-checklist-detail__section {
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 6px;
  padding: 12px;
}

.diff-checklist-detail__section--reply {
  border-left: 3px solid var(--el-color-primary);
}

.diff-checklist-detail__section--book {
  border-left: 3px solid var(--el-color-success);
}

.diff-checklist-detail__section--result {
  border-left: 3px solid var(--el-color-info);
  background: var(--el-fill-color-lighter);
}

.diff-checklist-detail__section--alert {
  border-left-color: var(--el-color-danger);
  background: var(--el-color-danger-light-9);
}

.diff-checklist-detail__section-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--el-text-color-secondary);
  margin-bottom: 8px;
}

.diff-checklist-detail__step {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 6px 0;
}

.diff-checklist-detail__step--computed {
  border-top: 1px dashed var(--el-border-color-light);
  margin-top: 4px;
  padding-top: 8px;
}

.diff-checklist-detail__step--final {
  font-size: 14px;
}

.diff-checklist-detail__label {
  font-size: 13px;
  color: var(--el-text-color-primary);
  display: flex;
  align-items: center;
  gap: 4px;
}

.diff-checklist-detail__value {
  font-variant-numeric: tabular-nums;
  font-size: 14px;
  font-weight: 500;
}

.diff-checklist-detail__value--computed {
  color: var(--el-color-primary);
}

.diff-checklist-detail__value--final {
  font-size: 16px;
  font-weight: 700;
}

.diff-checklist-detail__value--zero {
  color: var(--el-color-success);
}

.diff-checklist-detail__value--nonzero {
  color: var(--el-color-danger);
}

.diff-checklist-detail__input {
  width: 160px;
}

.diff-checklist-detail__note {
  margin-top: 12px;
  padding-top: 8px;
  border-top: 1px solid var(--el-border-color-lighter);
}
</style>
