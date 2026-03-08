"""
tests/test_integration.py
IntegrationManager — add / list / remove 단위 테스트 (최소 8개)
"""
import pytest
from rolemesh.integration import (
    IntegrationManager,
    DuplicateIntegrationError,
    IntegrationNotFoundError,
)


@pytest.fixture
def mgr(tmp_path):
    db = str(tmp_path / "test_integration.db")
    m = IntegrationManager(db_path=db)
    yield m
    m.close()


# ── add ───────────────────────────────────────────────────────────────────────

def test_add_returns_info(mgr):
    info = mgr.add("bot1", role="builder", endpoint="http://localhost:9000")
    assert info["name"] == "bot1"
    assert info["role"] == "builder"
    assert info["endpoint"] == "http://localhost:9000"
    assert info["capabilities"] == []


def test_add_with_capabilities(mgr):
    info = mgr.add(
        "bot2", role="analyzer", endpoint="http://localhost:9001",
        capabilities=["analyze", "review"]
    )
    assert set(info["capabilities"]) == {"analyze", "review"}


def test_add_duplicate_raises(mgr):
    mgr.add("dup-bot", role="builder", endpoint="http://localhost:9002")
    with pytest.raises(DuplicateIntegrationError):
        mgr.add("dup-bot", role="builder", endpoint="http://localhost:9002")


def test_add_duplicate_allow_update(mgr):
    mgr.add("upd-bot", role="builder", endpoint="http://localhost:9003")
    info = mgr.add(
        "upd-bot", role="deployer", endpoint="http://localhost:9004",
        allow_update=True
    )
    assert info["role"] == "deployer"
    assert info["endpoint"] == "http://localhost:9004"


def test_add_empty_name_raises(mgr):
    with pytest.raises(ValueError):
        mgr.add("", role="builder", endpoint="http://localhost:9000")


def test_add_empty_endpoint_raises(mgr):
    with pytest.raises(ValueError):
        mgr.add("bot-x", role="builder", endpoint="")


# ── list ──────────────────────────────────────────────────────────────────────

def test_list_empty(mgr):
    assert mgr.list() == []


def test_list_returns_all(mgr):
    mgr.add("a", role="r1", endpoint="http://a")
    mgr.add("b", role="r2", endpoint="http://b")
    result = mgr.list()
    assert len(result) == 2
    names = {i["name"] for i in result}
    assert names == {"a", "b"}


def test_list_includes_capabilities(mgr):
    mgr.add("cap-bot", role="tester", endpoint="http://test",
             capabilities=["test", "lint"])
    result = mgr.list()
    assert len(result) == 1
    assert set(result[0]["capabilities"]) == {"test", "lint"}


# ── remove ────────────────────────────────────────────────────────────────────

def test_remove_existing(mgr):
    mgr.add("rm-bot", role="r", endpoint="http://rm")
    mgr.remove("rm-bot")
    assert mgr.list() == []


def test_remove_also_deletes_capabilities(mgr):
    mgr.add("rm-cap", role="r", endpoint="http://rc", capabilities=["a", "b"])
    mgr.remove("rm-cap")
    # DB에서 capabilities도 삭제됐는지 확인
    conn = mgr._client._conn_ctx()
    rows = conn.execute(
        "SELECT * FROM capabilities WHERE agent_id = ?", ("rm-cap",)
    ).fetchall()
    assert rows == []


def test_remove_nonexistent_raises(mgr):
    with pytest.raises(IntegrationNotFoundError):
        mgr.remove("ghost-bot")


# ── get ───────────────────────────────────────────────────────────────────────

def test_get_existing(mgr):
    mgr.add("get-bot", role="tester", endpoint="http://get",
             capabilities=["run"])
    info = mgr.get("get-bot")
    assert info["name"] == "get-bot"
    assert info["role"] == "tester"
    assert "run" in info["capabilities"]


def test_get_nonexistent_raises(mgr):
    with pytest.raises(IntegrationNotFoundError):
        mgr.get("no-such-bot")
