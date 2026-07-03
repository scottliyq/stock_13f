"""Default manager registry for institution-focused views."""

from dataclasses import dataclass


@dataclass(frozen=True)
class ManagerRegistryEntry:
    manager_name: str
    manager_cik: int
    focus_areas: str
    short_description: str
    display_order: int
    is_active: bool = True


DEFAULT_MANAGER_WATCHLIST: tuple[ManagerRegistryEntry, ...] = (
    ManagerRegistryEntry(
        manager_name="Pershing Square Capital Management, L.P.",
        manager_cik=1336528,
        focus_areas="集中组合、平台/消费/基础设施变化",
        short_description="Bill Ackman 旗下集中型主动管理机构，持仓数量少、单票权重大，适合观察大市值平台公司和基础设施类资产的季度权重变化。",
        display_order=1,
    ),
    ManagerRegistryEntry(
        manager_name="Appaloosa Management LP",
        manager_cik=1006438,
        focus_areas="宏观周期、科技权重、金融/周期股切换",
        short_description="David Tepper 相关机构，历史上带有宏观和周期交易色彩；本地脚本继续保留用于追踪其公开 13F 变化。",
        display_order=2,
    ),
    ManagerRegistryEntry(
        manager_name="Situational Awareness LP",
        manager_cik=2045724,
        focus_areas="AI 基建、半导体、数据中心、电力链",
        short_description="Leopold Aschenbrenner 相关 AI 主题机构，组合高度集中在 AI 算力、半导体、数据中心和电力瓶颈方向，是本项目 AI 资金流监控的核心样本。",
        display_order=3,
    ),
    ManagerRegistryEntry(
        manager_name="Citrine Capital LLC",
        manager_cik=2053242,
        focus_areas="Citrini 主题映射、AI 瓶颈链条、ETF/权重变化",
        short_description="用户口径中的 Citrini 资金对应申报主体；适合和 Citrini 研报方向交叉验证，观察 AI 产业链、半导体和宏观/ETF 配置变化。",
        display_order=4,
    ),
    ManagerRegistryEntry(
        manager_name="ARK Investment Management LLC",
        manager_cik=1697748,
        focus_areas="创新成长、AI 应用、自动驾驶、基因/软件",
        short_description="Cathie Wood 旗下 ARK 系列 ETF 管理人，组合偏高成长与高波动创新资产，适合观察 AI 应用、自动驾驶、软件和新兴科技主题轮动。",
        display_order=5,
    ),
    ManagerRegistryEntry(
        manager_name="Light Street Capital Management, LLC",
        manager_cik=1569049,
        focus_areas="半导体、AI 云、互联网成长股",
        short_description="科技成长风格机构，13F 中常见半导体、互联网平台和 AI 云相关持仓，适合观察中高 beta 科技资金偏好。",
        display_order=6,
    ),
    ManagerRegistryEntry(
        manager_name="Coatue Management LLC",
        manager_cik=1135730,
        focus_areas="大型科技、半导体设备、AI 数据中心配套",
        short_description="Philippe Laffont 旗下科技投资机构，组合覆盖大型科技、半导体设备、云平台和电力/数据中心配套，是 AI 产业链机构资金的重要样本。",
        display_order=7,
    ),
    ManagerRegistryEntry(
        manager_name="CastleKnight Management LP",
        manager_cik=1835751,
        focus_areas="中小盘 AI 链、期权、光通信/存储/矿企 AIDC",
        short_description="组合覆盖面较广，适合筛选小中盘 AI 基建线索；尤其关注普通股与 Call/Put 对同一主题的方向差异。",
        display_order=8,
    ),
    ManagerRegistryEntry(
        manager_name="H&H International Investment, LLC",
        manager_cik=1759760,
        focus_areas="段永平相关组合、Apple/NVDA/TSLA/CRDO 等变化",
        short_description="段永平名下公开 13F 申报主体，组合集中度高；适合观察消费电子、AI 芯片、自动驾驶和少量高弹性 AI 互连仓位变化。",
        display_order=9,
    ),
    ManagerRegistryEntry(
        manager_name="Maverick Capital Ltd",
        manager_cik=934639,
        focus_areas="多空成长基金的科技/AI 权重、季度加减仓",
        short_description="Lee Ainslie 相关老牌成长型对冲基金，13F 适合观察科技、互联网、半导体和成长股的主动配置变化。",
        display_order=10,
    ),
    ManagerRegistryEntry(
        manager_name="Eclipse Operations, LLC",
        manager_cik=1908066,
        focus_areas="Eclipse / Physical AI 相关公开持仓",
        short_description="Eclipse 相关 13F 申报主体，公开持仓高度集中，适合观察其上市公司退出/保留仓位，而不是完整反映其一级市场 Physical AI 投资组合。",
        display_order=11,
    ),
)


def list_default_managers() -> list[ManagerRegistryEntry]:
    return list(DEFAULT_MANAGER_WATCHLIST)
