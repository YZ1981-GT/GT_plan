/**
 * 公式全局设置 / 本项目适配 / 待确认 / 公式模板（spec formula-global-settings-sync，design §10 / §16.4）。
 *
 * 权限由后端判定：读全局 = 登录；写全局、发布、审核候选 = admin；项目侧读 = 项目 readonly、写 = 项目 edit；
 * 模板改名 / 删除 / 发布 = 所有者或 admin。前端只做展示层门控。
 */

/** 全局设置（`/api/formula-settings`） */
export const formulaSettings = {
  /** GET 公式域清单（含作用范围选项、是否已接入、当前用户是否 admin） */
  domains: '/api/formula-settings/domains',
  /** GET `?scope=` 某域某作用范围的全局定义（无全局时为系统预设） */
  global: (domain: string) => `/api/formula-settings/${domain}/global`,
  /** POST 发布前影响预览（只读） */
  globalPreview: (domain: string) => `/api/formula-settings/${domain}/global/preview`,
  /** POST 发布（带决策与请求号） */
  globalPublish: (domain: string) => `/api/formula-settings/${domain}/global/publish`,
  /** GET `?domain=&scope=&status=` 发布记录 / 全局候选 */
  publishes: '/api/formula-settings/publishes',
  /** POST 全局候选的影响预览（admin） */
  candidatePreview: (publishId: string) => `/api/formula-settings/candidates/${publishId}/preview`,
  /** POST 审核全局候选（admin，通过即发布） */
  candidateReview: (publishId: string) => `/api/formula-settings/candidates/${publishId}/review`,
  /** GET `?source=&q=` 全平台校对规则目录（只读；不带参数只给来源清单） */
  checkRules: '/api/formula-catalog/check-rules',
} as const

/** 本项目适配 / 待确认 / 应用到其他（`/api/projects/{pid}/formula-settings`） */
export const projectFormulaSettings = {
  /** GET 本项目待确认事项 */
  pending: (pid: string) => `/api/projects/${pid}/formula-settings/pending`,
  /** POST 处理待确认（采用新上游 / 保留本项目 / 手工修改） */
  resolve: (pid: string) => `/api/projects/${pid}/formula-settings/pending/resolve`,
  /** GET `?domain=` 「应用到指定项目」可选目标 */
  applyTargets: (pid: string) => `/api/projects/${pid}/formula-settings/apply-targets`,
  /** GET 本项目某域全部公式位的有效定义与层级 */
  effective: (pid: string, domain: string) => `/api/projects/${pid}/formula-settings/${domain}/effective`,
  /** PUT 保存本项目适配；DELETE `?slot_key=` 恢复为全局 */
  overrides: (pid: string, domain: string) => `/api/projects/${pid}/formula-settings/${domain}/overrides`,
  /** POST 应用范围预览（设为全局 / 提交候选 / 应用到指定项目） */
  applyPreview: (pid: string, domain: string) => `/api/projects/${pid}/formula-settings/${domain}/apply-preview`,
  /** POST 应用范围执行 */
  apply: (pid: string, domain: string) => `/api/projects/${pid}/formula-settings/${domain}/apply`,
} as const

/** 公式模板（`/api/formula-templates`） */
export const formulaTemplates = {
  /** GET 可见模板列表；POST 新建模板 */
  list: '/api/formula-templates',
  /** GET 详情；PUT 改名 / 共享范围；DELETE 删除（有订阅时 409） */
  detail: (id: string) => `/api/formula-templates/${id}`,
  /** GET 两个模板版本的规范化差异 */
  diff: (id: string) => `/api/formula-templates/${id}/diff`,
  /** POST 回滚预览 / 回滚到历史快照（生成新版本） */
  rollbackPreview: (id: string) => `/api/formula-templates/${id}/rollback-preview`,
  rollback: (id: string) => `/api/formula-templates/${id}/rollback`,
  /** GET 版本历史 */
  versions: (id: string) => `/api/formula-templates/${id}/versions`,
  /** GET 订阅项目（所有者 / admin） */
  subscribers: (id: string) => `/api/formula-templates/${id}/subscribers`,
  /** POST 发布新版本前的订阅者影响预览 */
  publishPreview: (id: string) => `/api/formula-templates/${id}/publish-preview`,
  /** POST 发布新版本 */
  publish: (id: string) => `/api/formula-templates/${id}/publish`,
  /** POST 设为全局的影响预览（admin） */
  promotePreview: (id: string) => `/api/formula-templates/${id}/promote-preview`,
  /** POST 设为全局（admin）/ 提交全局候选（其他人） */
  promote: (id: string) => `/api/formula-templates/${id}/promote`,
} as const

/** 项目订阅公式模板（`/api/projects/{pid}/formula-templates`） */
export const projectFormulaTemplates = {
  /** GET 本项目当前订阅（每个域最多一个） */
  subscriptions: (pid: string) => `/api/projects/${pid}/formula-templates/subscriptions`,
  subscribePreview: (pid: string) => `/api/projects/${pid}/formula-templates/subscribe-preview`,
  subscribe: (pid: string) => `/api/projects/${pid}/formula-templates/subscribe`,
  unsubscribePreview: (pid: string) => `/api/projects/${pid}/formula-templates/unsubscribe-preview`,
  unsubscribe: (pid: string) => `/api/projects/${pid}/formula-templates/unsubscribe`,
} as const
