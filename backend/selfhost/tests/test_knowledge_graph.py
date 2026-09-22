from sqlalchemy import select

from selfhost.db import Record, User, ident, transaction


def test_knowledge_graph_requires_authentication(client):
    capabilities = client.get("/v1/server-info").json()["capabilities"]
    assert {"knowledge_graph", "static_maps"}.issubset(capabilities)
    assert client.get("/v1/knowledge-graph").status_code == 401
    assert client.post("/v1/knowledge-graph/rebuild").status_code == 401


def test_knowledge_graph_reflects_only_the_owners_memories(client, admin, other):
    empty = client.get("/v1/knowledge-graph", headers=admin)
    assert empty.status_code == 200
    assert empty.json()["nodes"] == [{"id": "user-node", "label": "Me", "node_type": "user"}]

    own = client.post(
        "/v3/memories",
        headers=admin,
        json={"content": "The garden needs water", "category": "personal"},
    )
    foreign = client.post("/v3/memories", headers=other, json={"content": "A private secret"})
    assert own.status_code == foreign.status_code == 200

    graph = client.get("/v1/knowledge-graph", headers=admin)
    assert graph.status_code == 200
    body = graph.json()
    assert body["node_count"] == 3
    assert body["edge_count"] == 2
    assert body["truncated"] is False
    assert {node["label"] for node in body["nodes"]} == {"Me", "personal", "The garden needs water"}
    assert {edge["target_id"] for edge in body["edges"]} == {"memory-category:personal", "memory:" + own.json()["id"]}
    assert client.post("/v1/knowledge-graph/rebuild", headers=admin).json() == {
        "status": "ready",
        "nodes_count": 3,
        "edges_count": 2,
    }

    client.delete("/v3/memories/" + own.json()["id"], headers=admin)
    assert client.get("/v1/knowledge-graph", headers=admin).json()["node_count"] == 1


def test_knowledge_graph_shows_conversations_and_source_links(client, admin):
    created = client.post("/v1/conversations", headers=admin, json={})
    assert created.status_code == 200
    conversation_id = created.json()["conversation"]["id"]
    client.patch(
        "/v1/conversations/" + conversation_id,
        headers=admin,
        json={"title": "Garden planning"},
    )
    with transaction() as db:
        owner = db.scalar(select(User).where(User.email == "admin@test.local"))
        memory_id = ident()
        db.add(
            Record(
                id=memory_id,
                user_id=owner.id,
                kind="memory",
                data={
                    "content": "Plant tomatoes",
                    "category": "personal",
                    "conversation_id": conversation_id,
                    "tags": ["garden"],
                },
            )
        )

    graph = client.get("/v1/knowledge-graph", headers=admin).json()
    assert {node["label"] for node in graph["nodes"]} == {
        "Me",
        "Conversations",
        "Garden planning",
        "Plant tomatoes",
        "personal",
        "garden",
    }
    assert {(edge["source_id"], edge["target_id"]) for edge in graph["edges"]} >= {
        ("conversation:" + conversation_id, "memory:" + memory_id)
    }
