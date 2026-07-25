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
import { DisplayPrefs_Key } from '../composables/displayPrefsKey'
import { useDisplayPrefsStore } from '@/stores/displayPrefs'

const props = defineProps<{
  /** 四表取数来源行 */
  sources: FourTableSourceRow[]
  /** 提取截止日（资产负债表日） */
  asOf?: string
  /** 只读态 */
  isReadonly?: boolean
  /** 该 sheet 是否已被用户手工编辑过（有持久化数据）→ 提示重新取数会覆盖 */
  hasManualData?: boolean
}>()

const emit = defineEmits<{ (e: 're-extract'): void }>()

const displayPrefs = inject(DisplayPrefs_Key, null) ?? useDisplayPrefsStore()

const totalEnding = computed(() =>
  props.sources.reduce((s, r) => s + (Number(r.ending) || 0), 0),
)
const totalOpening = computed(() =>
  props.sources.reduce((s, r) => s + (Number(r.opening) || 0), 0),
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
