<template>
  <div class="i1-tab-title-check">
    <div class="guidance-area">
      <div class="guidance-grid">
        <div class="guidance-step"><span class="step-num">①</span> 检查权证原件/复印件，填编号、权利人、登记日、权利起止、索引</div>
        <div class="guidance-step"><span class="step-num">②</span> 从 I1-2 带入账面原值/摊销/减值，净值自动勾稽</div>
        <div class="guidance-step"><span class="step-num">③</span> 核对权利人是否为被审计单位；记录抵押/受限</div>
        <div class="guidance-step"><span class="step-num">④</span> 关注到期/临期续展；形成说明与结论</div>
      </div>
    </div>

    <div class="methodology-context">
      <p>
        <strong>编制逻辑（对齐 Excel I1-8 / CAS6）：</strong>
        检查产权证原件，明确归属，是否存在担保、抵押等情况。
        账面净值 = 原值 − 累计摊销 − 减值准备（源表「累计折旧」按无形资产准则改为摊销）。
        土地使用权等需关注出让/划拨及剩余年限；质押受限应披露并关注持续经营。
      </p>
    </div>

    <el-alert
      type="info"
      :closable="false"
      show-icon
      class="objective-alert"
      title="审计目标：检查产权证原件，明确归属，是否存在担保、抵押等情况；核实权利人与被审计单位一致，账面净值勾稽正确。"
    />

    <div class="tab-toolbar">
      <div class="toolbar-left">
        <span class="chip-wrap"><GtIndexChip value="wp:I1-8" :context-project-id="projectId" /></span>
        <el-tag size="small" type="info">共 {{ state.rows.value.length }} 项</el-tag>
        <el-tag v-if="state.mortgagedCount.value" size="small" type="warning">
          抵押 {{ state.mortgagedCount.value }}
        </el-tag>
        <el-tag v-if="state.expiredCount.value" size="small" type="danger">
          已到期 {{ state.expiredCount.value }}
        </el-tag>
        <el-tag v-if="state.nearExpiryCount.value" size="small" type="warning">
          ≤1年 {{ state.nearExpiryCount.value }}
        </el-tag>
        <el-tag v-if="state.holderMismatchCount.value" size="small" type="danger">
          权利人不一致 {{ state.holderMismatchCount.value }}
        </el-tag>
        <el-tag v-if="!state.prepValidation.value.ok" size="small" type="danger">
          编制校验 {{ state.prepValidation.value.messages.length }}
        </el-tag>
      </div>
      <div class="toolbar-right">
        <GtIndexChip value="wp:I1-2" :context-project-id="projectId" />
        <el-tag size="small" class="nav-chip" @click="emit('navigate-sheet', 'I1-2')">← I1-2</el-tag>
      </div>
    </div>

    <el-alert
      v-if="!state.prepValidation.value.ok"
      type="warning"
      :closable="false"
      show-icon
      class="mb-8"
      :title="state.prepValidation.value.messages[0]"
      :description="state.prepValidation.value.messages.slice(1, 4).join('；') || undefined"
    />

    <el-card shadow="never" class="main-card">
      <template #header>
        <div class="section-title">
          <span>无形资产权属检查表 I1-8</span>
          <div class="title-actions">
            <el-input
              v-model="state.entityName.value"
              size="small"
              clearable
              placeholder="被审计单位名称（权利人核对）"
              style="width: 200px"
              :disabled="isReadonly"
              @change="handleEntityCheck"
            />
            <el-select
              v-model="state.filterType.value"
              size="small"
              placeholder="按类型"
              clearable
              style="width: 120px"
            >
              <el-option label="全部" value="" />
              <el-option v-for="t in I1_TITLE_TYPE_OPTIONS" :key="t" :label="t" :value="t" />
            </el-select>
            <el-button size="small" :disabled="isReadonly" @click="handleSeedFromDetail">从 I1-2 带入</el-button>
            <el-button size="small" type="primary" :disabled="isReadonly" @click="handleAddRow">+ 新增</el-button>
            <el-button
              v-if="useVirtualScroll"
              size="small"
              @click="toggleBrowseMode"
            >
              {{ browseMode ? '切换表格编辑' : '切换虚拟速览' }}
            </el-button>
            <el-button size="small" circle @click="openReview('I1-8')">💬</el-button>
          </div>
        </div>
      </template>

      <el-alert
        v-if="useVirtualScroll"
        type="info"
        :closable="false"
        show-icon
        class="mb-8"
        :title="`行数较多（${state.filteredRows.value.length}）· ${browseMode ? '虚拟滚动速览' : '表格编辑'} · 双击行可切换编辑`"
      />

      <el-table-v2
        v-if="useVirtualScroll && browseMode"
        :columns="virtualColumns"
        :data="state.filteredRows.value"
        :width="tableWidth"
        :height="tableHeight"
        :row-height="36"
        :header-height="40"
        :row-event-handlers="rowEventHandlers"
        fixed
        class="title-check-v2"
      />

      <el-table
        v-else
        :data="state.filteredRows.value"
        border
        stripe
        size="small"
        max-height="520"
        class="title-check-table"
        row-key="rowId"
        show-summary
        :summary-method="getSummary"
        :row-class-name="rowClassName"
      >
        <el-table-column type="index" label="#" width="44" align="center" fixed />

        <el-table-column prop="name" label="资产名称" min-width="120" fixed>
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              :model-value="row.name"
              size="small"
              @change="(v: string) => state.updateField(row.rowId, 'name', v)"
            />
            <span v-else>{{ row.name || '-' }}</span>
          </template>
        </el-table-column>

        <el-table-column prop="type" label="类型" width="110" align="center">
          <template #default="{ row }">
            <el-select
              v-if="!isReadonly"
              :model-value="row.type"
              size="small"
              style="width: 98px"
              @change="(v: string) => state.updateField(row.rowId, 'type', v)"
            >
              <el-option v-for="t in I1_TITLE_TYPE_OPTIONS" :key="t" :label="t" :value="t" />
            </el-select>
            <span v-else>{{ row.type || '-' }}</span>
          </template>
        </el-table-column>

        <!-- 权证记载 -->
        <el-table-column label="权证记载" align="center">
          <el-table-column prop="certNo" label="权证编号" min-width="110">
            <template #default="{ row }">
              <el-input
                v-if="!isReadonly"
                :model-value="row.certNo"
                size="small"
                @change="(v: string) => state.updateField(row.rowId, 'certNo', v)"
              />
              <span v-else>{{ row.certNo || '-' }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="rightHolder" label="权利人名称" min-width="110">
            <template #default="{ row }">
              <el-input
                v-if="!isReadonly"
                :model-value="row.rightHolder"
                size="small"
                @change="(v: string) => state.updateField(row.rowId, 'rightHolder', v)"
              />
              <span v-else :class="{ 'mismatch': row.holderConsistent === 'N' }">{{ row.rightHolder || '-' }}</span>
            </template>
          </el-table-column>
          <el-table-column label="与单位一致" width="90" align="center">
            <template #default="{ row }">
              <el-select
                v-if="!isReadonly"
                :model-value="row.holderConsistent"
                size="small"
                style="width: 72px"
                @change="(v: string) => state.updateField(row.rowId, 'holderConsistent', v)"
              >
                <el-option label="—" value="" />
                <el-option label="是" value="Y" />
                <el-option label="否" value="N" />
              </el-select>
              <el-tag v-else-if="row.holderConsistent === 'Y'" type="success" size="small">是</el-tag>
              <el-tag v-else-if="row.holderConsistent === 'N'" type="danger" size="small">否</el-tag>
              <span v-else>-</span>
            </template>
          </el-table-column>
          <el-table-column prop="registrationDate" label="登记日期" width="120">
            <template #default="{ row }">
              <el-date-picker
                v-if="!isReadonly"
                :model-value="row.registrationDate"
                type="date"
                size="small"
                value-format="YYYY-MM-DD"
                style="width: 110px"
                @change="(v: string) => state.updateField(row.rowId, 'registrationDate', v || '')"
              />
              <span v-else>{{ row.registrationDate || '-' }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="rightStartDate" label="权利起日" width="120">
            <template #default="{ row }">
              <el-date-picker
                v-if="!isReadonly"
                :model-value="row.rightStartDate"
                type="date"
                size="small"
                value-format="YYYY-MM-DD"
                style="width: 110px"
                @change="(v: string) => state.updateField(row.rowId, 'rightStartDate', v || '')"
              />
              <span v-else>{{ row.rightStartDate || '-' }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="rightEndDate" label="权利止日" width="130">
            <template #default="{ row }">
              <el-date-picker
                v-if="!isReadonly"
                :model-value="row.rightEndDate"
                type="date"
                size="small"
                value-format="YYYY-MM-DD"
                style="width: 110px"
                @change="(v: string) => state.updateField(row.rowId, 'rightEndDate', v || '')"
              />
              <span v-else :class="expiryClass(row.rightEndDate)">{{ row.rightEndDate || '-' }}</span>
            </template>
          </el-table-column>
          <el-table-column label="到期" width="72" align="center">
            <template #default="{ row }">
              <el-tag v-if="state.classifyExpiry(row.rightEndDate) === 'expired'" type="danger" size="small">到期</el-tag>
              <el-tag v-else-if="state.classifyExpiry(row.rightEndDate) === 'near'" type="warning" size="small">≤1年</el-tag>
              <span v-else>-</span>
            </template>
          </el-table-column>
          <el-table-column prop="copyIndex" label="复印件索引" min-width="100">
            <template #default="{ row }">
              <el-input
                v-if="!isReadonly"
                :model-value="row.copyIndex"
                size="small"
                placeholder="如 I1-8-1"
                @change="(v: string) => state.updateField(row.rowId, 'copyIndex', v)"
              />
              <span v-else>{{ row.copyIndex || '-' }}</span>
            </template>
          </el-table-column>
        </el-table-column>

        <!-- 财务账面 -->
        <el-table-column label="财务账面记载" align="center">
          <el-table-column prop="cost" label="原值" width="110" align="right">
            <template #default="{ row }">
              <el-input-number
                v-if="!isReadonly"
                :model-value="row.cost"
                :controls="false"
                size="small"
                :precision="2"
                style="width: 96px"
                @change="(v: number | undefined) => state.updateField(row.rowId, 'cost', v ?? 0)"
              />
              <span v-else class="amt-cell">{{ fmtAmt(row.cost) }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="accAmort" label="累计摊销" width="110" align="right">
            <template #header>
              <span class="formula-header" title="源表写「累计折旧」，无形资产按 CAS6 为累计摊销">累计摊销</span>
            </template>
            <template #default="{ row }">
              <el-input-number
                v-if="!isReadonly"
                :model-value="row.accAmort"
                :controls="false"
                size="small"
                :precision="2"
                style="width: 96px"
                @change="(v: number | undefined) => state.updateField(row.rowId, 'accAmort', v ?? 0)"
              />
              <span v-else class="amt-cell">{{ fmtAmt(row.accAmort) }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="impairment" label="减值准备" width="110" align="right">
            <template #default="{ row }">
              <el-input-number
                v-if="!isReadonly"
                :model-value="row.impairment"
                :controls="false"
                size="small"
                :precision="2"
                style="width: 96px"
                @change="(v: number | undefined) => state.updateField(row.rowId, 'impairment', v ?? 0)"
              />
              <span v-else class="amt-cell">{{ fmtAmt(row.impairment) }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="netBookValue" label="净值" width="110" align="right">
            <template #header>
              <span class="formula-header" title="= 原值 − 累计摊销 − 减值准备（Excel J=G−H−I）">净值</span>
            </template>
            <template #default="{ row }">
              <span class="formula-cell amt-cell">{{ fmtAmt(row.netBookValue) }}</span>
            </template>
          </el-table-column>
        </el-table-column>

        <!-- 抵押 -->
        <el-table-column label="抵押情况" align="center">
          <el-table-column label="是否抵押受限" width="110" align="center">
            <template #default="{ row }">
              <el-select
                v-if="!isReadonly"
                :model-value="row.mortgageRestricted"
                size="small"
                style="width: 88px"
                @change="(v: string) => state.updateField(row.rowId, 'mortgageRestricted', v)"
              >
                <el-option label="—" value="" />
                <el-option label="是" value="Y" />
                <el-option label="否" value="N" />
              </el-select>
              <el-tag v-else-if="row.mortgageRestricted === 'Y'" type="danger" size="small">是</el-tag>
              <el-tag v-else-if="row.mortgageRestricted === 'N'" type="success" size="small">否</el-tag>
              <span v-else>-</span>
            </template>
          </el-table-column>
          <el-table-column prop="mortgageValue" label="抵押价值" width="110" align="right">
            <template #default="{ row }">
              <el-input-number
                v-if="!isReadonly"
                :model-value="row.mortgageValue"
                :controls="false"
                size="small"
                :precision="2"
                style="width: 96px"
                :disabled="row.mortgageRestricted !== 'Y'"
                @change="(v: number | undefined) => state.updateField(row.rowId, 'mortgageValue', v ?? 0)"
              />
              <span v-else class="amt-cell">{{ fmtAmt(row.mortgageValue) }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="mortgageNature" label="抵押性质" min-width="100">
            <template #default="{ row }">
              <el-input
                v-if="!isReadonly"
                :model-value="row.mortgageNature"
                size="small"
                placeholder="质押/抵押/冻结…"
                :disabled="row.mortgageRestricted !== 'Y'"
                @change="(v: string) => state.updateField(row.rowId, 'mortgageNature', v)"
              />
              <span v-else>{{ row.mortgageNature || '-' }}</span>
            </template>
          </el-table-column>
        </el-table-column>

        <el-table-column prop="conclusion" label="结论" width="100" align="center">
          <template #default="{ row }">
            <el-select
              v-if="!isReadonly"
              :model-value="row.conclusion"
              size="small"
              style="width: 88px"
              @change="(v: string) => state.updateField(row.rowId, 'conclusion', v)"
            >
              <el-option label="无异常" value="无异常" />
              <el-option label="有差异" value="有差异" />
              <el-option label="需补办" value="需补办" />
              <el-option label="已注销" value="已注销" />
            </el-select>
            <span v-else>{{ row.conclusion || '-' }}</span>
          </template>
        </el-table-column>

        <el-table-column prop="remark" label="备注" min-width="120">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              :model-value="row.remark"
              size="small"
              @change="(v: string) => state.updateField(row.rowId, 'remark', v)"
            />
            <span v-else>{{ row.remark || '-' }}</span>
          </template>
        </el-table-column>

        <el-table-column v-if="!isReadonly" label="操作" width="50" fixed="right">
          <template #default="{ row }">
            <el-button size="small" type="danger" link @click="state.removeRow(row.rowId)">删</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="summary-bar">
        <span>检查 <b>{{ state.rows.value.length }}</b> 项</span>
        <span>原值合计 <b class="amt-cell">{{ fmtAmt(state.totalCost.value) }}</b></span>
        <span>净值合计 <b class="amt-cell">{{ fmtAmt(state.totalNet.value) }}</b></span>
        <span>抵押价值 <b class="amt-cell">{{ fmtAmt(state.totalMortgage.value) }}</b></span>
        <span>权利人不一致 <b :class="{ 'error-amount': state.holderMismatchCount.value > 0 }">{{ state.holderMismatchCount.value }}</b></span>
      </div>

      <div v-if="state.groupStats.value.length" class="group-stats">
        <span v-for="g in state.groupStats.value" :key="g.type" class="group-chip">
          <el-tag size="small" type="info">{{ g.type }}</el-tag>
          <span class="group-count">{{ g.count }}项 / 净值 {{ fmtAmt(g.netTotal) }}</span>
        </span>
      </div>
    </el-card>

    <el-card shadow="never" class="note-card">
      <template #header><div class="section-title"><span>三、审计说明</span></div></template>
      <el-input
        :model-value="state.auditNote.value"
        type="textarea"
        :autosize="{ minRows: 4 }"
        :disabled="isReadonly"
        placeholder="权证核验范围与方式、权利人核对、抵押/受限、到期续展、与 I1-2 账面勾稽等。"
        @change="(v: string) => state.saveNote(v)"
      />
    </el-card>

    <el-card shadow="never" class="note-card">
      <template #header>
        <div class="section-title">
          <span>四、审计结论</span>
          <el-button size="small" plain :disabled="isReadonly" @click="fillDraft">填入结论模板</el-button>
        </div>
      </template>
      <el-input
        :model-value="state.auditConclusion.value"
        type="textarea"
        :autosize="{ minRows: 3 }"
        :disabled="isReadonly"
        placeholder="经核查，无形资产权属…"
        @change="(v: string) => state.saveConclusion(v)"
      />
    </el-card>

    <p class="ipo-ref">
      参考：《首发业务若干问题解答》（2020年6月修订版）——关注权属清晰、不存在重大权属瑕疵及抵押担保对持续经营的影响。
    </p>

    <details class="compile-hint">
      <summary>编制提示（对齐 Excel I1-8）</summary>
      <ol>
        <li>净值公式 J = G − H − I（原值 − 累计摊销 − 减值准备）；源表「累计折旧」按无形资产改为摊销。</li>
        <li>权证记载：编号、权利人、登记日、权利起止、复印件索引；优先查验原件。</li>
        <li>「从 I1-2 带入」自动填原值/摊销/减值；按同名更新已有行。</li>
        <li>填写被审计单位名称后，可自动勾稽权利人是否一致。</li>
        <li>抵押受限=是时须填抵押价值与性质；到期/临期须关注续展。</li>
      </ol>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * I1TabTitleCheck.vue — I1-8 无形资产权属检查表
 * 对齐 Excel：权证记载 + 账面(净值公式) + 抵押情况
 * >30 行启用 el-table-v2 虚拟速览（双击切编辑）
 */
import { computed, inject } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  useI1TitleCheck,
  I1_TITLE_TYPE_OPTIONS,
  type I1TitleCheckRow,
} from '../../composables/useI1TitleCheck'
import { useWorkpaperBrowseMode } from '../../composables/useWorkpaperBrowseMode'
import { virtualTextCol, virtualNumCol } from '../../composables/virtualColumnHelpers'
import GtIndexChip from '../../GtIndexChip.vue'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const emit = defineEmits<{
  (e: 'navigate-sheet', sheetName: string): void
  (e: 'save', itemId?: string, value?: any): void
}>()

const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})
const allResponsesRef = computed(() => props.allResponses)

const state = useI1TitleCheck({
  allResponses: allResponsesRef as any,
  onSave: (itemId, value) => emit('save', itemId, value),
})

const virtualColumns = computed(() => [
  virtualTextCol('name', '资产名称', 140),
  virtualTextCol('type', '类型', 100),
  virtualTextCol('certNo', '权证编号', 120),
  virtualTextCol('rightHolder', '权利人', 120),
  virtualNumCol('cost', '原值', 100, fmtAmt),
  virtualNumCol('accAmort', '累计摊销', 100, fmtAmt),
  virtualNumCol('impairment', '减值', 90, fmtAmt),
  virtualNumCol('netBookValue', '净值', 100, fmtAmt),
  virtualTextCol('mortgageRestricted', '抵押', 70),
  virtualTextCol('rightEndDate', '权利止日', 110),
  virtualTextCol('holderConsistent', '权利人一致', 90),
  virtualTextCol('conclusion', '结论', 90),
])

const {
  browseMode,
  useVirtualScroll,
  rowEventHandlers,
  tableWidth,
  tableHeight,
  toggleBrowseMode,
} = useWorkpaperBrowseMode({
  rows: state.filteredRows,
  virtualColumns,
  threshold: 30,
  tableWidth: 1400,
  tableHeight: 520,
})
async function handleAddRow() {
  try {
    const { value } = await ElMessageBox.prompt('请输入资产名称', '新增权属检查项', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      inputPattern: /\S+/,
      inputErrorMessage: '名称不能为空',
    })
    if (value) state.addRow(value.trim())
  } catch { /* cancelled */ }
}

function handleSeedFromDetail() {
  const r = state.seedFromDetail()
  ElMessage({ type: r.ok ? 'success' : 'warning', message: r.message })
}

function handleEntityCheck() {
  const n = state.applyEntityNameCheck(state.entityName.value)
  if (state.entityName.value) {
    ElMessage.success(n > 0 ? `已更新 ${n} 行权利人勾稽` : '权利人勾稽已完成（无变更）')
  }
}

function fillDraft() {
  state.fillConclusionDraft()
  ElMessage.success('已填入结论模板')
}

function openReview(id: string) {
  openReviewDialog(id)
}

function expiryClass(date: string): string {
  const f = state.classifyExpiry(date)
  if (f === 'expired') return 'expired-date'
  if (f === 'near') return 'near-date'
  return ''
}

function rowClassName({ row }: { row: I1TitleCheckRow }): string {
  if (row.holderConsistent === 'N' || state.classifyExpiry(row.rightEndDate) === 'expired') {
    return 'row-attention'
  }
  return ''
}

function getSummary({ columns }: { columns: any[] }) {
  const sums: string[] = []
  columns.forEach((col: any, idx: number) => {
    if (idx === 0) {
      sums[idx] = '合计'
      return
    }
    const prop = col.property
    if (prop === 'cost') sums[idx] = fmtAmt(state.totalCost.value)
    else if (prop === 'accAmort') sums[idx] = fmtAmt(state.totalAccAmort.value)
    else if (prop === 'impairment') sums[idx] = fmtAmt(state.totalImpairment.value)
    else if (prop === 'netBookValue') sums[idx] = fmtAmt(state.totalNet.value)
    else if (prop === 'mortgageValue') sums[idx] = fmtAmt(state.totalMortgage.value)
    else sums[idx] = ''
  })
  return sums
}

function fmtAmt(val: number | null | undefined): string {
  if (val == null) return '-'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.i1-tab-title-check { padding: 16px; font-size: var(--wp-font-size, 13px); }

.guidance-area {
  background: linear-gradient(135deg, #e8f4fd 0%, #d6ecfa 100%);
  border-radius: 8px;
  padding: 14px 18px;
  margin-bottom: 12px;
}
.guidance-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px 24px;
}
.guidance-step {
  font-size: 12px;
  color: #1a5276;
  display: flex;
  align-items: flex-start;
  gap: 6px;
}
.step-num {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  border-radius: 50%;
  background: #2980b9;
  color: #fff;
  font-size: 11px;
  font-weight: 600;
  flex-shrink: 0;
}

.methodology-context {
  border-left: 3px solid var(--el-color-warning);
  background: #fffbe6;
  padding: 10px 14px;
  margin-bottom: 12px;
  border-radius: 4px;
  font-size: 12px;
  color: #7d6608;
  line-height: 1.6;
}

.objective-alert { margin-bottom: 12px; }
.mb-8 { margin-bottom: 8px; }

.tab-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
  flex-wrap: wrap;
  gap: 8px;
}
.toolbar-left, .toolbar-right { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.chip-wrap { display: inline-flex; align-items: center; }
.nav-chip { cursor: pointer; }

.main-card { margin-bottom: 12px; }
.section-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 8px;
}
.title-actions { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }

.title-check-table { font-size: var(--wp-font-size, 13px); }
.title-check-v2 { margin-top: 4px; }
.mb-8 { margin-bottom: 8px; }
.amt-cell { font-variant-numeric: tabular-nums; }
.formula-header {
  border-bottom: 1px dashed var(--el-border-color);
  cursor: help;
}
.formula-cell {
  border-bottom: 1px dashed var(--el-border-color);
  cursor: help;
  font-variant-numeric: tabular-nums;
}
.mismatch, .expired-date, .error-amount {
  color: var(--el-color-danger);
  font-weight: 600;
}
.near-date { color: var(--el-color-warning); font-weight: 600; }

:deep(.row-attention) { background: #fff7e6 !important; }

.summary-bar {
  display: flex;
  gap: 20px;
  padding: 10px 12px;
  margin-top: 12px;
  background: var(--el-fill-color-light);
  border-radius: 4px;
  flex-wrap: wrap;
  font-size: 13px;
}

.group-stats {
  display: flex;
  gap: 12px;
  padding: 8px 12px;
  margin-top: 8px;
  flex-wrap: wrap;
}
.group-chip { display: inline-flex; align-items: center; gap: 4px; }
.group-count { font-size: 12px; color: var(--el-text-color-secondary); }

.note-card { margin-bottom: 12px; }
.ipo-ref {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin: 8px 0;
  line-height: 1.6;
}
.compile-hint { margin-top: 8px; font-size: 12px; color: var(--el-text-color-secondary); }
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ol { padding-left: 20px; margin-top: 8px; line-height: 1.8; }
</style>
