<script setup lang="ts">
/**
 * E1TabDepositInterestDaily.vue — E1-30 存款规模与利息收入匹配性分析
 * 日余额 × 年利率 / 360；按月分页展示；配置银行账号后动态列。
 */
import { computed, inject, toRef, type Ref } from 'vue'
import { MagicStick } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  useE1DepositDailyMatch,
  DAILY_DEPOSIT_TYPE_OPTIONS,
  dailyDepositTypeLabel,
  type DailyDepositType,
  type E15SyncMode,
} from '../composables/useE1DepositDailyMatch'
import { useE1AiGenerate } from '../composables/useE1AiGenerate'
import { useE1ImportExport } from '../composables/useE1ImportExport'
import type { UseE1BaseOptions } from '../composables/useE1Adjudication'
import E1IpoSheetChrome from './E1IpoSheetChrome.vue'
import { DisplayPrefs_Key } from '../composables/displayPrefsKey'
import { useDisplayPrefsStore } from '@/stores/displayPrefs'

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

const displayPrefs = inject(DisplayPrefs_Key, null) ?? useDisplayPrefsStore()
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
  viewMonth,
  monthDates,
  calculatedInterest,
  interestDiff,
  typeYearInterest,
  groupDayInterest,
  dayInterest,
  dayBalances,
  dayRates,
  setApplicable,
  setYear,
  setBookInterest,
  addGroup,
  removeGroup,
  updateGroup,
  addAccount,
  removeAccount,
  updateAccountNo,
  setBalance,
  setRateOverride,
  syncFromE15,
  previewSyncFromE15,
  saveNote,
  saveConclusion,
  hydrate,
} = useE1DepositDailyMatch(options)

const { generateText, isGenerating } = useE1AiGenerate(toRef(props, 'wpId') as Ref<string>)
const sheetCode = computed(() => 'E1-30')
const { exportTemplate, exportData, importData, isImporting } = useE1ImportExport({
  wpId: toRef(props, 'wpId') as unknown as Ref<string>,
  sheet: sheetCode as unknown as Ref<string>,
})

const monthOptions = Array.from({ length: 12 }, (_, i) => ({
  value: i + 1,
  label: `${i + 1}月`,
}))

const conclusionTemplates = [
  {
    value: 'A',
    label: 'A—测算相符',
    text: '按每日存款余额及约定利率测算的利息收入与账面利息收入差异在可接受范围内，利息收入记录合理、完整，未见重大异常。',
  },
  {
    value: 'B',
    label: 'B—差异已解释',
    text: '测算利息与账面利息存在差异，原因已核实并说明；除已识别事项外，未见其他重大异常。',
  },
  {
    value: 'C',
    label: 'C—需进一步核查',
    text: '测算与账面利息差异较大或证据不足，需扩大核对范围或提请调整，结果见审计说明。',
  },
]

function fmtAmt(v: number): string {
  return displayPrefs.fmtAmount(v)
}

function aiContext(): Record<string, unknown> {
  return {
    底稿: 'E1-30 存款规模与利息收入匹配性分析',
    年份: pack.value.year,
    银行组数: pack.value.groups.length,
    测算利息收入: calculatedInterest.value,
    账面利息收入: pack.value.bookInterest,
    差异: interestDiff.value,
    活期测算: typeYearInterest.value.demand,
    七天通知测算: typeYearInterest.value.notice,
    大额存单测算: typeYearInterest.value.cd,
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
    section: 'e1-30-audit-note',
    prompt: [
      '你是注册会计师助理。请撰写 E1-30「审计说明」，只描述日余额利息测算与账面核对过程与发现，不要写审计结论。',
      '应概括：年份、测算方法（日余额×年利率/360）、测算合计、账面利息、差异及主要原因方向。',
      '严禁 markdown；约 120～250 字。',
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
    section: 'e1-30-audit-conclusion',
    prompt: [
      '你是注册会计师助理。请撰写 E1-30「审计结论」。',
      '可参考：A 测算相符；B 差异已解释；C 需进一步核查。',
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

async function onSyncE15(mode: E15SyncMode = 'replace'): Promise<void> {
  const preview = previewSyncFromE15()
  if (!preview) {
    ElMessage.warning('未找到 E1-15 利息测算账户数据')
    return
  }
  const bankHint = preview.banks.length
    ? `（银行：${preview.banks.join('、')}${preview.accountCount > preview.banks.length ? ' 等' : ''}）`
    : ''
  try {
    await ElMessageBox.confirm(
      `预览：E1-15 共 ${preview.accountCount} 户${bankHint}；当前本表 ${preview.existingGroups} 个账户组`
      + (preview.bookInterest ? `；账面利息 ${preview.bookInterest}` : '')
      + '。\n'
      + (mode === 'merge'
        ? '合并：按账号增量加入，保留已有日余额/利率；空格子才用月均摊日。'
        : '覆盖：替换账户组，并按月均余额摊成日余额（需对账单精修）。')
      + '\n是否继续？',
      mode === 'merge' ? '从 E1-15 合并同步' : '从 E1-15 覆盖同步',
      { type: 'warning', confirmButtonText: '执行', cancelButtonText: '取消' },
    )
  } catch {
    return
  }
  const r = syncFromE15({ fillDailyFromMonthly: true, mode })
  if (!r.groups) {
    ElMessage.warning('未找到 E1-15 利息测算账户数据')
    return
  }
  ElMessage.success(
    `已${mode === 'merge' ? '合并' : '覆盖'}同步 ${r.groups} 个账户组`
    + (r.addedAccounts ? `（新增账号 ${r.addedAccounts}）` : '')
    + (r.bookInterest ? `，账面利息 ${r.bookInterest}` : '')
    + (r.daysFilled ? `，摊入日余额 ${r.daysFilled} 格` : ''),
  )
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
</script>

<template>
  <E1IpoSheetChrome
    class="e1-tab-deposit-daily"
    title="存款规模与利息匹配 (E1-30)"
    :is-applicable="isApplicable"
    :is-readonly="isReadonly"
    :is-loading="isLoading"
    :project-id="projectId"
    :index-chips="['wp:E1-15', 'wp:E1-3']"
    :is-importing="isImporting"
    :skeleton-rows="10"
    @update:applicable="setApplicable"
    @export-template="exportTemplate"
    @export-data="exportData"
    @import="handleImport"
  >
    <template #guidance>
      <details class="guidance-details">
        <summary>📋 编制提示</summary>
        <div class="guidance-content">
          <p>1. 本表用于 IPO/舞弊应对下，按每日存款余额测算全年利息并与账面利息核对。</p>
          <p>2. 先配置活期 / 七天通知 / 大额存单的银行与账号及年利率，再按月填入日余额（可从 E1-15 覆盖/合并同步；月均摊日仅为辅助，须按对账单精修）。</p>
          <p>3. 测算利息 = 余额 × 年利率 ÷ 360（对齐源模板）；活期按银行合计余额×组利率。</p>
          <p>4. 与 E1-15 月度粗算衔接：月度差异大时下钻本表逐日核对。</p>
        </div>
      </details>
    </template>

    <template #goal>
      <el-alert
        type="info"
        :closable="false"
        class="mb8"
        title="一、审计目标：1.资产负债表中记录的货币资金是存在的，且已记录于恰当的账户；2.所有应当记录的货币资金均已记录；3.货币资金以恰当金额计入报表并恰当披露。"
      />
    </template>

    <template #status>
      <span v-if="isApplicable" class="year-wrap">
        年度
        <el-input-number
          :model-value="pack.year"
          :disabled="isReadonly"
          :controls="false"
          :min="2000"
          :max="2100"
          size="small"
          style="width: 90px"
          @change="(v: number) => setYear(v ?? pack.year)"
        />
      </span>
    </template>

    <template #actions>
      <el-dropdown size="small" trigger="click" :disabled="isReadonly || !isApplicable">
        <el-button size="small" :disabled="isReadonly || !isApplicable">从 E1-15 同步 ▾</el-button>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item @click="onSyncE15('replace')">覆盖同步</el-dropdown-item>
            <el-dropdown-item @click="onSyncE15('merge')">合并同步</el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
    </template>

        <el-alert type="info" :closable="false" class="mb8" title="二、审计过程">
          获取全部账号每日存款余额，根据利率计算全年利息收入，与账面实际利息收入核对。计息按「余额×年利率/360」。
        </el-alert>

        <!-- 账户配置 -->
        <el-card shadow="never" class="section-card">
          <template #header>
            <div class="card-header">
              <span>银行账号配置</span>
              <el-dropdown size="small" :disabled="isReadonly" @command="(t: DailyDepositType) => addGroup(t)">
                <el-button size="small" type="primary">+ 添加银行组 ▾</el-button>
                <template #dropdown>
                  <el-dropdown-menu>
                    <el-dropdown-item v-for="o in DAILY_DEPOSIT_TYPE_OPTIONS" :key="o.value" :command="o.value">
                      {{ o.label }}
                    </el-dropdown-item>
                  </el-dropdown-menu>
                </template>
              </el-dropdown>
            </div>
          </template>
          <div v-for="g in pack.groups" :key="g.id" class="group-block">
            <div class="group-head">
              <el-select
                :model-value="g.depositType"
                :disabled="isReadonly"
                size="small"
                style="width: 140px"
                @change="(v: DailyDepositType) => updateGroup(g.id, 'depositType', v)"
              >
                <el-option v-for="o in DAILY_DEPOSIT_TYPE_OPTIONS" :key="o.value" :label="o.label" :value="o.value" />
              </el-select>
              <el-input
                :model-value="g.bank"
                :disabled="isReadonly"
                size="small"
                placeholder="银行名称"
                style="width: 160px"
                @change="(v: string) => updateGroup(g.id, 'bank', v)"
              />
              <span>年利率</span>
              <el-input-number
                :model-value="g.annualRate"
                :disabled="isReadonly"
                :controls="false"
                :step="0.0001"
                size="small"
                style="width: 110px"
                @change="(v: number) => updateGroup(g.id, 'annualRate', v ?? 0)"
              />
              <el-button size="small" :disabled="isReadonly" @click="addAccount(g.id)">+ 账号</el-button>
              <el-button size="small" type="danger" text :disabled="isReadonly" @click="removeGroup(g.id)">删除组</el-button>
            </div>
            <div class="acct-row">
              <div v-for="a in g.accounts" :key="a.id" class="acct-item">
                <el-input
                  :model-value="a.accountNo"
                  :disabled="isReadonly"
                  size="small"
                  placeholder="账号"
                  style="width: 140px"
                  @change="(v: string) => updateAccountNo(g.id, a.id, v)"
                />
                <el-button
                  v-if="g.accounts.length > 1"
                  size="small"
                  type="danger"
                  text
                  :disabled="isReadonly"
                  @click="removeAccount(g.id, a.id)"
                >删</el-button>
              </div>
            </div>
          </div>
        </el-card>

        <!-- 日余额（按月） -->
        <el-card shadow="never" class="section-card">
          <template #header>
            <div class="card-header">
              <span>三、每日存款余额与测算利息</span>
              <el-radio-group v-model="viewMonth" size="small">
                <el-radio-button v-for="m in monthOptions" :key="m.value" :value="m.value">{{ m.label }}</el-radio-button>
              </el-radio-group>
            </div>
          </template>
          <div class="table-scroll">
            <el-table :data="monthDates" border size="small" max-height="480" style="width: max-content; min-width: 100%">
              <el-table-column label="日期" width="110" fixed>
                <template #default="{ row }">{{ row }}</template>
              </el-table-column>
              <el-table-column
                v-for="g in pack.groups"
                :key="g.id"
                :label="`${dailyDepositTypeLabel(g.depositType)} · ${g.bank || '未命名银行'}`"
                align="center"
              >
                <el-table-column
                  v-for="a in g.accounts"
                  :key="a.id"
                  :label="a.accountNo || '账号'"
                  width="118"
                  align="right"
                >
                  <template #default="{ row }">
                    <el-input-number
                      :model-value="dayBalances(row)[a.id] || 0"
                      :disabled="isReadonly"
                      :controls="false"
                      size="small"
                      style="width: 100%"
                      @change="(v: number) => setBalance(row, a.id, v ?? 0)"
                    />
                  </template>
                </el-table-column>
                <template v-if="g.depositType !== 'demand'">
                  <el-table-column
                    v-for="a in g.accounts"
                    :key="`rate-${a.id}`"
                    :label="`${a.accountNo || '账号'}利率`"
                    width="100"
                    align="right"
                  >
                    <template #default="{ row }">
                      <el-input-number
                        :model-value="dayRates(row)[a.id] ?? g.annualRate"
                        :disabled="isReadonly"
                        :controls="false"
                        :step="0.0001"
                        size="small"
                        style="width: 100%"
                        @change="(v: number) => setRateOverride(row, a.id, v ?? 0)"
                      />
                    </template>
                  </el-table-column>
                </template>
                <el-table-column label="利息" width="100" align="right">
                  <template #default="{ row }">
                    <span class="calc">{{ fmtAmt(groupDayInterest(g.id, row)) }}</span>
                  </template>
                </el-table-column>
              </el-table-column>
              <el-table-column label="利息收入合计" width="120" align="right" fixed="right">
                <template #default="{ row }">
                  <span class="calc">{{ fmtAmt(dayInterest(row)) }}</span>
                </template>
              </el-table-column>
            </el-table>
          </div>
          <div class="summary-bar">
            <span>活期测算：{{ fmtAmt(typeYearInterest.demand) }}</span>
            <span>七天通知：{{ fmtAmt(typeYearInterest.notice) }}</span>
            <span>大额存单：{{ fmtAmt(typeYearInterest.cd) }}</span>
            <span><b>全年测算合计：{{ fmtAmt(calculatedInterest) }}</b></span>
          </div>
        </el-card>

        <!-- 核对 -->
        <el-card shadow="never" class="section-card">
          <template #header><span>三、审计说明 · 利息核对</span></template>
          <el-table
            :data="[
              { item: '测算利息收入', amount: calculatedInterest, editable: false },
              { item: '账面利息收入', amount: pack.bookInterest, editable: true },
              { item: '差异', amount: interestDiff, editable: false },
            ]"
            border
            size="small"
            style="max-width: 480px; margin-bottom: 12px"
          >
            <el-table-column prop="item" label="项目" width="140" />
            <el-table-column label="金额" align="right">
              <template #default="{ row }">
                <el-input-number
                  v-if="row.editable"
                  :model-value="pack.bookInterest"
                  :disabled="isReadonly"
                  :controls="false"
                  size="small"
                  style="width: 100%"
                  @change="(v: number) => setBookInterest(v ?? 0)"
                />
                <span v-else :class="{ 'diff-warn': row.item === '差异' && Math.abs(row.amount) >= 0.01 }">
                  {{ fmtAmt(row.amount) }}
                </span>
              </template>
            </el-table-column>
          </el-table>

          <el-card shadow="never" class="audit-note-card">
            <template #header>
              <div class="card-header">
                <span>审计说明</span>
                <el-button
                  size="small"
                  type="primary"
                  plain
                  :disabled="isReadonly"
                  :loading="isGenerating('e1-30-audit-note')"
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
              placeholder="说明测算方法、样本范围、与账面差异原因等…"
              @update:model-value="(v: string) => { if (!isReadonly) auditNote = v }"
              @change="(v: string) => saveNote(v)"
            />
          </el-card>
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
                  :loading="isGenerating('e1-30-audit-conclusion')"
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
.e1-tab-deposit-daily { padding: 12px 0; }
.guidance-details {
  margin-bottom: 12px;
  border-left: 3px solid #409eff;
  background: #ecf5ff;
  border-radius: 4px;
  padding: 8px 12px;
}
.guidance-details summary { cursor: pointer; font-weight: 500; color: #409eff; }
.guidance-content { margin-top: 8px; font-size: var(--wp-font-size, 13px); color: #606266; line-height: 1.6; }
.guidance-content p { margin: 2px 0; }
.mb8 { margin-bottom: 8px; }
.tab-toolbar {
  display: flex; justify-content: space-between; align-items: center;
  flex-wrap: wrap; gap: 8px; margin-bottom: 12px;
}
.toolbar-left, .toolbar-right, .header-actions, .card-header, .group-head, .acct-row {
  display: flex; align-items: center; gap: 8px; flex-wrap: wrap;
}
.year-wrap { display: inline-flex; align-items: center; gap: 6px; font-size: 13px; }
.chip-wrap { display: inline-flex; }
.not-applicable { padding: 48px 0; text-align: center; }
.section-card { margin-bottom: 12px; }
.card-header { font-weight: 500; width: 100%; justify-content: space-between; }
.group-block {
  border: 1px solid #ebeef5; border-radius: 4px; padding: 10px; margin-bottom: 10px; background: #fafafa;
}
.acct-item { display: inline-flex; align-items: center; gap: 4px; }
.table-scroll { overflow-x: auto; }
.calc { color: #606266; font-variant-numeric: tabular-nums; }
.summary-bar {
  display: flex; gap: 20px; flex-wrap: wrap;
  padding: 10px 12px; margin-top: 10px; background: #f5f7fa; border-radius: 4px;
  font-size: var(--wp-font-size, 13px);
}
.diff-warn { color: #f56c6c; font-weight: 600; }
.audit-note-card { margin-top: 12px; }
</style>
