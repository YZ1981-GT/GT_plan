<template>
  <div class="f2-undisclosed f2-ipo-soft">
    <header class="sheet-header">
      <div>
        <h3>识别未披露的关联方</h3>
        <span class="code">F2-67 · 人员身份交叉核对矩阵</span>
      </div>
      <div class="stat-row">
        <span class="stat">已核对 {{ up.riskSummary.value.total }} 人</span>
        <el-tag v-if="up.riskSummary.value.matched" type="danger" size="small">
          存在关系 {{ up.riskSummary.value.matched }} 人
        </el-tag>
        <el-tag type="info" size="small">
          涉及采购额 {{ fmtAmount(up.riskSummary.value.totalPurchaseAmount) }}
        </el-tag>
      </div>
    </header>

    <details class="methodology">
      <summary>📖 审计目标与识别过程</summary>
      <div class="methodology-body">
        <p><strong>一、审计目标：</strong>{{ objectiveText }}</p>
        <p><strong>二、审计过程：</strong></p>
        <ol>
          <li>选择大额、异常的供应商或交易。</li>
          <li>查询供应商工商、银行、税务信息，关注地址、董监高、关键管理人员、联系方式，并与发票及网站信息核对。</li>
          <li>选取重要供应商，获取关联方关系确认函。</li>
          <li>取得实际控制人、董监高及密切家庭成员的对外投资清单，与重要供应商股东和关键经办人员比对。</li>
          <li>取得保荐机构、PE 投资机构等利益相关方清单，与重要供应商、法人、股东和关键经办人员比对。</li>
          <li>取得主要股东、董监高、关键管理人员及利益相关方确认函，确认不存在未披露交易。</li>
        </ol>
      </div>
    </details>

    <div class="process-strip">
      <span>编制流程：</span>
      <b>①选取供应商</b><i>→</i><b>②工商穿透</b><i>→</i>
      <b>③人员名单比对</b><i>→</i><b>④身份核验</b><i>→</i><b>⑤确认结论</b>
    </div>

    <div class="tab-toolbar">
      <div class="toolbar-left">
        <el-button size="small" type="primary" :disabled="isReadonly" @click="up.addRow()">+ 添加核对人员</el-button>
        <el-input
          v-model="up.searchQuery.value"
          size="small"
          placeholder="搜索姓名/身份/说明"
          clearable
          class="search"
        />
      </div>
      <div class="toolbar-right">
        <F2SheetToolbar
          :wp-id="wpId"
          api-prefix="f2-spe"
          sheet="F2-67"
          :disabled="isReadonly"
          review-section="F2-67-undisclosed"
        />
        <GtIndexChip value="wp:F2-67" />
      </div>
    </div>

    <div class="table-scroll">
      <table class="match-table">
        <thead>
          <tr>
            <th class="sticky seq">序号</th>
            <th class="sticky name">姓名</th>
            <th v-for="column in matchColumns" :key="column.key">{{ column.label }}</th>
            <th class="calc-head">合计</th>
            <th class="relation-head">供应商与公司员工或者其家属存在关系（Y/N）</th>
            <th>公司股东/高管/亲属/员工</th>
            <th>本年度采购额</th>
            <th class="note-col">说明</th>
            <th>索引号</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="(row, index) in up.filteredRows.value"
            :key="row.id"
            :class="{ 'row-match': row.isAbnormal }"
          >
            <td class="sticky seq">{{ index + 1 }}</td>
            <td class="sticky name">
              <el-input
                v-if="!isReadonly"
                :model-value="row.name"
                size="small"
                placeholder="姓名"
                @update:model-value="(value: string) => up.updateRow(row.id, { name: value })"
              />
              <span v-else>{{ row.name || '—' }}</span>
            </td>
            <td v-for="column in matchColumns" :key="column.key" class="match-cell">
              <el-input-number
                v-if="!isReadonly"
                :model-value="row[column.key]"
                :controls="false"
                :min="0"
                size="small"
                class="match-input"
                @change="(value: number | undefined) => updateMatch(row.id, column.key, value)"
              />
              <span v-else>{{ row[column.key] || '—' }}</span>
            </td>
            <td class="calc-cell">{{ row.total || '—' }}</td>
            <td>
              <el-select
                v-if="!isReadonly"
                :model-value="row.isRelated || row.suggestedRelated || undefined"
                size="small"
                clearable
                placeholder="自动"
                @change="(value: string) => up.updateRow(row.id, { isRelated: (value || '') as any })"
              >
                <el-option label="Y" value="Y" />
                <el-option label="N" value="N" />
              </el-select>
              <strong v-else :class="{ danger: row.isAbnormal }">
                {{ row.isRelated || row.suggestedRelated || '—' }}
              </strong>
            </td>
            <td>
              <el-input
                v-if="!isReadonly"
                :model-value="row.identity"
                size="small"
                placeholder="股东/高管/亲属/员工"
                @update:model-value="(value: string) => up.updateRow(row.id, { identity: value })"
              />
              <span v-else>{{ row.identity || '—' }}</span>
            </td>
            <td>
              <el-input-number
                v-if="!isReadonly"
                :model-value="row.annualPurchaseAmount"
                :controls="false"
                :min="0"
                size="small"
                class="amount-input"
                @change="(value: number | undefined) => up.updateRow(row.id, { annualPurchaseAmount: value ?? 0 })"
              />
              <span v-else class="amount">{{ fmtAmount(row.annualPurchaseAmount) }}</span>
            </td>
            <td class="note-col">
              <el-input
                v-if="!isReadonly"
                :model-value="row.note"
                size="small"
                placeholder="身份核验或差异说明"
                @update:model-value="(value: string) => up.updateRow(row.id, { note: value })"
              />
              <span v-else>{{ row.note || '—' }}</span>
            </td>
            <td>
              <el-input
                v-if="!isReadonly"
                :model-value="row.indexRef"
                size="small"
                @update:model-value="(value: string) => up.updateRow(row.id, { indexRef: value })"
              />
              <span v-else>{{ row.indexRef || '—' }}</span>
            </td>
            <td>
              <el-button
                link
                type="danger"
                size="small"
                :disabled="isReadonly || up.rows.value.length <= 1"
                @click="up.removeRow(row.id)"
              >删除</el-button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <el-card class="opinion-card" shadow="never">
      <template #header>
        <div class="opinion-header">
          <span>三、审计说明</span>
          <el-button
            size="small"
            type="primary"
            plain
            :disabled="isReadonly || !aiAvailable"
            :loading="aiLoading"
            @click="runAi('undisclosed-party-note')"
          >AI 填写审计说明</el-button>
        </div>
      </template>
      <el-input
        v-model="up.auditNote.value"
        type="textarea"
        :autosize="{ minRows: 5, maxRows: 12 }"
        :disabled="isReadonly"
        placeholder="说明股东、董监高、亲属及员工名单概况，供应商法人和关键人员概况，姓名比对及身份证核验结果……"
      />
    </el-card>

    <el-card class="opinion-card" shadow="never">
      <template #header>
        <div class="opinion-header">
          <span>四、审计结论</span>
          <el-button
            size="small"
            type="primary"
            plain
            :disabled="isReadonly || !aiAvailable"
            :loading="aiLoading"
            @click="runAi('undisclosed-party-conclusion')"
          >AI 生成结论</el-button>
        </div>
      </template>
      <el-input
        :model-value="auditConclusion"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        :disabled="isReadonly"
        placeholder="说明是否识别出重要供应商与公司存在未披露的关联方关系。"
        @update:model-value="saveConclusion"
      />
    </el-card>

    <div class="tips">
      <strong>提示：</strong>识别未披露关联方可以参考收入循环相应底稿；重点核对供应商实际控制人、关键人员及其家属与公司人员名单、身份证信息和任职关系。
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref, toRef, type Ref } from 'vue'
import { useF2UndisclosedParty } from '../../composables/useF2UndisclosedParty'
import {
  F2_67_OBJECTIVE,
  type MatchField,
} from '../../composables/useF2UndisclosedPartyFormulas'
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

const up = useF2UndisclosedParty({
  allResponses: toRef(props, 'allResponses'),
  isReadonly: toRef(props, 'isReadonly'),
})
const objectiveText = F2_67_OBJECTIVE

const matchColumns: Array<{ key: MatchField; label: string }> = [
  { key: 'personalSupplier', label: '个人供应商' },
  { key: 'supplierLegalPerson', label: '供应商法人' },
  { key: 'contractSignee', label: '合同签订人' },
  { key: 'formerPurchasingStaff', label: '离职采购' },
  { key: 'financeDept', label: '财务部门' },
  { key: 'managementDept', label: '管理部门' },
  { key: 'technologyDept', label: '技术部门' },
  { key: 'productionDept', label: '生产部门' },
  { key: 'marketingDept', label: '营销部门' },
  { key: 'otherDept', label: '其他部门' },
]

function updateMatch(rowId: string, field: MatchField, value: number | undefined): void {
  up.updateRow(rowId, { [field]: value ?? 0 })
}

function fmtAmount(value: number): string {
  return value
    ? value.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
    : '—'
}

const CONCLUSION_KEY = 'F2-67-audit-conclusion'
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
  const legacy = props.allResponses.get('F2-67-audit-note')?.remark
  if (!up.auditNote.value && legacy) up.auditNote.value = legacy
})

const wpIdRef = toRef(() => props.wpId || '') as Ref<string>
const { aiAvailable, loading: aiLoading, generateAndConfirm } = useF2SpecialAiGenerate(wpIdRef)

function aiContext(): Record<string, unknown> {
  return {
    sheet: 'F2-67',
    checkedCount: up.riskSummary.value.total,
    matchedCount: up.riskSummary.value.matched,
    totalPurchaseAmount: up.riskSummary.value.totalPurchaseAmount,
    rows: up.filteredRows.value
      .filter((row) => row.name.trim())
      .slice(0, 50)
      .map((row) => ({
        name: row.name,
        totalMatches: row.total,
        isRelated: row.isRelated || row.suggestedRelated,
        identity: row.identity,
        annualPurchaseAmount: row.annualPurchaseAmount,
        note: row.note,
      })),
    auditNote: up.auditNote.value,
  }
}

async function runAi(section: F2SpeAiSection): Promise<void> {
  const isNote = section === 'undisclosed-party-note'
  const content = await generateAndConfirm(
    section,
    isNote ? up.auditNote.value : auditConclusion.value,
    aiContext(),
    isNote ? 'AI 生成 · 未披露关联方审计说明' : 'AI 生成 · 未披露关联方审计结论',
  )
  if (!content) return
  if (isNote) up.auditNote.value = content
  else saveConclusion(content)
}
</script>

<style scoped>
.f2-undisclosed{padding:14px 18px;font-size:var(--wp-font-size, 13px);background:linear-gradient(180deg,#faf8fc 0,#fff 130px);--purple:#4b2d77}
.sheet-header,.stat-row,.tab-toolbar,.toolbar-left,.toolbar-right,.opinion-header{display: flex;align-items:center}
.sheet-header,.tab-toolbar,.opinion-header{justify-content:space-between}.sheet-header{gap:12px;margin-bottom:12px}.sheet-header h3{margin:0;color:#35204f}.code{font-size:12px;color:#8c7b9d}.stat-row,.toolbar-left,.toolbar-right{gap:8px;flex-wrap:wrap}
.methodology{border:1px solid #eadff2;border-left:3px solid var(--purple);border-radius:6px;background:#fbf9fd;margin-bottom:12px}.methodology summary{cursor:pointer;padding:9px 13px;color:var(--purple);font-weight:600}.methodology-body{padding:0 16px 10px;color:#606266;line-height:1.75}.methodology-body p{margin:6px 0}.methodology-body ol{margin:4px 0;padding-left:22px}
.process-strip{display:flex;align-items:center;gap:7px;flex-wrap:wrap;padding:9px 13px;margin-bottom:12px;border:1px solid #d8c9e4;border-radius:6px;background:#f4eff8;color:#68468a}.process-strip b{padding:2px 7px;background:#fff;border-radius:4px;font-size:12px}.process-strip i{font-style:normal;color:#a590b8}
.tab-toolbar{gap:10px;margin-bottom:10px}.search{width:200px}.table-scroll{max-width:100%;overflow-x:auto;border:1px solid #d2c3df;border-radius:6px}
.match-table{width:100%;min-width:1750px;border-collapse:separate;border-spacing:0;font-size:11px}.match-table th,.match-table td{border-right:1px solid #d8cce3;border-bottom:1px solid #d8cce3;padding:4px;text-align:center;vertical-align:middle;background:#fff}.match-table th{position:sticky;top:0;z-index:3;height:52px;background:var(--purple);color:#fff;font-weight:600;line-height:1.25}.match-table .sticky{position:sticky;z-index:4}.match-table th.sticky{z-index:5;background:var(--purple)}.match-table td.sticky{background:#fff}.seq{left:0;width:45px;min-width:45px}.name{left:45px;width:90px;min-width:90px}.match-cell{width:62px;min-width:62px}.calc-head{background:#6f5290!important}.relation-head{width:155px;min-width:155px}.note-col{width:175px;min-width:175px;text-align:left!important}.calc-cell{background:#f1eaf6!important;color:var(--purple);font-weight:700}.row-match td{background:#fef0f0}.row-match td.sticky{background:#fef0f0}.danger{color:#c45656}.amount{display:block;text-align:right;white-space:nowrap}
:deep(.match-input){width:48px}:deep(.match-input .el-input__inner){padding:0 2px;text-align:center}:deep(.amount-input){width:110px}:deep(.amount-input .el-input__inner){text-align:right}
.opinion-card{margin-top:16px;border-color:#ded3e8}.opinion-card :deep(.el-card__header){padding:10px 14px;background:#faf8fc}.opinion-header span{font-weight:700;color:var(--purple)}
.tips{margin-top:14px;padding:10px 14px;background:#ecf5ff;border-left:3px solid #409eff;line-height:1.7}
</style>
