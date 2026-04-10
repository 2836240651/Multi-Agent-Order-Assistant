from __future__ import annotations

import json
import random
from pathlib import Path
from memory.long_term import LongTermMemory

CATEGORIES = {
    "refund": {
        "name": "退款退货",
        "templates": [
            "【{category}】{condition}，{action}。{note}",
            "【{category}】{scenario}时，{rule}。{time_limit}",
            "【{category}】关于{category}的常见问题：{qa}",
        ],
        "conditions": [
            "已发货但未签收的商品，支持全额退款",
            "已签收的商品，在签收后7天内可申请退货",
            "定制商品、生鲜食品、内衣裤等特殊性商品不支持7天无理由退货",
            "退款将在收到退货并确认后3-5个工作日内原路返回",
            "使用优惠券的订单，优惠金额不返还",
            "订单取消后金额将在1小时内原路退回",
            "退货时需保持商品完好、配件齐全",
            "跨境购商品退货政策另行规定",
            "秒杀商品不支持退货",
            "限时折扣商品一旦购买不支持价格保护",
        ],
        "scenarios": [
            "申请退款",
            "取消订单后想重新购买",
            "重复支付",
            "商品与描述不符",
            "未收到货",
            "商品损坏",
            "发错货",
            "漏发货",
        ],
        "rules": [
            "退款金额为实际支付金额",
            "运费险覆盖范围内可获得运费赔付",
            "超出政策期限的退款申请不予受理",
            "退款优先级：原路退回 > 账户余额",
            "分期付款订单退款将退还至原支付渠道",
        ],
        "time_limits": [
            "请在签收后7天内申请",
            "处理周期为1-3个工作日",
            "逾期将无法处理",
            "请第一时间联系客服",
        ],
        "qas": [
            "退款多久到账？一般3-5个工作日。",
            "退款退到哪？原支付渠道。",
            "退货需要运费吗？质量问题我们承担。",
        ],
    },
    "shipping": {
        "name": "物流配送",
        "conditions": [
            "同城配送1-2天，省内2-3天，省外3-5天",
            "偏远地区5-7天",
            "如配送超期超过承诺时间5天以上，可申请全额退款",
            "大件商品需提前预约安装时间",
            "生鲜商品采用冷链配送",
            "同一订单包含多种商品可能分批发货",
            "节假日期间配送可能有所延迟",
            "天气原因等不可抗力会影响配送时效",
        ],
        "scenarios": [
            "查询物流",
            "催发货",
            "改地址",
            "拒收",
            "自提",
            "他人代收",
        ],
        "rules": [
            "物流信息更新可能有延迟",
            "签收前请检查外包装",
            "签收后发现问题需在24小时内反馈",
            "部分商品需实名认证",
        ],
        "time_limits": [
            "请在预计时间3天后仍未收到时联系我们",
            "超过7天未收到可申请退款",
        ],
        "qas": [
            "怎么查物流？订单详情页有快递单号。",
            "可以指定时间吗？暂不支持指定时间。",
        ],
    },
    "payment": {
        "name": "支付问题",
        "conditions": [
            "支付失败常见原因：银行卡限额、余额不足、网络超时",
            "支持支付宝、微信支付、银行卡、信用卡",
            "使用优惠券后申请退款，优惠金额不返还",
            "分期付款会产生手续费",
            "余额支付可享受额外优惠",
        ],
        "scenarios": [
            "支付失败",
            "重复扣款",
            "优惠没生效",
            "无法使用优惠券",
            "转账失败",
            "货到付款",
        ],
        "rules": [
            "每笔订单仅限使用一张优惠券",
            "优惠券不可叠加使用",
            "余额不可提现",
        ],
        "time_limits": [
            "重复扣款会在1-3个工作日内退回",
        ],
        "qas": [
            "为什么支付失败？请检查银行卡限额。",
            "优惠券怎么用？结算时自动抵扣。",
        ],
    },
    "invoice": {
        "name": "发票问题",
        "conditions": [
            "电子发票：在订单完成后可在订单详情中下载，有效期为1年",
            "纸质发票：需在确认收货后15天内联系客服申请",
            "发票内容默认为商品明细",
            "增值税专用发票需提供企业资质",
            "发票一旦开具不支持更换",
        ],
        "scenarios": [
            "申请发票",
            "换发票",
            "发票丢失",
            "普票换专票",
            "补开发票",
        ],
        "rules": [
            "发票金额以实际支付金额为准",
            "电子发票与纸质发票具有同等效力",
            "发票抬头可选择个人或单位",
        ],
        "time_limits": [
            "请在确认收货后15天内申请",
        ],
        "qas": [
            "怎么开电子发票？订单完成后下载。",
            "专票怎么开？联系客服提供资质。",
        ],
    },
    "coupon": {
        "name": "优惠券",
        "conditions": [
            "优惠券有效期为领取后30天内",
            "每个订单仅限使用一张优惠券",
            "优惠券不可叠加使用",
            "优惠券一经使用，若订单取消，优惠券不予返还",
            "部分商品不可使用优惠券",
            "新人专享券仅限首次下单用户",
        ],
        "scenarios": [
            "领优惠券",
            "优惠券无法使用",
            "优惠券过期",
            "优惠券叠加",
            "退款后优惠券",
        ],
        "rules": [
            "优惠券需在有效期内使用",
            "优惠券不可折算现金",
            "退款订单优惠券不予返还",
        ],
        "time_limits": [
            "过期后不可延期",
        ],
        "qas": [
            "优惠券怎么领？活动页领取。",
            "为什么用不了？检查商品是否在限定范围内。",
        ],
    },
    "membership": {
        "name": "会员权益",
        "conditions": [
            "会员等级分为：普通、银牌、金牌、钻石",
            "银牌会员享受全场95折",
            "金牌会员享受9折",
            "钻石会员享受85折",
            "会员生日当月可领取专属生日礼包",
            "高等级会员可享受专属客服",
        ],
        "scenarios": [
            "升级会员",
            "会员权益",
            "生日礼包",
            "会员日活动",
            "专属优惠",
        ],
        "rules": [
            "等级根据累计消费金额计算",
            "等级每月更新一次",
            "会员权益不可转让",
        ],
        "time_limits": [
            "生日礼包请在生日当月领取",
        ],
        "qas": [
            "怎么升级？累计消费达标自动升级。",
            "生日礼包有什么？优惠券和双倍积分。",
        ],
    },
    "points": {
        "name": "积分规则",
        "conditions": [
            "每消费1元累积1积分",
            "积分可在下次购物时抵扣（100积分=1元）",
            "积分有效期为获得后12个月",
            "退货订单的积分将从账户中扣除",
        ],
        "scenarios": [
            "积分查询",
            "积分兑换",
            "积分扣除",
            "积分过期",
            "积分转赠",
        ],
        "rules": [
            "积分不可折算现金",
            "积分兑换商品不支持退货",
            "账户积分不足时会从退款中扣除",
        ],
        "time_limits": [
            "积分过期前会发送提醒",
        ],
        "qas": [
            "积分怎么用？结算时抵扣。",
            "积分会过期吗？获得后12个月。",
        ],
    },
    "product": {
        "name": "商品咨询",
        "conditions": [
            "商品详情页标注正品保障表示为官方渠道正品",
            "商品价格随市场波动",
            "商品库存显示售罄时可点击到货提醒",
            "商品图片仅供参考，以实物为准",
            "部分商品因批次不同会有细微差异",
        ],
        "scenarios": [
            "商品真伪",
            "价格变动",
            "库存查询",
            "到货通知",
            "规格参数",
            "颜色差异",
        ],
        "rules": [
            "以下单时价格为准",
            "不支持事后价格保护申请",
        ],
        "time_limits": [
            "到货提醒我们会在第一时间通知您",
        ],
        "qas": [
            "是正品吗？官方渠道正品保障。",
            "什么时候到货？查看商品页预计到货时间。",
        ],
    },
    "service": {
        "name": "售后服务",
        "conditions": [
            "电器类商品享有一年官方保修",
            "保修期内非人为损坏可免费维修",
            "人为损坏或过保需付费维修",
            "维修周期一般为7-15个工作日",
            "全国联保可就近选择维修点",
        ],
        "scenarios": [
            "申请保修",
            "维修进度",
            "延保服务",
            "换货申请",
            "维修费用",
        ],
        "rules": [
            "需提供购买凭证",
            "人为损坏不在保修范围",
            "进水、摔伤不在保修范围",
        ],
        "time_limits": [
            "请在保修期内及时申请",
        ],
        "qas": [
            "保修需要什么？购买凭证和保修卡。",
            "维修要多久？7-15个工作日。",
        ],
    },
    "account": {
        "name": "账户安全",
        "conditions": [
            "建议设置支付密码、开启手机验证",
            "发现账户异常登录请立即修改密码并联系客服",
            "一个账户最多绑定5台常用设备",
            "密码连续错误5次将被锁定",
        ],
        "scenarios": [
            "修改密码",
            "绑定手机",
            "设备管理",
            "账户被盗",
            "解锁账户",
        ],
        "rules": [
            "密码需包含字母和数字",
            "手机号用于接收验证码",
        ],
        "time_limits": [
            "密码连续错误5次锁定30分钟",
        ],
        "qas": [
            "密码忘了？通过手机验证码重置。",
            "怎么绑定手机？账户设置里操作。",
        ],
    },
    "cancel": {
        "name": "取消订单",
        "conditions": [
            "未发货订单可自助取消",
            "已发货订单不支持取消",
            "取消后金额将在1小时内原路退回",
            "使用优惠券的订单取消后优惠金额不返还",
        ],
        "scenarios": [
            "取消未发货",
            "取消已发货",
            "取消后退款",
            "取消后重拍",
        ],
        "rules": [
            "发货后只能拒收",
            "预售订单需支付尾款后才能取消",
        ],
        "time_limits": [
            "请在发货前尽快申请取消",
        ],
        "qas": [
            "怎么取消？订单详情页自助取消。",
            "已发货怎么办？收到后申请退货。",
        ],
    },
    "quality": {
        "name": "质量问题",
        "conditions": [
            "商品存在质量问题可申请退换货",
            "需提供照片或视频证据",
            "质量问题退货运费由我们承担",
            "部分地区可上门取件",
        ],
        "scenarios": [
            "商品破损",
            "功能故障",
            "描述不符",
            "假货投诉",
        ],
        "rules": [
            "需在收货后24小时内反馈",
            "保留原包装",
            "配件需齐全",
        ],
        "time_limits": [
            "超过7天将无法处理质量问题",
        ],
        "qas": [
            "坏了怎么办？申请售后或联系客服。",
            "怎么证明是质量问题？提供照片或视频。",
        ],
    },
}


def generate_documents(target_count: int = 500) -> list[dict]:
    documents = []
    category_list = list(CATEGORIES.items())

    while len(documents) < target_count:
        for category_key, category_data in category_list:
            if len(documents) >= target_count:
                break

            templates = category_data.get("templates", ["【{category}】{condition}"])
            conditions = category_data.get("conditions", ["默认条件"])
            scenarios = category_data.get("scenarios", ["默认场景"])
            rules = category_data.get("rules", ["默认规则"])
            time_limits = category_data.get("time_limits", ["请及时处理"])
            qas = category_data.get("qas", ["请联系我们"])

            template = random.choice(templates)
            template_vars = {
                "category": category_data["name"],
                "condition": random.choice(conditions),
                "action": random.choice(["支持全额退款", "不支持退款", "可申请退货"]) if "退款" in category_key else "",
                "note": random.choice(time_limits),
                "scenario": random.choice(scenarios),
                "rule": random.choice(rules),
                "time_limit": random.choice(time_limits),
                "qa": random.choice(qas),
            }

            content = template.format(**template_vars)

            documents.append({
                "content": content,
                "source": f"{category_key}_policy.md",
                "category": category_key,
            })

            if len(documents) >= target_count:
                break

    return documents


def main():
    target_count = 500
    print(f"Generating {target_count} knowledge base documents...")

    documents = generate_documents(target_count)
    print(f"Generated {len(documents)} documents")

    kb_path = Path("./vector_store/knowledge_base.json")
    kb_path.parent.mkdir(parents=True, exist_ok=True)

    mem = LongTermMemory(index_path="./vector_store/faiss_index")

    existing_sources = set()
    for doc in documents:
        source = doc["source"]
        if source not in existing_sources:
            existing_sources.add(source)

    print(f"Adding documents to FAISS index (this may take a few minutes)...")
    for i, doc in enumerate(documents):
        mem.add_document(
            content=doc["content"],
            source=doc["source"],
            metadata={"category": doc["category"]},
        )
        if (i + 1) % 50 == 0:
            print(f"  Progress: {i + 1}/{len(documents)}")

    mem.save()
    print(f"Knowledge base saved to {kb_path}")
    print(f"FAISS index saved to ./vector_store/faiss_index")

    results = mem.search("退款", top_k=3)
    print(f"\nTest search '退款': {len(results)} results")
    for r in results:
        print(f"  score={r['score']:.4f} | {r['content'][:60]}...")

    results = mem.search("物流查询", top_k=3)
    print(f"\nTest search '物流查询': {len(results)} results")
    for r in results:
        print(f"  score={r['score']:.4f} | {r['content'][:60]}...")


if __name__ == "__main__":
    main()