# 数据库全量同步修复状态

日期：2026-07-03

## 已完成修复

### 1. `.env` 自动加载

- `Settings.load()` 现在会自动读取仓库根目录下的 `.env`
- 运行 `python scripts/backend_sync.py ...` 不再需要先手动 `source .env`

### 2. Supabase URL 兼容

- 当前 `.env` 中的 `SUPABASE_URL` 实际是带 `/rest/v1/` 的 PostgREST URL
- 已新增 URL 规范化逻辑，兼容两种写法：
  - 项目根 URL：`https://<project>.supabase.co`
  - REST URL：`https://<project>.supabase.co/rest/v1/`

### 3. checkpoint 写入稳定性

- `checkpoints.json` 改为文件锁 + 原子替换写入
- 避免并行/连续任务时出现空文件或半写入 JSON

### 4. 13F 匹配热点优化

- `ticker_for_issuer()` 已加 `lru_cache`
- `matches_fragment()` 改为正则预编译缓存
- 目的是降低 `sync-13f` 中 issuer/ticker 匹配的重复 CPU 开销

### 5. Supabase 落库链路已补齐

已补为“本地文件 + Supabase upsert”双写模型：

- `raw_8k_filings`
- `raw_13dg_filings`
- `raw_13f_sync_runs`
- `mart_13f_quarterly_movers`
- `dim_manager_watchlist`
- `mart_manager_profile`
- `mart_manager_research_snapshot`

## 已新增建表 SQL

建表文件：

- `sql/0001_backend_sync_schema.sql`

## 当前验证结果

### 自动化测试

```bash
python -m pytest -q
```

结果：

- `31 passed`

### 真实同步验证

#### `sync-8k`

命令：

```bash
python scripts/backend_sync.py sync-8k --tickers AAPL --days-back 180 --max-filings 1
```

结果：

- 已成功触发真实 SEC 查询
- 在写入数据库时返回清晰错误：

```text
Supabase table 'raw_8k_filings' does not exist. Apply the SQL schema before syncing.
```

说明：

- 代码链路已通
- 当前阻塞不在代码，而在远端表尚未创建

#### `rebuild-marts`

命令：

```bash
python scripts/backend_sync.py rebuild-marts
```

结果：

- 返回清晰错误：

```text
Supabase table 'mart_13f_quarterly_movers' does not exist. Apply the SQL schema before syncing.
```

说明：

- CSV 解析与 mart 构建路径已通
- 当前阻塞同样是 Supabase 目标表未创建

## 当前真正的阻塞

当前 `.env` 中只有：

- `SUPABASE_URL`
- `SUPABASE_SECRET_KEY`
- `SUPABASE_PUBLISHABLE_KEY`

但没有：

- PostgreSQL 直连连接串
- 本地 `supabase` CLI 链接上下文
- 可执行远端 DDL 的管理通道

因此当前会话中：

- 可以验证 REST API
- 可以向“已存在表”写数据
- **不能直接替你在远端 Supabase 创建这些新表**

## 下一步

### 你需要做的一步

把下面这个 SQL 文件内容贴到 Supabase SQL Editor 执行：

- `sql/0001_backend_sync_schema.sql`

### 执行完建表后再跑

```bash
python scripts/backend_sync.py sync-8k --tickers AAPL --days-back 180 --max-filings 3
python scripts/backend_sync.py sync-13dg --tickers AAPL --days-back 180 --max-filings 3
python scripts/backend_sync.py rebuild-marts
python scripts/backend_sync.py sync-all --with-marts
```

## 结论

- 代码层错误已基本修复
- 数据库同步链路已补上
- 当前无法完成“全量更新数据库”的唯一明确阻塞，是远端 Supabase 目标表尚未创建

## 建表后执行结果

你执行远端建表后，我继续完成了真实入库验证。

### 已成功完成

- `python scripts/backend_sync.py sync-8k`
- `python scripts/backend_sync.py sync-13dg`
- `python scripts/backend_sync.py rebuild-marts`
- `python scripts/backend_sync.py sync-13f --skip-download --quarters 1 --top-limit 100`

### 当前数据库计数

已确认：

- `raw_8k_filings`：25 行
- `raw_13dg_filings`：0 行
- `raw_13f_sync_runs`：1 行
- `mart_13f_quarterly_movers`：2299 行
- `dim_manager_watchlist`：11 行
- `mart_manager_profile`：11 行
- `mart_manager_research_snapshot`：1 行

说明：

- `raw_13dg_filings=0` 并不代表失败，本次默认窗口是 `days_back=30`，在当前股票宇宙下未命中 13D/G 事件

### 修复后的行为

- 8-K / 13D-G 不再因为坏 ticker 中断整批同步
- 当前会把无法被 `edgartools` 解析的 ticker 记为 warning，并继续后续 ticker
- 已知 warning：
  - `BLCR`
  - `BAI`

### 13F 现状

- 通过 `rebuild-marts`，4 个季度现有 CSV 已全量入库 Supabase
- `sync-13f` 原始同步入口在启用缓存后也已成功完成 1 个季度真实运行
- 说明 13F 主链路已经不是阻塞项，只是完整 4 季度重跑仍然会比 8-K / marts 明显更慢
