/**
 * S33 应对14号公告核查程序 Bundle — Tab & Sub-Sheet 映射表
 *
 * 来源：Phase0 双源核对，源模板 openpyxl 读取 + design.md 交叉验证
 * 产出日期：2026-07（Task 1 of s33-announcement14-bundle spec）
 *
 * 结构：9 核查底稿 Tab，每个 Tab 对应一个 S33-x 底稿
 *   - programSheet: 核查程序表 sheet 名（主体，GtAProgramConsole 渲染）
 *   - tipSheet: 提示 sheet（部分底稿有，顶部可折叠区块嵌入）
 *   - hiddenVariantSheet: 隐藏程序表变体（仅 S33-4 有，默认渲染可见版，切换入口）
 *
 * Requirements: 3.1, 3.3, 3.4
 */

export interface S33TabDef {
  /** Tab id，对应 wp_code（如 'S33-1'） */
  id: string
  /** Tab 标签简称（核查底稿名称） */
  label: string
  /** 底稿编码 */
  wpCode: string
  /** 程序表 sheet 名（源模板中实际 sheet name） */
  programSheet: string
  /** 提示 sheet 名（可选，顶部 details 折叠区块） */
  tipSheet?: string
  /** 隐藏程序表变体 sheet 名（可选，如 S33-4 的完整版） */
  hiddenVariantSheet?: string
}

/**
 * 9 核查底稿完整 Tab 配置
 *
 * 数据来源：openpyxl 读取源模板 S33-1~9.xlsx（2025年修订版）
 * GT_Custom 为系统元数据 sheet，不纳入用户可见 Tab 映射
 *
 * 特殊说明：
 *   - S33-3 程序表 sheet 名为 "S33-3"（无"程序表"后缀）
 *   - S33-5 程序表 sheet 名为 "S33-5（IB5）核查程序"
 *   - S33-6 程序表 sheet 名为 "S33-6（IB6）核查程序"
 *   - S33-4 含隐藏变体 "S33-4(IB4)程序表-隐"（state=hidden, 92x10, 完整版）
 *     可见版为 "S33-4(IB4)程序表"（state=visible, 53x11, 精简版）
 */
export const S33_ANN14_TABS: S33TabDef[] = [
  {
    id: 'S33-1',
    label: '财务报告内部控制制度',
    wpCode: 'S33-1',
    programSheet: 'S33-1程序表',
  },
  {
    id: 'S33-2',
    label: '财务与非财务信息印证',
    wpCode: 'S33-2',
    programSheet: 'S33-2程序表',
  },
  {
    id: 'S33-3',
    label: '盈利异常增长和异常交易',
    wpCode: 'S33-3',
    programSheet: 'S33-3',
    tipSheet: '提示',
  },
  {
    id: 'S33-4',
    label: '关联方关系及其交易',
    wpCode: 'S33-4',
    programSheet: 'S33-4(IB4)程序表',
    tipSheet: '提示',
    hiddenVariantSheet: 'S33-4(IB4)程序表-隐',
  },
  {
    id: 'S33-5',
    label: '收入及毛利率',
    wpCode: 'S33-5',
    programSheet: 'S33-5（IB5）核查程序',
  },
  {
    id: 'S33-6',
    label: '主要客户和供应商',
    wpCode: 'S33-6',
    programSheet: 'S33-6（IB6）核查程序',
  },
  {
    id: 'S33-7',
    label: '存货及其他资产',
    wpCode: 'S33-7',
    programSheet: 'S33-7程序表',
    tipSheet: '提示',
  },
  {
    id: 'S33-8',
    label: '现金收付交易',
    wpCode: 'S33-8',
    programSheet: 'S33-8程序表',
    tipSheet: '提示',
  },
  {
    id: 'S33-9',
    label: '财务异常信息',
    wpCode: 'S33-9',
    programSheet: 'S33-9程序表',
    tipSheet: '提示',
  },
]

/** 所有 S33 wp_code 集合（用于 skip 映射校验） */
export const S33_WP_CODES = S33_ANN14_TABS.map((t) => t.wpCode) as readonly string[]

/** 含提示 sheet 的底稿编码集合 */
export const S33_WITH_TIPS = S33_ANN14_TABS
  .filter((t) => t.tipSheet)
  .map((t) => t.wpCode) as readonly string[]

/** 含隐藏程序表变体的底稿编码集合（目前仅 S33-4） */
export const S33_WITH_HIDDEN_VARIANT = S33_ANN14_TABS
  .filter((t) => t.hiddenVariantSheet)
  .map((t) => t.wpCode) as readonly string[]
