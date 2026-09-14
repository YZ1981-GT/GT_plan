<template>
  <div class="g1-fv-test" data-testid="g1-fv-test">
    <div class="section-head">
      <div class="title-block">
        <h3 class="sheet-title">G1-6 公允价值测试表</h3>
        <p class="sheet-sub">
          账面 vs 测试（审定）→ 按 Level1/2/3 取证 → 回写 G1-2；Level3 变动调节见 G1-7
        </p>
      </div>
      <div class="head-actions">
        <G1ImportExportDropdown
          v-if="wpId"
          :wp-id="wpId"
          sheet="G1-6"
          :disabled="isReadonly"
          @imported="onImported"
        />
        <el-button size="small" :disabled="isReadonly" @click="onSyncDetail">从 G1-2 带入</el-button>
        <el-button size="small" type="warning" plain :disabled="isReadonly" @click="onPushDetail">
          回写至 G1-2
        </el-button>
        <el-button
          size="small"
          type="danger"
          plain
          :disabled="isReadonly || balanceOk"
          @click="onPushAdj"
        >差异推送 G1-3</el-button>
        <el-button
          size="small"
          type="warning"
          plain
          :disabled="isReadonly || balanceOk || !projectId || pushingG13"
          :loading="pushingG13"
          data-testid="g1-fv-push-g13"
          @click="onPushG13"
        >差异推送 G13-3</el-button>
        <el-button size="small" type="success" plain :disabled="isReadonly" @click="onPushL3">
          L3 推送 G1-7
        </el-button>
        <el-button size="small" :disabled="isReadonly" @click="validateLevel3()">Level3校验</el-button>
        <el-button size="small" type="primary" :disabled="isReadonly" @click="addRow()">新增证券</el-button>
        <span class="chip-wrap"><GtIndexChip value="wp:G1-2" /></span>
        <span class="chip-wrap"><GtIndexChip value="wp:G1-7" /></span>
        <el-button size="small" @click="openReviewDialog('G1-6-conclusion')">💬复核</el-button>
      </div>
    </div>

    <el-alert
      type="info"
      :closable="false"
      show-icon
      class="objective-alert"
      title="审计目标：确认交易性金融资产期末以公允价值计量；核实层次划分与估值输入合理，测试值与账面差异可解释，并支撑 G1-2 期末公允及附注披露。"
    />

    <section class="gates-card">
      <header class="gates-head">
        <div>
          <h4>二、审计过程（编制闸门）</h4>
          <p>核对计量方法 → 判断层次 → 核实报价/输入 → Level3 假设与专家工作</p>
        </div>
        <el-tag :type="gatesReady ? 'success' : 'warning'" size="small" effect="plain">
          {{ gatesReady ? '已就绪' : '待完成' }}
        </el-tag>
      </header>
      <div class="gates-grid">
        <label class="gate-item">
          <el-checkbox
            :model-value="gates.levelPolicyReviewed"
            :disabled="isReadonly"
            @change="(v: boolean | string | number) => updateGates({ levelPolicyReviewed: !!v })"
          />
          <span>
            <strong>公允层级政策已复核</strong>
            <small>划分依据与会计政策一致；估值方法与上期比较</small>
          </span>
        </label>
        <label class="gate-item">
          <el-checkbox
            :model-value="gates.quoteSourceVerified"
            :disabled="isReadonly"
            @change="(v: boolean | string | number) => updateGates({ quoteSourceVerified: !!v })"
          />
          <span>
            <strong>报价/可观察输入已核实</strong>
            <small>Level1 来源机构；Level2 输入及调整可验证</small>
          </span>
        </label>
        <label class="gate-item">
          <el-checkbox
            :model-value="gates.level3AssumptionsNoted"
            :disabled="isReadonly"
            @change="(v: boolean | string | number) => updateGates({ level3AssumptionsNoted: !!v })"
          />
          <span>
            <strong>Level3 假设/专家工作已记录</strong>
            <small>无 L3 可勾选表示不适用；有 L3 须填技术与输入</small>
          </span>
        </label>
      </div>
    </section>

    <div class="status-bar" :class="balanceOk ? 'ok' : 'warn'">
      <span class="status-main">
        {{ balanceOk ? '测试合计与账面勾平' : `测试合计与账面差 ${fmt(stats.diffTotal)}` }}
      </span>
      <span class="status-meta">
        L1 {{ stats.level1 }} / L2 {{ stats.level2 }} / L3 {{ stats.level3 }}
        · 超阈值 {{ stats.overThreshold }}
        · 账面 {{ fmt(stats.bookTotal) }}
        · 测试 {{ fmt(stats.testedTotal) }}
      </span>
    </div>

    <el-alert
      v-if="level3Violations.length"
      type="warning"
      :closable="false"
      class="l3-alert"
      :title="`Level3 建议补全：${level3Violations.map((v) => v.securityName).join('、')}`"
    />

    <el-segmented v-model="activeTab" :options="tabOptions" size="small" class="seg" />

    <el-table :data="rows" border size="small" max-height="480" style="margin-top: 8px; font-size: 13px">
      <el-table-column label="#" prop="seq" width="44" fixed />
      <el-table-column label="投资项目" min-width="120" fixed>
        <template #default="{ row }">
          <el-input
            v-if="!isReadonly"
            :model-value="row.securityName"
            size="small"
            placeholder="证券/债券/基金"
            @update:model-value="(v: string) => updateCell(row.id, 'securityName', v)"
          />
          <span v-else>{{ row.securityName }}</span>
        </template>
      </el-table-column>
      <el-table-column label="代码" width="88">
        <template #default="{ row }">
          <el-input
            v-if="!isReadonly"
            :model-value="row.securityCode"
            size="small"
            @update:model-value="(v: string) => updateCell(row.id, 'securityCode', v)"
          />
          <span v-else>{{ row.securityCode }}</span>
        </template>
      </el-table-column>

      <template v-if="activeTab === 'basic'">
        <el-table-column label="期末账面数" align="center">
          <el-table-column label="数量" width="88" align="right">
            <template #default="{ row }">
              <el-input-number
                v-if="!isReadonly"
                :model-value="row.quantity"
                size="small"
                :controls="false"
                style="width: 100%"
                @update:model-value="(v: number | undefined) => updateCell(row.id, 'quantity', v ?? 0)"
              />
              <span v-else>{{ row.quantity }}</span>
            </template>
          </el-table-column>
          <el-table-column label="单位公允" width="88" align="right">
            <template #default="{ row }">
              <el-input-number
                v-if="!isReadonly"
                :model-value="row.bookUnitFv"
                size="small"
                :controls="false"
                style="width: 100%"
                @update:model-value="(v: number | undefined) => updateCell(row.id, 'bookUnitFv', v ?? 0)"
              />
              <span v-else>{{ row.bookUnitFv }}</span>
            </template>
          </el-table-column>
          <el-table-column label="公允价值" width="100" align="right">
            <template #default="{ row }">
              <WpAmountInput
                v-if="!isReadonly"
                :model-value="row.bookValue"
                size="small"
                style="width: 100%"
                @update:model-value="(v: number | undefined) => updateCell(row.id, 'bookValue', v ?? 0)"
              />
              <span v-else>{{ fmt(row.bookValue) }}</span>
            </template>
          </el-table-column>
        </el-table-column>

        <el-table-column label="期末测试/审定数" align="center">
          <el-table-column label="层次" width="92">
            <template #default="{ row }">
              <el-select
                v-if="!isReadonly"
                :model-value="row.fvLevel"
                size="small"
                @update:model-value="(v: 1|2|3) => updateCell(row.id, 'fvLevel', v)"
              >
                <el-option :value="1" label="Level1" />
                <el-option :value="2" label="Level2" />
                <el-option :value="3" label="Level3" />
              </el-select>
              <span v-else>L{{ row.fvLevel }}</span>
            </template>
          </el-table-column>
          <el-table-column label="测试公允价值" width="110" align="right">
            <template #default="{ row }">
              <span class="formula-cell" title="L1=数量×报价；L2/L3=估值结果">{{ fmt(row.testedValue) }}</span>
            </template>
          </el-table-column>
        </el-table-column>

        <el-table-column label="差异" width="96" align="right">
          <template #default="{ row }">
            <span
              class="formula-cell"
              :class="{ 'diff-warn': Math.abs(row.activeDiff) > 0.01 }"
              title="测试值 − 账面值"
            >{{ fmt(row.activeDiff) }}</span>
          </template>
        </el-table-column>
      </template>

      <template v-else>
        <el-table-column label="估值方法" width="110">
          <template #default="{ row }">
            <el-select
              v-if="!isReadonly"
              :model-value="row.valuationMethod"
              size="small"
              filterable
              allow-create
              @update:model-value="(v: string) => updateCell(row.id, 'valuationMethod', v)"
            >
              <el-option v-for="m in valuationMethodOptions" :key="m" :label="m" :value="m" />
            </el-select>
            <span v-else>{{ row.valuationMethod }}</span>
          </template>
        </el-table-column>
        <el-table-column label="与上期一致" width="96">
          <template #default="{ row }">
            <el-select
              v-if="!isReadonly"
              :model-value="row.methodConsistentWithPrior"
              size="small"
              @update:model-value="(v: string) => updateCell(row.id, 'methodConsistentWithPrior', v)"
            >
              <el-option label="是" value="yes" />
              <el-option label="否" value="no" />
            </el-select>
            <span v-else>{{ row.methodConsistentWithPrior === 'yes' ? '是' : row.methodConsistentWithPrior === 'no' ? '否' : '' }}</span>
          </template>
        </el-table-column>

        <el-table-column label="第一层次" align="center">
          <el-table-column label="报价日" width="120">
            <template #default="{ row }">
              <el-date-picker
                v-if="!isReadonly && row.fvLevel === 1"
                :model-value="row.quoteDate"
                type="date"
                size="small"
                value-format="YYYY-MM-DD"
                style="width: 100%"
                @update:model-value="(v: string) => updateCell(row.id, 'quoteDate', v || '')"
              />
              <span v-else :class="{ muted: row.fvLevel !== 1 }">{{ row.fvLevel === 1 ? row.quoteDate : '—' }}</span>
            </template>
          </el-table-column>
          <el-table-column label="来源机构" min-width="100">
            <template #default="{ row }">
              <el-input
                v-if="!isReadonly && row.fvLevel === 1"
                :model-value="row.quoteSource"
                size="small"
                placeholder="交易所/行情"
                @update:model-value="(v: string) => updateCell(row.id, 'quoteSource', v)"
              />
              <span v-else :class="{ muted: row.fvLevel !== 1 }">{{ row.fvLevel === 1 ? row.quoteSource : '—' }}</span>
            </template>
          </el-table-column>
          <el-table-column label="报价值" width="88" align="right">
            <template #default="{ row }">
              <WpAmountInput
                v-if="!isReadonly && row.fvLevel === 1"
                :model-value="row.quoteValue"
                size="small"
                style="width: 100%"
                @update:model-value="(v: number | undefined) => updateCell(row.id, 'quoteValue', v ?? 0)"
              />
              <span v-else :class="{ muted: row.fvLevel !== 1 }">{{ row.fvLevel === 1 ? row.quoteValue : '—' }}</span>
            </template>
          </el-table-column>
        </el-table-column>

        <el-table-column label="第二层次" align="center">
          <el-table-column label="输入来源及调整" min-width="130">
            <template #default="{ row }">
              <el-input
                v-if="!isReadonly && row.fvLevel === 2"
                :model-value="row.observableDesc"
                size="small"
                type="textarea"
                :autosize="{ minRows: 1, maxRows: 2 }"
                @update:model-value="(v: string) => updateCell(row.id, 'observableDesc', v)"
              />
              <span v-else :class="{ muted: row.fvLevel !== 2 }">{{ row.fvLevel === 2 ? row.observableDesc : '—' }}</span>
            </template>
          </el-table-column>
          <el-table-column label="估值结果" width="100" align="right">
            <template #default="{ row }">
              <el-input-number
                v-if="!isReadonly && row.fvLevel === 2"
                :model-value="row.level2Result"
                size="small"
                :controls="false"
                style="width: 100%"
                @update:model-value="(v: number | undefined) => updateCell(row.id, 'level2Result', v ?? 0)"
              />
              <span v-else :class="{ muted: row.fvLevel !== 2 }">{{ row.fvLevel === 2 ? fmt(row.level2Result) : '—' }}</span>
            </template>
          </el-table-column>
        </el-table-column>

        <el-table-column label="第三层次" align="center">
          <el-table-column label="估值技术" min-width="110">
            <template #default="{ row }">
              <el-input
                v-if="!isReadonly && row.fvLevel === 3"
                :model-value="row.valuationTechnique"
                size="small"
                :class="{ 'l3-required': !row.valuationTechnique && !row.assumption }"
                placeholder="如收益法(DCF)"
                @update:model-value="(v: string) => updateCell(row.id, 'valuationTechnique', v)"
              />
              <span v-else :class="{ muted: row.fvLevel !== 3 }">{{ row.fvLevel === 3 ? row.valuationTechnique : '—' }}</span>
            </template>
          </el-table-column>
          <el-table-column label="不可观察输入" min-width="120">
            <template #default="{ row }">
              <el-input
                v-if="!isReadonly && row.fvLevel === 3"
                :model-value="row.unobservableInput"
                size="small"
                type="textarea"
                :autosize="{ minRows: 1, maxRows: 2 }"
                :class="{ 'l3-required': !row.unobservableInput }"
                placeholder="WACC、增长率等"
                @update:model-value="(v: string) => updateCell(row.id, 'unobservableInput', v)"
              />
              <span v-else :class="{ muted: row.fvLevel !== 3 }">{{ row.fvLevel === 3 ? row.unobservableInput : '—' }}</span>
            </template>
          </el-table-column>
          <el-table-column label="数值" width="80">
            <template #default="{ row }">
              <el-input
                v-if="!isReadonly && row.fvLevel === 3"
                :model-value="row.unobservableInputValue"
                size="small"
                @update:model-value="(v: string) => updateCell(row.id, 'unobservableInputValue', v)"
              />
              <span v-else :class="{ muted: row.fvLevel !== 3 }">{{ row.fvLevel === 3 ? row.unobservableInputValue : '—' }}</span>
            </template>
          </el-table-column>
          <el-table-column label="估值结果" width="100" align="right">
            <template #default="{ row }">
              <el-input-number
                v-if="!isReadonly && row.fvLevel === 3"
                :model-value="row.level3Result"
                size="small"
                :controls="false"
                style="width: 100%"
                @update:model-value="(v: number | undefined) => updateCell(row.id, 'level3Result', v ?? 0)"
              />
              <span v-else :class="{ muted: row.fvLevel !== 3 }">{{ row.fvLevel === 3 ? fmt(row.level3Result) : '—' }}</span>
            </template>
          </el-table-column>
        </el-table-column>

        <el-table-column label="估值文件索引" width="110">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              :model-value="row.valuationDocIndex"
              size="small"
              @update:model-value="(v: string) => updateCell(row.id, 'valuationDocIndex', v)"
            />
            <span v-else>{{ row.valuationDocIndex }}</span>
          </template>
        </el-table-column>
      </template>

      <el-table-column v-if="!isReadonly" label="操作" width="56" fixed="right">
        <template #default="{ row }">
          <el-button link type="danger" size="small" @click="removeRow(row.id)">删</el-button>
        </template>
      </el-table-column>
    </el-table>

    <G1AuditTextCards
      :wp-id="wpId"
      :is-readonly="isReadonly"
      v-model:note="auditNote"
      v-model:conclusion="auditConclusion"
      note-ai-section="fair-value-note"
      conclusion-ai-section="fair-value-conclusion"
      :related-context="{
        Level1: stats.level1,
        Level2: stats.level2,
        Level3: stats.level3,
        超阈值项: stats.overThreshold,
        账面合计: stats.bookTotal,
        测试合计: stats.testedTotal,
        差异合计: stats.diffTotal,
        闸门就绪: gatesReady,
        Level3缺失: level3Violations.length,
      }"
      note-placeholder="三、审计说明：层级划分依据、报价/估值来源、专家工作利用、超阈值差异原因及是否提议调整；可交叉索引 G1-7。"
      note-hint="覆盖公允层级、输入可靠性、与 G1-2/附注勾稽及差异处理。"
      conclusion-placeholder="四、审计结论：公允价值计量是否准确、层次划分是否恰当。"
      conclusion-hint="A 未见异常；B 除重大调整外未见异常；C 因未调整或范围受限无法确认。"
    />

    <details class="prep-hint">
      <summary>📋 编制说明（公允价值层次）</summary>
      <ul>
        <li><b>第一层次</b>：活跃市场中相同资产的报价（未经调整）。</li>
        <li><b>第二层次</b>：除第一层次报价外，可观察输入值（直接或间接），如场外衍生、利率互换等。</li>
        <li><b>第三层次</b>：不可观察输入值；须记录估值技术、关键参数，变动调节见 G1-7。</li>
        <li>差异 = 测试公允价值 − 账面公允价值；|差异|&gt;0.01 高亮。优先从 G1-2 带入后回写层级与单位公允。</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
import WpAmountInput from '../../shared/WpAmountInput.vue'
import { ref, toRef, inject, watch, computed } from 'vue'
import { ElMessage } from 'element-plus'
import { useG1FairValueTest } from '../../composables/useG1FairValueTest'
import { pushSourceFvDiffToG13, G13_FV_DIFF_THRESHOLD } from '../../composables/g13FvCrossHelpers'
import type { ChecklistResponse } from '../../composables/useF1FormData'
import GtIndexChip from '../../GtIndexChip.vue'
import G1AuditTextCards from '../G1AuditTextCards.vue'
import G1ImportExportDropdown from '../G1ImportExportDropdown.vue'

const props = defineProps<{
  allResponses: Map<string, ChecklistResponse>
  isReadonly: boolean
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
  wpId?: string
  projectId?: string
}>()

const wpId = computed(() => props.wpId ?? '')
const projectId = computed(() => props.projectId ?? '')
const pushingG13 = ref(false)
const emit = defineEmits<{ imported: [] }>()
const openReviewDialog = inject<(sectionId: string) => void>('openReviewDialog', () => {})

const {
  rows,
  gates,
  gatesReady,
  auditConclusion,
  activeTab,
  stats,
  balanceOk,
  level3Violations,
  updateGates,
  updateCell,
  addRow,
  removeRow,
  syncFromDetail,
  pushToDetail,
  pushDiffToAdjustment,
  pushLevel3ToG1_7,
  validateLevel3,
  valuationMethodOptions,
  loadAll,
} = useG1FairValueTest({
  allResponses: toRef(props, 'allResponses'),
  debouncedSave: props.debouncedSave,
  isReadonly: toRef(props, 'isReadonly'),
})

const tabOptions = [
  { label: '基础+审定', value: 'basic' },
  { label: '估值详情', value: 'valuation' },
]

const AUDIT_NOTE_KEY = 'G1-6-audit-note'
const auditNote = ref(props.allResponses.get(AUDIT_NOTE_KEY)?.remark ?? '')
watch(auditNote, (v) => {
  if (!props.isReadonly) props.debouncedSave(AUDIT_NOTE_KEY, { conclusion: null, remark: v })
})

function fmt(v: unknown): string {
  return typeof v === 'number' ? v.toLocaleString(undefined, { maximumFractionDigits: 2 }) : String(v ?? '')
}

function onSyncDetail() {
  const n = syncFromDetail()
  if (!n) {
    ElMessage.warning('G1-2 无可用明细')
    return
  }
  ElMessage.success(`已从 G1-2 带入 ${n} 项`)
}

function onPushDetail() {
  const n = pushToDetail()
  if (!n) {
    ElMessage.warning('未匹配到 G1-2 同名证券')
    return
  }
  ElMessage.success(`已回写 ${n} 行公允层级/单位公允至 G1-2`)
}

function onPushAdj() {
  const n = pushDiffToAdjustment()
  if (!n) {
    ElMessage.warning('无超阈值差异可推送')
    return
  }
  ElMessage.success(`已推送 ${n} 条调整草稿至 G1-3`)
}

async function onPushG13() {
  if (!projectId.value) {
    ElMessage.warning('缺少项目 ID，无法推送 G13-3')
    return
  }
  const targets = rows.value.filter((r) => Math.abs(r.activeDiff) > G13_FV_DIFF_THRESHOLD)
  if (!targets.length) {
    ElMessage.warning('无超阈值差异可推送')
    return
  }
  pushingG13.value = true
  try {
    const result = await pushSourceFvDiffToG13({
      projectId: projectId.value,
      source: 'G1-6',
      items: targets.map((r) => ({
        description: `G1-6 公允测试差异：${r.securityName || '未命名'}`,
        amount: r.activeDiff,
        belongAccount: 'G1',
        indexRef: 'G1-6',
        nameKey: r.securityName || r.rowId,
        remark: `Level ${r.fvLevel} 测试 ${r.testedValue} − 账面 ${r.bookValue}`,
      })),
    })
    if (result.ok) ElMessage.success(result.message)
    else ElMessage.warning(result.message)
  } finally {
    pushingG13.value = false
  }
}

function onPushL3() {
  const n = pushLevel3ToG1_7()
  if (!n) {
    ElMessage.warning('无 Level3 行可推送')
    return
  }
  ElMessage.success(`已推送/合并 ${n} 项至 G1-7`)
}

function onImported() {
  emit('imported')
  loadAll()
}
</script>

<style scoped>
.g1-fv-test {
  padding: 4px 4px 20px;
  font-size: var(--wp-font-size, 13px);
  color: #303133;
}
.section-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
  margin-bottom: 14px;
  flex-wrap: wrap;
}
.title-block { min-width: 200px; }
.sheet-title { margin: 0; font-size: 16px; font-weight: 600; color: #1f2a37; }
.sheet-sub { margin: 4px 0 0; font-size: 12px; color: #86909c; line-height: 1.4; }
.head-actions { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
.chip-wrap { display: inline-flex; align-items: center; }
.objective-alert { margin-bottom: 12px; }

.gates-card {
  margin-bottom: 12px;
  border: 1px solid #e8ecf2;
  border-left: 3px solid #3d6b8e;
  background: #f7fafc;
  border-radius: 6px;
  padding: 12px 14px;
}
.gates-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
  margin-bottom: 10px;
}
.gates-head h4 { margin: 0; font-size: 13px; font-weight: 600; color: #1f2a37; }
.gates-head p { margin: 2px 0 0; font-size: 12px; color: #86909c; }
.gates-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  gap: 8px 16px;
}
.gate-item {
  display: flex;
  gap: 8px;
  align-items: flex-start;
  cursor: pointer;
  font-size: 12px;
  color: #4e5969;
  line-height: 1.45;
}
.gate-item strong { display: block; color: #1f2a37; font-weight: 600; }
.gate-item small { display: block; color: #86909c; margin-top: 2px; }

.status-bar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px 16px;
  margin-bottom: 12px;
  padding: 8px 12px;
  border-radius: 6px;
  font-size: 12px;
  border: 1px solid #e4e7ed;
}
.status-bar.ok { background: #f0f9f4; border-color: #c6e8d4; color: #2d6a4f; }
.status-bar.warn { background: #fff8f0; border-color: #f0d9b8; color: #9a5b1a; }
.status-main { font-weight: 600; }
.status-meta { color: #606266; flex: 1; }
.l3-alert { margin-bottom: 8px; }
.seg { margin-bottom: 4px; }

.formula-cell { border-bottom: 1px dashed #909399; cursor: help; font-size: 12px; color: #606266; }
.diff-warn { color: #e6a23c; font-weight: 600; }
.muted { color: #c0c4cc; }
.l3-required :deep(.el-input__wrapper) { box-shadow: 0 0 0 1px #f56c6c inset; }

.prep-hint { margin-top: 12px; font-size: 12px; color: #909399; }
.prep-hint summary { cursor: pointer; }
.prep-hint ul { margin: 8px 0 0; padding-left: 18px; line-height: 1.6; }
</style>
