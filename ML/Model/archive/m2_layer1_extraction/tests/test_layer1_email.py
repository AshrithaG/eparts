"""Layer 1 email extraction tests (V1 spec §4.1)."""
from __future__ import annotations

from src.contracts import SourceType
from src.layer1_extraction import extract_from_email


def _build_email(subject: str, sender: str, body: str) -> str:
    return (
        f"From: {sender}\r\n"
        f"To: orders@eparts.test\r\n"
        f"Subject: {subject}\r\n"
        f"MIME-Version: 1.0\r\n"
        f"Content-Type: text/plain; charset=us-ascii\r\n"
        f"\r\n"
        f"{body}"
    )


def test_email_extracts_subject_and_body(aliases):
    raw = _build_email(
        subject="Need pricing on T-6000",
        sender="buyer@customer.test",
        body="Hello,\n\nLooking for a 24 VAC thermistor, Johnson Controls T-6000.\n",
    )
    result = extract_from_email(raw, aliases=aliases, source_ref="msg:42")
    assert result.source_type == SourceType.EMAIL
    assert "Need pricing on T-6000" in result.text
    assert "thermistor" in result.text
    assert result.structured_fields["sender"] == "buyer@customer.test"
    assert result.normalized_units == {"value_unit_0": ("24", "vac")}
    assert result.source_ref == "msg:42"


def test_email_strips_simple_signature(aliases):
    body = (
        "Need a quote on a 12 VDC pump.\n"
        "\n"
        "--\n"
        "Jane Buyer, ACME Corp\n"
        "555-1234\n"
    )
    raw = _build_email("Quote", "jane@acme.test", body)
    result = extract_from_email(raw, aliases=aliases)
    assert "Jane Buyer" not in result.text
    assert "555-1234" not in result.text
    assert "12 VDC pump" in result.text


def test_email_strips_reply_chain(aliases):
    body = (
        "Following up on the 24 VAC actuator.\n"
        "\n"
        "On Mon, Jan 5, 2026 at 10:00 AM, Sales <sales@eparts.test> wrote:\n"
        "> Please confirm voltage.\n"
        "> Thanks.\n"
    )
    raw = _build_email("Re: Actuator", "buyer@cust.test", body)
    result = extract_from_email(raw, aliases=aliases)
    assert "Please confirm voltage" not in result.text
    assert "actuator" in result.text


def test_email_strips_mobile_signature(aliases):
    body = "I need a 70 deg F thermostat.\n\nSent from my iPhone\n"
    raw = _build_email("Thermostat", "field@cust.test", body)
    result = extract_from_email(raw, aliases=aliases)
    assert "iPhone" not in result.text
    assert "thermostat" in result.text.lower()


def test_email_missing_body_yields_subject_only(aliases):
    raw = _build_email("Question", "x@y.test", "")
    result = extract_from_email(raw, aliases=aliases)
    assert result.text.strip() == "Question"
