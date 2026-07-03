#!/usr/bin/env python3
"""Monitor selected 13F filings and report AI-related holdings."""

import argparse
import asyncio
import json
import logging
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any


DEFAULT_USER_AGENT = "13f-ai-monitor/1.0 contact@example.com"
WATCHLIST = (
    ("Pershing Square Capital Management, L.P.", 1336528),
    ("Appaloosa Management LP", 1006438),
    ("Situational Awareness LP", 2045724),
    ("Citrine Capital LLC", 2053242),
    ("ARK Investment Management LLC", 1697748),
    ("Light Street Capital Management, LLC", 1569049),
    ("Coatue Management LLC", 1135730),
    ("CastleKnight Management LP", 1835751),
    ("H&H International Investment, LLC", 1759760),
    ("Maverick Capital Ltd", 934639),
    ("Eclipse Operations, LLC", 1908066),
)
FORM_TYPES = {"13F-HR", "13F-HR/A"}
VALUE_DOLLAR_START = date(2023, 1, 3)
LOGGER = logging.getLogger("monitor_13f_ai")


@dataclass(frozen=True)
class ManagerConfig:
    name: str
    cik: int


@dataclass(frozen=True)
class AiRule:
    fragment: str
    theme: str
    reason: str


@dataclass(frozen=True)
class IndustryRule:
    fragment: str
    industry: str
    ai_relationship: str
    ai_connection: str


@dataclass(frozen=True)
class BusinessRule:
    fragment: str
    business: str
    ai_detail: str


@dataclass(frozen=True)
class InfraFlowBucket:
    name: str
    fragments: tuple[str, ...]
    note: str


@dataclass(frozen=True)
class FilingMeta:
    manager_name: str
    cik: int
    form: str
    accession: str
    filing_date: str
    report_date: str
    primary_document: str
    info_table_document: str
    filing_url: str
    info_table_url: str


@dataclass(frozen=True)
class Holding:
    name_of_issuer: str
    title_of_class: str
    cusip: str
    value_usd: int
    shares_or_principal: int
    amount_type: str
    put_call: str
    investment_discretion: str
    voting_sole: int
    voting_shared: int
    voting_none: int
    industry: str
    ai_relationship: str
    ai_connection: str
    ai_theme: str
    ai_reason: str


@dataclass(frozen=True)
class FilingSnapshot:
    manager_name: str
    cik: int
    form: str
    accession: str
    filing_date: str
    report_date: str
    info_table_url: str
    downloaded_at: str
    holdings: list[Holding]


@dataclass(frozen=True)
class HoldingChange:
    key: str
    name_of_issuer: str
    title_of_class: str
    cusip: str
    put_call: str
    industry: str
    ai_relationship: str
    status: str
    previous_shares_or_principal: int
    current_shares_or_principal: int
    share_change: int
    previous_value_usd: int
    current_value_usd: int
    value_change_usd: int
    ai_theme: str
    ai_reason: str


class MonitorError(RuntimeError):
    """Raised when the monitor cannot fetch or parse SEC data."""


AI_RULES = (
    AiRule("NVIDIA", "AI accelerator", "GPU and accelerator supply chain"),
    AiRule("ADVANCED MICRO", "AI accelerator", "GPU and accelerator supply chain"),
    AiRule("INTEL", "AI semiconductor", "AI chips, CPUs, foundry, and data center silicon"),
    AiRule("BROADCOM", "AI semiconductor", "AI networking and custom silicon"),
    AiRule("MARVELL", "AI semiconductor", "AI networking and custom silicon"),
    AiRule("CREDO TECHNOLOGY", "AI optical networking", "high-speed connectivity chips for AI data centers"),
    AiRule("TAIWAN SEMICONDUCTOR", "AI foundry", "advanced AI chip manufacturing"),
    AiRule("ASML", "AI semiconductor equipment", "advanced lithography supply chain"),
    AiRule("APPLIED MATLS", "AI semiconductor equipment", "chip manufacturing equipment"),
    AiRule("LAM RESEARCH", "AI semiconductor equipment", "chip manufacturing equipment"),
    AiRule("KLA", "AI semiconductor equipment", "chip process control"),
    AiRule("ARM", "AI semiconductor IP", "processor IP used in AI edge and servers"),
    AiRule("CADENCE", "AI chip design software", "EDA software for chip design"),
    AiRule("SYNOPSYS", "AI chip design software", "EDA software for chip design"),
    AiRule("MICROSOFT", "AI cloud/platform", "cloud AI platform and foundation models"),
    AiRule("ALPHABET", "AI cloud/platform", "AI models, chips, and cloud"),
    AiRule("ALIBABA", "AI cloud/platform", "cloud, commerce data, and foundation model ecosystem"),
    AiRule("AMAZON", "AI cloud/platform", "AWS AI infrastructure and services"),
    AiRule("META PLATFORMS", "AI platform", "large-scale AI infrastructure"),
    AiRule("ORACLE", "AI cloud/platform", "cloud and database AI infrastructure"),
    AiRule("APPLE", "AI device platform", "on-device AI ecosystem"),
    AiRule("SALESFORCE", "AI application software", "enterprise AI software"),
    AiRule("SERVICENOW", "AI application software", "workflow automation and AI software"),
    AiRule("PALANTIR", "AI application software", "AI data and decision platforms"),
    AiRule("SNOWFLAKE", "AI data infrastructure", "enterprise data platform for AI workloads"),
    AiRule("CLOUDFLARE", "AI edge infrastructure", "edge network and AI inference infrastructure"),
    AiRule("DATADOG", "AI observability", "infrastructure observability for AI workloads"),
    AiRule("CROWDSTRIKE", "AI cybersecurity", "security software with AI-driven detection"),
    AiRule("SUPER MICRO", "AI server", "AI server and rack systems"),
    AiRule("DELL", "AI server", "AI server and enterprise infrastructure"),
    AiRule("COREWEAVE", "AI cloud infrastructure", "GPU cloud capacity for AI training and inference"),
    AiRule("CORE SCIENTIFIC", "AI/HPC data center infrastructure", "digital infrastructure and power capacity can be repurposed for AI/HPC hosting"),
    AiRule("APPLIED DIGITAL", "AI data center", "AI and high-performance compute data centers"),
    AiRule("BLOOM ENERGY", "AI data center power", "power supply for AI data centers"),
    AiRule("LUMENTUM", "AI optical networking", "optical connectivity for AI data centers"),
    AiRule("SANDISK", "AI storage", "storage demand from AI data pipelines"),
    AiRule("IREN", "AI/HPC data center infrastructure", "renewable-powered data centers for Bitcoin mining and AI cloud/HPC"),
    AiRule("CIPHER MINING", "AI/HPC data center optionality", "large power sites and data center assets can be redirected toward HPC and AI workloads"),
    AiRule("COHERENT", "AI optical networking", "optical components and lasers for AI data center connectivity"),
    AiRule("SOLARIS ENERGY", "AI data center power", "distributed power equipment for AI data center power demand"),
    AiRule("TOWER SEMICONDUCTOR", "AI semiconductor foundry", "specialty foundry capacity supports analog and mixed-signal chips used around AI systems"),
    AiRule("RIOT PLATFORMS", "AI/HPC data center optionality", "Bitcoin mining power and data center assets can support HPC and AI workloads"),
    AiRule("HUT 8", "AI/HPC data center optionality", "Bitcoin mining and data center assets can support GPU and HPC hosting"),
    AiRule("WHITEFIBER", "AI cloud infrastructure", "GPU cloud and high-performance data center infrastructure"),
    AiRule("POWER SOLUTIONS", "AI data center power", "engines and gensets can support prime and backup power for data centers"),
    AiRule("BITDEER", "AI/HPC data center optionality", "mining and cloud infrastructure can support AI/HPC workloads"),
    AiRule("CLEANSPARK", "AI/HPC power optionality", "Bitcoin mining power portfolio may have AI/HPC hosting optionality"),
    AiRule("BITFARMS", "AI/HPC power optionality", "Bitcoin mining sites may have AI/HPC hosting optionality"),
    AiRule("EQUINIX", "AI data center", "data center infrastructure"),
    AiRule("DIGITAL RLTY", "AI data center", "data center infrastructure"),
    AiRule("VERTIV", "AI data center power", "power and cooling for AI data centers"),
    AiRule("TESLA", "AI/autonomy", "autonomy, robotics, and AI compute"),
    AiRule("TEMPUS AI", "AI healthcare application", "AI-enabled precision medicine and clinical data platform"),
    AiRule("GOOGLE", "AI cloud/platform", "AI models, chips, and cloud"),
)

INDUSTRY_RULES = (
    IndustryRule("NVIDIA", "Semiconductors", "核心AI基础设施", "GPU/加速卡直接决定模型训练与推理算力供给。"),
    IndustryRule("ADVANCED MICRO", "Semiconductors", "核心AI基础设施", "GPU/CPU 加速器参与 AI 服务器算力供给。"),
    IndustryRule("BROADCOM", "Semiconductors", "核心AI基础设施", "网络芯片与定制 ASIC 连接 AI 集群。"),
    IndustryRule("MARVELL", "Semiconductors", "核心AI基础设施", "高速互连和定制芯片受益于 AI 数据中心扩张。"),
    IndustryRule("CREDO TECHNOLOGY", "Optical networking", "AI基础设施配套", "高速连接芯片和 SerDes 方案服务 AI 数据中心互连。"),
    IndustryRule("TAIWAN SEMICONDUCTOR", "Semiconductor foundry", "核心AI基础设施", "先进制程代工承接 AI 芯片制造需求。"),
    IndustryRule("ASML", "Semiconductor equipment", "核心AI基础设施", "EUV 光刻是先进 AI 芯片制造的关键设备。"),
    IndustryRule("APPLIED MATLS", "Semiconductor equipment", "核心AI基础设施", "晶圆制造设备支撑先进芯片产能。"),
    IndustryRule("LAM RESEARCH", "Semiconductor equipment", "核心AI基础设施", "刻蚀/沉积设备支撑先进芯片制造。"),
    IndustryRule("KLA", "Semiconductor equipment", "核心AI基础设施", "过程控制设备提升先进芯片良率。"),
    IndustryRule("ARM", "Semiconductor IP", "核心AI基础设施", "CPU IP 被用于云端、边缘与终端 AI 芯片。"),
    IndustryRule("INTEL", "Semiconductors", "核心AI基础设施", "CPU、加速器、晶圆代工和数据中心芯片均与 AI 算力有关。"),
    IndustryRule("TOWER SEMICONDUCTOR", "Semiconductor foundry", "核心AI基础设施", "特色模拟/混合信号晶圆代工支撑 AI 设备周边芯片。"),
    IndustryRule("CADENCE", "EDA software", "核心AI基础设施", "EDA 工具支撑 AI 芯片设计。"),
    IndustryRule("SYNOPSYS", "EDA software", "核心AI基础设施", "EDA 与 IP 组合支撑 AI 芯片设计。"),
    IndustryRule("SUPER MICRO", "AI servers", "核心AI基础设施", "AI 服务器和整机集成直接承接 GPU 集群需求。"),
    IndustryRule("DELL", "AI servers", "核心AI基础设施", "企业服务器和存储受益于 AI 基础设施采购。"),
    IndustryRule("APPLIED DIGITAL", "Data centers", "核心AI基础设施", "高性能计算和 AI 数据中心提供算力承载。"),
    IndustryRule("COREWEAVE", "Cloud AI infrastructure", "核心AI基础设施", "GPU 云基础设施直接面向 AI 训练和推理需求。"),
    IndustryRule("CORE SCIENTIFIC", "Digital infrastructure", "AI基础设施配套", "矿机托管和电力/机房资产可转向 HPC 与 AI 托管。"),
    IndustryRule("IREN", "Digital infrastructure", "AI基础设施配套", "可再生能源数据中心资产可承载 Bitcoin mining、HPC 与 AI 云服务。"),
    IndustryRule("CIPHER MINING", "Digital infrastructure", "AI基础设施配套", "大规模电力和数据中心站点具备向 HPC/AI 托管转型的可选性。"),
    IndustryRule("RIOT PLATFORMS", "Digital infrastructure", "AI基础设施配套", "Bitcoin mining 的电力和数据中心资产具备 AI/HPC 托管可选性。"),
    IndustryRule("HUT 8", "Digital infrastructure", "AI基础设施配套", "Bitcoin mining、托管和数据中心资产具备 AI/HPC 托管可选性。"),
    IndustryRule("WHITEFIBER", "Cloud AI infrastructure", "核心AI基础设施", "GPU 云和高性能数据中心直接服务 AI 工作负载。"),
    IndustryRule("BITDEER", "Digital infrastructure", "AI基础设施配套", "矿机、云算力和数据中心能力可延伸至 AI/HPC 工作负载。"),
    IndustryRule("CLEANSPARK", "Digital infrastructure", "AI基础设施配套", "Bitcoin mining 的电力资产可能具备 AI/HPC 托管可选性。"),
    IndustryRule("BITFARMS", "Digital infrastructure", "AI基础设施配套", "Bitcoin mining 站点可能具备 AI/HPC 托管可选性。"),
    IndustryRule("EQUINIX", "Data centers", "AI基础设施配套", "数据中心机房承载云与 AI 工作负载。"),
    IndustryRule("DIGITAL RLTY", "Data centers", "AI基础设施配套", "数据中心机房承载云与 AI 工作负载。"),
    IndustryRule("VERTIV", "Data center power/cooling", "AI基础设施配套", "供电与散热是高密度 AI 数据中心瓶颈。"),
    IndustryRule("BLOOM ENERGY", "Power infrastructure", "AI基础设施配套", "AI 数据中心提升稳定电力和分布式能源需求。"),
    IndustryRule("VISTRA", "Power infrastructure", "AI基础设施配套", "电力资产受益于数据中心用电需求增长。"),
    IndustryRule("LUMENTUM", "Optical networking", "AI基础设施配套", "光通信器件服务数据中心高速互连。"),
    IndustryRule("COHERENT", "Optical networking", "AI基础设施配套", "光模块、激光器和材料服务高速数据中心互连。"),
    IndustryRule("SANDISK", "Storage", "AI基础设施配套", "AI 数据流水线提升高性能存储需求。"),
    IndustryRule("MICROSOFT", "Cloud and software", "AI平台/应用", "云平台、企业软件和模型生态连接 AI 应用落地。"),
    IndustryRule("ALPHABET", "Internet platforms and cloud", "AI平台/应用", "搜索、广告、云和自研模型/芯片共同形成 AI 平台。"),
    IndustryRule("GOOGLE", "Internet platforms and cloud", "AI平台/应用", "搜索、广告、云和自研模型/芯片共同形成 AI 平台。"),
    IndustryRule("ALIBABA", "E-commerce and cloud", "AI平台/应用", "云计算、通义模型、电商推荐和企业 AI 服务共同形成 AI 平台暴露。"),
    IndustryRule("AMAZON", "E-commerce and cloud", "AI平台/应用", "AWS 提供 AI 云服务，电商业务也使用推荐与自动化。"),
    IndustryRule("META PLATFORMS", "Internet platforms", "AI平台/应用", "社交平台、广告模型和大规模开源模型形成 AI 投入。"),
    IndustryRule("ORACLE", "Cloud and database", "AI平台/应用", "数据库与云基础设施承接企业 AI 工作负载。"),
    IndustryRule("SALESFORCE", "Enterprise software", "AI平台/应用", "CRM 工作流接入生成式 AI 和自动化。"),
    IndustryRule("SERVICENOW", "Enterprise software", "AI平台/应用", "流程自动化软件接入 AI 助手与企业工作流。"),
    IndustryRule("PALANTIR", "Data and analytics software", "AI平台/应用", "数据平台把企业数据转化为 AI 决策系统。"),
    IndustryRule("SNOWFLAKE", "Data infrastructure software", "AI平台/应用", "数据平台是企业训练、检索和分析 AI 的基础。"),
    IndustryRule("CLOUDFLARE", "Edge infrastructure", "AI平台/应用", "边缘网络可支撑低延迟 AI 推理与安全。"),
    IndustryRule("DATADOG", "Observability software", "AI平台/应用", "监控 AI 工作负载与云基础设施稳定性。"),
    IndustryRule("CROWDSTRIKE", "Cybersecurity software", "AI平台/应用", "AI 驱动安全检测，也保护 AI 基础设施。"),
    IndustryRule("APPLE", "Consumer electronics", "AI终端/生态入口", "终端设备和操作系统是端侧 AI 分发入口。"),
    IndustryRule("TESLA", "Automotive and autonomy", "AI终端/生态入口", "自动驾驶、机器人和车端算力属于 AI 应用。"),
    IndustryRule("TEMPUS AI", "Healthcare AI software", "AI平台/应用", "临床数据、基因组数据和 AI 模型用于精准医疗决策。"),
    IndustryRule("DISNEY", "Media and entertainment", "AI间接受益/运营提效", "媒体、流媒体和主题公园可用 AI 做内容工具、推荐、广告和运营提效。"),
    IndustryRule("BERKSHIRE HATHAWAY", "Investment conglomerate", "非AI核心暴露", "保险、铁路、能源和投资组合驱动，与 AI 关系主要来自所投公司和运营提效。"),
    IndustryRule("PDD", "E-commerce", "AI间接受益/运营提效", "电商平台可用 AI 做推荐、广告、供应链和商家工具，收入并非 AI 原生。"),
    IndustryRule("AMERICAN EXPRESS", "Payments and financial services", "AI间接受益/运营提效", "AI 可用于风控、欺诈检测、客服和营销优化，但不是核心 AI 资产。"),
    IndustryRule("BANK AMERICA", "Banks", "AI间接受益/运营提效", "银行可用 AI 改善风控、投顾、运营和客服效率。"),
    IndustryRule("CAPITAL ONE", "Consumer finance", "AI间接受益/运营提效", "金融科技和风控模型有 AI 应用空间。"),
    IndustryRule("VISA", "Payments", "AI间接受益/运营提效", "支付网络可用 AI 做欺诈检测和交易风控。"),
    IndustryRule("MASTERCARD", "Payments", "AI间接受益/运营提效", "支付网络可用 AI 做欺诈检测和交易风控。"),
    IndustryRule("MOODYS", "Financial data and analytics", "AI间接受益/运营提效", "信用数据和分析产品可嵌入 AI 助手与自动化研究。"),
    IndustryRule("COCA COLA", "Consumer staples", "AI间接受益/运营提效", "AI 主要用于营销、供应链和需求预测，收入不是 AI 原生。"),
    IndustryRule("KRAFT HEINZ", "Consumer staples", "AI间接受益/运营提效", "AI 主要用于供应链、定价和品类管理。"),
    IndustryRule("KROGER", "Consumer staples retail", "AI间接受益/运营提效", "零售可用 AI 做库存、定价、推荐和供应链优化。"),
    IndustryRule("DOMINOS", "Restaurants", "AI间接受益/运营提效", "AI 主要用于门店运营、配送调度和需求预测。"),
    IndustryRule("RESTAURANT BRANDS", "Restaurants", "AI间接受益/运营提效", "AI 主要用于门店运营、营销和供应链效率。"),
    IndustryRule("CHIPOTLE", "Restaurants", "AI间接受益/运营提效", "AI 主要用于门店运营、排班和供应链效率。"),
    IndustryRule("HILTON", "Travel and lodging", "AI间接受益/运营提效", "AI 主要用于定价、会员营销和客服自动化。"),
    IndustryRule("UBER", "Mobility platform", "AI终端/生态入口", "调度、定价、地图和自动驾驶生态均依赖机器学习。"),
    IndustryRule("OCCIDENTAL", "Energy", "AI基础设施配套", "能源资产可间接受益于数据中心电力需求，但业务不是 AI 原生。"),
    IndustryRule("CHEVRON", "Energy", "AI基础设施配套", "能源资产可间接受益于数据中心电力需求，也可用 AI 优化勘探和运营。"),
    IndustryRule("EQT", "Natural gas", "AI基础设施配套", "天然气供给可能受益于数据中心和电力负荷增长。"),
    IndustryRule("CHUBB", "Insurance", "AI间接受益/运营提效", "保险可用 AI 做承保、理赔和欺诈检测。"),
    IndustryRule("AON", "Insurance brokerage", "AI间接受益/运营提效", "风险模型和咨询业务可受益于 AI 分析工具。"),
    IndustryRule("DAVITA", "Healthcare services", "AI间接受益/运营提效", "医疗运营可用 AI 做排班、预测和临床辅助。"),
    IndustryRule("UNITEDHEALTH", "Managed healthcare", "AI间接受益/运营提效", "医疗支付和服务可用 AI 做运营、审核和预测。"),
    IndustryRule("VERISIGN", "Internet infrastructure", "AI基础设施配套", "域名和互联网基础设施是数字服务底层，但非 AI 核心。"),
    IndustryRule("SIRIUS XM", "Media", "AI间接受益/运营提效", "AI 主要用于内容推荐、广告和运营效率。"),
    IndustryRule("LIBERTY ENERGY", "Energy services", "AI基础设施配套", "能源服务可能间接受益于电力和数据中心建设需求。"),
    IndustryRule("LIBERTY", "Media and tracking stocks", "AI间接受益/运营提效", "媒体/跟踪股组合可能受益于广告和内容推荐 AI。"),
    IndustryRule("NEW YORK TIMES", "Media", "AI间接受益/运营提效", "媒体可用 AI 做编辑工具、推荐和广告优化。"),
    IndustryRule("CHARTER", "Telecom", "AI基础设施配套", "宽带网络承载云和 AI 应用流量。"),
    IndustryRule("NUCOR", "Materials", "AI基础设施配套", "钢材和材料可能受益于数据中心与电力基础设施建设。"),
    IndustryRule("SOLARIS ENERGY", "Power infrastructure", "AI基础设施配套", "移动发电和配电设备可缓解 AI 数据中心并网和电力瓶颈。"),
    IndustryRule("POWER SOLUTIONS", "Power infrastructure", "AI基础设施配套", "发动机和发电机组可用于数据中心备用、主用或微电网电力。"),
    IndustryRule("BABCOCK", "Power infrastructure", "AI基础设施配套", "锅炉、环保和发电设备可间接受益于电力基础设施投资。"),
    IndustryRule("LENNAR", "Homebuilding", "非AI核心暴露", "主要由地产周期驱动，与 AI 关系较弱。"),
    IndustryRule("POOL", "Consumer discretionary", "非AI核心暴露", "主要由消费和住宅周期驱动，与 AI 关系较弱。"),
    IndustryRule("ALLEGIOn", "Industrial products", "AI间接受益/运营提效", "工业产品可用 AI 优化制造和安防功能。"),
    IndustryRule("LAMAR", "Advertising", "AI间接受益/运营提效", "广告资产可用 AI 改善投放和定价。"),
    IndustryRule("BROOKFIELD", "Asset management and infrastructure", "AI基础设施配套", "基础设施和电力资产可能承接 AI 数据中心投资需求。"),
    IndustryRule("KILROY", "Real estate", "非AI核心暴露", "办公和生命科学地产主要由地产供需驱动，与 AI 关系偏间接。"),
    IndustryRule("INFOSYS", "IT services", "AI平台/应用", "IT 咨询和数字化服务可帮助企业落地生成式 AI 与自动化。"),
    IndustryRule("PROPETRO", "Energy services", "AI基础设施配套", "油服业务与 AI 关系主要来自能源供给和运营提效的间接链条。"),
)

BUSINESS_RULES = (
    BusinessRule("BLOOM ENERGY", "固体氧化物燃料电池和分布式发电系统供应商，为企业、工业和数据中心客户提供现场电力。", "AI 数据中心受制于电网接入和稳定电力，Bloom 的现场发电可作为主电源、补充电源或备用电源。"),
    BusinessRule("APPLE", "消费电子、操作系统、服务和芯片生态公司，核心产品包括 iPhone、Mac、iPad、可穿戴设备和服务。", "AI 关系主要来自端侧 AI、设备生态、应用分发和自研芯片；更像 AI 终端入口，而非算力基础设施。"),
    BusinessRule("MICROSOFT", "企业软件、Azure 云、Office、Windows、GitHub 和 AI 平台公司。", "AI 关系来自 Azure GPU 云、OpenAI 生态、Copilot、企业软件分发和开发者平台。"),
    BusinessRule("ALPHABET", "搜索、广告、YouTube、Android 和 Google Cloud 平台公司。", "AI 关系来自 Gemini 模型、TPU、Google Cloud、搜索/广告重构和 YouTube 推荐系统。"),
    BusinessRule("TESLA", "电动车、能源、自动驾驶和机器人公司。", "AI 关系来自 FSD、车端数据、训练算力、机器人和能源管理，但估值也高度受汽车周期影响。"),
    BusinessRule("OCCIDENTAL", "油气勘探生产和低碳业务公司，拥有美国及国际油气资产。", "AI 关系偏电力/能源配套：数据中心用电增长可能支撑能源需求，公司自身也可用 AI 优化勘探与运营。"),
    BusinessRule("UNITEDHEALTH", "美国管理式医疗、医保服务和医疗数据/药房福利平台公司。", "AI 关系偏运营提效：理赔审核、风控、客服、医疗数据分析和护理管理可被 AI 改善。"),
    BusinessRule("VANECK ETF TRUST", "VanEck 半导体 ETF，组合通常覆盖半导体设计、制造、设备和相关供应链公司。", "该 ETF 是半导体链条的篮子暴露；Put 头寸更可能表达对拥挤 AI 芯片交易的保护、波动或下行情景，而不是单一公司基本面判断。"),
    BusinessRule("NVIDIA", "GPU、AI 加速器、网络和数据中心计算平台公司。", "NVIDIA 是 AI 训练和推理算力的核心供应商，但 Put 头寸需要按期权策略理解，不能简单视为普通股多头。"),
    BusinessRule("ORACLE", "数据库、企业软件和云基础设施公司，正在扩张 AI 云和 GPU 算力基础设施。", "Oracle 与 AI 的关系来自 OCI 云、数据库和企业 AI 工作负载；Put 头寸可能是对 AI 云资本开支交易的保护或方向性表达。"),
    BusinessRule("BROADCOM", "半导体和基础设施软件公司，重点包括网络芯片、交换芯片、定制 ASIC 和连接方案。", "Broadcom 同时受益于 AI 定制芯片和 AI 集群网络互连，但 Put 头寸未必代表看多普通股。"),
    BusinessRule("CREDO TECHNOLOGY", "高速连接芯片和 SerDes 方案供应商，产品用于数据中心、AI 集群和网络设备互连。", "AI 集群扩大东西向流量，对低功耗高速互连芯片需求提升，Credo 属于 AI 网络基础设施配套。"),
    BusinessRule("ADVANCED MICRO", "CPU、GPU 和数据中心加速器公司，提供 EPYC CPU、Instinct GPU 等 AI 算力产品。", "AMD 是 NVIDIA 之外的重要 AI 加速器供给方，关系来自 GPU、CPU 和 AI 服务器生态。"),
    BusinessRule("MICRON", "存储芯片公司，产品包括 DRAM、NAND 和高带宽内存相关解决方案。", "AI 服务器提升 HBM、DRAM 和 SSD 需求，Micron 是 AI 内存/存储周期的重要标的。"),
    BusinessRule("TAIWAN SEMICONDUCTOR", "全球领先晶圆代工厂，制造先进制程芯片。", "AI GPU、ASIC、网络芯片和高性能计算芯片高度依赖先进代工能力。"),
    BusinessRule("ALIBABA", "中国电商、云计算、本地生活和数字媒体公司，拥有阿里云和通义大模型生态。", "AI 关系来自云计算、模型服务、电商推荐广告和企业 AI 应用，但也受中国消费和监管周期影响。"),
    BusinessRule("ASML", "先进光刻设备供应商，EUV/DUV 设备是先进制程扩产的关键瓶颈。", "AI 芯片需求推动先进制程资本开支，ASML 是半导体制造设备链条的关键环节。"),
    BusinessRule("CORNING", "玻璃、光纤、显示和材料科技公司，产品覆盖通信网络、数据中心和先进材料。", "AI 数据中心和网络带宽升级可能带动光纤、连接和材料需求，但 AI 关系偏配套。"),
    BusinessRule("COREWEAVE", "GPU 云和专用 AI 云基础设施公司，向 AI 实验室和企业出租高性能 GPU 算力。", "这是最直接的 AI 算力供给资产，收入与训练、推理和 GPU 集群利用率高度相关。"),
    BusinessRule("INTEL", "半导体公司，业务覆盖 CPU、数据中心芯片、AI 加速器、网络芯片和晶圆代工。", "AI 关系来自数据中心 CPU、AI 加速器、先进封装/代工，以及 AI 服务器中的通用计算需求。"),
    BusinessRule("LUMENTUM", "光通信和激光器件供应商，产品用于数据中心、通信网络、工业和消费电子。", "AI 集群需要高速光互连，Lumentum 受益于数据中心光模块、激光器和网络带宽升级。"),
    BusinessRule("CORE SCIENTIFIC", "数字基础设施公司，历史核心是 Bitcoin mining 和矿机托管，并拥有电力与数据中心场地。", "矿场、电力合同和机房可被改造为 HPC/AI 托管，属于 AI 算力基础设施的转型可选性。"),
    BusinessRule("IREN", "运营大型数据中心，业务包括 Bitcoin mining，并扩展到 AI cloud/HPC 服务。", "可再生能源和数据中心容量可承接 GPU 托管与 AI 云需求，是矿业资产转 AI 的典型路径。"),
    BusinessRule("APPLIED DIGITAL", "建设和运营面向高性能计算、云和 AI 的数据中心基础设施。", "直接承接 AI/HPC 数据中心需求，关键变量是机房、电力、客户合同和交付节奏。"),
    BusinessRule("SANDISK", "闪存和存储产品公司，提供 NAND、SSD 和数据存储解决方案。", "AI 训练、推理和数据管道会提升高速存储、归档和数据中心 SSD 需求。"),
    BusinessRule("CIPHER MINING", "Bitcoin mining 公司，拥有大规模电力接入和数据中心站点。", "当前核心是挖矿，但电力和场地资源具备转向 HPC/AI 托管的期权价值。"),
    BusinessRule("EQT", "美国天然气生产商，聚焦 Appalachian Basin 的天然气资产。", "AI 关系偏电力链条：数据中心负荷增长可能推升燃气发电和天然气需求。"),
    BusinessRule("COHERENT", "光子、激光、材料和网络器件供应商，服务通信、工业、电子和仪器市场。", "AI 数据中心升级高速光互连，带动光模块、激光器、收发器和相关材料需求。"),
    BusinessRule("SOLARIS ENERGY", "提供移动发电、配电和能源基础设施设备，也服务能源、工业和数据中心客户。", "AI 数据中心面临并网排队，临时/模块化发电可以帮助项目更快上线。"),
    BusinessRule("TOWER SEMICONDUCTOR", "特色晶圆代工厂，聚焦模拟、射频、电源管理、传感器和混合信号芯片。", "不是 GPU 代工，但 AI 服务器、光通信、电源管理和边缘设备需要大量模拟/混合信号芯片。"),
    BusinessRule("RIOT PLATFORMS", "Bitcoin mining 和数字基础设施公司，拥有矿场、电力和数据中心运营能力。", "与 AI 的关系主要是电力和机房可选性，部分资产可能转向 HPC/GPU 托管。"),
    BusinessRule("KILROY", "美国西海岸办公和生命科学地产 REIT。", "AI 关系较弱，主要可能来自 AI 企业租赁办公/研发空间或地产运营提效。"),
    BusinessRule("HUT 8", "Bitcoin mining、托管和数字基础设施公司，拥有数据中心和能源相关资产。", "矿业/托管基础设施可转向 AI/HPC，关注电力成本、机房改造和客户签约。"),
    BusinessRule("WHITEFIBER", "AI 基础设施公司，提供 GPU cloud、HPC 数据中心和 colocation 服务。", "直接面向生成式 AI 和高性能计算工作负载，是算力、机房和云服务的组合。"),
    BusinessRule("POWER SOLUTIONS", "设计制造发动机、动力系统和发电机组，应用于工业、车辆、能源和数据中心等场景。", "AI 数据中心需要主用、备用和微电网电力，发电机组和动力系统属于电力配套链条。"),
    BusinessRule("BITDEER", "数字资产挖矿和算力基础设施公司，提供自挖矿、云算力、矿机和数据中心服务。", "矿场和算力基础设施可延伸到 HPC/AI 托管，但当前业务仍受 Bitcoin mining 周期影响。"),
    BusinessRule("CLEANSPARK", "Bitcoin mining 公司，运营低成本电力驱动的矿场组合。", "AI 关系主要是电力和场地资产的可选性，是否转 AI 取决于改造能力和客户需求。"),
    BusinessRule("BITFARMS", "Bitcoin mining 公司，运营多地矿场和电力资产。", "AI 关系主要是矿场电力和数据中心资产可能转向 HPC/AI 托管。"),
    BusinessRule("LIBERTY ENERGY", "油田服务公司，提供压裂、完井和能源服务。", "与 AI 的关系偏间接：能源供给链可能受数据中心电力需求拉动，公司自身也可用 AI 提升作业效率。"),
    BusinessRule("INFOSYS", "印度 IT 服务和咨询公司，提供软件开发、云迁移、数据、自动化和外包服务。", "AI 关系来自企业生成式 AI、数据工程、自动化实施和咨询服务；Put 头寸表示方向性或对冲暴露。"),
    BusinessRule("SNOWFLAKE", "云数据仓库和数据平台公司，帮助企业管理、共享和分析数据。", "AI 应用需要高质量企业数据、特征工程和治理，Snowflake 属于企业 AI 数据基础设施。"),
    BusinessRule("PROPETRO", "油田服务公司，主要提供水力压裂、完井和相关油气服务。", "AI 关系偏间接，主要通过能源供给链和油服运营自动化体现。"),
    BusinessRule("BABCOCK", "能源和环保工程公司，提供锅炉、发电、热处理和环境设备/服务。", "AI 数据中心带动电力基础设施投资，公司可能间接受益于发电和电力设备需求。"),
    BusinessRule("BERKSHIRE HATHAWAY", "多元化控股公司，业务覆盖保险、铁路、能源、制造和股票投资。", "AI 关系不是核心主线，更多来自旗下运营效率提升、能源资产和持有科技股的间接暴露。"),
    BusinessRule("PDD", "跨境和国内电商平台公司，核心包括 Temu、拼多多和商家服务。", "AI 主要用于推荐、广告投放、商家工具、搜索和供应链效率，属于运营提效型暴露。"),
    BusinessRule("TEMPUS AI", "医疗 AI 和数据平台公司，整合临床、分子和影像数据，为精准医疗提供分析工具。", "AI 是其业务核心，用于诊疗辅助、药物研发数据分析和临床决策支持。"),
    BusinessRule("DISNEY", "全球媒体、影视、主题公园和流媒体公司。", "AI 关系偏间接，主要体现在内容生产工具、推荐系统、广告投放和运营效率。"),
)

TICKER_RULES = (
    ("VANECK ETF TRUST", "SMH"),
    ("NVIDIA", "NVDA"),
    ("ORACLE", "ORCL"),
    ("BROADCOM", "AVGO"),
    ("ADVANCED MICRO", "AMD"),
    ("BLOOM ENERGY", "BE"),
    ("SANDISK", "SNDK"),
    ("MICRON", "MU"),
    ("COREWEAVE", "CRWV"),
    ("TAIWAN SEMICONDUCTOR", "TSM"),
    ("ASML", "ASML"),
    ("IREN", "IREN"),
    ("CORE SCIENTIFIC", "CORZ"),
    ("APPLIED DIGITAL", "APLD"),
    ("INTEL", "INTC"),
    ("RIOT PLATFORMS", "RIOT"),
    ("CLEANSPARK", "CLSK"),
    ("SOLARIS ENERGY", "SEI"),
    ("T1 ENERGY", "TE"),
    ("BITFARMS", "BITF"),
    ("BITDEER", "BTDR"),
    ("POWER SOLUTIONS", "PSIX"),
    ("CORNING", "GLW"),
    ("WHITEFIBER", "WYFI"),
    ("BABCOCK", "BW"),
    ("SHARONAI", "SHAR"),
    ("PROPETRO", "PUMP"),
    ("INFOSYS", "INFY"),
    ("HIVE DIGITAL", "HIVE"),
    ("LUMENTUM", "LITE"),
    ("CIPHER MINING", "CIFR"),
    ("EQT", "EQT"),
    ("COHERENT", "COHR"),
    ("TOWER SEMICONDUCTOR", "TSEM"),
    ("KILROY", "KRC"),
    ("HUT 8", "HUT"),
    ("LIBERTY ENERGY", "LBRT"),
    ("ALPHABET", "GOOGL"),
    ("AMAZON", "AMZN"),
    ("MICROSOFT", "MSFT"),
    ("META PLATFORMS", "META"),
    ("APPLE", "AAPL"),
    ("ELI LILLY", "LLY"),
    ("EXXON MOBIL", "XOM"),
    ("JOHNSON & JOHNSON", "JNJ"),
    ("JPMORGAN CHASE", "JPM"),
    ("MASTERCARD", "MA"),
    ("NETFLIX", "NFLX"),
    ("VISA", "V"),
    ("ASTRAZENECA", "AZN"),
    ("SHOPIFY", "SHOP"),
    ("UNILEVER", "UL"),
    ("ABBVIE", "ABBV"),
    ("AMCOR", "AMCR"),
    ("APPLOVIN", "APP"),
    ("BARRICK", "GOLD"),
    ("CAPITAL ONE", "COF"),
    ("CARNIVAL", "CCL"),
    ("CATERPILLAR", "CAT"),
    ("CHEVRON", "CVX"),
    ("CORE S&P500 ETF", "IVV"),
    ("FIDELITY NATIONAL FINANCIAL", "FNF"),
    ("GE VERNOVA", "GEV"),
    ("PINNACLE FINL PARTNERS", "PNFP"),
    ("PHYSICAL GOLD TR", "PHYS"),
    ("PHYSICAL SILVER", "PSLV"),
    ("ROCKET LAB", "RKLB"),
    ("SOUTHSTATE", "SSB"),
    ("STATE STREET ENE", "XLE"),
    ("STATE STREET FIN", "XLF"),
    ("STATE STREET HEA", "XLV"),
    ("STATE STREET TEC", "XLK"),
    ("SPDR S&P 500 ETF TR", "SPY"),
    ("STATE STR SPDR S&P 500 ETF T", "SPY"),
    ("BOEING", "BA"),
    ("COSTCO", "COST"),
    ("UBER TECHNOLOGIES", "UBER"),
    ("BERKSHIRE HATHAWAY", "BRK.B"),
    ("PDD", "PDD"),
    ("OCCIDENTAL", "OXY"),
    ("ALIBABA", "BABA"),
    ("DISNEY", "DIS"),
    ("UNITEDHEALTH", "UNH"),
    ("CREDO TECHNOLOGY", "CRDO"),
    ("TEMPUS AI", "TEM"),
    ("TESLA", "TSLA"),
    ("PALANTIR", "PLTR"),
    ("SNOWFLAKE", "SNOW"),
    ("MARVELL", "MRVL"),
    ("LAM RESEARCH", "LRCX"),
    ("APPLIED MATLS", "AMAT"),
    ("EQUINIX", "EQIX"),
    ("VERTIV", "VRT"),
    ("SYNOPSYS", "SNPS"),
    ("SALESFORCE", "CRM"),
    ("SERVICENOW", "NOW"),
    ("CLOUDFLARE", "NET"),
    ("DATADOG", "DDOG"),
    ("CROWDSTRIKE", "CRWD"),
)

AI_INFRA_FLOW_BUCKETS = (
    InfraFlowBucket(
        "AI芯片",
        ("NVIDIA", "ADVANCED MICRO", "BROADCOM", "TAIWAN SEMICONDUCTOR", "ARM"),
        "GPU、AI 加速器、定制芯片、先进代工和处理器 IP。",
    ),
    InfraFlowBucket(
        "设备/制造",
        ("ASML", "APPLIED MATLS", "LAM RESEARCH", "KLA"),
        "先进制程、晶圆设备和半导体制造资本开支。",
    ),
    InfraFlowBucket(
        "AI云/算力",
        ("COREWEAVE", "ORACLE", "MICROSOFT", "AMAZON"),
        "GPU 云、超大规模云平台和模型训练/推理算力。",
    ),
    InfraFlowBucket(
        "数据中心/电力",
        ("BLOOM ENERGY", "VISTRA", "CONSTELLATION ENERGY", "APPLIED DIGITAL", "CORE SCIENTIFIC", "IREN", "CIPHER MINING"),
        "AI 数据中心、矿场转 HPC、并网、电力、燃气和现场发电。",
    ),
    InfraFlowBucket(
        "光通信/网络",
        ("LUMENTUM", "COHERENT", "MARVELL", "ARISTA", "BROADCOM", "CREDO TECHNOLOGY"),
        "AI 集群互连、光模块、网络芯片和高速交换网络；AVGO 同时计入该链条。",
    ),
)


def slugify(value: str) -> str:
    lowered = value.lower()
    return re.sub(r"[^a-z0-9]+", "-", lowered).strip("-")


def parse_int(value: str | None) -> int:
    if not value:
        return 0
    cleaned = value.replace(",", "").strip()
    if not cleaned:
        return 0
    return int(float(cleaned))


def parse_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def normalize_value(raw_value: int, report_date: str) -> int:
    if parse_date(report_date) < VALUE_DOLLAR_START:
        return raw_value * 1000
    return raw_value


def child_text(element: ET.Element, child_name: str) -> str:
    for child in list(element):
        if child.tag.split("}")[-1] == child_name:
            return (child.text or "").strip()
    return ""


def nested_text(element: ET.Element, parent_name: str, child_name: str) -> str:
    for child in list(element):
        if child.tag.split("}")[-1] == parent_name:
            return child_text(child, child_name)
    return ""


def classify_ai_holding(name_of_issuer: str) -> tuple[str, str]:
    upper_name = name_of_issuer.upper()
    for rule in AI_RULES:
        if matches_fragment(upper_name, rule.fragment):
            return rule.theme, rule.reason
    return "", ""


def classify_holding_context(name_of_issuer: str) -> tuple[str, str, str]:
    upper_name = name_of_issuer.upper()
    for rule in INDUSTRY_RULES:
        if matches_fragment(upper_name, rule.fragment):
            return rule.industry, rule.ai_relationship, rule.ai_connection
    return "Unclassified", "未识别直接AI关系", "未根据名称规则识别出明确行业或直接 AI 关系。"


def business_profile(name_of_issuer: str) -> tuple[str, str]:
    upper_name = name_of_issuer.upper()
    for rule in BUSINESS_RULES:
        if matches_fragment(upper_name, rule.fragment):
            return rule.business, rule.ai_detail
    return "暂未在内置规则中识别出详细业务描述。", "暂未识别出明确 AI 关系，需结合公司最新披露进一步核实。"


@lru_cache(maxsize=32768)
def ticker_for_issuer(name_of_issuer: str) -> str:
    upper_name = name_of_issuer.upper()
    for fragment, ticker in TICKER_RULES:
        if matches_fragment(upper_name, fragment):
            return ticker
    return ""


def display_issuer(name_of_issuer: str) -> str:
    ticker = ticker_for_issuer(name_of_issuer)
    if not ticker:
        return name_of_issuer
    return f"{name_of_issuer} ({ticker})"


@lru_cache(maxsize=4096)
def _compiled_fragment_pattern(fragment: str) -> re.Pattern[str]:
    escaped = re.escape(fragment.upper()).replace(r"\ ", r"\s+")
    return re.compile(rf"(?<![A-Z0-9]){escaped}(?![A-Z0-9])")


def matches_fragment(upper_name: str, fragment: str) -> bool:
    return _compiled_fragment_pattern(fragment).search(upper_name) is not None


def holding_key(holding: Holding) -> str:
    put_call = holding.put_call or "COMMON"
    return f"{holding.cusip}|{put_call}|{holding.title_of_class}".upper()


def snapshot_path(data_dir: Path, manager_name: str, report_date: str, accession: str) -> Path:
    manager_dir = data_dir / "history" / slugify(manager_name)
    return manager_dir / f"{report_date}_{accession}.json"


def http_get_bytes(url: str, user_agent: str, attempts: int = 3) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": user_agent})
    for attempt in range(1, attempts + 1):
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return response.read()
        except urllib.error.HTTPError as error:
            should_retry = error.code == 429 or error.code >= 500
            if not should_retry or attempt == attempts:
                raise MonitorError(f"SEC request failed: {url} HTTP {error.code}") from error
        except urllib.error.URLError as error:
            if attempt == attempts:
                raise MonitorError(f"SEC request failed: {url} {error.reason}") from error
        except TimeoutError as error:
            if attempt == attempts:
                raise MonitorError(f"SEC request timed out: {url}") from error
        time.sleep(0.75 * attempt)
    raise MonitorError(f"SEC request failed after {attempts} attempts: {url}")


async def fetch_json(url: str, user_agent: str) -> dict[str, Any]:
    payload = await asyncio.to_thread(http_get_bytes, url, user_agent)
    return json.loads(payload.decode("utf-8"))


async def fetch_text(url: str, user_agent: str) -> str:
    payload = await asyncio.to_thread(http_get_bytes, url, user_agent)
    return payload.decode("utf-8", errors="replace")


async def recent_13f_filings(
    manager: ManagerConfig,
    user_agent: str,
    limit: int = 2,
) -> list[FilingMeta]:
    submissions_url = f"https://data.sec.gov/submissions/CIK{manager.cik:010d}.json"
    data = await fetch_json(submissions_url, user_agent)
    recent = data["filings"]["recent"]
    metas: list[FilingMeta] = []
    seen_report_dates: set[str] = set()

    for index, form in enumerate(recent["form"]):
        if form not in FORM_TYPES:
            continue
        report_date = recent["reportDate"][index]
        if report_date in seen_report_dates:
            continue
        seen_report_dates.add(report_date)
        accession = recent["accessionNumber"][index]
        base_url = filing_base_url(manager.cik, accession)
        info_document = await find_info_table_document(base_url, user_agent)
        metas.append(
            FilingMeta(
                manager_name=manager.name,
                cik=manager.cik,
                form=form,
                accession=accession,
                filing_date=recent["filingDate"][index],
                report_date=report_date,
                primary_document=recent["primaryDocument"][index],
                info_table_document=info_document,
                filing_url=f"{base_url}/{accession}-index.html",
                info_table_url=f"{base_url}/{urllib.parse.quote(info_document)}",
            )
        )
        if len(metas) >= limit:
            break
    return metas


async def find_info_table_document(base_url: str, user_agent: str) -> str:
    index_url = f"{base_url}/index.json"
    index_data = await fetch_json(index_url, user_agent)
    items = index_data["directory"]["item"]
    xml_names = [
        item["name"]
        for item in items
        if item.get("name", "").lower().endswith(".xml")
        and item.get("name", "").lower() != "primary_doc.xml"
    ]
    if not xml_names:
        raise MonitorError(f"No 13F information table XML found in {index_url}")
    preferred = [
        name
        for name in xml_names
        if "info" in name.lower() or "13f" in name.lower() or "table" in name.lower()
    ]
    return (preferred or xml_names)[0]


def filing_base_url(cik: int, accession: str) -> str:
    accession_dir = accession.replace("-", "")
    return f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession_dir}"


def parse_info_table(xml_text: str, report_date: str) -> list[Holding]:
    root = ET.fromstring(xml_text)
    holdings: list[Holding] = []
    for info_table in root.findall(".//{*}infoTable"):
        name = child_text(info_table, "nameOfIssuer")
        raw_value = parse_int(child_text(info_table, "value"))
        ai_theme, ai_reason = classify_ai_holding(name)
        industry, ai_relationship, ai_connection = classify_holding_context(name)
        holdings.append(
            Holding(
                name_of_issuer=name,
                title_of_class=child_text(info_table, "titleOfClass"),
                cusip=child_text(info_table, "cusip"),
                value_usd=normalize_value(raw_value, report_date),
                shares_or_principal=parse_int(nested_text(info_table, "shrsOrPrnAmt", "sshPrnamt")),
                amount_type=nested_text(info_table, "shrsOrPrnAmt", "sshPrnamtType"),
                put_call=child_text(info_table, "putCall"),
                investment_discretion=child_text(info_table, "investmentDiscretion"),
                voting_sole=parse_int(nested_text(info_table, "votingAuthority", "Sole")),
                voting_shared=parse_int(nested_text(info_table, "votingAuthority", "Shared")),
                voting_none=parse_int(nested_text(info_table, "votingAuthority", "None")),
                industry=industry,
                ai_relationship=ai_relationship,
                ai_connection=ai_connection,
                ai_theme=ai_theme,
                ai_reason=ai_reason,
            )
        )
    return aggregate_holdings(holdings)


def aggregate_holdings(holdings: list[Holding]) -> list[Holding]:
    aggregated: dict[str, Holding] = {}
    for holding in holdings:
        key = holding_key(holding)
        existing = aggregated.get(key)
        if existing is None:
            aggregated[key] = holding
            continue
        aggregated[key] = Holding(
            name_of_issuer=existing.name_of_issuer,
            title_of_class=existing.title_of_class,
            cusip=existing.cusip,
            value_usd=existing.value_usd + holding.value_usd,
            shares_or_principal=existing.shares_or_principal + holding.shares_or_principal,
            amount_type=existing.amount_type or holding.amount_type,
            put_call=existing.put_call or holding.put_call,
            investment_discretion="MIXED"
            if existing.investment_discretion != holding.investment_discretion
            else existing.investment_discretion,
            voting_sole=existing.voting_sole + holding.voting_sole,
            voting_shared=existing.voting_shared + holding.voting_shared,
            voting_none=existing.voting_none + holding.voting_none,
            industry=existing.industry or holding.industry,
            ai_relationship=existing.ai_relationship or holding.ai_relationship,
            ai_connection=existing.ai_connection or holding.ai_connection,
            ai_theme=existing.ai_theme or holding.ai_theme,
            ai_reason=existing.ai_reason or holding.ai_reason,
        )
    return list(aggregated.values())


async def download_snapshot(meta: FilingMeta, data_dir: Path, user_agent: str) -> FilingSnapshot:
    raw_dir = data_dir / "raw" / str(meta.cik) / meta.accession.replace("-", "")
    raw_dir.mkdir(parents=True, exist_ok=True)
    xml_text = await fetch_text(meta.info_table_url, user_agent)
    (raw_dir / meta.info_table_document).write_text(xml_text, encoding="utf-8")

    snapshot = FilingSnapshot(
        manager_name=meta.manager_name,
        cik=meta.cik,
        form=meta.form,
        accession=meta.accession,
        filing_date=meta.filing_date,
        report_date=meta.report_date,
        info_table_url=meta.info_table_url,
        downloaded_at=datetime.now(timezone.utc).isoformat(),
        holdings=parse_info_table(xml_text, meta.report_date),
    )
    save_snapshot(snapshot, data_dir)
    return snapshot


def save_snapshot(snapshot: FilingSnapshot, data_dir: Path) -> None:
    path = snapshot_path(data_dir, snapshot.manager_name, snapshot.report_date, snapshot.accession)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = asdict(snapshot)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def load_snapshot(path: Path) -> FilingSnapshot:
    payload = json.loads(path.read_text(encoding="utf-8"))
    holdings = [holding_from_payload(item) for item in payload["holdings"]]
    payload["holdings"] = holdings
    return FilingSnapshot(**payload)


def holding_from_payload(payload: dict[str, Any]) -> Holding:
    data = dict(payload)
    industry, ai_relationship, ai_connection = classify_holding_context(str(data.get("name_of_issuer", "")))
    ai_theme, ai_reason = classify_ai_holding(str(data.get("name_of_issuer", "")))
    if not data.get("industry") or data.get("industry") == "Unclassified":
        data["industry"] = industry
    if not data.get("ai_relationship") or data.get("ai_relationship") == "未识别直接AI关系":
        data["ai_relationship"] = ai_relationship
    if not data.get("ai_connection") or data.get("ai_connection") == "未根据名称规则识别出明确行业或直接 AI 关系。":
        data["ai_connection"] = ai_connection
    if not data.get("ai_theme"):
        data["ai_theme"] = ai_theme
    if not data.get("ai_reason"):
        data["ai_reason"] = ai_reason
    return Holding(**data)


def existing_snapshot(data_dir: Path, meta: FilingMeta) -> FilingSnapshot | None:
    path = snapshot_path(data_dir, meta.manager_name, meta.report_date, meta.accession)
    if not path.exists():
        return None
    return load_snapshot(path)


def latest_previous_snapshot(data_dir: Path, current: FilingSnapshot) -> FilingSnapshot | None:
    manager_dir = data_dir / "history" / slugify(current.manager_name)
    if not manager_dir.exists():
        return None
    snapshots = [
        load_snapshot(path)
        for path in manager_dir.glob("*.json")
        if current.accession not in path.name
    ]
    snapshots.sort(key=lambda item: (item.report_date, item.filing_date, item.accession), reverse=True)
    return snapshots[0] if snapshots else None


def compare_holdings(current: FilingSnapshot, previous: FilingSnapshot | None) -> list[HoldingChange]:
    if previous is None:
        return []

    current_map = {holding_key(holding): holding for holding in current.holdings}
    previous_map = {holding_key(holding): holding for holding in previous.holdings} if previous else {}
    changes: list[HoldingChange] = []

    for key in sorted(current_map.keys() | previous_map.keys()):
        current_holding = current_map.get(key)
        previous_holding = previous_map.get(key)
        reference = current_holding or previous_holding
        if reference is None:
            continue
        previous_shares = previous_holding.shares_or_principal if previous_holding else 0
        current_shares = current_holding.shares_or_principal if current_holding else 0
        previous_value = previous_holding.value_usd if previous_holding else 0
        current_value = current_holding.value_usd if current_holding else 0
        status = classify_change_status(previous_shares, current_shares, previous_holding, current_holding)
        ai_theme = (current_holding.ai_theme if current_holding else "") or reference.ai_theme
        ai_reason = (current_holding.ai_reason if current_holding else "") or reference.ai_reason
        changes.append(
            HoldingChange(
                key=key,
                name_of_issuer=reference.name_of_issuer,
                title_of_class=reference.title_of_class,
                cusip=reference.cusip,
                put_call=reference.put_call,
                industry=reference.industry,
                ai_relationship=reference.ai_relationship,
                status=status,
                previous_shares_or_principal=previous_shares,
                current_shares_or_principal=current_shares,
                share_change=current_shares - previous_shares,
                previous_value_usd=previous_value,
                current_value_usd=current_value,
                value_change_usd=current_value - previous_value,
                ai_theme=ai_theme,
                ai_reason=ai_reason,
            )
        )
    return changes


def classify_change_status(
    previous_shares: int,
    current_shares: int,
    previous_holding: Holding | None,
    current_holding: Holding | None,
) -> str:
    if previous_holding is None and current_holding is not None:
        return "new"
    if previous_holding is not None and current_holding is None:
        return "exited"
    if current_shares > previous_shares:
        return "increased"
    if current_shares < previous_shares:
        return "decreased"
    return "unchanged"


def money(value: int) -> str:
    sign = "-" if value < 0 else ""
    absolute = abs(value)
    if absolute >= 1_000_000_000:
        return f"{sign}${absolute / 1_000_000_000:.2f}B"
    if absolute >= 1_000_000:
        return f"{sign}${absolute / 1_000_000:.2f}M"
    if absolute >= 1_000:
        return f"{sign}${absolute / 1_000:.2f}K"
    return f"{sign}${absolute}"


def number(value: int) -> str:
    return f"{value:,}"


def percent(numerator: int, denominator: int) -> str:
    if denominator == 0:
        return "0.0%"
    return f"{numerator / denominator * 100:.1f}%"


def table_row(values: list[str]) -> str:
    return "| " + " | ".join(value.replace("\n", " ") for value in values) + " |"


def bucket_totals(holdings: list[Holding], attribute: str) -> dict[str, int]:
    totals: dict[str, int] = {}
    for holding in holdings:
        key = str(getattr(holding, attribute)) or "Unclassified"
        totals[key] = totals.get(key, 0) + holding.value_usd
    return totals


def top_bucket_text(totals: dict[str, int], portfolio_value: int, limit: int) -> str:
    ranked = sorted(totals.items(), key=lambda item: item[1], reverse=True)
    return "；".join(f"{name} {percent(value, portfolio_value)}" for name, value in ranked[:limit])


def relationship_bucket(value: str) -> str:
    if value in {"核心AI基础设施", "AI平台/应用", "AI终端/生态入口"}:
        return "AI直接暴露"
    if value in {"AI基础设施配套", "AI间接受益/运营提效"}:
        return "AI配套/间接受益"
    return "非AI或未识别"


def relationship_group_totals(holdings: list[Holding]) -> dict[str, int]:
    totals: dict[str, int] = {}
    for holding in holdings:
        key = relationship_bucket(holding.ai_relationship)
        totals[key] = totals.get(key, 0) + holding.value_usd
    return totals


def industry_analysis_section(snapshots: list[FilingSnapshot]) -> list[str]:
    lines = [
        "## 行业与AI关系总览",
        "",
        table_row(["管理人", "行业Top3", "AI直接暴露", "AI配套/间接受益", "主要判断"]),
        table_row(["---", "---", "---:", "---:", "---"]),
    ]
    for snapshot in snapshots:
        total_value = sum(holding.value_usd for holding in snapshot.holdings)
        industry_text = top_bucket_text(bucket_totals(snapshot.holdings, "industry"), total_value, 3)
        relationship_totals = relationship_group_totals(snapshot.holdings)
        direct_value = relationship_totals.get("AI直接暴露", 0)
        adjacent_value = relationship_totals.get("AI配套/间接受益", 0)
        lines.append(
            table_row(
                [
                    snapshot.manager_name,
                    industry_text,
                    f"{money(direct_value)} / {percent(direct_value, total_value)}",
                    f"{money(adjacent_value)} / {percent(adjacent_value, total_value)}",
                    manager_ai_judgement(snapshot),
                ]
            )
        )

    lines.append("")
    for snapshot in snapshots:
        lines.extend(industry_detail_section(snapshot))
    return lines


def manager_ai_judgement(snapshot: FilingSnapshot) -> str:
    holdings = sorted(snapshot.holdings, key=lambda item: item.value_usd, reverse=True)
    direct = [holding for holding in holdings if relationship_bucket(holding.ai_relationship) == "AI直接暴露"]
    adjacent = [holding for holding in holdings if relationship_bucket(holding.ai_relationship) == "AI配套/间接受益"]
    if direct:
        names = "、".join(unique_holding_names(direct, 3))
        return f"AI 暴露主要来自 {names}，属于{direct[0].ai_relationship}。"
    if adjacent:
        names = "、".join(unique_holding_names(adjacent, 3))
        return f"未见明显核心 AI 标的，更多是 {names} 等行业的运营提效或基础设施配套关系。"
    return "组合主要由传统行业驱动，暂未按内置规则识别出明确 AI 关系。"


def unique_holding_names(holdings: list[Holding], limit: int) -> list[str]:
    names: list[str] = []
    seen: set[str] = set()
    for holding in holdings:
        normalized = holding.name_of_issuer.upper()
        if normalized in seen:
            continue
        seen.add(normalized)
        names.append(display_issuer(holding.name_of_issuer))
        if len(names) >= limit:
            break
    return names


def industry_detail_section(snapshot: FilingSnapshot) -> list[str]:
    total_value = sum(holding.value_usd for holding in snapshot.holdings)
    industry_totals = bucket_totals(snapshot.holdings, "industry")
    lines = [
        f"### {snapshot.manager_name}",
        "",
        manager_ai_judgement(snapshot),
        "",
        table_row(["行业", "市值", "组合占比", "AI关系Top", "代表持仓", "与AI的关系"]),
        table_row(["---", "---:", "---:", "---", "---", "---"]),
    ]
    for industry, value in sorted(industry_totals.items(), key=lambda item: item[1], reverse=True):
        industry_holdings = [holding for holding in snapshot.holdings if holding.industry == industry]
        relationship_text = top_bucket_text(bucket_totals(industry_holdings, "ai_relationship"), value, 2)
        representatives = "、".join(
            unique_holding_names(sorted(industry_holdings, key=lambda item: item.value_usd, reverse=True), 3)
        )
        relation_note = representative_connection(industry_holdings)
        lines.append(
            table_row(
                [
                    industry,
                    money(value),
                    percent(value, total_value),
                    relationship_text,
                    representatives,
                    relation_note,
                ]
            )
        )
    lines.append("")
    return lines


def representative_connection(holdings: list[Holding]) -> str:
    direct = [holding for holding in holdings if holding.ai_theme]
    if direct:
        return direct[0].ai_reason or direct[0].ai_connection
    ranked = sorted(holdings, key=lambda item: item.value_usd, reverse=True)
    return ranked[0].ai_connection if ranked else ""


def situational_awareness_detail_section(
    snapshots: list[FilingSnapshot],
    changes_by_manager: dict[str, list[HoldingChange]],
) -> list[str]:
    snapshot = next((item for item in snapshots if item.manager_name == "Situational Awareness LP"), None)
    if snapshot is None:
        return []

    total_value = sum(holding.value_usd for holding in snapshot.holdings)
    changes = {change.key: change for change in changes_by_manager.get(snapshot.manager_name, [])}
    lines = [
        "## Situational Awareness LP 逐股业务与AI关系详解",
        "",
        f"报告期：{snapshot.report_date}；13F accession：{snapshot.accession}。"
        "下表按最新披露市值排序，逐行列出股票/期权工具的业务、AI 关系和上一期变化。",
        "",
        table_row(["标的", "工具", "业务", "AI关系", "和AI的关系", "市值", "组合占比", "较上期"]),
        table_row(["---", "---", "---", "---", "---", "---:", "---:", "---:"]),
    ]

    for holding in sorted(snapshot.holdings, key=lambda item: item.value_usd, reverse=True):
        business, ai_detail = business_profile(holding.name_of_issuer)
        change = changes.get(holding_key(holding))
        change_value = money(change.value_change_usd) if change else "n/a"
        lines.append(
            table_row(
                [
                    display_issuer(holding.name_of_issuer),
                    instrument_label(holding),
                    business,
                    f"{holding.industry}；{holding.ai_relationship}",
                    ai_detail,
                    money(holding.value_usd),
                    percent(holding.value_usd, total_value),
                    change_value,
                ]
            )
        )

    lines.extend(
        [
            "",
            "解读：该组合的 AI 暴露集中在三条链：GPU 云和数据中心算力、数据中心电力/储能/燃气配套、以及光互连/半导体/存储。"
            "其中 CoreWeave、Applied Digital、WhiteFiber 更接近直接算力基础设施；Bloom Energy、Solaris Energy、Power Solutions、EQT 等更偏电力瓶颈配套；"
            "Bitcoin mining 公司如 Core Scientific、IREN、Cipher、Riot、Hut 8、Bitdeer、CleanSpark、Bitfarms 的 AI 关系主要来自电力和机房资产转向 HPC/GPU 托管的可选性。",
            "",
        ]
    )
    return lines


def situational_awareness_investment_analysis_section(
    snapshots: list[FilingSnapshot],
    changes_by_manager: dict[str, list[HoldingChange]],
    previous_snapshot: FilingSnapshot | None,
) -> list[str]:
    snapshot = next((item for item in snapshots if item.manager_name == "Situational Awareness LP"), None)
    if snapshot is None:
        return []

    changes = changes_by_manager.get(snapshot.manager_name, [])
    if not changes:
        return []

    previous_value = sum(change.previous_value_usd for change in changes)
    current_value = sum(change.current_value_usd for change in changes)
    previous_ai_value = sum(change.previous_value_usd for change in changes if change.ai_theme)
    current_ai_value = sum(change.current_value_usd for change in changes if change.ai_theme)
    previous_report = previous_snapshot.report_date if previous_snapshot else "上一期 13F"
    previous_accession = previous_snapshot.accession if previous_snapshot else "n/a"
    previous_holding_count = len(previous_snapshot.holdings) if previous_snapshot else len([change for change in changes if change.previous_value_usd > 0])
    changed = [change for change in changes if change.status != "unchanged"]
    status_counts = {
        status: sum(1 for change in changes if change.status == status)
        for status in ["new", "exited", "increased", "decreased"]
    }

    lines = [
        "## 调仓总览与投资思路",
        "",
        table_row(["指标", "上一期", "最新一期", "变化"]),
        table_row(["---", "---:", "---:", "---:"]),
        table_row(["报告期", previous_report, snapshot.report_date, f"{previous_accession} -> {snapshot.accession}"]),
        table_row(["持仓数", number(previous_holding_count), number(len(snapshot.holdings)), number(len(snapshot.holdings) - previous_holding_count)]),
        table_row(["组合市值", money(previous_value), money(current_value), money(current_value - previous_value)]),
        table_row(["AI识别市值", money(previous_ai_value), money(current_ai_value), money(current_ai_value - previous_ai_value)]),
        "",
        f"- 调仓结构：新增 {status_counts['new']} 个，清仓 {status_counts['exited']} 个，增持 {status_counts['increased']} 个，减持 {status_counts['decreased']} 个。",
        "- 核心判断：组合从 2025Q4 的 AI 电力/数据中心/光通信主题，扩展为 2026Q1 的半导体期权 + 数据中心硬资产双主线。",
        "- 期权提示：本期大额新增包含多只 Put，13F 只能说明基金持有相关期权，不能直接等同于看多普通股；更合理的理解是对 AI 芯片拥挤交易做保护、波动或相对价值表达。",
        "",
    ]

    lines.extend(situational_awareness_current_structure(snapshot))
    lines.extend(situational_awareness_change_tables(changed))
    lines.extend(situational_awareness_increased_business_logic_lines())
    lines.extend(situational_awareness_thesis_lines())
    return lines


def situational_awareness_current_structure(snapshot: FilingSnapshot) -> list[str]:
    total_value = sum(holding.value_usd for holding in snapshot.holdings)
    lines = [
        "### 当前组合结构",
        "",
        table_row(["维度", "市值", "组合占比", "代表方向"]),
        table_row(["---", "---:", "---:", "---"]),
    ]
    industry_totals = bucket_totals(snapshot.holdings, "industry")
    for industry, value in sorted(industry_totals.items(), key=lambda item: item[1], reverse=True)[:8]:
        holdings = [holding for holding in snapshot.holdings if holding.industry == industry]
        representatives = "、".join(unique_holding_names(sorted(holdings, key=lambda item: item.value_usd, reverse=True), 3))
        lines.append(table_row([industry, money(value), percent(value, total_value), representatives]))

    lines.extend(
        [
            "",
            "### 期权与现股结构",
            "",
            table_row(["工具", "市值", "组合占比", "解读"]),
            table_row(["---", "---:", "---:", "---"]),
        ]
    )
    option_totals = option_value_totals(snapshot.holdings)
    descriptions = {
        "Put": "主要用于保护、看跌或相对价值交易，不能按普通股多头解读。",
        "Call": "上行期权暴露，通常体现对标的弹性或事件驱动的押注。",
        "Stock/ETF": "普通股或 ETF 持仓，更接近方向性资产配置。",
    }
    for instrument, value in sorted(option_totals.items(), key=lambda item: item[1], reverse=True):
        lines.append(table_row([instrument, money(value), percent(value, total_value), descriptions[instrument]]))
    lines.append("")
    return lines


def option_value_totals(holdings: list[Holding]) -> dict[str, int]:
    totals = {"Put": 0, "Call": 0, "Stock/ETF": 0}
    for holding in holdings:
        if holding.put_call == "Put":
            totals["Put"] += holding.value_usd
        elif holding.put_call == "Call":
            totals["Call"] += holding.value_usd
        else:
            totals["Stock/ETF"] += holding.value_usd
    return totals


def situational_awareness_change_tables(changes: list[HoldingChange]) -> list[str]:
    sections = [
        ("主要新进", {"new"}),
        ("主要增持", {"increased"}),
        ("主要减持", {"decreased"}),
        ("主要清仓", {"exited"}),
    ]
    lines: list[str] = []
    for title, statuses in sections:
        ranked = [change for change in changes if change.status in statuses]
        ranked.sort(key=lambda item: abs(item.value_change_usd), reverse=True)
        if not ranked:
            continue
        lines.extend(
            [
                f"### {title}",
                "",
                table_row(["标的", "工具", "行业", "AI关系", "上一期市值", "最新市值", "变化", "数量变化"]),
                table_row(["---", "---", "---", "---", "---:", "---:", "---:", "---:"]),
            ]
        )
        for change in ranked[:10]:
            lines.append(
                table_row(
                    [
                        display_issuer(change.name_of_issuer),
                        change.put_call or change.title_of_class,
                        change.industry,
                        change.ai_relationship,
                        money(change.previous_value_usd),
                        money(change.current_value_usd),
                        money(change.value_change_usd),
                        number(change.share_change),
                    ]
                )
            )
        lines.append("")
    return lines


def situational_awareness_increased_business_logic_lines() -> list[str]:
    return [
        "### 主要增持公司业务逻辑与AI相关性",
        "",
        table_row(["公司", "增持逻辑", "AI相关性", "关键观察点"]),
        table_row(["---", "---", "---", "---"]),
        table_row(
            [
                "SANDISK CORP (SNDK)",
                "闪存、NAND、SSD 和数据存储需求受 AI 数据管道扩张拉动；本期普通股明显增持，同时新进 Call。",
                "AI 训练、推理、向量数据库、日志和多模态数据会放大高速存储与归档需求，属于 AI 基础设施配套。",
                "重点看企业级 SSD、NAND 周期、AI 数据中心存储采购和价格周期。",
            ]
        ),
        table_row(
            [
                "COREWEAVE INC (CRWV)",
                "增持普通股，但大幅减持 Call，说明仍保留核心 GPU 云敞口，同时降低期权杠杆。",
                "直接出租 GPU 算力，是 AI 训练和推理需求最直接的承接资产之一，属于核心 AI 基础设施。",
                "重点看 GPU 供给、客户集中度、合同期限、融资成本和数据中心交付节奏。",
            ]
        ),
        table_row(
            [
                "CLEANSPARK INC (CLSK)",
                "从小仓位提升为更有意义的矿场/电力可选性仓位。",
                "当前核心仍是 Bitcoin mining，但低成本电力、矿场和并网资源可能转向 AI/HPC 托管。",
                "重点看是否签 AI/HPC 客户、机房改造能力、电力成本和 BTC 周期暴露。",
            ]
        ),
        table_row(
            [
                "IREN LIMITED (IREN)",
                "继续增持电力和数据中心容量资产，强化矿场转 AI cloud/HPC 主线。",
                "可再生能源和数据中心容量可承接 GPU 托管和 AI 云需求，是矿业资产转 AI 的典型路径。",
                "重点看 AI cloud/HPC 收入占比、GPU 部署、客户签约和电力资源质量。",
            ]
        ),
        table_row(
            [
                "RIOT PLATFORMS INC (RIOT)",
                "增持代表继续押注已有电力接入和矿场资产的重估。",
                "AI 数据中心缺电和并网排队时，矿场电力与机房资产具备转 AI/HPC 托管的期权价值。",
                "重点看电力协议、矿场位置、资本开支和能否从挖矿切换到 HPC 客户。",
            ]
        ),
        table_row(
            [
                "APPLIED DIGITAL CORP (APLD)",
                "继续加仓直接面向 AI/HPC 的数据中心基础设施。",
                "公司建设和运营 AI/HPC 数据中心，关系比矿企更直接，属于核心 AI 数据中心资产。",
                "重点看数据中心交付、客户合同、融资压力、电力接入和项目执行。",
            ]
        ),
        table_row(
            [
                "BITFARMS LTD (BITF)",
                "增持矿场和电力资产的 AI/HPC 转型可选性。",
                "与 AI 的关系来自矿场、电力和数据中心资产可能承接 GPU/HPC 托管。",
                "重点看转型公告、客户签约、资本开支与 BTC mining 周期风险。",
            ]
        ),
        table_row(
            [
                "BITDEER TECHNOLOGIES GROUP (BTDR)",
                "增持算力基础设施和矿业平台资产。",
                "矿场、云算力和数据中心服务可向 AI/HPC 托管延伸，但当前仍受挖矿业务影响。",
                "重点看 AI/HPC 业务落地、矿机/自挖矿周期和数据中心利用率。",
            ]
        ),
        table_row(
            [
                "INTEL CORP (INTC)",
                "现股小额增持，但上一期大额 Call 已清仓，说明仅保留较低权重的半导体可选性。",
                "AI 关系来自 CPU、数据中心芯片、AI 加速器、先进封装和代工，但执行不确定性高。",
                "重点看代工进展、AI 加速器竞争力、数据中心 CPU 份额和资本开支压力。",
            ]
        ),
        "",
        "- 小结：这些增持不是围绕 AI 应用软件，而是围绕 AI capex 的底层瓶颈：存储、GPU 云、数据中心、电力、矿场转 HPC 和半导体供给。",
        "- 风险提示：矿场转 AI/HPC 需要客户合同、电力质量、机房改造、融资和执行兑现；不能只因有电力资产就直接等同于 AI 数据中心。",
        "",
    ]


def situational_awareness_thesis_lines() -> list[str]:
    return [
        "### 投资思路判断",
        "",
        "- 第一层：从 AI 电力/数据中心纯基建，扩展到半导体周期和 AI 芯片链。新进 NVIDIA、Broadcom、AMD、TSMC、ASML、Micron、VanEck Semiconductor ETF，说明它把 AI 算力瓶颈从机房和电力进一步上溯到 GPU、ASIC、晶圆代工、光刻设备和内存。",
        "- 第二层：继续保留真实资产型 AI 基建。Bloom Energy、CoreWeave 普通股、Applied Digital、IREN、Core Scientific、Riot、CleanSpark、Bitfarms 等仍在组合里，说明它没有放弃数据中心、电力和矿场转 HPC 这条主线。",
        "- 第三层：降低上一期部分拥挤或阶段性兑现的资产。Intel Call、Lumentum、Coherent、Cipher、EQT、Hut 8、Tower Semiconductor 被清仓，CoreWeave Call 大幅减持，代表组合从单点光通信/能源/矿业可选性转向更宽的半导体篮子。",
        "- 第四层：用期权表达非线性风险收益。本期最大新增多为 Put，包括 VanEck Semiconductor ETF、NVIDIA、Oracle、Broadcom、AMD、TSMC、ASML、Micron。它可能不是简单看空 AI，而是在 AI 半导体交易拥挤、波动上升时，用期权构建保护、波动率或相对价值仓位。",
        "- 第五层：组合仍围绕 AI 基建瓶颈。核心不是应用软件，而是芯片、内存、云算力、电力、数据中心和矿场资产再利用，投资框架偏“AI capex picks-and-shovels”。",
        "",
    ]


def instrument_label(holding: Holding) -> str:
    if holding.put_call:
        return f"{holding.title_of_class} {holding.put_call}"
    return holding.title_of_class


def updated_filing_analysis_section(
    snapshots: list[FilingSnapshot],
    changes_by_manager: dict[str, list[HoldingChange]],
    data_dir: Path,
) -> list[str]:
    current_report_date = max(snapshot.report_date for snapshot in snapshots)
    updated_snapshots = [snapshot for snapshot in snapshots if snapshot.report_date == current_report_date]
    if not updated_snapshots:
        return []

    lines = [
        "## 最新一期调仓变化分析",
        "",
        f"本节聚焦当前最新报告期 `{current_report_date}`，逐家比较最新 13F 与上一期 13F。"
        "新增管理人如本地暂缺不同报告期基线，将先列入监控并在后续披露后自动生成调仓比较。",
        "",
    ]

    for snapshot in updated_snapshots:
        previous = latest_previous_snapshot(data_dir, snapshot)
        if previous is None:
            lines.extend([f"### {snapshot.manager_name}", "", "暂无上一期 13F 基线，无法做调仓比较。", ""])
            continue
        changes = changes_by_manager.get(snapshot.manager_name, [])
        lines.extend(manager_rebalance_analysis(snapshot, previous, changes))
        lines.append("")
    return lines


def manager_rebalance_analysis(
    current: FilingSnapshot,
    previous: FilingSnapshot,
    changes: list[HoldingChange],
) -> list[str]:
    current_value = sum(holding.value_usd for holding in current.holdings)
    previous_value = sum(holding.value_usd for holding in previous.holdings)
    current_ai_value = sum(holding.value_usd for holding in current.holdings if holding.ai_theme)
    previous_ai_value = sum(holding.value_usd for holding in previous.holdings if holding.ai_theme)
    changed = [change for change in changes if change.status != "unchanged"]
    status_counts = {status: sum(1 for change in changes if change.status == status) for status in ["new", "exited", "increased", "decreased"]}

    lines = [
        f"### {current.manager_name}",
        "",
        table_row(["指标", "上一期", "最新一期", "变化"]),
        table_row(["---", "---:", "---:", "---:"]),
        table_row(
            [
                "报告期",
                previous.report_date,
                current.report_date,
                f"{previous.accession} -> {current.accession}",
            ]
        ),
        table_row(["持仓数", number(len(previous.holdings)), number(len(current.holdings)), number(len(current.holdings) - len(previous.holdings))]),
        table_row(["组合市值", money(previous_value), money(current_value), money(current_value - previous_value)]),
        table_row(["AI识别市值", money(previous_ai_value), money(current_ai_value), money(current_ai_value - previous_ai_value)]),
        "",
        f"- 调仓结构：新增 {status_counts['new']} 个，清仓 {status_counts['exited']} 个，增持 {status_counts['increased']} 个，减持 {status_counts['decreased']} 个。",
        f"- AI 暴露变化：{money(previous_ai_value)} -> {money(current_ai_value)}，变化 {money(current_ai_value - previous_ai_value)}。",
    ]

    ai_changes = [change for change in changed if change.ai_theme]
    if ai_changes:
        ai_changes.sort(key=lambda item: abs(item.value_change_usd), reverse=True)
        lines.append("- AI相关调仓：" + "；".join(change_sentence(change) for change in ai_changes[:5]) + "。")
    else:
        lines.append("- AI相关调仓：本期未识别到 AI 相关标的的明显调仓。")

    add_actions = [change for change in changed if change.status in {"new", "increased"}]
    reduce_actions = [change for change in changed if change.status in {"exited", "decreased"}]
    add_actions.sort(key=lambda item: abs(item.value_change_usd), reverse=True)
    reduce_actions.sort(key=lambda item: abs(item.value_change_usd), reverse=True)
    if add_actions:
        lines.append("- 主要新进/增持：" + "；".join(change_sentence(change) for change in add_actions[:5]) + "。")
    if reduce_actions:
        lines.append("- 主要清仓/减持：" + "；".join(change_sentence(change) for change in reduce_actions[:5]) + "。")
    lines.append(f"- 组合解读：{rebalance_judgement(current, previous)}")
    return lines


def change_sentence(change: HoldingChange) -> str:
    action = {
        "new": "新进",
        "exited": "清仓",
        "increased": "增持",
        "decreased": "减持",
        "unchanged": "持平",
    }.get(change.status, change.status)
    return f"{display_issuer(change.name_of_issuer)} {action}，市值变化 {money(change.value_change_usd)}"


def rebalance_judgement(current: FilingSnapshot, previous: FilingSnapshot) -> str:
    current_value = sum(holding.value_usd for holding in current.holdings)
    previous_value = sum(holding.value_usd for holding in previous.holdings)
    current_ai_value = sum(holding.value_usd for holding in current.holdings if holding.ai_theme)
    previous_ai_value = sum(holding.value_usd for holding in previous.holdings if holding.ai_theme)
    ai_delta = current_ai_value - previous_ai_value
    portfolio_delta = current_value - previous_value
    if ai_delta > 0 and portfolio_delta > 0:
        return "组合规模和 AI 识别暴露同步上升，新增/加仓方向偏向 AI 平台、芯片或相关生态。"
    if ai_delta > 0:
        return "组合总规模下降或变化有限，但 AI 识别暴露上升，说明资金结构向 AI 相关资产倾斜。"
    if ai_delta < 0:
        return "AI 识别暴露下降，需关注是否来自核心 AI 标的减仓，或仅是市值波动导致。"
    return "AI 识别暴露基本稳定，调仓更多体现非 AI 行业或个股权重调整。"


def ai_infra_flow_section(
    snapshots: list[FilingSnapshot],
    changes_by_manager: dict[str, list[HoldingChange]],
) -> list[str]:
    lines = [
        "## AI基建资金流向",
        "",
        "本节按五条 AI 基建链条跟踪 13F 调仓信号；同一标的可能同时属于多个链条，例如 AVGO 同时计入 `AI芯片` 与 `光通信/网络`，因此各链条金额不应简单加总。",
        "",
        table_row(["链条", "当前市值", "较上期市值变化", "加仓/新进", "减仓/清仓", "代表持仓", "说明"]),
        table_row(["---", "---:", "---:", "---", "---", "---", "---"]),
    ]

    for bucket in AI_INFRA_FLOW_BUCKETS:
        current_value = 0
        change_value = 0
        bucket_changes: list[HoldingChange] = []
        representatives: list[Holding] = []
        for snapshot in snapshots:
            for holding in snapshot.holdings:
                if holding_matches_fragments(holding.name_of_issuer, bucket.fragments):
                    current_value += holding.value_usd
                    representatives.append(holding)
            for change in changes_by_manager.get(snapshot.manager_name, []):
                if holding_matches_fragments(change.name_of_issuer, bucket.fragments) and change.status != "unchanged":
                    change_value += change.value_change_usd
                    bucket_changes.append(change)

        adds = [change for change in bucket_changes if change.status in {"new", "increased"}]
        reductions = [change for change in bucket_changes if change.status in {"exited", "decreased"}]
        adds.sort(key=lambda item: abs(item.value_change_usd), reverse=True)
        reductions.sort(key=lambda item: abs(item.value_change_usd), reverse=True)
        representatives.sort(key=lambda item: item.value_usd, reverse=True)
        lines.append(
            table_row(
                [
                    bucket.name,
                    money(current_value),
                    money(change_value),
                    compact_change_list(adds, 4),
                    compact_change_list(reductions, 4),
                    compact_holding_list(representatives, 5),
                    bucket.note,
                ]
            )
        )

    lines.extend(["", *ai_infra_manager_focus_lines(snapshots, changes_by_manager), ""])
    return lines


def holding_matches_fragments(name_of_issuer: str, fragments: tuple[str, ...]) -> bool:
    upper_name = name_of_issuer.upper()
    return any(matches_fragment(upper_name, fragment) for fragment in fragments)


def compact_change_list(changes: list[HoldingChange], limit: int) -> str:
    if not changes:
        return "无明显动作"
    return "；".join(change_sentence(change) for change in changes[:limit])


def compact_holding_list(holdings: list[Holding], limit: int) -> str:
    if not holdings:
        return "无"
    return "、".join(unique_holding_names(holdings, limit))


def ai_infra_manager_focus_lines(
    snapshots: list[FilingSnapshot],
    changes_by_manager: dict[str, list[HoldingChange]],
) -> list[str]:
    lines = ["### 管理人信号"]
    for snapshot in snapshots:
        manager_changes = []
        for change in changes_by_manager.get(snapshot.manager_name, []):
            if change.status == "unchanged":
                continue
            if any(holding_matches_fragments(change.name_of_issuer, bucket.fragments) for bucket in AI_INFRA_FLOW_BUCKETS):
                manager_changes.append(change)
        if not manager_changes:
            continue
        manager_changes.sort(key=lambda item: abs(item.value_change_usd), reverse=True)
        lines.append(f"- {snapshot.manager_name}：" + "；".join(change_sentence(change) for change in manager_changes[:6]) + "。")
    return lines


def duan_yongping_fund_analysis_section(
    snapshots: list[FilingSnapshot],
    changes_by_manager: dict[str, list[HoldingChange]],
    data_dir: Path,
) -> list[str]:
    snapshot = next((item for item in snapshots if item.manager_name == "H&H International Investment, LLC"), None)
    if snapshot is None:
        return []
    previous = latest_previous_snapshot(data_dir, snapshot)
    if previous is None:
        return [
            "## 段永平名下基金 H&H 最近两期调仓分析",
            "",
            "当前已加入 H&H International Investment, LLC（CIK 0001759760），但本地暂缺上一期 13F 基线，下一次获取两期快照后可生成调仓分析。",
            "",
        ]

    changes = [change for change in changes_by_manager.get(snapshot.manager_name, []) if change.status != "unchanged"]
    changes.sort(key=lambda item: abs(item.value_change_usd), reverse=True)
    previous_value = sum(holding.value_usd for holding in previous.holdings)
    current_value = sum(holding.value_usd for holding in snapshot.holdings)
    previous_ai_value = sum(holding.value_usd for holding in previous.holdings if holding.ai_theme)
    current_ai_value = sum(holding.value_usd for holding in snapshot.holdings if holding.ai_theme)
    status_counts = {
        status: sum(1 for change in changes_by_manager.get(snapshot.manager_name, []) if change.status == status)
        for status in ["new", "exited", "increased", "decreased"]
    }
    top_holdings = sorted(snapshot.holdings, key=lambda item: item.value_usd, reverse=True)[:10]
    ai_changes = [change for change in changes if change.ai_theme]

    lines = [
        "## 段永平名下基金 H&H 最近两期调仓分析",
        "",
        "申报主体：H&H International Investment, LLC（CIK 0001759760）。本节按最近两期 13F 比较，"
        "用于观察段永平公开美股组合的集中度、AI 暴露和季度调仓方向。",
        "",
        table_row(["指标", "上一期", "最新一期", "变化"]),
        table_row(["---", "---:", "---:", "---:"]),
        table_row(["报告期", previous.report_date, snapshot.report_date, f"{previous.accession} -> {snapshot.accession}"]),
        table_row(["持仓数", number(len(previous.holdings)), number(len(snapshot.holdings)), number(len(snapshot.holdings) - len(previous.holdings))]),
        table_row(["组合市值", money(previous_value), money(current_value), money(current_value - previous_value)]),
        table_row(["AI识别市值", money(previous_ai_value), money(current_ai_value), money(current_ai_value - previous_ai_value)]),
        "",
        f"- 调仓结构：新增 {status_counts['new']} 个，清仓 {status_counts['exited']} 个，增持 {status_counts['increased']} 个，减持 {status_counts['decreased']} 个。",
        f"- 集中度观察：最新前 3 大持仓为 {'、'.join(unique_holding_names(top_holdings, 3))}，组合仍是高度集中、低换手的价值投资/长期持有风格。",
    ]
    if ai_changes:
        ai_changes.sort(key=lambda item: abs(item.value_change_usd), reverse=True)
        lines.append("- AI相关调仓：" + "；".join(change_sentence(change) for change in ai_changes[:8]) + "。")
    else:
        lines.append("- AI相关调仓：最近两期未识别到 AI 相关标的的明显变动。")

    lines.extend(
        [
            "- 投资思路判断：H&H 的 AI 暴露不是 Situational Awareness 那类全链条 AI 基建交易，"
            "更像在长期核心仓位中叠加少数高质量科技平台、AI 芯片/代工和 AI 网络小仓位。",
            "- 风险提示：13F 只披露季度末美国上市证券多头和可报告期权，不披露日内交易、海外非 13F 资产、空头和衍生品完整结构。",
            "",
            "### H&H 最新前十大持仓",
            "",
            table_row(["标的", "行业", "AI关系", "数量", "市值", "组合占比", "业务/AI关系"]),
            table_row(["---", "---", "---", "---:", "---:", "---:", "---"]),
        ]
    )
    for holding in top_holdings:
        _, ai_detail = business_profile(holding.name_of_issuer)
        lines.append(
            table_row(
                [
                    display_issuer(holding.name_of_issuer),
                    holding.industry,
                    holding.ai_relationship,
                    number(holding.shares_or_principal),
                    money(holding.value_usd),
                    percent(holding.value_usd, current_value),
                    ai_detail,
                ]
            )
        )

    if changes:
        lines.extend(
            [
                "",
                "### H&H 主要调仓",
                "",
                table_row(["标的", "动作", "行业", "AI关系", "上一期市值", "最新市值", "变化", "数量变化"]),
                table_row(["---", "---", "---", "---", "---:", "---:", "---:", "---:"]),
            ]
        )
        for change in changes[:12]:
            lines.append(
                table_row(
                    [
                        display_issuer(change.name_of_issuer),
                        {
                            "new": "新进",
                            "exited": "清仓",
                            "increased": "增持",
                            "decreased": "减持",
                        }.get(change.status, change.status),
                        change.industry,
                        change.ai_relationship,
                        money(change.previous_value_usd),
                        money(change.current_value_usd),
                        money(change.value_change_usd),
                        number(change.share_change),
                    ]
                )
            )
    lines.append("")
    return lines


def build_report(
    snapshots: list[FilingSnapshot],
    changes_by_manager: dict[str, list[HoldingChange]],
    updated_accessions: set[str],
    data_dir: Path,
) -> str:
    generated_at = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")
    lines = [
        "# 13F AI 持仓监控报告",
        "",
        f"生成时间：{generated_at}",
        "",
        "数据源：SEC EDGAR Submissions API 与 Archives 13F information table XML。13F 披露有季度滞后，"
        "本报告用于跟踪公开披露持仓变化，不构成投资建议。",
        "",
        "## 组合概览",
        "",
        table_row(
            ["管理人", "最新报告期", "提交日", "持仓数", "组合市值", "AI识别市值", "AI识别占比", "行业Top3", "本次状态"]
        ),
        table_row(["---", "---", "---", "---:", "---:", "---:", "---:", "---", "---"]),
    ]

    for snapshot in snapshots:
        total_value = sum(holding.value_usd for holding in snapshot.holdings)
        ai_value = sum(holding.value_usd for holding in snapshot.holdings if holding.ai_theme)
        update_status = "已下载新13F" if snapshot.accession in updated_accessions else "无新增13F"
        industry_text = top_bucket_text(bucket_totals(snapshot.holdings, "industry"), total_value, 3)
        lines.append(
            table_row(
                [
                    snapshot.manager_name,
                    snapshot.report_date,
                    snapshot.filing_date,
                    number(len(snapshot.holdings)),
                    money(total_value),
                    money(ai_value),
                    percent(ai_value, total_value),
                    industry_text,
                    update_status,
                ]
            )
        )

    lines.extend([""])
    lines.extend(industry_analysis_section(snapshots))

    duan_analysis = duan_yongping_fund_analysis_section(snapshots, changes_by_manager, data_dir)
    if duan_analysis:
        lines.extend([""])
        lines.extend(duan_analysis)

    updated_analysis = updated_filing_analysis_section(snapshots, changes_by_manager, data_dir)
    if updated_analysis:
        lines.extend([""])
        lines.extend(updated_analysis)

    lines.extend([""])
    lines.extend(ai_infra_flow_section(snapshots, changes_by_manager))

    situational_lines = situational_awareness_detail_section(snapshots, changes_by_manager)
    if situational_lines:
        lines.extend([""])
        lines.extend(situational_lines)

    lines.extend(["", "## AI相关投资", ""])
    ai_rows = ai_holding_rows(snapshots, changes_by_manager)
    if ai_rows:
        lines.extend(ai_rows)
    else:
        lines.append("当前最新 13F 中未按内置规则识别到 AI 相关持仓。")

    lines.extend(["", "## 持仓变化摘要", ""])
    for snapshot in snapshots:
        changes = changes_by_manager.get(snapshot.manager_name, [])
        previous_changes = [change for change in changes if change.status != "unchanged"]
        previous_changes.sort(key=lambda item: abs(item.value_change_usd), reverse=True)
        lines.append(f"### {snapshot.manager_name}")
        previous = "可比较历史" if previous_changes else "暂无变化或缺少上一期基线"
        lines.append(f"- 最新 accession：{snapshot.accession}，报告期：{snapshot.report_date}，{previous}。")
        for change in previous_changes[:10]:
            lines.append(
                "- "
                f"{display_issuer(change.name_of_issuer)}：{change.status}，"
                f"数量 {number(change.previous_shares_or_principal)} -> {number(change.current_shares_or_principal)}，"
                f"市值变化 {money(change.value_change_usd)}。"
            )
        lines.append("")

    lines.extend(["## 最新逐股持仓", ""])
    for snapshot in snapshots:
        lines.append(f"### {snapshot.manager_name}")
        lines.extend(holding_table(snapshot))
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def build_situational_awareness_report(
    snapshots: list[FilingSnapshot],
    changes_by_manager: dict[str, list[HoldingChange]],
    data_dir: Path | None = None,
) -> str:
    generated_at = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")
    lines = [
        "# Situational Awareness LP 持仓分析报告",
        "",
        f"生成时间：{generated_at}",
        "",
        "数据源：SEC EDGAR Submissions API 与 Archives 13F information table XML。"
        "13F 披露有季度滞后，本报告用于跟踪公开披露持仓变化，不构成投资建议。",
        "",
    ]
    situational_snapshot = next((item for item in snapshots if item.manager_name == "Situational Awareness LP"), None)
    previous_snapshot = latest_previous_snapshot(data_dir, situational_snapshot) if data_dir and situational_snapshot else None
    analysis_lines = situational_awareness_investment_analysis_section(snapshots, changes_by_manager, previous_snapshot)
    if analysis_lines:
        lines.extend(analysis_lines)
    detail_lines = situational_awareness_detail_section(snapshots, changes_by_manager)
    if not detail_lines:
        lines.append("当前 watchlist 中没有 Situational Awareness LP 快照。")
    else:
        lines.extend(detail_lines)
    return "\n".join(lines).rstrip() + "\n"


def ai_holding_rows(
    snapshots: list[FilingSnapshot],
    changes_by_manager: dict[str, list[HoldingChange]],
) -> list[str]:
    rows = [
        table_row(["管理人", "标的", "行业", "AI关系", "数量", "市值", "组合占比", "AI主题", "关系说明", "较上期"]),
        table_row(["---", "---", "---", "---", "---:", "---:", "---:", "---", "---", "---:"]),
    ]
    has_ai = False
    for snapshot in snapshots:
        total_value = sum(holding.value_usd for holding in snapshot.holdings)
        changes = {change.key: change for change in changes_by_manager.get(snapshot.manager_name, [])}
        ai_holdings = [holding for holding in snapshot.holdings if holding.ai_theme]
        ai_holdings.sort(key=lambda item: item.value_usd, reverse=True)
        for holding in ai_holdings:
            has_ai = True
            change = changes.get(holding_key(holding))
            change_value = money(change.value_change_usd) if change else "n/a"
            rows.append(
                table_row(
                    [
                        snapshot.manager_name,
                        display_issuer(holding.name_of_issuer),
                        holding.industry,
                        holding.ai_relationship,
                        number(holding.shares_or_principal),
                        money(holding.value_usd),
                        percent(holding.value_usd, total_value),
                        holding.ai_theme,
                        holding.ai_reason or holding.ai_connection,
                        change_value,
                    ]
                )
            )
    return rows if has_ai else []


def holding_table(snapshot: FilingSnapshot) -> list[str]:
    total_value = sum(holding.value_usd for holding in snapshot.holdings)
    rows = [
        table_row(["标的", "类别", "行业", "AI关系", "CUSIP", "Put/Call", "数量", "市值", "组合占比", "AI主题"]),
        table_row(["---", "---", "---", "---", "---", "---", "---:", "---:", "---:", "---"]),
    ]
    holdings = sorted(snapshot.holdings, key=lambda item: item.value_usd, reverse=True)
    for holding in holdings:
        rows.append(
            table_row(
                [
                    display_issuer(holding.name_of_issuer),
                    holding.title_of_class,
                    holding.industry,
                    holding.ai_relationship,
                    holding.cusip,
                    holding.put_call or "",
                    number(holding.shares_or_principal),
                    money(holding.value_usd),
                    percent(holding.value_usd, total_value),
                    holding.ai_theme or "",
                ]
            )
        )
    return rows


async def run_monitor(data_dir: Path, report_path: Path, user_agent: str) -> list[FilingSnapshot]:
    data_dir.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    managers = [ManagerConfig(name=name, cik=cik) for name, cik in WATCHLIST]
    snapshots: list[FilingSnapshot] = []
    updated_accessions: set[str] = set()

    for manager in managers:
        filings = await recent_13f_filings(manager, user_agent)
        if not filings:
            LOGGER.warning("no_13f_filings", extra={"manager": manager.name, "cik": manager.cik})
            continue
        if len(filings) > 1 and existing_snapshot(data_dir, filings[1]) is None:
            LOGGER.info("download_baseline_13f", extra={"manager": manager.name, "accession": filings[1].accession})
            await download_snapshot(filings[1], data_dir, user_agent)

        latest_meta = filings[0]
        latest_snapshot = existing_snapshot(data_dir, latest_meta)
        if latest_snapshot is None:
            LOGGER.info("download_latest_13f", extra={"manager": manager.name, "accession": latest_meta.accession})
            latest_snapshot = await download_snapshot(latest_meta, data_dir, user_agent)
            updated_accessions.add(latest_meta.accession)

        snapshots.append(latest_snapshot)

    changes_by_manager = {
        snapshot.manager_name: compare_holdings(snapshot, latest_previous_snapshot(data_dir, snapshot))
        for snapshot in snapshots
    }
    report = build_report(snapshots, changes_by_manager, updated_accessions, data_dir)
    report_path.write_text(report, encoding="utf-8")
    situational_report_path = report_path.parent / "situational_awareness_lp_report.md"
    situational_report = build_situational_awareness_report(snapshots, changes_by_manager, data_dir)
    situational_report_path.write_text(situational_report, encoding="utf-8")
    save_state(data_dir, snapshots, updated_accessions, report_path)
    return snapshots


def save_state(
    data_dir: Path,
    snapshots: list[FilingSnapshot],
    updated_accessions: set[str],
    report_path: Path,
) -> None:
    state = {
        "last_run_at": datetime.now(timezone.utc).isoformat(),
        "report_path": str(report_path),
        "updated_accessions": sorted(updated_accessions),
        "latest": [
            {
                "manager_name": snapshot.manager_name,
                "cik": snapshot.cik,
                "accession": snapshot.accession,
                "filing_date": snapshot.filing_date,
                "report_date": snapshot.report_date,
            }
            for snapshot in snapshots
        ],
    }
    (data_dir / "state.json").write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


def parse_args() -> argparse.Namespace:
    repo_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description="Monitor selected 13F filings for AI-related holdings.")
    parser.add_argument("--data-dir", type=Path, default=repo_root / "data" / "13f_monitor")
    parser.add_argument("--report-path", type=Path, default=repo_root / "reports" / "13_following" / "13f_ai_report.md")
    parser.add_argument(
        "--user-agent",
        default=os.environ.get("SEC_USER_AGENT", DEFAULT_USER_AGENT),
        help="SEC User-Agent header. Prefer setting SEC_USER_AGENT with your contact email.",
    )
    return parser.parse_args()


async def async_main() -> int:
    configure_logging()
    args = parse_args()
    await run_monitor(args.data_dir, args.report_path, args.user_agent)
    LOGGER.info("report_updated", extra={"report_path": str(args.report_path)})
    return 0


def main() -> int:
    return asyncio.run(async_main())


if __name__ == "__main__":
    raise SystemExit(main())
