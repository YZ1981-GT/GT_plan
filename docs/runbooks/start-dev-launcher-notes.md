# start-dev.bat 运维说明

`start-dev.bat` 必须保持**纯 ASCII**。本文承载被从脚本里移出的中文说明与实测数据。

## 一、为什么 bat 不能写中文（2026-09-05 事故）

### 现象

脚本被加入中文 REM 注释后，启动时打出：

```
[1/5] Stopping old processes...
      Done.
[2/5] Starting backend on :9980 ...
'??' is not recognized as an internal or external command,
[3/5] Waiting for backend health (max 60s, migrations may take 20-40s)...
'*在' is not recognized as an internal or external command,
'连接失败。' is not recognized as an internal or external command,
'[WARN]' is not recognized as an internal or external command,
```

那些「命令」全是中文 REM 注释的**后半截**，被 cmd 当命令执行了。

### 根因

cmd.exe 先按**父 console 当前代码页**打开并逐行解析 bat。第 3 行 `chcp 65001`
把代码页换成 UTF-8 后，cmd 的「字符数 vs 字节数」记账失去同步。解析
`( ... )` 块（`for /L` + `if`）时它需要回退文件指针重读，错位的指针落到某行
中间，于是从中文注释的中段恢复解析。

### 2×2 因子实验（实测）

| 块内多字节字符 | 解析中途 `chcp 65001` | 结果 |
|---|---|---|
| 有 | 有 | **碎（复现残片）** |
| 有 | 无 | 干净 |
| 无 | 有 | 干净 |

两个因子**缺一不可**。另外中文放在括号块**外**也不碎——但不要依赖这点，
块的边界会随后续编辑漂移。

### 触发依赖父进程代码页

| 父 console CP | 结果 |
|---|---|
| 936（中文 Windows 默认，双击 bat 的真实情形） | **碎** |
| 65001（已切 UTF-8 的终端） | 不碎 |
| python subprocess + 管道 / detached 无 console | 不碎 |

**排查启示**：在已切 UTF-8 的终端里手动跑脚本可能完全正常，用户双击却必碎。
复现时必须显式 `chcp 936`。

### 结论

无法在 bat 内部规避，只能保证文件纯 ASCII。守卫：
`backend/tests/test_start_dev_bat_ascii_guard.py`（6 条，含 CP936 下的反向自检
与真实脚本端到端 dry-run）。

## 二、健康探测的地址族不对称（有意设计，勿"对称化"）

前后端探测地址**故意相反**，改成一致会立刻坏掉：

| 服务 | 监听 | 探测必须用 | 实测 |
|---|---|---|---|
| 后端 uvicorn `--host 0.0.0.0` | 仅 IPv4，`::1` 无监听 | `127.0.0.1` | localhost 2053ms / 127.0.0.1 16ms / `[::1]` 拒绝 |
| 前端 vite（默认 host） | node 解析 localhost 得 `::1`，仅 IPv6 | `localhost` | localhost 49ms / `127.0.0.1:3030` 连不上 |

后端若用 `localhost` + `-TimeoutSec 1`：Windows 先解析 `::1`，连接失败后才回退
IPv4，固定耗时约 2050ms > 1s 超时 ⇒ **探测永远在 IPv6 阶段超时**，无论后端是否
健康都判失败，打出误导性的 `[WARN] Backend not responding`。

**已知限制**：前端请用 `localhost:3030` 访问，`127.0.0.1:3030` 不通。
若要改 vite 为 `host: '127.0.0.1'`，必须同时把 `http://127.0.0.1:3030` 加进后端
`CORS_ORIGINS`（当前只有 `localhost:5173,localhost:3030`），否则一点开就撞 CORS。

## 三、后端健康等待为何是 60s

启动时 MigrationRunner 要跑全部 `V*.sql`（已 150+ 个）+ schema drift 检查，
冷启动实测超过 30s。30s 上限会在后端其实正常的情况下打出
`[WARN] Backend not responding`，把排查方向带到后端上。

## 四、括号块内 echo 的圆括号必须转义

`if ... ( ... ) else ( ... )` 多行块内任何裸 `)` 都会被当成块结束符：

```bat
REM 错误：(vendor read-only) 里的 ) 提前闭合 if 块，残留的 . 成为孤立 token
echo [3.5] DSH SDK runtime detected (vendor read-only).
REM 正确
echo [3.5] DSH SDK runtime detected ^(vendor read-only^).
```

错误写法让 cmd 报 `. was unexpected at this time.` 并**整体终止脚本
（exit 255）**，于是 `[4/5]` 启动前端那行永远不执行 ——
现象是「后端起来了、前端根本没起」。这发生在**解析阶段**，所以连 `[3.5]`
自己的 echo 都不会打印，唯一线索是紧跟 `[3/5]` 之后的一行报错，极易被忽略。

## 五、`:wait_port_free` 的性能约束

轮询必须保持在**单次 powershell 调用内**，且只能用
`IPGlobalProperties.GetActiveTcpListeners()`：

- bat 的 for 循环每轮重启 powershell，约 2s/轮，不可接受
- `Get-NetTCPConnection` 是 CIM 查询，约 1.2s/次
- `TcpListener` bind 只绑一个地址族，可能给出错误结论
- `GetActiveTcpListeners()` 是纯 .NET 调用（毫秒级），返回所有地址族

vite 配了 `strictPort`，端口被占就直接退出（不会漂到 3031）；`taskkill` 后
socket 未必立即释放，所以必须显式等端口空闲。
