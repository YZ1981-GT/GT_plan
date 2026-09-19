<script setup lang="ts">
/**
 * E1TabBankAccountAnalysis.vue — E1-29 银行账户分析
 * （一）清单+开户地 （二）多年指标 （三）（四）说明结论 + 红旗提示
 */
import { computed, inject, toRef, type Ref } from 'vue'
import { MagicStick } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  useE1BankAccountAnalysis,
  type BankAnalysisRow,
  type YesNo,
} from '../composables/useE1BankAccountAnalysis'
import { useE1AiGenerate } from '../composables/useE1AiGenerate'
import { useE1ImportExport } from '../composables/useE1ImportExport'
import type { UseE1BaseOptions } from '../composables/useE1Adjudication'
import E1IpoSheetChrome from './E1IpoSheetChrome.vue'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  saveImmediate: (items: any[]) => Promise<void>
  debouncedSave: (items: any[]) => Promise<void>
  isReadonly: boolean
  sheetName?: string
  bsDate?: string
}>()

const reloadWorkpaperData = inject<(() => Promise<void>) | null>('reloadWorkpaperData', null)

const options: UseE1BaseOptions = {
  wpId: toRef(props, 'wpId') as unknown as Ref<string>,
  projectId: toRef(props, 'projectId') as unknown as Ref<string>,
  allResponses: toRef(props, 'allResponses') as unknown as Ref<Map<string, any>>,
  saveImmediate: props.saveImmediate,
  debouncedSave: props.debouncedSave,
  isReadonly: toRef(props, 'isReadonly') as unknown as Ref<boolean>,
  bsDate: toRef(props, 'bsDate') as unknown as Ref<string>,
}

const {
  pack,
  auditNote,
  auditConclusion,
  isLoading,
  isApplicable,
  inconsistencyCount,
  remoteCount,
  setApplicable,
  addRow,
  removeRow,
  updateCell,
  updateYearCell,
  updateJudgment,
  updateTip,
  recalcCurrentYearFromRows,
  syncFromE10,
  previewSyncFromE10,
  saveNote,
  saveConclusion,
  hydrate,
} = useE1BankAccountAnalysis(options)

const { generateText, isGenerating } = useE1AiGenerate(toRef(props, 'wpId') as Ref<string>)
const sheetCode = computed(() => 'E1-29')
const { exportTemplate, exportData, importData, isImporting } = useE1ImportExport({
  wpId: toRef(props, 'wpId') as unknown as Ref<string>,
  sheet: sheetCode as unknown as Ref<string>,
})

const ynOptions = [
  { label: '是', value: '是' },
  { label: '否', value: '否' },
]
const consistentOptions = [
  { label: '一致', value: '一致' },
  { label: '不一致', value: '不一致' },
]

const conclusionTemplates = [
  {
    value: 'A',
    label: 'A—未见异常',
    text: '已开立银行结算账户清单与账面核对一致；账户数量与开销户变动未见异常，异地开户及零余额账户均已了解并评估，未见重大完整性或舞弊风险迹象。',
  },
  {
    value: 'B',
    label: 'B—异常已说明',
    text: '除已识别并记录的账户异常事项外，其余银行账户清单核对及变动分析未见重大异常；相关事项原因合理或已提请进一步核查。',
  },
  {
    value: 'C',
    label: 'C—需扩大核查',
    text: '因存在开户完整性疑虑或异常红旗（如频繁开销户、异地无业务开户等），已扩大询问/取证范围，结果见审计说明。',
  },
]

function aiContext(): Record<string, unknown> {
  return {
    底稿: 'E1-29 银行账户分析',
    账户笔数: pack.value.rows.filter(r => r.bank || r.accountNo).length,
    不一致笔数: inconsistencyCount.value,
    无业务开户地笔数: remoteCount.value,
    多年指标: pack.value.years,
    判断: pack.value.judgment,
    已勾选红旗: pack.value.tips.filter(t => t.checked).map(t => t.label),
  }
}

function sanitize(raw: string, kind: 'note' | 'conclusion'): string {
  let t = String(raw || '').trim()
  if (kind === 'note') {
    t = t.replace(/^\*{0,2}审计说明\*{0,2}\s*/i, '')
    t = t.replace(/\n+\s*\*{0,2}审计结论\*{0,2}.*$/s, '')
  } else {
    t = t.replace(/^\*{0,2}审计结论\*{0,2}\s*/i, '')
    t = t.replace(/^[ABC]、\s*/i, '')
  }
  return t.trim()
}

async function generateAuditNote(): Promise<void> {
  if (props.isReadonly) return
  const text = await generateText({
    section: 'e1-29-audit-note',
    prompt: [
      '你是注册会计师助理。请撰写 E1-29「审计说明」，只描述清单核对、账户变动分析与异常发现，不要写审计结论。',
      '应概括：清单与账面核对、开户地/异地开户、三年账户数量与开销户、已勾选异常红旗。',
      '严禁 markdown；约 150～280 字。',
    ].join(''),
    context: aiContext(),
    existingContent: auditNote.value,
    confirmTitle: 'AI 生成 · 审计说明',
  })
  if (text) saveNote(sanitize(text, 'note'))
}

async function generateAuditConclusion(): Promise<void> {
  if (props.isReadonly) return
  const text = await generateText({
    section: 'e1-29-audit-conclusion',
    prompt: [
      '你是注册会计师助理。请撰写 E1-29「审计结论」。',
      '可参考：A 未见异常；B 异常已说明；C 需扩大核查。',
      '只写结论；严禁 markdown；约 60～150 字。',
    ].join(''),
    context: aiContext(),
    existingContent: auditConclusion.value,
    confirmTitle: 'AI 生成 · 审计结论',
  })
  if (text) saveConclusion(sanitize(text, 'conclusion'))
}

function applyConclusionTemplate(code: string): void {
  const t = conclusionTemplates.find(i => i.value === code)
  if (t) saveConclusion(t.text)
}

async function handleImport(file: File): Promise<boolean> {
  const res = await importData(file)
  if (res.success) {
    ElMessage.success(res.message || '导入成功')
    await reloadWorkpaperData?.()
    hydrate()
  } else {
    ElMessage.warning(res.message || '导入失败')
  }
  return false
}

async function onSyncE10(mode: 'replace' | 'merge' = 'replace'): Promise<void> {
  const preview = previewSyncFromE10()
  if (!preview) {
    ElMessage.warning('未找到 E1-10 账户清单数据')
    return
  }
  try {
    await ElMessageBox.confirm(
      `预览：E1-10 共 ${preview.sourceCount} 户；当前本表 ${preview.existingCount} 户`
      + (preview.newAccounts ? `（可新增 ${preview.newAccounts}）` : '')
      + '。\n'
      + (mode === 'merge'
        ? '合并：仅追加本表尚无的账号，保留已有加深字段。'
        : '覆盖：按 E1-10 重建清单，同账号保留开户地/异地原因等加深字段。')
      + '\n是否继续？',
      mode === 'merge' ? '从 E1-10 合并同步' : '从 E1-10 覆盖同步',
      { type: 'warning', confirmButtonText: '执行', cancelButtonText: '取消' },
    )
  } catch {
    return
  }
  const n = syncFromE10(mode)
  if (n) ElMessage.success(`已${mode === 'merge' ? '合并' : '覆盖'}同步 ${n} 户`)
  else ElMessage.warning(mode === 'merge' ? '无新增账号可合并' : '未找到 E1-10 账户清单数据')
}

function onRecalc(): void {
  recalcCurrentYearFromRows()
  ElMessage.success('已按明细回填本期年度指标')
}

function rowClass({ row }: { row: BankAnalysisRow }): string {
  if (row.checkResult === '不一致' || row.companyInfoConsistent === '不一致') return 'e1-ba-warn'
  if (row.hasBusiness === '否') return 'e1-ba-remote'
  return ''
}
</script>

<template>
  <E1IpoSheetChrome
    class="e1-tab-bank-analysis"
    title="银行账户分析 (E1-29)"
    :is-applicable="isApplicable"
    :is-readonly="isReadonly"
    :is-loading="isLoading"
    :project-id="projectId"
    :index-chips="['wp:E1-10', 'wp:E1-11', 'wp:E1-18']"
    :is-importing="isImporting"
    @update:applicable="setApplicable"
    @export-template="exportTemplate"
    @export-data="exportData"
    @import="handleImport"
  >
    <template #guidance>
      <details class="guidance-details">
        <summary>📋 编制提示</summary>
        <div class="guidance-content">
          <p>1. 本表为 IPO/舞弊应对下银行账户完整性加深程序（E1-10 的延伸）。</p>
          <p>2. （一）清单核对账面，并填写开户地、当地有无经济业务、异地开户原因。</p>
          <p>3. （二）汇总三年账户数量/开销户/零余额，判断是否匹配业务规模、是否频繁开销户。</p>
          <p>4. 按下方红旗提示逐项排查，异常写入说明；可从 E1-10 同步清单后补齐加深字段。</p>
        </div>
      </details>
    </template>

    <template #goal>
      <el-alert type="info" :closable="false" class="mb8" title="一、审计目标">
        <p>1. 资产负债表中记录的货币资金是存在的，且已记录于恰当的账户；记录的货币资金由被审计单位拥有或控制；</p>
        <p>2. 所有应当记录的货币资金均已记录，相关披露已包括。</p>
      </el-alert>
    </template>

    <template #status>
      <el-tag v-if="isApplicable && inconsistencyCount" size="small" type="danger">不一致 {{ inconsistencyCount }}</el-tag>
      <el-tag v-if="isApplicable && remoteCount" size="small" type="warning">无业务开户地 {{ remoteCount }}</el-tag>
    </template>

    <template #actions>
      <el-dropdown size="small" trigger="click" :disabled="isReadonly || !isApplicable">
        <el-button size="small" :disabled="isReadonly || !isApplicable">从 E1-10 同步 ▾</el-button>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item @click="onSyncE10('replace')">覆盖同步</el-dropdown-item>
            <el-dropdown-item @click="onSyncE10('merge')">合并同步</el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
    </template>

        <!-- （一）清单 -->
        <el-card shadow="never" class="section-card">
          <template #header>
            <div class="card-header">
              <span>二、审计过程（一）银行账户清单与账面核对</span>
              <el-button size="small" type="primary" :disabled="isReadonly" @click="addRow">+ 添加行</el-button>
            </div>
          </template>
          <div class="table-scroll">
            <el-table :data="pack.rows" border size="small" max-height="420" :row-class-name="rowClass">
              <el-table-column type="index" label="序号" width="50" />
              <el-table-column label="开户银行" min-width="120">
                <template #default="{ row }">
                  <el-input :model-value="row.bank" :disabled="isReadonly" size="small"
                    @change="(v: string) => updateCell(row.id, 'bank', v)" />
                </template>
              </el-table-column>
              <el-table-column label="账号" width="130">
                <template #default="{ row }">
                  <el-input :model-value="row.accountNo" :disabled="isReadonly" size="small"
                    @change="(v: string) => updateCell(row.id, 'accountNo', v)" />
                </template>
              </el-table-column>
              <el-table-column label="账户性质" width="90">
                <template #default="{ row }">
                  <el-input :model-value="row.accountType" :disabled="isReadonly" size="small"
                    @change="(v: string) => updateCell(row.id, 'accountType', v)" />
                </template>
              </el-table-column>
              <el-table-column label="账户状态" width="90">
                <template #default="{ row }">
                  <el-input :model-value="row.accountStatus" :disabled="isReadonly" size="small"
                    @change="(v: string) => updateCell(row.id, 'accountStatus', v)" />
                </template>
              </el-table-column>
              <el-table-column label="开户日期" width="120">
                <template #default="{ row }">
                  <el-date-picker
                    :model-value="row.openDate"
                    :disabled="isReadonly"
                    type="date"
                    value-format="YYYY-MM-DD"
                    size="small"
                    style="width: 100%"
                    @update:model-value="(v: string) => updateCell(row.id, 'openDate', v || '')"
                  />
                </template>
              </el-table-column>
              <el-table-column label="销户日期" width="120">
                <template #default="{ row }">
                  <el-date-picker
                    :model-value="row.closeDate"
                    :disabled="isReadonly"
                    type="date"
                    value-format="YYYY-MM-DD"
                    size="small"
                    style="width: 100%"
                    @update:model-value="(v: string) => updateCell(row.id, 'closeDate', v || '')"
                  />
                </template>
              </el-table-column>
              <el-table-column label="开户原因" min-width="100">
                <template #default="{ row }">
                  <el-input :model-value="row.openReason" :disabled="isReadonly" size="small"
                    @change="(v: string) => updateCell(row.id, 'openReason', v)" />
                </template>
              </el-table-column>
              <el-table-column label="销户原因" min-width="100">
                <template #default="{ row }">
                  <el-input :model-value="row.closeReason" :disabled="isReadonly" size="small"
                    @change="(v: string) => updateCell(row.id, 'closeReason', v)" />
                </template>
              </el-table-column>
              <el-table-column label="与企业信息一致" width="120">
                <template #default="{ row }">
                  <el-select
                    :model-value="row.companyInfoConsistent"
                    :disabled="isReadonly"
                    size="small"
                    clearable
                    @change="(v: string) => updateCell(row.id, 'companyInfoConsistent', v || '')"
                  >
                    <el-option v-for="o in consistentOptions" :key="o.value" :label="o.label" :value="o.value" />
                  </el-select>
                </template>
              </el-table-column>
              <el-table-column label="不一致原因" min-width="100">
                <template #default="{ row }">
                  <el-input :model-value="row.inconsistencyReason" :disabled="isReadonly" size="small"
                    @change="(v: string) => updateCell(row.id, 'inconsistencyReason', v)" />
                </template>
              </el-table-column>
              <el-table-column label="账户开户地" width="100" class-name="emphasis-col">
                <template #default="{ row }">
                  <el-input :model-value="row.location" :disabled="isReadonly" size="small"
                    @change="(v: string) => updateCell(row.id, 'location', v)" />
                </template>
              </el-table-column>
              <el-table-column label="当地有经济业务" width="120" class-name="emphasis-col">
                <template #default="{ row }">
                  <el-select
                    :model-value="row.hasBusiness"
                    :disabled="isReadonly"
                    size="small"
                    clearable
                    @change="(v: string) => updateCell(row.id, 'hasBusiness', (v || '') as YesNo)"
                  >
                    <el-option v-for="o in ynOptions" :key="o.value" :label="o.label" :value="o.value" />
                  </el-select>
                </template>
              </el-table-column>
              <el-table-column label="异地开户原因" min-width="110" class-name="emphasis-col">
                <template #default="{ row }">
                  <el-input :model-value="row.remoteReason" :disabled="isReadonly" size="small"
                    @change="(v: string) => updateCell(row.id, 'remoteReason', v)" />
                </template>
              </el-table-column>
              <el-table-column label="账面有记录" width="100">
                <template #default="{ row }">
                  <el-select
                    :model-value="row.hasBookRecord"
                    :disabled="isReadonly"
                    size="small"
                    clearable
                    @change="(v: string) => updateCell(row.id, 'hasBookRecord', (v || '') as YesNo)"
                  >
                    <el-option v-for="o in ynOptions" :key="o.value" :label="o.label" :value="o.value" />
                  </el-select>
                </template>
              </el-table-column>
              <el-table-column label="清单与账面" width="100">
                <template #default="{ row }">
                  <el-select
                    :model-value="row.checkResult"
                    :disabled="isReadonly"
                    size="small"
                    clearable
                    @change="(v: string) => updateCell(row.id, 'checkResult', v || '')"
                  >
                    <el-option v-for="o in consistentOptions" :key="o.value" :label="o.label" :value="o.value" />
                  </el-select>
                </template>
              </el-table-column>
              <el-table-column label="零余额" width="80">
                <template #default="{ row }">
                  <el-select
                    :model-value="row.isZeroBalance"
                    :disabled="isReadonly"
                    size="small"
                    clearable
                    @change="(v: string) => updateCell(row.id, 'isZeroBalance', (v || '') as YesNo)"
                  >
                    <el-option v-for="o in ynOptions" :key="o.value" :label="o.label" :value="o.value" />
                  </el-select>
                </template>
              </el-table-column>
              <el-table-column label="备注" min-width="90">
                <template #default="{ row }">
                  <el-input :model-value="row.remark" :disabled="isReadonly" size="small"
                    @change="(v: string) => updateCell(row.id, 'remark', v)" />
                </template>
              </el-table-column>
              <el-table-column label="操作" width="64" fixed="right">
                <template #default="{ row }">
                  <el-button type="danger" text size="small" :disabled="isReadonly" @click="removeRow(row.id)">删</el-button>
                </template>
              </el-table-column>
            </el-table>
          </div>
        </el-card>

        <!-- （二）分析 -->
        <el-card shadow="never" class="section-card">
          <template #header>
            <div class="card-header">
              <span>二、审计过程（二）公司账户情况分析</span>
              <el-button size="small" :disabled="isReadonly" @click="onRecalc">按明细回填本期</el-button>
            </div>
          </template>
          <el-table :data="[
            { key: 'accountCount', label: '公司账户数量' },
            { key: 'openedCount', label: '本期开户数量' },
            { key: 'closedCount', label: '本期销户数量' },
            { key: 'zeroBalanceCount', label: '零余额账户数量' },
          ]" border size="small" style="margin-bottom: 12px">
            <el-table-column prop="label" label="项目" width="150" />
            <el-table-column v-for="y in pack.years" :key="y.year" :label="`${y.year}年`" width="120" align="right">
              <template #default="{ row }">
                <el-input-number
                  :model-value="(y as any)[row.key]"
                  :disabled="isReadonly"
                  :controls="false"
                  size="small"
                  style="width: 100%"
                  @change="(v: number) => updateYearCell(y.year, row.key, v ?? 0)"
                />
              </template>
            </el-table-column>
          </el-table>

          <el-form label-width="180px" size="small" class="judgment-form">
            <el-form-item label="无经济业务地开户数量">
              <el-input-number
                :model-value="pack.judgment.remoteNoBusinessCount"
                :disabled="isReadonly"
                :controls="false"
                @change="(v: number) => updateJudgment('remoteNoBusinessCount', v ?? 0)"
              />
            </el-form-item>
            <el-form-item label="是否与业务规模匹配">
              <el-select
                :model-value="pack.judgment.matchBusinessScale"
                :disabled="isReadonly"
                clearable
                style="width: 120px"
                @change="(v: string) => updateJudgment('matchBusinessScale', (v || '') as YesNo)"
              >
                <el-option v-for="o in ynOptions" :key="o.value" :label="o.label" :value="o.value" />
              </el-select>
            </el-form-item>
            <el-form-item label="是否频繁开户">
              <el-select
                :model-value="pack.judgment.frequentOpen"
                :disabled="isReadonly"
                clearable
                style="width: 120px"
                @change="(v: string) => updateJudgment('frequentOpen', (v || '') as YesNo)"
              >
                <el-option v-for="o in ynOptions" :key="o.value" :label="o.label" :value="o.value" />
              </el-select>
            </el-form-item>
            <el-form-item label="是否频繁销户">
              <el-select
                :model-value="pack.judgment.frequentClose"
                :disabled="isReadonly"
                clearable
                style="width: 120px"
                @change="(v: string) => updateJudgment('frequentClose', (v || '') as YesNo)"
              >
                <el-option v-for="o in ynOptions" :key="o.value" :label="o.label" :value="o.value" />
              </el-select>
            </el-form-item>
            <el-form-item label="异常说明">
              <el-input
                type="textarea"
                :model-value="pack.judgment.anomalyNote"
                :disabled="isReadonly"
                :autosize="{ minRows: 2 }"
                @change="(v: string) => updateJudgment('anomalyNote', v)"
              />
            </el-form-item>
            <el-form-item label="其他备注">
              <el-input
                :model-value="pack.judgment.otherRemark"
                :disabled="isReadonly"
                @change="(v: string) => updateJudgment('otherRemark', v)"
              />
            </el-form-item>
          </el-form>
        </el-card>

        <!-- 红旗提示 -->
        <el-card shadow="never" class="section-card">
          <template #header><span>提示 · 异常情形检查</span></template>
          <div v-for="t in pack.tips" :key="t.key" class="tip-row">
            <el-checkbox
              :model-value="t.checked"
              :disabled="isReadonly"
              @change="(v: string | number | boolean) => updateTip(t.key, 'checked', Boolean(v))"
            >
              {{ t.label }}
            </el-checkbox>
            <el-input
              v-if="t.checked"
              :model-value="t.note"
              :disabled="isReadonly"
              size="small"
              placeholder="说明/索引"
              style="max-width: 360px"
              @change="(v: string) => updateTip(t.key, 'note', v)"
            />
          </div>
          <el-alert type="info" :closable="false" class="mt8" show-icon>
            另应：询问出纳了解开立/使用/注销；结合企业信用报告（E1-18）；外币户完整性存疑时查公章登记/网银清单或外管局。
          </el-alert>
        </el-card>

        <!-- 说明结论 -->
        <el-card shadow="never" class="audit-note-card">
          <template #header>
            <div class="card-header">
              <span>三、审计说明</span>
              <el-button
                size="small"
                type="primary"
                plain
                :disabled="isReadonly"
                :loading="isGenerating('e1-29-audit-note')"
                @click="generateAuditNote"
              >
                <el-icon><MagicStick /></el-icon> AI辅助
              </el-button>
            </div>
          </template>
          <el-input
            type="textarea"
            :model-value="auditNote"
            :disabled="isReadonly"
            :autosize="{ minRows: 4 }"
            placeholder="说明清单核对、账户变动分析及异常排查结果…"
            @update:model-value="(v: string) => { if (!isReadonly) auditNote = v }"
            @change="(v: string) => saveNote(v)"
          />
        </el-card>

        <el-card shadow="never" class="audit-note-card">
          <template #header>
            <div class="card-header">
              <span>四、审计结论</span>
              <div class="header-actions">
                <el-select
                  size="small"
                  placeholder="结论模板"
                  style="width: 140px"
                  :disabled="isReadonly"
                  @change="applyConclusionTemplate"
                >
                  <el-option v-for="t in conclusionTemplates" :key="t.value" :label="t.label" :value="t.value" />
                </el-select>
                <el-button
                  size="small"
                  type="primary"
                  plain
                  :disabled="isReadonly"
                  :loading="isGenerating('e1-29-audit-conclusion')"
                  @click="generateAuditConclusion"
                >
                  <el-icon><MagicStick /></el-icon> AI辅助
                </el-button>
              </div>
            </div>
          </template>
          <el-input
            type="textarea"
            :model-value="auditConclusion"
            :disabled="isReadonly"
            :autosize="{ minRows: 3 }"
            placeholder="填写审计结论…"
            @update:model-value="(v: string) => { if (!isReadonly) auditConclusion = v }"
            @change="(v: string) => saveConclusion(v)"
          />
        </el-card>
  </E1IpoSheetChrome>
</template>

<style scoped>
.e1-tab-bank-analysis { padding: 12px 0; }
.guidance-details {
  margin-bottom: 12px; border-left: 3px solid #409eff; background: #ecf5ff;
  border-radius: 4px; padding: 8px 12px;
}
.guidance-details summary { cursor: pointer; font-weight: 500; color: #409eff; }
.guidance-content { margin-top: 8px; font-size: var(--wp-font-size, 13px); color: #606266; line-height: 1.6; }
.guidance-content p { margin: 2px 0; }
.mb8 { margin-bottom: 8px; }
.mt8 { margin-top: 8px; }
.card-header, .header-actions {
  display: flex; align-items: center; gap: 8px; flex-wrap: wrap;
}
.section-card { margin-bottom: 12px; }
.card-header { font-weight: 500; width: 100%; justify-content: space-between; }
.table-scroll { overflow-x: auto; }
.judgment-form { max-width: 720px; }
.tip-row {
  display: flex; align-items: center; gap: 12px; flex-wrap: wrap;
  margin-bottom: 8px; font-size: var(--wp-font-size, 13px);
}
.audit-note-card { margin-top: 12px; }
:deep(.emphasis-col .cell) { color: #c45656; font-weight: 600; }
:deep(.e1-ba-warn) { background-color: #fef0f0 !important; }
:deep(.e1-ba-remote) { background-color: #fdf6ec !important; }
</style>
