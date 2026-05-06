/**
 * API 服务层统一入口
 *
 * 按业务域组织：
 *   commonApi    — 通用/跨模块（项目/人员/知识库/回收站/看板/批注/论坛/打卡等）
 *   auditApi     — 审计核心（试算表/调整分录/重要性/未更正错报/报表/附注/审计报告/导出）
 *   workpaperApi — 底稿管理（模板/取数公式/底稿CRUD/QC/复核批注/抽样/WOPI）
 *   consolidationApi — 合并报表（范围/试算/内部交易/少数股东/商誉/外币/附注/报表）
 *   collaborationApi — 协作功能（归档/审计发现/审计日志/PBC/函证/风险/工时等）
 *   staffApi     — 人员管理（人员库/委派/工时）
 *   aiApi        — AI功能（聊天/合同分析/证据链/OCR/底稿填充等）
 *   aiModelApi   — AI模型配置
 *   pmApi        — 项目经理看板
 *   partnerApi   — 合伙人看板
 *   qcDashboardApi — 质控看板
 *
 * 用法：
 *   import { listProjects, listUsers } from '@/services/commonApi'
 *   import { getTrialBalance } from '@/services/auditPlatformApi'
 */

export * as commonApi from './commonApi'
export * as auditApi from './auditPlatformApi'
export * as workpaperApi from './workpaperApi'
export * as consolidationApi from './consolidationApi'
export * as collaborationApi from './collaborationApi'
export * as staffApi from './staffApi'
export * as aiApi from './aiApi'
export * as aiModelApi from './aiModelApi'
export * as pmApi from './pmApi'
export * as partnerApi from './partnerApi'
export * as qcDashboardApi from './qcDashboardApi'
export { API } from './apiPaths'
