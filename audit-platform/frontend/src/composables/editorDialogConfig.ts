/**
 * editorDialogConfig — 底稿编辑器 template dialog 配置驱动 [V3 Req 12.1.4]
 *
 * 骨架已建 + 示范提取，完整瘦身需独立 Sprint。
 * 将 WorkpaperEditor.vue 中 ~400 行 template dialog 配置抽离为声明式数组，
 * 配合通用 TemplateDialogRunner 组件实现配置驱动渲染。
 *
 * @example
 * import { TEMPLATE_DIALOGS, getDialogByKey } from './editorDialogConfig'
 * const dialog = getDialogByKey('aging')
 */

export interface TemplateDialogConfig {
  /** 唯一标识 */
  key: string
  /** 对话框标题 */
  title: string
  /** 动态组件名（lazy import 路径） */
  componentPath: string
  /** 触发条件（按钮 key / cycle 事件） */
  triggers: string[]
  /** 所属循环 */
  cycle?: string
  /** 对话框宽度 */
  width?: string
  /** 是否需要 append-to-body */
  appendToBody?: boolean
  /** 是否全屏 */
  fullscreen?: boolean
}

/**
 * 底稿编辑器所有 template dialog 配置
 * 完整迁移时从 WorkpaperEditor.vue 模板中提取所有 el-dialog 配置
 */
export const TEMPLATE_DIALOGS: TemplateDialogConfig[] = [
  // ─── D 循环 ───
  {
    key: 'sampling',
    title: '抽样计算',
    componentPath: '@/components/workpaper/SamplingDialog.vue',
    triggers: ['button:sampling', 'cycle:D'],
    cycle: 'D',
    width: '800px',
    appendToBody: true,
  },
  {
    key: 'aging',
    title: '账龄分析',
    componentPath: '@/components/workpaper/AgingAnalysisDialog.vue',
    triggers: ['button:aging', 'cycle:D'],
    cycle: 'D',
    width: '900px',
    appendToBody: true,
  },
  // ─── F 循环 ───
  {
    key: 'impairment',
    title: '减值测试',
    componentPath: '@/components/workpaper/ImpairmentDialog.vue',
    triggers: ['button:impairment', 'cycle:F'],
    cycle: 'F',
    width: '800px',
    appendToBody: true,
  },
  {
    key: 'valuationSample',
    title: '计价测试抽样',
    componentPath: '@/components/workpaper/ValuationSampleDialog.vue',
    triggers: ['cycle:F'],
    cycle: 'F',
    width: '700px',
    appendToBody: true,
  },
  // ─── H 循环 ───
  {
    key: 'depreciationCalc',
    title: '折旧计算',
    componentPath: '@/components/workpaper/DepreciationCalcDialog.vue',
    triggers: ['button:depreciation', 'cycle:H'],
    cycle: 'H',
    width: '800px',
    appendToBody: true,
  },
  {
    key: 'assetImpairment',
    title: '资产减值',
    componentPath: '@/components/workpaper/AssetImpairmentDialog.vue',
    triggers: ['cycle:H'],
    cycle: 'H',
    width: '800px',
    appendToBody: true,
  },
  // ─── I 循环 ───
  {
    key: 'amortizationCalc',
    title: '摊销计算',
    componentPath: '@/components/workpaper/AmortizationCalcDialog.vue',
    triggers: ['cycle:I'],
    cycle: 'I',
    width: '800px',
    appendToBody: true,
  },
  {
    key: 'goodwillImpairment',
    title: '商誉减值',
    componentPath: '@/components/workpaper/GoodwillImpairmentDialog.vue',
    triggers: ['cycle:I'],
    cycle: 'I',
    width: '800px',
    appendToBody: true,
  },
  // ─── G 循环 ───
  {
    key: 'fairValueTest',
    title: '公允价值测试',
    componentPath: '@/components/workpaper/FairValueTestDialog.vue',
    triggers: ['cycle:G'],
    cycle: 'G',
    width: '800px',
    appendToBody: true,
  },
  {
    key: 'eclCalc',
    title: 'ECL 计算',
    componentPath: '@/components/workpaper/ECLCalcDialog.vue',
    triggers: ['cycle:G'],
    cycle: 'G',
    width: '800px',
    appendToBody: true,
  },
  // ─── N 循环 ───
  {
    key: 'incomeTaxCalc',
    title: '所得税计算',
    componentPath: '@/components/workpaper/IncomeTaxCalcDialog.vue',
    triggers: ['cycle:N'],
    cycle: 'N',
    width: '900px',
    appendToBody: true,
  },
]

/** 按 key 查找 dialog 配置 */
export function getDialogByKey(key: string): TemplateDialogConfig | undefined {
  return TEMPLATE_DIALOGS.find((d) => d.key === key)
}

/** 按 cycle 过滤 dialog 配置 */
export function getDialogsByCycle(cycle: string): TemplateDialogConfig[] {
  return TEMPLATE_DIALOGS.filter((d) => d.cycle === cycle)
}

/** 按 trigger 查找 dialog 配置 */
export function getDialogByTrigger(trigger: string): TemplateDialogConfig | undefined {
  return TEMPLATE_DIALOGS.find((d) => d.triggers.includes(trigger))
}
