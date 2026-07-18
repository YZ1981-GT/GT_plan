<template>
  <div class="f2-interview-summary f2-ipo-soft">
    <header class="sheet-header">
      <div>
        <h3>供应商访谈记录汇总表</h3>
        <span class="code">F2-71 · 访谈项目 × 供应商（卡片 / 矩阵 / 在线编辑三模式，联动 F2-68/70/72）</span>
      </div>
      <div class="stats">
        <el-tag size="small">访谈 {{ iv.summary.value.supplierCount }} 家</el-tag>
        <el-tag v-if="iv.summary.value.incompleteCount" size="small" type="warning">
          待完善 {{ iv.summary.value.incompleteCount }} 家
        </el-tag>
        <el-tag v-if="iv.summary.value.riskCount" size="small" type="danger">
          风险 {{ iv.summary.value.riskCount }} 家
        </el-tag>
      </div>
    </header>

    <details class="guidance-details">
      <summary>📋 审计目标、走访范围与编制思路</summary>
      <div class="guidance-content">
        <p><strong>一、审计目标：</strong>通过供应商实地走访/访谈验证采购交易真实性与商业合理性，识别关联关系及异常交易迹象。</p>
        <p><strong>二、走访范围（提示1）：</strong>主要客户和供应商（如前十名）；新增的主要供应商；存在疑虑的重要客户及供应商；主要基建工程建造商。</p>
        <p><strong>三、编制思路：</strong>每家受访供应商一列档案，按"访谈安排 → 访谈人员与行程 → 现场核对 → 结论与索引"填写；行程票据、现场照片等证据用列内"附件"上传；注册地址可一键取自 F2-70，交易金额核对可参照 F2-68 采购额，访谈明细索引联动 F2-72。</p>
        <p><strong>四、录入方式：</strong>「卡片模式」浏览并弹窗逐家录入；「矩阵模式」按访谈项目×供应商对照编辑；在线编辑请切换上方「在线编辑」页签。</p>
        <p>
          <strong>五、示例：</strong>访谈如何询问与核对，可点击
          <el-button link type="warning" @click="exampleVisible = true">「查看编制示例」</el-button>
          参照 XYZ 公司「访谈记录与核对」示例。
        </p>
      </div>
    </details>

    <div class="tab-toolbar">
      <div class="toolbar-left">
        <el-radio-group v-model="viewMode" size="small">
          <el-radio-button value="card">卡片模式</el-radio-button>
          <el-radio-button value="matrix">矩阵模式</el-radio-button>
        </el-radio-group>
        <el-button size="small" type="primary" :disabled="isReadonly" @click="openCreateDialog">
          + 新增供应商访谈
        </el-button>
        <el-button size="small" type="warning" plain @click="exampleVisible = true">
          📚 查看编制示例
        </el-button>
      </div>
      <div class="toolbar-right">
        <F2SheetToolbar
          :wp-id="wpId"
          api-prefix="f2-spe"
          sheet="F2-71"
          :disabled="isReadonly"
          review-section="F2-71-interview"
        />
        <GtIndexChip value="wp:F2-71" />
      </div>
    </div>

    <!-- ═══ 卡片模式 ═══ -->
    <div v-if="viewMode === 'card'" class="card-grid">
      <el-card
        v-for="(entity, index) in iv.enrichedEntities.value"
        :key="entity.id"
        shadow="hover"
        class="supplier-card"
        :class="{ 'risk-card': entity.isRisk }"
      >
        <template #header>
          <div class="card-head">
            <div class="card-title">
              <span class="supplier-seq">供应商{{ index + 1 }}</span>
              <strong>{{ entity.supplierName || '未命名供应商' }}</strong>
              <GtIndexChip
                v-if="entity.supplierName"
                :value="`F2-72:${entity.supplierName}`"
                label="→F2-72"
              />
            </div>
            <div class="card-actions">
              <el-button size="small" link type="primary" @click="openEditDialog(entity.id)">
                {{ isReadonly ? '查看' : '编辑' }}
              </el-button>
              <el-button
                v-if="!isReadonly"
                size="small"
                link
                type="danger"
                :disabled="iv.entities.value.length <= 1"
                @click="iv.removeEntity(entity.id)"
              >删除</el-button>
            </div>
          </div>
        </template>
        <div class="card-progress">
          <span class="progress-label">填写完整度 <span class="formula">{{ Math.round(entity.completionPct * 100) }}%</span></span>
          <el-progress
            :percentage="Math.round(entity.completionPct * 100)"
            :show-text="false"
            :stroke-width="6"
            :status="entity.completionPct === 1 ? 'success' : undefined"
          />
        </div>
        <dl class="card-fields">
          <div class="card-field"><dt>访谈时间</dt><dd>{{ entity.interviewDate || '—' }}</dd></div>
          <div class="card-field"><dt>访谈方式</dt><dd>{{ entity.method || '—' }}</dd></div>
          <div class="card-field"><dt>受访人</dt><dd>{{ entity.interviewee || '—' }}</dd></div>
          <div class="card-field"><dt>审计人员</dt><dd>{{ entity.auditors || '—' }}</dd></div>
          <div class="card-field"><dt>现场函证</dt><dd>{{ entity.onSiteConfirmation || '—' }}</dd></div>
          <div class="card-field"><dt>记录索引</dt><dd>{{ entity.recordIndex || '—' }}</dd></div>
          <div class="card-field wide"><dt>访谈原因</dt><dd>{{ entity.reason || '—' }}</dd></div>
          <div class="card-field wide"><dt>访谈结论</dt><dd>{{ entity.conclusion || '—' }}</dd></div>
        </dl>
        <div class="card-attachments">
          <span class="att-label">行程/证据附件</span>
          <ItemAttachment
            v-if="projectId && wpId"
            :project-id="projectId"
            :wp-id="wpId"
            sheet-key="F2-71"
            :item-index="entity.attSlot"
          />
        </div>
        <div class="card-risk">
          <template v-if="entity.riskFlags.length">
            <el-tag v-for="flag in entity.riskFlags" :key="flag" type="danger" size="small" class="risk-tag">
              {{ flag }}
            </el-tag>
          </template>
          <span v-else class="ok-flag">未见异常</span>
        </div>
      </el-card>
      <button v-if="!isReadonly" type="button" class="add-card" @click="openCreateDialog">
        <span class="add-plus">＋</span>
        <span>弹窗录入新访谈</span>
      </button>
    </div>

    <!-- ═══ 矩阵模式 ═══ -->
    <div v-else class="table-scroll">
      <table class="info-matrix">
        <thead>
          <tr>
            <th class="sticky item-col">项目</th>
            <th
              v-for="(entity, index) in iv.enrichedEntities.value"
              :key="entity.id"
              class="supplier-head"
              :class="{ 'risk-head': entity.isRisk }"
            >
              <div class="supplier-head-inner">
                <span class="supplier-seq">供应商{{ index + 1 }}</span>
                <span class="head-ops">
                  <el-button link size="small" class="head-btn" @click="openEditDialog(entity.id)">✎</el-button>
                  <el-button
                    v-if="!isReadonly"
                    link
                    size="small"
                    class="head-btn"
                    :disabled="iv.entities.value.length <= 1"
                    @click="iv.removeEntity(entity.id)"
                  >✕</el-button>
                </span>
              </div>
              <el-input
                v-if="!isReadonly"
                :model-value="entity.supplierName"
                size="small"
                placeholder="供应商名称"
                @update:model-value="(value: string) => iv.updateEntity(entity.id, { supplierName: value })"
              />
              <strong v-else>{{ entity.supplierName || '未填写' }}</strong>
            </th>
          </tr>
        </thead>
        <tbody>
          <template v-for="section in sections" :key="section.title">
            <tr class="section-row">
              <td class="sticky item-col section-cell">{{ section.title }}</td>
              <td v-for="entity in iv.enrichedEntities.value" :key="entity.id" class="section-cell"></td>
            </tr>
            <tr v-for="item in section.items" :key="item.key">
              <td class="sticky item-col">{{ item.label }}</td>
              <td
                v-for="entity in iv.enrichedEntities.value"
                :key="entity.id"
                :class="{
                  'risk-cell': (item.riskWhenNo && entity[item.key] === '否')
                    || (item.key === 'visitAddress' && entity.isAddressMismatch),
                }"
              >
                <template v-if="isReadonly">
                  <span>{{ entity[item.key] || '—' }}</span>
                </template>
                <el-date-picker
                  v-else-if="item.type === 'date'"
                  :model-value="entity.interviewDate"
                  type="date"
                  size="small"
                  value-format="YYYY-MM-DD"
                  style="width: 100%"
                  @update:model-value="(value: string | null) => iv.updateEntity(entity.id, { interviewDate: value ?? '' })"
                />
                <el-select
                  v-else-if="item.type === 'method'"
                  :model-value="entity.method || undefined"
                  size="small"
                  clearable
                  placeholder="—"
                  @change="(value: string) => iv.updateEntity(entity.id, { method: (value || '') as any })"
                >
                  <el-option v-for="m in INTERVIEW_METHODS" :key="m" :label="m" :value="m" />
                </el-select>
                <el-select
                  v-else-if="item.type === 'yesno'"
                  :model-value="entity[item.key] || undefined"
                  size="small"
                  clearable
                  placeholder="—"
                  @change="(value: string) => iv.updateEntity(entity.id, { [item.key]: (value || '') as any })"
                >
                  <el-option label="是" value="是" />
                  <el-option label="否" value="否" />
                </el-select>
                <div v-else class="cell-with-link">
                  <el-input
                    :model-value="String(entity[item.key] ?? '')"
                    size="small"
                    :placeholder="item.placeholder || ''"
                    :type="item.textarea ? 'textarea' : 'text'"
                    :autosize="item.textarea ? { minRows: 1, maxRows: 3 } : undefined"
                    @update:model-value="(value: string) => iv.updateEntity(entity.id, { [item.key]: value as any })"
                  />
                  <el-button
                    v-if="item.key === 'registeredAddress' && linkedAddress(entity)"
                    link
                    size="small"
                    type="primary"
                    class="link-btn"
                    @click="iv.fillRegisteredAddress(entity.id)"
                  >取F2-70</el-button>
                </div>
                <div v-if="item.key === 'transactionAmountMatch' && linkedAmount(entity) !== null" class="link-hint">
                  F2-68 采购额：<span class="formula">{{ fmtAmount(linkedAmount(entity)!) }}</span>
                </div>
                <div v-if="item.key === 'recordIndex' && entity.supplierName" class="link-hint">
                  <GtIndexChip :value="`F2-72:${entity.supplierName}`" label="→F2-72 访谈明细" />
                </div>
              </td>
            </tr>
          </template>
          <tr class="section-row">
            <td class="sticky item-col section-cell">五、证据附件与系统核对（自动）</td>
            <td v-for="entity in iv.enrichedEntities.value" :key="entity.id" class="section-cell"></td>
          </tr>
          <tr>
            <td class="sticky item-col">行程/证据附件</td>
            <td v-for="entity in iv.enrichedEntities.value" :key="entity.id" class="att-cell">
              <ItemAttachment
                v-if="projectId && wpId"
                :project-id="projectId"
                :wp-id="wpId"
                sheet-key="F2-71"
                :item-index="entity.attSlot"
              />
            </td>
          </tr>
          <tr>
            <td class="sticky item-col">填写完整度</td>
            <td v-for="entity in iv.enrichedEntities.value" :key="entity.id" class="calc-cell">
              <span class="formula">{{ Math.round(entity.completionPct * 100) }}%</span>
              <el-progress
                :percentage="Math.round(entity.completionPct * 100)"
                :show-text="false"
                :stroke-width="5"
                :status="entity.completionPct === 1 ? 'success' : undefined"
              />
            </td>
          </tr>
          <tr>
            <td class="sticky item-col">风险提示</td>
            <td v-for="entity in iv.enrichedEntities.value" :key="entity.id" class="calc-cell">
              <template v-if="entity.riskFlags.length">
                <el-tag v-for="flag in entity.riskFlags" :key="flag" type="danger" size="small" class="risk-tag">
                  {{ flag }}
                </el-tag>
              </template>
              <span v-else class="ok-flag">未见异常</span>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- 编制示例弹窗 -->
    <el-dialog
      v-model="exampleVisible"
      title="访谈记录与核对（示例） · 只读参照"
      width="920px"
      class="example-dialog"
    >
      <div class="example-dialog-body">
        <F2InterviewCheckExample compact />
      </div>
      <template #footer>
        <el-button type="primary" @click="exampleVisible = false">我知道了</el-button>
      </template>
    </el-dialog>

    <!-- ═══ 弹窗录入 ═══ -->
    <el-dialog
      v-model="dialogVisible"
      :title="dialogTitle"
      width="800px"
      class="interview-dialog"
      :close-on-click-modal="false"
    >
      <div v-if="draft" class="dialog-body">
        <div class="dialog-name-row">
          <label class="dialog-field wide">
            <span class="field-label">供应商名称（可从 F2-68/70/72 已建档供应商中选择）</span>
            <el-select
              :model-value="draft.supplierName || undefined"
              filterable
              allow-create
              default-first-option
              clearable
              placeholder="输入或选择供应商"
              :disabled="isReadonly"
              @change="onDraftSupplierChange"
            >
              <el-option
                v-for="name in iv.linkage.value.knownSuppliers"
                :key="name"
                :label="name"
                :value="name"
              />
            </el-select>
          </label>
        </div>
        <template v-for="section in sections" :key="section.title">
          <h4 class="dialog-section-title">{{ section.title }}</h4>
          <div class="dialog-grid">
            <label
              v-for="item in section.items"
              :key="item.key"
              class="dialog-field"
              :class="{ wide: item.textarea }"
            >
              <span class="field-label">
                {{ item.label }}
                <template v-if="item.key === 'transactionAmountMatch' && draftAmount !== null">
                  （F2-68 采购额：{{ fmtAmount(draftAmount) }}）
                </template>
              </span>
              <el-date-picker
                v-if="item.type === 'date'"
                :model-value="draft.interviewDate"
                type="date"
                value-format="YYYY-MM-DD"
                style="width: 100%"
                :disabled="isReadonly"
                @update:model-value="(value: string | null) => { draft!.interviewDate = value ?? '' }"
              />
              <el-select
                v-else-if="item.type === 'method'"
                :model-value="draft.method || undefined"
                clearable
                placeholder="—"
                :disabled="isReadonly"
                @change="(value: string) => { (draft as any).method = value || '' }"
              >
                <el-option v-for="m in INTERVIEW_METHODS" :key="m" :label="m" :value="m" />
              </el-select>
              <el-select
                v-else-if="item.type === 'yesno'"
                :model-value="draft[item.key] || undefined"
                clearable
                placeholder="—"
                :disabled="isReadonly"
                @change="(value: string) => { (draft as any)[item.key] = value || '' }"
              >
                <el-option label="是" value="是" />
                <el-option label="否" value="否" />
              </el-select>
              <el-input
                v-else
                :model-value="String(draft[item.key] ?? '')"
                :type="item.textarea ? 'textarea' : 'text'"
                :autosize="item.textarea ? { minRows: 2, maxRows: 4 } : undefined"
                :placeholder="item.placeholder || ''"
                :disabled="isReadonly"
                @update:model-value="(value: string) => { (draft as any)[item.key] = value }"
              />
            </label>
          </div>
        </template>
        <div class="dialog-attachments">
          <span class="field-label">行程/证据附件（车票、机票、住宿发票、身份证/名片复印件、现场合影等）</span>
          <ItemAttachment
            v-if="!isNewDraft && projectId && wpId"
            :project-id="projectId"
            :wp-id="wpId"
            sheet-key="F2-71"
            :item-index="draft.attSlot"
          />
          <span v-else class="att-tip">保存档案后即可在卡片或矩阵中上传附件。</span>
        </div>
        <div class="dialog-preview">
          <span>填写完整度 <span class="formula">{{ Math.round(draftEnriched.completionPct * 100) }}%</span></span>
          <template v-if="draftEnriched.riskFlags.length">
            <el-tag v-for="flag in draftEnriched.riskFlags" :key="flag" type="danger" size="small" class="risk-tag">
              {{ flag }}
            </el-tag>
          </template>
          <span v-else class="ok-flag">未见异常</span>
        </div>
      </div>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button v-if="!isReadonly" type="primary" @click="saveDraft">保存访谈档案</el-button>
      </template>
    </el-dialog>

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
            @click="runAi('interview-summary-note')"
          >AI 填写审计说明</el-button>
        </div>
      </template>
      <el-input
        v-model="iv.auditNote.value"
        type="textarea"
        :autosize="{ minRows: 5, maxRows: 12 }"
        :disabled="isReadonly"
        placeholder="说明走访范围与选取标准、各供应商访谈执行情况、地址/交易金额/往来余额核对结果、发现的异常及处理……"
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
            @click="runAi('interview-summary-conclusion')"
          >AI 生成结论</el-button>
        </div>
      </template>
      <el-input
        :model-value="auditConclusion"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        :disabled="isReadonly"
        placeholder="综合评价供应商访谈覆盖率、核对结果与交易真实性结论。"
        @update:model-value="saveConclusion"
      />
    </el-card>

    <details class="fraud-details">
      <summary>⚠️ 提示2：访谈需核对和注意事项</summary>
      <div class="fraud-body">
        <ol>
          <li>走访地址与注册地址是否一致？不一致的原因是否合理？公司基本情况是否与工商信息查询信息一致？走访的公司地址是否与百度地图等查询走访地址一致？</li>
          <li>交易内容是否与走访公司实际业务范围一致？</li>
          <li>交易金额是否与走访公司规模（注册资本、人数、设备数量等）匹配？</li>
          <li>交易价格是否与同行业类似交易一致？</li>
          <li>是否核实走访对象身份？</li>
          <li>是否根据走访公司及访谈对象具体情况修改访谈问卷？</li>
          <li>是否现场获取盖公章的函证回函（交易、往来、关联方关系确认）？</li>
          <li>是否同为客户和供应商？理由是否合理？</li>
          <li>是否存在异常情况（如地址与被审计单位关联方相同或相近、已处于停产状态、产能利用率异常、无法证明相关产品来自被审计单位）？</li>
          <li>保留访谈对象身份证复印件、名片/工牌复印件、与访谈对象合影（厂区门口、仓库、车间等地）、走访公司工作现场照片。</li>
        </ol>
      </div>
    </details>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, toRef, type Ref } from 'vue'
import { useF2InterviewSummary } from '../../composables/useF2InterviewSummary'
import {
  INTERVIEW_METHODS,
  emptyInterviewSummaryEntity,
  enrichInterviewSummaryEntity,
  nextAttSlot,
  type EnrichedInterviewSummaryEntity,
  type InterviewSummaryEntity,
  type InterviewSummaryField,
} from '../../composables/useF2InterviewSummaryFormulas'
import { useF2SpecialAiGenerate, type F2SpeAiSection } from '../../composables/useF2SpecialAiGenerate'
import type { ChecklistResponse } from '../../composables/useF2SpecialFormData'
import F2SheetToolbar from '../../f2/shared/F2SheetToolbar.vue'
import GtIndexChip from '../../GtIndexChip.vue'
import ItemAttachment from '../../ItemAttachment.vue'
import F2InterviewCheckExample from './F2InterviewCheckExample.vue'

const props = defineProps<{
  wpId?: string
  projectId?: string
  allResponses: Map<string, ChecklistResponse>
  isReadonly: boolean
}>()

const exampleVisible = ref(false)

const iv = useF2InterviewSummary({
  allResponses: toRef(props, 'allResponses'),
  isReadonly: toRef(props, 'isReadonly'),
})

const viewMode = ref<'card' | 'matrix'>('card')

interface CheckItem {
  key: InterviewSummaryField
  label: string
  type?: 'date' | 'method' | 'yesno'
  textarea?: boolean
  riskWhenNo?: boolean
  placeholder?: string
}

const sections: Array<{ title: string; items: CheckItem[] }> = [
  {
    title: '一、访谈安排',
    items: [
      { key: 'interviewDate', label: '访谈时间', type: 'date' },
      { key: 'reason', label: '访谈原因', placeholder: '发行人第X大供应商/新增供应商/采购价格异常等' },
      { key: 'method', label: '访谈方式', type: 'method' },
      { key: 'registeredAddress', label: '被访谈公司注册地址', placeholder: '可从 F2-70 联动取数' },
      { key: 'visitAddress', label: '实地走访公司地址', placeholder: '与注册地址不一致时自动预警' },
    ],
  },
  {
    title: '二、访谈人员与行程',
    items: [
      { key: 'interviewee', label: '接受访谈人员及身份', placeholder: '身份信息、职务信息、具体负责的工作等' },
      { key: 'auditors', label: '参与访谈的审计人员' },
      { key: 'otherParticipants', label: '参与访谈的其他人员' },
      { key: 'tripInfo', label: '访谈人员行程信息', textarea: true, placeholder: '车票、机票、住宿发票、酒店照片等（附件上传）' },
    ],
  },
  {
    title: '三、现场核对情况',
    items: [
      { key: 'onSiteConfirmation', label: '是否现场函证', type: 'yesno', riskWhenNo: true },
      { key: 'focusPoints', label: '访谈关注要点', textarea: true },
      { key: 'contractCheck', label: '合同执行核对情况', textarea: true },
      { key: 'transactionAmountMatch', label: '交易金额核对是否一致', type: 'yesno', riskWhenNo: true },
      { key: 'balanceMatch', label: '往来金额核对是否一致', type: 'yesno', riskWhenNo: true },
    ],
  },
  {
    title: '四、结论与索引',
    items: [
      { key: 'conclusion', label: '访谈结论', textarea: true },
      { key: 'recordIndex', label: '访谈记录索引', placeholder: '如 F2-72-1（联动访谈明细）' },
    ],
  },
]

function linkedAddress(entity: EnrichedInterviewSummaryEntity): string {
  return entity.supplierName ? iv.linkage.value.registeredAddressOf(entity.supplierName) : ''
}

function linkedAmount(entity: EnrichedInterviewSummaryEntity): number | null {
  return entity.supplierName ? iv.linkage.value.purchaseAmountOf(entity.supplierName) : null
}

function fmtAmount(value: number): string {
  return value.toLocaleString('zh-CN', { maximumFractionDigits: 2 })
}

// ─── 弹窗录入 ────────────────────────────────────────────────────────────────
const dialogVisible = ref(false)
const draft = ref<InterviewSummaryEntity | null>(null)
const isNewDraft = ref(false)

const dialogTitle = computed(() => {
  if (props.isReadonly) return '访谈档案 · 查看'
  return isNewDraft.value ? '弹窗录入 · 新增供应商访谈' : `编辑访谈档案：${draft.value?.supplierName || '未命名'}`
})

const draftEnriched = computed(() =>
  enrichInterviewSummaryEntity(draft.value ?? emptyInterviewSummaryEntity()),
)

const draftAmount = computed(() =>
  draft.value?.supplierName ? iv.linkage.value.purchaseAmountOf(draft.value.supplierName) : null,
)

function onDraftSupplierChange(value: string): void {
  if (!draft.value) return
  draft.value.supplierName = value || ''
  if (draft.value.supplierName && !draft.value.registeredAddress) {
    draft.value.registeredAddress = iv.linkage.value.registeredAddressOf(draft.value.supplierName)
  }
}

function openCreateDialog(): void {
  if (props.isReadonly) return
  draft.value = emptyInterviewSummaryEntity(nextAttSlot(iv.entities.value))
  isNewDraft.value = true
  dialogVisible.value = true
}

function openEditDialog(id: string): void {
  const entity = iv.entities.value.find((item) => item.id === id)
  if (!entity) return
  draft.value = JSON.parse(JSON.stringify(entity)) as InterviewSummaryEntity
  isNewDraft.value = false
  dialogVisible.value = true
}

function saveDraft(): void {
  if (!draft.value || props.isReadonly) return
  const { id, ...patch } = draft.value
  if (iv.entities.value.some((entity) => entity.id === id)) {
    iv.updateEntity(id, patch)
  } else {
    iv.addEntityFrom(draft.value)
  }
  dialogVisible.value = false
}

// ─── 审计结论（沿用 f2-spe:save-items 持久化）───────────────────────────────
const CONCLUSION_KEY = 'F2-71-audit-conclusion'
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
  const legacy = props.allResponses.get('F2-71-audit-note')?.remark
  if (!iv.auditNote.value && legacy) iv.auditNote.value = legacy
})

// ─── AI 说明/结论 ────────────────────────────────────────────────────────────
const wpIdRef = toRef(() => props.wpId || '') as Ref<string>
const { aiAvailable, loading: aiLoading, generateAndConfirm } = useF2SpecialAiGenerate(wpIdRef)

function aiContext(): Record<string, unknown> {
  return {
    sheet: 'F2-71',
    summary: iv.summary.value,
    interviews: iv.enrichedEntities.value
      .filter((entity) => entity.supplierName.trim())
      .slice(0, 20)
      .map((entity) => ({
        supplierName: entity.supplierName,
        interviewDate: entity.interviewDate,
        reason: entity.reason,
        method: entity.method,
        registeredAddress: entity.registeredAddress,
        visitAddress: entity.visitAddress,
        isAddressMismatch: entity.isAddressMismatch,
        interviewee: entity.interviewee,
        auditors: entity.auditors,
        onSiteConfirmation: entity.onSiteConfirmation,
        focusPoints: entity.focusPoints,
        contractCheck: entity.contractCheck,
        transactionAmountMatch: entity.transactionAmountMatch,
        balanceMatch: entity.balanceMatch,
        f268PurchaseAmount: iv.linkage.value.purchaseAmountOf(entity.supplierName),
        conclusion: entity.conclusion,
        recordIndex: entity.recordIndex,
        completionPct: entity.completionPct,
        riskFlags: entity.riskFlags,
      })),
    auditNote: iv.auditNote.value,
  }
}

async function runAi(section: F2SpeAiSection): Promise<void> {
  const isNote = section === 'interview-summary-note'
  const content = await generateAndConfirm(
    section,
    isNote ? iv.auditNote.value : auditConclusion.value,
    aiContext(),
    isNote ? 'AI 生成 · 供应商访谈审计说明' : 'AI 生成 · 供应商访谈审计结论',
  )
  if (!content) return
  if (isNote) iv.auditNote.value = content
  else saveConclusion(content)
}
</script>

<style scoped>
.f2-interview-summary{padding:14px 18px;font-size:var(--wp-font-size, 13px);background:linear-gradient(180deg,#faf8fc 0,#fff 130px);--purple:#4b2d77}
.sheet-header,.stats,.tab-toolbar,.toolbar-left,.toolbar-right,.opinion-header{display: flex;align-items:center}.sheet-header,.tab-toolbar,.opinion-header{justify-content:space-between}.sheet-header{gap:12px;margin-bottom:12px}.sheet-header h3{margin:0;color:#35204f}.code{font-size:12px;color:#8c7b9d}.stats,.toolbar-left,.toolbar-right{gap:8px;flex-wrap:wrap}
.guidance-details{margin-bottom:12px;border-left:3px solid var(--purple);background:#f7f2fa;border-radius:5px;padding:8px 12px}.guidance-details summary{cursor:pointer;font-weight:600;color:var(--purple)}.guidance-content{margin-top:8px;color:#606266;line-height:1.75}.guidance-content p{margin:4px 0}.tab-toolbar{gap:10px;margin-bottom:12px}

/* 卡片模式 */
.card-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(400px,1fr));gap:12px}
.supplier-card{border-color:#ded3e8}.supplier-card :deep(.el-card__header){padding:9px 14px;background:#faf8fc}
.risk-card{border-color:#f3b2b2}.risk-card :deep(.el-card__header){background:#fdf3f3}
.card-head{display:flex;align-items:center;justify-content:space-between;gap:8px}
.card-title{display:flex;align-items:center;gap:8px;min-width:0;flex-wrap:wrap}.card-title strong{color:#35204f;overflow:hidden;text-overflow:ellipsis}
.card-actions{display:flex;align-items:center;flex-shrink:0}
.supplier-seq{font-size:11px;color:#8c7b9d;background:#f0e9f6;border-radius:3px;padding:1px 6px;white-space:nowrap}
.card-progress{display:flex;flex-direction:column;gap:4px;margin-bottom:8px}.progress-label{font-size:12px;color:#606266}
.card-fields{display:grid;grid-template-columns:1fr 1fr;gap:4px 14px;margin:0}
.card-field{display:flex;gap:6px;min-width:0}.card-field.wide{grid-column:1 / -1}
.card-field dt{color:#8c7b9d;flex-shrink:0}.card-field dd{margin:0;color:#303133;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.card-field.wide dd{white-space:normal}
.card-attachments{margin-top:8px;padding-top:8px;border-top:1px dashed #e4d9ee}
.att-label{display:block;font-size:12px;color:#8c7b9d;margin-bottom:4px}
.card-risk{margin-top:8px;padding-top:8px;border-top:1px dashed #e4d9ee}
.add-card{display:flex;flex-direction:column;align-items:center;justify-content:center;gap:6px;min-height:200px;border:1.5px dashed #b7a1cf;border-radius:6px;background:#fbf9fd;color:var(--purple);cursor:pointer;font-size:13px}
.add-card:hover{background:#f4eef9;border-color:var(--purple)}.add-plus{font-size:26px;line-height:1}

/* 矩阵模式 */
.table-scroll{max-width:100%;overflow-x: auto;border:1px solid #d7cae2;border-radius:7px}
.info-matrix{width:100%;min-width:900px;border-collapse:separate;border-spacing:0;font-size:11px}
.info-matrix th,.info-matrix td{border-right:1px solid #d8cce3;border-bottom:1px solid #d8cce3;padding:4px 6px;vertical-align:middle;background:#fff;text-align:center;min-width:220px}
.info-matrix thead th{position:sticky;top:0;z-index:3;background:var(--purple);color:#fff;font-weight:600}
.info-matrix .sticky{position:sticky;left:0;z-index:4}.info-matrix th.sticky{z-index:5}
.item-col{width:185px;min-width:185px !important;background:#f5f0f8 !important;color:#4b2d77;font-weight:600;text-align:left !important}
.info-matrix thead th.item-col{color:#4b2d77}
.supplier-head-inner{display:flex;align-items:center;justify-content:space-between;margin-bottom:4px}
.head-ops{display:inline-flex;gap:0}.head-btn{color:#e8dff2 !important}
.info-matrix .supplier-seq{color:#e8dff2;background:transparent;padding:0}
.risk-head{background:#7a3b52 !important}
.section-row .section-cell{background:#e8dff0 !important;color:#3f2465;font-weight:700;text-align:left !important;padding:5px 8px}
.risk-cell{background:#fef0f0 !important}
.calc-cell{background:#f2ecf7 !important}
.att-cell{text-align:left}
.cell-with-link{display:flex;align-items:center;gap:2px}.cell-with-link .el-input{flex:1}.link-btn{flex-shrink:0;font-size:11px}
.link-hint{margin-top:3px;font-size:11px;color:#8c7b9d;text-align:left}
.formula{border-bottom:1px dotted #8d78a2;cursor:help;color:#4b2d77;font-weight:600}
.risk-tag{margin:1px 2px}.ok-flag{color:#67a23a}

/* 弹窗录入 */
.dialog-body{max-height:64vh;overflow-y:auto;padding-right:6px}
.example-dialog-body{max-height:68vh;overflow-y:auto;padding-right:6px}
.dialog-name-row{margin-bottom:6px}
.dialog-section-title{margin:12px 0 8px;padding:5px 10px;background:#f0e9f6;border-left:3px solid var(--purple);border-radius:3px;color:#3f2465;font-size:13px}
.dialog-grid{display:grid;grid-template-columns:1fr 1fr;gap:8px 14px}
.dialog-field{display:flex;flex-direction:column;gap:4px;font-size:12px}.dialog-field.wide{grid-column:1 / -1}
.field-label{color:#606266}
.dialog-attachments{margin-top:14px;padding:8px 12px;background:#fbf9fd;border:1px dashed #d7cae2;border-radius:5px}
.att-tip{font-size:12px;color:#a596b5}
.dialog-preview{display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-top:14px;padding:8px 12px;background:#f7f2fa;border-radius:5px;color:#606266}

.opinion-card{margin-top:16px;border-color:#ded3e8}.opinion-card :deep(.el-card__header){padding:10px 14px;background:#faf8fc}.opinion-header span{font-weight:700;color:var(--purple)}
.fraud-details{margin-top:14px;border:1px solid #fde2e2;border-left:3px solid #f56c6c;border-radius:5px;background:#fffafa}.fraud-details summary{cursor:pointer;padding:9px 13px;color:#c45656;font-weight:600}.fraud-body{padding:0 16px 12px;color:#606266;line-height:1.75}.fraud-body ol{margin:4px 0 10px;padding-left:22px}
</style>
