# Requirements Document

## Introduction

审计现场的证据附件里有三类格式目前**只能下载到本地打开**：压缩包（客户一次性打包提交的凭证影像）、邮件（`.eml` / `.msg` 形态的函证回函与管理层往来）、CAD 图纸（固定资产盘点的厂房与设备图）。本 spec 为这三类补浏览器内预览，**docx / xlsx / pdf / 图片 的现有渲染路径一律不动**。

本 spec 是**新增能力**，不是替换。明确不覆盖：

- 不替换 `@vue-office/{docx,excel,pdf}`，不替换 OnlyOffice / Univer，不改底稿本身的 HTML 渲染器；
- 不改附件上传链路（后端本来就无扩展名白名单，三类格式已可上传）；
- 不改 `/api/attachments/{id}/preview` 既有白名单的**行为**（只新增一条不经过它的取字节通道）；
- 不新增数据库迁移，不改附件数据模型；
- 不做 `.dwg` 的图形渲染（见 Requirement 6 的许可证裁决）；
- 不做压缩包与邮件附件的**二级预览**（点开压缩包内某个 docx 再渲染它）——本轮只到清单与纯文本正文；
- 不修复既有的 `xlsx@0.18.5` 供应链告警（独立议题，见 Requirement 9 的登记要求，本 spec 只登记不修）。

## Glossary

- **Preview_Host**：`audit-platform/frontend/src/components/extension/AttachmentPreview.vue`。弹窗形态预览宿主，消费方为 `views/AttachmentManagement.vue` 与 `components/workpaper/WorkpaperAttachmentsDrawer.vue`。
- **Drawer_Host**：`audit-platform/frontend/src/components/common/AttachmentPreviewDrawer.vue`。抽屉形态预览宿主，消费方为 `views/AttachmentHub.vue` 与 `components/workpaper/AttachmentTabPanel.vue`（底稿内嵌附件 Tab）。
- **两宿主**：Preview_Host 与 Drawer_Host 的合称。二者是平台上并存的两条预览路径，本 spec 的能力必须在两者都可达。
- **Format_Registry**：新增的扩展名 → 渲染器判定单一真源。两宿主与守卫共同读它，任何一侧不得自带第二份扩展名清单。
- **新增三类**：`archive`（`zip` / `tar` / `gz` / `tgz`）、`email`（`eml` / `msg`）、`drawing`（`dxf`）三个渲染族。
- **Legacy_Formats**：`docx` / `doc` / `xlsx` / `xls` / `csv` / `pdf` 及图片扩展名，即本 spec 之前两宿主已支持的集合。
- **Preview_Endpoint**：`GET /api/attachments/{attachment_id}/preview`（`backend/app/routers/attachments.py`）。对白名单内格式返回字节流，对白名单外格式返回 JSON 对象 `{"previewable": false, ...}`。
- **Download_Endpoint**：`GET /api/attachments/{attachment_id}/download`（同文件）。对任意格式返回 `application/octet-stream` 字节流，鉴权与 Preview_Endpoint 同为 `_ensure_project_access` + `enforce_attachment_wp_visibility` 两层。
- **Byte_Channel**：新增三类取字节所用的通道，取值为 Download_Endpoint。Legacy_Formats 继续走 Preview_Endpoint。
- **JSON_Blob_Trap**：对白名单外格式调用 Preview_Endpoint 并以 `responseType: 'blob'` 接收时，得到的是一个 MIME 为 `application/json` 且内容为 `{"previewable": false, ...}` 的 blob，而非文件字节。本 spec 的首要接线缺陷来源。
- **Archive_Limits**：压缩包解析的资源上限集合，含条目数上限、单条目解压后大小上限、总解压后大小上限、解压比上限、嵌套深度上限五项。
- **Zip_Bomb**：解压后体积与压缩包体积之比异常高，或条目数异常多的压缩包。
- **Path_Traversal_Entry**：压缩包内条目名经归一化后逃出根目录（含 `..` 段、绝对路径、盘符前缀、以及 `\` 与 `/` 混用的变体）。
- **Email_Sanitizer**：邮件 HTML 正文的净化环节。基于平台已有的 `dompurify`。
- **Remote_Asset_Leak**：邮件 HTML 正文中引用外部主机资源（`img` / `link` / `iframe` / CSS `url()` / `srcset`）导致渲染即向外部发起请求，从而把「某审计项目正在查阅某封函证」泄露给外部主机。审计保密场景下按缺陷处理。
- **Bundle_Budget**：本 spec 引入的依赖对前端生产构建的体积增量上限。判据取生产构建产物中**新增的、被首屏或附件预览路由实际加载的** JavaScript 字节数。
- **路线 A**：依赖 `@open-file-viewer/core` 加其 Vue 适配器实现三类渲染。
- **路线 B**：直接依赖三类格式各自的底层解析库（压缩包、MIME 邮件、OLE 邮件、DXF），不引入 `@open-file-viewer/core`。
- **Route_Decision**：路线 A 与路线 B 之间的选择结论，由 Bundle_Budget 的实测结果裁决，不由偏好裁决。
- **变异四态**：RED（打红且正是预期那条测试）、GREEN（守卫缺陷）、ANCHOR-MISS（脚本缺陷，锚点未命中或命中多于一处）、WRONG-TEST（打红但不是预期项）。

## Requirements

### Requirement 1: 扩展名到渲染器的单一真源

**User Story:** 作为平台前端维护者，我需要一份扩展名到渲染器的单一真源，以便两宿主对同一文件给出相同的渲染判定，而不是各自维护一份会漂移的扩展名清单。

#### Acceptance Criteria

1. THE Format_Registry SHALL 为任一文件名与可选 MIME 返回落在封闭枚举 `{archive, email, drawing, legacy, unsupported}` 内的渲染族判定。
2. WHEN 同一文件名与同一 MIME 被重复判定，THE Format_Registry SHALL 返回相同的渲染族。
3. THE Format_Registry SHALL 对大小写混合的扩展名（如 `.ZIP`、`.Eml`）与前后含空白的文件名返回与其归一形态相同的判定。
4. WHEN 文件名不含扩展名，THE Format_Registry SHALL 依据 MIME 判定，且在 MIME 亦不可判时返回 `unsupported`。
5. THE Format_Registry SHALL 把 Legacy_Formats 判为 `legacy`，使其继续由既有渲染分支处理。
6. THE Format_Registry SHALL 为每个渲染族同时给出该族的 Byte_Channel 取值，`legacy` 族为 Preview_Endpoint，新增三类为 Download_Endpoint。
7. THE Format_Registry SHALL 提供守卫可调用的断言，扫描两宿主源码，把两宿主内自带的扩展名字面量清单报为违规，除非该位置从 Format_Registry 取值。
8. IF 一个扩展名同时出现在 Legacy_Formats 与新增三类的声明中，THEN THE Format_Registry SHALL 在模块加载期抛错而非按声明顺序静默取先者。

### Requirement 2: 取字节通道绕开白名单陷阱

**User Story:** 作为审计助理，我需要压缩包与邮件附件点开就能看，而不是看到一个空白或报错的预览框，因为我无法从界面上分辨「文件坏了」和「平台没接好」。

#### Acceptance Criteria

1. WHEN 渲染族为新增三类之一，THE 两宿主 SHALL 从 Download_Endpoint 取字节，而不从 Preview_Endpoint 取。
2. WHEN 渲染族为 `legacy`，THE 两宿主 SHALL 继续从 Preview_Endpoint 取字节，其请求 URL 与本 spec 实施前逐字相同。
3. WHEN 取回的响应 MIME 为 `application/json` 而当前渲染族为新增三类之一，THE 两宿主 SHALL 判定为接线缺陷，展示明确的失败态并记 ERROR 级日志，而不静默降级为「暂不支持预览」。
4. THE 两宿主 SHALL 在取字节失败（网络错误、鉴权拒绝、404）时区分展示「无权访问」「文件不存在」「加载失败」三种状态，而不合并为一句「暂不支持预览此格式」。
5. WHEN 附件预览弹窗或抽屉关闭，THE 两宿主 SHALL 释放该次预览创建的全部对象 URL 与解析器实例。
6. THE 两宿主 SHALL 在同一次会话内重复打开同一附件时不累积未释放的对象 URL。
7. IF 取字节请求在响应到达前该宿主已关闭或已切换到另一附件，THEN THE 两宿主 SHALL 丢弃该响应，不把过期结果渲染到当前视图。

### Requirement 3: 压缩包预览与资源上限

**User Story:** 作为现场经理，我需要在不下载的情况下看清客户提交的压缩包里到底有哪些凭证文件，以便判断证据是否齐备。

#### Acceptance Criteria

1. WHEN 渲染族为 `archive`，THE 两宿主 SHALL 展示条目清单，每条含条目名、解压后大小、修改时间与目录标识。
2. THE 压缩包解析 SHALL 在浏览器内完成，不把附件字节发往任何平台外主机。
3. THE 压缩包解析 SHALL 对 Archive_Limits 五项逐项设限，并在任一项被触及时停止解析、保留已解析出的条目、展示明确的「已达解析上限」提示与被触及的具体那一项。
4. WHEN 压缩包为 Zip_Bomb，THE 压缩包解析 SHALL 在解压总量达到总量上限前中止，且中止判定不依赖压缩包自报的解压后大小字段。
5. THE 压缩包解析 SHALL 把 Path_Traversal_Entry 标记为可疑并在清单中显式标注，且不以该条目名在任何文件系统或存储接口上落盘。
6. THE 压缩包解析 SHALL 对条目名的字符编码按压缩包声明解码，声明缺失时按 UTF-8 尝试并在失败时回退到不抛错的替换解码，使中文条目名不显示为乱码且不中断整包解析。
7. WHEN 压缩包受密码保护，THE 两宿主 SHALL 展示「该压缩包已加密，请下载后打开」而非展示空清单或失败态。
8. IF 压缩包字节不是受支持的压缩格式（含扩展名与实际内容不符的情形），THEN THE 两宿主 SHALL 依据实际内容判定并展示格式不符的提示，而不依据扩展名强行解析。
9. THE 压缩包解析 SHALL 不因单个条目解析失败而放弃整包，该条目在清单中标注为不可解析。

### Requirement 4: 邮件预览

**User Story:** 作为审计助理，我需要直接在平台内查阅函证回函邮件的发件人、收件人、时间与正文，以便把回函要素录进函证底稿而不必来回切换本地邮件客户端。

#### Acceptance Criteria

1. WHEN 渲染族为 `email`，THE 两宿主 SHALL 展示发件人、收件人、抄送、主题、发送时间与正文。
2. THE 邮件解析 SHALL 同时支持 MIME 形态（`.eml`）与 OLE 复合文档形态（`.msg`）。
3. THE 两宿主 SHALL 列出邮件自身的附件清单，每条含文件名与大小。
4. WHEN 邮件同时含 HTML 与纯文本正文，THE 两宿主 SHALL 默认展示经 Email_Sanitizer 处理后的 HTML，并提供切换到纯文本的入口。
5. THE Email_Sanitizer SHALL 移除脚本、事件处理属性、表单元素与 `javascript:` 协议引用。
6. THE 两宿主 SHALL 阻断 Remote_Asset_Leak，使邮件正文渲染时不向外部主机发起任何请求，并对被阻断的外部资源展示占位与「已阻止外部资源加载」说明。
7. THE 邮件正文中引用的内嵌资源（`cid:` 引用）SHALL 从邮件自身的附件部件解析后渲染，不经外部请求。
8. WHEN 邮件头部字段采用编码字（RFC 2047）或非 UTF-8 字符集，THE 邮件解析 SHALL 解码为可读中文，不显示原始编码串。
9. IF 邮件字节解析失败，THEN THE 两宿主 SHALL 展示失败原因与下载入口，且失败不影响同一宿主随后打开其他附件。

### Requirement 5: 预览与既有能力不互相干扰

**User Story:** 作为质量控制复核合伙人，我需要确认新增预览没有动到已在用的底稿证据与 OCR 链路，以便这次改动不需要重新验证全部既有底稿。

#### Acceptance Criteria

1. THE 两宿主对 Legacy_Formats 的渲染分支、DOM 结构与展示文案 SHALL 与本 spec 实施前逐项一致。
2. THE Drawer_Host 的 Office 转 PDF 路径（`preview-pdf` 端点与健康探测）SHALL 不受本 spec 影响。
3. THE Drawer_Host 既有的 OCR 状态徽标与 OCR 文本展示 SHALL 在新增三类的预览视图中同样可见。
4. THE 两宿主 SHALL 保留既有的下载入口，且新增三类在预览失败时下载入口仍可用。
5. THE 本 spec SHALL 不改动 Preview_Endpoint 的 `previewable_types` 集合与其返回结构。
6. THE 本 spec SHALL 不改动附件上传的任何校验，并在 spec 交付物中记录后端上传当前无扩展名白名单这一实测事实。
7. WHEN 新增三类的解析器抛出异常，THE 两宿主 SHALL 捕获后展示失败态，不使宿主页面整体崩溃或使弹窗无法关闭。

### Requirement 6: CAD 与许可证裁决

**User Story:** 作为内网私有化部署的负责人，我需要 CAD 预览的许可证边界在实施前就定清楚，以便交付物不会因引入传染性许可证而无法随平台分发。

#### Acceptance Criteria

1. THE 本 spec SHALL 把 `drawing` 族的范围限定为 `dxf`，且 `dwg` 不进入 Format_Registry 的可渲染集合。
2. WHEN 附件扩展名为 `dwg`，THE 两宿主 SHALL 展示「该格式需下载后用 CAD 软件打开」而非进入任何解析路径。
3. THE 本 spec SHALL 不引入以 GPL 系许可证分发的依赖，交付物的依赖新增项许可证 SHALL 全部落在 MIT、Apache-2.0、BSD 系之内。
4. THE 交付物 SHALL 记录每个新增依赖的名称、版本、许可证与选用理由，形成可复核的清单。
5. IF `dxf` 渲染所需依赖的体积使 Bundle_Budget 不成立，THEN THE `drawing` 族 SHALL 整体退出本 spec 范围，且退出决定与实测数据一并记录，而不以缩小上限的方式使判据成立。
6. THE 新增依赖 SHALL 按精确版本或锁定版本引入，不使用开放范围。

### Requirement 7: 依赖体积门与路线裁决

**User Story:** 作为前端性能负责人，我需要这次新增能力的体积代价先被实测再被接受，以便不会为两个低频格式让全平台首屏变慢。

#### Acceptance Criteria

1. THE Route_Decision SHALL 由路线 A 与路线 B 各自的实测体积增量比对得出，不由声明或偏好得出。
2. THE 体积实测 SHALL 基于前端生产构建的实际产物，而不基于依赖包的解包大小或依赖清单推算。
3. THE 体积实测 SHALL 分别报告首屏加载增量与附件预览路径按需加载增量两项。
4. WHEN 路线 A 的实测首屏增量超出 Bundle_Budget，THE Route_Decision SHALL 取路线 B。
5. THE 新增三类的解析代码 SHALL 以按需加载方式引入，使未打开附件预览的用户不加载这些解析器。
6. THE 交付物 SHALL 记录 Bundle_Budget 的具体数值、其设定依据与实测结果，使后续变更可复核该门是否仍成立。
7. IF 两条路线的实测首屏增量均超出 Bundle_Budget，THEN THE 本 spec SHALL 缩减范围到能通过该门的格式子集，而不放宽该门。

### Requirement 8: 守卫与变异检验

**User Story:** 作为审计平台的质量负责人，我需要这次改动的守卫本身被证明能打红，以便「测试全绿」不再等于「功能真的接上了」。

#### Acceptance Criteria

1. THE 守卫 SHALL 覆盖 Format_Registry 的判定确定性、两宿主的渲染族分发、Byte_Channel 选取、JSON_Blob_Trap 识别、Archive_Limits 五项、Path_Traversal_Entry 标记、Email_Sanitizer 净化与 Remote_Asset_Leak 阻断。
2. THE 守卫 SHALL 以行为或结构为判据，不以「源码中存在某字符串」为判据。
3. THE 变异检验 SHALL 为每条守卫声明至少一处变异，判读结果落在变异四态内且不由进程退出码单独决定。
4. WHEN 某条变异的判读为 GREEN，THE 交付 SHALL 视为守卫存在缺陷并补强该守卫，而不记为「代码本就正确」。
5. WHEN 某个锚点在源码中的命中次数不等于一，THE 变异检验 SHALL 判为 ANCHOR-MISS 并报告实际命中次数。
6. THE 变异检验脚本 SHALL 在起手拍摄全量原始快照、在收尾无条件全量还原，且在变异前先跑一次基线，基线不通过时拒绝拍摄快照并报告工作树不洁。
7. THE 变异检验 SHALL 在判定 GREEN 之前读回确认变异已真正落盘。
8. THE 守卫 SHALL 断言两宿主**都**接上了新增三类，使只改其中一个宿主的实现无法通过。
9. THE 守卫 SHALL 断言新增三类的渲染分支在宿主模板中存在遍历、外层门控与内层嵌套三要素，使「模型声明了但模板从未渲染」的形态被打红。

### Requirement 9: 交付物入库与遗留登记

**User Story:** 作为项目维护者，我需要这次的守卫与脚本真进版本库、并把顺带发现的既有缺陷登记下来，以便干净检出的 CI 不会因文件缺失而挂、且发现的问题不会被这次交付淹没。

#### Acceptance Criteria

1. THE 交付 SHALL 在收口时逐项核对本 spec 全部产物的版本库跟踪状态，任何未跟踪项须登记为待入库。
2. WHEN 守卫被挂进持续集成配置，THE 被引用的文件路径 SHALL 在版本库中存在且已跟踪。
3. THE 对持续集成配置的改动 SHALL 只追加本 spec 的作业，其验收判据按「变动是否落在本 spec 追加的字节区间内」归因，不以「其他作业一个都没变」为判据。
4. THE 交付 SHALL 登记既有的 `xlsx@0.18.5` 供应链告警（原型链污染与正则拒绝服务两条），含其在平台内解析不可信上传字节的调用位置，并明确该项不在本 spec 修复范围。
5. THE 交付 SHALL 登记 `views/AttachmentHub.vue` 中以 `window.open` 代替预览宿主的既有待办，并明确该项不在本 spec 修复范围。
6. THE 交付 SHALL 登记两宿主并存这一平台现状及其带来的重复维护成本，并给出是否收敛为单一宿主的建议，本 spec 不执行该收敛。
7. THE 会话产生的临时诊断产物 SHALL 在收口前清除。
