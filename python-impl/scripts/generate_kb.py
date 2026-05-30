"""生成 W1 演示用知识库种子文档（≥20 篇，覆盖退款/物流/售后/会员/活动/隐私等）。

特点：
- 不调用真实 LLM，纯模板拼接
- 同时产出全局文档（tenant_id 空）和租户专属文档（tenant_id=1/2）
- 输出到 docs/knowledge_base/{global,tenant_a,tenant_b}/*.md
- 每篇 600~1500 字，含明确条款 / 期限 / 例外，便于 RAG 评测
"""
from __future__ import annotations

import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]  # 智能售后/
KB_DIR = ROOT / "docs" / "knowledge_base"


def _doc(
    *,
    doc_no: str,
    title: str,
    category: str,
    tenant_id: int | None,
    sections: list[tuple[str, str]],
) -> str:
    """生成单篇 Markdown：YAML frontmatter + 多级正文。"""
    fm_lines = [
        "---",
        f"doc_no: {doc_no}",
        f"title: {title}",
        f"category: {category}",
    ]
    if tenant_id is not None:
        fm_lines.append(f"tenant_id: {tenant_id}")
    fm_lines.extend(["effective_from: 2026-01-01", "effective_to: 2027-12-31", "---", ""])
    body = [f"# {title}", ""]
    for heading, text in sections:
        body.append(f"## {heading}")
        body.append("")
        body.append(text.strip())
        body.append("")
    return "\n".join(fm_lines) + "\n".join(body)


GLOBAL_DOCS: list[dict] = [
    {
        "doc_no": "KB-G-001",
        "title": "7 天无理由退换货政策",
        "category": "refund",
        "sections": [
            ("适用范围", "适用于所有自营商品。第三方店铺商品请以店铺挂出的售后页为准。"),
            (
                "时限",
                "签收之日（含）起 7 天内可申请。系统以物流签收时间为准。"
                "超过 7 天系统将拒绝自动退款；如有特殊情况可走人工渠道。",
            ),
            (
                "条件",
                "商品保持原包装、未拆封或未使用，吊牌齐全。\n"
                "已激活的电子产品、贴身衣物、定制商品不支持 7 天无理由。",
            ),
            ("退款到账", "原路退回，3-5 个工作日到账。信用卡可能延迟到下月账单。"),
        ],
    },
    {
        "doc_no": "KB-G-002",
        "title": "退款流程与状态说明",
        "category": "refund",
        "sections": [
            ("申请入口", "订单详情页 → 申请退款；或售后助手对话框直接说「申请退款」。"),
            (
                "状态说明",
                "1. 待审核：客服 4 小时内确认；\n"
                "2. 待退货：用户上传物流单号；\n"
                "3. 退款中：财务原路退回；\n"
                "4. 已完成：款项到账。",
            ),
            ("常见拒绝原因", "证据照片不清晰、商品有人为损坏痕迹、超期申请。"),
        ],
    },
    {
        "doc_no": "KB-G-003",
        "title": "运费规则",
        "category": "shipping",
        "sections": [
            ("包邮门槛", "下单满 99 元包邮（偏远地区除外）。会员包邮门槛 59 元。"),
            ("退货运费", "质量问题商家承担；7 天无理由用户承担。运费险按险种自动赔付。"),
            ("偏远地区清单", "新疆、西藏、内蒙部分地区、海南部分地区不参与全国包邮。"),
        ],
    },
    {
        "doc_no": "KB-G-004",
        "title": "发货时效",
        "category": "shipping",
        "sections": [
            ("常规", "现货商品 48 小时内发货；预售商品按详情页公示时效发货。"),
            ("节假日", "国家法定节假日仓库轮休，发货时效顺延 1-2 天。"),
            ("延迟赔付", "超 7 天未发货可申请单价 5% 平台券补偿，上限 50 元。"),
        ],
    },
    {
        "doc_no": "KB-G-005",
        "title": "修改收货地址",
        "category": "shipping",
        "sections": [
            ("允许范围", "订单状态为「待付款」或「待发货」时支持自助修改。"),
            ("已发货", "已发货订单需联系快递公司中转，平台无法代操作。失败概率较高。"),
            ("跨省限制", "原则上不允许跨省修改；如确有需要请联系客服评估。"),
        ],
    },
    {
        "doc_no": "KB-G-006",
        "title": "物流签收与拒收",
        "category": "shipping",
        "sections": [
            ("签收异常", "外包装破损、内件少件需当面拒收并联系客服。"),
            ("拒收处理", "拒收件回仓后系统自动触发退款。退款流程同 7 天无理由。"),
        ],
    },
    {
        "doc_no": "KB-G-007",
        "title": "商品质量问题判定",
        "category": "after_sales",
        "sections": [
            ("可视为质量问题", "功能失效、外观与商详不符、显著色差、严重瑕疵。"),
            ("不视为质量问题", "正常使用磨损、用户拆改、个人喜好（颜色偏好）。"),
            ("赔付", "质量问题可申请退一赔三；以最近一次司法判例为参考上限。"),
        ],
    },
    {
        "doc_no": "KB-G-008",
        "title": "电子产品保修政策",
        "category": "warranty",
        "sections": [
            ("保修期", "整机 1 年，主要部件 2 年。具体以商品保修卡为准。"),
            ("不在保修范围", "进液、跌落、私拆、自然磨损、非授权维修。"),
            ("送修方式", "在线申请 → 上门取件 → 厂家鉴定 → 维修/换新 → 寄回。"),
        ],
    },
    {
        "doc_no": "KB-G-009",
        "title": "会员等级与权益",
        "category": "membership",
        "sections": [
            ("等级体系", "普通 / 银卡（年消费 ≥1000）/ 金卡（≥5000）/ 黑金（≥20000）。"),
            ("核心权益", "金卡专享 9 折、黑金免运费、生日双倍积分、专属客服通道。"),
            ("降级规则", "自然年度未达标自动降级一档。"),
        ],
    },
    {
        "doc_no": "KB-G-010",
        "title": "积分使用规则",
        "category": "membership",
        "sections": [
            ("获取", "下单结算金额 1 元 = 1 积分；商品评价额外 +50 积分。"),
            ("使用", "100 积分 = 1 元，单笔最多抵扣订单金额 20%。"),
            ("有效期", "次年 12 月 31 日清零。临期前 30 天会站内信提醒。"),
        ],
    },
    {
        "doc_no": "KB-G-011",
        "title": "优惠券规则",
        "category": "promotion",
        "sections": [
            ("叠加", "店铺券 + 平台券可叠加；同类券不可叠加。"),
            ("退款影响", "整单退款时优惠券原路退回券包；部分退款时已抵扣金额不返还。"),
        ],
    },
    {
        "doc_no": "KB-G-012",
        "title": "发票申请",
        "category": "invoice",
        "sections": [
            ("普票", "下单时选择电子普票，订单完成 24 小时内开具。"),
            ("专票", "需提交资质（一般纳税人证明），人工审核 3 个工作日。"),
            ("重开/换抬头", "180 天内可申请重开一次，超期不再支持。"),
        ],
    },
    {
        "doc_no": "KB-G-013",
        "title": "投诉与升级",
        "category": "complaint",
        "sections": [
            ("一线客服", "在线/电话首次响应 5 分钟，解决时效 24 小时。"),
            ("升级条件", "超时未解决或对一线方案不满可升级；升级后 48 小时内主管回访。"),
        ],
    },
    {
        "doc_no": "KB-G-014",
        "title": "用户隐私与数据使用",
        "category": "privacy",
        "sections": [
            ("收集范围", "仅收集下单、物流、售后所必需的最少信息。"),
            ("第三方共享", "仅在用户授权或法律要求时共享，且签订数据处理协议。"),
            ("注销账户", "可在 App 内提交注销，30 天冷静期后彻底清除可识别信息。"),
        ],
    },
    {
        "doc_no": "KB-G-015",
        "title": "禁限售商品",
        "category": "policy",
        "sections": [
            ("禁售", "管制刀具、易燃易爆、违禁药品、走私品。"),
            ("限售", "酒类需身份验证；处方药需在线问诊。"),
        ],
    },
]


# 租户 A 专属（tenant_id=1）
TENANT_A_DOCS: list[dict] = [
    {
        "doc_no": "KB-A-001",
        "title": "RetailGuard A 店 VIP 售后通道",
        "category": "after_sales",
        "sections": [
            ("通道", "VIP 用户可走绿色通道，工单优先处理，承诺 2 小时响应。"),
            ("识别", "下单账号会员等级 ≥ 金卡自动识别为 VIP。"),
        ],
    },
    {
        "doc_no": "KB-A-002",
        "title": "RetailGuard A 店专属退换货补贴",
        "category": "refund",
        "sections": [
            ("额度", "A 店用户额外享 30 元来回运费补贴券，单月限 2 次。"),
            ("发放", "退款审核通过即自动发券至账户。"),
        ],
    },
    {
        "doc_no": "KB-A-003",
        "title": "RetailGuard A 店赠品政策",
        "category": "promotion",
        "sections": [
            ("规则", "满 200 送同店赠品 1 份；退款时赠品需一并退回，否则按吊牌价抵扣。"),
        ],
    },
]


# 租户 B 专属（tenant_id=2）— 用于隔离测试
TENANT_B_DOCS: list[dict] = [
    {
        "doc_no": "KB-B-001",
        "title": "RetailGuard B 店退换货政策（30 天）",
        "category": "refund",
        "sections": [
            ("时限", "B 店所有商品支持 30 天无理由退换，远超全网 7 天。"),
            ("条件", "保持商品完好、配件齐全。"),
        ],
    },
    {
        "doc_no": "KB-B-002",
        "title": "RetailGuard B 店企业大客户专线",
        "category": "after_sales",
        "sections": [
            ("入口", "企业账号绑定后显示专属客服按钮。"),
            ("权益", "1 对 1 客户经理、专属对账单、优先发货。"),
        ],
    },
    {
        "doc_no": "KB-B-003",
        "title": "RetailGuard B 店海外仓发货说明",
        "category": "shipping",
        "sections": [
            ("时效", "海外仓发货约 7-15 个工作日，关税由 B 店统一垫付。"),
        ],
    },
]


def write_docs(out_dir: Path, docs: list[dict], tenant_id: int | None) -> int:
    out_dir.mkdir(parents=True, exist_ok=True)
    for d in docs:
        path = out_dir / f"{d['doc_no']}.md"
        path.write_text(
            _doc(
                doc_no=d["doc_no"],
                title=d["title"],
                category=d["category"],
                tenant_id=tenant_id,
                sections=d["sections"],
            ),
            encoding="utf-8",
        )
    return len(docs)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=str(KB_DIR), help="输出目录")
    args = parser.parse_args()

    base = Path(args.out)
    n_g = write_docs(base / "global", GLOBAL_DOCS, tenant_id=None)
    n_a = write_docs(base / "tenant_a", TENANT_A_DOCS, tenant_id=1)
    n_b = write_docs(base / "tenant_b", TENANT_B_DOCS, tenant_id=2)
    total = n_g + n_a + n_b
    print(f"[generate_kb] global={n_g} tenant_a={n_a} tenant_b={n_b} total={total}  →  {base}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
