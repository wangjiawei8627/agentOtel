"""会话上下文测试。"""

from agentotel.context import (
    AgentContext,
    use_context,
    get_context,
)


def test_new_generates_session():
    ctx = AgentContext.new()
    assert ctx.session_id.startswith("sess_")
    assert ctx.user_id is None


def test_new_preserves_fields():
    ctx = AgentContext.new(session_id="s1", user_id="u1", agent_name="a1")
    assert ctx.session_id == "s1"
    assert ctx.user_id == "u1"
    assert ctx.agent_name == "a1"


def test_use_context_sets_and_restores():
    assert get_context() is None
    ctx = AgentContext.new(user_id="u1")
    with use_context(ctx):
        assert get_context() is ctx
        assert get_context().user_id == "u1"
    # 退出后恢复
    assert get_context() is None


def test_nested_context():
    outer = AgentContext.new(session_id="outer")
    inner = AgentContext.new(session_id="inner")
    with use_context(outer):
        with use_context(inner):
            assert get_context().session_id == "inner"
        assert get_context().session_id == "outer"
