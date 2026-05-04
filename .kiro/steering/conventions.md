---
inclusion: manual
---

# 编码与 UI 规范

需要了解项目编码规范、UI 偏好、命名约定时用 `#conventions` 引用此文件。

## UI 视觉规范（致同品牌）

- 主色 #4b2d77（紫色），设计 Token 在 gt-design-tokens.css
- 样式层级：gt-tokens → global.css → gt-page-components.css → gt-polish.css
- 按钮圆角 8px，表格行间距 10px，边框 0.5px 半透明
- 进度条流动光泽动画，标签降低饱和度
- 页面切换 Transition 过渡动画（gt-page mode=out-in）
- 页面横幅统一紫色渐变（网格纹理+径向光晕）
- 按钮三种模式：实心渐变+白字、plain 浅色+深色字、text 透明+纯文字
- 弹窗遮罩：半透明白色 rgba(255,255,255,0.6) + backdrop-filter: blur(2px)
- el-dialog 必须加 append-to-body（三栏布局 overflow:hidden 会截断）
- 输入框 focus：只保留 1px 浅紫色边框，去掉双层阴影和浏览器 outline
- 危险操作按钮用 text 模式纯文字，删除图标默认灰色 hover 变红
- 全局字号 15px（--gt-font-size-base）

## 表格规范

- 所有 el-table 必须 border + resizable（支持拖拽列宽）
- 报表表头冻结：el-table 用 max-height，矩阵表格用 thead sticky
- 行高约 0.7cm（26px），单元格 padding 2px 6px，字号 12px
- 选中行浅蓝 #e8f4fd，hover 行 #f5f8fc
- 金额单位：数据库以"元"存储，前端 displayPrefs Store 控制显示（元/万元/千元），顶栏"Aa"面板切换
- 金额格式化：统一用 formatters.ts 的 fmtAmount/fmtAmountUnit，禁止各组件自定义 fmt 函数
- 条件格式：负数红色(.gt-amount--negative) + 变动超阈值黄色(.gt-amount--highlight)，displayPrefs.amountClass() 返回 CSS 类
- 表格字号：通过 `:style="{ fontSize: displayPrefs.fontConfig.tableFont }"` 绑定，4档预设（11/12/13/14px）
- 单元格选中样式：统一使用 CellContextMenu.vue 全局 gt-ucell--selected（淡紫色半透明背景+边缘边框），禁止各模块自定义 scoped 选中样式
- 单选时加 gt-ucell--single-selected（outline + 右下角填充柄小方块，Excel 风格）
- 拖拽框选：setupTableDrag(tableRef, getCellVal) 一行代码启用，拖拽期间 body 加 .gt-dragging 禁止文本选中
- 复制按钮命名：工具栏"复制整表"（复制整个表格）vs 右键菜单"复制选中区域(N格)"/"复制值"（复制选中单元格）
- 搜索栏位置：必须在表格上方（横幅/提示区下方），致同品牌紫色渐变背景
- Ctrl+F：各组件内 document.addEventListener('keydown') + e.preventDefault() 拦截浏览器默认搜索
- 项目列建议 fixed，金额列建议 sortable

## 附注编辑器规范

- 目录树 indent 10px，子节点 padding 2px
- 章节标题不显示序号前缀（只显示科目名称）
- 正文段落间距 10px、字号 13px、行高 1.8、首行缩进 2em
- 单元格三种模式：auto（自动提数）→ manual（手动编辑）→ locked（锁定）
- TipTap 富文本编辑器用于叙述文字区域
- 空表格处理：只有"报表项目主要注释"（第五章/第八章）下的科目表格需要数据行和合计行；会计政策/关联交易/前期差错等章节的表格是描述型，不需要填充数据行

## 报表规范

- 横幅必须显示：单位名称 + 年度 + 模板类型（国企/上市）+ 口径（合并/单体），全部下拉可切换
- 审核按钮只执行 logic_check + reasonability 公式（auto_calc 不参与）
- 报表行次严格参照致同 Excel 模板，不能自己编造
- 无数据时显示预设模板结构（行次+项目名称），金额列为空

## 后端编码规范

- asyncpg 时区规则：所有与 PG TIMESTAMP WITHOUT TIME ZONE 列比较的 datetime 必须用 `datetime.utcnow()`（naive），不能用 `datetime.now(timezone.utc)`（aware）
- UTF-8 BOM 防御：读取 JSON/HTML 文件统一用 `utf-8-sig` 编码
- SoftDeleteMixin：所有软删除调用 `soft_delete()` 方法
- 路由认证：所有端点必须有 `Depends(get_current_user)` 或 `require_project_access`
- 事件发布用 `asyncio.create_task`（非阻塞），失败只记日志不阻断
- LLM 调用统一 temperature=0.3 + max_tokens=2000 + 超时 30s + 失败不阻断手动操作
- consolidation_models server_default：PG 枚举列用 `server_default="xxx"` 纯字符串

## 前端编码规范

- 禁止直接 import http 拼 URL，必须通过 apiProxy.ts 或 commonApi.ts
- 数据解包：http.ts 响应拦截器已自动解包 ApiResponse，前端用 `const { data } = await http.get(url)`
- SSE 统一封装：sse.ts（createSSE 自动重连 + fetchSSE 流式 POST）
- tsconfig 不支持 Map 迭代，用 Record 代替
- 大文件上传用原生 fetch 绕过 http.ts 拦截器（去重/重试/解包冲突）
- webkitdirectory 上传文件名含路径，后端用 `Path(file.filename).name` 只取纯文件名

## Word 导出排版规范

- 字体：仿宋_GB2312 + Arial Narrow（数字）
- 页边距：3/3.18/3.2/2.54cm
- 表格：上下 1 磅边框无左右（三线表）
- 高风险标红，页脚页码
- 千分位格式，0 显示 '-'

## 命名约定

- 路由路径：新代码统一用 working-papers（带连字符），旧代码 workpapers 保持不变（breaking change 不改）
- 报表标准：applicable_standard = soe_consolidated / soe_standalone / listed_consolidated / listed_standalone
- 底稿编码体系：B(风险评估)/C(控制测试)/D-N(实质性程序)/A(完成阶段)/S(特定项目)
- 附注章节编号：国企版 14 章（一~十四），上市版 17 章（一~十七）

## 用户交互偏好

- 删除操作必须 ElMessageBox 二次确认
- 空状态：全宽简洁（图标+一句话+一个按钮），不要啰嗦步骤说明
- 项目子页面返回按钮跳转 /projects（不是首页 /）
- 导航按角色裁剪（审计员 6 项，管理层多看看板/委派，admin 额外看用户管理）
- 空壳页面（<50 行）标记 developing 灰色不可点击
- 功能收敛：停止加新功能，核心 6-8 个页面做到极致
