"""Metrics 上报测试（通过 InMemoryMetricReader 断言数据点）。"""


def _collect(metric_reader):
    """从内存 reader 把所有指标按 name 收集成 {name: [data_points]}。"""
    data = metric_reader.get_metrics_data()
    out = {}
    if not data:
        return out
    for rm in data.resource_metrics:
        for sm in rm.scope_metrics:
            for metric in sm.metrics:
                points = metric.data.data_points
                out.setdefault(metric.name, []).extend(points)
    return out


def _attr(dp, key):
    return dp.attributes.get(key)


def test_record_llm(reporter, metric_reader):
    reporter.record_llm("gpt-4o-mini", "openai",
                        input_tokens=100, output_tokens=20, duration_ms=300)
    metrics = _collect(metric_reader)

    # token counter：input / output 各一条
    token_points = metrics["agentotel_llm_tokens"]
    by_type = {_attr(p, "type"): p.value for p in token_points}
    assert by_type["input"] == 100
    assert by_type["output"] == 20
    assert all(_attr(p, "model") == "gpt-4o-mini" for p in token_points)

    # duration histogram 有一个点
    dur = metrics["agentotel_llm_duration_ms"]
    assert len(dur) == 1 and dur[0].count == 1


def test_record_tool(reporter, metric_reader):
    reporter.record_tool("search", "extension", duration_ms=120, status="ok")
    reporter.record_tool("search", "extension", duration_ms=10, status="error")
    metrics = _collect(metric_reader)

    calls = metrics["agentotel_tool_calls"]
    assert len(calls) == 2
    statuses = {_attr(p, "status") for p in calls}
    assert statuses == {"ok", "error"}

    dur = metrics["agentotel_tool_duration_ms"]
    assert sum(p.count for p in dur) == 2


def test_record_agent(reporter, metric_reader):
    reporter.record_agent("my-agent", duration_ms=1000, status="ok")
    metrics = _collect(metric_reader)
    calls = metrics["agentotel_agent_calls"]
    assert calls[0].value == 1
    assert _attr(calls[0], "agent") == "my-agent"


def test_record_retrieval(reporter, metric_reader):
    reporter.record_retrieval("kb", duration_ms=200, doc_count=3, status="ok")
    metrics = _collect(metric_reader)
    docs = metrics["agentotel_retrieval_doc_count"]
    assert docs[0].sum == 3


def test_record_http(reporter, metric_reader):
    reporter.record_http("POST", "/agent", 200, duration_ms=80)
    reporter.record_http("GET", "/health", 500, duration_ms=5)
    metrics = _collect(metric_reader)

    calls = metrics["agentotel_http_calls"]
    by_route = {_attr(p, "route"): _attr(p, "status") for p in calls}
    assert by_route["/agent"] == "ok"
    assert by_route["/health"] == "error"


def test_reporter_never_raises(reporter, metric_reader):
    # 传入异常参数也不应抛出（增强能力不能影响业务）
    reporter.record_llm(None, None)
    reporter.record_tool(None)
    reporter.record_http(None, None, None)


def test_record_quality(reporter, metric_reader):
    reporter.record_quality("my-agent", 88.0, evaluator="rule")
    reporter.record_feedback("my-agent", "positive")
    metrics = _collect(metric_reader)

    score = metrics["agentotel_quality_score"]
    assert len(score) == 1 and score[0].sum == 88.0
    assert _attr(score[0], "evaluator") == "rule"

    feedback = metrics["agentotel_quality_feedback"]
    assert feedback[0].value == 1
    assert _attr(feedback[0], "sentiment") == "positive"
