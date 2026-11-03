<template>
  <div class="tw-view tw-tokens">
    <TaxReturnCatalog
      :active-code="activeCode"
      :filed="filed"
      :readonly="!year"
      :saving="marksSaving"
      @open="openSheet"
      @toggle="toggleFiled"
    />

    <main class="tw-view__content">
      <p v-if="yearLoading" class="tr-empty">正在读取项目信息…</p>
      <p v-else-if="!year" class="tr-empty">项目未设置审核年度，请先在项目信息里填写</p>
      <TaxReturnSheetPanel
        v-else
        ref="panelRef"
        :code="activeCode"
        :project-id="projectId"
        :year="year"
        :filed="activeCode === TAX_RETURN_INDEX.cover.code || !!filed[activeCode]"
        :exporting="exporting"
        @export="exportXlsx"
      />
    </main>
  </div>
</template>

<script setup lang="ts">
/**
 * 汇算申报表（CITAR 鉴证报告 · 汇算申报表）：左为「表单」目录（是否填报），右为单表。
 * 「是否填报」存为样表「表单」页 C 列（√ / □），与申报表其他手工值同一保存机制（编号 TR-FORMS）。
 */
import { computed, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useCitarProject } from '@/citar/useCitarProject'
import { downloadTaxAssurance } from '@/citar/taxAssuranceApi'
import { handleApiError } from '@/utils/errorHandler'
import type { TaxSheetResult } from '@/views/tax-workpapers/taxWorkpaperApi'
import TaxReturnCatalog from './TaxReturnCatalog.vue'
import TaxReturnSheetPanel from './TaxReturnSheetPanel.vue'
import { fetchTaxReturnSheet, saveTaxReturnSheet } from './taxReturnApi'
import { FILED_MARK, TAX_RETURN_INDEX, UNFILED_MARK } from './taxReturnSheets'

defineOptions({ name: 'TaxReturnView' })

const ACTIVE_PREFIX = 'gt.tax-return-active.'
const { projectId, year, yearLoading } = useCitarProject()
const panelRef = ref<{ dirty: boolean } | null>(null)
const activeCode = ref(TAX_RETURN_INDEX.cover.code)
const exporting = ref(false)

// ── 是否填报 ──
const marks = ref<TaxSheetResult | null>(null)
const marksSaving = ref(false)
const formsSheet = TAX_RETURN_INDEX.formsSheet

function markOf(cellRef: string): string | null {
  const v = marks.value?.parts.find(p => p.source === formsSheet)?.values[cellRef]
  return v && 's' in v ? v.s.trim() : null
}

const filed = computed<Record<string, boolean>>(() => {
  const out: Record<string, boolean> = {}
  for (const f of TAX_RETURN_INDEX.forms) {
    const mark = markOf(f.markRef)
    out[f.code] = mark === null ? f.filed : mark === FILED_MARK
  }
  return out
})

async function loadMarks() {
  marks.value = null
  if (!year.value || !projectId.value) return
  try {
    marks.value = await fetchTaxReturnSheet(projectId.value, year.value, TAX_RETURN_INDEX.formsCode)
  } catch (e) {
    handleApiError(e, '读取申报表目录')
  }
}

async function toggleFiled(code: string, value: boolean) {
  const form = TAX_RETURN_INDEX.forms.find(f => f.code === code)
  if (!form || !year.value || !marks.value) return
  marksSaving.value = true
  try {
    // 只存与样表默认不同的标记；全部标记一次提交（同一编号的手工值整体保存）
    const inputs: Record<string, string> = {}
    for (const f of TAX_RETURN_INDEX.forms) {
      const want = f.code === code ? value : filed.value[f.code]
      if (want !== f.filed) inputs[f.markRef] = want ? FILED_MARK : UNFILED_MARK
    }
    marks.value = await saveTaxReturnSheet(projectId.value, year.value, TAX_RETURN_INDEX.formsCode, marks.value.version, { [formsSheet]: inputs })
    ElMessage.success(`${code} 已${value ? '勾选填报' : '取消填报'}`)
  } catch (e: any) {
    if (e?.response?.status === 409) {
      ElMessage.warning('表单已被他人修改，已重新读取')
      await loadMarks()
    } else {
      handleApiError(e, '保存是否填报')
    }
  } finally {
    marksSaving.value = false
  }
}

// ── 切表 ──
function loadActive(pid: string): string {
  try {
    const saved = sessionStorage.getItem(ACTIVE_PREFIX + pid)
    if (saved && (saved === TAX_RETURN_INDEX.cover.code || TAX_RETURN_INDEX.forms.some(f => f.code === saved))) return saved
  } catch {
    // sessionStorage 不可用时回到封面
  }
  return TAX_RETURN_INDEX.cover.code
}

async function openSheet(code: string) {
  if (code === activeCode.value) return
  if (panelRef.value?.dirty) {
    try {
      await ElMessageBox.confirm('本表有未保存的修改，离开后修改会丢失。', '提示', {
        confirmButtonText: '离开', cancelButtonText: '留下', type: 'warning',
      })
    } catch {
      return
    }
  }
  activeCode.value = code
  try {
    sessionStorage.setItem(ACTIVE_PREFIX + projectId.value, code)
  } catch {
    // 记不住上次的表不影响使用
  }
}

async function exportXlsx() {
  if (!year.value) return
  exporting.value = true
  try {
    await downloadTaxAssurance('taxReturnExport', projectId.value, year.value, `${year.value}年度企业所得税年度纳税申报表.xlsx`)
  } catch (e) {
    handleApiError(e, '导出申报表')
  } finally {
    exporting.value = false
  }
}

watch(projectId, (pid) => { activeCode.value = loadActive(pid) }, { immediate: true })
watch([projectId, year], loadMarks, { immediate: true })
</script>

<style scoped src="../tax-workpapers/taxWorkpaperTokens.css"></style>

<style scoped>
.tw-view {
  display: flex;
  flex: 1 1 auto;
  min-width: 0;
  background: var(--tw-page-bg);
  font-family: "Microsoft YaHei", "PingFang SC", system-ui, sans-serif;
}

.tw-view__content {
  flex: 1 1 auto;
  min-width: 0;
  padding: 20px 24px;
}

.tr-empty {
  padding: 48px 24px;
  text-align: center;
  font-size: var(--gt-font-size-sm);
  color: var(--tw-text-muted);
}
</style>
