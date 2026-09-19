<template>
  <div class="g1-level3" data-testid="g1-level3-reconciliation">
    <div class="methodology">
      {{ FORMULA_HINT }}；「企业报告期末」与公式期末差异 > 0.01 须核查说明。
    </div>

    <div class="section-head">
      <h3 class="sheet-title">G1-7 第三层次公允价值计量的调节表</h3>
      <div class="head-actions tab-toolbar">
        <G1ImportExportDropdown
          v-if="wpId"
          :wp-id="wpId"
          sheet="G1-7"
          :disabled="isReadonly"
          @imported="onImported"
        />
        <el-button size="small" type="primary" :disabled="isReadonly" @click="l3.addRow()">新增调节行</el-button>
        <el-button size="small" :disabled="isReadonly" @click="l3.pullFromDetail()">从 G1-2 带入</el-button>
        <el-button size="small" :disabled="isReadonly" @click="l3.pullFromFairValueTest()">从 G1-6 带入</el-button>
        <span class="chip-wrap"><GtIndexChip value="wp:G1-2" /></span>
        <span class="chip-wrap"><GtIndexChip value="wp:G1-6" /></span>
        <el-tag size="small" type="info">共 {{ l3.rows.value.length }} 行</el-tag>
        <el-button size="small" @click="openReviewDialog('G1-7-conclusion')">💬复核</el-button>
      </div>
    </div>

    <el-alert
      type="info"
      :closable="false"
      show-icon
      class="objective-alert"
      title="审计目标：确定交易性金融资产以恰当的金额列示于财务报表，相关的计价或分摊调整已恰当记录，相关披露已恰当计量和描述。"
    />

    <details class="audit-process" open>
      <summary>二、审计过程</summary>
      <ol>
        <li>获取第三层次公允价值计量明细，验证加计正确性。</li>
        <li>判断第三层次公允价值计量的调节过程披露是否恰当（与附注⑤ / 上市公司披露格式勾稽）。</li>
      </ol>
    </details>

    <el-alert
      v-if="l3.varianceRows.value.length"
      type="warning"
      :closable="false"
      class="var-alert"
      :title="`${l3.varianceRows.value.length} 行存在差异（企业报告期末 ≠ 公式期末）`"
    />
    <el-alert
      v-if="l3.unrealizedWarnings.value.length"
      type="warning"
      :closable="false"
      class="var-alert"
      :title="`仍持有未实现校验：${l3.unrealizedWarnings.value.map(w => `${w.itemName}（${w.reason}）`).join('；')}`"
    />

    <el-table :data="l3.rows.value" border size="small" max-height="520" class="l3-table">
      <el-table-column label="序号" width="52" fixed>
        <template #default="{ $index }">{{ $index + 1 }}</template>
      </el-table-column>
      <el-table-column label="投资项目" min-width="130" fixed>
        <template #default="{ row }">
          <el-input
            v-model="row.itemName"
            size="small"
            :disabled="isReadonly"
            @change="l3.updateRow(row.id, { itemName: row.itemName })"
          />
        </template>
      </el-table-column>
      <el-table-column label="品种" width="120" fixed>
        <template #default="{ row }">
          <el-select
            v-model="row.assetClass"
            size="small"
            :disabled="isReadonly"
            style="width:100%"
            @change="l3.updateRow(row.id, { assetClass: row.assetClass })"
          >
            <el-option
              v-for="opt in ASSET_CLASS_OPTIONS"
              :key="opt.value"
              :label="opt.label"
              :value="opt.value"
            />
          </el-select>
        </template>
      </el-table-column>
      <el-table-column label="期初余额" width="100" align="right">
        <template #default="{ row }">
          <WpAmountInput
            v-model="row.openingBalance"
            size="small"
            :disabled="isReadonly"
            style="width:100%"
            @change="l3.updateRow(row.id, { openingBalance: row.openingBalance })"
          />
        </template>
      </el-table-column>

      <el-table-column label="转入/转出第三层次" align="center">
        <el-table-column label="转入" width="96" align="right">
          <template #default="{ row }">
            <el-input-number
              v-model="row.transferIn"
              size="small"
              :controls="false"
              :disabled="isReadonly"
              style="width:100%"
              @change="l3.updateRow(row.id, { transferIn: row.transferIn })"
            />
          </template>
        </el-table-column>
        <el-table-column label="转出" width="96" align="right">
          <template #default="{ row }">
            <el-input-number
              v-model="row.transferOut"
              size="small"
              :controls="false"
              :disabled="isReadonly"
              style="width:100%"
              @change="l3.updateRow(row.id, { transferOut: row.transferOut })"
            />
          </template>
        </el-table-column>
      </el-table-column>

      <el-table-column label="当期利得或损失总额" align="center">
        <el-table-column label="公允价值变动损益" width="120" align="right">
          <template #default="{ row }">
            <WpAmountInput
              v-model="row.gainPl"
              size="small"
              :disabled="isReadonly"
              style="width:100%"
              @change="l3.updateRow(row.id, { gainPl: row.gainPl })"
            />
          </template>
        </el-table-column>
        <el-table-column label="投资收益" width="100" align="right">
          <template #default="{ row }">
            <el-input-number
              v-model="row.investmentIncome"
              size="small"
              :controls="false"
              :disabled="isReadonly"
              style="width:100%"
              @change="l3.updateRow(row.id, { investmentIncome: row.investmentIncome })"
            />
          </template>
        </el-table-column>
      </el-table-column>

      <el-table-column label="购买、发行、出售和结算" align="center">
        <el-table-column label="购买" width="88" align="right">
          <template #default="{ row }">
            <el-input-number
              v-model="row.purchase"
              size="small"
              :controls="false"
              :disabled="isReadonly"
              style="width:100%"
              @change="l3.updateRow(row.id, { purchase: row.purchase })"
            />
          </template>
        </el-table-column>
        <el-table-column label="发行" width="80" align="right">
          <template #default="{ row }">
            <el-input-number
              v-model="row.issue"
              size="small"
              :controls="false"
              :disabled="isReadonly"
              style="width:100%"
              @change="l3.updateRow(row.id, { issue: row.issue })"
            />
          </template>
        </el-table-column>
        <el-table-column label="出售" width="80" align="right">
          <template #default="{ row }">
            <el-input-number
              v-model="row.sale"
              size="small"
              :controls="false"
              :disabled="isReadonly"
              style="width:100%"
              @change="l3.updateRow(row.id, { sale: row.sale })"
            />
          </template>
        </el-table-column>
        <el-table-column label="结算" width="80" align="right">
          <template #default="{ row }">
            <el-input-number
              v-model="row.settlement"
              size="small"
              :controls="false"
              :disabled="isReadonly"
              style="width:100%"
              @change="l3.updateRow(row.id, { settlement: row.settlement })"
            />
          </template>
        </el-table-column>
      </el-table-column>

      <el-table-column label="期末余额" width="100" align="right">
        <template #default="{ row }">
          <span class="formula-cell" :title="FORMULA_HINT">{{ fmtNum(row.closingBalance) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="仍持有未实现损益变动" width="130" align="right">
        <template #header>
          <el-tooltip
            content="对于在报告期末持有的资产，计入损益的当期未实现利得或损失的变动"
            placement="top"
          >
            <span>仍持有未实现</span>
          </el-tooltip>
        </template>
        <template #default="{ row }">
          <el-input-number
            v-model="row.unrealizedHeld"
            size="small"
            :controls="false"
            :disabled="isReadonly"
            style="width:100%"
            :class="{ 'uh-warn': hasUnrealizedWarn(row.id) }"
            @change="l3.updateRow(row.id, { unrealizedHeld: row.unrealizedHeld })"
          />
        </template>
      </el-table-column>
      <el-table-column label="企业报告期末" width="110" align="right">
        <template #default="{ row }">
          <el-input-number
            v-model="row.reportedClosing"
            size="small"
            :controls="false"
            :disabled="isReadonly"
            style="width:100%"
            @change="l3.updateRow(row.id, { reportedClosing: row.reportedClosing })"
          />
        </template>
      </el-table-column>
      <el-table-column label="差异" width="88" align="right">
        <template #default="{ row }">
          <span :class="{ 'var-warn': Math.abs(row.variance) > 0.01 }">{{ fmtNum(row.variance) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="备注" min-width="100">
        <template #default="{ row }">
          <el-input
            v-model="row.remark"
            size="small"
            :disabled="isReadonly"
            @change="l3.updateRow(row.id, { remark: row.remark })"
          />
        </template>
      </el-table-column>
      <el-table-column v-if="!isReadonly" label="操作" width="56" fixed="right">
        <template #default="{ row }">
          <el-button size="small" type="danger" link @click="l3.removeRow(row.id)">删</el-button>
        </template>
      </el-table-column>
    </el-table>

    <div class="totals" data-testid="g1-l3-totals">
      <span class="total-label">合计</span>
      <span>期初 {{ fmtNum(l3.grandTotal.value.openingBalance) }}</span>
      <span>转入 {{ fmtNum(l3.grandTotal.value.transferIn) }}</span>
      <span>转出 {{ fmtNum(l3.grandTotal.value.transferOut) }}</span>
      <span>公允变动 {{ fmtNum(l3.grandTotal.value.gainPl) }}</span>
      <span>投资收益 {{ fmtNum(l3.grandTotal.value.investmentIncome) }}</span>
      <span>公式期末 {{ fmtNum(l3.grandTotal.value.closingBalance) }}</span>
      <span>企业报告 {{ fmtNum(l3.grandTotal.value.reportedClosing) }}</span>
      <span :class="{ 'var-warn': Math.abs(l3.grandTotal.value.variance) > 0.01 }">
        差异 {{ fmtNum(l3.grandTotal.value.variance) }}
      </span>
      <span>仍持有未实现 {{ fmtNum(l3.grandTotal.value.unrealizedHeld) }}</span>
    </div>

    <G1AuditTextCards
      :wp-id="wpId"
      :is-readonly="isReadonly"
      v-model:note="auditNote"
      :conclusion="l3.auditConclusion.value"
      @update:conclusion="(v: string) => { l3.auditConclusion.value = v }"
      note-ai-section="level3-note"
      conclusion-ai-section="level3-conclusion"
      note-placeholder="填写审计说明：可概述第三层次调节各行变动核实、层次转入转出原因、企业报告期末与公式期末差异核查，以及仍持有资产未实现损益披露是否恰当。"
      note-hint="覆盖 Level3 调节勾稽、层次转移及与 G1-6 / 附注⑤ 勾稽。"
      :related-context="{ 行数: l3.rows.value.length, 差异行数: l3.varianceRows.value.length }"
    />

    <details class="prep-hint">
      <summary>📋 编制提示</summary>
      <ul>
        <li>{{ FORMULA_HINT }}，系统自动计算期末余额。</li>
        <li>「品种」用于附注⑤按债务工具 / 权益工具 / 衍生拆分同步；其他归入权益工具叶子。</li>
        <li>优先「从 G1-2 带入」拉取 Level3 明细变动；「从 G1-6 带入」可补估值期末勾稽。</li>
        <li>列结构对齐致同纸质底稿与 CAS 39：层次转移、当期利得或损失（公允变动/投资收益）、购买发行出售结算、仍持有未实现损益。</li>
        <li>估值方法、关键假设、敏感性分析在 G1-6 公允价值测试中记录；本表聚焦期初至期末数量金额调节。</li>
        <li>交易性金融资产计入损益，一般无 OCI；「投资收益」列对应利息/股利/处置等已实现损益。</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
import WpAmountInput from '../../shared/WpAmountInput.vue'
import { ref, toRef, inject, watch, computed } from 'vue'
import {
  useG1Level3,
  G1_LEVEL3_FORMULA_HINT,
  G1_LEVEL3_ASSET_CLASS_OPTIONS,
} from '../../composables/useG1Level3'
import type { ChecklistResponse } from '../../composables/useF1FormData'
import GtIndexChip from '../../GtIndexChip.vue'
import G1AuditTextCards from '../G1AuditTextCards.vue'
import G1ImportExportDropdown from '../G1ImportExportDropdown.vue'

const props = defineProps<{
  allResponses: Map<string, ChecklistResponse>
  isReadonly: boolean
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
  wpId?: string
}>()

const wpId = computed(() => props.wpId ?? '')

const emit = defineEmits<{ imported: [] }>()

const openReviewDialog = inject<(sectionId: string) => void>('openReviewDialog', () => {})

const l3 = useG1Level3({
  allResponses: toRef(props, 'allResponses'),
  debouncedSave: props.debouncedSave,
  isReadonly: toRef(props, 'isReadonly'),
})

const FORMULA_HINT = G1_LEVEL3_FORMULA_HINT
const ASSET_CLASS_OPTIONS = G1_LEVEL3_ASSET_CLASS_OPTIONS

const AUDIT_NOTE_KEY = 'G1-7-audit-note'
const auditNote = ref(props.allResponses.get(AUDIT_NOTE_KEY)?.remark ?? '')
watch(auditNote, (v) => {
  if (!props.isReadonly) props.debouncedSave(AUDIT_NOTE_KEY, { conclusion: null, remark: v })
})

function onImported() {
  emit('imported')
  l3.loadAll()
}

function hasUnrealizedWarn(id: string): boolean {
  return l3.unrealizedWarnings.value.some((w) => w.id === id)
}

function fmtNum(v: unknown): string {
  if (typeof v !== 'number' || Number.isNaN(v)) return String(v ?? '')
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.g1-level3 { padding: 12px; font-size: var(--wp-font-size, 13px); }
.g1-level3 :deep(.el-table) { --el-table-font-size: var(--wp-font-size, 13px); font-size: var(--wp-font-size, 13px); }
.g1-level3 :deep(.el-table .cell) { font-size: var(--wp-font-size, 13px); }
.methodology {
  border-left: 4px solid #e6a23c;
  background: #fdf6ec;
  padding: 8px 12px;
  margin-bottom: 10px;
  font-size: 12px;
  color: #606266;
}
.section-head { display: flex; justify-content: space-between; align-items: flex-start; gap: 12px; margin-bottom: 14px; flex-wrap: wrap; }
.sheet-title { margin: 0; font-size: 16px; font-weight: 600; color: #1f2a37; }
.head-actions { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.chip-wrap { display: inline-flex; align-items: center; }
.objective-alert { margin-bottom: 10px; }
.audit-process {
  margin-bottom: 10px;
  padding: 8px 12px;
  background: #f8f9fb;
  border: 1px solid #ebeef5;
  border-radius: 6px;
  font-size: 12px;
  color: #606266;
}
.audit-process summary { cursor: pointer; font-weight: 500; color: #303133; }
.audit-process ol { margin: 6px 0 0; padding-left: 18px; }
.var-alert { margin-bottom: 8px; }
.formula-cell { border-bottom: 1px dashed #909399; cursor: help; background: #f5f7fa; display: inline-block; width: 100%; text-align: right; }
.var-warn { color: #f56c6c; font-weight: 600; }
.uh-warn :deep(.el-input__inner) { color: #e6a23c; font-weight: 600; }
.totals {
  margin-top: 12px;
  padding: 8px 12px;
  background: #f5f7fa;
  border-radius: 6px;
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  font-size: 12px;
  font-weight: 600;
  color: #303133;
}
.total-label { margin-right: 4px; }
.prep-hint { margin-top: 12px; font-size: 12px; color: #909399; }
.prep-hint summary { cursor: pointer; }
.prep-hint ul { margin: 8px 0 0; padding-left: 18px; }
</style>
