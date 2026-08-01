from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, TypedDict

import agentsre_sdk
from dotenv import load_dotenv
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.tools import tool
from langgraph.graph import END, START, StateGraph


load_dotenv(Path(__file__).with_name(".env"), override=True)

# This file represents a normal retail-support application. These constants
# model its runtime conditions; they are not AgentSRE configuration.
SCENARIO_NAME = "Repeated order lookup"
ORDER_LOOKUP_ATTEMPTS = 4
ORDER_LOOKUP_DELAY_SECONDS = 0.04
ORDER_SERVICE_FAILURE = False
PROMPT_TOKENS = 210
COMPLETION_TOKENS = 75
UNSUPPORTED_ANSWER = False
MODEL_NAME = "gemini-2.5-flash"

ORDER_DATABASE = {
    "ORD-1048": {
        "customer": "Aarav Sharma",
        "status": "delivered",
        "email": "aarvsharma@gmail.com",
        "delivered_days_ago": 4,
        "item": "wireless headphones",
        "amount": 6499,
    }
}

REFUND_POLICY = {
    "return_window_days": 14,
    "requires_inspection": True,
    "automatic_approval": False,
}


class SupportState(TypedDict, total=False):
    question: str
    order_id: str
    intent: str
    order: dict[str, Any]
    policy: dict[str, Any]
    lookup_attempts: int
    answer: str


class DeterministicChatModel(FakeMessagesListChatModel):
    @property
    def _llm_type(self) -> str:
        return MODEL_NAME

    @property
    def _identifying_params(self) -> dict[str, str]:
        return {"model": MODEL_NAME, "model_name": MODEL_NAME}


def initialize_sdk() -> None:
    agentsre_sdk.init(
        tenant_id=os.getenv("AGENTSRE_TENANT_ID"),
        project_id=os.getenv("AGENTSRE_PROJECT_ID"),
        service_name=os.getenv("AGENTSRE_SERVICE_NAME"),
        environment=os.getenv("AGENTSRE_ENVIRONMENT", "demo"),
        api_key=os.getenv("AGENTSRE_API_KEY"),
        pii_redaction=True,
        sensitive_fields=["email", "phone", "ssn", "api_key"],
        instrument_langgraph=True,
        instrument_crewai=False,
    )


def invoke_model(prompt: str, response: str, input_tokens: int, output_tokens: int) -> str:
    model = DeterministicChatModel(responses=[AIMessage(
        content=response,
        response_metadata={"model_name": MODEL_NAME, "finish_reason": "stop"},
        usage_metadata={
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": input_tokens + output_tokens,
        },
    )])
    return str(model.invoke([HumanMessage(content=prompt)]).content)


@tool
def order_lookup(order_id: str) -> dict[str, Any]:
    """Retrieve an order from the retail order service."""
    time.sleep(ORDER_LOOKUP_DELAY_SECONDS)
    if ORDER_SERVICE_FAILURE:
        raise RuntimeError(f"Order service returned HTTP 503 for {order_id}.")
    return ORDER_DATABASE[order_id]


@tool
def refund_policy_lookup(item_category: str, country: str) -> dict[str, Any]:
    """Retrieve the refund policy for an item category and country."""
    time.sleep(0.03)
    return REFUND_POLICY


def classify_request(state: SupportState) -> SupportState:
    intent = invoke_model(
        state["question"],
        "Intent: refund eligibility. Required evidence: order status and return policy.",
        85,
        24,
    )
    return {"intent": intent}


def retrieve_order(state: SupportState) -> SupportState:
    order = None
    for _attempt in range(ORDER_LOOKUP_ATTEMPTS):
        order = order_lookup.invoke({"order_id": state["order_id"]})
    return {
        "order": order,
        "lookup_attempts": ORDER_LOOKUP_ATTEMPTS,
    }


def evaluate_refund_policy(_state: SupportState) -> SupportState:
    policy = refund_policy_lookup.invoke({"item_category": "electronics", "country": "IN"})
    return {"policy": policy}


def compose_response(state: SupportState) -> SupportState:
    if UNSUPPORTED_ANSWER:
        response = (
            "Your refund is guaranteed and already approved for immediate payment, "
            "although no captured order or policy evidence confirms that approval."
        )
    else:
        response = (
            f"Order {state['order_id']} was delivered {state['order']['delivered_days_ago']} days ago "
            f"and is within the {state['policy']['return_window_days']}-day return window. "
            "The item can be submitted for inspection; the policy does not guarantee automatic approval."
        )
    prompt = (
        f"Customer question: {state['question']}\n"
        f"Captured evidence: {json.dumps({'order': state['order'], 'policy': state['policy']})}"
    )
    return {"answer": invoke_model(prompt, response, PROMPT_TOKENS, COMPLETION_TOKENS)}


def build_agent():
    workflow = StateGraph(SupportState)
    workflow.add_node("ClassifyRequest", classify_request)
    workflow.add_node("RetrieveOrder", retrieve_order)
    workflow.add_node("EvaluateRefundPolicy", evaluate_refund_policy)
    workflow.add_node("ComposeResponse", compose_response)
    workflow.add_edge(START, "ClassifyRequest")
    workflow.add_edge("ClassifyRequest", "RetrieveOrder")
    workflow.add_edge("RetrieveOrder", "EvaluateRefundPolicy")
    workflow.add_edge("EvaluateRefundPolicy", "ComposeResponse")
    workflow.add_edge("ComposeResponse", END)
    return workflow.compile(name="RetailSupportWorkflow")


def main() -> None:
    initialize_sdk()
    try:
        result = build_agent().invoke(
            {
                "question": "Can I return my delivered wireless headphones for a refund?",
                "order_id": "ORD-1048",
                "lookup_attempts": 0,
            }
        )
        print(f"[{SCENARIO_NAME}]")
        print(result["answer"])
    except Exception as exc:
        print(f"[{SCENARIO_NAME}] failed: {exc}")
    finally:
        agentsre_sdk.shutdown()


if __name__ == "__main__":
    main()
