from __future__ import annotations

import json
from pathlib import Path
from memory.long_term import LongTermMemory

KNOWLEDGE_BASE = [
    {
        "content": "【退款政策】已发货但未签收的商品，支持全额退款申请。退款将在收到退货并确认后3-5个工作日内原路返回。",
        "source": "退款政策.md",
        "category": "refund",
    },
    {
        "content": "【退款政策】已签收的商品，在签收后7天内可申请退货退款，超出7天不再受理。",
        "source": "退款政策.md",
        "category": "refund",
    },
    {
        "content": "【退款政策】定制商品、生鲜食品、内衣裤等特殊性商品一旦购买不支持7天无理由退货。",
        "source": "退款政策.md",
        "category": "refund",
    },
    {
        "content": "【退款政策】退款状态说明：处理中（1-2个工作日审核）→ 已退款（3-5个工作日到账）。",
        "source": "退款政策.md",
        "category": "refund",
    },
    {
        "content": "【地址修改】订单在【待发货】状态下可自助修改收货地址。订单一旦发货，不再支持地址修改。",
        "source": "地址修改.md",
        "category": "address",
    },
    {
        "content": "【地址修改】修改地址后，若原收货人信息不同，配送员可能需要核实身份。",
        "source": "地址修改.md",
        "category": "address",
    },
    {
        "content": "【地址修改】已发货的订单如需更改地址，可联系客服申请拦截，拦截成功后可重新下单。",
        "source": "地址修改.md",
        "category": "address",
    },
    {
        "content": "【物流查询】订单发货后，可在【我的订单】中查看物流信息，包括快递单号和实时位置。",
        "source": "物流查询.md",
        "category": "shipping",
    },
    {
        "content": "【物流查询】常规配送时效：同城1-2天，省内2-3天，省外3-5天，偏远地区5-7天。",
        "source": "物流查询.md",
        "category": "shipping",
    },
    {
        "content": "【物流查询】如配送超期（超过承诺时间5天以上），可申请全额退款。",
        "source": "物流查询.md",
        "category": "shipping",
    },
    {
        "content": "【支付问题】支付失败常见原因：银行卡限额、余额不足、网络超时。建议稍后重试或更换支付方式。",
        "source": "支付问题.md",
        "category": "payment",
    },
    {
        "content": "【支付问题】支持支付宝、微信支付、银行卡、信用卡等多种支付方式。",
        "source": "支付问题.md",
        "category": "payment",
    },
    {
        "content": "【支付问题】使用优惠券/红包后申请退款，优惠金额不返还，优先退还实际支付金额。",
        "source": "支付问题.md",
        "category": "payment",
    },
    {
        "content": "【发票开具】电子发票：在订单完成后，可在【订单详情】中下载电子发票，有效期为1年。",
        "source": "发票问题.md",
        "category": "invoice",
    },
    {
        "content": "【发票开具】纸质发票：需在订单确认收货后15天内联系客服申请，快递费用自付。",
        "source": "发票问题.md",
        "category": "invoice",
    },
    {
        "content": "【发票开具】发票内容默认为商品明细，如需开具增值税专用发票需提供企业资质。",
        "source": "发票问题.md",
        "category": "invoice",
    },
    {
        "content": "【优惠券】优惠券有效期为领取后30天内，逾期自动作废，不可延期。",
        "source": "优惠券.md",
        "category": "coupon",
    },
    {
        "content": "【优惠券】每个订单仅限使用一张优惠券，优惠券不可叠加使用。",
        "source": "优惠券.md",
        "category": "coupon",
    },
    {
        "content": "【优惠券】优惠券一经使用，若订单取消，优惠券不予返还。",
        "source": "优惠券.md",
        "category": "coupon",
    },
    {
        "content": "【会员权益】会员等级分为：普通会员、银牌会员、金牌会员、钻石会员。",
        "source": "会员权益.md",
        "category": "membership",
    },
    {
        "content": "【会员权益】银牌会员享受全场95折，金牌会员享受9折，钻石会员享受85折。",
        "source": "会员权益.md",
        "category": "membership",
    },
    {
        "content": "【会员权益】会员生日当月可领取专属生日礼包，包括优惠券和双倍积分。",
        "source": "会员权益.md",
        "category": "membership",
    },
    {
        "content": "【积分规则】每消费1元累积1积分，积分可在下次购物时抵扣（100积分=1元）。",
        "source": "积分规则.md",
        "category": "points",
    },
    {
        "content": "【积分规则】积分有效期为获得后12个月，逾期自动清零，请及时使用。",
        "source": "积分规则.md",
        "category": "points",
    },
    {
        "content": "【积分规则】退货订单的积分将从账户中扣除，账户积分不足时将从退款中扣除。",
        "source": "积分规则.md",
        "category": "points",
    },
    {
        "content": "【商品咨询】商品详情页标注\"正品保障\"表示商品为官方渠道正品。",
        "source": "商品咨询.md",
        "category": "product",
    },
    {
        "content": "【商品咨询】商品价格随市场波动，以下单时价格为准，不接受事后价格保护申请。",
        "source": "商品咨询.md",
        "category": "product",
    },
    {
        "content": "【商品咨询】商品库存显示\"已售罄\"时，可点击到货提醒，我们会在到货后第一时间通知您。",
        "source": "商品咨询.md",
        "category": "product",
    },
    {
        "content": "【售后服务】电器类商品（手机、电脑、数码产品）享有一年官方保修服务。",
        "source": "售后服务.md",
        "category": "service",
    },
    {
        "content": "【售后服务】保修期内非人为损坏可免费维修，人为损坏或过了保修期需付费维修。",
        "source": "售后服务.md",
        "category": "service",
    },
    {
        "content": "【售后服务】维修周期一般为7-15个工作日，具体时间视维修点情况而定。",
        "source": "售后服务.md",
        "category": "service",
    },
    {
        "content": "【投诉建议】如对服务不满意，可通过客服热线、在线客服或邮件进行投诉。",
        "source": "投诉建议.md",
        "category": "feedback",
    },
    {
        "content": "【投诉建议】投诉处理时效：普通投诉3个工作日内回复，重大投诉7个工作日内回复。",
        "source": "投诉建议.md",
        "category": "feedback",
    },
    {
        "content": "【投诉建议】采纳有效建议后，赠送50元无门槛优惠券作为感谢。",
        "source": "投诉建议.md",
        "category": "feedback",
    },
    {
        "content": "【账户安全】建议设置支付密码，开启手机验证，提升账户安全等级。",
        "source": "账户安全.md",
        "category": "security",
    },
    {
        "content": "【账户安全】发现账户异常登录，请立即修改密码并联系客服冻结账户。",
        "source": "账户安全.md",
        "category": "security",
    },
    {
        "content": "【账户安全】一个账户最多绑定5台常用设备，超出后需解绑旧设备才能绑定新设备。",
        "source": "账户安全.md",
        "category": "security",
    },
    {
        "content": "【取消订单】未发货订单可自助取消，取消后金额将在1小时内原路退回。",
        "source": "取消订单.md",
        "category": "cancel",
    },
    {
        "content": "【取消订单】已发货订单不支持取消，需收到货后申请退货。",
        "source": "取消订单.md",
        "category": "cancel",
    },
    {
        "content": "【取消订单】使用优惠券/红包的订单取消后，优惠金额不返还。",
        "source": "取消订单.md",
        "category": "cancel",
    },
]


def init_knowledge_base(
    kb_path: str = "./vector_store/knowledge_base.json",
    index_path: str = "./vector_store/faiss_index",
):
    kb_file = Path(kb_path)
    kb_file.parent.mkdir(parents=True, exist_ok=True)

    if kb_file.exists():
        print(f"Knowledge base already exists at {kb_file}")
        choice = input("Overwrite? (y/N): ").strip().lower()
        if choice != "y":
            print("Skipped.")
            return

    mem = LongTermMemory(index_path=index_path)

    print(f"Adding {len(KNOWLEDGE_BASE)} documents to knowledge base...")
    for doc in KNOWLEDGE_BASE:
        mem.add_document(
            content=doc["content"],
            source=doc["source"],
            metadata={"category": doc["category"]},
        )

    mem.save()
    print(f"Knowledge base saved to {kb_file}")
    print(f"FAISS index saved to {index_path}")

    results = mem.search("退款", top_k=3)
    print(f"\nTest search '退款': {len(results)} results")
    for r in results:
        print(f"  - {r['content'][:40]}... (score={r['score']:.4f})")


if __name__ == "__main__":
    init_knowledge_base()