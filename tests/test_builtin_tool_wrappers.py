from pathlib import Path

from openagent.memory.store import MemoryStore
from openagent.skills.registry import SkillRegistry
from openagent.tools.memory_tool import MemoryTool
from openagent.tools.skill_tool import SkillTool
from openagent.tools.todo_tool import TodoStore, TodoTool


def test_todo_tool_add_update_list(tmp_path):
    tool = TodoTool(TodoStore(tmp_path / "todo.json"))

    rec = tool(action="add", text="write docs")
    assert rec.ok
    item_id = rec.result["id"]

    rec = tool(action="update", item_id=item_id, status="done")
    assert rec.ok
    assert rec.result["status"] == "done"

    rec = tool(action="list")
    assert rec.ok
    assert rec.result["items"][0]["status"] == "done"


def test_todo_tool_add_without_text_fails_gracefully(tmp_path):
    tool = TodoTool(TodoStore(tmp_path / "todo.json"))
    rec = tool(action="add")
    assert not rec.ok
    assert "text" in rec.error


def test_memory_tool_remember_recall(tmp_path):
    store = MemoryStore(tmp_path / "memory.sqlite3")
    tool = MemoryTool(store, provenance="test-suite")

    rec = tool(action="remember", scope="project:x", key="lang", value="python")
    assert rec.ok

    rec = tool(action="recall", scope="project:x", key="lang")
    assert rec.ok
    assert rec.result["records"][0]["value"] == "python"
    store.close()


def test_memory_tool_refuses_secret_via_error_field(tmp_path):
    store = MemoryStore(tmp_path / "memory.sqlite3")
    tool = MemoryTool(store)
    rec = tool(action="remember", scope="user", key="token", value="sk-realistictoken1234567890123456")
    assert not rec.ok
    assert rec.error
    store.close()


def test_memory_tool_search_and_forget(tmp_path):
    store = MemoryStore(tmp_path / "memory.sqlite3")
    tool = MemoryTool(store)
    rec = tool(action="remember", scope="project:x", key="framework", value="pytest")
    record_id = rec.result["id"]

    rec = tool(action="search", scope="project:x", query="pytest")
    assert rec.ok
    assert len(rec.result["records"]) == 1

    rec = tool(action="forget", scope="project:x", record_id=record_id)
    assert rec.ok
    assert rec.result["deleted"] is True
    store.close()


def test_skill_tool_catalog_find_load():
    registry = SkillRegistry()
    tool = SkillTool(registry)

    rec = tool(action="catalog")
    assert rec.ok
    assert len(rec.result["skills"]) > 0

    rec = tool(action="find", task_description="review this code for hardcoded secrets")
    assert rec.ok
    assert rec.result["matches"][0]["name"] == "defensive-security-review"

    name = rec.result["matches"][0]["name"]
    rec = tool(action="load", name=name)
    assert rec.ok
    assert len(rec.result["body"]) > 0


def test_skill_tool_unknown_action_errors():
    registry = SkillRegistry()
    tool = SkillTool(registry)
    rec = tool(action="bogus")
    assert not rec.ok
