"""Lifecycle smoke test for трубки. Run from backend/: python tests/test_trubki.py"""

import os
import pathlib
import shutil
import sys

TEST_DB = pathlib.Path("data/test_trubki.db")
TEST_UPLOADS = pathlib.Path("data/test_trubki_uploads")
if TEST_DB.exists():
    TEST_DB.unlink()
shutil.rmtree(TEST_UPLOADS, ignore_errors=True)

os.environ["BOT_POLLING_ENABLED"] = "false"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./data/test_trubki.db"
os.environ["UPLOADS_DIR"] = str(TEST_UPLOADS)
os.environ["DEV_AUTH_ENABLED"] = "true"
os.environ["DEV_AUTH_SECRET"] = "dev-only-secret"
os.environ["OWNER_TELEGRAM_IDS"] = "111111111"

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient  # noqa: E402

from app.config import get_settings  # noqa: E402

get_settings.cache_clear()

from app.main import app  # noqa: E402

OWNER = 111111111
ADMIN_USER = 333333333
NOGA_USER = 222222222


def token(client: TestClient, telegram_id: int) -> str:
    response = client.post(
        "/api/auth/dev",
        json={"telegram_id": telegram_id, "secret": "dev-only-secret"},
    )
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


def upload(
    client: TestClient, headers: dict, trubka_id: int, kind: str, body: bytes
):
    return client.post(
        f"/api/trubki/{trubka_id}/files",
        headers=headers,
        data={"kind": kind},
        files={"file": (f"{kind}.jpg", body, "image/jpeg")},
    )


def main() -> None:
    try:
        with TestClient(app) as client:
            owner = {"Authorization": "Bearer " + token(client, OWNER)}
            for telegram_id, role in ((ADMIN_USER, "admin"), (NOGA_USER, "noga")):
                response = client.post(
                    "/api/users",
                    headers=owner,
                    json={
                        "telegram_id": telegram_id,
                        "role": role,
                        "display_name": role,
                    },
                )
                assert response.status_code == 201, response.text
            admin = {"Authorization": "Bearer " + token(client, ADMIN_USER)}
            noga_user = {"Authorization": "Bearer " + token(client, NOGA_USER)}

            response = client.post(
                "/api/razgruzy",
                headers=owner,
                json={"name": "Альфа", "commission_percent": 3},
            )
            assert response.status_code == 201, response.text
            alfa = response.json()
            response = client.post(
                "/api/cities",
                headers=owner,
                json={"name": "Тула", "razgruz_ids": [alfa["id"]]},
            )
            assert response.status_code == 201, response.text
            tula = response.json()
            response = client.post(
                "/api/nogas",
                headers=admin,
                json={"name": "Пётр", "city_id": tula["id"]},
            )
            assert response.status_code == 201, response.text
            petr = response.json()

            base = {
                "city_id": tula["id"],
                "noga_id": petr["id"],
                "amount": 250000,
            }

            # Статус и валюта получают значения по умолчанию, данные заказчика необязательны.
            response = client.post("/api/trubki", headers=owner, json=base)
            assert response.status_code == 201, response.text
            trubka = response.json()
            assert trubka["status"] == "zacep"
            assert trubka["amount_currency"] == "RUB"
            assert trubka["customer_name"] is None
            assert trubka["customer_address"] is None
            assert trubka["delivery"] is None
            assert trubka["files"] == []
            assert [event["action"] for event in trubka["history"]] == ["created"]
            assert trubka["history"][0]["actor_name"]
            assert "T" in trubka["history"][0]["created_at"]
            print("minimal creation and created event ok")

            trubka_id = trubka["id"]

            response = client.patch(
                f"/api/trubki/{trubka_id}",
                headers=admin,
                json={
                    "customer_name": "Иванов Иван",
                    "customer_address": "Тула, Ленина 1",
                    "delivery": "taxi",
                },
            )
            assert response.status_code == 200, response.text
            assert response.json()["history"][-1]["action"] == "updated"
            assert response.json()["history"][-1]["actor_name"] == "admin"

            # Автоматический статус нельзя выбрать вручную; остальные четыре можно.
            response = client.patch(
                f"/api/trubki/{trubka_id}",
                headers=admin,
                json={"status": "razgruzhaetsya"},
            )
            assert response.status_code == 422, response.text
            for manual_status in ("zacep", "zabrali", "vyplacheno", "srez"):
                response = client.patch(
                    f"/api/trubki/{trubka_id}",
                    headers=admin,
                    json={"status": manual_status},
                )
                assert response.status_code == 200, response.text
                assert response.json()["status"] == manual_status
            print("manual and automatic status validation ok")

            # Читать карточку и файл может вся команда, загружать роль noga не может.
            response = client.get(f"/api/trubki/{trubka_id}", headers=noga_user)
            assert response.status_code == 200
            assert response.json()["can_manage"] is False
            response = upload(client, noga_user, trubka_id, "money_photo", b"forbidden")
            assert response.status_code == 403, response.text

            # Перерасчёт требует фото денег.
            response = client.post(
                f"/api/trubki/{trubka_id}/recalculation",
                headers=admin,
                json={"amount": 100001},
            )
            assert response.status_code == 409, response.text
            assert response.json()["detail"]["code"] == "MONEY_PHOTO_REQUIRED"

            response = upload(client, admin, trubka_id, "money_photo", b"first-photo")
            assert response.status_code == 201, response.text
            first_file = response.json()
            response = client.get(
                f"/api/trubki/{trubka_id}/files/{first_file['id']}",
                headers=noga_user,
            )
            assert response.status_code == 200
            assert response.content == b"first-photo"

            # Повтор того же вида безопасно заменяет единственный файл.
            response = upload(client, admin, trubka_id, "money_photo", b"replacement")
            assert response.status_code == 201, response.text
            replacement = response.json()
            assert replacement["id"] == first_file["id"]
            response = client.get(
                f"/api/trubki/{trubka_id}/files/{replacement['id']}",
                headers=owner,
            )
            assert response.content == b"replacement"
            response = client.get(f"/api/trubki/{trubka_id}", headers=owner)
            assert len(response.json()["files"]) == 1
            print("upload, protected read and replacement ok")

            response = client.post(
                f"/api/trubki/{trubka_id}/recalculation",
                headers=admin,
                json={"amount": 100001},
            )
            assert response.status_code == 200, response.text
            stage = response.json()
            assert stage["status"] == "razgruzhaetsya"
            assert stage["recalculation_amount"] == 100001
            assert stage["noga_payout"] == 10000
            assert stage["remainder"] == 90001
            print("recalculation and automatic unloading status ok")

            # Отчёт требует сначала USDT, затем фото чека.
            response = client.post(f"/api/trubki/{trubka_id}/report", headers=admin)
            assert response.status_code == 409
            assert response.json()["detail"]["code"] == "USDT_REQUIRED"

            response = client.post(
                f"/api/trubki/{trubka_id}/usdt",
                headers=admin,
                json={"amount": "1234.56789012"},
            )
            assert response.status_code == 200, response.text
            paid = response.json()
            assert paid["status"] == "vyplacheno"
            assert str(paid["usdt_received"]) == "1234.56789012"

            response = client.post(f"/api/trubki/{trubka_id}/report", headers=admin)
            assert response.status_code == 409
            assert response.json()["detail"]["code"] == "RECEIPT_PHOTO_REQUIRED"
            response = upload(client, admin, trubka_id, "receipt_photo", b"receipt")
            assert response.status_code == 201, response.text
            response = client.post(f"/api/trubki/{trubka_id}/report", headers=admin)
            assert response.status_code == 200, response.text
            completed = response.json()
            assert completed["report_sent_at"] is not None
            actions = [event["action"] for event in completed["history"]]
            for expected in (
                "created",
                "status_changed",
                "money_photo_uploaded",
                "recalculation_set",
                "usdt_received_set",
                "receipt_photo_uploaded",
                "report_sent",
            ):
                assert expected in actions, actions
            assert actions[-1] == "report_sent", actions
            print("USDT, receipt, report and history ok")

            # После отчёта трубка уходит из операционного списка, но остаётся в БД.
            response = client.get("/api/trubki", headers=admin)
            assert response.status_code == 200, response.text
            assert response.json() == [], response.json()
            response = client.get(f"/api/trubki/{trubka_id}", headers=admin)
            assert response.status_code == 200, response.text
            assert response.json()["id"] == trubka_id

            response = client.get(
                "/api/trubki?include_reported=true&with_total=true&limit=10&offset=0",
                headers=owner,
            )
            assert response.status_code == 200, response.text
            page = response.json()
            assert page["total"] == 1, page
            assert len(page["items"]) == 1
            assert page["items"][0]["id"] == trubka_id

            response = client.get(
                "/api/trubki?include_reported=true",
                headers=admin,
            )
            assert response.status_code == 403, response.text
            print("report hides from ops list, archive stays for stats ok")

            response = client.get("/api/dashboard/summary", headers=owner)
            assert response.status_code == 200, response.text
            summary = response.json()["trubki"]
            assert summary == {
                "total": 0,
                "zacep": 0,
                "zabrali": 0,
                "vyplacheno": 0,
                "srez": 0,
                "razgruzhaetsya": 0,
            }, summary
            print("new dashboard summary ok")

            response = client.get("/api/me", headers=owner)
            assert "stats:read" in response.json()["permissions"]
            response = client.get("/api/me", headers=admin)
            assert "stats:read" not in response.json()["permissions"]
            print("stats:read only for owner/right_hand ok")

            response = client.delete(f"/api/trubki/{trubka_id}", headers=admin)
            assert response.status_code == 204, response.text
            assert not (TEST_UPLOADS / "trubki" / str(trubka_id)).exists()
            print("cascade deletion and disk cleanup ok")

        print("\nALL TRUBKI LIFECYCLE TESTS PASSED")
    finally:
        shutil.rmtree(TEST_UPLOADS, ignore_errors=True)


if __name__ == "__main__":
    main()
