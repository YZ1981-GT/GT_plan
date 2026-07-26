<script setup lang="ts">
/**
 * H1FourTableSourcePanel — H1-2 明细「四表取数（公式管理）」来源面板
 *
 * 展示 H1-2 明细行的四表来源（tb_balance 叶子科目按分类聚合）：
 *   来源科目码 / 取数公式 / 原值期初·增·减·期末 / 累计折旧期末 / 减值期末
 * 并提供「🔄 重新从四表取数」（二次确认；覆盖取数行、保留手工新增行）。
 *
 * 宁缺勿造（Req8.1）：四表库无资产卡片维度，资产编号/取得日期/年限/残值率等
 * 一律不由取数产生，需台账导入或手工补录 —— 面板明示该边界。
 *
 * Spec: .kiro/specs/h1-four-table-extraction/  Requirements: 7.1, 7.2, 7.3
 */
import { computed, inject } from 'vue'
import { ElMessageBox } from 'element-plus'
import type { H1FourTablePrefill } from '../../composables/h1FourTablePrefill'
import { DisplayPrefs_Key } from '../../composables/displayPrefsKey'
import { useDisplayPrefsStore } from '@/stores/displayPrefs'

const props = defineProps<{
  /** 后端 render 注入的四表取数载荷（灰度关闭时为 null） */
  prefill: H1FourTablePrefill | null
  isReadonly?: boolean
  /** 明细表当前是否已有数据（有则提示重新取数会覆盖取数行） */
  hasManualData?: boolean
}>()

const emit = defineEmits<{ (e: 're-extract'): void }>()

const displayPrefs = inject(DisplayPrefs_Key, null) ?? useDisplayPrefsStore()

const rows = computed(() => props.prefill?.detail?.rows ?? [])
const totals = computed(() => props.prefill?.detail?.totals ?? { cost: 0, dep: 0, impair: 0 })
const counterpart = computed(() => props.prefill?.counterpart ?? null)
const ledger = computed(() => props.prefill?.ledger_movement ?? null)
const needsReviewCount = computed(() => rows.value.filter((r) => r.needs_review).length)

async function onReExtract() {
  try {
    await ElMessageBox.confirm(
      '将以四表库（tb_balance）最新数据覆盖本表的「取数行」，手工新增行会保留。是否继续？',
      '重新从四表取数',
      { type: 'warning', confirmButtonText: '重新取数', cancelButtonText: '取消' },
    )
  } catch {
    return
  }
  emit('re-extract')
}
</script>

<template>
  <details v-if="prefill" class="h1-ft-source-panel" open>
    <summary>
      🔗 四表取数（公式管理）
      <el-tag size="small" type="success" effect="plain">{{ rows.length }} 条来源</el-tag>
      <el-tag v-if="needsReviewCount" size="small" type="warning" effect="plain">
        {{ needsReviewCount }} 项分类待复核
      </el-tag>
      <span class="ft-src">来源：{{ prefill.detail?.source || 'tb_balance' }}</span>
    </summary>

    <div class="ft-body">
      <div class="ft-hint">
        下表金额自动提取自四表库（试算余额表 tb_balance 的<strong>叶子科目</strong>，父级科目不重复累加），
        按固定资产类别聚合；备抵段（累计折旧/减值）发生额已按方向归一。
        <strong>资产编号、取得日期、使用年限、残值率等卡片信息四表库无对应维度，需由台账导入或手工补录。</strong>
      </div>

      <el-empty v-if="!rows.length" description="四表库未取到固定资产科目余额（1601/1602/1603），请先导入余额表" :image-size="60" />

      <el-table v-else :data="rows" border size="small" style="width:100%" max-height="320">
        <el-table-column label="类别" min-width="130">
          <template #default="{ row }">
            <span class="ft-cat">{{ row.category }}</span>
            <el-tag v-if="row.needs_review" size="small" type="warning" effect="plain">待复核</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="来源科目" min-width="160">
          <template #default="{ row }">
            <span class="ft-code">{{ (row.source_codes || []).join(' / ') || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="取数公式（期末）" min-width="220">
          <template #default="{ row }">
            <code class="ft-formula">{{ row.formula || '—' }}</code>
          </template>
        </el-table-column>
        <el-table-column label="原值期初" width="130" align="right">
          <template #default="{ row }">{{ displayPrefs.fmtAmount(row.cost?.begin) }}</template>
        </el-table-column>
        <el-table-column label="原值增加(借)" width="130" align="right">
          <template #default="{ row }">{{ displayPrefs.fmtAmount(row.cost?.debit) }}</template>
        </el-table-column>
        <el-table-column label="原值减少(贷)" width="130" align="right">
          <template #default="{ row }">{{ displayPrefs.fmtAmount(row.cost?.credit) }}</template>
        </el-table-column>
        <el-table-column label="原值期末" width="130" align="right">
          <template #default="{ row }">{{ displayPrefs.fmtAmount(row.cost?.end) }}</template>
        </el-table-column>
        <el-table-column label="累计折旧期末" width="130" align="right">
          <template #default="{ row }">{{ displayPrefs.fmtAmount(row.dep?.end) }}</template>
        </el-table-column>
        <el-table-column label="减值期末" width="120" align="right">
          <template #default="{ row }">{{ displayPrefs.fmtAmount(row.impair?.end) }}</template>
        </el-table-column>
      </el-table>

      <div class="ft-footer">
        <span class="ft-total">
          四表提取合计：原值 {{ displayPrefs.fmtAmount(totals.cost) }} ｜ 累计折旧 {{ displayPrefs.fmtAmount(totals.dep) }} ｜ 减值 {{ displayPrefs.fmtAmount(totals.impair) }}
        </span>
        <el-button
          v-if="!isReadonly && rows.length"
          type="primary"
          plain
          size="small"
          @click="onReExtract"
        >🔄 重新从四表取数</el-button>
      </div>

      <div v-if="hasManualData && rows.length" class="ft-warn">
        ⚠️ 本表已有编制数据；「重新取数」只覆盖标注为「{{ '四表取数(tb_balance)' }}」的行，手工新增行保留。
      </div>
      <div v-if="ledger && !ledger.available" class="ft-note">
        序时账：未取到 1601 本期发生额（本期无分录或序时账未导入），本期增减核对无法自动执行。
      </div>
      <div v-if="counterpart && !counterpart.available" class="ft-note">
        折旧费用归属：{{ counterpart.reason }}
      </div>
    </div>
  </details>
</template>

<style scoped>
.h1-ft-source-panel {
  margin-bottom: 12px;
  border: 1px solid #d9ecff;
  border-left: 3px solid #409eff;
  background: #f4f9ff;
  border-radius: 4px;
  padding: 8px 12px;
}
.h1-ft-source-panel summary {
  cursor: pointer;
  font-weight: 600;
  color: #337ecc;
  font-size: 13px;
  display: flex;
  align-items: center;
  gap: 8px;
}
.ft-src { font-weight: 400; color: #909399; font-size: 12px; margin-left: auto; }
.ft-body { margin-top: 10px; }
.ft-hint { font-size: 12px; color: #606266; line-height: 1.6; margin-bottom: 8px; }
.h1-ft-source-panel :deep(.el-table),
.h1-ft-source-panel :deep(.el-table th),
.h1-ft-source-panel :deep(.el-table td),
.h1-ft-source-panel :deep(.el-table .cell) { font-size: 13px; }
.h1-ft-source-panel :deep(.el-table td.is-right .cell) {
  white-space: nowrap;
  font-variant-numeric: tabular-nums;
}
.ft-cat { font-weight: 600; color: #303133; margin-right: 6px; }
.ft-code { color: #606266; font-family: 'Consolas', monospace; font-size: 12px; }
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
.ft-total { font-weight: 600; color: #303133; font-size: 13px; }
.ft-warn { margin-top: 6px; font-size: 12px; color: #e6a23c; }
.ft-note { margin-top: 6px; font-size: 12px; color: #909399; }
</style>
