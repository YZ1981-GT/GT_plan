<template>
  <div class="wealth-conclusion">
    <el-divider content-position="left">审计说明与结论</el-divider>

    <!-- 审计说明 -->
    <el-card shadow="never" class="wealth-conclusion__card">
      <div class="wealth-conclusion__title-row">
        <h4 class="wealth-conclusion__title">审计说明</h4>
        <el-button v-if="!readonly" type="primary" size="small" plain :loading="aiLoading" @click="handleAiFill">
          AI 智能填充
        </el-button>
      </div>
      <el-form label-position="top" size="small">
        <el-form-item label="发函范围与选取说明">
          <el-input
            :model-value="auditNote.note_scope"
            type="textarea"
            :autosize="{ minRows: 3 }"
            :disabled="readonly"
            placeholder="说明理财产品的期末持有情况、本次发函的选取范围与理由（如全额函证 / 按重要性选取）"
            @input="(v: string) => $emit('update-note', 'note_scope', v)"
          />
        </el-form-item>
        <el-form-item label="受限情况说明（担保 / 其他使用限制）">
          <el-input
            :model-value="auditNote.note_restricted"
            type="textarea"
            :autosize="{ minRows: 3 }"
            :disabled="readonly"
            placeholder="对被用于担保或存在其他使用限制的产品，说明限制性质、对应披露落点（受限货币资金 / 受限资产附注）"
            @input="(v: string) => $emit('update-note', 'note_restricted', v)"
          />
        </el-form-item>
        <el-form-item label="其他事项">
          <el-input
            :model-value="auditNote.note_other"
            type="textarea"
            :autosize="{ minRows: 2 }"
            :disabled="readonly"
            placeholder="如已到期未兑付、开放式产品期后赎回等需说明的事项"
            @input="(v: string) => $emit('update-note', 'note_other', v)"
          />
        </el-form-item>
      </el-form>
    </el-card>

    <!-- 审计结论 -->
    <el-card shadow="never" class="wealth-conclusion__card">
      <h4 class="wealth-conclusion__title">审计结论</h4>
      <el-form label-position="top" size="small">
        <el-form-item label="结论类型">
          <el-radio-group
            :model-value="conclusion.conclusion_type"
            :disabled="readonly"
            @change="(v: any) => $emit('update-conclusion', 'conclusion_type', v)"
          >
            <el-radio value="完整">完整——理财产品发函清单已覆盖期末全部在持产品，信息完整可发函</el-radio>
            <el-radio value="存在例外需跟进">存在例外需跟进——存在汇总键缺失 / 已到期 / 受限等需跟进事项</el-radio>
            <el-radio value="不适用">不适用——本期期末未持有理财产品，无需函证</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="结论说明">
          <el-input
            :model-value="conclusion.conclusion_text"
            type="textarea"
            :autosize="{ minRows: 3 }"
            :disabled="readonly"
            placeholder="对发函清单的完整性与后续函证安排作出说明"
            @input="(v: string) => $emit('update-conclusion', 'conclusion_text', v)"
          />
        </el-form-item>
      </el-form>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import { useDisplayPrefsStore } from '@/stores/displayPrefs'
import type { WealthListAuditNote, WealthListConclusion, WealthListMetrics } from './wealthListTypes'

const props = defineProps<{
  auditNote: WealthListAuditNote
  conclusion: WealthListConclusion
  readonly: boolean
  metrics: WealthListMetrics
}>()

const emit = defineEmits<{
  (e: 'update-note', field: string, value: string): void
  (e: 'update-conclusion', field: string, value: any): void
}>()

const displayPrefs = useDisplayPrefsStore()
const aiLoading = ref(false)

/**
 * 按已录入数据生成说明草稿（只填空白字段，不覆盖已有内容）。
 * 只陈述表内可证实的事实与源模板口径，不虚构限制性质、不臆测科目归属。
 */
function handleAiFill() {
  aiLoading.value = true
  try {
    const m = props.metrics
    const fmt = (v: number) => displayPrefs.fmtAmount(v)

    let scope = ''
    if (m.total_count > 0) {
      scope = `本表登记期末在持理财产品 ${m.total_count} 只，发函金额合计 ${fmt(m.net_value_total)}（口径为各产品净值之和）。`
      if (m.closed_count || m.open_count) {
        scope += `其中封闭式 ${m.closed_count} 只、开放式 ${m.open_count} 只。`
      }
      if (m.missing_key_count > 0) {
        scope += `尚有 ${m.missing_key_count} 只未填「索引号」或「产品名称」，需补全后方可汇入 E0-1 发函金额。`
      }
      if (m.matured_count > 0) {
        scope += `另有 ${m.matured_count} 只到期日不晚于报表截止日，需核实期末是否仍应列示。`
      }
    } else {
      scope = '本期期末未持有理财产品，未执行理财产品函证程序。'
    }

    let restricted = ''
    if (m.restricted_count > 0) {
      restricted = `${m.restricted_count} 只理财产品被用于担保或存在其他使用限制，涉及金额 ${fmt(m.restricted_amount)}。`
        + '限制的具体性质及对应披露落点（受限制的货币资金 / 所有权或使用权受到限制的资产）待逐只核实后补充。'
    } else if (m.total_count > 0) {
      restricted = '本表登记的理财产品均未被用于担保，亦不存在其他使用限制。'
    }

    if (!props.auditNote.note_scope) emit('update-note', 'note_scope', scope)
    if (!props.auditNote.note_restricted && restricted) {
      emit('update-note', 'note_restricted', restricted)
    }

    if (!props.conclusion.conclusion_type) {
      if (m.total_count === 0) {
        emit('update-conclusion', 'conclusion_type', '不适用')
      } else if (m.missing_key_count > 0 || m.matured_count > 0 || m.restricted_count > 0) {
        emit('update-conclusion', 'conclusion_type', '存在例外需跟进')
      } else {
        emit('update-conclusion', 'conclusion_type', '完整')
      }
    }

    ElMessage.success('已按表内数据生成说明草稿，请结合实际情况复核修改')
  } finally {
    aiLoading.value = false
  }
}
</script>

<style scoped>
.wealth-conclusion__card {
  margin-bottom: 12px;
}

.wealth-conclusion__title-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}

.wealth-conclusion__title {
  font-size: 14px;
  font-weight: 500;
  margin: 4px 0 8px;
  color: var(--el-text-color-primary);
}

:deep(.el-radio) {
  display: block;
  margin-bottom: 8px;
  line-height: 1.6;
}
</style>
