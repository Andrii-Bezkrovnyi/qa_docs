import pytest
from fastapi.testclient import TestClient

from backend.main import app, QAHistory, SessionLocal, Base, engine

client = TestClient(app)

@pytest.fixture(scope="module", autouse=True)
def setup_and_teardown():
    # Create new database and tables before tests
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    db.query(QAHistory).delete()
    db.commit()
    db.close()
    yield
    # Delete all entries after tests (as you would in dev)
    db = SessionLocal()
    db.query(QAHistory).delete()
    db.commit()
    db.close()

def test_ask_endpoint_returns_answer():
    response = client.post("/api/ask", json={"question": "Що таке комп’ютер?"})
    assert response.status_code == 200
    data = response.json()
    assert "answer" in data
    assert isinstance(data["answer"], str)

def test_history_stores_question_and_answer():
    # Задаём новый вопрос
    question = "Is this a test question?"
    client.post("/api/ask", json={"question": question})

    # Смотрим, появился ли он в истории
    response = client.get("/api/history")
    assert response.status_code == 200
    history = response.json()
    assert any(qapair["question"] == question for qapair in history)

def test_ask_with_empty_pdf(monkeypatch):
    from backend import main
    monkeypatch.setattr(main, "PDF_CHUNKS", [])
    response = client.post(
        "/api/ask", json={
            "question": "Коли в Україні був створений перший комп'ютер ?"
        }
    )
    assert response.status_code == 200
    assert response.json()["answer"] in [
        "PDF is not loaded or missing.",
        "Rules PDF is not loaded or missing.",
        "I don't know."
    ]

def test_history_endpoint():
    response = client.get("/api/history")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    for item in data:
        assert "question" in item
        assert "answer" in item
