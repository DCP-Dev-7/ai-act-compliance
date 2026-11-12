from app.engine import classify


def base(**kw):
    f = {"provider_type": "external_api", "is_generative": False, "user_type": "B2C", "domain": "none"}
    f.update(kw)
    return f


def test_operator_role_developer_vs_deployer():
    assert classify(base(provider_type="self_developed"))["operator_role"] == "developer"
    assert classify(base(provider_type="external_api"))["operator_role"] == "deployer"
    r = classify(base(provider_type="unknown"))
    assert r["operator_role"] == "deployer" and r["assumptions"]


def test_generative_b2c_gets_notice_and_labeling():
    r = classify(base(is_generative=True, output_types=["image"]))
    assert r["art31"] == {"applicable": True, "prior_notice": True, "output_labeling": True,
                          "deepfake_notice": False, "internal_exemption": False}
    assert {"art31-1", "art31-2", "art2-generative"} <= set(r["applicable_articles"])
    assert r["high_impact"]["status"] == "not_applicable"


def test_deepfake_requires_clear_notice():
    r = classify(base(is_generative=True, output_types=["video"], realistic_synthetic=True))
    assert r["art31"]["deepfake_notice"] is True and "art31-3" in r["applicable_articles"]


def test_internal_use_is_exempt():
    r = classify(base(is_generative=True, user_type="internal", output_types=["text"]))
    assert r["art31"]["internal_exemption"] is True
    assert not r["art31"]["prior_notice"] and not r["art31"]["output_labeling"]
    assert "art31-exception" in r["applicable_articles"]


def test_internal_but_high_impact_is_not_exempt():
    r = classify(base(user_type="internal", domain="hiring", significant_impact=True, human_review="none"))
    assert r["art31"]["internal_exemption"] is False and r["art31"]["prior_notice"] is True


def test_high_impact_two_stage():
    assert classify(base(domain="none"))["high_impact"]["status"] == "not_applicable"
    assert classify(base(domain="lending", significant_impact=False))["high_impact"]["status"] == "not_applicable"
    r = classify(base(domain="lending", significant_impact=True, human_review="none"))
    assert r["high_impact"]["status"] == "candidate" and r["art34_applicable"] and r["art35_applicable"]
    assert not r["art33_recommended"]
    assert {"art34", "art35"} <= set(r["applicable_articles"])


def test_substantive_human_review_is_flagged_as_issue():
    r = classify(base(domain="hiring", significant_impact=True, human_review="substantive"))
    assert r["high_impact"]["status"] == "excluded_possible"
    assert r["high_impact"]["issue"] and "쟁점" in r["high_impact"]["issue_note"]
    assert r["art33_recommended"] and not r["art34_applicable"]


def test_formal_review_stays_candidate_with_issue():
    r = classify(base(domain="hiring", significant_impact=True, human_review="formal"))
    assert r["high_impact"]["status"] == "candidate" and r["high_impact"]["issue"] and r["art33_recommended"]


def test_unknown_significance_recommends_confirmation():
    r = classify(base(domain="nuclear", significant_impact=None))
    assert r["high_impact"]["status"] == "candidate" and r["art33_recommended"] and r["assumptions"]


def test_art32_art36_deemed():
    assert classify(base(cumulative_flops=1e26))["art32_applicable"]
    assert not classify(base(cumulative_flops=9e25))["art32_applicable"]
    assert classify(base(foreign_operator=True))["art36_applicable"]
    r = classify(base(domain="medical", significant_impact=True, other_law_compliance="디지털의료제품법"))
    assert r["deemed_compliance_possible"] and "deemed" in r["applicable_articles"]


def test_every_rationale_links_to_known_articles():
    from app.kb import file_clauses_v1

    clauses = file_clauses_v1()
    for facts in [base(is_generative=True, realistic_synthetic=True, output_types=["audio"]),
                  base(domain="medical", significant_impact=True, human_review="formal", cumulative_flops=2e26,
                       foreign_operator=True, other_law_compliance="디지털의료제품법"),
                  base(user_type="internal", is_generative=True)]:
        r = classify(facts)
        assert r["rationale"]
        for item in r["rationale"]:
            assert item["articles"], item
            assert all(a in clauses for a in item["articles"]), item
