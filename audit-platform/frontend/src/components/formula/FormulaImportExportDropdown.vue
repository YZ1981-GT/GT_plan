<!--
  FormulaImportExportDropdown — 公式「导入导出▾」下拉（Req 23.1；spec formula-governance-coverage-closure R4 接入）

  两种用法（同一组件，按 mode 出不同菜单）：
  - mode="preset"：公式预设库（平台级，挂在「公式预设库」弹窗）。
      导出模板（首区块 = 编报说明）/ 导出数据（当前页或全部）/ 导入数据（逐条引用校验，悬空的报告并跳过）。
      导入入库仅限可写预设的角色：管理员直接生效，合伙人提交为全局候选待审核；其他角色禁用并写明原因。
  - mode="package"：本项目公式包（挂在公式管理中心顶栏）。
      导出本项目的公式适配 / 把公式包导入为本项目适配（须有本项目公式编辑权限）。

  Spec: .kiro/specs/formula-management-library/  Task: 14.4
  Requirements: 23.1, 23.2, 23.3, 23.4, 23.5
-->
<template>
  <el-dropdown trigger="click" @command="onCommand">
    <el-button size="small" :loading="busy" :data-testid="`fie-${mode}`">
      {{ mode === 'package' ? '📦 公式包 ▾' : '导入导出 ▾' }}
    </el-button>
    <template #dropdown>
      <el-dropdown-menu>
        <template v-if="mode === 'package'">
          <el-dropdown-item command="export-package" :disabled="!projectId">导出本项目公式包</el-dropdown-item>
          <el-dropdown-item command="import-package" :disabled="!projectId || !canEditProject"
            :title="canEditProject ? '' : '当前账号只有公式查看权限，不能导入'">导入公式包到本项目</el-dropdown-item>
        </template>
        <template v-else>
          <el-dropdown-item command="template">导出模板（含编报说明）</el-dropdown-item>
          <el-dropdown-item command="export">导出数据（{{ pageKey || '全部页面' }}）</el-dropdown-item>
          <el-dropdown-item command="import" :disabled="!canImport"
            :title="canImport ? '' : '导入入库仅限管理员 / 合伙人'">导入数据</el-dropdown-item>
        </template>
      </el-dropdown-menu>
    </template>
  </el-dropdown>
  <input ref="fileRef" type="file" accept=".xlsx" hidden @change="onFile" />
  <input ref="packageFileRef" type="file" accept=".json" hidden @change="onPackageFile" />
</template>

<script setup lang="ts">
import { computed, h, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useFormulaImportExport, type FormulaImportResult } from '@/composables/useFormulaImportExport'
import { formulaErrorText, formulaSettingsApi } from '@/composables/formula/useFormulaSettings'
import {
  applyFormulaPackage, buildProjectPackage, describeApplyReport, parseFormulaPackage,
} from '@/composables/formula/formulaPackage'

const props = withDefaults(defineProps<{
  mode?: 'preset' | 'package'
  /** preset：导出数据限定的页面键（scope:key，如 workpaper:D2）；空 = 全部 */
  pageKey?: string
  /** package：目标项目 */
  projectId?: string
  /** preset：当前账号能否导入入库（可写预设的角色） */
  canImport?: boolean
  /** package：当前账号能否改本项目公式 */
  canEditProject?: boolean
}>(), { mode: 'preset', pageKey: '', projectId: '', canImport: false, canEditProject: false })

const emit = defineEmits<{
  /** preset：导入完成（含转候选） */
  imported: [result: FormulaImportResult]
  /** package：写入了哪些公式类别（宿主据此刷新） */
  'package-applied': [domains: string[]]
}>()

const fileRef = ref<HTMLInputElement | null>(null)
const packageFileRef = ref<HTMLInputElement | null>(null)
const ie = useFormulaImportExport()
const packageBusy = ref(false)
const busy = computed(() => ie.loading.value || ie.importing.value || packageBusy.value)

async function onCommand(cmd: string) {
  if (cmd === 'template') await ie.exportTemplate()
  else if (cmd === 'export') await ie.exportData(props.pageKey || undefined)
  else if (cmd === 'import' && props.canImport) fileRef.value?.click()
  else if (cmd === 'export-package') await exportPackage()
  else if (cmd === 'import-package' && props.canEditProject) packageFileRef.value?.click()
}

async function onFile(ev: Event) {
  const input = ev.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) return
  const result = await ie.importData(file)
  if (!result) return
  emit('imported', result)
  if (result.skipped_count > 0) {
    const detail = result.skipped
      .slice(0, 5)
      .map((s) => `第${s.row_number}行 ${s.page_key}/${s.target_cell}：${s.reason}`)
      .join('；')
    ElMessage.warning(`已跳过 ${result.skipped_count} 条悬空/无效公式：${detail}`)
  }
}

function download(text: string, filename: string) {
  const url = URL.createObjectURL(new Blob([text], { type: 'application/json' }))
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
}

async function exportPackage() {
  if (!props.projectId) return
  packageBusy.value = true
  try {
    const { pack, count } = await buildProjectPackage(props.projectId)
    if (!count) {
      ElMessage.info('本项目没有公式适配可导出（全部沿用全局设置 / 系统预设）')
      return
    }
    download(JSON.stringify(pack, null, 2), `公式包_本项目适配_${new Date().toISOString().slice(0, 10)}.json`)
    ElMessage.success(`已导出 ${count} 条本项目公式适配（${Object.keys(pack.domains).length} 类）`)
  } catch (e: any) {
    ElMessage.error(`导出公式包失败：${e?.message || '未知原因'}，未生成文件`)
  } finally {
    packageBusy.value = false
  }
}

async function onPackageFile(ev: Event) {
  const input = ev.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file || !props.projectId) return
  packageBusy.value = true
  try {
    const infos = (await formulaSettingsApi.domains()).domains || []
    const parsed = parseFormulaPackage(await file.text(), infos)
    if ('error' in parsed) { ElMessage.error(parsed.error); return }
    if (!parsed.total) { ElMessage.warning(['公式包里没有可导入的公式', ...parsed.warnings].join('；')); return }
    const lines = Object.entries(parsed.domains).map(([k, d]) =>
      `${infos.find((i) => i.key === k)?.label || k}：${d.slot_count} 条${d.scope ? `（适用范围 ${d.scope}）` : ''}`)
    try {
      // 弹窗内容不在本组件渲染上下文里，scoped 样式匹配不到 ⇒ 换行用内联样式
      await ElMessageBox.confirm(
        h('div', { style: 'white-space: pre-line;' }, [...lines, ...parsed.warnings].join('\n')
          + '\n\n将写为本项目适配（与本项目现有定义相同的不写；适用范围不同的整类跳过）。'),
        '导入公式包到本项目',
        { confirmButtonText: '确认导入', cancelButtonText: '取消', type: 'info' },
      )
    } catch { return }
    const report = await applyFormulaPackage(props.projectId, parsed.domains, infos)
    const text = describeApplyReport(report)
    if (report.failed.length || report.skipped.length) ElMessage.warning(text)
    else ElMessage.success(text)
    if (report.writtenDomains.length) emit('package-applied', report.writtenDomains)
  } catch (e) {
    ElMessage.error(formulaErrorText(e, '导入公式包失败'))
  } finally {
    packageBusy.value = false
  }
}
</script>
