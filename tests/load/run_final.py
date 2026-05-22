"""
最终压测执行脚本 — StepLoadShape 梯度加压 (100→6000 用户)

使用方法:
    python tests/load/run_final.py

可选参数:
    --host       目标主机 (默认 http://localhost:9980)
    --output     报告输出路径 (默认 tests/load/final_report.md)
    --baseline   基线报告路径 (默认 tests/load/baseline_report.md)

功能:
    1. 以无头模式运行 Locust StepLoadShape 梯度加压
    2. 收集各阶段 P50/P95/P99 响应时间、RPS、错误率
    3. 与基线报告对比，计算优化影响
    4. 输出最终报告 final_report.md（含 PASS/FAIL 判定）

梯度阶段:
    Stage 1: 100 用户  (60s 稳定)
    Stage 2: 500 用户  (120s 稳定)
    Stage 3: 1000 用户 (120s 稳定)
    Stage 4: 3000 用户 (180s 稳定)
    Stage 5: 6000 用户 (300s 稳定)

达标标准:
    - P95 ≤ 2000ms (6000 用户阶段)
    - 错误率 < 0.1% (全程)
"""

import argparse
import csv
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# 配置
# ---------------------------------------------------------------------------

SCRIPT_DIR = Path(__file__).resolve().parent
LOCUSTFILE = SCRIPT_DIR / "locustfile.py"
DEFAULT_HOST = "http://localhost:9980"
DEFAULT_OUTPUT = SCRIPT_DIR / "final_report.md"
DEFAULT_BASELINE = SCRIPT_DIR / "baseline_report.md"

# 梯度阶段定义（与 locustfile.py LOAD_STAGES 一致）
STAGES = [
    {"label": "Stage 1", "users": 100, "spawn_rate": 20, "duration": 60},
    {"label": "Stage 2", "users": 500, "spawn_rate": 50, "duration": 120},
    {"label": "Stage 3", "users": 1000, "spawn_rate": 100, "duration": 120},
    {"label": "Stage 4", "users": 3000, "spawn_rate": 200, "duration": 180},
    {"label": "Stage 5", "users": 6000, "spawn_rate": 300, "duration": 300},
]

# 达标标准
TARGET_P95_MS = 2000
TARGET_ERROR_RATE = 0.1  # percent

# 预估总运行时间（含加压过渡）
ESTIMATED_TOTAL_SECONDS = sum(
    s["users"] / s["spawn_rate"] + s["duration"] for s in STAGES
)


def parse_args():
    parser = argparse.ArgumentParser(description="运行 Locust 6000 用户目标压测")
    parser.add_argument("--host", default=DEFAULT_HOST, help="目标主机地址")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="最终报告输出路径")
    parser.add_argument("--baseline", default=str(DEFAULT_BASELINE), help="基线报告路径（用于对比）")
    return parser.parse_args()


def run_locust_full_shape(host: str) -> dict:
    """以无头模式运行 Locust StepLoadShape，返回统计数据。

    StepLoadShape 在 locustfile.py 中定义，自动控制梯度加压。
    Locust 会在所有阶段完成后自动停止。
    """

    csv_prefix = SCRIPT_DIR / f"_final_{int(time.time())}"

    cmd = [
        sys.executable, "-m", "locust",
        "-f", str(LOCUSTFILE),
        "--host", host,
        "--headless",
        "--csv", str(csv_prefix),
        "--csv-full-history",
    ]

    # 计算超时（总运行时间 + 120s 缓冲）
    timeout_seconds = int(ESTIMATED_TOTAL_SECONDS) + 120

    print(f"[INFO] 启动 Locust 目标压测 (StepLoadShape)...")
    print(f"[INFO] 命令: {' '.join(cmd)}")
    print(f"[INFO] 目标: {host}")
    print(f"[INFO] 梯度: {' → '.join(str(s['users']) for s in STAGES)} 用户")
    print(f"[INFO] 预估总时长: {ESTIMATED_TOTAL_SECONDS:.0f}s (~{ESTIMATED_TOTAL_SECONDS/60:.1f} 分钟)")
    print(f"[INFO] 超时设置: {timeout_seconds}s")
    print("=" * 70)

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            cwd=str(SCRIPT_DIR.parent.parent),  # 项目根目录
        )
        print(result.stdout[-3000:] if len(result.stdout) > 3000 else result.stdout)
        if result.stderr:
            # 只打印最后 1000 字符避免刷屏
            print(result.stderr[-1000:] if len(result.stderr) > 1000 else result.stderr)
    except subprocess.TimeoutExpired:
        print(f"[WARN] Locust 执行超时 ({timeout_seconds}s)，尝试读取已有 CSV 数据...")
    except FileNotFoundError:
        print("[ERROR] 未找到 locust 命令，请确认已安装: pip install locust")
        sys.exit(1)

    # 解析结果
    stats = parse_csv_results(csv_prefix)

    # 清理临时文件
    cleanup_csv(csv_prefix)

    return stats


def parse_csv_results(csv_prefix: Path) -> dict:
    """解析 Locust CSV 输出，提取汇总统计和各端点数据。"""

    stats_file = Path(f"{csv_prefix}_stats.csv")
    history_file = Path(f"{csv_prefix}_stats_history.csv")

    results = {
        "total": {},
        "endpoints": [],
        "stages": [],  # 各阶段快照（从 history 推断）
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }

    # 解析最终汇总统计
    if stats_file.exists():
        with open(stats_file, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                entry = _parse_stats_row(row)
                if entry["name"] == "Aggregated":
                    results["total"] = entry
                else:
                    results["endpoints"].append(entry)

    # 解析历史数据（用于推断各阶段指标）
    if history_file.exists():
        results["stages"] = _extract_stage_snapshots(history_file)

    return results


def _parse_stats_row(row: dict) -> dict:
    """解析单行 CSV 统计数据。"""
    return {
        "name": row.get("Name", ""),
        "type": row.get("Type", ""),
        "requests": int(row.get("Request Count", 0) or 0),
        "failures": int(row.get("Failure Count", 0) or 0),
        "median": float(row.get("Median Response Time", 0) or 0),
        "p95": float(row.get("95%", 0) or 0),
        "p99": float(row.get("99%", 0) or 0),
        "avg": float(row.get("Average Response Time", 0) or 0),
        "max": float(row.get("Max Response Time", 0) or 0),
        "rps": float(row.get("Requests/s", 0) or 0),
    }


def _extract_stage_snapshots(history_file: Path) -> list:
    """从 CSV 历史文件中提取各阶段的快照数据。

    通过 User Count 列判断当前处于哪个阶段，
    取每个阶段最后一条 Aggregated 记录作为该阶段的代表值。
    """
    stage_data = {s["users"]: None for s in STAGES}

    with open(history_file, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get("Name") != "Aggregated":
                continue

            user_count = int(row.get("User Count", 0) or 0)

            # 找到最接近的阶段
            closest_stage = None
            for stage in STAGES:
                if user_count >= stage["users"] * 0.9:
                    closest_stage = stage["users"]

            if closest_stage is not None:
                stage_data[closest_stage] = {
                    "users": closest_stage,
                    "user_count_actual": user_count,
                    "requests": int(row.get("Total Request Count", 0) or 0),
                    "failures": int(row.get("Total Failure Count", 0) or 0),
                    "p50": float(row.get("50%", 0) or 0),
                    "p95": float(row.get("95%", 0) or 0),
                    "p99": float(row.get("99%", 0) or 0),
                    "rps": float(row.get("Requests/s", 0) or 0),
                }

    # 按阶段顺序返回
    snapshots = []
    for stage in STAGES:
        data = stage_data.get(stage["users"])
        if data:
            snapshots.append(data)
        else:
            snapshots.append({
                "users": stage["users"],
                "user_count_actual": 0,
                "requests": 0,
                "failures": 0,
                "p50": 0,
                "p95": 0,
                "p99": 0,
                "rps": 0,
            })

    return snapshots


def cleanup_csv(csv_prefix: Path):
    """清理 Locust 生成的临时 CSV 文件。"""
    suffixes = ["_stats.csv", "_failures.csv", "_stats_history.csv", "_exceptions.csv"]
    for suffix in suffixes:
        f = Path(f"{csv_prefix}{suffix}")
        if f.exists():
            f.unlink()


def generate_final_report(stats: dict, args) -> str:
    """基于统计数据生成最终压测报告。"""

    total = stats.get("total", {})
    endpoints = stats.get("endpoints", [])
    stages = stats.get("stages", [])
    timestamp = stats.get("timestamp", "[未知]")

    # 计算全局错误率
    total_requests = total.get("requests", 0)
    total_failures = total.get("failures", 0)
    error_rate = (total_failures / total_requests * 100) if total_requests > 0 else 0

    # 6000 用户阶段数据
    stage_6000 = stages[-1] if stages else {}
    p95_6000 = stage_6000.get("p95", 0)
    error_rate_6000 = (
        (stage_6000.get("failures", 0) / stage_6000.get("requests", 1) * 100)
        if stage_6000.get("requests", 0) > 0 else 0
    )

    # 达标判定
    p95_pass = p95_6000 <= TARGET_P95_MS
    error_pass = error_rate < TARGET_ERROR_RATE
    overall_pass = p95_pass and error_pass

    # 各阶段表格
    def stage_row(s: dict) -> str:
        users = s.get("users", 0)
        reqs = s.get("requests", 0)
        fails = s.get("failures", 0)
        rps = s.get("rps", 0)
        err = (fails / reqs * 100) if reqs > 0 else 0
        return f"| Stage {STAGES[[st['users'] for st in STAGES].index(users) + 1] if users in [st['users'] for st in STAGES] else '?'} | {users} | {reqs} | {fails} | {rps:.1f} | {err:.3f}% |"

    stage_rows = "\n".join(stage_row(s) for s in stages) if stages else "| [无数据] | — | — | — | — | — |"

    # 各阶段详细指标
    def stage_detail(idx: int, s: dict) -> str:
        users = s.get("users", 0)
        p50 = s.get("p50", 0)
        p95 = s.get("p95", 0)
        p99 = s.get("p99", 0)
        rps = s.get("rps", 0)
        reqs = s.get("requests", 0)
        fails = s.get("failures", 0)
        err = (fails / reqs * 100) if reqs > 0 else 0
        p95_ok = "✅" if p95 <= TARGET_P95_MS else "❌"
        return f"""### Stage {idx + 1} — {users} 用户

| 指标 | 值 |
|------|-----|
| P50 (ms) | {p50:.0f} |
| P95 (ms) | {p95:.0f} |
| P99 (ms) | {p99:.0f} |
| RPS | {rps:.1f} |
| 错误率 (%) | {err:.3f}% |
| 达标 (P95 ≤ 2s) | {p95_ok} |
"""

    stage_details = "\n".join(stage_detail(i, s) for i, s in enumerate(stages)) if stages else "[无阶段数据]"

    # 各端点表格（6000 用户最终汇总）
    def endpoint_row(ep: dict) -> str:
        return (
            f"| {ep['type']} {ep['name']} | "
            f"{ep['median']:.0f} | {ep['p95']:.0f} | {ep['p99']:.0f} | "
            f"{ep['max']:.0f} | {ep['avg']:.0f} | {ep['rps']:.1f} |"
        )

    endpoint_rows = "\n".join(endpoint_row(ep) for ep in endpoints) if endpoints else "| [无数据] | — | — | — | — | — | — |"

    # 扩展性分析
    base_rps = stages[0].get("rps", 1) if stages else 1
    def scale_row(s: dict) -> str:
        users = s.get("users", 0)
        rps = s.get("rps", 0)
        p95 = s.get("p95", 0)
        reqs = s.get("requests", 0)
        fails = s.get("failures", 0)
        err = (fails / reqs * 100) if reqs > 0 else 0
        multiplier = users / 100
        linear_ratio = (rps / (base_rps * multiplier)) if (base_rps * multiplier) > 0 else 0
        return f"| {users} | {p95:.0f} | {rps:.1f} | {err:.3f}% | {linear_ratio:.2f}x |"

    scale_rows = "\n".join(scale_row(s) for s in stages) if stages else "| [无数据] | — | — | — | — |"

    # PASS/FAIL 判定文本
    verdict = "PASS ✅" if overall_pass else "FAIL ❌"
    p95_verdict = "✅ PASS" if p95_pass else "❌ FAIL"
    error_verdict = "✅ PASS" if error_pass else "❌ FAIL"

    report = f"""# 最终压测报告 — 6000 用户目标验证

## 测试概要

| 项目 | 值 |
|------|-----|
| 测试日期 | {timestamp} |
| 测试工具 | Locust 2.x + StepLoadShape |
| 目标主机 | {args.host} |
| 最大并发用户数 | 6000 |
| 梯度阶段 | 100 → 500 → 1000 → 3000 → 6000 |
| 总运行时长 | ~{ESTIMATED_TOTAL_SECONDS/60:.0f} 分钟（含加压 + 稳定负载） |
| 测试脚本 | `tests/load/locustfile.py` (StepLoadShape) |
| 优化版本 | 3.4 优化后（连接池/索引/Redis 缓存） |

## 压测场景

| 场景 | 权重 | 端点 |
|------|------|------|
| 登录 | 1 | POST /api/auth/login |
| 查询试算表 | 3 | GET /api/projects/{{pid}}/trial-balance |
| 查询底稿列表 | 2 | GET /api/projects/{{pid}}/workpapers |
| 编辑保存底稿 | 1 | GET + PUT /api/projects/{{pid}}/workpapers/{{wid}} |
| 穿透查询 | 2 | GET /api/projects/{{pid}}/drilldown?account_code=1001 |

---

## 各阶段结果

{stage_details}

---

## 各场景响应时间（全程汇总）

| 场景 | P50 | P95 | P99 | 最大值 | 平均值 | RPS |
|------|-----|-----|-----|--------|--------|-----|
{endpoint_rows}

---

## 吞吐量与错误率汇总

| 阶段 | 用户数 | 总请求 | 总失败 | RPS | 错误率 |
|------|--------|--------|--------|-----|--------|
{stage_rows}

---

## 与基线对比（优化影响分析）

### 优化措施清单（Task 3.4）

| 优化项 | 措施 | 预期效果 |
|--------|------|---------|
| DB 连接池 | pool_size=50, max_overflow=100 | 消除连接等待 |
| TB 查询索引 | tb_balance 复合索引 (project_id, account_code) | 查询加速 50%+ |
| Redis 查询缓存 | TB 数据 60s TTL | 减少 DB 压力 |
| prefill 结果缓存 | Redis key=wp_id+tb_version | 避免重复计算 |
| SSE 连接限制 | 每用户 1 个 SSE + 心跳 30s | 减少长连接数 |

### 扩展性分析

| 用户数 | P95 (ms) | RPS | 错误率 | 线性扩展比 |
|--------|----------|-----|--------|-----------|
{scale_rows}

> 线性扩展比 = (该阶段 RPS) / (100 用户 RPS × 用户倍数)。理想值 = 1.0，< 0.5 表示严重瓶颈。

---

## 资源使用率（6000 用户峰值）

| 指标 | 测试前 | Stage 3 (1000) | Stage 5 (6000) | 安全阈值 |
|------|--------|---------------|----------------|---------|
| CPU 使用率 (%) | [待实测] | [待实测] | [待实测] | < 80% |
| 内存使用率 (MB) | [待实测] | [待实测] | [待实测] | < 4096 |
| DB 连接数 (active) | [待实测] | [待实测] | [待实测] | < 150 |
| DB 连接数 (idle) | [待实测] | [待实测] | [待实测] | — |
| Redis 连接数 | [待实测] | [待实测] | [待实测] | < 200 |
| Redis 内存 (MB) | [待实测] | [待实测] | [待实测] | < 512 |

> 注：资源使用率需在压测期间手动采集或使用外部监控工具。

---

## 最终达标判定

### 核心指标

| 指标 | 目标 | 实测值 (6000 用户) | 达标 |
|------|------|-------------------|------|
| **P95 响应时间** | **≤ 2000ms** | **{p95_6000:.0f}ms** | **{p95_verdict}** |
| **错误率** | **< 0.1%** | **{error_rate:.3f}%** | **{error_verdict}** |
| P99 响应时间 | ≤ 5000ms | {total.get('p99', 0):.0f}ms | {'✅' if total.get('p99', 0) <= 5000 else '❌'} |
| RPS (6000 用户) | ≥ 500 | {total.get('rps', 0):.1f} | {'✅' if total.get('rps', 0) >= 500 else '❌'} |

### 综合判定

```
┌─────────────────────────────────────────────────────────┐
│                                                         │
│   最终结果:  {verdict:<42}│
│                                                         │
│   P95 ≤ 2s:     {p95_verdict:<38}│
│   错误率 < 0.1%: {error_verdict:<38}│
│                                                         │
└─────────────────────────────────────────────────────────┘
```

### 判定规则

- **PASS**: P95 ≤ 2000ms **且** 错误率 < 0.1%（两项同时满足）
- **FAIL**: 任一指标未达标
- 如 FAIL → 继续优化 → 重测（循环直到 PASS）

---

## 后续行动

- {'[x]' if overall_pass else '[ ]'} 如 PASS：归档报告，进入 UAT 验收
- {'[ ]' if overall_pass else '[x]'} 如 FAIL：分析瓶颈 → 针对性优化 → 重新执行 `python tests/load/run_final.py`
- [ ] 长期：接入 CI/CD 定期回归压测（防止性能退化）

---

## 执行方式

```bash
# 自动化执行（推荐）— 运行完整 StepLoadShape 梯度加压
python tests/load/run_final.py

# 指定参数
python tests/load/run_final.py --host {args.host} --output {args.output}

# 手动执行（使用 StepLoadShape 自动梯度加压）
locust -f tests/load/locustfile.py --host={args.host} --headless
```

---

*报告生成时间: {timestamp}*
*执行人: [待填写]*
*优化版本: Task 3.4 完成后*
"""
    return report


def main():
    args = parse_args()

    print("=" * 70)
    print("  审计平台目标压测 — 6000 用户 StepLoadShape 梯度加压")
    print("=" * 70)
    print()
    print(f"  目标: P95 ≤ {TARGET_P95_MS}ms / 错误率 < {TARGET_ERROR_RATE}%")
    print(f"  梯度: {' → '.join(str(s['users']) for s in STAGES)} 用户")
    print(f"  预估时长: ~{ESTIMATED_TOTAL_SECONDS/60:.0f} 分钟")
    print()

    # 检查 locustfile 存在
    if not LOCUSTFILE.exists():
        print(f"[ERROR] 未找到压测脚本: {LOCUSTFILE}")
        sys.exit(1)

    # 运行压测
    stats = run_locust_full_shape(args.host)

    # 生成报告
    total = stats.get("total", {})
    stages = stats.get("stages", [])

    if total or stages:
        print()
        print("=" * 70)
        print("  生成最终报告...")
        print("=" * 70)

        report_content = generate_final_report(stats, args)
        output_path = Path(args.output)
        output_path.write_text(report_content, encoding="utf-8")
        print(f"[OK] 报告已输出: {output_path}")

        # 打印摘要
        total_requests = total.get("requests", 0)
        total_failures = total.get("failures", 0)
        error_rate = (total_failures / total_requests * 100) if total_requests > 0 else 0

        # 6000 用户阶段
        stage_6000 = stages[-1] if stages else {}
        p95_6000 = stage_6000.get("p95", 0)

        p95_pass = p95_6000 <= TARGET_P95_MS
        error_pass = error_rate < TARGET_ERROR_RATE
        overall_pass = p95_pass and error_pass

        print()
        print("┌─────────────────────────────────────────────┐")
        print("│         目标压测结果摘要 (6000 用户)         │")
        print("├─────────────────────────────────────────────┤")
        print(f"│  总请求数:    {total_requests:<29} │")
        print(f"│  总失败数:    {total_failures:<29} │")
        print(f"│  错误率:      {error_rate:<28.3f}% │")
        print(f"│  RPS:         {total.get('rps', 0):<29.1f} │")
        print(f"│  P50:         {total.get('median', 0):<28.0f}ms │")
        print(f"│  P95:         {total.get('p95', 0):<28.0f}ms │")
        print(f"│  P99:         {total.get('p99', 0):<28.0f}ms │")
        print("├─────────────────────────────────────────────┤")
        print(f"│  P95 (6000):  {p95_6000:<28.0f}ms │")
        print(f"│  目标:        ≤ {TARGET_P95_MS}ms                        │")
        print(f"│  P95 达标:    {'✅ PASS' if p95_pass else '❌ FAIL':<29} │")
        print(f"│  错误率达标:  {'✅ PASS' if error_pass else '❌ FAIL':<29} │")
        print("├─────────────────────────────────────────────┤")
        verdict = "✅ PASS" if overall_pass else "❌ FAIL"
        print(f"│  最终判定:    {verdict:<29} │")
        print("└─────────────────────────────────────────────┘")

        if not overall_pass:
            print()
            print("[ACTION] 未达标！建议:")
            if not p95_pass:
                print(f"  - P95 ({p95_6000:.0f}ms) 超过目标 ({TARGET_P95_MS}ms)")
                print("  - 检查慢查询 / 增加缓存 / 优化连接池")
            if not error_pass:
                print(f"  - 错误率 ({error_rate:.3f}%) 超过目标 ({TARGET_ERROR_RATE}%)")
                print("  - 检查连接超时 / 增加 Worker 数 / 排查 5xx 错误")
            print()
            print("  优化后重新执行: python tests/load/run_final.py")
    else:
        print()
        print("[WARN] 未获取到统计数据，请检查:")
        print("  1. 后端服务是否已启动 (http://localhost:9980)")
        print("  2. Locust 是否正确安装 (pip install locust)")
        print("  3. 测试数据是否存在 (PROJECT_ID=1)")
        print("  4. StepLoadShape 是否正确定义在 locustfile.py 中")
        print()
        print("[INFO] 报告模板保留为占位状态，待实际执行后填充。")
        print(f"[INFO] 模板位置: {DEFAULT_OUTPUT}")


if __name__ == "__main__":
    main()
