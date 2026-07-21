# BACKLOG

## 维护约定

- 自 `2026-07-05` 起，所有修改记录统一维护在根目录 `BACKLOG.md`。
- 不再在 `reports/` 顶层新增按日期命名的修改记录文件。
- `reports/13_following/` 等业务报告、分析产物和数据文件继续保留，不纳入本次清理。

## 2026-07-05

- checkpoint 本地文件链路正式下线：`CheckpointRepository` 改为只写 / 只读 Supabase `public.sync_checkpoints`，`show-status` 不再回退本地 `checkpoints.json`，远端不可用时直接返回空列表；同时删除仓库内 `data/backend_sync/checkpoints.json`，避免后台继续产生本地状态副本。
- `show-status` 收口到与 UI 相同的 Supabase 状态源：`BackendOrchestrator.show_status()` 现优先读取 `public.sync_checkpoints`，只有远端不可用或无结果时才回退本地 `checkpoints.json`；并补充对应回归测试覆盖“远端优先 / 本地兜底”两条路径。
- 后台 / UI 分离部署场景补齐 `sync_checkpoints` Supabase 主链：新增 `sql/0004_sync_checkpoints.sql`，`CheckpointRepository` 支持双写本地文件与远端 `public.sync_checkpoints`，UI sidebar 改为只从 Supabase 读取任务状态，不再依赖本地 `checkpoints.json`。
- Supabase 客户端补上“只读 UI 可用 publishable key”能力：`build_supabase_client(..., allow_publishable_fallback=True)` 允许 UI 服务器仅配置 `SUPABASE_URL + SUPABASE_PUBLISHABLE_KEY` 读取 mart 与状态表，后台仍优先使用 `SUPABASE_SECRET_KEY` 写入。
- 修复 sidebar `Latest jobs` 刷新滞后：`load_checkpoint_statuses()` 改为绑定 `data/backend_sync/checkpoints.json` 的 `mtime` 自动失效缓存，并在 `streamlit_app.py` 侧边栏加入 `Refresh status` 按钮，确保手工跑完 `sync-13dg` 等后台任务后，UI 可立即显示最新完成时间。
- `Managers` 页多选交互改为“时间序列明细优先”：当全选或多选机构时，右侧 `Summary` 不再展示集合化的 multi-manager summary 表，改为复用单选 `13D/G monitor` 的字段口径，按 filing date 展示全部选中基金的 `13D/G` 调仓流水。
- 8-K / 13D-G 同步补上“基于 accession 的增量跳过”逻辑：若本地已存在对应 accession，则不再重复抓取 SEC filing 正文；其中 13D/G 会复用本地 payload，并继续补写 `raw_13dg_sync_sources` 映射，避免 manager / issuer 多入口下重复下载正文。
- 为增量跳过补测试：验证已同步 accession 不会再次调用 `build_8k_payload()` / `build_13dg_payload()`；同时删除误建的 `reports/2026-07-06-sec-download-duplication-check.md`，后续修改记录继续只维护在根目录 `backlog.md`。
- 更新 `~/.codex/superpowers/skills/using-superpowers/SKILL.md` 与 `references/codex-tools.md`，修正 Codex 场景下的 skill 加载说明、原生工具映射，以及多代理工具的真实约束。
- 已将 `reports/` 顶层历史修改记录合并到本文件，并清理旧的按日期拆分记录文件。
- 安装 Matt Pocock 核心 skills 到 `~/.codex/skills/`：
  `setup-matt-pocock-skills`、`grill-me`、`grill-with-docs`、`tdd`、`diagnosing-bugs`
- 待执行：重启 Codex 以重新加载新 skills
- 待执行：在目标仓库中运行 `/setup-matt-pocock-skills` 完成一次初始化
- 13D/G 覆盖缺口确认根因是“按 ticker / movers universe 拉 issuer filings”，不是按 manager CIK 拉 filer filings；这会系统性漏掉 `NBIS` 等不在 movers universe、但机构真实提交了 13D/G 的事件。
- 制定并落地 13D/G manager-centric 主链：`sync-13dg` 新增 `--mode manager`、`--manager-ciks`、`--manager-scope`，新增 `audit-13dg-coverage`，并引入 `raw_13dg_reporting_persons`、`raw_13dg_sync_sources`，远端需执行 `sql/0003_13dg_manager_sync.sql`。
- 定向修复 `NBIS` 漏项：执行 `sync-13dg --tickers NBIS --date-from 2024-01-01 --max-filings 20` 后写入 `10` 条；`Managers` 页改为优先展示机构自己的近期 13D/G，而不是只看全市场 recent feed 与当前 13F rebalance 的交集。
- `Managers` 页补强多选研究流程：支持 `Select all filtered`、`Clear`、多 manager 合并视图，并将 `13F tickers`、`13D/G monitor`、overlap 结果按组合口径展示。
- `Managers -> 13D/G monitor` 改为展示完整结果并增强滚动体验：不再只取前 `24` 条 13F rebalance 或前 `20` 条 recent 13D/G，页面改为读取完整 rebalance 明细、最近 `100` 条 13D/G，并为结果表设置固定高度滚动窗口。
- `Managers -> 13D/G monitor` 新增当前期与变化口径字段：补入 `Reported shares`、`Ownership %`、`13D/G change`、`13D/G delta shares`、`13D/G delta %`，并区分“对比上一份 13D/G”的变化与“对比最近两个 13F 报告期”的 `13F action`。
- `Managers` 页先后完成两轮 13F 交叉补值优化：最初可直接回查最近一期本地 13F ZIP 补 `13F action/current value/delta value`；随后新增 `mart_manager_security_latest`，把最新持仓交叉查询下沉到 Supabase mart，减少本地冷启动解析依赖。
- `Managers` 页延迟问题确认根因是 UI 路径仍会回退解析本地 13F ZIP；后续默认关闭 `allow_local_fallback`，未命中时直接显示 `Not reported`，并去掉重复的 recent 13D/G 查询与 overlap 计算。
- UI 研究数据主链已收口到 Supabase only：删除 UI 侧本地 13F ZIP fallback，`load_manager_13f_crosscheck()` 只读 `mart_manager_security_latest`，`load_recent_13dg_by_manager()` 复用缓存基表，`prewarm_core_ui_cache()` 与 `prewarm_manager_ui_cache()` 负责常用查询预热。
- 页面加载性能完成一轮收敛：将 `security history`、`8-K`、`13D/G` 精确查询下推到 Supabase 过滤，并把 `13F`、`Quarterly movers`、`Managers` 右侧 tabs 改成条件加载，减少首屏并发查询。
- 空 ticker 根因修复覆盖同步与 UI 两层：`SecurityIdentifierRepository` 支持 `CUSIP + issuer_name` 双路径解析、名称归一化、SEC `company_tickers.json` fallback，并让 `sync-13f` 在写 `mart_13f_quarterly_movers`、`mart_manager_rebalance_detail`、`mart_manager_security_latest` 前统一重算 ticker 与依赖 ticker 的 `row_key`。
- 增加正式后台命令 `backfill-tickers`，按本地 `cusip_ticker_map.csv`、SEC cache、既有 mart 映射、可选 OpenFIGI 逐层回补，并在源 mart 为空时拒绝执行、回写前按 `row_key` 去重。
- 第三轮 ticker 回补执行后，缺失数由 `mart_13f_quarterly_movers=11`、`mart_manager_rebalance_detail=1081`、`mart_manager_security_latest=990` 继续收敛到仅剩 `21` 个唯一 `CUSIP + issuer` 组合待补。
- `Managers` 页的 13D/G ticker 映射与当前期展示已补齐，新增 `N97284108 -> NBIS`、`778920306 -> SHAZ`、`21874A106 -> CORZ`、`21873S108 -> CRWV` 等映射，`Situational Awareness LP` 的相关近期记录可直接展示。

## 2026-07-03

- 明确统一后台入口与读写链路：`scripts/backend_sync.py` 负责 CLI 分发，`BackendOrchestrator` 统一调度 `sync-13f`、`sync-8k`、`sync-13dg`、`rebuild-marts`、`sync-all`、`show-status`。
- 后台 dry-run 冒烟验证确认 `.env` 缺少 `EDGAR_IDENTITY` 时无法运行；临时补齐后 `sync-13f --dry-run` 与 `sync-8k --dry-run` 均可成功，且发现 `--dry-run` 作为顶层参数时存在顺序要求。
- 进一步 live smoke 确认真实 `sync-8k` 与 `sync-13f` 请求链路可用，`.env` 自动加载与依赖状态基本正常。
- 数据库同步链路完成一轮稳固化：`Settings.load()` 自动读取仓库根目录 `.env`，`SUPABASE_URL` 兼容项目根 URL 与 `/rest/v1/` URL，两类 checkpoint 写入改为文件锁加原子替换，13F issuer/ticker 匹配加入缓存优化。
- Supabase 双写模型补齐到 `raw_8k_filings`、`raw_13dg_filings`、`raw_13f_sync_runs`、`mart_13f_quarterly_movers`、`dim_manager_watchlist`、`mart_manager_profile`、`mart_manager_research_snapshot`，对应建表脚本为 `sql/0001_backend_sync_schema.sql`。
- 在远端 schema 应用后，真实 `sync-8k`、`sync-13dg`、`rebuild-marts`、`sync-13f --skip-download --quarters 1 --top-limit 100` 全部打通；阶段性库内计数包括 `mart_13f_quarterly_movers=2299`、`dim_manager_watchlist=11`、`mart_manager_profile=11`。
- `sync-13f` 改为基于结构化 13F ZIP 在内存中直接构建并 upsert `mart_13f_quarterly_movers`，`rebuild-marts` 改为直接从 Supabase mart 重建快照，不再依赖 `reports/13_following/data/*.csv`；四季度真实重跑成功写入 `2299` 行。
- 修复 13D/G recent feed 为空的根因：SEC / `edgartools` 实际返回 `SCHEDULE 13D/13G` 家族，代码原先只过滤 `SC 13*`；扩展 form 兼容后，默认 `30` 天 `sync-13dg` 可写入 `41` 行。
- 修复 13D/G 详情页 payload 过于简陋的问题：新增 `build_13dg_payload()`，落库 `issuer_name`、`issuer_cusip`、`security_title`、`rule_designation`、`total_shares`、`total_percent`、`reporting_persons`、`purpose_text`、`summary`，并在页面右侧详情卡展示结构化字段。
- 13D/G 历史回补与 13F 页嵌入完成：同步服务增加 EDGAR 异常容错、单 ticker 失败降级 warning、单 filing 失败写 fallback payload；重点 ticker 历史回补后，`BLK`、`MS`、`WFC`、`JPM`、`MELI`、`TSLA`、`DELL`、`BAC`、`BFAM`、`PLTR`、`WBD`、`CRWV`、`MRVL`、`PLD`、`TER`、`UBER` 等样本已进入原始表并可在 13F 页面展示最近 13D/G 摘要。
