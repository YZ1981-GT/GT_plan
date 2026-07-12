<!--
  GtA51CashflowAudit.vue — A5-1 现金流量表审计

  el-segmented 双模式 + el-tabs 6 Tab + 会计提示 el-drawer +
  程序表(21步骤) + 审定表(8行公式) + 勾稽核对(4组) +
  核查-子公司(2卡片) + 核查-明细(10行) + 其他现金流量(3类收支)
-->
<template>
  <div class="gt-a51">
    <!-- Toolbar -->
    <div class="gt-a51__toolbar">
      <el-segmented v-model="viewMode" :options="segOpts" size="small" />
      <div class="gt-a51__toolbar-right">
        <el-button size="small" text @click="tipsVisible = true">💡 会计提示</el-button>
        <span class="gt-a51__save-status">
          <template v-if="saveError">⚠ 保存失败</template>
          <template v-else-if="lastSavedAt">✓ 已保存</template>
          <template v-else>○ 未保存</template>
        </span>
      </div>
    </div>

    <!-- Structured View -->
    <el-tabs v-if="mode === 'structured'" v-model="activeTab" class="gt-a51__tabs">
      <!-- Tab 1: 程序表 -->
      <el-tab-pane label="程序表" name="program">
        <div class="gt-a51__objectives">
          <div v-for="(obj, i) in AUDIT_OBJECTIVES" :key="i" class="gt-a51__obj-card">{{ i + 1 }}. {{ obj }}</div>
        </div>
        <div class="gt-a51__progress">
          <span>已填 {{ programProgress.filled }} / {{ programProgress.total }}</span>
          <el-progress :percentage="Math.round(programProgress.filled / programProgress.total * 100)" :stroke-width="10" />
        </div>
        <div class="gt-a51__steps">
          <div v-for="step in PROGRAM_STEPS" :key="step.id" class="gt-a51__step" :style="{ paddingLeft: step.level * 24 + 'px' }">
            <span class="gt-a51__step-id">{{ step.id.replace('step-', '') }}</span>
            <span class="gt-a51__step-title">{{ step.title }}</span>
            <div class="gt-a51__step-ctrls">
              <el-button-group size="small">
                <el-button :type="getField(`a51-program-${step.id}.conclusion`) === 'Y' ? 'success' : 'default'" @click="setField(`a51-program-${step.id}.conclusion`, 'Y')">Y</el-button>
                <el-button :type="getField(`a51-program-${step.id}.conclusion`) === 'N' ? 'danger' : 'default'" @click="setField(`a51-program-${step.id}.conclusion`, 'N')">N</el-button>
                <el-button :type="getField(`a51-program-${step.id}.conclusion`) === 'NA' ? 'info' : 'default'" @click="setField(`a51-program-${step.id}.conclusion`, 'NA')">NA</el-button>
              </el-button-group>
              <el-input :model-value="getField(`a51-program-${step.id}.executor`)" size="small" placeholder="执行人" class="gt-a51__input-xs" @change="(v: string) => setField(`a51-program-${step.id}.executor`, v)" />
              <el-input :model-value="getField(`a51-program-${step.id}.description`)" size="small" placeholder="说明" class="gt-a51__input-md" @change="(v: string) => setField(`a51-program-${step.id}.description`, v)" />
              <el-input :model-value="getField(`a51-program-${step.id}.index_ref`)" size="small" placeholder="索引号" class="gt-a51__input-xs" @change="(v: string) => setField(`a51-program-${step.id}.index_ref`, v)" />
            </div>
          </div>
        </div>
        <div class="gt-a51__approval">
          <span>经理签字：</span>
          <el-input :model-value="getField('a51-program-approval.manager')" size="small" placeholder="经理" class="gt-a51__input-sm" @change="(v: string) => setField('a51-program-approval.manager', v)" />
          <span style="margin-left:16px">日期：</span>
          <el-date-picker :model-value="getField('a51-program-approval.date')" type="date" size="small" value-format="YYYY-MM-DD" placeholder="日期" @change="(v: any) => setField('a51-program-approval.date', v || '')" />
        </div>
      </el-tab-pane>

      <!-- Tab 2: 审定表 -->
      <el-tab-pane label="审定表" name="audit">
        <el-table :data="auditTableData" border size="small" class="gt-a51__audit-table">
          <el-table-column label="项目" prop="name" min-width="200" />
          <el-table-column label="未审数" width="130">
            <template #default="{ row }">
              <el-input v-if="row.type === 'editable'" :model-value="getField(`a51-audit-${row.id}.unadjusted`)" size="small" @change="(v: string) => setField(`a51-audit-${row.id}.unadjusted`, v)" />
              <span v-else class="gt-a51__auto">{{ fmtAmt(row.id === '6' ? getAuditRow6Amount() : getAuditRow8Amount()) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="调整额" width="130">
            <template #default="{ row }">
              <el-input v-if="row.type === 'editable'" :model-value="getField(`a51-audit-${row.id}.adjustment`)" size="small" @change="(v: string) => setField(`a51-audit-${row.id}.adjustment`, v)" />
              <span v-else class="gt-a51__auto">—</span>
            </template>
          </el-table-column>
          <el-table-column label="审计说明" width="160">
            <template #default="{ row }">
              <el-input v-if="row.type === 'editable'" :model-value="getField(`a51-audit-${row.id}.explanation`)" size="small" @change="(v: string) => setField(`a51-audit-${row.id}.explanation`, v)" />
            </template>
          </el-table-column>
          <el-table-column label="审定数" width="130">
            <template #default="{ row }">
              <span :class="{ 'gt-a51__auto': row.type === 'auto' }">{{ fmtAmt(row.type === 'auto' ? (row.id === '6' ? getAuditRow6Amount() : getAuditRow8Amount()) : getAuditedAmount(row.id)) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="备注" width="140">
            <template #default="{ row }">
              <el-input v-if="row.type === 'editable'" :model-value="getField(`a51-audit-${row.id}.remark`)" size="small" @change="(v: string) => setField(`a51-audit-${row.id}.remark`, v)" />
            </template>
          </el-table-column>
        </el-table>
        <div class="gt-a51__audit-note">
          <span class="gt-a51__label">审计说明：</span>
          <el-input :model-value="getField('a51-audit-note')" type="textarea" :autosize="{ minRows: 2 }" placeholder="审计说明" @change="(v: string) => setField('a51-audit-note', v)" />
        </div>
        <el-collapse class="gt-a51__collapse">
          <el-collapse-item title="编制说明">
            <ol class="gt-a51__notes-list">
              <li>货币资金余额取自审定后余额表。</li>
              <li>受限存款包括各类保证金、冻结存款等，需逐项核对银行函证。</li>
              <li>现金等价物仅限持有期≤3月、流动性高、价值变动风险小的投资。</li>
              <li>如存在外币现金，按资产负债表日即期汇率折算。</li>
              <li>上年余额应与上年审定数核对一致，差异需查明原因。</li>
              <li>净增减额应与现金流量表"现金及现金等价物净增加额"勾稽。</li>
            </ol>
          </el-collapse-item>
        </el-collapse>
      </el-tab-pane>

      <!-- Tab 3: 勾稽核对 -->
      <el-tab-pane label="勾稽核对" name="reconcile">
        <div v-for="group in RECONCILE_GROUPS" :key="group.id" class="gt-a51__reconcile-card">
          <h4 class="gt-a51__card-title">{{ group.title }}</h4>
          <el-table :data="group.items" border size="small">
            <el-table-column label="项目" prop="name" min-width="200" />
            <el-table-column label="金额" width="150" align="right">
              <template #default="{ row }">
                <el-input :model-value="getField(`a51-reconcile-${group.id}-${row.id}.amount`)" size="small" class="gt-a51__amt-input" @change="(v: string) => setField(`a51-reconcile-${group.id}-${row.id}.amount`, v)" />
              </template>
            </el-table-column>
            <el-table-column label="备注" width="140">
              <template #default="{ row }">
                <el-input :model-value="getField(`a51-reconcile-${group.id}-${row.id}.remark`)" size="small" @change="(v: string) => setField(`a51-reconcile-${group.id}-${row.id}.remark`, v)" />
              </template>
            </el-table-column>
            <el-table-column label="索引号" width="100">
              <template #default="{ row }">
                <el-input :model-value="getField(`a51-reconcile-${group.id}-${row.id}.index_ref`)" size="small" @change="(v: string) => setField(`a51-reconcile-${group.id}-${row.id}.index_ref`, v)" />
              </template>
            </el-table-column>
          </el-table>
          <div class="gt-a51__reconcile-summary">
            <div class="gt-a51__reconcile-row"><span>合计</span><span class="gt-a51__amt">{{ fmtAmt(getReconcileTotal(group.id)) }}</span></div>
            <div class="gt-a51__reconcile-row">
              <span>报表数</span>
              <el-input :model-value="getField(`a51-reconcile-${group.id}.report_amount`)" size="small" class="gt-a51__amt-input" @change="(v: string) => setField(`a51-reconcile-${group.id}.report_amount`, v)" />
            </div>
            <div class="gt-a51__reconcile-row" :class="{ 'gt-a51__diff-warn': getReconcileDiff(group.id) !== 0 }">
              <span>差异</span><span class="gt-a51__amt">{{ fmtAmt(getReconcileDiff(group.id)) }}</span>
            </div>
          </div>
        </div>
      </el-tab-pane>

      <!-- Tab 4: 核查-子公司 -->
      <el-tab-pane label="核查-子公司" name="check4">
        <div v-for="section in CHECK4_SECTIONS" :key="section.id" class="gt-a51__check-card">
          <h4 class="gt-a51__card-title">{{ section.title }}</h4>
          <el-table :data="section.rows" border size="small">
            <el-table-column label="项目" prop="name" min-width="180" />
            <el-table-column label="差异" width="120" align="right">
              <template #default="{ row }">
                <span v-if="row.type === 'editable'" :class="{ 'gt-a51__diff-red': getCheckDiff(`check4-${section.id}`, row.id) !== 0 }">{{ fmtAmt(getCheckDiff(`check4-${section.id}`, row.id)) }}</span>
                <span v-else class="gt-a51__auto">—</span>
              </template>
            </el-table-column>
            <el-table-column label="原报数" width="130">
              <template #default="{ row }">
                <el-input v-if="row.type === 'editable'" :model-value="getField(`a51-check4-${section.id}-${row.id}.reported`)" size="small" @change="(v: string) => setField(`a51-check4-${section.id}-${row.id}.reported`, v)" />
              </template>
            </el-table-column>
            <el-table-column label="测算数" width="130">
              <template #default="{ row }">
                <el-input v-if="row.type === 'editable'" :model-value="getField(`a51-check4-${section.id}-${row.id}.estimated`)" size="small" @change="(v: string) => setField(`a51-check4-${section.id}-${row.id}.estimated`, v)" />
              </template>
            </el-table-column>
            <el-table-column label="测算依据" min-width="160">
              <template #default="{ row }">
                <el-input v-if="row.type === 'editable'" :model-value="getField(`a51-check4-${section.id}-${row.id}.basis`)" size="small" @change="(v: string) => setField(`a51-check4-${section.id}-${row.id}.basis`, v)" />
              </template>
            </el-table-column>
          </el-table>
        </div>
      </el-tab-pane>

      <!-- Tab 5: 核查-明细 -->
      <el-tab-pane label="核查-明细" name="check5">
        <el-table :data="CHECK5_ROWS" border size="small">
          <el-table-column label="项目" prop="name" min-width="200" />
          <el-table-column label="差异" width="120" align="right">
            <template #default="{ row }">
              <template v-if="row.type === 'editable'">
                <span :class="{ 'gt-a51__diff-red': getCheckDiff('check5', row.id) !== 0 }">{{ fmtAmt(getCheckDiff('check5', row.id)) }}</span>
              </template>
              <template v-else>
                <span class="gt-a51__auto">{{ row.id === '8' ? fmtAmt(check5Row8() - safeFloat(getField('a51-check5-8.reported'))) : (row.id === '10' ? fmtAmt(check5Row10() - safeFloat(getField('a51-check5-10.reported'))) : '—') }}</span>
              </template>
            </template>
          </el-table-column>
          <el-table-column label="原报数" width="130">
            <template #default="{ row }">
              <el-input v-if="row.type === 'editable'" :model-value="getField(`a51-check5-${row.id}.reported`)" size="small" @change="(v: string) => setField(`a51-check5-${row.id}.reported`, v)" />
              <span v-else class="gt-a51__auto">{{ row.id === '8' ? fmtAmt(safeFloat(getField('a51-check5-8.reported'))) : fmtAmt(safeFloat(getField('a51-check5-10.reported'))) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="测算数" width="130">
            <template #default="{ row }">
              <el-input v-if="row.type === 'editable'" :model-value="getField(`a51-check5-${row.id}.estimated`)" size="small" @change="(v: string) => setField(`a51-check5-${row.id}.estimated`, v)" />
              <span v-else class="gt-a51__auto">{{ row.id === '8' ? fmtAmt(check5Row8()) : fmtAmt(check5Row10()) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="测算依据" min-width="160">
            <template #default="{ row }">
              <el-input v-if="row.type === 'editable'" :model-value="getField(`a51-check5-${row.id}.basis`)" size="small" @change="(v: string) => setField(`a51-check5-${row.id}.basis`, v)" />
            </template>
          </el-table-column>
        </el-table>
        <p class="gt-a51__footnote">注：如存在持有待售资产中的现金，应在上表中增列并计入期末余额。受限部分包括各类保证金、法院冻结款项等。</p>
      </el-tab-pane>

      <!-- Tab 6: 其他现金流量 -->
      <el-tab-pane label="其他现金流量" name="otherCF">
        <div v-for="group in OTHER_CF_GROUPS" :key="group.id" class="gt-a51__other-card">
          <h4 class="gt-a51__card-title">{{ group.title }}</h4>
          <div class="gt-a51__other-layout">
            <!-- 收到 -->
            <div class="gt-a51__other-side">
              <h5>收到的其他与{{ group.title }}有关的现金</h5>
              <div v-for="item in group.receive" :key="item.id" class="gt-a51__other-row">
                <el-input :model-value="getField(`a51-other-${group.id}-receive-${item.id}.name`) || item.name" size="small" class="gt-a51__other-name" @change="(v: string) => setField(`a51-other-${group.id}-receive-${item.id}.name`, v)" />
                <el-input :model-value="getField(`a51-other-${group.id}-receive-${item.id}.amount`)" size="small" class="gt-a51__amt-input" placeholder="金额" @change="(v: string) => setField(`a51-other-${group.id}-receive-${item.id}.amount`, v)" />
              </div>
              <div class="gt-a51__other-total"><span>合计</span><span class="gt-a51__amt">{{ fmtAmt(getOtherCFTotal(group.id, 'receive')) }}</span></div>
            </div>
            <!-- 支付 -->
            <div class="gt-a51__other-side">
              <h5>支付的其他与{{ group.title }}有关的现金</h5>
              <div v-for="item in group.pay" :key="item.id" class="gt-a51__other-row">
                <el-input :model-value="getField(`a51-other-${group.id}-pay-${item.id}.name`) || item.name" size="small" class="gt-a51__other-name" @change="(v: string) => setField(`a51-other-${group.id}-pay-${item.id}.name`, v)" />
                <el-input :model-value="getField(`a51-other-${group.id}-pay-${item.id}.amount`)" size="small" class="gt-a51__amt-input" placeholder="金额" @change="(v: string) => setField(`a51-other-${group.id}-pay-${item.id}.amount`, v)" />
              </div>
              <div class="gt-a51__other-total"><span>合计</span><span class="gt-a51__amt">{{ fmtAmt(getOtherCFTotal(group.id, 'pay')) }}</span></div>
            </div>
          </div>
        </div>
        <el-collapse class="gt-a51__collapse">
          <el-collapse-item title="编制说明">
            <ol class="gt-a51__notes-list">
              <li>收到的保证金/押金列为经营活动收到的其他现金。</li>
              <li>支付的保证金/押金列为经营活动支付的其他现金。</li>
              <li>收到的政府补助（与日常活动相关）列为经营活动收到的其他现金。</li>
              <li>支付的并购咨询费列为投资活动支付的其他现金。</li>
              <li>收到的借款保证金列为筹资活动收到的其他现金。</li>
              <li>支付的融资手续费列为筹资活动支付的其他现金。</li>
              <li>对于无法归入三大类主要项目的现金收支，列入其他项目。</li>
              <li>单项金额重大的其他现金收支应单独披露性质和金额。</li>
              <li>各类其他现金流量合计应与现金流量表列报数核对一致。</li>
            </ol>
          </el-collapse-item>
        </el-collapse>
      </el-tab-pane>
    </el-tabs>

    <!-- Excel Mode -->
    <GtOnlyOfficeSheet v-else :wp-id="props.wpId" sheet-name="A5-1" class="gt-a51__oo" />

    <!-- 会计提示 Drawer -->
    <el-drawer v-model="tipsVisible" title="会计提示" direction="rtl" size="480px">
      <div v-for="(section, idx) in ACCOUNTING_TIPS" :key="idx" class="gt-a51__tip-section">
        <h4>{{ section.title }}</h4>
        <p v-for="(line, li) in section.content" :key="li" class="gt-a51__tip-line">{{ line }}</p>
      </div>
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, toRef, watch, onMounted, onBeforeUnmount, defineAsyncComponent } from 'vue'
import { useA51CashflowAudit, AUDIT_OBJECTIVES, PROGRAM_STEPS, AUDIT_ROWS, RECONCILE_GROUPS, CHECK4_SECTIONS, CHECK5_ROWS, OTHER_CF_GROUPS, ACCOUNTING_TIPS } from './composables/useA51CashflowAudit'
import { useA51EditorMode } from './composables/useA51EditorMode'
import { fmtAmount } from '@/utils/formatters'

const GtOnlyOfficeSheet = defineAsyncComponent(() => import('./GtOnlyOfficeSheet.vue'))

defineOptions({ name: 'GtA51CashflowAudit' })

const props = withDefaults(defineProps<{
  wpId: string
  readonly?: boolean
}>(), { readonly: false })

// ─── Editor Mode ───
const { mode, onlyofficeHealthy, checkHealth, switchToExcel, switchToStructured } = useA51EditorMode()

// ─── Data ───
const {
  lastSavedAt, saveError,
  loadData, refreshData, getField, setField,
  getAuditedAmount, getAuditRow6Amount, getAuditRow8Amount,
  getReconcileTotal, getReconcileDiff, getCheckDiff,
  getOtherCFTotal, programProgress,
  flushPendingSave,
} = useA51CashflowAudit({ wpId: toRef(props, 'wpId') })

// ─── View state ───
const activeTab = ref('program')
const tipsVisible = ref(false)
const viewMode = ref('结构化视图')
const segOpts = computed(() =>
  onlyofficeHealthy.value ? ['结构化视图', 'Excel编辑'] : ['结构化视图'],
)

// Mode switch sync
watch(viewMode, async (val) => {
  if (val === 'Excel编辑') {
    await switchToExcel(() => flushPendingSave())
  } else {
    await switchToStructured(props.wpId, refreshData)
  }
})

// ─── Helpers ───
const fmtAmt = fmtAmount
function safeFloat(v: string | undefined | null): number {
  if (!v) return 0
  const n = parseFloat(v)
  return isNaN(n) ? 0 : n
}

/** Row 8 = SUM(rows 1~7 estimated) */
function check5Row8(): number {
  let sum = 0
  for (let i = 1; i <= 7; i++) sum += safeFloat(getField(`a51-check5-${i}.estimated`))
  return sum
}
/** Row 10 = row8 - row9 */
function check5Row10(): number {
  return check5Row8() - safeFloat(getField('a51-check5-9.estimated'))
}

// Audit table data for el-table :data binding
const auditTableData = computed(() => AUDIT_ROWS)

// ─── Lifecycle ───
onMounted(async () => {
  await loadData(props.wpId)
  await checkHealth()
})
onBeforeUnmount(() => { flushPendingSave() })
</script>

<style scoped>
.gt-a51 { padding: 16px; }
.gt-a51__toolbar { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
.gt-a51__toolbar-right { display: flex; align-items: center; gap: 12px; }
.gt-a51__save-status { font-size: 12px; color: #909399; }

/* Tabs */
.gt-a51__tabs { --el-tabs-header-height: 36px; }

/* Tab 1: 程序表 */
.gt-a51__objectives { display: flex; flex-direction: column; gap: 8px; margin-bottom: 16px; }
.gt-a51__obj-card { background: #ecf5ff; border-radius: 6px; padding: 10px 14px; font-size: var(--wp-font-size, 13px); color: #303133; }
.gt-a51__progress { display: flex; align-items: center; gap: 12px; margin-bottom: 12px; font-size: var(--wp-font-size, 13px); color: #606266; }
.gt-a51__progress .el-progress { flex: 1; max-width: 300px; }
.gt-a51__steps { display: flex; flex-direction: column; gap: 6px; margin-bottom: 16px; }
.gt-a51__step { display: flex; align-items: center; gap: 8px; padding: 6px 8px; border: 1px solid #ebeef5; border-radius: 4px; flex-wrap: wrap; }
.gt-a51__step-id { font-weight: 600; font-size: 12px; color: #409eff; min-width: 32px; }
.gt-a51__step-title { font-size: var(--wp-font-size, 13px); color: #303133; flex: 1; min-width: 180px; }
.gt-a51__step-ctrls { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
.gt-a51__input-xs { width: 80px; }
.gt-a51__input-sm { width: 120px; }
.gt-a51__input-md { width: 160px; }
.gt-a51__approval { display: flex; align-items: center; gap: 8px; padding: 12px; background: #fafafa; border-radius: 6px; font-size: var(--wp-font-size, 13px); }

/* Tab 2: 审定表 */
.gt-a51__audit-table :deep(tr) { &:nth-child(6), &:nth-child(8) { background-color: #f5f7fa; } }
.gt-a51__auto { color: #909399; font-style: italic; }
.gt-a51__audit-note { margin-top: 12px; }
.gt-a51__label { font-size: var(--wp-font-size, 13px); color: #606266; margin-bottom: 4px; display: block; }

/* Tab 3: 勾稽核对 */
.gt-a51__reconcile-card { border: 1px solid #ebeef5; border-radius: 8px; padding: 16px; margin-bottom: 16px; box-shadow: 0 1px 4px rgba(0,0,0,0.04); }
.gt-a51__card-title { margin: 0 0 12px; font-size: 14px; color: #303133; }
.gt-a51__reconcile-summary { margin-top: 8px; display: flex; flex-direction: column; gap: 6px; }
.gt-a51__reconcile-row { display: flex; align-items: center; justify-content: space-between; padding: 4px 8px; font-size: var(--wp-font-size, 13px); }
.gt-a51__amt { font-family: 'Menlo', monospace; text-align: right; }
.gt-a51__amt-input { width: 130px; }
.gt-a51__amt-input :deep(.el-input__inner) { text-align: right; }
.gt-a51__diff-warn { background: #fef0f0; color: #f56c6c; border-radius: 4px; font-weight: 600; }

/* Tab 4 & 5: 核查 */
.gt-a51__check-card { border: 1px solid #ebeef5; border-radius: 8px; padding: 16px; margin-bottom: 16px; }
.gt-a51__diff-red { color: #f56c6c; font-weight: 700; }
.gt-a51__footnote { font-size: 12px; color: #909399; margin-top: 8px; }

/* Tab 6: 其他现金流量 */
.gt-a51__other-card { border: 1px solid #ebeef5; border-radius: 8px; padding: 16px; margin-bottom: 16px; }
.gt-a51__other-layout { display: grid; grid-template-columns: 1fr 1fr; gap: 24px; }
.gt-a51__other-side h5 { font-size: var(--wp-font-size, 13px); color: #606266; margin: 0 0 8px; }
.gt-a51__other-row { display: flex; gap: 8px; margin-bottom: 4px; }
.gt-a51__other-name { flex: 1; }
.gt-a51__other-total { display: flex; justify-content: space-between; padding: 6px 8px; background: #f5f7fa; border-radius: 4px; margin-top: 6px; font-size: var(--wp-font-size, 13px); font-weight: 600; }

/* Collapse & Notes */
.gt-a51__collapse { margin-top: 16px; }
.gt-a51__notes-list { font-size: 12px; color: #606266; padding-left: 20px; margin: 0; line-height: 1.8; }

/* Drawer tips */
.gt-a51__tip-section { margin-bottom: 20px; }
.gt-a51__tip-section h4 { font-size: 14px; color: #303133; margin: 0 0 8px; }
.gt-a51__tip-line { font-size: var(--wp-font-size, 13px); color: #606266; line-height: 1.7; margin: 4px 0; }

/* OO */
.gt-a51__oo { height: calc(100vh - 200px); min-height: 500px; }
</style>
