<script setup lang="ts">
/**
 * E1FourTableSourcePanel.vue — E1「四表取数」公式管理面板
 *
 * 展示当前明细 sheet 从四表库（tb_balance 叶子子科目）自动提取的取数来源：
 * - 来源科目（code + name）
 * - 取数公式（TB('code','期末余额') / TB('code','期初余额')）
 * - 提取的期初 / 本期增加 / 本期减少 / 期末金额
 *
 * 提供「🔄 重新从四表取数」：以四表库最新数据覆盖当前明细行（persist）。
 * 让审计师在底稿当前页面即可「看到」每个数字的四表来源与公式，并可「编辑」
 * （明细表行本身可编辑；此处可一键重新取数刷新）。
 */
import { computed } from 'vue'
import { inject } from 'vue'
import type { FourTableSourceRow } from '../composables/e1FourTablePrefill'
import type { E1AccountPrefill } from '../composables/e1BankAccountPrefill'
import { assignedAccounts } from '../composables/e1BankAccountPrefill'
import { DisplayPrefs_Key } from '../composables/displayPrefsKey'
import { useDisplayPrefsStore } from '@/stores/displayPrefs'
import {
  negativeBalanceHint,
  pickNegativeAccounts,
  pickNegativeSlots,
} from '../composables/e1NegativeBalance'

const props = defineProps<{
  /** 四表取数来源行 */
  sources: FourTableSourceRow[]
  /** 提取截止日（资产负债表日） */
  asOf?: string
  /** 只读态 */
  isReadonly?: boolean
  /** 该 sheet 是否已被用户手工编辑过（有持久化数据）→ 提示重新取数会覆盖 */
  hasManualData?: boolean
  /**
   * 账户级取数溯源（`tb_aux_balance` 的「银行账户」维度）。
   *
   * 🔴 可选 —— 只有 E1-3 / E1-10 传。不传时账户级两块完全不渲染；
   * 传了但账户为空时显示「本项目无账户级明细，已退回叶子口径」
   * （「未传」与「传了但空」是两种状态，不可混为一谈）。
   */
  accounts?: E1AccountPrefill
}>()

const emit = defineEmits<{ (e: 're-extract'): void }>()

const displayPrefs = inject(DisplayPrefs_Key, null) ?? useDisplayPrefsStore()

const totalEnding = computed(() =>
  props.sources.reduce((s, r) => s + (Number(r.ending) || 0), 0),
)
const totalOpening = computed(() =>
  props.sources.reduce((s, r) => s + (Number(r.opening) || 0), 0),
)

// ─── 账户级取数溯源 ─────────────────────────────────────────────────────────

/** 槽键 → 中文标签（中文只在此处一份，勿在模板里写字面量）。 */
const SLOT_LABELS: Readonly<Record<string, string>> = {
  bank: '银行存款',
  other: '其他货币资金',
  finance_co: '存放财务公司款项',
}

/** `parsed_level` → 含义（数据质量指标）。 */
const LEVEL_LABELS: Readonly<Record<string, string>> = {
  '1': '账号 + 银行名',
  '2': '仅账号（未解析出银行名）',
  '3': '降级：账号取自辅助项名称',
}

/** 已归属账户（不含 unassigned），带槽标签。 */
const accountRows = computed(() => {
  const p = props.accounts
  if (!p) return []
  return assignedAccounts(p)
})

const unassignedRows = computed(() => props.accounts?.accounts.unassigned ?? [])

const accountCount = computed(
  () => accountRows.value.length + unassignedRows.value.length,
)

/** 传了 accounts 但一个账户都没有 ⇒ 已退回叶子口径（要如实告知，不是缺陷）。 */
const accountsEmpty = computed(() => !!props.accounts && accountCount.value === 0)

/** 各槽勾稽（只列后端产出条目 —— 两侧都有数据的槽才有勾稽意义）。 */
const reconcileRows = computed(() => {
  const rec = props.accounts?.reconcile ?? {}
  return Object.entries(rec).map(([slot, r]) => ({
    slot,
    label: SLOT_LABELS[slot] || slot,
    accountSum: Number(r.account_sum) || 0,
    leafSum: Number(r.leaf_sum) || 0,
    diff: Number(r.diff) || 0,
    ok: r.ok === true,
  }))
})

/** `parsed_level` 分布（按 level 升序）。 */
const levelRows = computed(() => {
  const dist = props.accounts?.meta.parsed_level_dist ?? {}
  return Object.entries(dist)
    .map(([level, count]) => ({
      level,
      label: LEVEL_LABELS[level] || `level ${level}`,
      count: Number(count) || 0,
    }))
    .sort((a, b) => a.level.localeCompare(b.level))
})

/** level 3 占比 —— 高时提示该客户 `aux_dimensions_raw` 格式与预期不同。 */
const level3Ratio = computed(() => {
  const total = levelRows.value.reduce((s, r) => s + r.count, 0)
  if (!total) return 0
  return (levelRows.value.find(r => r.level === '3')?.count ?? 0) / total
})

const showLevelWarn = computed(() => level3Ratio.value >= 0.5)

/** 是否有勾稽不平的槽（决定整块告警色）。 */
const hasReconcileDiff = computed(() => reconcileRows.value.some(r => !r.ok))

/**
 * 期末为负的账户与语义槽（Property 27）。
 *
 * 🔴 **判定逻辑在 `e1NegativeBalance.ts` 一份** —— 本组件与审定表共用同一真源，
 * 不在此处再写一遍阈值/过滤（抄第二份必漂移）。
 *
 * 🔴 **不经 `abs()`** —— 负数是「贷方性质」的真实语义（实测项目 `a7fc75e5`
 * 银行存款期末 −297,771,168.89，账户级与叶子勾稽 diff=0 ⇒ 取数是对的），
 * 套 `abs()` 会让「叶子和 == 父额」勾稽从 0 变成两倍差异。故只**提示**、不改值。
 */
const negativeAccounts = computed(() =>
  pickNegativeAccounts(
    accountRows.value.map(x => x.row),
    unassignedRows.value,
  ),
)

/** 期末为负的语义槽（账户级合计或叶子合计任一为负即提示）。 */
const negativeSlots = computed(() => pickNegativeSlots(reconcileRows.value))

/**
 * 负余额提示文案 —— **取自纯函数真源**（模板里不得抄一份，否则双真源）。
 * 无负余额时返回的 subject 为空，故用 `negativeAccounts/negativeSlots` 判是否渲染。
 */
const negativeHint = computed(() =>
  negativeBalanceHint(negativeSlots.value, negativeAccounts.value),
)

const accountTotalClosing = computed(() =>
  accountRows.value.reduce((s, x) => s + (Number(x.row.closing) || 0), 0),
)
const unassignedTotalClosing = computed(() =>
  unassignedRows.value.reduce((s, r) => s + (Number(r.closing) || 0), 0),
)
</script>

<template>
  <details class="e1-ft-source-panel" open>
    <summary>
      🔗 四表取数（公式管理）
      <el-tag size="small" type="success" effect="plain">{{ sources.length }} 条来源</el-tag>
      <span v-if="asOf" class="ft-asof">截止 {{ asOf }}</span>
    </summary>

    <div class="ft-body">
      <div class="ft-hint">
        以下数据自动提取自四表库（试算余额表 tb_balance 的叶子子科目，借正贷负）。
        每行金额可在上方明细表中直接编辑；如四表库数据更新，可点「重新取数」以最新四表数据覆盖。
      </div>

      <el-table :data="sources" border size="small" style="width: 100%" max-height="320">
        <el-table-column label="来源科目" min-width="220">
          <template #default="{ row }">
            <span class="ft-code">{{ row.code }}</span>
            <span class="ft-name">{{ row.name }}</span>
          </template>
        </el-table-column>
        <el-table-column label="取数公式（期末）" min-width="200">
          <template #default="{ row }">
            <code class="ft-formula">{{ row.formula }}</code>
          </template>
        </el-table-column>
        <el-table-column label="期初" width="130" align="right">
          <template #default="{ row }">{{ displayPrefs.fmtAmount(row.opening) }}</template>
        </el-table-column>
        <el-table-column label="本期增加(借)" width="140" align="right">
          <template #default="{ row }">{{ displayPrefs.fmtAmount(row.increase) }}</template>
        </el-table-column>
        <el-table-column label="本期减少(贷)" width="140" align="right">
          <template #default="{ row }">{{ displayPrefs.fmtAmount(row.decrease) }}</template>
        </el-table-column>
        <el-table-column label="期末" width="140" align="right">
          <template #default="{ row }">{{ displayPrefs.fmtAmount(row.ending) }}</template>
        </el-table-column>
      </el-table>

      <div class="ft-footer">
        <span class="ft-total">四表提取合计：期初 {{ displayPrefs.fmtAmount(totalOpening) }} ｜ 期末 {{ displayPrefs.fmtAmount(totalEnding) }}</span>
        <el-button
          v-if="!isReadonly"
          type="primary"
          plain
          size="small"
          @click="emit('re-extract')"
        >🔄 重新从四表取数</el-button>
      </div>
      <div v-if="hasManualData" class="ft-warn">
        ⚠️ 本表已有编制数据；「重新取数」将以四表库最新数据覆盖当前明细行。
      </div>

      <!-- ── 账户级取数溯源（tb_aux_balance 的「银行账户」维度）── -->
      <div v-if="accountsEmpty" class="ft-acct-empty">
        本项目无账户级明细（辅助余额表无「银行账户」维度数据），已退回叶子科目口径取数。
      </div>
      <div v-else-if="accountCount > 0" class="ft-acct">
        <div class="ft-acct-head">
          <span class="ft-acct-title">🏦 账户级取数溯源</span>
          <el-tag size="small" type="success" effect="plain">{{ accountCount }} 个账户</el-tag>
          <el-tag
            v-for="lv in levelRows"
            :key="lv.level"
            size="small"
            :type="lv.level === '1' ? 'success' : lv.level === '2' ? 'warning' : 'danger'"
            effect="plain"
          >{{ lv.label }} {{ lv.count }}</el-tag>
          <el-tag
            v-if="hasReconcileDiff"
            size="small"
            type="danger"
          >勾稽不平</el-tag>
        </div>

        <div class="ft-hint">
          账户明细来自辅助余额表（<code>tb_aux_balance</code> 的「银行账户」维度）。
          客户的银行存款科目在试算余额表里不分户，逐户列示与账户完整性核对只能取自该维度。
        </div>

        <div v-if="showLevelWarn" class="ft-warn">
          ⚠️ 超过半数账户的辅助维度未能解析出银行名（降级取辅助项名称作账号），
          请核对该客户导出的「辅助项组合」格式，并逐行确认账号列。
        </div>

        <!-- 负余额提示（Property 27：如实显示不取绝对值，只提示不改值） -->
        <div
          v-if="negativeAccounts.length || negativeSlots.length"
          class="ft-warn ft-negative"
        >
          ⚠️ {{ negativeHint }}
        </div>

        <!-- 各槽勾稽：账户合计 vs 叶子合计 -->
        <el-table
          v-if="reconcileRows.length"
          :data="reconcileRows"
          border
          size="small"
          style="width: 100%"
        >
          <el-table-column prop="label" label="语义槽" min-width="150" />
          <el-table-column label="账户级合计（期末）" width="170" align="right">
            <template #default="{ row }">{{ displayPrefs.fmtAmount(row.accountSum) }}</template>
          </el-table-column>
          <el-table-column label="叶子科目合计（期末）" width="180" align="right">
            <template #default="{ row }">{{ displayPrefs.fmtAmount(row.leafSum) }}</template>
          </el-table-column>
          <el-table-column label="差异" width="150" align="right">
            <template #default="{ row }">
              <el-tag :type="row.ok ? 'success' : 'danger'" size="small" effect="plain">
                {{ displayPrefs.fmtAmount(row.diff) }}
              </el-tag>
            </template>
          </el-table-column>
        </el-table>

        <!-- 账户明细 -->
        <el-table
          :data="accountRows"
          border
          size="small"
          style="width: 100%; margin-top: 8px"
          max-height="260"
        >
          <el-table-column label="语义槽" width="150">
            <template #default="{ row }">{{ SLOT_LABELS[row.slot] || row.slot }}</template>
          </el-table-column>
          <el-table-column label="开户银行" min-width="180">
            <template #default="{ row }">
              <span v-if="row.row.bank_name">{{ row.row.bank_name }}</span>
              <span v-else class="ft-muted">（未解析出银行名）</span>
            </template>
          </el-table-column>
          <el-table-column label="银行账号" min-width="180">
            <template #default="{ row }">
              <span class="ft-code">{{ row.row.account_no }}</span>
            </template>
          </el-table-column>
          <el-table-column label="科目" width="120">
            <template #default="{ row }">
              <span class="ft-code">{{ row.row.account_code }}</span>
            </template>
          </el-table-column>
          <el-table-column label="币种" width="90">
            <template #default="{ row }">{{ row.row.currency || '—' }}</template>
          </el-table-column>
          <el-table-column label="期末" width="150" align="right">
            <template #default="{ row }">{{ displayPrefs.fmtAmount(row.row.closing) }}</template>
          </el-table-column>
          <el-table-column label="解析" width="90" align="center">
            <template #default="{ row }">
              <el-tag
                size="small"
                :type="row.row.parsed_level === 1 ? 'success' : row.row.parsed_level === 2 ? 'warning' : 'danger'"
                effect="plain"
              >L{{ row.row.parsed_level }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="合并笔数" width="100" align="center">
            <template #default="{ row }">
              <span v-if="row.row.row_count > 1" class="ft-merged">{{ row.row.row_count }}</span>
              <span v-else class="ft-muted">1</span>
            </template>
          </el-table-column>
        </el-table>

        <div class="ft-footer">
          <span class="ft-total">
            账户级提取合计（期末）：{{ displayPrefs.fmtAmount(accountTotalClosing) }}
          </span>
        </div>

        <!-- unassigned 告警：aux 里有账户但科目定位未覆盖 -->
        <div v-if="unassignedRows.length" class="ft-acct-unassigned">
          <div class="ft-warn">
            ⚠️ 有 {{ unassignedRows.length }} 个账户未归属到任何语义槽
            （合计期末 {{ displayPrefs.fmtAmount(unassignedTotalClosing) }}）——
            辅助余额表里有这些账户，但科目语义定位未覆盖其科目码。
            请核对科目表映射；这些账户已计入 E1-10 账户清单以便完整性核对。
          </div>
          <el-table :data="unassignedRows" border size="small" style="width: 100%">
            <el-table-column label="银行账号" min-width="180">
              <template #default="{ row }"><span class="ft-code">{{ row.account_no }}</span></template>
            </el-table-column>
            <el-table-column label="开户银行" min-width="160">
              <template #default="{ row }">{{ row.bank_name || '—' }}</template>
            </el-table-column>
            <el-table-column label="科目" width="130">
              <template #default="{ row }"><span class="ft-code">{{ row.account_code }}</span></template>
            </el-table-column>
            <el-table-column label="期末" width="150" align="right">
              <template #default="{ row }">{{ displayPrefs.fmtAmount(row.closing) }}</template>
            </el-table-column>
          </el-table>
        </div>
      </div>
    </div>
  </details>
</template>

<style scoped>
.e1-ft-source-panel {
  margin-bottom: 12px;
  border: 1px solid #d9ecff;
  border-left: 3px solid #409eff;
  background: #f4f9ff;
  border-radius: 4px;
  padding: 8px 12px;
}
.e1-ft-source-panel summary {
  cursor: pointer;
  font-weight: 600;
  color: #337ecc;
  font-size: var(--wp-font-size, 13px);
  display: flex;
  align-items: center;
  gap: 8px;
}
.ft-asof { font-weight: 400; color: #909399; font-size: 12px; margin-left: auto; }
.ft-body { margin-top: 10px; }
.ft-acct {
  margin-top: 12px;
  padding-top: 10px;
  border-top: 1px dashed #b3d8ff;
}
.ft-acct-head {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 6px;
}
.ft-acct-title { font-weight: 600; color: #337ecc; font-size: var(--wp-font-size, 13px); }
.ft-acct-empty {
  margin-top: 12px;
  padding: 6px 8px;
  border-top: 1px dashed #b3d8ff;
  font-size: 12px;
  color: #909399;
  line-height: 1.6;
}
.ft-acct-unassigned { margin-top: 10px; }
.ft-muted { color: #c0c4cc; }
.ft-merged { color: #e6a23c; font-weight: 600; }
.ft-hint {
  font-size: 12px;
  color: #606266;
  line-height: 1.6;
  margin-bottom: 8px;
}
.e1-ft-source-panel :deep(.el-table) {
  --el-table-font-size: 13px;
  font-size: 13px;
}
.e1-ft-source-panel :deep(.el-table th),
.e1-ft-source-panel :deep(.el-table td),
.e1-ft-source-panel :deep(.el-table .cell) {
  font-size: 13px;
}
.ft-code { font-weight: 600; color: #303133; margin-right: 6px; }
.ft-name { color: #606266; }
.ft-formula {
  font-family: 'Consolas', monospace;
  font-size: 12px;
  color: #409eff;
  background: #ecf5ff;
  padding: 1px 6px;
  border-radius: 3px;
}
.ft-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-top: 8px;
  flex-wrap: wrap;
  gap: 8px;
}
.ft-total { font-weight: 600; color: #303133; font-size: var(--wp-font-size, 13px); }
.ft-warn { margin-top: 6px; font-size: 12px; color: #e6a23c; }
</style>
