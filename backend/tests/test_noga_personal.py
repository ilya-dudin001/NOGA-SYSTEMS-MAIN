"""Личные данные ног, файлы и привязка ног к городу.

Запуск из backend/: python tests/test_noga_personal.py
"""

import os
import pathlib
import shutil
import sys

TEST_DB = pathlib.Path("data/test_noga_personal.db")
UPLOADS = pathlib.Path("data/test_uploads")
if TEST_DB.exists():
    TEST_DB.unlink()
shutil.rmtree(UPLOADS, ignore_errors=True)

os.environ["BOT_POLLING_ENABLED"] = "false"
os.environ["GEOCODE_ENABLED"] = "false"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./data/test_noga_personal.db"
os.environ["UPLOADS_DIR"] = "./data/test_uploads"
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

PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
    "890000000a49444154789c6300010000050001"
)
MP4 = b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 32


def token(client: TestClient, telegram_id: int) -> str:
    r = client.post(
        "/api/auth/dev", json={"telegram_id": telegram_id, "secret": "dev-only-secret"}
    )
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def stored_files(noga_id: int) -> list[pathlib.Path]:
    folder = UPLOADS / "nogas" / str(noga_id)
    return sorted(p for p in folder.iterdir() if p.is_file()) if folder.is_dir() else []


def main() -> None:
    with TestClient(app) as client:
        owner = {"Authorization": "Bearer " + token(client, OWNER)}
        r = client.post(
            "/api/users",
            headers=owner,
            json={"telegram_id": ADMIN_USER, "role": "admin", "display_name": "admin"},
        )
        assert r.status_code == 201, r.text
        admin = {"Authorization": "Bearer " + token(client, ADMIN_USER)}

        # ---------- привязка ног к городу ----------

        r = client.post("/api/cities", headers=owner, json={"name": "Тула"})
        assert r.status_code == 201, r.text
        tula = r.json()["id"]

        r = client.post("/api/nogas", headers=owner, json={"name": "Иван", "city_id": tula})
        assert r.status_code == 201, r.text
        ivan = r.json()["id"]

        # Нога без города: появляется в списке, но города нет
        r = client.post("/api/nogas", headers=owner, json={"name": "Максим"})
        assert r.status_code == 201 and r.json()["city_id"] is None, r.text
        maxim = r.json()["id"]

        detail = client.get(f"/api/cities/{tula}", headers=owner).json()
        assert [n["name"] for n in detail["nogas"]] == ["Иван"], detail["nogas"]
        assert detail["nogas_count"] == 1
        print("noga created with city is attached automatically ok")

        # Прикрепляем Максима к Туле через форму города
        r = client.patch(
            f"/api/cities/{tula}", headers=owner, json={"noga_ids": [ivan, maxim]}
        )
        assert r.status_code == 200, r.text
        assert sorted(n["name"] for n in r.json()["nogas"]) == ["Иван", "Максим"], r.text
        print("attach noga from city form ok")

        # Открепляем Ивана: город остаётся только у Максима
        r = client.patch(f"/api/cities/{tula}", headers=owner, json={"noga_ids": [maxim]})
        assert r.status_code == 200, r.text
        assert [n["name"] for n in r.json()["nogas"]] == ["Максим"], r.text
        r = client.get(f"/api/nogas/{ivan}", headers=owner).json()
        assert r["city_id"] is None and r["city_name"] is None, r
        print("detach noga from city form ok")

        # Явный null в PATCH ноги тоже открепляет, а город возвращается по city_id
        r = client.patch(f"/api/nogas/{ivan}", headers=owner, json={"city_id": tula})
        assert r.status_code == 200 and r.json()["city_name"] == "Тула", r.text
        r = client.patch(f"/api/nogas/{ivan}", headers=owner, json={"city_id": None})
        assert r.status_code == 200 and r.json()["city_id"] is None, r.text
        print("patch city_id null detaches ok")

        # Тёзки: нельзя собрать в городе двух ног с одинаковым именем
        r = client.post("/api/nogas", headers=owner, json={"name": "Максим"})
        assert r.status_code == 201, r.text
        maxim_two = r.json()["id"]
        r = client.patch(
            f"/api/cities/{tula}", headers=owner, json={"noga_ids": [maxim, maxim_two]}
        )
        assert r.status_code == 409, r.text
        r = client.patch(f"/api/nogas/{maxim_two}", headers=owner, json={"city_id": tula})
        assert r.status_code == 409, r.text
        print("duplicate names in one city -> 409 ok")

        # Неизвестная нога в составе города
        r = client.patch(f"/api/cities/{tula}", headers=owner, json={"noga_ids": [9999]})
        assert r.status_code == 404, r.text
        print("unknown noga id -> 404 ok")

        # Город с ногами не удаляется, без ног — удаляется
        r = client.post("/api/cities", headers=owner, json={"name": "Самара"})
        samara = r.json()["id"]
        r = client.patch(f"/api/cities/{samara}", headers=owner, json={"noga_ids": [maxim_two]})
        assert r.status_code == 200, r.text
        assert client.delete(f"/api/cities/{samara}", headers=owner).status_code == 409
        assert (
            client.patch(f"/api/cities/{samara}", headers=owner, json={"noga_ids": []}).status_code
            == 200
        )
        assert client.delete(f"/api/cities/{samara}", headers=owner).status_code == 204
        print("city with nogas -> 409, after detach -> 204 ok")

        # Города можно задать сразу при создании
        r = client.post(
            "/api/cities", headers=owner, json={"name": "Казань", "noga_ids": [maxim_two]}
        )
        assert r.status_code == 201, r.text
        assert [n["name"] for n in r.json()["nogas"]] == ["Максим"], r.text
        kazan = r.json()["id"]
        print("noga_ids on city create ok")

        # ---------- история городов ----------

        # Максим-второй: заведён без города, прикреплён к Самаре, потом к Казани
        r = client.get(f"/api/nogas/{maxim_two}", headers=owner).json()
        assert r["initial_city_name"] == "Самара", r
        assert r["last_city_name"] == "Казань", r
        print("city history: first attach remembered, last overwritten ok")

        # Переименование города подтягивает снимки
        r = client.patch(f"/api/cities/{kazan}", headers=owner, json={"name": "Казань-2"})
        assert r.status_code == 200, r.text
        r = client.get(f"/api/nogas/{maxim_two}", headers=owner).json()
        assert r["last_city_name"] == "Казань-2", r
        print("city rename updates history ok")

        # Удаление города с ногами: сначала вопрос, потом принудительное удаление
        r = client.delete(f"/api/cities/{kazan}", headers=owner)
        assert r.status_code == 409, r.text
        detail = r.json()["detail"]
        assert detail["code"] == "CITY_HAS_NOGAS", detail
        assert detail["nogas"] == ["Максим"], detail
        assert "Максим" in detail["message"], detail

        r = client.delete(f"/api/cities/{kazan}?detach_nogas=true", headers=owner)
        assert r.status_code == 204, r.text
        assert client.get(f"/api/cities/{kazan}", headers=owner).status_code == 404

        r = client.get(f"/api/nogas/{maxim_two}", headers=owner).json()
        assert r["city_id"] is None and r["city_name"] is None, r
        assert r["initial_city_name"] == "Самара", r
        assert r["last_city_name"] == "Казань-2", "история должна пережить удаление города"
        print("delete city with detach_nogas keeps nogas and their history ok")

        # ---------- личные данные ----------

        r = client.patch(
            f"/api/nogas/{ivan}",
            headers=owner,
            json={
                "address": "  Тула,   Ленина 1  ",
                "phones": ["+7 900 000-00-00", "", "+7 900 000-00-00", "+7 911 111-11-11"],
                "telegrams": ["@ivan", "@ivan_work"],
            },
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["address"] == "Тула, Ленина 1", body
        assert body["phones"] == ["+7 900 000-00-00", "+7 911 111-11-11"], body
        assert body["telegrams"] == ["@ivan", "@ivan_work"], body
        assert body["has_personal_access"] is True
        print("personal data saved and normalized ok")

        # Личные данные не трогаются, если поля не переданы
        r = client.patch(f"/api/nogas/{ivan}", headers=owner, json={"is_test": True})
        assert r.status_code == 200 and r.json()["address"] == "Тула, Ленина 1", r.text
        # Пустой список чистит контакты, null — адрес
        r = client.patch(
            f"/api/nogas/{ivan}", headers=owner, json={"phones": [], "address": None}
        )
        assert r.status_code == 200, r.text
        assert r.json()["phones"] == [] and r.json()["address"] is None, r.text
        print("patch semantics for personal fields ok")

        # ---------- файлы ----------

        r = client.post(
            f"/api/nogas/{ivan}/files",
            headers=owner,
            data={"kind": "passport"},
            files={"file": ("passport.png", PNG, "image/png")},
        )
        assert r.status_code == 201, r.text
        passport_file = r.json()
        assert passport_file["kind"] == "passport"
        assert passport_file["size_bytes"] == len(PNG)
        assert passport_file["uploaded_by_name"], passport_file

        # HEIC с iOS приходит без внятного content-type — ориентируемся на расширение
        r = client.post(
            f"/api/nogas/{ivan}/files",
            headers=owner,
            data={"kind": "passport_selfie"},
            files={"file": ("selfie.HEIC", PNG, "application/octet-stream")},
        )
        assert r.status_code == 201, r.text
        assert r.json()["content_type"] == "image/heic", r.text

        r = client.post(
            f"/api/nogas/{ivan}/files",
            headers=owner,
            data={"kind": "face_video"},
            files={"file": ("face.mov", MP4, "video/quicktime")},
        )
        assert r.status_code == 201, r.text
        print("upload png / heic / mov ok")

        detail = client.get(f"/api/nogas/{ivan}", headers=owner).json()
        assert sorted(f["kind"] for f in detail["files"]) == [
            "face_video",
            "passport",
            "passport_selfie",
        ], detail["files"]
        assert len(stored_files(ivan)) == 3, stored_files(ivan)
        print("files listed in detail and stored on disk ok")

        # Скачивание отдаёт байты и тип
        r = client.get(f"/api/nogas/{ivan}/files/{passport_file['id']}", headers=owner)
        assert r.status_code == 200, r.text
        assert r.content == PNG
        assert r.headers["content-type"].startswith("image/png"), r.headers
        print("download ok")

        # Чужой файл по другому id ноги не отдаётся
        r = client.get(f"/api/nogas/{maxim}/files/{passport_file['id']}", headers=owner)
        assert r.status_code == 404, r.text

        # Неподходящие форматы
        r = client.post(
            f"/api/nogas/{ivan}/files",
            headers=owner,
            data={"kind": "passport"},
            files={"file": ("scan.txt", b"hello", "text/plain")},
        )
        assert r.status_code == 400, r.text
        r = client.post(
            f"/api/nogas/{ivan}/files",
            headers=owner,
            data={"kind": "face_video"},
            files={"file": ("photo.png", PNG, "image/png")},
        )
        assert r.status_code == 400, r.text
        r = client.post(
            f"/api/nogas/{ivan}/files",
            headers=owner,
            data={"kind": "passport"},
            files={"file": ("empty.png", b"", "image/png")},
        )
        assert r.status_code == 400, r.text
        assert len(stored_files(ivan)) == 3, "битые загрузки не должны оставлять файлы"
        print("bad uploads rejected without leftovers ok")

        # Удаление файла чистит и диск
        r = client.delete(f"/api/nogas/{ivan}/files/{passport_file['id']}", headers=owner)
        assert r.status_code == 204, r.text
        assert len(stored_files(ivan)) == 2, stored_files(ivan)
        assert (
            client.delete(f"/api/nogas/{ivan}/files/{passport_file['id']}", headers=owner).status_code
            == 404
        )
        print("delete file ok")

        # ---------- права ----------

        me_admin = client.get("/api/me", headers=admin).json()
        assert "nogas:read" in me_admin["permissions"]
        # Личные данные чужой ноги админу нужны: если нога соседа пропала со
        # связи, с ней надо связаться напрямую. Править её при этом нельзя.
        assert "nogas:personal" in me_admin["permissions"]
        assert "nogas:all" not in me_admin["permissions"]

        detail = client.get(f"/api/nogas/{ivan}", headers=admin).json()
        assert detail["has_personal_access"] is True, detail
        assert detail["telegrams"] and detail["files"], detail
        assert detail["can_manage"] is False, detail
        assert detail["name"] == "Иван"

        r = client.patch(f"/api/nogas/{ivan}", headers=admin, json={"address": "Куда-то"})
        assert r.status_code == 403, r.text
        r = client.post(
            f"/api/nogas/{ivan}/files",
            headers=admin,
            data={"kind": "passport"},
            files={"file": ("passport.png", PNG, "image/png")},
        )
        assert r.status_code == 403, r.text
        files_left = client.get(f"/api/nogas/{ivan}", headers=owner).json()["files"]
        r = client.get(f"/api/nogas/{ivan}/files/{files_left[0]['id']}", headers=admin)
        assert r.status_code == 200, r.text
        print("admin: reads foreign noga with personal data, cannot edit ok")

        me_owner = client.get("/api/me", headers=owner).json()
        assert "nogas:personal" in me_owner["permissions"]

        # ---------- удаление ноги вместе с файлами ----------

        assert client.delete(f"/api/nogas/{ivan}", headers=owner).status_code == 204
        assert not (UPLOADS / "nogas" / str(ivan)).exists(), "каталог файлов должен исчезнуть"
        assert client.get(f"/api/nogas/{ivan}", headers=owner).status_code == 404
        print("delete noga removes files ok")

    print("NOGA PERSONAL TESTS OK")


if __name__ == "__main__":
    main()
