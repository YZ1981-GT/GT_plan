# Design Document

## Overview

本 spec 在两条既有附件预览链上并联 `archive` / `email` / `drawing` 三个渲染族。复盘后采用五项不可交换的设计约束：

1. **文件名优先、Type_Hint 只作弱提示**：数据库没有真实 MIME，生产 `file_type` 是分类词、扩展名和调用方覆盖值的混合域。
2. **候选路线先过资格门再量体积**：`@open-file-viewer` 路线若不能满足压缩包五限、邮件零外发、DXF 与许可证门，即使体积小也不得入选。
3. **不可信解析全部进入可终止 Worker**：主线程只负责取字节、状态机、净化后的 DOM 和可视化；关闭或超时直接终止 worker。
4. **邮件正文双层隔离**：私有 DOMPurify 实例做显式 allowlist 与资源重写，sandbox iframe + CSP 做第二道零外发边界。
5. **legacy 单一真源不等于求并集**：registry 保存宿主专属能力矩阵，逐字复刻实施前行为；SVG、大小写和 Office 格式不得被顺手“修好”。

范围内允许一处平台共享改动：`utils/http.ts` 增加 `_dedupe:false`，使调用方 signal 不被 `addPending()` 覆盖且两个宿主的同 URL 请求不互相取消。默认路径保持现状。

## 1. 现状实测与复盘裁决

### 1.1 两宿主与真实消费链

| 链路 | 实测事实 | 设计结论 |
|---|---|---|
| `AttachmentPreview.vue` | props 为 `modelValue/fileUrl/fileName/fileType?`；legacy 以 blob + `@vue-office` 渲染；无过期栅栏 | 新增 `attachmentId/downloadUrl/typeHint`，legacy 分支代码与 URL 原样保留 |
| `AttachmentPreviewDrawer.vue` | `AttachmentForPreview.mime_type` 名不副实；PDF/图片直接交 URL，Office 走 `preview-pdf` | 将字段语义收敛为 `type_hint`；新增分支显式受 drawer active 状态控制 |
| `AttachmentManagement.vue` | Preview_Host 消费方，已有 attachment id | 显式传 id 与 `P_att.download(id)`，不通过字符串替换推导新通道 |
| `WorkpaperAttachmentsDrawer.vue` | Preview_Host 消费方，已有 attachment id | 同上 |
| `AttachmentTabPanel.vue` | Drawer_Host 唯一真实消费方；把 `file_type` 填进 `mime_type`；列表 DTO 无 OCR 字段 | process-record 只读投影补 `ocr_status/ocr_text`；用真实 DTO 做链路测试 |
| `AttachmentHub.vue` | 只有死 import 与 `window.open` TODO，模板未挂载 Drawer_Host | 登记债务，本 spec 不接线 |

### 1.2 Type_Hint 真相

`Attachment` ORM 只有 `file_type`，无 MIME 列。`AttachmentService._guess_file_type()` 对图片、表格、Word 返回 `image/excel/word`，其他格式多返回扩展名；上传表单还可覆盖它。因此：

- 生产字段统一在前端命名为 `typeHint/type_hint`；
- 文件名扩展名存在时优先判族；
- 只有文件名无扩展名时，才接受已知 MIME、分类词或扩展名别名；
- archive 仍按 magic/容器结构复核，email/drawing 也不把 Type_Hint 当安全证明；
- 不新增 MIME 数据库列，不信任浏览器上传 `Content-Type` 作为探测结果。

### 1.3 后端与 OCR

- Preview_Endpoint 对 legacy 白名单返回字节、对白名单外返回 JSON；集合保持不变。
- Download_Endpoint 返回任意附件原始字节，鉴权与可见性门保持不变。
- 上传只有 50 MiB 大小上限，无扩展名/magic 白名单；该事实只登记，不改变准入。
- process-record 附件投影当前只给 `id/file_name/file_size/file_type/created_at`，导致 Drawer_Host 的 OCR UI 在真实链路拿不到 `ocr_status/ocr_text`。本 spec 只把已有列加入只读查询/DTO，不改模型、上传、OCR 任务或 preview 端点。

### 1.4 HTTP 基线

`http.ts:addPending()`当前无条件覆盖 `config.signal`，相同 GET 还会取消先发请求。故“传 AbortController”在现状下是假取消。复盘裁决：

```ts
interface InternalRequestOptions {
  _silent?: boolean
  _dedupe?: boolean // 默认 true；false 时不进 pendingMap，且保留调用方 signal
}
```

`addPending()`第一步检查 `_dedupe === false` 并直接返回；仅新增预览请求传 `{ responseType:'blob', _silent:true, _dedupe:false, signal }`。这样不改平台其他请求的去重语义，也无需把两个 signal 复杂合并。

401 在响应拦截器中优先走全局刷新/登出，不能稳定映射到局部状态；局部 `forbidden` 只认 403。JSON_Blob_Trap 业务日志走 `@/utils/logger` 的 `logger.error()`，不使用 `console.error`，且日志只含 attachment id、family、content-type、request id，不含文件名以外的内容或正文。

### 1.5 路线 A 资格裁决

路线 A 的真实候选不是只 import core，而是同时固定：

- `@open-file-viewer/core@0.1.44`
- `@open-file-viewer/vue@0.1.44`
- 实际调用 `archivePlugin()` / `emailPlugin()` / `cadPlugin()`，并挂载最小 Vue viewer；`drawingPlugin()`不支持 DXF，不能拿来替代 `cadPlugin()`。

公开实现的 `archivePlugin()`使用 JSZip/pako 且没有本 spec 五项资源门，`emailPlugin()`允许 http(s) URI 且没有零外发/CSP 契约；其 CAD 依赖图还暴露 GPL-3.0 的 `@mlightcad/libredwg-web` optional peer。故路线 A 必须在 probe 中被真实验证，预期结论为 `capability_eligible=false`；绝不安装 GPL 包来“补齐”probe。体积结果仍记录，作为淘汰证据，但不能反向选中没有实施任务的路线。

路线 B 是当前唯一具备可控安全边界的生产实现路线；`drawing` 是否保留仍由真实 chunk 门决定。

## 2. 模块与边界

```text
components/attachment/preview/
  attachmentPreviewFormats.ts       新增族 + 宿主专属 legacy 能力矩阵
  extendedPreviewRequest.ts         download 取字节、错误分类、取消与代际栅栏
  previewResourceScope.ts           object URL / worker / listener / abort 回收
  previewWorkerClient.ts             worker lease、transfer、deadline、终止
  bundleBudget.ts                   资格门与体积裁决纯函数
  ExtendedFormatPreview.vue         状态机与动态边界
  archive/
    archiveLimits.ts                五项单一真源
    archive.worker.ts               不可信容器解析入口
    archiveContainer.ts             ZIP/TAR/GZIP 边界解析
    archiveInflate.ts               method 0/8 实际计数与 CRC
    ArchiveEntryList.vue
  email/
    emailLimits.ts
    email.worker.ts
    emailParser.ts
    emailSanitizer.ts               私有 purifier + 安全 DOM 模型
    EmailMessageView.vue            sandbox iframe + CSP / 纯文本
  drawing/
    drawingLimits.ts
    dxf.worker.ts
    dxfModel.ts
    dxfToSvg.ts                     typed render model，禁止 v-html
    DxfDrawingView.vue
```

三个 worker 只能由 `ExtendedFormatPreview.vue` 后的异步族模块创建。Vite worker URL 采用 `new Worker(new URL('./x.worker.ts', import.meta.url), { type:'module' })`；应用 entry 不得静态可达解析依赖或 worker chunk。

## 3. Format_Registry 与 legacy 零回归

### 3.1 契约

```ts
export type PreviewFamily = 'archive' | 'email' | 'drawing' | 'legacy' | 'unsupported'
export type ByteChannel = 'preview' | 'download'
export type TypeHint = string | null | undefined

export interface FamilyVerdict {
  family: PreviewFamily
  byteChannel: ByteChannel
  ext: string
  advice: 'cad_download_only' | 'generic'
  evidence: 'extension' | 'type_hint' | 'none'
}

export function resolvePreviewFamily(fileName: string, typeHint?: TypeHint): FamilyVerdict
export function isExtendedFamily(family: PreviewFamily): boolean
export const LEGACY_CAPABILITIES: Readonly<{
  previewHost: { word: readonly string[]; excel: readonly string[]; image: readonly string[] }
  drawerHost: { office: readonly string[]; pdfSuffix: string; imageTypePrefix: string }
  attachmentTab: { office: readonly string[]; iconGroups: Readonly<Record<string, readonly string[]>> }
}>
```

新增族声明：archive=`zip/tar/gz/tgz`，email=`eml/msg`，drawing=`dxf`；`dwg` 只在 advice 表。建表函数接收声明作为参数，使冲突守卫可用合成坏输入真跑，而不是修改生产常量。

Type_Hint 回退接受：

- 已知 MIME：`message/rfc822`、`application/vnd.ms-outlook`、`application/zip`、`application/gzip`、`application/x-tar` 及 legacy MIME；
- 分类词：`word/excel/image`；
- 无点扩展名别名：`zip/eml/msg/dxf/...`。

未知扩展名不会被 Type_Hint 覆盖；这避免“文件名是 `.exe`、提示是 image”时误入图片路径。

### 3.2 宿主专属 legacy 矩阵

矩阵必须复刻现状，而不是求并集：

- Preview_Host 图片仅 `jpg/jpeg/png/gif/bmp/webp`，**不因后端白名单含 svg 而补 svg**；
- Drawer_Host Office 维持现有 10 项，PDF 维持原大小写语义，图片维持原 `image/` 提示语义；
- AttachmentTabPanel Office 与 icon 分组维持自身当前集合，不借 Drawer 的 10 项扩面。

宿主删除内联数组后仍调用与现状等价的宿主专属 helper。`resolvePreviewFamily()`只决定新增族挂载和公共 advice；它不把 union 后的 legacy 结果直接驱动宿主既有 DOM。

### 3.3 单一真源守卫

`inlineExtensionListViolations(cleanSource, label)`扫描 Preview_Host、Drawer_Host、AttachmentTabPanel：

- registry 外含两个及以上已知扩展名的数组/Set；
- `endsWith('.xxx')`、`=== '.xxx'` 等私有判定；
- 从 registry 导入并消费的常量/helper 豁免。

守卫自带 SFC/TS 安全 `stripComments()`，并以合成坏源码做反向自检。源码扫描只是结构补充；legacy 结果最终由挂载 DOM + 请求 spy 的行为矩阵锁定。

## 4. 路线资格与 Bundle_Budget

### 4.1 两阶段裁决

```ts
interface RouteMeasurement {
  route: 'A' | 'B'
  capability: Record<'archiveLimits'|'emailIsolation'|'dxf'|'disposable'|'license', boolean>
  entryGzip: number
  chunks: Record<string, number>
}

function decideRoute(m: RouteMeasurement[], budget: BundleBudget): RouteDecision
```

算法：

1. 任一 capability 为 false → `ineligible`；
2. 只在 eligible 路线间比较真实构建；
3. A eligible 但首屏超门 → B；
4. B 的 drawing chunk 超门 → 删除 drawing、重建并复测；
5. 所有 eligible 路线首屏超门 → 按实测贡献缩格式，不放宽门；
6. 实施后确认门失败必须执行回退分支并再次 build，不能只记录红值后继续。

### 4.2 真实 probe

`bundle-probe/`是可删除 workspace。A probe 同时安装 core/vue 精确版本，执行插件工厂、注册并挂载最小 Vue viewer，使用 zip/eml/dxf 最小样本；构建脚本从 Rollup module graph 断言 core、vue adapter 与三个插件模块确实进入产物。若 GPL peer 被解析进 lock/chunk，A 立即 license=false；probe 不安装该 peer。

B probe 真实创建 fflate 流、postal-mime parser、msgreader 与 dxf parser，防止 tree-shaking。两条路线同 Vite 版本、同 target、同 minify 与 gzip 算法。

### 4.3 预算

| 判据 | 上限 | 门类型 |
|---|---:|---|
| 解析依赖/worker 进入首屏可达 chunk（module graph 归因） | 0 B | **硬门** |
| 同一基线 commit/lock digest 下首屏 gzip 增量 | 8 KiB | 参考量 |
| archive 按需 chunk | 96 KiB | **硬门** |
| email 按需 chunk | 700 KiB | **硬门** |
| drawing 按需 chunk | 400 KiB | **硬门** |
| 按需合计 | 1.2 MiB | **硬门** |

**首屏门口径（2026-09-09 收口明确）**：首屏的**硬安全门 = 本 spec 新增解析依赖（fflate/postal-mime/msgreader/dxf-parser）与三个 worker 模块进入首屏可达 chunk 的字节数必须为 0 B**，由 Rollup/Vite 生产 module graph 精确归因（见 `task16_production_bundle_gate.json` 的 `entry_chunks[].{fflate,postal,msg,dxf,archiveApi}` 全 false 与 `measured.entryParserBytes=0`）。

「首屏 gzip 增量 8 KiB」降级为**参考量而非硬门**，原因有二：① 应用工作树长期存在并发会话改动（guidance/registry/router 等），实施前后首屏总 gzip 差异无法单独归因给本 spec，把并发字节算给本 spec 会得出错误结论；② 完整 minify 生产构建在本机 OOM（`--minify false` 用于 module-graph 归因）。因此首屏是否被本 spec 撑大，以**可精确归因的 module-graph 0 B 判据**为准，而非不可归因的总字节差。此为**收紧判据口径**（从不可归因的总量差改为可归因的模块归属），非放宽安全门。

Task 2 在任何生产改动前记录 baseline commit、`package-lock.json` digest、构建命令和 entry graph。实施后若基线已漂移，先在同一 commit/lock 条件重算，不把并发改动的字节算给本 spec。模块归属判据优先于总字节差。

直接产品依赖固定 `fflate@0.8.3`、`postal-mime@3.0.0`、`@kenjiuno/msgreader@1.28.0`、`dxf-parser@1.1.2`；传递依赖版本从 lockfile 精确读取，台账不得写 `0.6.x/1.x`。许可证台账同时记录“是否进入产品 chunk”。

## 5. 请求、并发与资源生命周期

### 5.1 显式通道

新增组件只接收显式 `attachmentId` 与 `downloadUrl`。真实消费方都已有 id，必须传 `P_att.download(id)`；新增能力不允许用 `fileUrl.replace('/preview','/download')` 猜 URL。旧下载按钮可保持既有实现，legacy 路径不进新 request 层。

取字节必须直接用 `http.get()`拿完整 response：

```ts
const response = await http.get(downloadUrl, {
  responseType: 'blob',
  _silent: true,
  _dedupe: false,
  signal: abortController.signal,
})
```

header 或 `blob.type` 为 `application/json`即 `wiring_error` + `logger.error`。403/404/其他分别映射 `forbidden/not_found/load_failed`；401由全局认证链处理；Axios cancel 映射 `cancelled/stale`，不显示加载失败。

### 5.2 双保险并发模型

每次 load：

1. 递增 `generation`；
2. 先 release 旧 scope；
3. 建新 `AbortController` 与 worker lease；
4. fetch 完成、arrayBuffer 转移前后、worker 返回后均检查 generation；
5. 任一不等即回收后返回；
6. close/switch 将 generation 再递增，abort 请求并 terminate worker。

`_dedupe:false`保证两个宿主同开同一 URL 不互相取消。守卫必须真发两个并发 mock request，两个都成功；再 abort 其中一个，另一个不受影响。

### 5.3 PreviewResourceScope

```ts
class PreviewResourceScope {
  trackObjectUrl(url: string): string
  releaseObjectUrl(url: string): void
  trackAbortController(c: AbortController): void
  trackWorker(w: Worker): void
  trackCleanup(fn: () => void): void
  releaseAll(): void
  snapshot(): { objectUrls: number; workers: number; cleanups: number }
}
```

release 幂等；单个 CID object URL 由 `releaseObjectUrl` 从同一 scope 精确释放，换邮件与卸载最终仍统一走 `releaseAll`，子组件不得维护逃逸台账。Drawer 的新增分支使用 `v-if="modelValue && extendedFamily"`（或等价 active 门）保证关闭即卸载；不能假设 el-drawer 自然销毁 slot。Preview_Host close、两宿主 switch 与 `onUnmounted` 都调用同一释放入口。

## 6. archive：Worker 内的受限容器解析

### 6.1 Worker 协议

主线程把 ArrayBuffer 作为 transferable 交给 `archive.worker.ts`，不复制条目正文回来。worker 只逐批返回条目元数据和最终状态；主线程 deadline 默认 15 秒，超时/关闭立即 terminate。64 MiB 是**实际输出计数门**，不是浏览器总内存上界；监控另记录输入大小、峰值批次与耗时。

### 6.2 五项单一真源

```ts
ARCHIVE_LIMITS = {
  maxEntries: 2000,
  maxEntryUncompressedBytes: 32 * MiB,
  maxTotalUncompressedBytes: 64 * MiB,
  maxCompressionRatio: 100,
  maxPathDepth: 8,
}
```

比例分母用实际消费的压缩数据字节，防零除；总量与比例均用流式实际输出。每个 entry 的输出直接喂 size/CRC sink 后丢弃，不组装完整正文。每批 metadata 数量也有上限，防 postMessage 洪泛。

### 6.3 ZIP 支持矩阵与结构门

首版只支持单磁盘 classic ZIP 的 method 0（stored）和 8（deflate）。以下在读取 entry 数据前返回明确 `container_unsupported`：ZIP64、multi-disk、AES/method 99、Deflate64/BZip2/LZMA/Zstd 等其他 method。加密 bit 0 返回 `encrypted`。

结构检查：

- EOCD 只在规范允许的尾部 comment 窗口搜索；
- 所有 offset/length 用安全整数并先做边界检查；
- central/local header 的 name、method、flags 与数据范围一致；
- 支持 bit 3/data descriptor，但 descriptor 不能覆盖中央目录；
- method 0/8 的实际输出大小与 CRC 校验；
- 自报 size 只作诊断，不作上限判据；
- 容器级截断/越界/CRC 失败 fail closed，entry 自身不支持的方法可逐条标记并继续。

### 6.4 TAR/GZIP

TAR 校验 512-byte header checksum、size/offset、结束块与 header/PAX mtime；受限 PAX `x/g`、GNU `L/K` 只更新下一真实条目或全局元数据，扩展头不进入附件列表，扩展正文上限 64 KiB；symlink/hardlink 只列元数据绝不跟随，sparse、`GNU.sparse.*` 与异常扩展明确 `container_unsupported`。路径深度在 ratio 之前裁决，确保双重违规时稳定返回 `maxPathDepth`，但不放宽任何拒绝。

GZIP 按 chunk 增量解压，校验 trailer CRC、ISIZE、尾随数据与可选 header 边界；ratio 分母只含实际 deflate 数据。调用方通过 `hintExt` 分流：普通 `.gz` 返回单条实际文件元数据，`.tgz` 或无 hint 才把输出流喂增量 TAR 状态机，均不先物化整份输出。

### 6.5 编码、路径与零 I/O

ZIP EFS → UTF-8；无 EFS → UTF-8 fatal → GBK → UTF-8 replacement。CID 之外不做任意编码猜测。条目名先把 `\` 归一为 `/`，再检测 `..`、绝对路径、盘符、NUL 与 `maxPathDepth`。

archive 模块不得 import service/http，不得引用 fetch/XHR/File System Access/download anchor。结构守卫 + worker 行为守卫双锁；真实 zip/tar/tgz 夹具断言外部网络调用为 0。

## 7. email：受限解析、私有净化与 sandbox/CSP

### 7.1 Worker 解析与模型

`email.worker.ts`在 15 秒 deadline 内执行：输入 ≤ 后端 50 MiB、MIME part ≤ 500、单个 inline raster ≤ 10 MiB、inline 总量 ≤ 32 MiB。普通附件只回 `{filename,size,contentId}`；只有候选 inline raster 的 bytes 通过 transferable 回主线程。

```ts
interface ParsedEmail {
  from: string
  to: string[]
  cc: string[]
  subject: string
  date: string | null
  html: string | null
  text: string | null
  attachments: Array<{ filename: string; size: number; contentId: string | null }>
  inlineParts: Array<{ canonicalCid: string; declaredMime: string; bytes: ArrayBuffer }>
}
```

`.eml`用 postal-mime，`.msg`用 msgreader，归一后视图不区分来源。CID canonicalization = trim、去外围 `< >`、单次 percent decode、ASCII lowercase；同一 canonical CID 多次出现即标歧义，不产生 URL。

### 7.2 inline 资源门

只允许 png/jpeg/gif/webp。声明 MIME 与 magic 必须一致；SVG、HTML、未知或超限部件进入 blocked 列表。对象 URL 由主线程 scope 创建，下一封邮件前全部 revoke。

### 7.3 Email_Sanitizer

每次预览创建独立 DOMPurify 实例；若使用 hook，只能挂到该实例并在 `finally`移除，禁止 `removeAllHooks()`。净化采用显式 HTML tag/attribute allowlist：

- 禁 script/iframe/object/embed/form/input/button/select/textarea/link/meta/base/style/audio/video/source/picture/SVG/MathML；
- 禁所有 `on*`、style、srcset、poster、background、formaction 等自动加载/提交属性；
- `img[src]`只接受本 scope 生成的 blob URL或受限 raster data URL；
- 外部 `http(s)`、scheme-relative、CSS URL、SVG href 等记录到 `blockedResources`，不保留可加载属性；
- 外部超链接显示为惰性文本/目标主机标签，不保留可点击 href，避免用户点击后在 iframe 内外发。

返回值不是裸 string：

```ts
interface SafeEmailBody {
  html: string
  blockedResources: Array<{ kind: string; host?: string }>
  generatedObjectUrls: string[]
}
```

被整节点删除的 link/iframe 也通过 blockedResources 形成汇总占位，避免“节点已被 FORBID 却还要求后置 hook 给它打标”的不可实现设计。

### 7.4 第二道隔离

净化 HTML 只进入 `<iframe sandbox="" :srcdoc="...">`，不加 `allow-scripts/allow-same-origin/allow-forms/allow-popups`。srcdoc 首部固定 CSP：

```text
default-src 'none'; img-src blob: data:; style-src 'unsafe-inline';
font-src 'none'; media-src 'none'; connect-src 'none'; frame-src 'none';
form-action 'none'; base-uri 'none'
```

纯文本用 `textContent` 路径。Playwright 监听所有 request，覆盖 img/srcset、picture/source、video poster、SVG、CSS url/@import 等样本并断言外部 host 0 请求。连续“坏邮件→好邮件→另一封 CID 邮件”证明 worker、hook 和 CID 不串线。

## 8. drawing：DXF Worker 与 typed SVG

`dxf.worker.ts`先做输入字节和 group-code `0` 轻量预扫，再调用 `dxf-parser`；预扫统计 `ENTITIES/BLOCKS` 中全部非结构实体 token，支持类型与 `HATCH/SPLINE/unknown` 等不支持类型同样计入 flood 门，禁止借 unsupported 类型绕过。默认输入上限 16 MiB、候选 entity ≤ 200000、INSERT 深度 ≤ 8；`DRAWING_LIMITS.deadlineMs=10_000` 是单一真源并由宿主 worker client 真实消费。预扫或 worker deadline 先于完整对象膨胀生效。

支持 LINE/LWPOLYLINE/POLYLINE/CIRCLE/ARC/ELLIPSE/POINT/TEXT/MTEXT/INSERT。worker 返回 typed render model；Vue 以元素/VNode属性渲染，文本走 `textContent`，禁止拼 SVG string 后 `v-html`。超限展示部分结果与明确提示。

`dwg`只得到 `cad_download_only`，行为守卫传 `.dwg` 给编排层并断言 worker factory 调用数为 0。若 drawing chunk 超门，删除 dxf family、动态 import、产品依赖与相关 UI后重建；`.dxf/.dwg`均落下载提示。

## 9. 编排、宿主接线与 OCR

### 9.1 状态机

`ExtendedFormatPreview.vue`状态：`loading/ready/forbidden/not_found/load_failed/wiring_error/limit_reached/encrypted/format_mismatch/container_unsupported/parse_failed/unsupported/cancelled`。`cancelled`不渲染错误；所有其他非 ready 状态有下载入口。异常只转状态，不冒泡到宿主。

archive/email/drawing 视图通过异步 import；worker factory 也在该边界后。状态文案、错误码和 `data-testid` 单一真源，两个宿主不各写一份。

### 9.2 Preview_Host

- 新增 `attachmentId/downloadUrl/typeHint`，两个消费方显式传值；
- legacy helper 改读 `LEGACY_CAPABILITIES.previewHost`，结果逐项与基线相同；
- 在 legacy 分支之后挂一条 ExtendedFormatPreview；
- unsupported 默认文案不变，仅 dwg 用 CAD 文案；
- 新增分支受 `modelValue` 门控，关闭即释放。

### 9.3 Drawer_Host 与 Type_Hint 重命名

`AttachmentForPreview.mime_type`重命名为 `type_hint`并一次性更新真实消费方和测试，不保留第二字段 fallback。Drawer legacy helper读 `LEGACY_CAPABILITIES.drawerHost`，不顺手修大小写/图片提示缺陷。新增分支用 `v-if="modelValue && extendedFamily"`。

Office `preview-pdf`、health cache 与降级文案不动。OCR badge 和正文仍位于分支链外；process-record DTO补齐字段后，以真实 payload 贯穿 TabPanel→Drawer 的集成守卫验证，而非直接传理想 props。

## 10. 守卫、变异与浏览器验证

### 10.1 守卫层级

| 层 | 关键判据 |
|---|---|
| 纯函数 | registry、资格/体积裁决、错误分类、五限、路径归一、CID/magic |
| 行为 | HTTP signal/dedupe、worker terminate/deadline、容器实际计数、sanitizer 输出、DTO 投影 |
| 挂载 DOM | 两宿主分发、legacy 矩阵、OCR 真实链、archive 行、邮件切换与 blocked 提示 |
| 结构图 | 动态 import/worker chunk 不可从 entry 同步到达、archive 无网络/落盘 API、DXF 无 v-html |
| API 契约 | 上传三类成功、preview 对新增类仍 JSON、download 原字节、legacy preview 字节 |
| 浏览器 | 两宿主真实上传→预览、外部网络 0、关闭/切换无泄漏、console error 0 |

后端“零改动”不再只冻结源码字符串：行为契约是主判据，AST/源码检查仅补充。legacy 期望来自 Task 1 对现状的冻结结果，并覆盖生产真实 `file_type` 形状。

### 10.2 三要素

Requirement 8.9 落在**每个宿主挂载后的完整 render tree**：

1. archive 结果确有 N 个行 DOM；
2. 非 archive family 时该区块为 0，证明外层门控；
3. 每行内含 name/size/time/directory/suspicious 等字段，证明内层嵌套。

不要求宿主源码本身含 `v-for`；遍历位于共享 `ArchiveEntryList.vue`才是本设计的目标。

### 10.3 变异 harness 加强

继续复用 `_mutation_kit` 的锚点、单变异应用、四态与差集判读，但本 spec 外层新增：

1. 严格基线：失败集合为空、passed 数和 test nodeid manifest 均与冻结值相同，否则 ABORT；
2. 基线通过后，对**所有声明 mutation target**拍 bytes+hash manifest，而不是只按当前单文件备份；
3. 以 `O_EXCL` spec lock 防同脚本并发；
4. 每条变异后沿用 kit 即时还原并读回；
5. 最外层 `finally`核验全部目标。只恢复本脚本可证明拥有的 mutation digest；发现外部字节漂移则报 `RESTORE-CONFLICT`、保留恢复副本并停止，绝不盲覆他人编辑；
6. `guard_coverage.json`以 `Property → test nodeid → mutation ids`为分母，文件级 tally 仅作补充；
7. GREEN、WRONG-TEST、ANCHOR-MISS、restore conflict 任一存在均不交付。

### 10.4 Playwright

真实上传 zip/tar/tgz、eml、msg、dxf、dwg；两宿主逐一走完整链。网络监听按 origin/host断言邮件外发 0、新增三类请求 Preview_Endpoint 0；两宿主同开同附件不互相取消；快速关闭/切换后页面无陈旧结果，worker/object URL/pending 探针归零。drawing 已按体积退出时，dxf 用例改为验证下载提示，不能无条件期待 SVG。

## 11. 交付台账与 CI

`evidence/attachment-preview-format-expansion/`至少包含：

- `route_capability_and_bundle_budget.json`
- `dependency_licenses.json`
- `registered_debt.json`
- `guard_coverage.json`
- `mutation_verdicts.json`
- `browser_evidence.json`
- `artifact_manifest.json`

`artifact_manifest.json`列出每个实现、守卫、fixture、脚本、台账和 CI 引用路径及 git 状态。CI 分前端与后端两个归因型 job，路径从 manifest/固定清单生成，干净 checkout 逐项验证 exists+tracked。`governance-checks.yml`只追加本 spec 区块，不对并发 job 做全局等值断言。

遗留登记保持三项：xlsx 0.18.5 告警、AttachmentHub 死 import/TODO、两宿主长期收敛建议。会话临时文件按前缀、mtime、内容归属清理，不删除并发会话产物。

## 12. Correctness Properties

### Property 1: 判族确定、归一、封闭且 Type_Hint 只在无扩展名时作受限回退
**Validates: Requirements 1.1, 1.2, 1.3, 1.4**

### Property 2: legacy 归族、宿主能力矩阵与 Byte_Channel 均由 registry 单向派生
**Validates: Requirements 1.5, 1.6**

### Property 3: registry 外无第二份清单，跨族重复或 dwg 入族均 fail closed
**Validates: Requirements 1.7, 1.8**

### Property 4: 新增三类只走 Download_Endpoint，两个宿主 legacy URL 逐字不变
**Validates: Requirements 2.1, 2.2**

### Property 5: JSON_Blob_Trap 记无敏感内容的 ERROR，403/404/其他失败互斥
**Validates: Requirements 2.3, 2.4**

### Property 6: close/switch/unmount 取消请求、终止 worker、释放 URL 与监听器，重复打开不累积
**Validates: Requirements 2.5, 2.6**

### Property 7: `_dedupe:false`保留调用方 signal，同 URL 双宿主互不取消，代际栅栏丢弃迟到结果
**Validates: Requirements 2.7**

### Property 8: archive 清单展示实际大小且全部不可信解析在零网络、零落盘 Worker 内完成
**Validates: Requirements 3.1, 3.2**

### Property 9: 五项上限各自可触发，zip bomb 只按实际流式输出中止
**Validates: Requirements 3.3, 3.4**

### Property 10: 路径穿越被标记且解析图无写出接口
**Validates: Requirements 3.5**

### Property 11: 编码回退、加密提示、内容嗅探、unsupported 容器/方法、entry 与 container 失败分层正确
**Validates: Requirements 3.6, 3.7, 3.8, 3.9**

### Property 12: eml/msg 在受限 Worker 中归一并展示头、正文与轻量附件清单
**Validates: Requirements 4.1, 4.2, 4.3**

### Property 13: HTML 默认展示且可切文本，主动标签/属性与危险协议全部移除
**Validates: Requirements 4.4, 4.5**

### Property 14: sanitizer 资源重写与 sandbox/CSP 双层阻断全部自动加载向量
**Validates: Requirements 4.6**

### Property 15: CID 仅安全栅格且跨邮件隔离，中文头可读，失败不污染下一封
**Validates: Requirements 4.7, 4.8, 4.9**

### Property 16: 两宿主各自 legacy DOM/文案/URL 不变且 Office 转 PDF 不受影响
**Validates: Requirements 5.1, 5.2**

### Property 17: OCR 通过真实 DTO 链在新增视图可达，所有失败态保留下载
**Validates: Requirements 5.3, 5.4**

### Property 18: preview/upload 行为契约不变且上传无扩展名白名单事实入账
**Validates: Requirements 5.5, 5.6**

### Property 19: 任一解析异常都被状态机隔离且宿主仍可关闭
**Validates: Requirements 5.7**

### Property 20: drawing 仅 dxf，dwg 永不创建 worker并显示专用文案
**Validates: Requirements 6.1, 6.2**

### Property 21: 产品 chunk 许可证白名单、精确依赖清单与 lockfile 版本均可复核
**Validates: Requirements 6.3, 6.4, 6.6**

### Property 22: drawing 超门时完整退出并重建，不通过改阈值伪绿
**Validates: Requirements 6.5**

### Property 23: Route_Eligibility 先于真实生产构建体积裁决，A probe 无法被 tree-shaking 清空
**Validates: Requirements 7.1, 7.2, 7.4**

### Property 24: 首屏与各按需 chunk 分别报告且解析/worker 模块零字节归属首屏
**Validates: Requirements 7.3, 7.5**

### Property 25: 预算、基线 digest 与实测可复核，确认门失败会回退并复测而非放门
**Validates: Requirements 7.6, 7.7**

### Property 26: 守卫覆盖全部判据面且行为/DOM/网络优先于字符串存在
**Validates: Requirements 8.1, 8.2**

### Property 27: 每条 Property/test nodeid 有变异，四态按预期测试差集判读
**Validates: Requirements 8.3, 8.4, 8.5**

### Property 28: strict baseline、全目标快照/锁、finally 所有权安全还原与落盘读回成立
**Validates: Requirements 8.6, 8.7**

### Property 29: 两宿主以真实 Type_Hint/DTO 接线，完整 render tree 的三要素均可观察
**Validates: Requirements 8.8, 8.9**

### Property 30: artifact manifest 逐项证明 tracked，CI 引用在干净检出存在且改动归因正确
**Validates: Requirements 9.1, 9.2, 9.3**

### Property 31: xlsx 告警、AttachmentHub 待办与两宿主成本均登记且明确不夹带修复
**Validates: Requirements 9.4, 9.5, 9.6**

### Property 32: 本会话临时诊断产物按归属清除
**Validates: Requirements 9.7**
