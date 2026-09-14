<!--
  K1TabBadDebtCalc.vue — K1-8 坏账准备测算

  对齐致同源模板：
    (一) 单项计提
    (二) 押金/保证金组合 — 信用期
    (三) 其他组合 — 账龄（3年段 / 5年段 / 自定义，多组合）
  公式：应计提③ = ①×②；差异⑤ = ③−④
-->
<template>
  <div class="k1-audit-sheet">
    <div class="section-head">
      <h3 class="sheet-title">K1-8 坏账准备测算</h3>
      <div class="head-actions">
        <el-button size="small" @click="onExportTemplate">导出模板</el-button>
        <el-button size="small" @click="onExportData">导出数据</el-button>
        <el-upload v-if="!isReadonly" :show-file-list="false" accept=".xlsx,.xls" :auto-upload="false" :on-change="onImportChange">
          <el-button size="small" :loading="importing">导入 Excel</el-button>
        </el-upload>
        <el-button size="small" type="primary" link @click="handleReview">💬 复核</el-button>
      </div>
    </div>

    <el-alert type="info" :closable="false" class="audit-objective">
      <template #title><span class="ao-title">一、审计目标</span></template>
      <p class="ao-text">其他应收款、坏账准备以恰当的金额包括在财务报表中，与之相关的计价或分摊调整已恰当记录，相关披露已得到恰当计量和描述。</p>
    </el-alert>

    <details class="compile-hint top-hint">
      <summary>编制提示</summary>
      <ul>
        <li>结构对齐源模板：单项 → 押金/保证金（信用期）→ 账龄组合；不适用的信用期行可删除。</li>
        <li>公式：应计提③ = 审定余额① × 预期信用损失率②；差异⑤ = 应计提③ − 账面准备④。</li>
        <li>账龄段支持「3年段 / 5年段 / 自定义」枚举（默认 5 年双标签）；切换后各组合账龄行自动同步并保留已填数。</li>
        <li>账龄从确认资产凭证日期起算，需考虑信用期；组合划分应与 K1-6 会计政策一致。</li>
        <li>预期信用损失率可参考 K2 账龄-预期信用损失率测算表；测算合计须与 K1-3 坏账准备明细勾稽。</li>
      </ul>
    </details>

    <div class="aging-toolbar">
      <span class="muted">账龄口径</span>
      <el-select
        :model-value="calc.agingPreset.value"
        size="small"
        style="width: 110px"
        :disabled="isReadonly"
        @change="onAgingPresetChange"
      >
        <el-option label="3年段" value="THREE_YEAR" />
        <el-option label="5年段" value="FIVE_YEAR" />
        <el-option label="自定义" value="CUSTOM" />
      </el-select>
      <el-tag size="small" type="info">{{ calc.agingSegments.value.length }} 段</el-tag>

      <el-button
        size="small"
        type="primary"
        plain
        :disabled="isReadonly"
        @click="onPullFromK1Detail"
      >从 K1-2 灌数</el-button>
    </div>

    <el-alert
      :type="Math.abs(calc.grandTotal.value.diff) < 0.01 ? 'success' : 'warning'"
      :closable="false"
      show-icon
      class="recon-bar"
    >
      <template #title>
        测算合计差异（应计提 − 账面）：{{ fmtAmt(calc.grandTotal.value.diff) }}
        <span v-if="Math.abs(calc.grandTotal.value.diff) < 0.01">　✓ 核对差异为零</span>
        <span v-else>　⚠ 存在差异，需分析计提是否充分</span>
      </template>
    </el-alert>

    <el-alert v-if="calc.diffAlert.value" type="warning" :closable="false" show-icon :title="calc.diffAlert.value" class="recon-bar" />

    <el-alert
      v-if="portfolioDeeplinkHint"
      type="info"
      :closable="true"
      class="deeplink-bar"
      @close="portfolioDeeplinkHint = ''"
    >
      <template #title><span>{{ portfolioDeeplinkHint }}</span></template>
    </el-alert>

    <!-- (一) 单项计提 -->
    <el-card shadow="never" class="section-card">
      <template #header>
        <div class="card-header-row">
          <span class="card-title">（一）单项计提坏账准备</span>
          <el-button v-if="!isReadonly" size="small" @click="calc.addSingleRow(); persist()">＋ 新增</el-button>
        </div>
      </template>
      <el-table :data="calc.singleRows.value" border size="small" :max-height="260" class="audit-table">
        <el-table-column label="债务人名称" min-width="150">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.label" size="small"
              @change="(v: string) => { calc.updateSingleCell(row.rowId, 'label', v); persist() }" />
            <span v-else>{{ row.label || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="审定账面余额①" min-width="120" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.auditedBalance" :controls="false" size="small" class="amt"
              @update:model-value="(v: number) => { calc.updateSingleCell(row.rowId, 'auditedBalance', v ?? 0); persist() }" />
            <span v-else class="amount-cell">{{ fmtAmt(row.auditedBalance) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="预期信用损失率②" width="130" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.lossRate" :controls="false" :min="0" :max="1" :precision="4" size="small" class="amt"
              @update:model-value="(v: number) => { calc.updateSingleCell(row.rowId, 'lossRate', v ?? 0); persist() }" />
            <span v-else>{{ pct(row.lossRate) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期末应计提③=①×②" min-width="130" align="right">
          <template #default="{ row }">
            <span class="formula-cell" title="③=①×②">{{ fmtAmt(row.expectedProvision) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期末坏账准备账面④" min-width="130" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.bookProvision" :controls="false" size="small" class="amt"
              @update:model-value="(v: number) => { calc.updateSingleCell(row.rowId, 'bookProvision', v ?? 0); persist() }" />
            <span v-else class="amount-cell">{{ fmtAmt(row.bookProvision) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="差异⑤=③-④" min-width="110" align="right">
          <template #default="{ row }">
            <span class="formula-cell" :class="{ 'diff-warn': Math.abs(row.difference) > 0.01 }" title="⑤=③-④">{{ fmtAmt(row.difference) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="计提依据及文件" min-width="150">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.basis" size="small"
              @change="(v: string) => { calc.updateSingleCell(row.rowId, 'basis', v); persist() }" />
            <span v-else>{{ row.basis || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="索引号" width="90">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.indexRef" size="small"
              @change="(v: string) => { calc.updateSingleCell(row.rowId, 'indexRef', v); persist() }" />
            <span v-else>{{ row.indexRef || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column v-if="!isReadonly" label="操作" width="56" align="center" fixed="right">
          <template #default="{ row }">
            <el-button size="small" type="danger" link @click="calc.removeSingleRow(row.rowId); persist()">删除</el-button>
          </template>
        </el-table-column>
        <template #append>
          <div class="table-total">
            小计　应计提③：{{ fmtAmt(calc.singleTotal.value.expected) }}　账面④：{{ fmtAmt(calc.singleTotal.value.book) }}
          </div>
        </template>
      </el-table>
    </el-card>

    <!-- (二) 押金/保证金组合 -->
    <el-card shadow="never" class="section-card">
      <template #header>
        <span class="card-title">（二）押金/保证金组合计提坏账准备（按信用期）</span>
        <span class="hint-inline">【不适用的行项目请删除】</span>
      </template>
      <p class="aging-hint">逾期从确认资产凭证日期起计算，逾期需考虑信用期。</p>
      <div v-for="group in calc.creditGroups.value" :key="group.groupId">
        <el-table :data="group.rows.filter(r => !r.archived)" border size="small" class="audit-table">
          <el-table-column label="信用期" min-width="160" prop="label" />
          <el-table-column label="审定账面余额①" min-width="120" align="right">
            <template #default="{ row }">
              <el-input-number v-if="!isReadonly" :model-value="row.auditedBalance" :controls="false" size="small" class="amt"
                @update:model-value="(v: number) => { calc.updateCreditCell(group.groupId, row.rowId, 'auditedBalance', v ?? 0); persist() }" />
              <span v-else class="amount-cell">{{ fmtAmt(row.auditedBalance) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="预期信用损失率②" width="130" align="right">
            <template #default="{ row }">
              <el-input-number v-if="!isReadonly" :model-value="row.lossRate" :controls="false" :min="0" :max="1" :precision="4" size="small" class="amt"
                @update:model-value="(v: number) => { calc.updateCreditCell(group.groupId, row.rowId, 'lossRate', v ?? 0); persist() }" />
              <span v-else>{{ pct(row.lossRate) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="期末应计提③=①×②" min-width="130" align="right">
            <template #default="{ row }"><span class="formula-cell" title="③=①×②">{{ fmtAmt(row.expectedProvision) }}</span></template>
          </el-table-column>
          <el-table-column label="期末坏账准备账面④" min-width="130" align="right">
            <template #default="{ row }">
              <el-input-number v-if="!isReadonly" :model-value="row.bookProvision" :controls="false" size="small" class="amt"
                @update:model-value="(v: number) => { calc.updateCreditCell(group.groupId, row.rowId, 'bookProvision', v ?? 0); persist() }" />
              <span v-else class="amount-cell">{{ fmtAmt(row.bookProvision) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="差异⑤=③-④" min-width="110" align="right">
            <template #default="{ row }">
              <span class="formula-cell" :class="{ 'diff-warn': Math.abs(row.difference) > 0.01 }">{{ fmtAmt(row.difference) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="计提依据" min-width="140">
            <template #default="{ row }">
              <el-input v-if="!isReadonly" :model-value="row.basis" size="small"
                @change="(v: string) => { calc.updateCreditCell(group.groupId, row.rowId, 'basis', v); persist() }" />
              <span v-else>{{ row.basis || '—' }}</span>
            </template>
          </el-table-column>
          <el-table-column v-if="!isReadonly" label="" width="50" align="center">
            <template #default="{ row }">
              <el-button type="danger" text size="small" @click="calc.removeCreditRow(group.groupId, row.rowId); persist()">删</el-button>
            </template>
          </el-table-column>
        </el-table>
      </div>
      <div class="table-total">
        信用期小计　应计提③：{{ fmtAmt(calc.creditTotal.value.expected) }}　账面④：{{ fmtAmt(calc.creditTotal.value.book) }}
      </div>
    </el-card>

    <!-- (三) 其他组合（账龄） -->
    <el-card shadow="never" class="section-card">
      <template #header>
        <div class="card-header-row">
          <span class="card-title">（三）其他组合计提坏账准备（按账龄）</span>
          <el-button v-if="!isReadonly" size="small" @click="calc.addAgingGroup(); persist()">添加组合</el-button>
        </div>
      </template>
      <p class="aging-hint">默认 5 年段标签对齐源模板「账龄/逾期」双口径；可切换 3 年段或自定义段名。</p>

      <div v-for="(group, gIdx) in calc.agingGroups.value" :key="group.groupId"
        :data-group-id="group.groupId"
        class="aging-group"
        :class="{ 'group-deeplink-hl': groupHighlightId === group.groupId }"
      >
        <div class="group-header">
          <el-input
            v-if="!isReadonly"
            :model-value="group.groupName"
            size="small"
            placeholder="组合名称"
            style="width:180px"
            @change="(v: string) => { calc.updateGroupName(group.groupId, v); persist() }"
          />
          <span v-else class="group-name">{{ group.groupName || `组合${gIdx + 1}` }}</span>
          <el-button
            v-if="group.groupName"
            size="small"
            type="primary"
            link
            @click="navigateToK11(group.groupName)"
          >→ K1-1</el-button>
          <el-button v-if="!isReadonly" type="danger" text size="small" @click="calc.removeAgingGroup(group.groupId); persist()">删除组合</el-button>
        </div>
        <el-table :data="group.rows.filter(r => !r.archived)" border size="small" class="audit-table">
          <el-table-column label="账龄" min-width="180" prop="label" />
          <el-table-column label="审定账面余额①" min-width="120" align="right">
            <template #default="{ row }">
              <el-input-number v-if="!isReadonly" :model-value="row.auditedBalance" :controls="false" size="small" class="amt"
                @update:model-value="(v: number) => { calc.updateAgingCell(group.groupId, row.rowId, 'auditedBalance', v ?? 0); persist() }" />
              <span v-else class="amount-cell">{{ fmtAmt(row.auditedBalance) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="预期信用损失率②" width="130" align="right">
            <template #default="{ row }">
              <el-input-number v-if="!isReadonly" :model-value="row.lossRate" :controls="false" :min="0" :max="1" :precision="4" size="small" class="amt"
                @update:model-value="(v: number) => { calc.updateAgingCell(group.groupId, row.rowId, 'lossRate', v ?? 0); persist() }" />
              <span v-else>{{ pct(row.lossRate) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="期末应计提③=①×②" min-width="130" align="right">
            <template #default="{ row }"><span class="formula-cell" title="③=①×②">{{ fmtAmt(row.expectedProvision) }}</span></template>
          </el-table-column>
          <el-table-column label="期末坏账准备账面④" min-width="130" align="right">
            <template #default="{ row }">
              <el-input-number v-if="!isReadonly" :model-value="row.bookProvision" :controls="false" size="small" class="amt"
                @update:model-value="(v: number) => { calc.updateAgingCell(group.groupId, row.rowId, 'bookProvision', v ?? 0); persist() }" />
              <span v-else class="amount-cell">{{ fmtAmt(row.bookProvision) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="差异⑤=③-④" min-width="110" align="right">
            <template #default="{ row }">
              <span class="formula-cell" :class="{ 'diff-warn': Math.abs(row.difference) > 0.01 }">{{ fmtAmt(row.difference) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="计提依据" min-width="140">
            <template #default="{ row }">
              <el-input v-if="!isReadonly" :model-value="row.basis" size="small"
                @change="(v: string) => { calc.updateAgingCell(group.groupId, row.rowId, 'basis', v); persist() }" />
              <span v-else>{{ row.basis || '—' }}</span>
            </template>
          </el-table-column>
          <el-table-column label="索引号" width="90">
            <template #default="{ row }">
              <el-input v-if="!isReadonly" :model-value="row.indexRef" size="small"
                @change="(v: string) => { calc.updateAgingCell(group.groupId, row.rowId, 'indexRef', v); persist() }" />
              <span v-else>{{ row.indexRef || '—' }}</span>
            </template>
          </el-table-column>
        </el-table>
        <div class="group-sub">小计 — 应计提 {{ fmtAmt(sumGroup(group)) }}</div>
      </div>
      <div class="table-total">
        账龄合计　应计提③：{{ fmtAmt(calc.agingTotal.value.expected) }}　账面④：{{ fmtAmt(calc.agingTotal.value.book) }}
      </div>
      <div class="table-total grand">
        总计　应计提③：{{ fmtAmt(calc.grandTotal.value.expected) }}　账面④：{{ fmtAmt(calc.grandTotal.value.book) }}　核对差异：{{ fmtAmt(calc.grandTotal.value.diff) }}
      </div>
    </el-card>

    <el-card shadow="never" class="section-card">
      <template #header><span class="card-title">三、审计说明</span></template>
      <el-input v-model="auditNote" type="textarea" :autosize="{ minRows: 3 }" :disabled="isReadonly"
        placeholder="（1）选取金额大于X且逾期超过Y天的账户，与授信部门了解并复核往来函件；（2）预期信用损失率计量参考 K2 账龄-预期信用损失率测算表" @change="persist" />
    </el-card>

    <el-card shadow="never" class="conclusion-card">
      <template #header><span class="card-title">四、审计结论</span></template>
      <el-select v-model="conclusionOption" :disabled="isReadonly" size="small" class="concl-select"
        placeholder="选择结论模板" @change="onConclusionOption">
        <el-option label="A、未见异常" value="A" />
        <el-option label="B、除上述调整事项外，其余未见异常" value="B" />
        <el-option label="C、存在重大未调整事项，不可确认" value="C" />
      </el-select>
      <el-input v-model="conclusion" type="textarea" :autosize="{ minRows: 2 }" :disabled="isReadonly"
        placeholder="形成审计结论..." @change="persist" />
    </el-card>

    <el-dialog v-model="showAgingDialog" title="自定义账龄段" width="420px" destroy-on-close @close="cancelAgingDialog">
      <p class="muted">每行一个账龄段名称（至少 2 段，最多 10 段）。</p>
      <el-input v-model="agingDraft" type="textarea" :autosize="{ minRows: 6, maxRows: 12 }"
        placeholder="例：&#10;6个月以内&#10;6个月-1年&#10;1-2年&#10;2年以上" />
      <template #footer>
        <el-button @click="cancelAgingDialog">取消</el-button>
        <el-button type="primary" @click="confirmAgingCustom">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, inject, toRef, nextTick } from 'vue'
import type { UploadFile } from 'element-plus'
import {
  useK1BadDebtCalcSheet,
  type K1AgingPreset,
  type K1CalcGroup,
} from '../../composables/useK1BadDebtCalcSheet'
import { K1_CONCLUSION_TEMPLATES } from '../../composables/useK1AuditRows'
import { useK1ImportExport } from '../../composables/useK1ImportExport'
import {
  K1RowNavigationKey,
  buildK1PortfolioDeeplinkHint,
  resolveK18GroupFocus,
} from '../../composables/useK1RowNavigation'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()
const emit = defineEmits<{
  (e: 'save', itemId: string, value: any): void
  (e: 'navigate-sheet', sheetName: string): void
}>()
const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})
const k1Nav = inject(K1RowNavigationKey, null)

const calc = useK1BadDebtCalcSheet()
const { isImporting: importing, exportTemplate, exportData, importData } = useK1ImportExport({ wpId: toRef(props, 'wpId') })
const auditNote = ref('')
const conclusion = ref('')
const conclusionOption = ref('')
const showAgingDialog = ref(false)
const agingDraft = ref('')
const portfolioDeeplinkHint = ref('')
const groupHighlightId = ref('')

const ITEM_ID = calc.STORAGE_ITEM_ID
const CROSS_SHEET_PROVISION_KEY = 'K1-8-calc-provision-total'

onMounted(() => {
  const stored = props.allResponses.get(ITEM_ID)
  const raw = stored?.remark ?? stored?.value
  if (raw) calc.loadFromRaw(typeof raw === 'string' ? raw : JSON.stringify(raw))
  auditNote.value = calc.payload.value.auditNote ?? auditNote.value
  conclusion.value = calc.payload.value.conclusion ?? conclusion.value
  conclusionOption.value = calc.payload.value.conclusionOption ?? conclusionOption.value
  publishCrossSheetKeys()
  applyIncomingPortfolioFocus()
})

function applyIncomingPortfolioFocus(): void {
  const focus = k1Nav?.consumeFocus('K1-8')
  if (!focus) return
  let groupId = focus.groupId ?? ''
  if (!groupId && focus.portfolioLabel) {
    const resolved = resolveK18GroupFocus(props.allResponses, focus.portfolioLabel)
    if (resolved) groupId = resolved.groupId
  }
  if (groupId) {
    groupHighlightId.value = groupId
    k1Nav?.focusRow(groupId)
    nextTick(() => scrollToGroup(groupId))
  }
  if (focus.portfolioLabel || focus.sourceSheet) {
    portfolioDeeplinkHint.value = buildK1PortfolioDeeplinkHint(focus)
  }
}

function scrollToGroup(groupId: string): void {
  if (!groupId) return
  const el = document.querySelector(`[data-group-id="${groupId}"]`) as HTMLElement | null
  el?.scrollIntoView({ block: 'center', behavior: 'smooth' })
}

function navigateToK11(groupName: string): void {
  if (k1Nav) {
    k1Nav.navigateToRow({ sheet: 'K1-1', portfolioLabel: groupName, sourceSheet: 'K1-8' })
    return
  }
  emit('navigate-sheet', '审定表K1-1')
}

function persist() {
  calc.setAuditMeta(auditNote.value, conclusion.value, conclusionOption.value)
  const data = calc.serialize()
  props.allResponses.set(ITEM_ID, { item_id: ITEM_ID, conclusion: null, remark: data })
  emit('save', ITEM_ID, { remark: data })
  publishCrossSheetKeys()
}

function publishCrossSheetKeys() {
  const total = calc.grandTotal.value.expected
  props.allResponses.set(CROSS_SHEET_PROVISION_KEY, { item_id: CROSS_SHEET_PROVISION_KEY, remark: String(total) })
  emit('save', CROSS_SHEET_PROVISION_KEY, { remark: String(total) })
}

function onConclusionOption(val: string) {
  if (K1_CONCLUSION_TEMPLATES[val] && !conclusion.value) conclusion.value = K1_CONCLUSION_TEMPLATES[val]
  persist()
}

function onAgingPresetChange(val: K1AgingPreset) {
  if (val === 'CUSTOM') {
    agingDraft.value = (calc.customAgingLabels.value.length
      ? calc.customAgingLabels.value
      : calc.agingSegments.value.map((s) => s.label)
    ).join('\n')
    showAgingDialog.value = true
    return
  }
  calc.setAgingPreset(val)
  persist()
}

function confirmAgingCustom() {
  const labels = agingDraft.value.split('\n').map((l) => l.trim()).filter(Boolean)
  if (calc.setAgingPreset('CUSTOM', labels)) {
    showAgingDialog.value = false
    persist()
  }
}

function cancelAgingDialog() {
  showAgingDialog.value = false
}

function onPullFromK1Detail() {
  if (props.isReadonly) return
  calc.pullBalancesFromK1Detail(props.allResponses)
  persist()
}

function sumGroup(group: K1CalcGroup): number {
  return group.rows
    .filter((r) => !r.archived)
    .reduce((s, r) => s + (r.expectedProvision || 0), 0)
}

function fmtAmt(v: number | null | undefined): string {
  if (v == null || !Number.isFinite(Number(v))) return '—'
  return Number(v).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function pct(v: number | null | undefined): string {
  if (v == null || !Number.isFinite(Number(v))) return '—'
  return (Number(v) * 100).toFixed(2) + '%'
}

function handleReview() {
  openReviewDialog('K1-8-bad-debt-calc')
}

function onExportTemplate() { exportTemplate('K1-8') }
function onExportData() { exportData('K1-8') }
async function onImportChange(uploadFile: UploadFile) {
  const raw = uploadFile.raw
  if (!raw) return
  const result = await importData('K1-8', raw)
  if (result) {
    const stored = props.allResponses.get(ITEM_ID)
    const data = stored?.remark ?? stored?.value
    if (data) calc.loadFromRaw(typeof data === 'string' ? data : JSON.stringify(data))
    publishCrossSheetKeys()
  }
}
</script>

<style scoped>
.k1-audit-sheet { padding: 12px 14px; font-size: var(--wp-font-size, 13px); }
.section-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 10px; }
.sheet-title { font-size: 15px; font-weight: 600; margin: 0; }
.head-actions { display: flex; gap: 8px; align-items: center; }
.audit-objective { margin-bottom: 8px; }
.audit-objective :deep(.el-alert__content) { padding: 2px 0; }
.ao-title { font-weight: 600; }
.ao-text { margin: 4px 0 0; line-height: 1.6; font-size: 12px; }
.recon-bar { margin-bottom: 10px; }
.section-card { margin-bottom: 10px; }
.section-card :deep(.el-card__header) { padding: 8px 14px; }
.section-card :deep(.el-card__body) { padding: 12px 14px; }
.card-title { font-weight: 600; }
.card-header-row { display: flex; align-items: center; justify-content: space-between; }
.audit-table { font-size: var(--wp-font-size, 13px); }
.amount-cell { font-variant-numeric: tabular-nums; }
.amt { width: 100%; }
.formula-cell { border-bottom: 1px dashed var(--el-border-color); cursor: help; font-variant-numeric: tabular-nums; }
.diff-warn { color: var(--el-color-danger); font-weight: 600; }
.table-total { padding: 6px 12px; text-align: right; font-size: 12px; font-weight: 600; color: var(--el-text-color-regular); }
.table-total.grand { border-top: 1px solid var(--el-border-color); margin-top: 4px; padding-top: 8px; }
.conclusion-card { margin-bottom: 10px; }
.conclusion-card :deep(.el-card__header) { padding: 8px 14px; }
.conclusion-card :deep(.el-card__body) { padding: 12px 14px; }
.concl-select { width: 100%; margin-bottom: 8px; }
.compile-hint { margin-top: 6px; font-size: 12px; color: var(--el-text-color-secondary); }
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ul { padding-left: 18px; margin-top: 8px; line-height: 1.7; }
.top-hint { margin-bottom: 10px; }
.aging-toolbar { display: flex; align-items: center; gap: 8px; margin-bottom: 10px; flex-wrap: wrap; }
.muted { color: var(--el-text-color-secondary); font-size: 12px; }
.hint-inline { margin-left: 8px; font-size: 12px; color: var(--el-color-danger); font-weight: normal; }
.aging-hint { font-size: 12px; color: var(--el-text-color-secondary); margin: 0 0 8px; }
.aging-group { margin-bottom: 12px; }
.group-header { display: flex; align-items: center; gap: 8px; margin-bottom: 6px; }
.group-name { font-weight: 600; }
.group-sub { text-align: right; font-size: 12px; color: var(--el-text-color-secondary); padding: 4px 8px; }
.deeplink-bar { margin-bottom: 10px; }
.group-deeplink-hl {
  border: 2px solid var(--el-color-primary);
  border-radius: 6px;
  padding: 6px;
  animation: k1-group-flash 1.2s ease-in-out 0s 2;
}
@keyframes k1-group-flash { 0%, 100% { background-color: #ecf5ff; } 50% { background-color: #d9ecff; } }
</style>
