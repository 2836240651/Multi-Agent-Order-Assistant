"""
添加物流相关知识库文档
"""

from __future__ import annotations

import sys
sys.path.insert(0, '.')

from memory.long_term import LongTermMemory


LOGISTICS_KNOWLEDGE = [
    # 物流基础政策
    {
        "content": "【配送时效】常规配送时效：同城1-2天，省内2-3天，省外3-5天，偏远地区5-7天。节假日期间可能有所延迟。",
        "source": "物流政策.md",
        "category": "logistics",
    },
    {
        "content": "【配送时效】大件商品（如家具、家电）配送时效可能延长1-2天，需预约安装时间。",
        "source": "物流政策.md",
        "category": "logistics",
    },
    {
        "content": "【配送范围】支持全国范围内配送，部分偏远地区（如西藏、新疆、内蒙古等）可能需要更长时间。",
        "source": "物流政策.md",
        "category": "logistics",
    },
    {
        "content": "【配送费用】订单金额满99元免运费，不满99元收取8-12元运费，具体以结算页面为准。",
        "source": "物流政策.md",
        "category": "logistics",
    },
    {
        "content": "【配送费用】大件商品运费根据重量和体积计算，具体费用在商品页标注。",
        "source": "物流政策.md",
        "category": "logistics",
    },
    {
        "content": "【保价服务】可选择保价服务，保价费为商品金额的0.5%，最高不超过100元。",
        "source": "物流政策.md",
        "category": "logistics",
    },
    {
        "content": "【保价服务】如商品在运输过程中丢失或损坏，按保价金额赔偿；未保价商品按运费的3倍赔偿。",
        "source": "物流政策.md",
        "category": "logistics",
    },

    # 物流查询
    {
        "content": "【物流查询】订单发货后，可在「我的订单」中查看物流信息，包括快递单号和实时位置。",
        "source": "物流查询.md",
        "category": "logistics",
    },
    {
        "content": "【物流查询】物流信息更新可能有1-2小时延迟，如暂时查询不到请稍后再试。",
        "source": "物流查询.md",
        "category": "logistics",
    },
    {
        "content": "【物流查询】通过快递单号可在对应快递公司官网实时追踪包裹位置。",
        "source": "物流查询.md",
        "category": "logistics",
    },
    {
        "content": "【物流查询】如配送超期（超过承诺时间5天以上），可申请全额退款。",
        "source": "物流查询.md",
        "category": "logistics",
    },
    {
        "content": "【物流异常】如发现物流信息长时间未更新（超过3天），请联系客服协助查询。",
        "source": "物流查询.md",
        "category": "logistics",
    },
    {
        "content": "【物流异常】包裹异常（联系收件人未果、地址不详等）时，快递员会联系客服，客服会主动联系您。",
        "source": "物流查询.md",
        "category": "logistics",
    },

    # 签收与拒收
    {
        "content": "【签收规则】签收前请检查外包装是否完好，如包装破损可拒收并联系客服。",
        "source": "签收规则.md",
        "category": "logistics",
    },
    {
        "content": "【签收规则】签收后发现商品损坏，需在24小时内反馈并提供照片证据。",
        "source": "签收规则.md",
        "category": "logistics",
    },
    {
        "content": "【拒收规则】如需拒收，请在快递员联系您时说明，快递员会带回包裹。",
        "source": "签收规则.md",
        "category": "logistics",
    },
    {
        "content": "【拒收规则】拒收后订单将自动退款，运费不退还。",
        "source": "签收规则.md",
        "category": "logistics",
    },
    {
        "content": "【代收规则】如需他人代收，请提前告知快递员，并确认代收人信息。",
        "source": "签收规则.md",
        "category": "logistics",
    },

    # 催发货
    {
        "content": "【催发货】如订单超过48小时未发货，可申请催促发货。",
        "source": "催发货.md",
        "category": "logistics",
    },
    {
        "content": "【催发货】催促发货后，仓库会加急处理，但无法保证具体发货时间。",
        "source": "催发货.md",
        "category": "logistics",
    },
    {
        "content": "【催发货】预售商品因库存有限，催发货可能无法生效，具体发货时间以商品页标注为准。",
        "source": "催发货.md",
        "category": "logistics",
    },
    {
        "content": "【催发货】节假日（如双11、618）期间订单量大，催发货处理可能较慢。",
        "source": "催发货.md",
        "category": "logistics",
    },
    {
        "content": "【催发货】如订单超过7天未发货，可申请全额退款。",
        "source": "催发货.md",
        "category": "logistics",
    },

    # 改地址
    {
        "content": "【改地址】订单在「待发货」状态下可自助修改收货地址。",
        "source": "地址修改.md",
        "category": "logistics",
    },
    {
        "content": "【改地址】订单一旦发货，不再支持地址修改。",
        "source": "地址修改.md",
        "category": "logistics",
    },
    {
        "content": "【改地址】已发货的订单如需更改地址，可联系客服申请拦截，拦截成功后可重新下单。",
        "source": "地址修改.md",
        "category": "logistics",
    },
    {
        "content": "【改地址】拦截可能产生额外费用（10-20元），具体以快递公司实际收费为准。",
        "source": "地址修改.md",
        "category": "logistics",
    },

    # 退换货与物流
    {
        "content": "【退换物流】退货时需将商品寄回指定仓库地址，运费由责任方承担（质量问题我们承担运费）。",
        "source": "退换物流.md",
        "category": "logistics",
    },
    {
        "content": "【退换物流】换货时我们会先发出新商品，同时发送退货包裹，收货后完成换货。",
        "source": "退换物流.md",
        "category": "logistics",
    },
    {
        "content": "【退换物流】跨境购商品退货需退回国内仓库，运费较高，建议谨慎购买。",
        "source": "退换物流.md",
        "category": "logistics",
    },
    {
        "content": "【退换物流】生鲜商品一旦发货不支持退货，如有质量问题可联系客服处理。",
        "source": "退换物流.md",
        "category": "logistics",
    },
    {
        "content": "【退换物流】定制商品（如刻字、定制尺寸）不支持7天无理由退货。",
        "source": "退换物流.md",
        "category": "logistics",
    },

    # 赔付政策
    {
        "content": "【赔付政策】商品在运输过程中丢失，凭快递公司证明可申请全额退款。",
        "source": "赔付政策.md",
        "category": "logistics",
    },
    {
        "content": "【赔付政策】商品在运输过程中损坏（如包装完好但商品破损），需提供照片证据。",
        "source": "赔付政策.md",
        "category": "logistics",
    },
    {
        "content": "【赔付政策】赔付金额以商品实际支付金额为准，不超过商品原价。",
        "source": "赔付政策.md",
        "category": "logistics",
    },
    {
        "content": "【赔付政策】如商品降价促销，不接受价格保护申请。",
        "source": "赔付政策.md",
        "category": "logistics",
    },
    {
        "content": "【赔付政策】因不可抗力（自然灾害、疫情等）导致的配送延误，不在我司赔付范围内。",
        "source": "赔付政策.md",
        "category": "logistics",
    },

    # 特殊商品物流
    {
        "content": "【特殊商品】生鲜商品采用冷链配送，确保新鲜度。收到后请尽快冷藏保存。",
        "source": "特殊商品.md",
        "category": "logistics",
    },
    {
        "content": "【特殊商品】易碎商品（如玻璃、陶瓷）会加强包装，但仍可能在运输中损坏，建议当面签收。",
        "source": "特殊商品.md",
        "category": "logistics",
    },
    {
        "content": "【特殊商品】液体商品（如化妆品、饮料）因航空限制可能走陆运，时效较长。",
        "source": "特殊商品.md",
        "category": "logistics",
    },
    {
        "content": "【特殊商品】电池、含电池商品（如手机、笔记本）需走特殊通道，可能延迟1-2天发货。",
        "source": "特殊商品.md",
        "category": "logistics",
    },
    {
        "content": "【特殊商品】家具、家电等大件商品由专业物流配送，需预约安装时间。",
        "source": "特殊商品.md",
        "category": "logistics",
    },

    # 自提服务
    {
        "content": "【自提服务】部分商品支持自提，自提点分布在上海、北京、广州、深圳等城市。",
        "source": "自提服务.md",
        "category": "logistics",
    },
    {
        "content": "【自提服务】自提商品需在收到取货码后7天内提取，逾期将退回仓库。",
        "source": "自提服务.md",
        "category": "logistics",
    },
    {
        "content": "【自提服务】自提无需支付运费，部分商品自提可享受额外优惠。",
        "source": "自提服务.md",
        "category": "logistics",
    },
    {
        "content": "【自提服务】取货时请携带有效身份证件，并提供取货码。",
        "source": "自提服务.md",
        "category": "logistics",
    },
]


def main():
    print("Loading existing LongTermMemory...")
    mem = LongTermMemory(index_path="./vector_store/faiss_index")
    print(f"Current documents: {len(mem._documents)}")

    print(f"\nAdding {len(LOGISTICS_KNOWLEDGE)} logistics knowledge documents...")
    for doc in LOGISTICS_KNOWLEDGE:
        mem.add_document(
            content=doc["content"],
            source=doc["source"],
            metadata={"category": doc["category"]},
        )

    print(f"Total documents after add: {len(mem._documents)}")

    print("\nSaving to FAISS index...")
    mem.save()
    print("Done!")

    print("\nTest search:")
    results = mem.search_hybrid("快递", top_k=3)
    for r in results:
        print(f"  [{r['metadata']['category']}] score={r['score']:.4f} | {r['content'][:50]}...")

    results = mem.search_hybrid("催发货", top_k=3)
    for r in results:
        print(f"  [{r['metadata']['category']}] score={r['score']:.4f} | {r['content'][:50]}...")


if __name__ == "__main__":
    main()