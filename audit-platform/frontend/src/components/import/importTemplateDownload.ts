/**
 * 导入弹窗「下载导入模板」的下载计划解析（纯函数）
 *
 * 背景（adjustment-import-export-contract Task 1.5 / Requirement 4）：
 * 调整分录有两个模板入口——
 *   - 工具栏：`GET /api/projects/{pid}/adjustments/export-template`
 *     项目感知富模板（4 sheet：关注事项 / AJE模板 / RJE模板 / 项目科目库，
 *     E 列科目下拉 + D/F/G/H 编码名称报表项目联动）
 *   - 导入弹窗：`GET /api/import-templates/{importType}/download`
 *     通用裸模板（10 列，无项目科目库 sheet、无下拉、无联动）
 * 两者必填列集合兼容（都能导入），但从弹窗下载的用户拿不到下拉 → 手打科目名易错。
 *
 * 故 `importType === 'adjustments'` 且有项目上下文（projectId + year）时，
 * 弹窗内下载改走项目感知富模板；否则降级通用裸模板并提示无下拉。
 *
 * 抽为纯函数便于单测（不挂载组件）。
 */
import { adjustments as P_adj } from '@/services/apiPaths/accounting'

export interface TemplateDownloadPlan {
  /** 下载 URL（相对路径，走 axios 带鉴权头） */
  url: string
  /** 下载文件名 */
  filename: string
  /**
   * 是否为项目感知富模板（含项目科目库 sheet / 科目下拉 / 编码名称联动）。
   * false 表示走通用裸模板，调用方应提示「无科目下拉，请核对科目编码/名称」。
   */
  rich: boolean
}

export interface TemplateDownloadContext {
  /** 导入类型（adjustments / report / workpaper / staff / trial_balance ...） */
  importType: string
  /** 类型中文名（用于裸模板文件名，保持既有命名口径） */
  typeLabel: string
  /** 项目 ID（props 优先，其次 route.params.projectId） */
  projectId?: string | null
  /** 审计年度 */
  year?: number | null
}

/** 通用裸模板下载端点 */
function bareTemplateUrl(importType: string): string {
  return `/api/import-templates/${importType}/download`
}

/**
 * 解析「下载导入模板」的下载计划。
 *
 * - `adjustments` + 有项目上下文（projectId 且 year）→ 项目感知富模板
 *   （`template_type` 不传，由后端按项目 `template_type` 派生国企版/上市版，
 *    避免弹窗内选错版本；文件名沿用工具栏含年度的命名口径）
 * - 其余情况（含无项目上下文、其他 importType）→ 通用裸模板，
 *   文件名保持既有 `${typeLabel}导入模板.xlsx`
 */
export function resolveTemplateDownloadPlan(ctx: TemplateDownloadContext): TemplateDownloadPlan {
  const { importType, typeLabel, projectId, year } = ctx

  if (importType === 'adjustments' && projectId && year) {
    return {
      url: `${P_adj.exportTemplate(projectId)}?year=${year}`,
      filename: `调整分录导入模板_${year}.xlsx`,
      rich: true,
    }
  }

  return {
    url: bareTemplateUrl(importType),
    filename: `${typeLabel}导入模板.xlsx`,
    rich: false,
  }
}

/** 降级到裸模板时的提示文案（调整分录专用；其他类型本就只有裸模板不提示） */
export const BARE_TEMPLATE_WARNING = '当前无项目上下文，下载的是通用模板：无科目下拉，请核对科目编码/名称'
