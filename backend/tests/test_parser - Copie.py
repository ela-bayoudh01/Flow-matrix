from datetime import datetime

import pytest

from app.parser import LogParsingError, parse_line

from .sample_logs import ALLOW_HTTPS_LINE, BLOCK_SMB_LINE, ICMP_BLOCK_LINE


def test_parses_allow_https_line_into_structured_fields():
    parsed = parse_line(ALLOW_HTTPS_LINE)

    assert parsed["src_ip"] == "10.10.1.32"
    assert parsed["dst_ip"] == "203.0.113.10"
    assert parsed["dst_port"] == 443
    assert parsed["protocol"] == "tcp"
    assert parsed["access_control_rule_action"] == "Allow"
    assert parsed["access_control_rule_name"] == "ACL_ANY_INTERNET_HTTPS_OUT"
    assert parsed["ingress_zone"] == "Users_Zone"
    assert parsed["egress_zone"] == "Internet_Zone"
    assert parsed["application_protocol"] == "HTTPS"
    assert parsed["web_application"] == "Kaspersky"
    assert parsed["connection_duration"] == 610
    assert parsed["initiator_bytes"] == 1423
    assert parsed["responder_bytes"] == 9856
    assert parsed["device_uuid"] == "00000000-0000-4000-a000-000000000001"
    assert parsed["firewall_device_ip"] == "10.10.64.254"
    assert parsed["first_packet_at"] == datetime(2026, 6, 28, 23, 23, 56)  # naïf, UTC implicite
    assert parsed["raw_line"] == ALLOW_HTTPS_LINE
    assert parsed["ac_policy"] == "SITE-A-FWTEST"


def test_fields_not_promoted_to_columns_are_preserved_in_extra():
    parsed = parse_line(ALLOW_HTTPS_LINE)

    assert parsed["extra"]["URLCategory"] == "Computer Security"
    assert parsed["extra"]["URL"] == "https://ds.kaspersky.com"
    assert parsed["extra"]["NAT_ResponderIP"] == "203.0.113.10"
    assert parsed["extra"]["Prefilter Policy"] == "Default Prefilter Policy"
    assert parsed["extra"]["_msg_id"] == "%FTD-6-430003"
    # champs promus en colonnes -> absents d'extra (pas dupliqués)
    assert "SrcIP" not in parsed["extra"]
    assert "AccessControlRuleAction" not in parsed["extra"]


def test_blocked_connection_has_fewer_optional_fields_but_parses_cleanly():
    parsed = parse_line(BLOCK_SMB_LINE)

    assert parsed["access_control_rule_action"] == "Block"
    assert parsed["dst_port"] == 139
    assert parsed["access_control_rule_name"] == "Default Action"
    # champs absents sur les connexions bloquées -> None, pas une erreur
    assert parsed["application_protocol"] is None
    assert parsed["web_application"] is None
    assert parsed["connection_duration"] is None
    assert parsed["initiator_bytes"] == 0


def test_icmp_line_has_no_ports_but_keeps_icmp_fields_in_extra():
    parsed = parse_line(ICMP_BLOCK_LINE)

    assert parsed["protocol"] == "icmp"
    assert parsed["src_port"] is None
    assert parsed["dst_port"] is None
    assert parsed["ingress_zone"] is None
    assert parsed["extra"]["ICMPType"] == "Destination Unreachable"
    assert parsed["extra"]["ICMPCode"] == "Port unreachable"
    assert parsed["extra"]["VLAN_ID"] == "253"


def test_malformed_line_raises_explicit_error_instead_of_silently_failing():
    with pytest.raises(LogParsingError):
        parse_line("this is not a Cisco FTD log line")
