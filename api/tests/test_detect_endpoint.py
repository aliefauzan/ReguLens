"""The detect endpoint is what lets the upload form stop interrogating people.

It has to answer without storing anything: a user who changes their mind after
seeing what we read must leave no document and no file behind.
"""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_pasted_text_comes_back_read():
    response = client.post(
        "/documents/detect",
        data={"text": "COMMISSION REGULATION (EU) No 1129/2011. Official Journal of the European Union."},
    )
    assert response.status_code == 200
    found = response.json()["detection"]
    assert found["jurisdiction"]["value"] == "EU"
    assert found["source_type"]["value"] == "official_regulation"
    assert found["needs_confirmation"] is False


def test_a_document_with_no_text_says_so_in_words_a_user_can_act_on():
    response = client.post("/documents/detect", data={"text": "   "})
    assert response.status_code == 422
    assert "paste the wording" in response.json()["detail"]


def test_an_unreadable_source_asks_rather_than_guesses():
    response = client.post(
        "/documents/detect",
        data={"text": "Sodium benzoate shall not exceed 200 mg/kg."},
    )
    assert response.status_code == 200
    found = response.json()["detection"]
    assert found["needs_confirmation"] is True
    assert found["jurisdiction"]["value"] is None
