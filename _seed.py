"""Временный сидер демо-данных для визуальной проверки. Удаляется после проверки."""
import json
import urllib.request

BASE = "http://127.0.0.1:8000"


def call(method, path, token=None, payload=None):
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", "Bearer " + token)
    try:
        with urllib.request.urlopen(req) as res:
            body = res.read().decode("utf-8")
            return res.status, json.loads(body) if body else None
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode("utf-8") or "{}")


token = call("POST", "/api/auth/dev", payload={"telegram_id": 111111111, "secret": "dev-only-secret"})[1][
    "access_token"
]

print("list trubki:", call("GET", "/api/trubki", token))

# Чистим прошлые демо-хвосты
for trubka in call("GET", "/api/trubki", token)[1]:
    call("DELETE", "/api/trubki/%d" % trubka["id"], token)
for noga in call("GET", "/api/nogas", token)[1]:
    if noga["name"].startswith("Демо") or "?" in noga["name"]:
        call("DELETE", "/api/nogas/%d" % noga["id"], token)
for city in call("GET", "/api/cities", token)[1]:
    if city["name"].startswith("Демо") or "?" in city["name"]:
        call("DELETE", "/api/cities/%d?detach_nogas=true" % city["id"], token)
for razgruz in call("GET", "/api/razgruzy", token)[1]:
    if razgruz["name"].startswith("Демо") or "?" in razgruz["name"]:
        call("DELETE", "/api/razgruzy/%d?detach_cities=true" % razgruz["id"], token)

status, city = call(
    "POST",
    "/api/cities",
    token,
    {"name": "Демо-Тула", "min_amount": 200000, "min_amount_currency": "RUB"},
)
print("city", status, city.get("name"))
status, razgruz = call(
    "POST", "/api/razgruzy", token, {"name": "Демо-Альфа", "commission_percent": 3.5, "contact": "@demo"}
)
print("razgruz", status, razgruz.get("name"))
call("PATCH", "/api/cities/%d" % city["id"], token, {"razgruz_ids": [razgruz["id"]]})

nogas = []
for name in ("Демо-Пётр", "Демо-Анна"):
    status, noga = call("POST", "/api/nogas", token, {"name": name, "city_id": city["id"]})
    print("noga", status, noga.get("name"))
    call(
        "PATCH",
        "/api/nogas/%d" % noga["id"],
        token,
        {"address": "Тула, Гагарина 3", "phones": ["+7 900 111-22-33"], "telegrams": ["@demo_noga"]},
    )
    nogas.append(noga)

rows = [
    ("zacep", 180000, "zahod"),
    ("vedut", 250000, "taxi"),
    ("srez", 90000, "zahod"),
    ("zabrali", 420000, "taxi"),
    ("razgruzheno", 1250000, "zahod"),
]
for index, (status_value, amount, delivery) in enumerate(rows):
    code, trubka = call(
        "POST",
        "/api/trubki",
        token,
        {
            "status": status_value,
            "city_id": city["id"],
            "noga_id": nogas[index % 2]["id"],
            "razgruz_id": razgruz["id"],
            "amount": amount,
            "amount_currency": "RUB",
            "customer_name": "Иванов Иван Иванович" if index else "Петрова Мария Сергеевна",
            "customer_address": "Тула, улица Ленина, дом %d" % (index + 1),
            "delivery": delivery,
        },
    )
    print("trubka", code, trubka.get("status"), trubka.get("amount"))
