# backend_schedule.py 运行超时崩溃排查

日期：2026-07-06

## 假设

- 不是 `schedule` 包自身出错
- 是某个定时任务执行时，把未捕获异常直接抛回调度器主循环

## 实验

读取用户提供的控制台报错栈：

- 启动正常：`backend_scheduler_started`
- 到首个工作日 ET `06:00` 之后，`sync-8k` 被触发
- 大量 `edgar` warning 表示正在真实抓取 8-K
- 最终异常落点在：
  - `BackendScheduleService._execute_job()`
  - `BackendOrchestrator.sync_8k()`
  - `EightKSyncService.sync()`
  - `EdgarToolsClient.build_8k_payload()`

最底层真实错误是：

- `httpx.ReadTimeout: The read operation timed out`

## 根因

`sync-8k` 在“查 ticker 对应 filings”阶段只兜了 `EdgarTickerLookupError`，  
在“单条 filing 解析 payload”阶段只兜了：

- `AttributeError`
- `KeyError`
- `OSError`
- `RuntimeError`
- `TypeError`
- `ValueError`

但这次真实线上错误是 `httpx.ReadTimeout`，不在 fallback 捕获范围内，所以没有降级成 warning，而是直接把整个 scheduler 进程打崩。

## 最小修复

在 `EightKSyncService` 里把以下异常纳入可恢复错误：

- ticker 搜索阶段：`httpx.HTTPError`、`OSError`、`TimeoutError`
- payload 解析阶段：`httpx.HTTPError`、`TimeoutError`

修复后行为：

- 单个 ticker 搜索超时：记 warning，继续后续 ticker
- 单条 8-K 解析超时：记 warning，写 fallback payload，继续后续 filing
- 不再因为单条 SEC 网络超时直接退出整个调度器

## 验证

新增回归测试：

- `tests/test_eightk_sync_service.py`

覆盖两类场景：

1. 单个 ticker 搜索超时但整体任务继续成功
2. 单条 filing 解析超时但 fallback 成功写入
