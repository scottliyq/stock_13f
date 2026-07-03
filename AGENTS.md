# AGENTS.md
最后更新: 2026-07-02

## 本文件的作用


每次新建文件、改动核心逻辑、写测试时，**请阅读本文件前几段**。

## 1. 项目基本信息

项目类型：      RESTful + WebSocket 混合后端 + 轻量前端
主要领域：      爬虫数据处理
Python 版本：   3.12
包管理：        conda
依赖管理：      conda


## 2. 代码风格强约束（AI 必须遵守）

必须使用的代码风格：
- 所有 public API 必须写类型注解（100%）
- async def / await 是主流，尽量写异步代码
- 禁止在业务逻辑层直接 print()，使用 structlog
- 始终使用markdown格式保存输出的报告
- 使用Agent Reach 爬取x和reddit的数据


强烈推荐的模式（AI 应优先考虑）：
- dependency injection 风格（fastapi Depends + di 容器）
- Repository 模式 + UnitOfWork
- 服务层（Service） / 用例层（UseCase） 分层
- 返回 Result[T, Error] 或 Result型（使用 returns 或 自制 Result 类）
- 优先使用 attrs / dataclasses 而非 namedtuple / dict

明确禁止的写法（AI 不要生成）：
- from __future__ import annotations （3.11+ 不需要）
- class Meta: 这种 django 风格（本项目不是 django）
- @classmethod + @staticmethod 混用在一个类中很深
- try: ... except Exception: ... （太宽泛）
- logger.error("xxx", exc_info=True) 这种老写法 → 改用 logger.exception()
- 使用 os.path → 全部用 pathlib.Path


# 本项目
from app.core import settings
from app.domain import User, UserId
from app.repositories import UserRepository
from app.services import UserService

任何时候你打算：
- 运行 python、pip、pytest、ruff、black、isort、mypy、streamlit、uvicorn 等命令
- 生成可以运行的代码片段并建议执行
- 使用终端执行任何项目相关操作

你**必须**先执行以下检查/激活步骤之一，且**必须看到 (py312aiproxy)** 提示才可以继续：
你**必须**每次收到对话需求后，先回答**yes sir** 才继续任务,每个不同的研究任务生成不同的独立的markdown文件

```bash
conda activate py312aiproxy || echo "请先手动激活 py312aiproxy"
# 或者更保险：
source $(conda info --base)/etc/profile.d/conda.sh && conda activate py312aiproxy
