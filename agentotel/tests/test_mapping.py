"""语义映射测试。"""

from agentotel.semconv.mapping import apply_mapping, _dig, get_mapping
from agentotel.semconv import attributes as A


OPENAI_RESP = {
    "id": "chatcmpl-1",
    "model": "gpt-4o-mini",
    "usage": {
        "prompt_tokens": 100,
        "completion_tokens": 20,
        "total_tokens": 120,
    },
    "choices": [{"finish_reason": "stop"}],
}


def test_dig_simple():
    assert _dig({"a": {"b": 1}}, "a.b") == 1
    assert _dig({"a": {"b": 1}}, "a.c") is None


def test_dig_index():
    data = {"choices": [{"finish_reason": "stop"}]}
    assert _dig(data, "choices[0].finish_reason") == "stop"
    assert _dig(data, "choices[].finish_reason") == "stop"


def test_openai_mapping():
    out = apply_mapping("openai", OPENAI_RESP)
    assert out[A.USAGE_INPUT_TOKENS] == 100
    assert out[A.USAGE_OUTPUT_TOKENS] == 20
    assert out[A.USAGE_TOTAL_TOKENS] == 120
    assert out[A.REQUEST_MODEL] == "gpt-4o-mini"
    assert out[A.RESPONSE_FINISH_REASONS] == ["stop"]


def test_langchain_mapping():
    msg = {
        "usage_metadata": {
            "input_tokens": 10,
            "output_tokens": 5,
            "total_tokens": 15,
        },
        "response_metadata": {"finish_reason": "tool_calls", "model_name": "gpt-4o"},
    }
    out = apply_mapping("langchain", msg)
    assert out[A.USAGE_INPUT_TOKENS] == 10
    assert out[A.RESPONSE_FINISH_REASONS] == ["tool_calls"]
    assert out[A.RESPONSE_MODEL] == "gpt-4o"


def test_unknown_framework_empty():
    assert get_mapping("nope") == {}
    assert apply_mapping("nope", {"a": 1}) == {}


def test_missing_values_skipped():
    out = apply_mapping("openai", {"model": "x"})
    assert A.USAGE_INPUT_TOKENS not in out
