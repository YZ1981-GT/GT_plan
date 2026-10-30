/**
 * queryTemplateScope.ts — 查询模板的可见范围（前端展示与提交侧；advanced-query-linkage-closure 任务 28 / 29，ADR-AQL-11）
 *
 * 从页面版 `CustomQueryTab.vue` 挪出，页面版模板列表与「保存为模板」对话框（`QueryTemplateSaveDialog.vue`，页面版与
 * 弹窗 💾 共用）一处定义。与后端 `TemplateScopeAdapter` 同源：历史 `global` / `personal` 只作为输入接受，展示恒为规范值；
 * 前端只给「仅我可见 / 指定项目共享 / 公开」三档，`team` 只作历史兼容显示。
 */

export type TemplateScope = 'private' | 'team' | 'project' | 'public'

const TEMPLATE_SCOPE_ALIASES: Readonly<Record<string, TemplateScope>> = {
  global: 'public',
  personal: 'private',
}

export const TEMPLATE_SCOPE_LABELS: Readonly<Record<TemplateScope, string>> = {
  private: '仅我可见',
  team: '团队共享',
  project: '指定项目共享',
  public: '公开',
}

/** 需要分享权限的范围：至少有一个可编辑项目才可选（后端对「指定项目共享」的每个目标逐项目鉴权） */
export const SHARE_REQUIRED_SCOPES: readonly TemplateScope[] = ['team', 'project', 'public']

/** 保存对话框里可选的三档（ADR-AQL-11 D8） */
export const SAVABLE_SCOPES: readonly TemplateScope[] = ['private', 'project', 'public']

export function normalizeTemplateScope(scope?: string | null): string {
  const raw = String(scope ?? '').trim().toLowerCase()
  return TEMPLATE_SCOPE_ALIASES[raw] ?? raw
}

export function templateScopeLabel(scope?: string | null): string {
  const canonical = normalizeTemplateScope(scope) as TemplateScope
  return TEMPLATE_SCOPE_LABELS[canonical] ?? '未知'
}
