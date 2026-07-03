# 后台同步 dry-run 冒烟验证

日期：2026-07-03

## 目标

验证以下两条统一后台入口命令在当前本地环境中的可用性，并确认 `.env` 与依赖状态：

- `python scripts/backend_sync.py --dry-run sync-13f`
- `python scripts/backend_sync.py --dry-run sync-8k`

## 环境

- conda 环境：`py312aiproxy`
- `.env`：存在

## `.env` 检查结果

仅检查是否存在，不记录具体敏感值：

- `SUPABASE_URL`：已配置
- `SUPABASE_SECRET_KEY`：已配置
- `SUPABASE_PUBLISHABLE_KEY`：已配置
- `EDGAR_IDENTITY`：缺失

结论：

- 当前 `.env` **不完整**
- 按现有代码实现，`EDGAR_IDENTITY` 缺失会在 `validate_edgar()` 阶段直接报错，即使是 dry-run

## 实际执行结果

### 1. 严格按当前 `.env` 执行

命令：

```bash
python scripts/backend_sync.py --dry-run sync-13f
python scripts/backend_sync.py --dry-run sync-8k
```

结果：

- 两条命令都失败
- 失败原因一致：`EDGAR_IDENTITY is required for backend sync commands.`

说明：

- 当前 `.env` 状态下，后台入口**不能直接运行**

### 2. 使用临时 `EDGAR_IDENTITY` 覆盖后重跑

临时设置：

```bash
export EDGAR_IDENTITY='Codex Smoke Test smoke@example.com'
```

结果：

- `sync-13f --dry-run`：成功
- `sync-8k --dry-run --tickers AAPL,MSFT --days-back 7`：成功

`sync-13f --dry-run` 输出要点：

- `status=success`
- `report_dates=["2026-03-31","2025-12-31","2025-09-30","2025-06-30"]`

`sync-8k --dry-run` 输出要点：

- `status=success`
- `tickers=["AAPL","MSFT"]`
- `warnings=["8-K dry-run does not contact EDGAR."]`

### 3. `show-status`

命令：

```bash
python scripts/backend_sync.py show-status
```

结果：

- 能正常返回 `sync-13f` 和 `sync-8k` 的最近状态

## 本次验证暴露出的真实问题

### 问题 1：`.env` 缺少 `EDGAR_IDENTITY`

影响：

- 当前配置下，后台入口无法直接运行

建议：

- 在 `.env` 中补上合法的 `EDGAR_IDENTITY`
- 推荐格式：`姓名 邮箱` 或 `项目名 邮箱`

### 问题 2：CLI 参数顺序有坑

现象：

```bash
python scripts/backend_sync.py sync-13f --dry-run
```

会报：

- `unrecognized arguments: --dry-run`

原因：

- 目前 `--dry-run` 是顶层参数，必须写在子命令前

正确写法：

```bash
python scripts/backend_sync.py --dry-run sync-13f
python scripts/backend_sync.py --dry-run sync-8k
```

### 问题 3：`checkpoints.json` 不适合并行写

现象：

- 并行执行 dry-run 时，`sync-8k` 曾出现 `JSONDecodeError`

原因：

- `CheckpointRepository` 当前是简单的读改写 JSON 文件，没有并发保护

影响：

- 后续如果 `sync-all` 之外还有并行任务编排，会有 checkpoint 文件损坏风险

## 可用性结论

### 当前状态

- 代码与依赖：**可用**
- `.env`：**不完整**
- 统一后台 dry-run：**在补齐 `EDGAR_IDENTITY` 后可用**

### 对“外部依赖是否正常”的结论

这次仅做了 dry-run：

- 已验证：CLI、配置读取、服务层、checkpoint 写入、`edgartools` 运行时依赖
- 未验证：真实 SEC 网络请求、真实 Supabase 写入

原因：

- `sync-8k --dry-run` 明确不会联系 EDGAR
- `sync-13f --dry-run` 也没有实际下载或写库

## 下一步建议

要真正确认外部链路，建议下一步做最小 live smoke：

```bash
python scripts/backend_sync.py sync-13f --mode incremental --quarters 1 --skip-download
python scripts/backend_sync.py sync-8k --tickers AAPL --days-back 3 --max-filings 3
```

前提：

- 先在 `.env` 中补齐 `EDGAR_IDENTITY`

## Live Smoke 补充结果

在 `.env` 补齐 `EDGAR_IDENTITY` 后，进一步执行了真实请求级别的最小冒烟。

### 1. `sync-8k` 真实请求

命令：

```bash
python scripts/backend_sync.py sync-8k --tickers AAPL --days-back 180 --max-filings 3
```

结果：

- 执行成功
- `rows_written=3`
- 本地已写入 3 个 raw 8-K JSON 文件

落盘样例：

- `data/backend_sync/raw_8k/0000320193-26-000011.json`
- `data/backend_sync/raw_8k/0001140361-26-006577.json`
- `data/backend_sync/raw_8k/0001140361-26-015711.json`

说明：

- SEC 请求链路正常
- `edgartools` 导入和查询正常
- 本地 raw 表达层落盘正常

观察到的 warning：

- `Failed to load company_tickers.parquet from package: Repetition level histogram size mismatch`

影响判断：

- 不阻塞查询
- 本次真实 `sync-8k` 仍成功完成

### 2. `sync-13f` 真实执行

命令：

```bash
python scripts/backend_sync.py sync-13f --mode incremental --quarters 1 --top-limit 10
```

结果：

- 成功启动
- 已进入真实业务计算链路
- 在 smoke 时间窗内未完成，因此手动中断

已确认到的执行链路：

- 后台入口正常启动
- 13F service 正常进入 `export_13f_quarterly_rebalance_csv.py`
- 运行中日志出现 `quarter_data_loaded`
- 进程持续高 CPU 运行，并非启动即失败或无响应

中断时调用栈显示主要耗时在：

- `summarize_quarter`
- `security_identity`
- `ticker_for_security`
- `ticker_for_issuer`
- `matches_fragment`

影响判断：

- 当前 `sync-13f` 不存在“配置缺失导致无法启动”的问题
- 也不是“依赖缺失/网络报错/导入失败”问题
- 当前瓶颈更像是本地 13F 汇总与 issuer->ticker 映射逻辑计算较重，导致首版 live smoke 窗口内未收尾

### 更新后的可用性结论

- `sync-8k`：**已完成真实端到端验证，可用**
- `sync-13f`：**可启动并进入真实计算链路，但当前执行耗时较长，需继续优化或给更长运行窗口**

### 当前最关键的后续优化点

1. 优化 `sync-13f` 中 `ticker_for_issuer` / `matches_fragment` 相关标的映射性能
2. 为 `CheckpointRepository` 增加并发保护，避免多任务并行写 `checkpoints.json`
3. 改进 CLI 参数体验，支持 `sync-13f --dry-run` 这种更自然的参数顺序
