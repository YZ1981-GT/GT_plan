<template>
  <el-alert
    v-if="loaded"
    :type="result?.passed ? 'success' : 'warning'"
    show-icon
    :closable="false"
    class="completeness-banner"
  >
    <template #title>
      <div class="completeness-banner__row">
        <span v-if="result?.passed">三件套完整性检查通过</span>
        <span v-else>
          交付物完整性未通过
          <template v-if="result?.warnings?.length">
            — {{ result.warnings.join('；') }}
          </template>
        </span>
        <el-button
          v-if="!result?.passed"
          size="small"
          type="primary"
          text
          @click="refresh"
        >
          重新检查
        </el-button>
      </div>
    </template>

    <!-- 需求 11.3：三件套各自绑定的数据快照三列对照，并指出滞后的类别 -->
    <div v-if="showTrioTable" class="completeness-banner__trio">
      <table class="trio-table">
        <thead>
          <tr>
            <th v-for="row in trioRows" :key="`h-${row.docType}`">{{ row.label }}</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td v-for="row in trioRows" :key="`v-${row.docType}`">
              <span v-if="row.short" class="trio-table__hash">快照 {{ row.short }}</span>
              <span v-else class="trio-table__muted">尚未生成</span>
            </td>
          </tr>
          <tr>
            <td v-for="row in trioRows" :key="`s-${row.docType}`">
              <el-tag v-if="row.lagging" size="small" type="warning">滞后</el-tag>
              <el-tag v-else-if="row.short && isMajority(row)" size="small" type="success">
                最新
              </el-tag>
              <span v-else class="trio-table__muted">—</span>
            </td>
          </tr>
          <tr>
            <td v-for="row in trioRows" :key="`a-${row.docType}`">
              <el-button
                v-if="row.lagging || trioAmbiguous"
                size="small"
                type="primary"
                text
                @click="emit('regenerate', row.docType)"
              >
                重新生成这一类
              </el-button>
            </td>
          </tr>
        </tbody>
      </table>
      <p v-if="trioAmbiguous" class="completeness-banner__hint">
        三类绑定的数据快照互不相同，无法判定哪一类滞后，建议三类一并重新生成。
      </p>
    </div>
  </el-alert>
</template>

<script setup lang="ts">
/**
 * 交付物完整性横幅。
 *
 * Spec: deliverable-lineage-wiring-and-writeback-closure — 需求 11.3 / 11.4
 * 原实现只把 `trio_message` 拼进一句 warnings 文字，看不出**哪一类**滞后；
 * 这里改为三列对照（各自 tb_hash 短标识 + 滞后徽标 + 重新生成入口）。
 */
import { computed, onMounted, ref, watch } from 'vue'
import { fetchCompleteness, type CompletenessResult } from '@/services/deliverableApi'
import { shortHash } from './deliverableLineageLabels'

const props = defineProps<{
  projectId: string
  year: number
}>()

const emit = defineEmits<{ (e: 'regenerate', docType: string): void }>()

const result = ref<CompletenessResult | null>(null)
const loaded = ref(false)

/** 三件套固定顺序与中文名（与后端 `_TRIO_LABEL` 同口径；禁裸英文 doc_type） */
const TRIO: ReadonlyArray<{ docType: string; label: string }> = Object.freeze([
  { docType: 'audit_report', label: '审计报告' },
  { docType: 'financial_report', label: '财务报表' },
  { docType: 'disclosure_notes', label: '财务报表附注' },
])

const trioAmbiguous = computed(() => result.value?.trio_ambiguous === true)

/**
 * 只在**不一致**时展开三列对照 —— 一致时横幅保持单行（平台 UI 铁律：
 * 状态面板禁空洞卡片，改紧凑单行 bar）。
 */
const showTrioTable = computed(
  () => result.value != null && result.value.trio_consistent === false,
)

const trioRows = computed(() =>
  TRIO.map((t) => {
    const hash = result.value?.trio_tb_hashes?.[t.docType] ?? null
    return {
      docType: t.docType,
      label: t.label,
      hash,
      short: shortHash(hash),
      lagging: (result.value?.trio_lagging ?? []).includes(t.docType),
    }
  }),
)

function isMajority(row: { hash: string | null }): boolean {
  const majority = result.value?.trio_majority_tb_hash
  return !!majority && row.hash === majority
}

async function refresh() {
  try {
    result.value = await fetchCompleteness(props.projectId, props.year)
  } catch {
    result.value = null
  } finally {
    loaded.value = true
  }
}

watch(
  () => [props.projectId, props.year],
  () => refresh(),
)

onMounted(refresh)

defineExpose({ refresh })
</script>

<style scoped>
.completeness-banner {
  margin-bottom: 12px;
}
.completeness-banner__row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}
.completeness-banner__trio {
  margin-top: 8px;
}
.trio-table {
  border-collapse: collapse;
  font-size: 12px;
}
.trio-table th,
.trio-table td {
  border: 1px solid var(--el-border-color-lighter);
  padding: 4px 10px;
  text-align: left;
  white-space: nowrap;
}
.trio-table th {
  background: var(--el-fill-color-light);
  font-weight: 600;
}
.trio-table__hash {
  font-family: var(--el-font-family-monospace, monospace);
}
.trio-table__muted {
  color: var(--el-text-color-placeholder);
}
.completeness-banner__hint {
  margin: 6px 0 0;
  color: var(--el-text-color-regular);
}
</style>
