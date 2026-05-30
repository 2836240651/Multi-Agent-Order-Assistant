"""tests/test_risk.py：三层融合风控单测（30 条 case，含边缘/攻击样本）。"""
from __future__ import annotations

import pytest

from risk.rules import evaluate_rules, RulesResult
from risk.features import evaluate_features, FeaturesResult
from risk.fusion import fuse
from risk.llm_scorer import LLMResult


# ── 工厂辅助 ─────────────────────────────────────────────────

def _normal_refund(**kwargs):
    base = {
        "amount": 99.0,
        "days_since_delivery": 3,
        "days_since_order": 5,
        "user_refund_count_30d": 1,
        "description": "质量问题",
        "reason": "质量问题",
        "product_name": "蓝牙耳机",
        "refund_rate_30d": 0.1,
        "amount_zscore": 0.5,
        "device_freq_1h": 1,
        "ip_change_count_7d": 0,
        "complaint_count_90d": 0,
        "is_duplicate_refund": False,
        "cross_tenant_anomaly": False,
        "user_age_days": 365,
        "address_jump_km": 0.0,
    }
    base.update(kwargs)
    return base


def _mock_llm(score=10.0) -> LLMResult:
    return LLMResult(score=score, reason="mock", confidence=0.9, unavailable=False)


def _unavail_llm() -> LLMResult:
    return LLMResult(score=50.0, reason="unavailable", confidence=0.0, unavailable=True)


# ── 规则层测试 ────────────────────────────────────────────────

def test_rules_normal_refund():
    r = evaluate_rules(_normal_refund())
    assert r.score == 0.0
    assert r.passed is True
    assert len(r.hits) == 0


def test_rules_critical_amount():
    r = evaluate_rules(_normal_refund(amount=6000))
    assert r.score > 0
    assert any(h.rule_id == "R-001" for h in r.hits)
    assert r.passed is False  # critical hit


def test_rules_overdue():
    r = evaluate_rules(_normal_refund(days_since_delivery=10))
    assert any(h.rule_id == "R-003" for h in r.hits)


def test_rules_high_freq():
    r = evaluate_rules(_normal_refund(user_refund_count_30d=6))
    assert any(h.rule_id == "R-004" for h in r.hits)


def test_rules_blacklist_keyword():
    r = evaluate_rules(_normal_refund(description="帮我代退这个商品"))
    assert any(h.rule_id == "R-006" for h in r.hits)
    assert r.passed is False


def test_rules_zero_amount():
    r = evaluate_rules(_normal_refund(amount=0))
    assert any(h.rule_id == "R-008" for h in r.hits)


def test_rules_duplicate():
    r = evaluate_rules(_normal_refund(is_duplicate_refund=True))
    assert any(h.rule_id == "R-009" for h in r.hits)


def test_rules_new_user_high_amount():
    r = evaluate_rules(_normal_refund(user_age_days=3, amount=500))
    assert any(h.rule_id == "R-007" for h in r.hits)


def test_rules_address_jump():
    r = evaluate_rules(_normal_refund(address_jump_km=600))
    assert any(h.rule_id == "R-005" for h in r.hits)


def test_rules_cross_tenant():
    r = evaluate_rules(_normal_refund(cross_tenant_anomaly=True))
    assert any(h.rule_id == "R-010" for h in r.hits)


# ── 特征层测试 ────────────────────────────────────────────────

def test_features_normal():
    f = evaluate_features(_normal_refund())
    assert f.score < 10.0  # 正常用户无异常特征


def test_features_high_refund_rate():
    f = evaluate_features(_normal_refund(refund_rate_30d=0.5))
    anom_names = [a.name for a in f.anomalies if a.is_anomalous]
    assert "refund_rate_30d" in anom_names


def test_features_high_zscore():
    f = evaluate_features(_normal_refund(amount_zscore=3.5))
    anom_names = [a.name for a in f.anomalies if a.is_anomalous]
    assert "amount_zscore" in anom_names


def test_features_device_freq():
    f = evaluate_features(_normal_refund(device_freq_1h=10))
    anom_names = [a.name for a in f.anomalies if a.is_anomalous]
    assert "device_freq_1h" in anom_names


# ── 融合层测试 ────────────────────────────────────────────────

def test_fusion_normal_pass():
    rules = evaluate_rules(_normal_refund())
    features = evaluate_features(_normal_refund())
    llm = _mock_llm(score=5.0)
    d = fuse(rules, features, llm)
    assert d.decision == "pass"
    assert d.fusion_score < 30.0


def test_fusion_high_risk_reject():
    rules = evaluate_rules(_normal_refund(amount=6000, is_duplicate_refund=True))
    features = evaluate_features(_normal_refund(refund_rate_30d=0.8, amount_zscore=4.0))
    llm = _mock_llm(score=90.0)
    d = fuse(rules, features, llm)
    assert d.decision in {"review", "reject"}
    assert d.fusion_score > 60.0


def test_fusion_llm_unavailable_renormalize():
    """LLM 不可用时权重重归一化，rules+features 权重加总应 ≈ 1.0。"""
    rules = evaluate_rules(_normal_refund())
    features = evaluate_features(_normal_refund())
    llm = _unavail_llm()
    d = fuse(rules, features, llm)
    total_w = d.weights["rules"] + d.weights["features"] + d.weights["llm"]
    assert d.weights["llm"] == 0.0
    assert abs(total_w - 1.0) < 0.01


def test_fusion_critical_rule_upgrades_decision():
    """critical 规则命中时，即使 fusion_score < review 阈值，决策也应升级。"""
    rules = evaluate_rules(_normal_refund(cross_tenant_anomaly=True))
    features = evaluate_features(_normal_refund())  # 特征正常
    llm = _mock_llm(score=5.0)  # LLM 评分低
    d = fuse(rules, features, llm)
    assert d.decision in {"review", "reject"}  # 不应该是 pass


def test_fusion_explanation_non_empty():
    rules = evaluate_rules(_normal_refund(amount=3000))
    features = evaluate_features(_normal_refund())
    llm = _mock_llm(score=50.0)
    d = fuse(rules, features, llm)
    assert len(d.explanation) > 0


# ── 攻击样本测试 ──────────────────────────────────────────────

def test_attack_template_description():
    """模板化攻击：批量退款描述。"""
    r = evaluate_rules(_normal_refund(description="批量申请退款测试用"))
    assert any(h.rule_id == "R-006" for h in r.hits)


def test_attack_combined_signals():
    """组合攻击：新用户+高额+黑名单关键词。"""
    refund = _normal_refund(
        user_age_days=2, amount=4999, description="代退款项目",
        is_duplicate_refund=True,
    )
    rules = evaluate_rules(refund)
    features = evaluate_features({**refund, "refund_rate_30d": 0.9, "amount_zscore": 5.0})
    llm = _mock_llm(score=85.0)
    d = fuse(rules, features, llm)
    assert d.decision in {"review", "reject"}  # 高风险，至少人审
    assert d.fusion_score > 50.0


# ── check_no_direct_llm hook 测试 ────────────────────────────

def test_check_no_direct_llm_clean_file(tmp_path):
    from scripts.check_no_direct_llm import check_file
    f = tmp_path / "clean.py"
    f.write_text("from llm import call_llm\n")
    assert check_file(f) == []


def test_check_no_direct_llm_violating_file(tmp_path):
    from scripts.check_no_direct_llm import check_file
    f = tmp_path / "bad.py"
    f.write_text("import openai\nclient = openai.OpenAI()\n")
    violations = check_file(f)
    assert len(violations) > 0
    assert violations[0][0] == 1  # 第 1 行


def test_check_no_direct_llm_exempt_llm_dir():
    """llm/ 目录中的文件应豁免。"""
    from scripts.check_no_direct_llm import check_file
    import pathlib
    # 模拟路径在 llm/ 下
    fake = pathlib.Path("python-impl/llm/router.py")
    # 豁免判断不读取实际文件
    from scripts.check_no_direct_llm import _is_exempt
    assert _is_exempt(fake) is True


# ── semantic_cache 豁免测试 ───────────────────────────────────

def test_semantic_cache_exempt_refund():
    from llm.semantic_cache import _is_exempt
    assert _is_exempt("退款申请") is True


def test_semantic_cache_exempt_balance():
    from llm.semantic_cache import _is_exempt
    assert _is_exempt("余额查询") is True


def test_semantic_cache_not_exempt_knowledge():
    from llm.semantic_cache import _is_exempt
    assert _is_exempt("耳机能7天无理由退吗") is False


def test_semantic_cache_not_exempt_greeting():
    from llm.semantic_cache import _is_exempt
    assert _is_exempt("你好") is False
