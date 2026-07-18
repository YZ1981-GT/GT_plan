<template>
  <div class="f2-supplier-checklist f2-ipo-soft">
    <header class="sheet-header">
      <div>
        <h3>供应商核查清单</h3>
        <span class="code">F2-69 · 选取原因、反向核查、函证资料与核查方式</span>
      </div>
      <div class="stats">
        <el-tag size="small">已列示 {{ sc.summary.value.supplierCount }} 家</el-tag>
        <el-tag size="small" type="success">已执行 {{ sc.summary.value.completedMethods }} 项</el-tag>
        <el-tag v-if="sc.summary.value.incompleteCount" size="small" type="warning">
          待完善 {{ sc.summary.value.incompleteCount }} 家
        </el-tag>
        <el-tag v-if="sc.summary.value.mismatchCount" size="small" type="danger">
          金额差异 {{ sc.summary.value.mismatchCount }} 家
        </el-tag>
      </div>
    </header>

    <details class="guidance-details">
      <summary>📋 审计目标与核查步骤</summary>
      <div class="guidance-content">
        <p>1. 结合 F2-68 主要供应商结构分析，选取重大、异常、新增或集中度较高的供应商。</p>
        <p>2. 对采购真实性、合同主要条款、资金支付、物流流向和期后付款进行核查。</p>
        <p>3. 通过工商资料、互联网公开信息、访谈/电话访谈、函证及实地走访多渠道交叉验证。</p>
        <p>4. 将供应商反向核查数据与公司账面及函证资料比较，差异超过 1% 自动提示关注。</p>
        <p>5. 每家供应商应填写最终索引号；存在差异或未执行程序的，应在备注中说明。</p>
      </div>
    </details>

    <div class="tab-toolbar">
      <div class="toolbar-left">
        <el-button size="small" type="primary" :disabled="isReadonly" @click="sc.addRow()">
          + 新增供应商
        </el-button>
        <el-input
          v-model="sc.searchQuery.value"
          size="small"
          placeholder="搜索供应商/选取原因/备注"
          clearable
          class="search"
        />
      </div>
      <div class="toolbar-right">
        <F2SheetToolbar
          :wp-id="wpId"
          api-prefix="f2-spe"
          sheet="F2-69"
          :disabled="isReadonly"
          review-section="F2-69-checklist"
        />
        <GtIndexChip value="wp:F2-69" />
      </div>
    </div>

    <div class="table-scroll">
      <table class="checklist-table">
        <thead>
          <tr>
            <th rowspan="2" class="sticky supplier">供应商名称</th>
            <th rowspan="2" class="reason-col">选取原因</th>
            <th rowspan="2">走访结论</th>
            <th rowspan="2">上次实访时间</th>
            <th colspan="2">反向核查</th>
            <th colspan="2">函证资料</th>
            <th colspan="5">核查方式（√）</th>
            <th rowspan="2" class="calc-head">完成度</th>
            <th rowspan="2" class="remark-col">差异/未执行原因</th>
            <th rowspan="2">最终索引号</th>
            <th rowspan="2">操作</th>
          </tr>
          <tr>
            <th>期末余额</th>
            <th>本期采购额</th>
            <th>期末余额</th>
            <th>本期采购额</th>
            <th v-for="method in methods" :key="method.key">{{ method.label }}</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="row in sc.filteredRows.value"
            :key="row.id"
            :class="{ 'risk-row': row.isRisk }"
          >
            <td class="sticky supplier">
              <TextCell
                :value="row.supplierName"
                :readonly="isReadonly"
                placeholder="供应商名称"
                @change="(value) => sc.updateRow(row.id, { supplierName: value })"
              />
            </td>
            <td class="reason-col">
              <TextCell
                :value="row.selectionReason"
                :readonly="isReadonly"
                placeholder="重大/异常/新增等"
                @change="(value) => sc.updateRow(row.id, { selectionReason: value })"
              />
            </td>
            <td>
              <TextCell
                :value="row.visitConclusion"
                :readonly="isReadonly"
                placeholder="走访结果"
                @change="(value) => sc.updateRow(row.id, { visitConclusion: value })"
              />
            </td>
            <td>
              <el-date-picker
                v-if="!isReadonly"
                :model-value="row.lastVisitDate"
                type="date"
                value-format="YYYY-MM-DD"
                size="small"
                class="date-input"
                @update:model-value="(value: string | null) => sc.updateRow(row.id, { lastVisitDate: value || '' })"
              />
              <span v-else>{{ row.lastVisitDate || '—' }}</span>
            </td>
            <td>
              <NumberCell
                :value="row.reverseEndingBalance"
                :readonly="isReadonly"
                @change="(value) => sc.updateRow(row.id, { reverseEndingBalance: value })"
              />
            </td>
            <td>
              <NumberCell
                :value="row.reversePurchaseAmount"
                :readonly="isReadonly"
                @change="(value) => sc.updateRow(row.id, { reversePurchaseAmount: value })"
              />
            </td>
            <td :class="{ 'amount-mismatch': row.isAmountMismatch }">
              <NumberCell
                :value="row.confirmationEndingBalance"
                :readonly="isReadonly"
                @change="(value) => sc.updateRow(row.id, { confirmationEndingBalance: value })"
              />
            </td>
            <td :class="{ 'amount-mismatch': row.isAmountMismatch }">
              <NumberCell
                :value="row.confirmationPurchaseAmount"
                :readonly="isReadonly"
                @change="(value) => sc.updateRow(row.id, { confirmationPurchaseAmount: value })"
              />
            </td>
            <td v-for="method in methods" :key="method.key" class="method-cell">
              <el-checkbox
                :model-value="row[method.key]"
                :disabled="isReadonly"
                @change="(checked: boolean | string | number) => sc.toggleMethod(row.id, method.key, Boolean(checked))"
              />
            </td>
            <td class="calc-cell">
              <span class="formula">{{ row.completedMethodCount }}/{{ methods.length }}</span>
              <el-progress
                :percentage="Math.round(row.completionPct * 100)"
                :show-text="false"
                :stroke-width="5"
                :status="row.completionPct === 1 ? 'success' : undefined"
              />
            </td>
            <td class="remark-col">
              <TextCell
                :value="row.remark"
                :readonly="isReadonly"
                placeholder="差异或未执行原因"
                @change="(value) => sc.updateRow(row.id, { remark: value })"
              />
            </td>
            <td>
              <TextCell
                :value="row.finalIndexRef"
                :readonly="isReadonly"
                placeholder="索引"
                @change="(value) => sc.updateRow(row.id, { finalIndexRef: value })"
              />
            </td>
            <td>
              <el-button
                link
                type="danger"
                size="small"
                :disabled="isReadonly || sc.rows.value.length <= 1"
                @click="sc.removeRow(row.id)"
              >删除</el-button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <el-card class="opinion-card" shadow="never">
      <template #header>
        <div class="opinion-header">
          <span>四、审计说明</span>
          <el-button
            size="small"
            type="primary"
            plain
            :disabled="isReadonly || !aiAvailable"
            :loading="aiLoading"
            @click="runAi('supplier-checklist-note')"
          >AI 填写审计说明</el-button>
        </div>
      </template>
      <el-input
        v-model="sc.auditNote.value"
        type="textarea"
        :autosize="{ minRows: 5, maxRows: 12 }"
        :disabled="isReadonly"
        placeholder="说明供应商选取范围、已执行核查方式、账面与反向核查/函证差异、异常事项及处理情况……"
      />
    </el-card>

    <el-card class="opinion-card" shadow="never">
      <template #header>
        <div class="opinion-header">
          <span>五、审计结论</span>
          <el-button
            size="small"
            type="primary"
            plain
            :disabled="isReadonly || !aiAvailable"
            :loading="aiLoading"
            @click="runAi('supplier-checklist-conclusion')"
          >AI 生成结论</el-button>
        </div>
      </template>
      <el-input
        :model-value="auditConclusion"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        :disabled="isReadonly"
        placeholder="综合评价主要供应商采购交易真实性、核查程序执行情况及异常事项。"
        @update:model-value="saveConclusion"
      />
    </el-card>

    <details class="tips-details">
      <summary>提示：核查关注要点</summary>
      <ol>
        <li>核对采购真实性、合同签订及验收、付款等主要条款的一致性。</li>
        <li>结合供应商规模、采购量、资金支付及物流流向评价交易合理性。</li>
        <li>对新增、异常、集中度较高或期末大额交易供应商扩大核查范围。</li>
        <li>结合工商资料、公开信息及访谈识别未披露关联方和商业实质风险。</li>
        <li>函证、走访和反向核查证据应完整归档并填写最终索引号。</li>
      </ol>
    </details>
  </div>
</template>

<script setup lang="ts">
import { defineComponent, h, onMounted, ref, toRef, type Ref } from 'vue'
import { ElInput, ElInputNumber } from 'element-plus'
import { useF2SupplierChecklist } from '../../composables/useF2SupplierChecklist'
import type { CheckMethodField } from '../../composables/useF2SupplierChecklistFormulas'
import { useF2SpecialAiGenerate, type F2SpeAiSection } from '../../composables/useF2SpecialAiGenerate'
import type { ChecklistResponse } from '../../composables/useF2SpecialFormData'
import F2SheetToolbar from '../../f2/shared/F2SheetToolbar.vue'
import GtIndexChip from '../../GtIndexChip.vue'

const props = defineProps<{
  wpId?: string
  projectId?: string
  allResponses: Map<string, ChecklistResponse>
  isReadonly: boolean
}>()

const sc = useF2SupplierChecklist({
  allResponses: toRef(props, 'allResponses'),
  isReadonly: toRef(props, 'isReadonly'),
})

const methods: Array<{ key: CheckMethodField; label: string }> = [
  { key: 'registryChecked', label: '工商资料查询' },
  { key: 'internetChecked', label: '互联网信息查询' },
  { key: 'interviewChecked', label: '访谈/电话访谈' },
  { key: 'confirmationChecked', label: '函证' },
  { key: 'siteVisitChecked', label: '实地走访' },
]

const TextCell = defineComponent({
  props: {
    value: { type: String, default: '' },
    readonly: { type: Boolean, default: false },
    placeholder: { type: String, default: '' },
  },
  emits: ['change'],
  setup(componentProps, { emit }) {
    return () => componentProps.readonly
      ? h('span', componentProps.value || '—')
      : h(ElInput, {
          modelValue: componentProps.value,
          size: 'small',
          placeholder: componentProps.placeholder,
          'onUpdate:modelValue': (value: string) => emit('change', value),
        })
  },
})

const NumberCell = defineComponent({
  props: {
    value: { type: Number, default: 0 },
    readonly: { type: Boolean, default: false },
  },
  emits: ['change'],
  setup(componentProps, { emit }) {
    return () => componentProps.readonly
      ? h('span', { class: 'amount' }, fmtAmount(componentProps.value))
      : h(ElInputNumber, {
          modelValue: componentProps.value,
          size: 'small',
          controls: false,
          class: 'number-input',
          'onUpdate:modelValue': (value: number | undefined) => emit('change', value ?? 0),
        })
  },
})

function fmtAmount(value: number): string {
  return value
    ? value.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
    : '—'
}

const CONCLUSION_KEY = 'F2-69-audit-conclusion'
const auditConclusion = ref('')

function saveConclusion(value: string): void {
  if (props.isReadonly) return
  auditConclusion.value = value
  const item = { item_id: CONCLUSION_KEY, conclusion: null, remark: value }
  props.allResponses.set(CONCLUSION_KEY, item)
  window.dispatchEvent(new CustomEvent('f2-spe:save-items', { detail: { items: [item] } }))
}

onMounted(() => {
  auditConclusion.value = props.allResponses.get(CONCLUSION_KEY)?.remark || ''
  const legacy = props.allResponses.get('F2-69-audit-note')?.remark
  if (!sc.auditNote.value && legacy) sc.auditNote.value = legacy
})

const wpIdRef = toRef(() => props.wpId || '') as Ref<string>
const { aiAvailable, loading: aiLoading, generateAndConfirm } = useF2SpecialAiGenerate(wpIdRef)

function aiContext(): Record<string, unknown> {
  return {
    sheet: 'F2-69',
    summary: sc.summary.value,
    suppliers: sc.enrichedRows.value
      .filter((row) => row.supplierName.trim())
      .slice(0, 30)
      .map((row) => ({
        supplierName: row.supplierName,
        selectionReason: row.selectionReason,
        visitConclusion: row.visitConclusion,
        completedMethods: row.completedMethodCount,
        reverseEndingBalance: row.reverseEndingBalance,
        reversePurchaseAmount: row.reversePurchaseAmount,
        confirmationEndingBalance: row.confirmationEndingBalance,
        confirmationPurchaseAmount: row.confirmationPurchaseAmount,
        amountMismatch: row.isAmountMismatch,
        incomplete: row.isIncomplete,
        remark: row.remark,
        indexRef: row.finalIndexRef,
      })),
    auditNote: sc.auditNote.value,
  }
}

async function runAi(section: F2SpeAiSection): Promise<void> {
  const isNote = section === 'supplier-checklist-note'
  const content = await generateAndConfirm(
    section,
    isNote ? sc.auditNote.value : auditConclusion.value,
    aiContext(),
    isNote ? 'AI 生成 · 供应商核查审计说明' : 'AI 生成 · 供应商核查审计结论',
  )
  if (!content) return
  if (isNote) sc.auditNote.value = content
  else saveConclusion(content)
}
</script>

<style scoped>
.f2-supplier-checklist{padding:14px 18px;font-size:var(--wp-font-size, 13px);background:linear-gradient(180deg,#faf8fc 0,#fff 130px);--purple:#4b2d77}
.sheet-header,.stats,.tab-toolbar,.toolbar-left,.toolbar-right,.opinion-header{display: flex;align-items:center}.sheet-header,.tab-toolbar,.opinion-header{justify-content:space-between}.sheet-header{gap:12px;margin-bottom:12px}.sheet-header h3{margin:0;color:#35204f}.code{font-size:12px;color:#8c7b9d}.stats,.toolbar-left,.toolbar-right{gap:8px;flex-wrap:wrap}
.guidance-details{margin-bottom:12px;border-left:3px solid var(--purple);background:#f7f2fa;border-radius:5px;padding:8px 12px}.guidance-details summary{cursor:pointer;font-weight:600;color:var(--purple)}.guidance-content{margin-top:8px;color:#606266;line-height:1.7}.guidance-content p{margin:3px 0}.tab-toolbar{gap:10px;margin-bottom:12px}.search{width:220px}
.table-scroll{max-width:100%;overflow-x: auto;border:1px solid #d7cae2;border-radius:7px}.checklist-table{width:100%;min-width:1780px;border-collapse:separate;border-spacing:0;font-size:11px}.checklist-table th,.checklist-table td{border-right:1px solid #d8cce3;border-bottom:1px solid #d8cce3;padding:4px;text-align:center;vertical-align:middle;background:#fff}.checklist-table th{position:sticky;top:0;z-index:3;background:var(--purple);color:#fff;font-weight:600;line-height:1.25}.checklist-table .sticky{position:sticky;z-index:4}.checklist-table th.sticky{z-index:5}.checklist-table td.sticky{background:#fff}.supplier{left:0;width:145px;min-width:145px}.reason-col{width:155px;min-width:155px;text-align:left!important}.remark-col{width:165px;min-width:165px;text-align:left!important}.calc-head{background:#6b4b89!important}.calc-cell{background:#f2ecf7!important;min-width:85px;color:#4b2d77}.formula{border-bottom:1px dotted #8d78a2;cursor:help}.method-cell{width:74px;min-width:74px}.risk-row td{background:#fef0f0}.risk-row td.sticky{background:#fef0f0}.amount-mismatch{box-shadow:inset 0 0 0 2px #e6a23c}.amount{display:block;text-align:right;white-space:nowrap}
:deep(.number-input){width:100px}:deep(.number-input .el-input__inner){text-align:right;padding:0 4px}:deep(.date-input){width:115px}
.opinion-card{margin-top:16px;border-color:#ded3e8}.opinion-card :deep(.el-card__header){padding:10px 14px;background:#faf8fc}.opinion-header span{font-weight:700;color:var(--purple)}
.tips-details{margin-top:14px;border:1px solid #d9ecff;border-left:3px solid #409eff;border-radius:5px}.tips-details summary{cursor:pointer;padding:8px 12px;color:#337ecc;font-weight:600}.tips-details ol{margin:2px 12px 10px;padding-left:20px;line-height:1.8;color:#606266}
</style>
