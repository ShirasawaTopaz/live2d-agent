from internal.memory.types_ext import TokenUsage


def test_ollama_token_extraction():
    response = {"prompt_eval_count": 50, "eval_count": 25}
    token_count = None
    if isinstance(response, dict):
        input_tok = response.get("prompt_eval_count", 0) or 0
        output_tok = response.get("eval_count", 0) or 0
        if input_tok or output_tok:
            token_count = TokenUsage(
                input_tokens=input_tok,
                output_tokens=output_tok,
                total_tokens=input_tok + output_tok,
            ).to_dict()
    assert token_count is not None
    assert token_count["input"] == 50
    assert token_count["output"] == 25
    assert token_count["total"] == 75


def test_online_token_extraction():
    class Usage:
        prompt_tokens = 60
        completion_tokens = 30
        total_tokens = 90

    response = type("Response", (), {"usage": Usage()})()
    token_count = None
    if response and hasattr(response, "usage") and response.usage:
        token_count = {
            "input": response.usage.prompt_tokens or 0,
            "output": response.usage.completion_tokens or 0,
            "total": response.usage.total_tokens or 0,
        }
    assert token_count is not None
    assert token_count["input"] == 60
    assert token_count["output"] == 30
    assert token_count["total"] == 90


def test_online_token_extraction_no_usage():
    response = type("Response", (), {"usage": None})()
    token_count = None
    if response and hasattr(response, "usage") and response.usage:
        token_count = {}
    assert token_count is None


def test_transformers_token_estimation():
    input_tokens = 100
    output_tokens = 40
    usage = TokenUsage(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=input_tokens + output_tokens,
    ).to_dict()
    assert usage["total"] == 140
