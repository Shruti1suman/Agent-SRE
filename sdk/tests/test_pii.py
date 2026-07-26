from agentsre_sdk.processors.pii_processor import PIIProcessor, REDACTED


def test_redacts_common_pii_patterns() -> None:
    processor = PIIProcessor(enabled=True)

    text = "Email jane@example.com, phone 555-123-4567, ssn 123-45-6789, card 4111 1111 1111 1111."

    redacted = processor.redact_text(text)
    assert "jane@example.com" not in redacted
    assert "555-123-4567" not in redacted
    assert "123-45-6789" not in redacted
    assert "4111 1111 1111 1111" not in redacted
    assert redacted.count(REDACTED) == 4


def test_redact_payload_reports_redaction_findings() -> None:
    processor = PIIProcessor(enabled=True, sensitive_fields={"api_key"})
    payload = {
        "llm": {
            "prompt": "Traveler Email: jane@example.com, phone 555-123-4567, ssn 123-45-6789.",
            "response": "customer name: Jane Doe. paid with 4111 1111 1111 1111.",
        },
        "tool": {"api_key": "secret"},
    }

    redacted, findings = processor.redact_payload_with_findings(payload)

    assert redacted["llm"]["prompt"] == f"Traveler Email: {REDACTED}, phone {REDACTED}, ssn {REDACTED}."
    assert redacted["llm"]["response"] == f"customer name: {REDACTED}. paid with {REDACTED}."
    assert redacted["tool"]["api_key"] == REDACTED
    assert findings[("llm", "prompt")] == {"email", "phone", "ssn"}
    assert findings[("llm", "response")] == {"credit_card", "name"}
    assert findings[("tool", "api_key")] == {"api_key"}


def test_redacts_nested_sensitive_fields() -> None:
    processor = PIIProcessor(enabled=True, sensitive_fields={"api_key", "email"})
    payload = {"tool": {"api_key": "secret", "args": [{"email": "person@example.com"}]}}

    redacted = processor.redact_payload(payload)

    assert redacted["tool"]["api_key"] == REDACTED
    assert redacted["tool"]["args"][0]["email"] == REDACTED


def test_redaction_can_be_disabled() -> None:
    processor = PIIProcessor(enabled=False, sensitive_fields={"email"})
    payload = {"email": "person@example.com"}

    assert processor.redact_payload(payload) == payload


def test_json_string_redaction_does_not_treat_provider_timestamps_as_phone_numbers() -> None:
    processor = PIIProcessor(enabled=True)
    payload = {
        "llm": {
            "response": (
                '{"created":1721851200,'
                '"message":{"content":"Email person@example.com or call 555-123-4567"}}'
            )
        }
    }

    redacted, findings = processor.redact_payload_with_findings(payload)

    assert '"created":1721851200' in redacted["llm"]["response"]
    assert "person@example.com" not in redacted["llm"]["response"]
    assert "555-123-4567" not in redacted["llm"]["response"]
    assert findings[("llm", "response", "message", "content")] == {"email", "phone"}


def test_redacts_common_traveler_fields_without_explicit_configuration() -> None:
    processor = PIIProcessor(enabled=True)
    payload = {
        "tool": {
            "traveler_name": "Ananya Rao",
            "traveler_email": "ananya@example.com",
            "traveler_phone": "555-123-4567",
        }
    }

    redacted, findings = processor.redact_payload_with_findings(payload)

    assert redacted["tool"]["traveler_name"] == REDACTED
    assert redacted["tool"]["traveler_email"] == REDACTED
    assert redacted["tool"]["traveler_phone"] == REDACTED
    assert findings[("tool", "traveler_name")] == {"name"}
    assert findings[("tool", "traveler_email")] == {"email"}
    assert findings[("tool", "traveler_phone")] == {"phone"}


def test_redacts_generic_sensitive_fields_only_in_runtime_content() -> None:
    processor = PIIProcessor(enabled=True)
    payload = {
        "patient_name": "Ananya Rao",
        "spans": [
            {
                "tool": {
                    "tool_arguments": {
                        "patient_name": "Ananya Rao",
                        "employee_name": "Ravi Kumar",
                        "client_email": "client@example.com",
                        "access_token": "secret-token",
                        "passport_number": "P1234567",
                    }
                }
            }
        ],
    }

    redacted, findings = processor.redact_payload_with_findings(payload)

    args = redacted["spans"][0]["tool"]["tool_arguments"]
    assert redacted["patient_name"] == "Ananya Rao"
    assert args["patient_name"] == REDACTED
    assert args["employee_name"] == REDACTED
    assert args["client_email"] == REDACTED
    assert args["access_token"] == REDACTED
    assert args["passport_number"] == REDACTED
    assert findings[("spans", 0, "tool", "tool_arguments", "patient_name")] == {"name"}
    assert findings[("spans", 0, "tool", "tool_arguments", "employee_name")] == {"name"}
    assert findings[("spans", 0, "tool", "tool_arguments", "client_email")] == {"email"}
    assert findings[("spans", 0, "tool", "tool_arguments", "access_token")] == {"secret"}
    assert findings[("spans", 0, "tool", "tool_arguments", "passport_number")] == {"identity"}


def test_sensitive_field_values_are_redacted_from_free_text_and_json_strings() -> None:
    processor = PIIProcessor(enabled=True)
    payload = {
        "tool": {
            "traveler_name": "Ananya Rao",
            "tool_output": "Reservation confirmed for Ananya Rao on SkyBridge from Bengaluru-Mysore.",
            "tool_error": "Supplier reservation gateway timed out for Ananya Rao: SUP-504.",
            "json_output": '{"message":"Ananya Rao is booked on SkyBridge","route":"Bengaluru-Mysore"}',
        }
    }

    redacted, findings = processor.redact_payload_with_findings(payload)

    assert redacted["tool"]["traveler_name"] == REDACTED
    assert redacted["tool"]["tool_output"] == f"Reservation confirmed for {REDACTED} on SkyBridge from Bengaluru-Mysore."
    assert redacted["tool"]["tool_error"] == f"Supplier reservation gateway timed out for {REDACTED}: SUP-504."
    assert redacted["tool"]["json_output"] == f'{{"message":"{REDACTED} is booked on SkyBridge","route":"Bengaluru-Mysore"}}'
    assert findings[("tool", "tool_output")] == {"name"}
    assert findings[("tool", "tool_error")] == {"name"}
    assert findings[("tool", "json_output", "message")] == {"name"}


def test_static_available_tool_schema_descriptors_are_not_redacted() -> None:
    processor = PIIProcessor(enabled=True)
    payload = {
        "execution": {
            "available_tools": [
                {
                    "tool_name": "lookup",
                    "tool_arguments": {
                        "traveler_name": {"title": "Traveler Name", "type": "string"},
                        "client_email": {"title": "Client Email", "type": "string"},
                    },
                }
            ]
        },
        "spans": [
            {
                "tool": {
                    "tool_arguments": {
                        "traveler_name": "Ananya Rao",
                        "client_email": "client@example.com",
                    }
                }
            }
        ],
    }

    redacted = processor.redact_payload(payload)

    assert redacted["execution"]["available_tools"][0]["tool_arguments"] == {
        "traveler_name": {"title": "Traveler Name", "type": "string"},
        "client_email": {"title": "Client Email", "type": "string"},
    }
    assert redacted["spans"][0]["tool"]["tool_arguments"] == {
        "traveler_name": REDACTED,
        "client_email": REDACTED,
    }


def test_sdk_metadata_names_and_schema_values_are_not_redacted() -> None:
    processor = PIIProcessor(enabled=True)
    payload = {
        "execution": {
            "available_tools": [
                {
                    "tool_name": "traveler_profile_lookup",
                    "tool_type": "Tool",
                    "tool_arguments": {
                        "traveler_email": {"title": "Traveler Email", "type": "string"},
                    },
                }
            ],
            "available_agents": [
                {
                    "agent_name": "TravelOperationsCoordinator",
                    "agent_role": "Agent",
                    "agent_type": "LangGraphNode",
                }
            ],
        },
        "spans": [
            {
                "span_name": "LangGraph Node: TravelOperationsCoordinator",
                "span_kind": "AGENT",
                "agent": {
                    "agent_name": "TravelOperationsCoordinator",
                    "agent_role": "Agent",
                    "agent_type": "LangGraphNode",
                },
                "reasoning": {
                    "node_name": "TravelOperationsCoordinator",
                    "previous_node": None,
                    "next_node": "PolicyComplianceAdvisor",
                },
            },
            {
                "span_name": "traveler_profile_lookup",
                "span_kind": "TOOL",
                "tool": {
                    "tool_name": "traveler_profile_lookup",
                    "tool_type": "Tool",
                    "tool_arguments": {"traveler_email": "ananya.rao@example.com"},
                },
            },
        ],
    }

    redacted = processor.redact_payload(payload)

    assert redacted["execution"]["available_tools"][0]["tool_name"] == "traveler_profile_lookup"
    assert redacted["execution"]["available_tools"][0]["tool_arguments"]["traveler_email"]["type"] == "string"
    assert redacted["execution"]["available_agents"][0]["agent_name"] == "TravelOperationsCoordinator"
    assert redacted["spans"][0]["span_name"] == "LangGraph Node: TravelOperationsCoordinator"
    assert redacted["spans"][0]["agent"]["agent_name"] == "TravelOperationsCoordinator"
    assert redacted["spans"][0]["reasoning"]["node_name"] == "TravelOperationsCoordinator"
    assert redacted["spans"][0]["reasoning"]["next_node"] == "PolicyComplianceAdvisor"
    assert redacted["spans"][1]["tool"]["tool_name"] == "traveler_profile_lookup"
    assert redacted["spans"][1]["tool"]["tool_arguments"]["traveler_email"] == REDACTED


def test_llm_provider_json_preserves_tool_metadata_but_redacts_runtime_values() -> None:
    processor = PIIProcessor(enabled=True)
    payload = {
        "spans": [
            {
                "tool": {
                    "tool_arguments": {
                        "traveler_name": "Ananya Rao",
                        "traveler_email": "ananya.rao@example.com",
                    }
                }
            },
            {
                "llm": {
                    "prompt": (
                        '{"messages":[{"role":"user","content":"Dear Ananya, use Ananya\\u0027s profile '
                        'ananya.rao@example.com"}],'
                        '"tools":[{"type":"function","function":{"name":"traveler_profile_lookup",'
                        '"description":"Retrieves traveler profile preferences.",'
                        '"parameters":{"type":"object","properties":{"traveler_email":{"type":"string"}}}}}]}'
                    )
                }
            },
        ]
    }

    redacted = processor.redact_payload(payload)
    prompt = redacted["spans"][1]["llm"]["prompt"]

    assert "Dear [REDACTED]" in prompt
    assert "use [REDACTED] profile" in prompt
    assert "ananya.rao@example.com" not in prompt
    assert '"name":"traveler_profile_lookup"' in prompt
    assert '"type":"string"' in prompt


def test_contextual_name_fallback_is_conservative() -> None:
    processor = PIIProcessor(enabled=True)
    text = "Reservation for Ananya Rao on SkyBridge from Bengaluru-Mysore using CrewAI."

    redacted, fields = processor.redact_text_with_findings(text)

    assert redacted == f"Reservation for {REDACTED} on SkyBridge from Bengaluru-Mysore using CrewAI."
    assert fields == {"name"}
