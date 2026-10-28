/**
 * 离屏同步覆盖清单（spec note-pull-header-formula-closure R2.3 / note-pull-followup-closure R1.4）：只许变短，逐码写明原因。
 *
 * 附注刷新时，已接入离屏同步的底稿按披露 Tab 同一套代码现算披露表同步到附注；未接入的底稿只能在底稿附注披露页
 * 保存一次才进附注（刷新提示会点名）。每接入一张底稿：在 `components/workpaper/headless/providers/` 本组登记文件里登记、
 * 从下面清单删掉这一项。底稿 → 附注章节映射真源 = `backend/data/note_workpaper_sync_registry.json`。
 */
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'
import { headlessDisclosureWpCodes } from '../noteHeadlessDisclosure'

/** M6 / M9 / M10：Tab 的 `useDisclosureAutoSync(sync)` 传参错误、页面没有手动同步按钮 ⇒ 同步函数从未被调用、载荷从未经真实数据检验 */
const M_NEVER_SYNCED = '载荷从未发出过（Tab 自动同步传参错误、无手动同步按钮）；'

/** 未接入的底稿 → 原因（只许删条目） */
const NOT_YET_HEADLESS: Readonly<Record<string, string>> = {
  E1: '受限资金表取数依赖宿主逐 sheet 下发的 html_data.restricted_prefill，受限行 / 说明 / 外币行的加载内联在 Tab 且被源码守卫'
    + '钉在组件内，外币段推送还要逐条回报 row_scope_unresolved；待抽出后接入（主表由公式推送写入）',
  F1: '披露 Tab 的数据由宿主装配后注入：GtF1Prepayment 先建 useF1AgingScope（表级账龄枚举覆盖 > 项目配置 > 3 年段，带保存回调）、'
    + '再建 useF1CrossSheet，经 props.crossSheet 与 provide(\'f1AgingScope\') 传给 Tab，Tab 内再套 useF1DisclosureListed / Soe；'
    + '离屏要复刻宿主这条装配链才同口径 —— 待把宿主装配抽成工厂（宿主与离屏共用）后接入',
  G7: '同步不只推附注：成功后把本次推送的表记成基线（previouslySyncedTables）并写回底稿，下次同步据此算 _removed_table_keys；'
    + '离屏不写底稿 ⇒ 基线与附注实际状态脱节，之后底稿页同步会漏删 / 误删子表；另走批量端点一次写 五、18 与 七、1 等多章节'
    + '（R8.1）—— 待基线改为由附注侧记录后接入',
  H1: '载荷的适用准则取宿主传入的项目模板类型 / 报表口径（props.templateType / reportScope → resolveH1CurrentStandardFromProject，'
    + '并据此拦截口径不符的同步），离屏上下文没有这两项；读回与审定 / 明细取数散在 1300 余行组件内，同步后另推受限资产段 —— 待抽出后接入',
  H3: '读回链路断：Tab 用自建的 useH3FormData（只解构 getValue / setValue，从不加载）读已保存披露行，Map 恒空 ⇒ 重新打开底稿'
    + '后已保存的行读不回、同步恒推 0（探针实测：已存「按成本计量」行挂载后同步仍为 0）；离屏同口径只有全 0 载荷 —— 待 Tab 改为'
    + '从宿主回复读回后接入',
  K3: '与 M1 同写 五、42 / 八、42 的「应付股利」表（后写覆盖先写）；上市 K3 没有「超过 1 年未支付的应付股利」行时把该表放进'
    + ' _removed_table_keys，删的是 M1 名下的表（Tab 同步同样如此）—— 应付股利写权待定（应付利息已按 L 循环裁决移交 L2），定了再接',
  L4: '快照不来自底稿回复：Tab 不读回已保存的核对表 / 附注文本（只在本次会话内存），buildL4SyncPayload 从不传主表 / 增减变动行，'
    + '离屏同口径只有空载荷（写入只会把章节标成已同步）；待 Tab 补读回与主表取数后接入',
  L5: '快照不来自底稿回复：Tab 不读回已保存的分类表 / 未确认融资费用（只在本次会话内存），新挂载 Tab 同步恒推全 0 的长期应付款'
    + '主表；八、47 一年内到期 builder 无 Tab 调用；待 Tab 补读回后接入',
  M6: M_NEVER_SYNCED + '行结构与附注模板不一致：五、61 / 八、63 模板是「调整前上期末未分配利润 / 调整期初合计数 / 调整后期初'
    + ' / 本期净利润 / 盈余公积弥补亏损 … / 期末未分配利润」，Tab 是另一套行名（含「一、」编号与「其中：子公司盈余公积转入」），'
    + '且快照剔掉「调整后期初未分配利润」「可供分配利润」两行小计 —— 离屏写入会把模板表换成这套结构；按模板对齐行后接入',
  M9: M_NEVER_SYNCED + '上市 五、57 两张表（资产负债表 / 利润表口径）推同一份数据（Tab 注明「当前 UI 未区分」），行名带底稿批注'
    + '（「1. 重新计量设定受益计划变动额（J2）」）、不带「一、二、」分组行；两表口径拆开、行名按模板对齐后接入',
  M10: M_NEVER_SYNCED + '上市 五、54 三张表里「基本情况」只有金额、其余列全空，「持有者信息」推空表，变动表数量列恒 0'
    + '（Tab 注明「待 Tab 增强后填充」）—— 离屏写入会用空列覆盖模板；Tab 补齐基本情况 / 持有者录入后接入',
}

function registryCodes(): string[] {
  const path = resolve(__dirname, '../../../../../../backend/data/note_workpaper_sync_registry.json')
  const doc = JSON.parse(readFileSync(path, 'utf-8')) as { entries: Array<{ wp_code: string }> }
  return [...new Set(doc.entries.map((e) => e.wp_code))]
}

describe('附注离屏同步覆盖清单', () => {
  it('注册表里每张底稿要么已接入离屏同步，要么在待接入清单（清单只许变短）', () => {
    const covered = new Set(headlessDisclosureWpCodes())
    const missing = registryCodes().filter((c) => !covered.has(c)).sort()
    expect(missing).toEqual(Object.keys(NOT_YET_HEADLESS).sort())
  })

  it('已接入的底稿都在注册表里（不接入没有附注映射的底稿）', () => {
    const registry = new Set(registryCodes())
    expect(headlessDisclosureWpCodes().filter((c) => !registry.has(c))).toEqual([])
    expect(registry.size).toBeGreaterThan(70)
  })

  it('仍未接入的底稿逐码写明具体原因（不许用「待接入」类笼统标签占位）', () => {
    expect(Object.entries(NOT_YET_HEADLESS).filter(([, why]) => !why.trim() || /^待接入/.test(why) || why.length < 40))
      .toEqual([])
  })

  it('清单只许变短：note-pull-followup-closure 收尾时 11 张（E1 F1 G7 H1 H3 K3 L4 L5 M6 M9 M10）', () => {
    expect(Object.keys(NOT_YET_HEADLESS).length).toBeLessThanOrEqual(11)
  })
})
