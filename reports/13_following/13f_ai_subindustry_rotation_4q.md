# 最近4个季度13F调仓中的AI细分行业资金迁移

- 生成时间：2026-07-03 13:00:32
- 数据目录：`/Users/scottliyq/go/codex_space/stock_13f/reports/13_following/data`
- 样本口径：每个季度优先选取同季度可用的最大 `topN` 股票/ETF 调仓榜，本次实际为最近 4 个季度。
- 观察重点：`top_new_manager_count` 反映“当季新进机构最多”的方向，`top_reduced_manager_count` 反映“当季减仓/退出机构最多”的方向，`top_total_holding_value` 作为存量拥挤度背景参考。
- 分析方法：以下以“单季度截面”为主，不再把 4 个季度简单合并后作为主判断依据。

## 重点结论

- 最新季度 `2026-03-31` 的AI加仓主线是 **AI平台/软件**，减仓主线是 **AI平台/软件**。
- 过去 4 个季度里，AI 加仓领先细分行业的季度路径大致是：`AI平台/软件 -> AI平台/软件 -> AI平台/软件 -> AI平台/软件`。
- 同期 AI 减仓领先细分行业的季度路径大致是：`AI终端/自动驾驶 -> AI平台/软件 -> AI云/算力 -> AI平台/软件`。
- 这说明资金并非统一增减 AI，而是按季度在平台软件、算力硬件、数据中心配套和科技 ETF 之间做结构性切换。
- ETF 加仓层面，最新季度高频出现的 AI 代理仓位包括 QQQ（纳指/大型科技）、XLK（科技板块）、IGV（软件）、SMH（半导体）、VGT（科技板块），说明部分资金仍通过板块 ETF 而非单票来表达 AI 风险偏好。
- ETF 减仓层面，最新季度被明显调出的 AI 代理仓位包括 QQQ（纳指/大型科技）、XLK（科技板块）、VGT（科技板块）、IYW（科技板块）、SMH（半导体），显示机构也在主动压缩部分宽基科技与 AI beta 敞口。

## 季度导航

| 季度 | AI新增机构合计 | AI减仓机构合计 | 加仓领先细分行业 | 减仓领先细分行业 | 加仓代表股 | 减仓代表股 | 加仓ETF | 减仓ETF |
| --- | ---: | ---: | --- | --- | --- | --- | --- | --- |
| 2026-03-31 | 8622 | 49859 | AI平台/软件 | AI平台/软件 | AMAT、SNDK、NVDA、LITE | MSFT、AAPL、AMZN、NVDA | QQQ、XLK、IGV | QQQ、XLK、VGT |
| 2025-12-31 | 10311 | 24218 | AI平台/软件 | AI云/算力 | AMZN、GOOGL、NVDA、MSFT | MSFT、ORCL、META、NVDA | XLK、QQQ、VGT | XLK、QQQ、VGT |
| 2025-09-30 | 8779 | 10708 | AI平台/软件 | AI平台/软件 | SNOW、TSLA、ORCL、AVGO | CRM、META、AMZN、NOW | QQQ、XLK、SHLD | QQQ、XLK、IYW |
| 2025-06-30 | 8510 | 7148 | AI平台/软件 | AI终端/自动驾驶 | ORCL、AVGO、PLTR、AMD | AAPL、INTC、CRM、BABA | QQQ、XLK、VGT | IBB、QQQ、XLK |

## 2026-03-31 季度分析

- 当季 AI 加仓领先细分行业：**AI平台/软件**；代表股票：AMAT、SNDK、NVDA、LITE、LRCX。
- 当季 AI 减仓领先细分行业：**AI平台/软件**；代表股票：MSFT、AAPL、AMZN、NVDA、GOOGL。
- ETF 侧的 AI 代理仓位：加仓以 QQQ、XLK、IGV、SMH 为主，减仓以 QQQ、XLK、VGT、IYW 为主。

### AI细分行业加仓汇总

| 细分行业 | 新增机构数 | 新进持仓金额 | 当前持仓市值 | 代表公司 |
| --- | ---: | ---: | ---: | --- |
| AI平台/软件 | 1828 | $67.53B | $2561.12B | ALPHABET INC - CAP STK CL A、ALPHABET INC - CAP STK CL C、META PLATFORMS INC、PALANTIR TECHNOLOGIES INC |
| AI芯片 | 1450 | $75.39B | $3304.22B | ADVANCED MICRO DEVICES INC、BROADCOM INC、NVIDIA CORPORATION、TAIWAN SEMICONDUCTOR MANUFAC - SPONSORED ADS |
| 设备/制造 | 1413 | $16.89B | $510.93B | APPLIED MATLS INC、ASML HLDG NV - N Y REGISTRY SHS、KLA CORP、LAM RESEARCH CORP |
| AI云/算力 | 1243 | $59.14B | $2757.87B | AMAZON COM INC、DELL TECHNOLOGIES INC、MICROSOFT CORP、ORACLE CORP |
| 光通信/网络 | 932 | $8.83B | $129.78B | COHERENT CORP、LUMENTUM HLDGS INC、MARVELL TECHNOLOGY INC |
| AI终端/自动驾驶 | 626 | $49.23B | $2177.57B | APPLE INC、TESLA INC |
| AI storage | 459 | $5.20B | $55.30B | SANDISK CORP |
| AI芯片/设备 | 349 | $2.81B | $113.57B | INTEL CORP |

### AI细分行业减仓汇总

| 细分行业 | 减仓机构数 | 减仓金额 | 当前持仓市值 | 代表公司 |
| --- | ---: | ---: | ---: | --- |
| AI平台/软件 | 17645 | $1039.41B | $2610.95B | ALPHABET INC - CAP STK CL A、ALPHABET INC - CAP STK CL C、CROWDSTRIKE HLDGS INC、META PLATFORMS INC |
| AI云/算力 | 12152 | $1327.39B | $2728.32B | AMAZON COM INC、MICROSOFT CORP、ORACLE CORP |
| AI芯片 | 8886 | $1027.62B | $3102.47B | ADVANCED MICRO DEVICES INC、BROADCOM INC、NVIDIA CORPORATION |
| AI终端/自动驾驶 | 7707 | $820.75B | $2177.57B | APPLE INC、TESLA INC |
| 数据中心/电力 | 1417 | $33.07B | $61.78B | CONSTELLATION ENERGY CORP |
| 光通信/网络 | 1078 | $22.67B | $78.60B | ARISTA NETWORKS INC - COM SHS |
| AI芯片/设备 | 974 | $20.25B | $49.63B | CADENCE DESIGN SYSTEM INC |

### AI重点加仓名单

| 排名 | 股票 | 细分行业 | 新增机构数 | 新进持仓金额 | 业务简述 |
| --- | --- | --- | ---: | ---: | --- |
| 1 | APPLIED MATLS INC (AMAT) | 设备/制造 | 471 | $4.96B | 公开股票/权益证券，主营业务需结合公司最新披露进一步核实。 |
| 2 | SANDISK CORP (SNDK) | AI storage | 459 | $5.20B | 闪存和存储产品公司，提供 NAND、SSD 和数据存储解决方案。 |
| 3 | NVIDIA CORPORATION (NVDA) | AI芯片 | 388 | $47.33B | GPU、AI 加速器、网络和数据中心计算平台公司。 |
| 4 | LUMENTUM HLDGS INC (LITE) | 光通信/网络 | 381 | $3.78B | 光通信和激光器件供应商，产品用于数据中心、通信网络、工业和消费电子。 |
| 5 | LAM RESEARCH CORP (LRCX) | 设备/制造 | 373 | $4.56B | 公开股票/权益证券，主营业务需结合公司最新披露进一步核实。 |
| 6 | AMAZON COM INC (AMZN) | AI云/算力 | 366 | $22.78B | 公开股票/权益证券，主营业务需结合公司最新披露进一步核实。 |
| 7 | TAIWAN SEMICONDUCTOR MANUFAC - SPONSORED ADS (TSM) | AI芯片 | 361 | $7.27B | 全球领先晶圆代工厂，制造先进制程芯片。 |
| 8 | MICROSOFT CORP (MSFT) | AI云/算力 | 360 | $32.47B | 企业软件、Azure 云、Office、Windows、GitHub 和 AI 平台公司。 |
| 9 | BROADCOM INC (AVGO) | AI芯片 | 357 | $16.12B | 半导体和基础设施软件公司，重点包括网络芯片、交换芯片、定制 ASIC 和连接方案。 |
| 10 | APPLE INC (AAPL) | AI终端/自动驾驶 | 353 | $39.57B | 消费电子、操作系统、服务和芯片生态公司，核心产品包括 iPhone、Mac、iPad、可穿戴设备和服务。 |
| 11 | INTEL CORP (INTC) | AI芯片/设备 | 349 | $2.81B | 半导体公司，业务覆盖 CPU、数据中心芯片、AI 加速器、网络芯片和晶圆代工。 |
| 12 | ADVANCED MICRO DEVICES INC (AMD) | AI芯片 | 344 | $4.67B | CPU、GPU 和数据中心加速器公司，提供 EPYC CPU、Instinct GPU 等 AI 算力产品。 |
| 13 | ALPHABET INC - CAP STK CL A (GOOGL) | AI平台/软件 | 337 | $23.89B | 搜索、广告、YouTube、Android 和 Google Cloud 平台公司。 |
| 14 | META PLATFORMS INC (META) | AI平台/软件 | 328 | $17.01B | 公开股票/权益证券，主营业务需结合公司最新披露进一步核实。 |
| 15 | ALPHABET INC - CAP STK CL C (GOOGL) | AI平台/软件 | 322 | $17.34B | 搜索、广告、YouTube、Android 和 Google Cloud 平台公司。 |
| 16 | VERTIV HOLDINGS CO - COM CL A (VRT) | 数据中心/电力 | 322 | $2.11B | 公开股票/权益证券，主营业务需结合公司最新披露进一步核实。 |
| 17 | ASML HLDG NV - N Y REGISTRY SHS (ASML) | 设备/制造 | 312 | $3.90B | 先进光刻设备供应商，EUV/DUV 设备是先进制程扩产的关键瓶颈。 |
| 18 | SERVICENOW INC (NOW) | AI平台/软件 | 297 | $2.62B | 公开股票/权益证券，主营业务需结合公司最新披露进一步核实。 |
| 19 | COHERENT CORP (COHR) | 光通信/网络 | 288 | $2.98B | 光子、激光、材料和网络器件供应商，服务通信、工业、电子和仪器市场。 |
| 20 | PALANTIR TECHNOLOGIES INC (PLTR) | AI平台/软件 | 280 | $3.96B | 公开股票/权益证券，主营业务需结合公司最新披露进一步核实。 |

### AI重点减仓名单

| 排名 | 股票 | 细分行业 | 减仓机构数 | 减仓金额 | 业务简述 |
| --- | --- | --- | ---: | ---: | --- |
| 1 | MICROSOFT CORP (MSFT) | AI云/算力 | 5005 | $878.23B | 企业软件、Azure 云、Office、Windows、GitHub 和 AI 平台公司。 |
| 2 | APPLE INC (AAPL) | AI终端/自动驾驶 | 4435 | $590.19B | 消费电子、操作系统、服务和芯片生态公司，核心产品包括 iPhone、Mac、iPad、可穿戴设备和服务。 |
| 3 | AMAZON COM INC (AMZN) | AI云/算力 | 4316 | $361.99B | 公开股票/权益证券，主营业务需结合公司最新披露进一步核实。 |
| 4 | NVIDIA CORPORATION (NVDA) | AI芯片 | 3858 | $655.52B | GPU、AI 加速器、网络和数据中心计算平台公司。 |
| 5 | ALPHABET INC - CAP STK CL A (GOOGL) | AI平台/软件 | 3702 | $298.30B | 搜索、广告、YouTube、Android 和 Google Cloud 平台公司。 |
| 6 | META PLATFORMS INC (META) | AI平台/软件 | 3401 | $277.05B | 公开股票/权益证券，主营业务需结合公司最新披露进一步核实。 |
| 7 | ALPHABET INC - CAP STK CL C (GOOGL) | AI平台/软件 | 3401 | $229.11B | 搜索、广告、YouTube、Android 和 Google Cloud 平台公司。 |
| 8 | TESLA INC (TSLA) | AI终端/自动驾驶 | 3272 | $230.56B | 电动车、能源、自动驾驶和机器人公司。 |
| 9 | BROADCOM INC (AVGO) | AI芯片 | 3191 | $313.49B | 半导体和基础设施软件公司，重点包括网络芯片、交换芯片、定制 ASIC 和连接方案。 |
| 10 | ORACLE CORP (ORCL) | AI云/算力 | 2831 | $87.17B | 数据库、企业软件和云基础设施公司，正在扩张 AI 云和 GPU 算力基础设施。 |
| 11 | SALESFORCE INC (CRM) | AI平台/软件 | 2198 | $78.44B | 公开股票/权益证券，主营业务需结合公司最新披露进一步核实。 |
| 12 | PALANTIR TECHNOLOGIES INC (PLTR) | AI平台/软件 | 1978 | $75.00B | 公开股票/权益证券，主营业务需结合公司最新披露进一步核实。 |
| 13 | ADVANCED MICRO DEVICES INC (AMD) | AI芯片 | 1837 | $58.61B | CPU、GPU 和数据中心加速器公司，提供 EPYC CPU、Instinct GPU 等 AI 算力产品。 |
| 14 | SERVICENOW INC (NOW) | AI平台/软件 | 1589 | $56.26B | 公开股票/权益证券，主营业务需结合公司最新披露进一步核实。 |
| 15 | CONSTELLATION ENERGY CORP (CEG) | 数据中心/电力 | 1417 | $33.07B | 公开股票/权益证券，主营业务需结合公司最新披露进一步核实。 |
| 16 | CROWDSTRIKE HLDGS INC (CRWD) | AI平台/软件 | 1376 | $25.23B | 公开股票/权益证券，主营业务需结合公司最新披露进一步核实。 |
| 17 | ARISTA NETWORKS INC - COM SHS (ANET) | 光通信/网络 | 1078 | $22.67B | 公开股票/权益证券，主营业务需结合公司最新披露进一步核实。 |
| 18 | CADENCE DESIGN SYSTEM INC (CDNS) | AI芯片/设备 | 974 | $20.25B | 公开股票/权益证券，主营业务需结合公司最新披露进一步核实。 |

### AI代理ETF：加仓与减仓

| 方向 | 代表ETF | 主题 | 机构数 | 变动金额 |
| --- | --- | --- | ---: | ---: |
| 加仓 | INVESCO QQQ TR - UNIT SER 1 (QQQ) | 纳指/大型科技 | 272 | $2.68B |
| 加仓 | SELECT SECTOR SPDR TR - STATE STREET TEC (XLK) | 科技板块 | 229 | $2.12B |
| 加仓 | ISHARES TR - EXPANDED TECH (IGV) | 软件 | 226 | $2.51B |
| 加仓 | VANECK ETF TRUST - SEMICONDUCTR ETF (SMH) | 半导体 | 180 | $1.21B |
| 加仓 | VANGUARD WORLD FD - INF TECH ETF (VGT) | 科技板块 | 135 | $308.2M |
| 加仓 | GLOBAL X FDS - DEFENSE TECH ETF (SHLD) | 科技板块 | 132 | $306.9M |
| 减仓 | INVESCO QQQ TR - UNIT SER 1 (QQQ) | 纳指/大型科技 | 2505 | $15.56B |
| 减仓 | SELECT SECTOR SPDR TR - STATE STREET TEC (XLK) | 科技板块 | 1489 | $4.15B |
| 减仓 | VANGUARD WORLD FD - INF TECH ETF (VGT) | 科技板块 | 1368 | $3.25B |
| 减仓 | ISHARES TR - U.S. TECH ETF (IYW) | 科技板块 | 893 | $1.95B |
| 减仓 | VANECK ETF TRUST - MRNGSTR WDE MOAT (SMH) | 半导体 | 506 | $919.8M |
| 减仓 | FIRST TR EXCHANGE TRADED FD - NASDAQ CYB ETF (CIBR) | 网络安全 | 488 | $940.3M |

## 2025-12-31 季度分析

- 当季 AI 加仓领先细分行业：**AI平台/软件**；代表股票：AMZN、GOOGL、NVDA、MSFT、AAPL。
- 当季 AI 减仓领先细分行业：**AI云/算力**；代表股票：MSFT、ORCL、META、NVDA、NOW。
- ETF 侧的 AI 代理仓位：加仓以 XLK、QQQ、VGT、SMH 为主，减仓以 XLK、QQQ、VGT、IGV 为主。

### AI细分行业加仓汇总

| 细分行业 | 新增机构数 | 新进持仓金额 | 当前持仓市值 | 代表公司 |
| --- | ---: | ---: | ---: | --- |
| AI平台/软件 | 3115 | $136.63B | $3498.41B | ALPHABET INC - CAP STK CL A、ALPHABET INC - CAP STK CL C、CROWDSTRIKE HLDGS INC、META PLATFORMS INC |
| AI芯片 | 2228 | $139.97B | $4178.88B | ADVANCED MICRO DEVICES INC、BROADCOM INC、NVIDIA CORPORATION、TAIWAN SEMICONDUCTOR MFG LTD - SPONSORED ADS |
| AI云/算力 | 1740 | $139.63B | $3947.88B | AMAZON COM INC、MICROSOFT CORP、ORACLE CORP |
| 设备/制造 | 1352 | $19.69B | $470.84B | APPLIED MATLS INC、ASML HOLDING N V - N Y REGISTRY SHS、KLA CORP、LAM RESEARCH CORP |
| AI终端/自动驾驶 | 1173 | $99.35B | $2909.94B | APPLE INC、TESLA INC |
| AI芯片/设备 | 390 | $12.22B | $108.09B | INTEL CORP |
| 数据中心/电力 | 313 | $3.14B | $82.48B | CONSTELLATION ENERGY CORP |

### AI细分行业减仓汇总

| 细分行业 | 减仓机构数 | 减仓金额 | 当前持仓市值 | 代表公司 |
| --- | ---: | ---: | ---: | --- |
| AI云/算力 | 8233 | $349.43B | $3947.88B | AMAZON COM INC、MICROSOFT CORP、ORACLE CORP |
| AI平台/软件 | 7139 | $184.13B | $1316.69B | CROWDSTRIKE HLDGS INC、META PLATFORMS INC、PALANTIR TECHNOLOGIES INC、SERVICENOW INC |
| AI芯片 | 3703 | $123.81B | $3789.63B | BROADCOM INC、NVIDIA CORPORATION |
| AI终端/自动驾驶 | 2152 | $77.24B | $2909.94B | APPLE INC、TESLA INC |
| 光通信/网络 | 1125 | $18.22B | $94.53B | ARISTA NETWORKS INC - COM SHS |
| 数据中心/电力 | 937 | $12.06B | $42.11B | VISTRA CORP |
| AI芯片/设备 | 929 | $11.96B | $64.98B | CADENCE DESIGN SYSTEM INC |

### AI重点加仓名单

| 排名 | 股票 | 细分行业 | 新增机构数 | 新进持仓金额 | 业务简述 |
| --- | --- | --- | ---: | ---: | --- |
| 1 | AMAZON COM INC (AMZN) | AI云/算力 | 683 | $51.81B | 公开股票/权益证券，主营业务需结合公司最新披露进一步核实。 |
| 2 | ALPHABET INC - CAP STK CL A (GOOGL) | AI平台/软件 | 682 | $48.12B | 搜索、广告、YouTube、Android 和 Google Cloud 平台公司。 |
| 3 | NVIDIA CORPORATION (NVDA) | AI芯片 | 647 | $91.24B | GPU、AI 加速器、网络和数据中心计算平台公司。 |
| 4 | MICROSOFT CORP (MSFT) | AI云/算力 | 641 | $80.20B | 企业软件、Azure 云、Office、Windows、GitHub 和 AI 平台公司。 |
| 5 | APPLE INC (AAPL) | AI终端/自动驾驶 | 640 | $75.52B | 消费电子、操作系统、服务和芯片生态公司，核心产品包括 iPhone、Mac、iPad、可穿戴设备和服务。 |
| 6 | ALPHABET INC - CAP STK CL C (GOOGL) | AI平台/软件 | 609 | $29.00B | 搜索、广告、YouTube、Android 和 Google Cloud 平台公司。 |
| 7 | BROADCOM INC (AVGO) | AI芯片 | 587 | $36.45B | 半导体和基础设施软件公司，重点包括网络芯片、交换芯片、定制 ASIC 和连接方案。 |
| 8 | ADVANCED MICRO DEVICES INC (AMD) | AI芯片 | 581 | $9.22B | CPU、GPU 和数据中心加速器公司，提供 EPYC CPU、Instinct GPU 等 AI 算力产品。 |
| 9 | TESLA INC (TSLA) | AI终端/自动驾驶 | 533 | $23.83B | 电动车、能源、自动驾驶和机器人公司。 |
| 10 | META PLATFORMS INC (META) | AI平台/软件 | 519 | $35.08B | 公开股票/权益证券，主营业务需结合公司最新披露进一步核实。 |
| 11 | ORACLE CORP (ORCL) | AI云/算力 | 416 | $7.61B | 数据库、企业软件和云基础设施公司，正在扩张 AI 云和 GPU 算力基础设施。 |
| 12 | TAIWAN SEMICONDUCTOR MFG LTD - SPONSORED ADS (TSM) | AI芯片 | 413 | $3.06B | 全球领先晶圆代工厂，制造先进制程芯片。 |
| 13 | APPLIED MATLS INC (AMAT) | 设备/制造 | 402 | $5.97B | 公开股票/权益证券，主营业务需结合公司最新披露进一步核实。 |
| 14 | INTEL CORP (INTC) | AI芯片/设备 | 390 | $12.22B | 半导体公司，业务覆盖 CPU、数据中心芯片、AI 加速器、网络芯片和晶圆代工。 |
| 15 | LAM RESEARCH CORP (LRCX) | 设备/制造 | 386 | $6.28B | 公开股票/权益证券，主营业务需结合公司最新披露进一步核实。 |
| 16 | PALANTIR TECHNOLOGIES INC (PLTR) | AI平台/软件 | 378 | $8.14B | 公开股票/权益证券，主营业务需结合公司最新披露进一步核实。 |
| 17 | SALESFORCE INC (CRM) | AI平台/软件 | 360 | $8.27B | 公开股票/权益证券，主营业务需结合公司最新披露进一步核实。 |
| 18 | CONSTELLATION ENERGY CORP (CEG) | 数据中心/电力 | 313 | $3.14B | 公开股票/权益证券，主营业务需结合公司最新披露进一步核实。 |
| 19 | SERVICENOW INC (NOW) | AI平台/软件 | 300 | $5.15B | 公开股票/权益证券，主营业务需结合公司最新披露进一步核实。 |
| 20 | ASML HOLDING N V - N Y REGISTRY SHS (ASML) | 设备/制造 | 295 | $2.49B | 先进光刻设备供应商，EUV/DUV 设备是先进制程扩产的关键瓶颈。 |

### AI重点减仓名单

| 排名 | 股票 | 细分行业 | 减仓机构数 | 减仓金额 | 业务简述 |
| --- | --- | --- | ---: | ---: | --- |
| 1 | MICROSOFT CORP (MSFT) | AI云/算力 | 4252 | $209.80B | 企业软件、Azure 云、Office、Windows、GitHub 和 AI 平台公司。 |
| 2 | ORACLE CORP (ORCL) | AI云/算力 | 2981 | $101.42B | 数据库、企业软件和云基础设施公司，正在扩张 AI 云和 GPU 算力基础设施。 |
| 3 | META PLATFORMS INC (META) | AI平台/软件 | 2980 | $137.39B | 公开股票/权益证券，主营业务需结合公司最新披露进一步核实。 |
| 4 | NVIDIA CORPORATION (NVDA) | AI芯片 | 2600 | $96.99B | GPU、AI 加速器、网络和数据中心计算平台公司。 |
| 5 | SERVICENOW INC (NOW) | AI平台/软件 | 1586 | $31.58B | 公开股票/权益证券，主营业务需结合公司最新披露进一步核实。 |
| 6 | PALANTIR TECHNOLOGIES INC (PLTR) | AI平台/软件 | 1462 | $10.31B | 公开股票/权益证券，主营业务需结合公司最新披露进一步核实。 |
| 7 | TESLA INC (TSLA) | AI终端/自动驾驶 | 1225 | $24.72B | 电动车、能源、自动驾驶和机器人公司。 |
| 8 | ARISTA NETWORKS INC - COM SHS (ANET) | 光通信/网络 | 1125 | $18.22B | 公开股票/权益证券，主营业务需结合公司最新披露进一步核实。 |
| 9 | CROWDSTRIKE HLDGS INC (CRWD) | AI平台/软件 | 1111 | $4.84B | 公开股票/权益证券，主营业务需结合公司最新披露进一步核实。 |
| 10 | BROADCOM INC (AVGO) | AI芯片 | 1103 | $26.82B | 半导体和基础设施软件公司，重点包括网络芯片、交换芯片、定制 ASIC 和连接方案。 |
| 11 | AMAZON COM INC (AMZN) | AI云/算力 | 1000 | $38.21B | 公开股票/权益证券，主营业务需结合公司最新披露进一步核实。 |
| 12 | VISTRA CORP (VST) | 数据中心/电力 | 937 | $12.06B | 公开股票/权益证券，主营业务需结合公司最新披露进一步核实。 |
| 13 | CADENCE DESIGN SYSTEM INC (CDNS) | AI芯片/设备 | 929 | $11.96B | 公开股票/权益证券，主营业务需结合公司最新披露进一步核实。 |
| 14 | APPLE INC (AAPL) | AI终端/自动驾驶 | 927 | $52.52B | 消费电子、操作系统、服务和芯片生态公司，核心产品包括 iPhone、Mac、iPad、可穿戴设备和服务。 |

### AI代理ETF：加仓与减仓

| 方向 | 代表ETF | 主题 | 机构数 | 变动金额 |
| --- | --- | --- | ---: | ---: |
| 加仓 | SELECT SECTOR SPDR TR - STATE STREET TEC (XLK) | 科技板块 | 1789 | $36.07B |
| 加仓 | INVESCO QQQ TR - UNIT SER 1 (QQQ) | 纳指/大型科技 | 438 | $4.12B |
| 加仓 | VANGUARD WORLD FD - INF TECH ETF (VGT) | 科技板块 | 223 | $703.9M |
| 加仓 | VANECK ETF TRUST - SEMICONDUCTR ETF (SMH) | 半导体 | 203 | $796.4M |
| 加仓 | ISHARES TR - ISHARES BIOTECH (IBB) | 科技板块 | 178 | $268.8M |
| 减仓 | SELECT SECTOR SPDR TR - TECHNOLOGY (XLK) | 科技板块 | 1681 | $34.62B |
| 减仓 | INVESCO QQQ TR - UNIT SER 1 (QQQ) | 纳指/大型科技 | 916 | $11.81B |
| 减仓 | VANGUARD WORLD FD - INF TECH ETF (VGT) | 科技板块 | 518 | $2.29B |
| 减仓 | ISHARES TR - EXPANDED TECH (IGV) | 软件 | 433 | $1.15B |
| 减仓 | SPDR SERIES TRUST - S&P BIOTECH (XBI) | 科技板块 | 432 | $7.10B |
| 减仓 | ISHARES TR - U.S. TECH ETF (IYW) | 科技板块 | 407 | $1.07B |

## 2025-09-30 季度分析

- 当季 AI 加仓领先细分行业：**AI平台/软件**；代表股票：SNOW、TSLA、ORCL、AVGO、PLTR。
- 当季 AI 减仓领先细分行业：**AI平台/软件**；代表股票：CRM、META、AMZN、NOW、MSFT。
- ETF 侧的 AI 代理仓位：加仓以 QQQ、XLK、SHLD、VGT 为主，减仓以 QQQ、XLK、IYW、VGT 为主。

### AI细分行业加仓汇总

| 细分行业 | 新增机构数 | 新进持仓金额 | 当前持仓市值 | 代表公司 |
| --- | ---: | ---: | ---: | --- |
| AI平台/软件 | 2742 | $86.25B | $2972.66B | ALIBABA GROUP HLDG LTD - SPONSORED ADS、ALPHABET INC - CAP STK CL A、ALPHABET INC - CAP STK CL C、META PLATFORMS INC |
| AI云/算力 | 1377 | $43.99B | $4091.25B | AMAZON COM INC、COREWEAVE INC - COM CL A、DELL TECHNOLOGIES INC、MICROSOFT CORP |
| AI芯片 | 1329 | $51.29B | $3980.61B | ADVANCED MICRO DEVICES INC、BROADCOM INC、NVIDIA CORPORATION、TAIWAN SEMICONDUCTOR MFG LTD - SPONSORED ADS |
| 数据中心/电力 | 826 | $4.31B | $177.66B | BLOOM ENERGY CORP - COM CL A、CONSTELLATION ENERGY CORP、VERTIV HOLDINGS CO - COM CL A、VISTRA CORP |
| 设备/制造 | 728 | $7.61B | $276.59B | APPLIED MATLS INC、ASML HOLDING N V - N Y REGISTRY SHS、LAM RESEARCH CORP |
| AI终端/自动驾驶 | 682 | $30.34B | $2689.35B | APPLE INC、TESLA INC |
| AI芯片/设备 | 612 | $7.35B | $160.09B | INTEL CORP、SYNOPSYS INC |
| 光通信/网络 | 483 | $2.75B | $157.95B | ARISTA NETWORKS INC - COM SHS、MARVELL TECHNOLOGY INC |

### AI细分行业减仓汇总

| 细分行业 | 减仓机构数 | 减仓金额 | 当前持仓市值 | 代表公司 |
| --- | ---: | ---: | ---: | --- |
| AI平台/软件 | 7653 | $178.67B | $1383.85B | CROWDSTRIKE HLDGS INC、META PLATFORMS INC、SALESFORCE INC、SERVICENOW INC |
| AI云/算力 | 3055 | $145.37B | $3733.27B | AMAZON COM INC、MICROSOFT CORP |

### AI重点加仓名单

| 排名 | 股票 | 细分行业 | 新增机构数 | 新进持仓金额 | 业务简述 |
| --- | --- | --- | ---: | ---: | --- |
| 1 | SNOWFLAKE INC - COM SHS (SNOW) | AI平台/软件 | 910 | $45.18B | 云数据仓库和数据平台公司，帮助企业管理、共享和分析数据。 |
| 2 | TESLA INC (TSLA) | AI终端/自动驾驶 | 420 | $6.80B | 电动车、能源、自动驾驶和机器人公司。 |
| 3 | ORACLE CORP (ORCL) | AI云/算力 | 395 | $3.30B | 数据库、企业软件和云基础设施公司，正在扩张 AI 云和 GPU 算力基础设施。 |
| 4 | BROADCOM INC (AVGO) | AI芯片 | 388 | $13.08B | 半导体和基础设施软件公司，重点包括网络芯片、交换芯片、定制 ASIC 和连接方案。 |
| 5 | PALANTIR TECHNOLOGIES INC (PLTR) | AI平台/软件 | 373 | $1.72B | 公开股票/权益证券，主营业务需结合公司最新披露进一步核实。 |
| 6 | ALPHABET INC - CAP STK CL A (GOOGL) | AI平台/软件 | 372 | $15.80B | 搜索、广告、YouTube、Android 和 Google Cloud 平台公司。 |
| 7 | ALPHABET INC - CAP STK CL C (GOOGL) | AI平台/软件 | 362 | $7.72B | 搜索、广告、YouTube、Android 和 Google Cloud 平台公司。 |
| 8 | INTEL CORP (INTC) | AI芯片/设备 | 353 | $4.14B | 半导体公司，业务覆盖 CPU、数据中心芯片、AI 加速器、网络芯片和晶圆代工。 |
| 9 | ADVANCED MICRO DEVICES INC (AMD) | AI芯片 | 350 | $4.84B | CPU、GPU 和数据中心加速器公司，提供 EPYC CPU、Instinct GPU 等 AI 算力产品。 |
| 10 | NVIDIA CORPORATION (NVDA) | AI芯片 | 303 | $29.40B | GPU、AI 加速器、网络和数据中心计算平台公司。 |
| 11 | LAM RESEARCH CORP (LRCX) | 设备/制造 | 290 | $2.05B | 公开股票/权益证券，主营业务需结合公司最新披露进一步核实。 |
| 12 | META PLATFORMS INC (META) | AI平台/软件 | 288 | $9.82B | 公开股票/权益证券，主营业务需结合公司最新披露进一步核实。 |
| 13 | TAIWAN SEMICONDUCTOR MFG LTD - SPONSORED ADS (TSM) | AI芯片 | 288 | $3.97B | 全球领先晶圆代工厂，制造先进制程芯片。 |
| 14 | ARISTA NETWORKS INC - COM SHS (ANET) | 光通信/网络 | 282 | $1.08B | 公开股票/权益证券，主营业务需结合公司最新披露进一步核实。 |
| 15 | AMAZON COM INC (AMZN) | AI云/算力 | 276 | $13.84B | 公开股票/权益证券，主营业务需结合公司最新披露进一步核实。 |
| 16 | COREWEAVE INC - COM CL A (CRWV) | AI云/算力 | 265 | $3.18B | GPU 云和专用 AI 云基础设施公司，向 AI 实验室和企业出租高性能 GPU 算力。 |
| 17 | APPLE INC (AAPL) | AI终端/自动驾驶 | 262 | $23.54B | 消费电子、操作系统、服务和芯片生态公司，核心产品包括 iPhone、Mac、iPad、可穿戴设备和服务。 |
| 18 | SYNOPSYS INC (SNPS) | AI芯片/设备 | 259 | $3.21B | 公开股票/权益证券，主营业务需结合公司最新披露进一步核实。 |
| 19 | MICROSOFT CORP (MSFT) | AI云/算力 | 251 | $23.21B | 企业软件、Azure 云、Office、Windows、GitHub 和 AI 平台公司。 |
| 20 | ALIBABA GROUP HLDG LTD - SPONSORED ADS (BABA) | AI平台/软件 | 231 | $2.59B | 中国电商、云计算、本地生活和数字媒体公司，拥有阿里云和通义大模型生态。 |

### AI重点减仓名单

| 排名 | 股票 | 细分行业 | 减仓机构数 | 减仓金额 | 业务简述 |
| --- | --- | --- | ---: | ---: | --- |
| 1 | SALESFORCE INC (CRM) | AI平台/软件 | 2089 | $35.92B | 公开股票/权益证券，主营业务需结合公司最新披露进一步核实。 |
| 2 | META PLATFORMS INC (META) | AI平台/软件 | 2067 | $66.06B | 公开股票/权益证券，主营业务需结合公司最新披露进一步核实。 |
| 3 | AMAZON COM INC (AMZN) | AI云/算力 | 1998 | $60.43B | 公开股票/权益证券，主营业务需结合公司最新披露进一步核实。 |
| 4 | SERVICENOW INC (NOW) | AI平台/软件 | 1528 | $25.60B | 公开股票/权益证券，主营业务需结合公司最新披露进一步核实。 |
| 5 | MICROSOFT CORP (MSFT) | AI云/算力 | 1057 | $84.94B | 企业软件、Azure 云、Office、Windows、GitHub 和 AI 平台公司。 |
| 6 | CROWDSTRIKE HLDGS INC (CRWD) | AI平台/软件 | 1047 | $8.18B | 公开股票/权益证券，主营业务需结合公司最新披露进一步核实。 |
| 7 | SNOWFLAKE INC (SNOW) | AI平台/软件 | 922 | $42.91B | 云数据仓库和数据平台公司，帮助企业管理、共享和分析数据。 |

### AI代理ETF：加仓与减仓

| 方向 | 代表ETF | 主题 | 机构数 | 变动金额 |
| --- | --- | --- | ---: | ---: |
| 加仓 | INVESCO QQQ TR - UNIT SER 1 (QQQ) | 纳指/大型科技 | 260 | $2.56B |
| 加仓 | SELECT SECTOR SPDR TR - TECHNOLOGY (XLK) | 科技板块 | 184 | $1.03B |
| 加仓 | GLOBAL X FDS - DEFENSE TECH ETF (SHLD) | 科技板块 | 161 | $401.4M |
| 加仓 | VANGUARD WORLD FD - INF TECH ETF (VGT) | 科技板块 | 150 | $1.95B |
| 加仓 | VANECK ETF TRUST - SEMICONDUCTR ETF (SMH) | 半导体 | 131 | $521.1M |
| 加仓 | ISHARES TR - U.S. TECH ETF (IYW) | 科技板块 | 126 | $135.5M |
| 减仓 | INVESCO QQQ TR - UNIT SER 1 (QQQ) | 纳指/大型科技 | 522 | $6.17B |
| 减仓 | SELECT SECTOR SPDR TR - TECHNOLOGY (XLK) | 科技板块 | 297 | $1.71B |
| 减仓 | ISHARES TR - U.S. TECH ETF (IYW) | 科技板块 | 281 | $2.68B |
| 减仓 | VANGUARD WORLD FD - INF TECH ETF (VGT) | 科技板块 | 219 | $434.2M |

## 2025-06-30 季度分析

- 当季 AI 加仓领先细分行业：**AI平台/软件**；代表股票：ORCL、AVGO、PLTR、AMD、NVDA。
- 当季 AI 减仓领先细分行业：**AI终端/自动驾驶**；代表股票：AAPL、INTC、CRM、BABA。
- ETF 侧的 AI 代理仓位：加仓以 QQQ、XLK、VGT、SMH 为主，减仓以 IBB、QQQ、XLK、XBI 为主。

### AI细分行业加仓汇总

| 细分行业 | 新增机构数 | 新进持仓金额 | 当前持仓市值 | 代表公司 |
| --- | ---: | ---: | ---: | --- |
| AI平台/软件 | 2442 | $87.58B | $2778.72B | ALPHABET INC - CAP STK CL A、ALPHABET INC - CAP STK CL C、CROWDSTRIKE HLDGS INC、META PLATFORMS INC |
| AI芯片 | 1610 | $106.48B | $3397.51B | ADVANCED MICRO DEVICES INC、BROADCOM INC、NVIDIA CORPORATION、TAIWAN SEMICONDUCTOR MFG LTD - SPONSORED ADS |
| AI云/算力 | 1394 | $118.30B | $3900.54B | AMAZON COM INC、COREWEAVE INC - COM CL A、MICROSOFT CORP、ORACLE CORP |
| 设备/制造 | 962 | $12.58B | $308.42B | APPLIED MATLS INC、ASML HOLDING N V - N Y REGISTRY SHS、KLA CORP、LAM RESEARCH CORP |
| 数据中心/电力 | 822 | $5.71B | $159.77B | CONSTELLATION ENERGY CORP、VERTIV HOLDINGS CO - COM CL A、VISTRA CORP |
| AI终端/自动驾驶 | 602 | $63.34B | $2146.71B | APPLE INC、TESLA INC |
| 光通信/网络 | 477 | $5.44B | $121.58B | ARISTA NETWORKS INC - COM SHS、MARVELL TECHNOLOGY INC |
| AI芯片/设备 | 201 | $2.62B | $63.29B | CADENCE DESIGN SYSTEM INC |

### AI细分行业减仓汇总

| 细分行业 | 减仓机构数 | 减仓金额 | 当前持仓市值 | 代表公司 |
| --- | ---: | ---: | ---: | --- |
| AI终端/自动驾驶 | 4118 | $173.35B | $1708.49B | APPLE INC |
| AI平台/软件 | 1826 | $30.02B | $207.95B | ALIBABA GROUP HLDG LTD - SPONSORED ADS、SALESFORCE INC |
| AI芯片/设备 | 1204 | $2.95B | $57.51B | INTEL CORP |

### AI重点加仓名单

| 排名 | 股票 | 细分行业 | 新增机构数 | 新进持仓金额 | 业务简述 |
| --- | --- | --- | ---: | ---: | --- |
| 1 | ORACLE CORP (ORCL) | AI云/算力 | 533 | $9.38B | 数据库、企业软件和云基础设施公司，正在扩张 AI 云和 GPU 算力基础设施。 |
| 2 | BROADCOM INC (AVGO) | AI芯片 | 483 | $27.42B | 半导体和基础设施软件公司，重点包括网络芯片、交换芯片、定制 ASIC 和连接方案。 |
| 3 | PALANTIR TECHNOLOGIES INC (PLTR) | AI平台/软件 | 468 | $4.90B | 公开股票/权益证券，主营业务需结合公司最新披露进一步核实。 |
| 4 | ADVANCED MICRO DEVICES INC (AMD) | AI芯片 | 406 | $5.54B | CPU、GPU 和数据中心加速器公司，提供 EPYC CPU、Instinct GPU 等 AI 算力产品。 |
| 5 | NVIDIA CORPORATION (NVDA) | AI芯片 | 395 | $70.75B | GPU、AI 加速器、网络和数据中心计算平台公司。 |
| 6 | META PLATFORMS INC (META) | AI平台/软件 | 356 | $31.29B | 公开股票/权益证券，主营业务需结合公司最新披露进一步核实。 |
| 7 | TESLA INC (TSLA) | AI终端/自动驾驶 | 353 | $13.96B | 电动车、能源、自动驾驶和机器人公司。 |
| 8 | TAIWAN SEMICONDUCTOR MFG LTD - SPONSORED ADS (TSM) | AI芯片 | 326 | $2.78B | 全球领先晶圆代工厂，制造先进制程芯片。 |
| 9 | APPLIED MATLS INC (AMAT) | 设备/制造 | 316 | $4.68B | 公开股票/权益证券，主营业务需结合公司最新披露进一步核实。 |
| 10 | AMAZON COM INC (AMZN) | AI云/算力 | 314 | $38.45B | 公开股票/权益证券，主营业务需结合公司最新披露进一步核实。 |
| 11 | CROWDSTRIKE HLDGS INC (CRWD) | AI平台/软件 | 301 | $2.50B | 公开股票/权益证券，主营业务需结合公司最新披露进一步核实。 |
| 12 | CONSTELLATION ENERGY CORP (CEG) | 数据中心/电力 | 298 | $2.19B | 公开股票/权益证券，主营业务需结合公司最新披露进一步核实。 |
| 13 | ALPHABET INC - CAP STK CL A (GOOGL) | AI平台/软件 | 294 | $27.61B | 搜索、广告、YouTube、Android 和 Google Cloud 平台公司。 |
| 14 | MICROSOFT CORP (MSFT) | AI云/算力 | 293 | $69.33B | 企业软件、Azure 云、Office、Windows、GitHub 和 AI 平台公司。 |
| 15 | SERVICENOW INC (NOW) | AI平台/软件 | 278 | $4.54B | 公开股票/权益证券，主营业务需结合公司最新披露进一步核实。 |
| 16 | ALPHABET INC - CAP STK CL C (GOOGL) | AI平台/软件 | 274 | $9.00B | 搜索、广告、YouTube、Android 和 Google Cloud 平台公司。 |
| 17 | VISTRA CORP (VST) | 数据中心/电力 | 262 | $1.97B | 公开股票/权益证券，主营业务需结合公司最新披露进一步核实。 |
| 18 | VERTIV HOLDINGS CO - COM CL A (VRT) | 数据中心/电力 | 262 | $1.55B | 公开股票/权益证券，主营业务需结合公司最新披露进一步核实。 |
| 19 | COREWEAVE INC - COM CL A (CRWV) | AI云/算力 | 254 | $1.15B | GPU 云和专用 AI 云基础设施公司，向 AI 实验室和企业出租高性能 GPU 算力。 |
| 20 | APPLE INC (AAPL) | AI终端/自动驾驶 | 249 | $49.38B | 消费电子、操作系统、服务和芯片生态公司，核心产品包括 iPhone、Mac、iPad、可穿戴设备和服务。 |

### AI重点减仓名单

| 排名 | 股票 | 细分行业 | 减仓机构数 | 减仓金额 | 业务简述 |
| --- | --- | --- | ---: | ---: | --- |
| 1 | APPLE INC (AAPL) | AI终端/自动驾驶 | 4118 | $173.35B | 消费电子、操作系统、服务和芯片生态公司，核心产品包括 iPhone、Mac、iPad、可穿戴设备和服务。 |
| 2 | INTEL CORP (INTC) | AI芯片/设备 | 1204 | $2.95B | 半导体公司，业务覆盖 CPU、数据中心芯片、AI 加速器、网络芯片和晶圆代工。 |
| 3 | SALESFORCE INC (CRM) | AI平台/软件 | 950 | $15.66B | 公开股票/权益证券，主营业务需结合公司最新披露进一步核实。 |
| 4 | ALIBABA GROUP HLDG LTD - SPONSORED ADS (BABA) | AI平台/软件 | 876 | $14.36B | 中国电商、云计算、本地生活和数字媒体公司，拥有阿里云和通义大模型生态。 |

### AI代理ETF：加仓与减仓

| 方向 | 代表ETF | 主题 | 机构数 | 变动金额 |
| --- | --- | --- | ---: | ---: |
| 加仓 | INVESCO QQQ TR - UNIT SER 1 (QQQ) | 纳指/大型科技 | 299 | $2.63B |
| 加仓 | SELECT SECTOR SPDR TR - TECHNOLOGY (XLK) | 科技板块 | 200 | $889.3M |
| 加仓 | VANGUARD WORLD FD - INF TECH ETF (VGT) | 科技板块 | 178 | $385.7M |
| 加仓 | VANECK ETF TRUST - SEMICONDUCTR ETF (SMH) | 半导体 | 177 | $639.9M |
| 加仓 | ISHARES TR - U.S. TECH ETF (IYW) | 科技板块 | 135 | $147.1M |
| 加仓 | FIRST TR EXCHANGE TRADED FD - NASDAQ CYB ETF (CIBR) | 网络安全 | 117 | $102.2M |
| 减仓 | ISHARES TR - ISHARES BIOTECH (IBB) | 科技板块 | 498 | $469.4M |
| 减仓 | INVESCO QQQ TR - UNIT SER 1 (QQQ) | 纳指/大型科技 | 429 | $8.16B |
| 减仓 | SELECT SECTOR SPDR TR - TECHNOLOGY (XLK) | 科技板块 | 274 | $1.82B |
| 减仓 | SPDR SERIES TRUST - S&P BIOTECH (XBI) | 科技板块 | 257 | $657.8M |

## 跨季度观察

- 这份报告的主口径是“逐季度看当期调仓”，所以更适合判断某个季度资金在 AI 链条里具体切向了哪里，而不是看 4 季累计后的平均结果。
- 如果某一季度出现“软件平台继续被加仓、宽基科技 ETF 同时被减仓”，更应理解为 AI 暴露在从被动 beta 转向主动选股，而不是 AI 主线失效。
- 如果某一季度加仓端转向 `设备/制造`、`光通信/网络` 或 `数据中心/电力`，通常意味着市场当期更重视 AI 的二阶瓶颈，而不只是软件叙事。
- 连续两个季度都位于减仓前列的大型科技或主题 ETF，更值得视为阶段性获利了结与仓位重配信号。
