/**
 * 从列描述构建 el-table-v2 VirtualColumn（浏览模式只读展示）
 */
import { h } from 'vue'
import type { VirtualColumn } from '@/composables/useVirtualTable'

export function virtualTextCol(key: string, title: string, width: number): VirtualColumn {
  return {
    key,
    dataKey: key,
    title,
    width,
    cellRenderer: ({ cellData }) => h('span', {}, cellData == null || cellData === '' ? '-' : String(cellData)),
  }
}

export function virtualNumCol(
  key: string,
  title: string,
  width: number,
  fmt: (v: number) => string = (v) => (v === 0 ? '-' : String(v)),
): VirtualColumn {
  return {
    key,
    dataKey: key,
    title,
    width,
    align: 'right',
    cellRenderer: ({ cellData }) => h('span', {}, fmt(Number(cellData) || 0)),
  }
}

export function virtualSelectCol(key: string, title: string, width: number): VirtualColumn {
  return virtualTextCol(key, title, width)
}
