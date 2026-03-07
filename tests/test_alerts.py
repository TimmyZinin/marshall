"""Tests for alert engine."""
import pytest
from pathlib import Path
from src.alerts.engine import AlertEngine, ISSUE_KEYWORDS


def test_alert_rules_load():
    """Test that YAML rules load correctly."""
    rules_path = str(Path(__file__).parent.parent / "config" / "alert_rules.yaml")
    engine = AlertEngine(rules_path)
    assert len(engine._customers) == 6
    assert "Тандер" in engine._customers
    assert "WB" in engine._customers
    assert "X5" in engine._customers
    assert "Магнит" in engine._customers
    assert "Сельта" in engine._customers
    assert "Сибур" in engine._customers


def test_customer_rules_have_all_types():
    """Each customer should have rules for all 5 alert types."""
    rules_path = str(Path(__file__).parent.parent / "config" / "alert_rules.yaml")
    engine = AlertEngine(rules_path)
    expected_types = {"delay", "equipment_failure", "docs_missing", "safety_violation", "downtime"}
    for customer, rules in engine._customers.items():
        assert expected_types.issubset(set(rules.keys())), f"{customer} missing: {expected_types - set(rules.keys())}"


def test_wb_delay_severity_is_high():
    """WB has 100% fine for delay, should be high severity."""
    rules_path = str(Path(__file__).parent.parent / "config" / "alert_rules.yaml")
    engine = AlertEngine(rules_path)
    assert engine._customers["WB"]["delay"]["severity"] == "high"
    assert "100%" in engine._customers["WB"]["delay"]["fine_text"]


def test_issue_keywords_coverage():
    """All 5 alert types should have keywords defined."""
    assert "delay" in ISSUE_KEYWORDS
    assert "equipment_failure" in ISSUE_KEYWORDS
    assert "downtime" in ISSUE_KEYWORDS
    assert "safety_violation" in ISSUE_KEYWORDS
    assert "docs_missing" in ISSUE_KEYWORDS


def test_keyword_detection_delay():
    """Delay keywords should match common dispatcher phrases."""
    keywords = ISSUE_KEYWORDS["delay"]
    assert any(kw in "опоздание на 40 минут" for kw in keywords)
    assert any(kw in "стою в пробке" for kw in keywords)


def test_keyword_detection_equipment():
    """Equipment failure keywords should match reefer issues."""
    keywords = ISSUE_KEYWORDS["equipment_failure"]
    assert any(kw in "реф не выходит на температуру" for kw in keywords)
    assert any(kw in "компрессор отключился" for kw in keywords)


def test_keyword_detection_docs():
    """Docs missing keywords should match document issues."""
    keywords = ISSUE_KEYWORDS["docs_missing"]
    assert any(kw in "забыл термограмму" for kw in keywords)
    assert any(kw in "нет накладной ттн" for kw in keywords)
