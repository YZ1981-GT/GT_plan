---
source: C:\Users\baiji\Desktop\文件\税务平台\CPAS数据链路调查报告.pdf
---

CPAS 数据链路调查报告
CPAS 数据链路调查报告：数据采集 · 数据导入 · 底稿取数
调查范围：cpas-workplatform-framework 仓库（ src/cpas-server 全量源码 + PDM 表结构文档） 生成日期：
2026-10-22
第 0 章 全链路总览
客户财务软件库（用友/金蝶等）
│ ① 数据采集（外部 exe 工具，源码不在本仓库）
▼
CPAS 项目库（SQL Server，每个组成部分一个库）
│ CW_KMYYEB 科目余额 / CW_KMB 科目 / CW_PZB 凭证 / CW_FZZXMB 辅助账
│ ② 审计层加工（存储过程）
▼
BB_KMSDB 科目审定表 → PROC_ReportItem_Recal → BB_ReportItemsData 报表项目基础数据
│ ③ 底稿取数（公式 / 行列取数标签触发）
▼
design_table / design_cell（底稿表格引擎）→ 报表 / 附注呈现
三块逻辑的核心结论：
模块 一句话结论
数据 执行主体是外部闭源 exe（数据采集工具.exe / P_DataConvert.exe），本仓库负责拉起工具与消费结果；转换状态靠
采集 sjxm_zcbf 数据库字段传递，无 HTTP 回调
数据 共 9 条导入链路（Excel 批注导入、抽样、AUE6 项目包、组成部分 zip、底稿模板 rar、外部底稿、表格模板、往来
导入 Excel、固定资产 sqlite），核心入库走 tedious bulkLoad 或批量 INSERT
底稿 真正取数核心在 CpasTable/engine + DisclosureService/dataSource：三种自定义公式
取数 （FS_CELL/CP_CELL/IN_CELL）+ 行列取数标签，由 OperationEngine 流水线驱动

第 1 章 数据采集逻辑
1.1 核心结论
本仓库不含采集工具源码。采集的执行主体是两个随 UFCPAS4 客户端发布的外部 exe（Delphi/C# 闭源），本仓库的
角色是拉起工具 + 消费结果数据：
| 工具    | 路径                          |     |     | 职责                         |     |
| ----- | --------------------------- | --- | --- | -------------------------- | --- |
| 数据采集工 | {UFCPAS4_PATH}/数据采集工具/数据采集工 |     |     | 连接客户财务软件库，抓取原始账务数据（无参数，自带界 |     |
| 具     | 具.exe                       |     |     | 面）                         |     |
数据转换系 {UFCPAS4_PATH}/DataConvert/P_DataConvert.e 把原始数据转换成 CPAS 标准格式写入项目库
| 统   | xe  |     |     |     |     |
| --- | --- | --- | --- | --- | --- |
1.2 exe 注册全景（workbenchExeInfo.js）
| key | exe |     | 参数  |     |     |
| --- | --- | --- | --- | --- | --- |
ufcpas4Main UFCPAS4.exe UserCode UserPwd ProjectCode ZcbfID ，workDir=SysBPL/
| dataDumpTool | 数据采集工具.exe |     | 无参（自带界面） |     |     |
| ------------ | ---------- | --- | -------- | --- | --- |
convertData P_DataConvert.exe ZcbfID zcbfName {SqlInstance} usercode xmqjStart xmqjEnd "0"
{SysDataBase}
| spaceClear | 作业系统空间清理工 |     | —   |     |     |
| ---------- | --------- | --- | --- | --- | --- |
具.exe
| batAttachDataba                  | SQL批量附加数据库工 |     | —   |         |       |
| -------------------------------- | ----------- | --- | --- | ------- | ----- |
| se                               | 具.exe       |     |     |         |       |
| 数据转换是按组成部分、按会计期间执行的（参数含期间起止日期，从  |             |     |     | sjxmcnd |  拆分）。 |
占位符来源（运行时由 electron 主进程解析）：
|                | ：读注册表  |                                      |     |     |  的   键 |
| -------------- | ------ | ------------------------------------ | --- | --- | ------ |
| {UFCPAS4_PATH} |        | HKEY_USERS\.DEFAULT\Software\UFCPAS4 |     |     | Path   |
{SysDataBase}  /  {SqlInstance} ：读  {UFCPAS4_PATH}/Config/UserConfig.ini  的  [DBCONNECTION]  节
|            |  /         |  /        | ：来自平台登录用户，UserPwd |     |  先 AES 解密再校验/补 md5 |
| ---------- | ---------- | --------- | ----------------- | --- | ------------------ |
| {UserCode} | {TrueName} | {UserPwd} |                   |     |                    |
1.3 启动链路
1. 工具注册：src/cpas-server/electron/workbench/workbenchExeInfo.js （L23-37）
2. 前端触发：工作台（workbench.js  L833）点击组成部分 →  getExeInfoUrl  拼协议 URL：
cpas://OpenLocalFile/?fileName=...&params=...&workDir=...&showParams=false

3. Electron 执行：electronRegister.service.ts （L1000-1034）拦截协议、 replaceUfCpasParams 替换 6 个占位
符后 child_process.exec 拉起 exe，并记录行为日志 behavior=305（打开应用）
4. 状态回写：转换完成后更新系统库 AudSys..sjxm_zcbf 的 ConvertStatus 、CWSoftName 、CWDataImportDate
关键结论：P_DataConvert.exe 与平台之间没有 HTTP 回调接口，状态完全靠数据库字段传递：
写：updateConvertStatus （convert.online.service.ts L43-52）直接 update [AudSys]..sjxm_zcbf set
ConvertStatus=...
读：myResponsibleParts.list SQL API 返回 CWSoftName / CWDataImportDate / DBIsExist （DBIsExist 用
DB_ID() 实时判断库是否附加在实例上）
同步：pm.syncProjectDbname.sql 等在联机端与本地间同步整行
1.4 工作台数据流
workbenchService.js 的 getApiData POST 到 /sqlapis/getApiData （header 带 cpasToken），调
myResponsibleParts.list （ReturnType=7 分页）
该 SQL 查 sjxm_zcbf inner join ProjectInfo ，分单机/联机两分支；联机分支带 sjxmuser 权限过滤
组成部分点击两条路径：openAuditTool （打开 web 审计作业）与 openAccountTool （触发 cpas:// 协议启动
UFCPAS4.exe）
1.5 单机转联机（convertToOnline）状态机
POST /project/convertToOnline （convert.online.service.ts）， while(true) 状态机按步骤推进，每步成功/失败都写
ConvertStatus （正数=步骤达成，负数=失败码，100=完成）：
0 → 2 分离数据库（shrinkDataBaseLog → killspid → sp_detach_db）
→ 3 改目录名（sjxmModifyDirectoryName）
→ 5 改 mdf/ldf 文件名 → sp_attach_db → modifyLogicalName（逻辑名与文件名一致）
→ 6 updateDataToNew（复制 sjxm_zcbf/sjxmuser/ProjectInfo 元数据到新库）
→ 100 完成
isReserveLocal=true 时原单机库重新 attach 保留；否则物理删除旧数据并把旧目录改名备份
convertToOffline 在代码库中不存在（联机转单机由外部程序完成）
1.6 平台侧消费采集数据
前端 → POST /sqlapis/getApiData
→ CpasApiController → CpasApiRunnerService.safeRun
→ SqlApiManagerService（sqlApi/impl/SqlApiManager.service.ts）
├─ 从 AudSys..SYS_Apis 表加载 SQL 模板
├─ 多数据源路由（dsName 空 → 系统库；否则 DbModule.dbServices[dsName]）
└─ 执行 SQL 或存储过程

1.7 采集相关核心表（PDM 文档佐证）
系统库：sjxm_zcbf （组成部分表：CWSoftName、CWDataImportDate、ConvertStatus、zcbfID、
DBName、xmqjs/xmqje 等）
项目库（每组成部分一库，按 Data_ID 区分年度账套）：
l_dwndInfo  /  l_dwndInfo_detail （账套信息：Data_ID、ND 年度、ByMonth、aDateS/aDateE、
Data_ID_Pre/Next）
|     |  科目表、 |  科目余额表（QCYE/JFFSE/DFFSE/QMYE/QCSL 数量/外币列） |     |     |
| --- | ----- | ----------------------------------------- | --- | --- |
CW_KMB CW_KMYYEB
|     | CW_PZB  凭证表（动态年度表  | CW_PZB+Data_ID | ）   |     |
| --- | ------------------ | -------------- | --- | --- |
 /  （辅助核算）
CW_FZZYYEB CW_FZZXMB
第 2 章 SQL API 体系（平台取数基础设施）
2.1 请求链路与端点
POST /sqlapis/getApiData  {name, params, reload}
  → CpasApiRunnerService.safeRun → SqlApiManagerService.getCpasApi
  → SqlApiDBLoaderService：select ReturnType,requireAuth,params,sqlText,dsName
      from [Audsys]..SYS_Apis where ApiName=?
  → 按 ReturnType 分派 SqlApiExecSqlService / SqlApiExecProcService
| 其他端点：getApisData | （批量顺序执行）、 |     | （apiKey 为键，支持  | nestApi: 前缀转发）、 |
| ---------------- | --------- | --- | -------------- | --------------- |
getApisDataOfApiKey
| update （updateTable 批量写入）、 | test（仅预览模板渲染）。 |     |     |     |
| -------------------------- | -------------- | --- | --- | --- |
2.2 SYS_Apis 表与 ReturnType 映射
SYS_Apis: ApiName(PK), paramsLen, params("a:type,b:type"), ReturnType, sqlText, dsName, requireAuth
SYS_ApiM: apiName, Name, Group, Memo（管理元数据）
| DB 值  | 枚举     |     | 效果                |     |
| ----- | ------ | --- | ----------------- | --- |
| 2 / 5 | LIST   |     | 结果集数组             |     |
| 51    | OBJECT |     | 首行对象              |     |
| 1 / 6 | UPDATE |     | 执行整段 T-SQL / 影响行数 |     |
3 / 4 / 41 ExecProc / OpenProcList / OpenProc 存储过程（无结果集 / 结果集 / 首行）
7 PagingList {total, rows[]} ，SQL 不能 order by 需  TOP 100 PERCENT
缓存现状：cpasApiMap  静态 Map 存在，但  sqlCache 默认  false （@Value  注解未生效）——当前每次请求都查
SYS_Apis 表。

2.3 SQL 模板语法（sqlTemplate.service.ts parseSql）
| 1. 自定义函数先解析：CustomRowToColumn("SQL片段", field) |     |     |     |  按参数双层循环展开行转列 |     |
| --------------------------------------------- | --- | --- | --- | ------------- | --- |
| 2. 注入系统库名：params["AudSys"] → 模板里              |     |     |     |  跨库引用         |     |
[#(AudSys)]..CWBBTX
| 3.  #para(x)：字符串加单引号（'' |     |  转义、 $ |  →  $$$$） |     |     |
| ----------------------- | --- | ------ | --------- | --- | --- |
| 4.  #(x)：仅数字直接替换（用于     |     |        |  等语法位）    |     |     |
IN(#(cols))
5. JFinal enjoy 引擎（4.9.2 经 jsweet 转译）渲染  #if(x)...#else...#end 、#for
| 6. 残留必填参数未传 → 抛  | "sql解析错误: 必填参数 x 未提供" |     |     |     |     |
| ---------------- | --------------------- | --- | --- | --- | --- |
存储过程执行：#(dbname)  占位缺 dbname 参数直接报  ；exec procName ?,?,...  按 params 顺序填实
NOT_DBNAME
参。
2.4 数据库服务封装（src/cpas-server/db）
AbstractDbService （Sequelize 基类）： getQueryList （内置 50 次×100ms 等连接就绪）、 findFirst 、
|            | （异常吞掉返回 message 字符串）、 |     |            | （分号拆分批量）、batExecSqlTransaction | （显式 |
| ---------- | --------------------- | --- | ---------- | ------------------------------ | --- |
| executeSql |                       |     | batExecSql |                                |     |
commit/rollback）
|               | ：系统库，含  |  逻辑删除状态机（SYNC/INSERT/DELETE/UPDATE × |     |     |     |
| ------------- | ------- | ------------------------------------ | --- | --- | --- |
| AudSysService |         | updateFlag                           |     |     |     |
INSERT/DELETE/UPDATE_RENAME 转移表）
ProjectDbService：项目库空壳，需按 dbname 手动  （账龄模块如此动态建连）
connect({database})
SqliteService ：dbname = "sqlite|相对路径"  约定建 sqlite 连接；mssql/sqlite 差异主要在 dialect 与 SQL 方言
连接语言统一  Chinese_Simplified_Pinyin_BIN ；tedious 连接  requestTimeout  600 分钟
第 3 章 账套数据加工链（存储过程）
3.1 主链
CW_KMYYEB / CW_KMB / CW_FZZYYEB（采集落地）
  → PROC_SubjectSDB_init → BB_KMSDB（科目审定表）
  → PROC_AssistSDB_init  → BB_FZZSDB（辅助审定表）
  → 调整重算：PROC_SubjectSDB_ZBAdjust_ReCal（账表调整）
              PROC_SubjectSDB_AuditAdjust_ReCal（审定调整）
  → PROC_ReportItem_Recal → BB_ReportItemsData（报表项目基础数据）
调度入口  merge.account.reportItem.reCal.sql ：BB_KMSDB 无数据走 init；有数据且  isRecalTZ  走 6 个调整重算过程
（自动补科目 → 账表调整 → 审定调整 → 自动补辅助 → 辅助账表/审定调整）；最后必跑  PROC_ReportItem_Recal 。
3.2 PROC_SubjectSDB_init（科目审定表初始化）
读：CW_KMYYEB、CW_KMB、上年度 BB_KMSDB；写：BB_KMSDB

isForceInit=1 全删重灌；取 min(YF) 与 PROC_GetCutOffDate 截止月
从 CW_KMB 挂期初/数量/外币期初，按 YF=@byMonth 从 CW_KMYYEB 回填本期借贷累计发生额、期末余额
Func_geData_ID_Pre 找上年度账套补 QCLJFSE （期初累计发生额）
收尾联动：自动补科目 → 账表调整重算 → 审定调整重算
3.3 核心公式（PROC_SubjectSDB_ZBAdjust_ReCal 源码摘录）
-- 先清零 12 个调整列；临时表汇总调整明细（按科目编号前缀归集到各级科目）
-- 未审数 = 账面 ± 账表调整（Oper = 科目方向 借+1 / 贷-1）
QCWSS = QCYE + Oper*(QCZBJFJE - QCZBDFJE)
WSS = QMYE + Oper*(ZBJFJE - ZBDFJE)
WSLJFSE = LJFSE + Oper*((ZBJFFSE-QCZBHCJFFSE) - (ZBDFFSE-QCZBHCDFFSE))
-- 审定数 = 未审数 ± 账项调整 ± 重分类
SDS = WSS + Oper*(ZXJFJE-ZXDFJE + CFLJFJE-CFLDFJE)
调整明细来源 BB_TZFLBill（BillType=0）join BB_TZFLDetail ，按 TZQJ （0=期初/1=本期）、 IsNoCalFSE （不计发生
额）、IsHCFSE （红字冲回）分组 SUM 回写。
3.4 PROC_ReportItem_Recal 逻辑
1. 清零 BB_ReportItemsData 全部 50+ 金额列
2. 算方向运行符 Operation ：报表项目方向与科目方向一致 +1 否则 -1
3. 非合计项（SumLevel=0）： BB_KMSDB join BB_ReportItemsRef group by FKGUID ，余额类乘 Operation、发生额
直加，一次回写 50+ 列
4. 上年数：Func_geData_ID_Pre 找上年度账套，按标准报表项目 Code 对齐回填 SNS（损益类取 SDLJFSE）；再算
SNSDS = SNS + Oper*(SNSTZJFJE-SNSTZDFJE)
5. 合计项按 Max(SumLevel) 逐层 while 循环汇总（含企业提供数 QYQCYE/QYQMYE）
3.5 BB_ReportItemsData 字段族
结构：GUID、Data_ID、Code（3 位一级 / 001001 子级）、ItemName、AliasItemName、FX、Type、
OwnerReport、JC、SumLevel、IsZDZH
账面：QCYE / QMYE / QCLJFSE / JFLJFSE / DFLJFSE / LJFSE
调整：QCZB*（账表）、ZB*（期末账表）、QCZX*/ZX*（账项）、QCCFL*/CFL*（重分类）、QCQT*/QT*（其
他）、红冲 QCZBHC*
结果：QCWSS / WSS（未审）、QCSDS / SDS（审定）、SNS / SNSDS（上年）、QYQCYE / QYQMYE（企业
提供）
全部金额列 numeric(28,4) ；唯一索引 (Data_ID, Code)
BB_KMSDB 与之同构（KMBH 代替 Code，联合主键 Data_ID+KMBH），另含数量列（QCSL/QMSL 等 float）与外
币列（WQCYE 等）。

（科目↔报表项目）、BB_ReportItemsSumRef（合计关系）、BB_ReportItemsRef_AllIn
科目映射：BB_ReportItemsRef 。
初始化模板  merge.account.reportItem.init.sql  从系统库  ReportItems  复制结构，并用游标解析科目词库自动建映射
（含"坏账准备"匹配 JC=2 二级，其余 JC=1 一级）。
第 4 章 底稿取数逻辑
4.1 两套底稿体系
1.  WorkPaper/draft  系列：Excel 文件型底稿的模板导入导出与文件树管理，本身不做数值取数（ReadMe.md 明确
职责）
2.  CpasTable/engine +  DisclosureService/dataSource ：真正的取数核心，通过公式和标签触发
4.2 取数的四种方式
| 方式  | 格式  |     | 数据来源 |     |
| --- | --- | --- | ---- | --- |
行列取数标 行取数:(CP,表名)  /  列取数:(FS,负债类) design_cell 或 BB_ReportItemsData
签
FS_CELL FS_CELL("base.reportItems","货币资金-库存现金","审定 数据模型取数源（DataModel 表注册的
|     | 数","2017") |     | SQL） |     |
| --- | ---------- | --- | ---- | --- |
CP_CELL CP_CELL("未审财务报表-负债表","库存现金","期初余额") 其他底稿表（design_table +
design_cell）
| IN_CELL | IN_CELL("固定资产","期末余额") |     | 本表内坐标引用 |     |
| ------- | ---------------------- | --- | ------- | --- |
4.3 触发入口（cpas-table-operation.controller.ts）
| 端点                         |        | 行为      |     |     |
| -------------------------- | ------ | ------- | --- | --- |
| dataRecalculate            | （L153） | 单表重算    |     |     |
| batchDataRecalculate（L243） |        | 批量重算 →  |     |  →  |
batchReCalculates
CalculateService.run
batchDataAndVerifyRecalculate （L654） 重算+勾稽组合（isForceRecalc 语义专为 Excel 导入）
| batchVerifyRecalculate |  /  batchVerifyRecalculateAll | 只勾稽不重算 |     |     |
| ---------------------- | ----------------------------- | ------ | --- | --- |
parseCustomFormula  /  parseFormula / 公式解析（富文本中  {FS_CELL(...)} ）
parseFormulaByContent

4.4 OperationEngine 流水线（四种装配组合）
| 模式 解析器队列                                            |     |     |     |
| --------------------------------------------------- | --- | --- | --- |
| FULL 普通 期间类型 → 逻辑公式(Dr/Dc) → 行列取数 → Excel聚合 → 单元格公式 |     |     |     |
| FULL + isZb 制表 期间类型 → 逻辑公式 → 单元格公式                  |     |     |     |
| SIMPLE 合并制表 期间类型 → Excel聚合 → 单元格公式                  |     |     |     |
| SIMPLE 普通 Excel聚合 → 单元格公式（无行列取数、无自定义公式）             |     |     |     |
parseState 状态机： READY → RUNNING → FINISH / NO_CHANGE / ERROR ，任一解析器 FINISH 即标记有变化
顺序强约束：期间类型必须最先（动态行列依赖它），自定义公式必须先算稳定才能整表 rebuild Excel 公式
逻辑公式 Dr/Dc 由  LogicFormulaService.registerFormula  注册后  scanAndExecuteAllFormula 扫描执行
4.5 行列取数标签完整语法（RowColumnData.ts）
1. 行取数：rmap 选择、cmap 全表      2. 列取数：rmap 全表、cmap 选择
3. 取数源两种：CpasTable / 报表基础数据
4. CpasTable 通配符：
   行取数:%试算平衡表-期初   → 2021-试算平衡表-期初, 2022-试算平衡表-期初（多表）
   行取数:%试算平衡表%       → 各年度各期全部
   行取数:未审财务报表-负债表 → 单表
5. 行取数:报表基础数据            （from='b'）
带前缀语法：行取数:(CP,表名) → from='c'；行取数:(FS,负债类) → from='b'
埋点位置：行标签在每行最后一列 JSON config 的  r_tag  数组；列标签在表头  headerColumn[i].config.c_tag
数组
只有 rmap/cmap 非空的行列纳入；检测结构 CheckTagResult { isHasGetDataTag, dataTagMaps }
执行顺序：先行取数、后列取数（列权重大于行，列覆盖行）
回填：Promise.all  并发请求  /disclosure/fetchData （合并走  /merge/  前缀），按  cellsMap["rmap_cmap"] =
"rindex_cindex"  坐标映射原地写入
参数
DataModelFetchDataDto { dbname, zcbfid?, tid?, from:"b"|"c", scope, rmap[], cmap[] }
4.6 FS_CELL 完整机制
| 参数：FS_CELL(数据模型表名, 主键值, 列名, 年度标签) |     | ，少于 4 参返回 0。 |     |
| --------------------------------- | --- | ------------ | --- |
两级缓存：
| 缓存                 | key   | value          |         |
| ------------------ | ----- | -------------- | ------- |
| memoryCacheFormula | 完整公式串 | 最终数值           |         |
|                    | 表名_年度 | "无数据"          |         |
| memoryCacheTable   |       | 整个数据集数组；哨兵字符串  |  表示查过为空 |

数仓联动（多线程批量场景）：resId （FormulaRepository.initRepository 生成的 nanoid）存在时，通过 POST
/cpasTableOperation/formulaRepository 与主进程数仓同步（action: get/getBlock/set），底层 Map<resId,
Map<"memoryCacheFormula"|"memoryCacheTable", {}>> ，结束 removeRepository 清空。
年度换算：dataId 为纯数字直接用；否则走 getYears：
const obj = { 上五年: y-5, ..., 上一年: y-1, 本年: y, 下一年: y+1, ..., 下三年: y+3 };
// y 来源：合并系统走 /cpasMergeTableEngine/getProjectPeriodSettings
// 单机走 /cpasTableEngine/getAuditYear
注意 dataId.startsWith("{") 动态占位未解析时直接返回 0。
取数请求：POST /disclosure/getDisclosureApiData ，body {name, data_id, dbName} 。行字段名固定叫 "主键" ：
for (row of result) {
if (!row["主键"]) { warn("未检测到取数源主键"); return 0; }
if (row["主键"] === primaryKey) return row[columnName];
}
无数据时缓存哨兵 "无数据" 并返回 0。
4.7 CP_CELL 完整机制
参数：3 参 [表名, rmap, cmap] 或 4 参加 data_id。
表名|后缀 语法决定查哪张物理表：
type = parseTName[1].trim() === "前" ? "ds" : "zl";
// "表名|前" → design_cell_notes，"表名|后" → design_cell_zl，无后缀 → design_cell
缓存 key：fs 按 表名_年度 分块，ds/zl 不分。
两次请求：GET /cpasTableEngine/getCpasTableByName （拿 tid）→ GET /cpasTableEngine/getCpasCellByTid （拿单元格
集），按 rmap+cmap 双键精确匹配。
防串数保护：取到的 dValue 若仍是 =FS/=CP 公式串（取数源接口不对或未清数据），按 0 处理。
4.8 IN_CELL 与求值
// 坐标翻译
rowIndex = getRowIndexByRmap(rmap, data) + 1; // data[*][0] 找 rmap
columnIndex = getColumnIndexByCmap(cmap, data); // 表头映射找列号
excelCoords = createCellPos(columnIndex) + rowIndex; // 如 "B5"，找不到返回 "0"

// 求值：HyperFormula 把整张 displayData 建成 Sheet0 作为上下文
HyperFormula.buildFromArray(tableData, { licenseKey: "gpl-v3", evaluateNullToZero: true });
let value = hyperInstance.calculateFormula(parseFormulaResult, 0); // 解决浮点误差
const fixedValue = new BigNumber(value).toFixed(4);                // 统一 4 位小数
写回由   完成：源数据（公式原样）与计算副本分离，
OperationCellParse.parseCustomFormula
rebuildAndRecalculate()  后  getSheetValues(0)  得 dValueData，落库时  sourceGridData.data  保留公式。
公式提取正则：
// 从 {..} 提取（附注注释场景）
const reg = /(?<=\{)(.*?)(?=\})/g;
// 提取自定义函数因子（支持最多三层嵌套括号），去重
const formula_reg = /(CP_CELL|FS_CELL|V_CROSS|IN_CELL|N)\((?:[^)(]+|\((?:[^)(]+|\([^)(]*\))*\))*\)/g;
4.9 取数源服务（ds.service.ts）源码细节
DataModel 表（系统库，"作业平台取数公式数据模型"）
| 字段                                            | 说明                         |         |
| --------------------------------------------- | -------------------------- | ------- |
| DMID / XH                                     | 主键 / 排序                    |         |
| DMName                                        | 数据模型名（如 base.reportItems）  |         |
| GroupName                                     | 企业基础数据 /                   | 底稿结构化数据 |
| ReportItemCode / ReportItemName / DataSrcName | 报表项目归属与菜单显示                |         |
| SqlStr                                        | nvarchar(4000) SQL 模板，含占位符 |         |
| SqlType                                       | 0=查询，1=存储过程                |         |
菜单树两级：GroupName → ReportItemCode → DMName。路由
 双前缀注册。
@Controller(["disclosure","merge/disclosure"])
占位符替换（关键技巧）
sqlstr = sqlstr.replaceAll("[@dbName]", dbname_val);
if (zcbfid_val && zcbfid_val !== "*") {
  // 闭引号技巧：模板里是 where Data_ID='[@Year]'
  // 替换后变成 where Data_ID='2017' and zcbfid='zcbf001'
  sqlstr = sqlstr.replaceAll("[@Year]", `${params.data_id}' and zcbfid='${params.zcbfid}`);
}

SqlType=0 vs SqlType=1
0（查询） 1（存储过程）
包装 select top N fields from (模板) T where (…) order 替换 [@Fields]/[@Where]/[@Order]/[@top] 四占
by … 位符
top 格式 top N 关键字 纯数字串
负 top 倒序取前 N（order asc/desc 互换） 同
where 转 无 '' 转义
义
默认 3 asc （第 3 列 Code） 传空串
order
失败 抛异常 console.log(e) 吞掉，返回 undefined
queryMeta=true 时走 sp_describe_first_result_set 式元数据查询，SQL 类型映射 JS 类型（BIT→boolean、
DECIMAL→number、DATETIME→Date、BINARY→Uint8Array）。
fetchData 四种 SQL 拼接
场景 1：传 tid + from='c' —— A/B 表 left join 比对：
-- A 表=目标表（tid 精确定位，提供 rindex 行号）
select a.rindex,a.rmap,a.cmap,a.dValue
from [库]..design_cell a join [库]..design_table b on a.tid=b.tid
where b.tid='${tid}' and isnull(a.rmap,'')<>''
and a.cmap not in('key','config','ItemName') and a.rmap in(...)
-- B 表=源表（scope 通配，表名前 4 位年份拼进 cmap 对齐）
select a.rmap, left(b.name,4)+isnull(a.cmap,'') as cmap, a.dValue
from ... where b.name like '${scope}'
-- left join on a.rmap=b.rmap and a.cmap=b.cmap → A有B无则 null
场景 2：from='b' —— BB_ReportItemsData UNPIVOT：
select itemName as rmap, isnull(Data_ID,'')+isnull(yeType,'') as cmap, dValue
from [库]..BB_ReportItemsData
UNPIVOT(dValue FOR yeType IN([QCYE],[QMYE]))t -- cmap.slice(4) 去年份前缀
where itemName in(...)
场景 3：试算平衡特殊处理（解决第一年报表"上年数"列）：
union all select a.rmap,
cast((convert(int, LEFT(b.name,4))-1) as varchar(5)) + SUBSTRING(isnull(a.cmap,''),3,50) as cmap,
a.dValue
from ... where b.type='fs'
and b.name=(select min(name) from design_table where name like '%试算平衡-利润表_上期')

最终输出统一 PIVOT：
select * from (上面长表)pt pivot(max(dValue) for cmap in([2019QCYE],[2019QMYE])) p;
-- 行=报表项目(rmap)，列=各 cmap；dValue 是 varchar(255)，max() 是字符串比较
notes_tree 关联
-- ds：notes_tree.fid = design_table.tid
-- zl：design_table.tid = notes_tree.fid + '-zl'
notes_tree 关键字段：
id/pid/orderNo/title/fid/Data_ID/disclosureContent(Note)/associatedReport/isIncludeTable/updateFlag。
4.10 底层数据链全景
CW_KMYYEB/CW_KMB/CW_FZZXMB（账套层）
→ BB_KMSDB（审计层，PROC_SubjectSDB_init + 调整重算）
→ PROC_ReportItem_Recal → BB_ReportItemsData（报表项目基础数据）
→ 科目↔报表项目映射在 BB_ReportItemsRef
→ 底稿取数（公式/标签）→ design_cell.dValue
→ ReportManager/report.service.ts 反向汇总回写（审定报表 FZ 列）
报表取数与底稿取数共享同一套基础设施（design_table / design_cell / BB_ReportItemsData / DataModel 四张核心
表），报表是底稿取数链条的下游回写环节。
第 5 章 Excel 导入核心链路（附注/报表）
5.1 三步流程总览
步骤 端点 说明
1 提取+匹 POST 解析批注、节点匹配、自动列匹配，落盘 Temp/excel.json
配 cpasTableEngine/importExcelToColumnMatc （GB2312）
h
2 人工调整 POST 前端可修正列匹配后再匹配一次
cpasTableEngine/autoMathExcelToSystem
3 入库 POST cpasTableEngine/saveExcelImport 合并、转换、 createCpasTable 、强制重算
5.2 批注标签规范（ExcelService.excelFileConvertJson）
批注取 cell.c[0].t ，. 前缀 = 附注节点名（同组归一个节点），标签全集：

| 批注标签              |                    |              | 作用        |        |
| ----------------- | ------------------ | ------------ | --------- | ------ |
| .{表头开始列}          |  /  .{表头结束行}       |  /  .{表头结束列} | 表头区定位     |        |
| .{表前注释}           | .{表后注释}            | .{首行内容}.<值>  |           |        |
|                   |  /                 |  /           | 注释行       |        |
| .{内容开始行}          |  /  .{内容结束行}       |              | 数据区       |        |
| {内容开始行}.cmap.<名称> |                    |              | 列映射，可叠加   | .{豁免列} |
| .{行配置标记}<JSON>    |                    |              | 行配置（rId）  |        |
| .{列隐藏}            |                    |              | 隐藏列       |        |
| .{豁免列}            |  /  豁免列excel公式.<值> |              | 豁免列坐标与替换值 |        |
| 行运算符公式.<值>        |                    |              | 行运算公式     |        |
空行与"新增浮动行占位"空行删除并  ，新增行自动补 rId，重复 rId 重新生成。
refreshExcelFormula
5.3 节点匹配：三级回退全等（非模糊）
① draftMatchData（底稿对应关系，ds用title / fs用name）
② 系统节点列表（同上全等）
③ 系统 disclosureContent（表前注释首行）
节点名预处理：去  （ 开头序号（slice(3)）、去圆圈序号 ①②③（正则  /^[\u20E3-\u218F\u2460-\u25FF]+/）。未命中
但带注释的节点也进入结果（无 tid），供前端手动关联。
fs 类型走  account.getFSTableNames  SQL API；ds 类型走  disclosure/notes 接口。
5.4 列匹配算法（autoColumnDataMatcher）
// 双方 cmap 全等 + 豁免列必须"两边同为豁免或同为非豁免"
if (i > 0 && j > 0 && excelCmapVal === systemCmapVal && isExecutehy && !isContain) {
  columnsIndex.push(excel豁免 && system豁免 ? `${i}-${j}-isHm` : `${i}-${j}`);
}
// 输出 ["1-1","2-2-isHm",...]；excel 列只允许匹配一次（isContain 判重）
// 系统豁免列来自 headerColumn[i].config.p_exclude

5.5 saveImport 完整流程
isForceImport 改名: rmap + "-" + (行号+2) + "-重复"（同步传 generalCellMetas 迁样式）
→ manualColumnsIndex merge（手动覆盖自动，matchColumnsIndex 改名 mathColumnsIndex）
→ nodes 过滤（只导勾选节点）
→ convertCpasData/generalCellMetas（cellsMeta 按 rmap_浮动行标签 键迁移，浮动行继承母行样式）
→ disclosureContent(Note) 合并进 cpasDesc（保留原 id 只覆盖 describe）
→ clearCpasTableFormula（OperationClearFormula.clearFormulas）
→ diffData 写入 → 转入库结构 → createCpasTable
→ ds: batchDataAndVerifyRecalculate(isForceRecalc) / fs: batchVerifyRecalculate
diffData 写入算法：新建 行数=excel行数、列数=系统列数 的矩阵，只填匹配列（含 0-0 rmap 列与行配置列），未匹配
列一律清空（注释明确：不保留没匹配上的系统数据，防止串行）；豁免列（三段坐标）和 Excel 公式单元格取
sourceExcelData（带公式）。
5.6 入库五表与字段
表 关键字段
design_table tid（md5(data_id+表名)，zl 加 -zl ）、name、type、config、isVerify、updateFlag、zcbfid
design_column cid、tid、pid、label、cov、lov、ish、level、config、cmap、keyword、formula、formulaState、
isDynamic
design_row rid、tid、ov、config、rmap、formula、formulaState、isDynamic
design_cell/_ id、rid、cid、rValue(原始值/公式)、dValue(显示值)、rindex、cindex、rmap、cmap、config(JSON)、
notes/_zl vFormula、verification、oValue、zcbfid；ds 额外 aValue/dxValue/mnValue
design_table_ tid、category（disclosureContent/disclosureContentNote）、describe
desc
分表规则 getTableNameByType ：fs→ design_cell ，ds→ design_cell_notes ，zl→design_cell_zl 。
tid 冲突处理： clearCpasTableMarkDel 清 updateFlag∈{2,-1} 的重名逻辑删除残留 → removeCpasTable 物理删旧
（verify→table→column→row→cell→desc 顺序）→ 重插。
5.7 IGridData → CpasTableDataDto 转换（saveToServerByCpasData）
rmap：i===0 空串；行取 rowMaps[i-1]；隐藏列 j===0→"key"；配置列 j===lastHeader→"config"
cmap：columnMaps[j-1]
rValue=source 原始值（公式），dValue=显示值；zl 模式 rValueFormat = dValueFormat
行配置 JSON 过滤前端私有字段后存 config；rId 存 rid，cid 取叶子列 key
ov = 全表序号（sourceRow.length * i + j）
合并系统 isRecByTzs （调整数重算）时按 aValue（调整前值）+ mnValue/dxValue（BigNumber 相加）重建
rValue/dValue

5.8 TSaveToServerService = workerpool 线程池（非子进程）
global.cpas_table_pool = workerpool.pool(worker_js_path, {
workerType: "thread", minWorkers: cpus < 2 ? 1 : cpus // 满核
});
// transformToServerDataWorker 内部就是 saveToServerByCpasData，单表失败进 errors 不中断
5.9 三个重算接口差异
接口 行为
reCalculate 单表重算，不做勾稽（注释：TODO 后期废弃）
batchDataAndVerifyR 批量重算+勾稽：formulaOff 过滤 → batchReCalculates(isForceRecalc) → dynamicVerify 补动态勾
ecalculate 稽 → FormulaRepository.initRepository → batchReVerify
batchVerifyRecalcul 只勾稽不重算
ate
第 6 章 其余导入体系
6.1 合并组成部分 zip 导入（bulkInsert.service.ts，1108 行）
上报包协议：{ t: 表名, f: ["字段 类型",...], rows: [[v1,v2,...]] } + part_info.json
入口：IPC exportImportData-start / POST merge/batImportPartData
流程：dropIndex 提速 → 逐组分解压（Tools/rar.exe）
→ 结构校验(INFORMATION_SCHEMA.COLUMNS 联查 sys.columns)
→ 缺表/缺 zcbfid 列跳过记录 errorMsg → 计算列不导 → 字段超长自动 ALTER(nvarchar)
→ 删旧(delete where zcbfid=) → tedious newBulkLoad
（bulkOption: checkConstraints=false, fireTriggers=false, keepNulls=false, lockTable=true）
→ 往来表 BB_ReportIntercourse 补 fromType=1/checked=0/Data_ID/DG_NAME
→ 单体法定特殊：design_cell_notes 改用 design_cell_zl.json，tid 去 -zl 后缀
收尾：afterImportOnePart 更新 l_dwndInfo(.detail).id=zcbfid
→ 重建索引 → DBCC SHRINKDATABASE
进度通过 IPC event.sender.send('exportImportData-progress', ...) 回推。
6.2 数据上报（UploadPartDataService）
按 CpasCloudSvr/data/sync/UploadReport.json 的表清单导出 → 每表一个 json（ {t,f,rows} 与导入格式对称）→ 生成
part_info.json（ {v:"1.0", zcbfid, zcbfName, reportUser, reportDate, tables:[{tableName,rowCount}]} ）→ Archiver
压 zip → POST /merge/fileApi/partData/data.upload （fromType 1=part / 2=merge）。与 CpasCloudSvr（C++
云端服务）共享同一 part_info 协议。

6.3 合并用复制（MergeUsePartService，1492 行）
copyToMergeUsePart：design 9 张表用模板数据（mergeUseTemplateZcbfid）、业务表用单体数据
（design_table/cell/cell_notes/cell_zl/column/row/table_desc/verify/notes_tree）
→ 7 步计算：复制内部往来 → 补附注行 → 修字段名 → 算报表数 → 算附注数
→ updatePeriodTypeData → 模拟调整重算 + batchDataRecalculate(SIMPLE) + 勾稽
→ merge.updateNotesOValue：dValue 复制为 oValue 原始值
6.4 AUE6 项目包导入（project.service.ts）
rar 解压 → ImpExp/ImpExpInfo.db（SQLite）四模型：sjuser/sjxm_zcbf/sjxmuser/ProjectInfo
→ 老包补列（pragma table_info + ALTER TABLE 7 列：AuditReportTemplate 等）
→ 项目信息 delete+insert（约 28 列，'null' 字符串替换为真 null）
→ 逐组成部分：同库存在则 killspid + sp_detach_db → cpSync 复制 mdf/ndf/ldf → sp_attach_db
→ 组成部分 INSERT 约 60 列（含 CWSoftName/CWDataImportDate/ConvertStatus/LocalZcbfID）
→ 成员只增不改（UserCode+zcbfID 判存在，10 列）
getProjectDataPathIfnfo：导入前预览，只解 *.db 返回项目/组分清单供勾选
6.5 其他导入链路
链路 要点
底稿模板 密码 www.ufaud.com ；包=模板目录+ImpExpInfo.db；SQLite 四中转表
rar mbsjdg/mbsjjd/mbsjdgSheet/StepLinkWorkPaper + mbType 登记（MBCode 三位零填充自增）；SQLite 中模
板名统一被覆盖为 rar 文件名
表格模板 新版包内一层"公共模板/专用模板"目录，老版无 → 先清同名 → 复制；reportType 优先级：入参 > data.db config
（报告模 表 > 文件名含"国企/上市"；tid 重刷 keyByMd5(dateId,name)，zl 加 -zl；config.formulaOff 强制改回 false；公
板） 式不落独立列：单元格公式在 design_cell.config JSON + vFormula 列，行公式在 design_row.formula
外部底稿 文件名格式 （索引号）底稿名称 ；索引号优先级：前端指定 > 文件名括号 > 阶段内 max(DGSYH) 自增 > DG+时间
docx/xls 戳随机；重名/索引号重复即跳过；三步事务：校验 → SQL → 文件IO，IO 成功才 commit；DGlb=3 外部导入
x
审计抽样 动态 create table（自带 AutoId identity + IsChecked bit）；元数据 sample_tables/sample_fields；tedious
Excel bulkLoad + RowsDataIterable 每 1000 行推进度；进度是 HTTP chunked JSON Lines，不是 SSE；失败调
delSampleTable 回滚
合并往来 ExcelJS 解析，表头单元格批注必须是 JSON {"dataField":"数据库字段名"}；无批注列不导入；copyFdToHby
Excel 三步事务：删旧(fromType=1) → 复制自动导入 → 复制账龄配置 BB_ReportIntercourse_zl
固定资产 sqlite → SQL Server 用 sequelize bulkInsert（非 tedious）；仅 FA_DepreFuncItem / FA_DepreFuncType 两表
全量删重灌
合并系统模板导入（importTemplatesToSqlServer）：本地 rar（密码 www.ufaud.com）解出 data.db（sqlite），
sqlite_master 拿表清单 → 与 SQL Server 字段比对 → 删旧 → tedious bulkLoad（补 zcbfid=TemplateData）→ fs
表名加 {DataID}_ 前缀防重 → 模板目录复制到项目 Template 目录。

第 7 章 账龄分析逻辑（zLAnalysisTool.ts，Delphi 移植）
7.1 入口与参数
POST /accountAge/executeZLAnalysis ：{dbname, zlDataId, kmbh, jzyf 截止月, importChecked 期初导入,
zlZoneListOfShow 账龄区间, zlTypeIndex} 。动态 new ProjectDbService().connect({database: dbname}) ，res.write 流
式推 JSON 进度。
zlTypeIndex：0=AgingAnalysisNew 账面、1=AgingAnalysisWss 未审/账面账龄表、2=AgingAnalysisSDS 审定账
龄表。
账龄表结构以 PDM/账龄分析相关表.xlsx 为准。代码中实证的表：AgingAnalysisNew（主表，Y1-Y10 奇偶段 + M1-
M12 月段 + Pre 前缀上期 + Cal* 计算列）、 AgingAnalysisWss（未审）、AgingAnalysisSDS（审定）、
CW_FZZYYEB_SUM / CW_KMYYEB_SUM （月合计）、ZlZoneShowNew （区间配置）、ZLImportTemp / ZLImportNew （期初导
入）、ZLFzhsSet （辅助设置）、 FLZYF （分期月份）。
7.2 Execute 八步
① InitAnalysisZlDatas：BB_FZZSDB/BB_KMSDB → 生成账龄单元树写入 AgingAnalysisNew
（ID = KMBH*|*HSXMLXBH*|*HSXMBH，ZLLY='ZZ'/'FZZ'）
② CalculateCurrentPeriodQCQM：期初期末回填（或从 ZLImportTemp 导入推算）
③ CreateTempTable：建 CW_FZZYYEB_SUM / CW_KMYYEB_SUM
④ DoWork 主循环：对 ZlDataId-5 至 ZlDataId 逐年回溯（仅 FLZYF 有数据的年度）
ChangeDirection（借贷归整为 CalJFFSE/CalDFFSE）
→ MoveZLData 移段：Y10+=Y9, Y9=Y7, Y7=Y5, Y5=Y3, Y3=Y1, Y1=本期发生额
→ CalculateZLData 抵扣：按 CalQCYE 正负与 CalDKE 从远段(Y10)到近段(Y1)依次冲减
→ 上一年额外 DoLastZL + DoMoreThanNYear + 月段 M1..M12 逐段"转换→移段→抵扣"
⑤ ClearMonthZlAtYearZLIsNull（MonthStage 位标记清理月/年不一致）
⑥ GenerateZLFzhsSet
⑦ MakeAdjustData（按 zlTypeIndex）：
1 = MakeZBZL_Ex → 复制到 AgingAnalysisWss，遍历 BB_TZFLBill/Detail 调整分录
（TZLX=1 重分类走 DoCFLZL/DKZLAutoIn/ZLAreaYWH/ZLAreaNull；TZLX=0 普通调整）
2 = 再加 MakeSDZL_Ex → AgingAnalysisSDS（BillType=1）
⑧ MakeNextQCZL：结果写 ZLImportNew（Data_ID+1），下年期初免导入
依赖关系：账龄与报表项目共享审定表 BB_KMSDB / BB_FZZSDB —— 先审定、后账龄。
7.3 与合并系统的账龄衔接
往来模块 createZhangLingFdToHby 把账龄显示列配置（[key] 前缀 Pre 为期初、否则期末）从单体复制到合并用
BB_ReportIntercourse_zl ；云端同步清单 UploadReport.json 含 ZlZoneShowNew （账龄区间配置表）。

第 8 章 合并系统架构
8.1 combine-system 目录职责
服务 职责
BulkInsertService 组成部分数据导入（第 6.1 节）
UploadPartDataService 数据上报打包（第 6.2 节）
MergeDbService 合并库生命周期：建库/建表/删除/备份恢复
MergeUsePartService 合并用组成部分核心（第 6.3 节）
MergeTrialBalancService 合并试算平衡表
MergeWindowService 合并独立窗口（BrowserWindow）
8.2 合并计算全流程
① 每个组成部分客户端（单机平台）用 UploadPartDataService 打包 zip 上报服务器
② 合并端收 exportImportData-start，BulkInsertService 解压 bulkLoad 进合并库
③ copyToMergeUsePart 把各组分数据复制对齐到"合并用"zcbfid
④ 触发 merge/cpasTableOperation/batchDataRecalculate 大表公式引擎重算
⑤ Merge 端 tasks 服务做任务队列调度
任务队列（Merge/tasks.service.ts）：内存队列 + projectMergeDb..tasks 表持久化（pending 状态），FIFO/LIFO，
maxConcurrentTasks=3，任务体 axios 自调
http://localhost:8070/cpasApi/merge/cpasTableOperation/batchDataRecalculate 。
8.3 合并系统与单机的差异机制
// 同一控制器双路由注册
@Controller(["cpasTableOperation", "merge/cpasTableOperation"])
// @logicDBName 装饰器：URL 含 /merge/ 时返回 "dbname|||zcbfid"
// SQL 层辅助函数：
whereZCBFID(zcbfid, type) // full→where zcbfid='..' / part→and zcbfid='..' / 空→''
insertFiledZCBFID(...) // 合并模式新增 DataCreateTime/oValue/ref_id 留痕字段
getDataId: if(zcbfid_val){ isOnline = true; } // 合并系统一律走线上期间设置
8.4 CpasCloudSvr（C++ 云端服务数据目录）
无源码，只有 data/ 运行数据：SyncMain.json（同步清单：底稿平台 sjjd/dglinkinfo + 报告系统账套/报表项目/调整
分录/财务报表/附注）、JOSN说明.md（行数据 JSON 协议 {v,t,st,option,f:[{s,l,t,k}],sub:[]}）、part_info.json
（与 electron 上报协议一致）、UploadReport.json（上传表清单，含 fromTable 中间清理表机制）。

第 9 章 全链路风险与缺陷清单（源码实证）
| # 位置 | 问题  |     |
| ---- | --- | --- |
1 ds.service.ts fetchData tid+from='b' 分支 UNPIVOT 缺右括号，会生成非法 SQL（疑似缺陷）
2 ds.service / zLAnalysisTool SQL 全字符串拼接，where/order/scope/reportItem 无参数化（SqlType=1 仅有   转
''
义），注入风险
3 cpas-table-excel.service Temp/excel.json  磁盘共享状态（GB2312），多用户并发导入互相覆盖
| 4 RowColumnData.executeFill | 原地写数据但返回的是入参对象（变量名误导，功能等价） |     |
| --------------------------- | -------------------------- | --- |
Data
| 5 CustomFormulaService | memoryYears 赋值后读取处被注释，每次重算年度 |                        |
| ---------------------- | ---------------------------- | ---------------------- |
| 6 ds.service PIVOT     | max(dValue)                  |  对 varchar 做聚合，字符串比较语义 |
| 7 cmap.slice(4)        | 硬编码去 4 位年份前缀，cmap 必须严格以年度开头  |                        |
8 zLAnalysisTool rows.map(item => \`` ' ${item['zlguid']}\ )` 缺结尾单引号（潜在 SQL 语法瑕疵）
MakeSDZL_Ex
9 getDisclosureApiData 合并系统 zcbfid 注入依赖模板中  [@Year]  位于单引号内的约定，脆弱
| 1 SqlApiManager | sqlCache 默认 false，每次请求查 SYS_Apis |     |
| --------------- | -------------------------------- | --- |
0
| 1 {UFCPAS4_PATH} | 注册表缺失则路径空串，OpenLocalFile 报"文件不存在"——环境排障第一入口 |     |
| ---------------- | ------------------------------------------- | --- |
1
1 draft ReadMe 文档称"单循环保一致性"，实际 insertDataBySqliteData 是 500 行批量（文档与实现不
| 2   | 符）  |     |
| --- | --- | --- |
附录 A 关键文件速查表
关注点 文件（相对 src/cpas-server/）
采集工具注册 electron/workbench/workbenchExeInfo.js
采集协议拉起 electron/electronRegister.service.ts（OpenLocalFile，L1000 附近）
单机转联机 nest/cpasApi/logic/methodapi/ProjectManager/project/convert/convert.online.service.ts
SQL API 总入口 nest/cpasApi/sqlApi/impl/SqlApiManager.service.ts
SQL 模板解析 nest/cpasApi/sqlApi/service/sqlTemplate.service.ts
Excel 导入核心 nest/cpasApi/logic/methodapi/CpasTable/engine/service/cpas-table-excel.service.ts
Excel 解析/标签 nest/cpasApi/logic/methodapi/CpasTable/engine/service/table-engine/ExcelGenerate/

关注点 文件（相对 src/cpas-server/）
底稿入库 nest/cpasApi/logic/methodapi/CpasTable/engine/cpas-table-engine.service.ts（createCpasTable
L472）
重算流水线 nest/cpasApi/logic/methodapi/CpasTable/engine/service/operation-engine/OperationEngine.ts
行列取数 .../table-engine/RowColumnData/RowColumnData.ts
单元格公式 .../table-engine/CustomFormula/CustomFormulaService.ts
取数源服务 nest/cpasApi/logic/methodapi/DisclosureService/dataSource/ds.service.ts
合并组成部分导 electron/service/combine-system/importPartData/bulkInsert.service.ts
入
数据上报 electron/service/combine-system/uploadPartData/uploadPartData.service.ts
合并用复制 electron/service/combine-system/mergeUsePart/mergeUsePart.service.ts
AUE6 项目包 nest/cpasApi/logic/methodapi/ProjectManager/project/project.service.ts
底稿模板 nest/cpasApi/logic/methodapi/WorkPaper/draft/draft.service.ts
外部底稿 nest/cpasApi/logic/methodapi/WorkPaper/draft-manage/draft-manage.service.ts
抽样导入 nest/cpasApi/logic/methodapi/auditSample/auditSample.service.ts
账龄分析 nest/cpasApi/logic/methodapi/accountAge/zLAnalysisTool.ts
报表项目加工链 nest/cpasApi/logic/sqlapi/Merge/Account/ + PDM/UFCPAS6.0--项目库.pdm
表结构文档 PDM/UFCPAS6.0--系统库.pdm、PDM/UFCPAS6.0--项目库.pdm、PDM/账龄分析相关表.xlsx