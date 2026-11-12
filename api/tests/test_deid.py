from app.deid import Deidentifier

TEXT = ("담당자 김가상, 주민등록번호 900101-1234567, 휴대전화 010-1234-5678, 사무실 02-345-6789, "
        "이메일 kim.test@example.co.kr, 카드 1234-5678-9012-3456, 계좌 110-234-567890 (가상은행), "
        "사업자등록번호 123-45-67890.")


def test_masks_all_korean_pii_patterns():
    d = Deidentifier().deidentify(TEXT)
    for raw in ["900101-1234567", "010-1234-5678", "02-345-6789", "kim.test@example.co.kr",
                "1234-5678-9012-3456", "110-234-567890", "123-45-67890"]:
        assert raw not in d.text, raw
    for label in ["주민등록번호", "휴대전화", "전화번호", "이메일", "카드번호", "계좌번호", "사업자등록번호"]:
        assert d.counts.get(label, 0) >= 1, (label, d.text)
        assert f"[{label}_1]" in d.text


def test_reversible_mapping():
    dz = Deidentifier()
    d = dz.deidentify(TEXT)
    assert dz.restore(d.text, d.mapping) == TEXT


def test_same_value_same_token_and_shared_mapping():
    dz = Deidentifier()
    d1 = dz.deidentify("연락처 010-1234-5678")
    d2 = dz.deidentify("다시 010-1234-5678 그리고 010-9999-0000", d1.mapping)
    assert "[휴대전화_1]" in d2.text and "[휴대전화_2]" in d2.text


def test_non_pii_untouched():
    t = "인공지능기본법 제31조는 2026-01-22 시행. 10^26 FLOPs, 직원 40명, 3천만원."
    assert Deidentifier().deidentify(t).text == t


def test_compact_formats():
    d = Deidentifier().deidentify("주민번호 9001011234567 휴대폰 01012345678")
    assert "9001011234567" not in d.text and "01012345678" not in d.text
