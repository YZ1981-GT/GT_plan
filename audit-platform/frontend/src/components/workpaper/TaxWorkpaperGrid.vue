<!--
  TaxWorkpaperGrid — 税审底稿的电子表格视图（照 CITAR WorkpaperGrid）。
  CITAR 用 x-data-spreadsheet；本仓已有 Univer（底稿编辑器在用），不另引依赖。
  行为与参考一致：带工具栏 / 网格线 / 右键菜单，可编辑但**不存盘**
  （改动只在内存里，离开页面即丢；存盘需另建表与接口）。
  有样表数据的表（constants/taxWorkpaperGrids/<编号>.json，生成脚本 gen_tax_workpaper_grids.py）按需加载
  （一个编号可有多张工作表，成为底部多个页签），其余给空白表。
  表编号变化时重建实例。
-->
<template>
  <div ref="hostRef" class="gt-twp-grid" :data-testid="testId || 'tax-wp-grid'" />
</template>

<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { createUniver, LocaleType, mergeLocales } from '@univerjs/presets'
import { UniverSheetsCorePreset } from '@univerjs/preset-sheets-core'
// @ts-ignore - locale file has no type declarations
import UniverPresetSheetsCoreZhCN from '@univerjs/preset-sheets-core/lib/locales/zh-CN'
import '@univerjs/preset-sheets-core/lib/index.css'
import { loadTaxWorkpaperGrid, type TaxWorkpaperGridData } from '@/constants/taxWorkpaperGrids'
import { logger } from '@/utils/logger'

const props = defineProps<{
  /** 底稿编号（如 1-02）；也是工作簿 id 的一部分，变化时重建实例 */
  code: string
  /** 工作簿名 */
  name: string
  /**
   * 自定义样表加载函数。缺省按 `code` 取税审底稿样表；
   * 纳税申报表等其他文书传自己的加载函数（返回 null 即给空白表）。
   */
  loader?: (code: string) => Promise<TaxWorkpaperGridData | null>
  /** 测试锚点，缺省 tax-wp-grid */
  testId?: string
}>()

/** 与参考一致：100 行 × 26 列，行高 25、列宽 100 */
const ROW_COUNT = 100
const COLUMN_COUNT = 26

const hostRef = ref<HTMLElement | null>(null)
let univer: { dispose: () => void } | null = null

/**
 * 组装 Univer 工作簿。样表数据是模块缓存里的同一个对象，深拷贝一份再交出去 ——
 * Univer 会就地改传入对象，不拷贝的话编辑会污染缓存，切回来看到的是上次的改动。
 */
function buildWorkbook(code: string, name: string, grid: TaxWorkpaperGridData | null) {
  const sheets: Record<string, unknown> = {}
  const sheetOrder: string[] = []
  if (grid) {
    grid.sheets.forEach((s, i) => {
      const id = `sheet${i}`
      sheetOrder.push(id)
      sheets[id] = { id, defaultColumnWidth: 100, ...structuredClone(s) }
    })
  } else {
    sheetOrder.push('sheet0')
    sheets.sheet0 = {
      id: 'sheet0',
      name: code,
      rowCount: ROW_COUNT,
      columnCount: COLUMN_COUNT,
      defaultRowHeight: 25,
      defaultColumnWidth: 100,
      cellData: {},
    }
  }
  return {
    id: `tax-wp-${code}`,
    name: `${code} ${name}`,
    sheetOrder,
    styles: grid ? structuredClone(grid.styles) : {},
    sheets,
  }
}

function dispose() {
  if (univer) {
    try { univer.dispose() } catch { /* 实例已销毁 */ }
    univer = null
  }
  // Univer 卸载后可能残留 DOM，清空容器防止切表时叠出两张表
  if (hostRef.value) hostRef.value.innerHTML = ''
}

/** 每次挂载递增；样表异步加载回来时若已切到别的表，丢弃这次结果 */
let mountSeq = 0

async function mount() {
  const seq = ++mountSeq
  dispose()
  let grid: TaxWorkpaperGridData | null = null
  try {
    grid = await (props.loader ?? loadTaxWorkpaperGrid)(props.code)
  } catch (e) {
    // 加载失败退回空白表，不让整页白屏
    logger.error('[TaxWorkpaperGrid] 样表加载失败', props.code, e)
  }
  if (seq !== mountSeq) return
  const host = hostRef.value
  if (!host) return
  const { univer: instance, univerAPI } = createUniver({
    locale: LocaleType.ZH_CN,
    locales: { [LocaleType.ZH_CN]: mergeLocales(UniverPresetSheetsCoreZhCN) },
    presets: [UniverSheetsCorePreset({ container: host })],
  })
  univer = instance
  univerAPI.createWorkbook(buildWorkbook(props.code, props.name, grid) as any)
}

onMounted(mount)
watch(() => props.code, mount)
onBeforeUnmount(() => {
  mountSeq++
  dispose()
})
</script>

<style scoped>
/* 控件按容器尺寸绘制，容器必须有确定高度（auto 会算出 0，表格不显示） */
.gt-twp-grid {
  position: relative;
  width: 100%;
  height: 70vh;
  min-height: 420px;
}
</style>
