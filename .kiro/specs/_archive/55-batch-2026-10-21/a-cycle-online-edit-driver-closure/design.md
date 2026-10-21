# 设计：A 循环在线编辑驱动收口

> 关联：#[[file:.kiro/specs/a-cycle-online-edit-driver-closure/requirements.md]]

## §0 现状 grep 确认（设计前必做，逐项现算）

| 事实 | 现算结果 | 来源 |
|---|---|---|
| A entries capability | `single_onlyoffice`（manifest 91 条该值） | `workpaperSyncManifest.generated.ts` |
| single_onlyoffice 是否支持 oo | 是，`single_onlyoffice: ['oo']` | `workpaperSyncModeStorage.ts:63` |
| switchToOnlyOffice capability 守卫 | `supportedModesForCapability(cap).includes('oo')` → A 通过 | `useWorkpaperSyncBridge.ts:429` |
| flushHtml 404 容错 | 已有（catch 返回空投影） | 各 A 宿主 flushHtml |
| 守卫识别 driver 的规则 | 模块体含 `switchToOnlyOffice(` → driver；宿主调 `\b<导出名>\s*\(` → 被驱动；固定点闭包 | `bridgeMaterializeDriven.spec.ts drivingWrappers()` |
| 参照 driver | `useGRenderModeSwitch`（G，带 managed/legacy 分派）/ `useHSyncMode`（H，整册四分支，更贴近 A） | sync/ + composables/ |

## §1 17 宿主分类（现算，含模板渲染方式）

| 类 | 宿主 | 在线编辑渲染 | mode 形态 | 预生成 | 结论 |
|---|---|---|---|---|---|
| **A（14）** | A101 A111 A112 A115 A121 A171 A1721 A1731 A173 A174 A176 A182 A271 A81 A91 | `<WorkpaperSyncEditorHost v-if="syncOoDescriptor">` + fallback | `ref<'html'\|'docx'>` + `el-segmented v-model=mode` | 无（A176 有 generate-docx/sync-from-docx 自定义流，纳入适配） | 接 driver |
| **B（1）** | A177 | 同上，外层多 `ooGenerating`/`ooReady` | `ref('结构化视图')` 中文串 + `@change=handleModeChange` | 有：generate-docx→ooReady | 接 driver，保留预生成 |
| **C（1）** | A38 | **`<GtOnlyOfficeSheet whole-workbook>`**（legacy 整册） | `activeMode` ref + 自定义 watch | docxDirty | 删死桥（见 §4） |

> A38 的 `syncBridge` / `syncOoDescriptor` / `WorkpaperSyncEditorHost` import 现算
> **零引用**（模板只渲染 `GtOnlyOfficeSheet`，syncOoDescriptor 不出现在模板）⇒ 纯死代码。

## §2 driver 设计：`sync/useARenderModeSwitch.ts`

对标 `useHSyncMode`，**裁掉 A 不需要的**：
- 去掉 `hManagedSheetOf` / `isManagedSheet` / `legacyMode` / `sheetKey` 派生 —— A 循环
  整册单一 OO 文档，没有「一册多 sheet、部分受管」的问题。整个 entry 要么 html 要么 docx。
- 保留：健康（`fetchOnlyOfficeHealthy` + TTL + 竞态 await 兜底）、四分支保存、
  fail-visible `lastNotice`、`syncHostRef`（forceSave）。

### 签名
```ts
export type ARenderMode = 'html' | 'docx'
export interface ASyncEditorHostRef { forceSave: () => Promise<{ operationId: string }> }
export interface UseARenderModeSwitchOptions {
  readonly entryId: string
  readonly wpId: Ref<string>
  readonly projectId: Ref<string>
  readonly isReadonly: Ref<boolean>
  readonly flushHtml: () => Promise<WorkpaperSyncFlushResult>
  readonly reloadHtml: (minimumRevision: number) => Promise<void>
  /** 切 docx 前的可 await flush（宿主的 flushPendingSaves）。 */
  readonly flushBeforeSwitch?: () => void | Promise<void>
  /** B 类（A177）：切 docx 前先生成 Word，返回 false 则中止切换。 */
  readonly beforeEnterOo?: () => Promise<boolean>
  /** 切回 html 后的额外清理（A177 的 ooReady=false 等）。 */
  readonly afterLeaveOo?: () => void | Promise<void>
}
export interface UseARenderModeSwitch {
  readonly renderMode: WritableComputedRef<ARenderMode>  // v-model 直接绑
  readonly modeOptions: ComputedRef<{label:string;value:ARenderMode;disabled:boolean}[]>
  readonly descriptor: ComputedRef<...>   // 模板 v-if
  readonly busy: ComputedRef<boolean>
  readonly syncStateTag: ComputedRef<{text:string;type:...}>
  readonly syncHostRef: Ref<ASyncEditorHostRef|null>
  readonly syncBridge: WorkpaperSyncBridge  // 模板 :bridge
  readonly lastNotice: Ref<...|null>
}
```

### switchMode 逻辑
```
renderMode = computed({
  get: () => bridge.mode.value === 'oo' ? 'docx' : 'html',
  set: (t) => void switchMode(t),
})

switchMode('docx'):
  if isReadonly → return
  if busy && !isAppliedHtmlReturn → return
  健康竞态兜底：!ooHealthy → await checkOoHealth(true)；仍不健康 → lastNotice(warning) return
  if bridge.mode==='oo' → return
  if beforeEnterOo && !(await beforeEnterOo()) → return   // A177 生成失败则不切
  if flushBeforeSwitch → await flushBeforeSwitch()
  try await bridge.switchToOnlyOffice() catch → lastNotice(danger)

switchMode('html'):
  if bridge.mode!=='oo' → persistMode('html'); await afterLeaveOo?(); return
  四分支（§R1.4）… 终了 await afterLeaveOo?()
```

> `disabled: busy`（不 `!ooHealthy`）；applied→html 不被 busy 短路（isAppliedHtmlReturn）。

### 为什么不直接复用 useHSyncMode
H 的 `renderMode` get/set 依赖 `isManagedSheet` 三态，mode 值是 `'onlyoffice'`，且强制
`currentCode` 派生受管判定。A 无 currentCode、无 managed 概念、mode 值 `'docx'`。硬塞
H 会引入「A 永远 isManagedSheet=false 走 legacyMode」的错误分支。故新建 A 专用 driver，
**四分支/健康/fail-visible 逐条照抄 H 的已验证实现**（H 注释里写明的 D4 六类 bug 规避
全部继承），只去掉 sheet 分派。

## §3 A 类 / B 类宿主接线（每宿主最小 diff）

A 类（以 A91 为模板，14 个同构）：
```
// 删：const mode = ref<'html'|'docx'>('html'); const modeOptions = ref([...]);
//     watch(mode, ...) 只 flush 不驱动的那段；checkOOHealth（driver 接管）
const a = useARenderModeSwitch({
  entryId: _ENTRY_ID, wpId: toRef(props,'wpId'), projectId: toRef(props,'projectId'),
  isReadonly: toRef(props,'readonly'),
  flushHtml: <原宿主 flushHtml 内联体搬进来，或保留宿主内并传引用>,
  reloadHtml: async () => { await loadData(props.wpId) },
  flushBeforeSwitch: () => flushPendingSaves(),
})
// 模板：<el-segmented v-model="a.renderMode" :options="a.modeOptions" />
//       v-if a.renderMode==='html' → 结构化；v-else →
//       <WorkpaperSyncEditorHost ref="a.syncHostRef... " v-if="a.descriptor" :descriptor="a.descriptor" :bridge="a.syncBridge" />
```
> `syncHostRef` 用法：模板 `:ref="(el)=>a.syncHostRef.value=el"` 或宿主持 ref 传入。
> 具体接法在实施时按 Vue setup ref 规范定（EditorHost 用 defineExpose 暴露 forceSave）。

B 类（A177）：传 `beforeEnterOo: async () => { await generate-docx; return ok }` +
`afterLeaveOo: () => { ooReady.value=false }`；中文串 mode 由 driver 的 `'html'|'docx'`
取代，`el-segmented` 选项标签仍「结构化视图/在线编辑」。

## §4 A38（C 类）裁决

**现算依据**：A38 docx 分支渲染 `GtOnlyOfficeSheet :whole-workbook`（整册 Excel），
`syncBridge`/`syncOoDescriptor`/`WorkpaperSyncEditorHost` import **零引用**（死代码）。

**裁决：采 (b) 删死桥**。理由：
1. A38 的在线编辑是「整册 Excel」(`whole-workbook`)，而 `WorkpaperSyncEditorHost` +
   bridge 是「单 sheet 受管 + descriptor 身份/revision 协议」路径，两者语义不同；A3-8
   商誉减值底稿用整册 legacy OO 看 Excel 原貌是合理的。
2. 桥建了却从不挂 EditorHost、descriptor 零引用 ⇒ 100% 死代码，删除零行为影响。
3. 守卫 `bridgeBuiltNotDriven` 的本意正是「不该建的桥别建」。删死桥是对的收敛，
   不是「假接过守卫」。

**执行**：删 A38 的 `useWorkpaperSyncBridge` 调用块、`syncOoDescriptor` computed、
`WorkpaperSyncEditorHost` import、`capabilityForEntry`/`readStoreProjection` 若仅此处用
则一并删。保留 `GtOnlyOfficeSheet` docx 分支与 `activeMode`/`docxDirty` 逻辑不变。

> 若实施时发现 A38 的 docx 其实该走受管双向（而非整册），则回到 (a) 接桥并在 tasks
> 注明裁决翻转理由 —— 但现算证据指向 (b)。

## §5 driver 单测与变异（`sync/tests/useARenderModeSwitch.spec.ts`）

- 切 docx：`switchToOnlyOffice` 真被调用（spy）；健康不就绪先 await checkOoHealth 再切。
- 四分支逐条：mock bridge state=applied→reloadAfterApplied；!dirty→leaveWithoutSaving；
  dirty+canForcesave→hostRef.forceSave；dirty+!canForcesave→persistMode+lastNotice(danger)。
- 健康竞态：mount 期 ooHealthy=false，点击触发 checkOoHealth(true)，健康则切成功。
- fail-visible：switchToOnlyOffice reject → lastNotice(danger)，不 unhandled rejection。
- B 类 beforeEnterOo 返 false → 不切（switchToOnlyOffice 未被调用）。
- 变异反证：driver 内部去掉 switchToOnlyOffice 调用 → 守卫 drivingWrappers 不再收录
  useARenderModeSwitch → 15 宿主被判空壳（在守卫测试里已有同型变异模式，复用其手法）。

## §6 守卫与回归

- `bridgeMaterializeDriven.spec.ts`：A 类 15（含 A177）接 driver 后 `hollowHosts()` 与
  `bridgeBuiltNotDriven()` 不再含 A101…A91；A38 删死桥后不再进 `bridgeBuiltNotDriven`。
  3 条红全绿，`KNOWN_HOLLOW`/`KNOWN_BUILT_NOT_DRIVEN` 保持 `[]`（§R5.1）。
  driver 被 `drivingWrappers()` 识别（内部调 switchToOnlyOffice）。
- 回归：15 个 A 宿主既有 spec（如 GtA111SubsequentEventsInquiry.spec.ts，注意它 M-dirty，
  实施时先看并发会话是否已动）+ sync 全目录（35 文件）不新增失败。

## §7 治理门交接材料（R7）

接 driver 后跑 `discover-workpaper-sync-mounts.mjs --json`，diff 新 sourceDigest vs
approved。预期变化：15 个 A 宿主的 mount 从「无驱动」变「有驱动」+ A38 删桥。产出
mount diff 清单交 workpaperSyncLegacyBaseline 治理门人工复核（不在本 spec auto-regen）。

## §8 风险与并发

- `GtA111SubsequentEventsInquiry.spec.ts` 现为 M-dirty（并发会话）。实施该宿主前先
  `git status` 确认，避免碰撞；必要时跳过并记。
- `ConsolNoteTab.vue` 等其它 M-dirty 文件与本 spec 无关，不碰。
- EditorHost setup ref 暴露 forceSave 的具体接法在实施时以 Vue 3.5 + defineExpose 规范为准。
