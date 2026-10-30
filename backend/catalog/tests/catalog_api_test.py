#!/usr/bin/env python3
"""
End-to-end check of the model catalog: HTTP API, guest filtering, admin rule,
key handling, import/export, conversations and settings, plus the resolver
and persona rendering (in-process, against the same database).

It WIPES the catalog tables (providers, models, personas) of the target
database, so it refuses to run unless the database name contains "test".

Usage (backend started with the same POSTGRES_DB and ADMIN_EMAILS containing the admin email):

    POSTGRES_DB=llm_chat_catalog_test ADMIN_EMAILS=admin@example.com PORT=8445 python start_backend.py
    POSTGRES_DB=llm_chat_catalog_test python backend/catalog/tests/catalog_api_test.py --base-url https://localhost:8445

Options: --admin-email, --user-email, --skip-network (no provider calls).
Exit code 0 if every check passed.
"""
import argparse
import os
import sys
import time
import warnings
from datetime import date
from pathlib import Path

# Make the backend package importable when run as a script
PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import httpx  # noqa: E402

from backend.config import POSTGRES_DB  # noqa: E402
from backend.database import db  # noqa: E402

TEST_KEY = "sk-test-0123456789abcdefWXYZ"
PREFIX = "zz-test"


class Checks:
    """Collects check results and prints them as they happen."""

    def __init__(self):
        self.passed = 0
        self.failed = []

    def check(self, condition, label, detail=""):
        if condition:
            self.passed += 1
            print(f"  ok    {label}")
        else:
            self.failed.append(label)
            print(f"  FAIL  {label} {detail}")
        return condition

    def section(self, title):
        print(f"\n== {title}")


class Session:
    """An httpx client logged in as one user, sending the CSRF header."""

    def __init__(self, base_url, responses):
        self.client = httpx.Client(base_url=base_url, verify=False, timeout=60)
        self.responses = responses  # (allow_keys, text) of every response, for the key leak check

    def request(self, method, path, allow_keys=False, **kwargs):
        headers = kwargs.pop("headers", {})
        csrf = self.client.cookies.get("csrf_token")
        if csrf:
            headers["X-CSRF-Token"] = csrf
        response = self.client.request(method, path, headers=headers, **kwargs)
        self.responses.append((allow_keys, response.text))
        return response

    def get(self, path, **kwargs):
        return self.request("GET", path, **kwargs)

    def post(self, path, **kwargs):
        return self.request("POST", path, **kwargs)

    def put(self, path, **kwargs):
        return self.request("PUT", path, **kwargs)

    def patch(self, path, **kwargs):
        return self.request("PATCH", path, **kwargs)

    def delete(self, path, **kwargs):
        return self.request("DELETE", path, **kwargs)


def login(base_url, responses, email=None):
    """Mock login (email) or guest login (no email)."""
    session = Session(base_url, responses)
    if email:
        response = session.post("/api/auth/mock-login", json={"email": email})
    else:
        db.reset_guest_usage("127.0.0.1")  # The guest login is rate limited per IP
        response = session.post("/api/auth/guest-login", json={"ip_address": "127.0.0.1"})
    response.raise_for_status()
    return session


def wipe_catalog():
    """Delete every provider (cascades to models) and persona."""
    for persona in db.get_personas():
        db.delete_persona(persona["id"])
    for provider in db.get_llm_providers():
        db.delete_llm_provider(provider["id"])


def provider_body(name, **extra):
    body = {"name": f"{PREFIX} {name}", "kind": "openai_compatible", "privacyTier": "eu", "currency": "EUR"}
    body.update(extra)
    return body


def model_body(provider_id, name, **extra):
    body = {"providerId": provider_id, "displayName": f"{PREFIX} {name}", "modelId": name.lower().replace(" ", "-")}
    body.update(extra)
    return body


def run_admin_rule(c, admin, user, guest, anonymous):
    c.section("Admin rule")
    c.check(admin.get("/api/auth/me").json()["user"]["isAdmin"] is True, "/me isAdmin true for admin")
    me_user = user.get("/api/auth/me").json()
    c.check(me_user["user"]["isAdmin"] is False and me_user["isAdmin"] is False, "/me isAdmin false for user")
    c.check(guest.get("/api/auth/me").json()["user"]["isAdmin"] is False, "/me isAdmin false for guest")

    for method, path, body in [
        ("GET", "/api/admin/providers", None),
        ("POST", "/api/admin/providers", provider_body("denied")),
        ("PUT", "/api/admin/providers/1", {"notes": "x"}),
        ("DELETE", "/api/admin/providers/1", None),
        ("POST", "/api/admin/providers/1/fetch-models", None),
        ("GET", "/api/admin/models", None),
        ("POST", "/api/admin/models", model_body(1, "denied")),
        ("PUT", "/api/admin/models/1", {"notes": "x"}),
        ("DELETE", "/api/admin/models/1", None),
        ("GET", "/api/admin/personas", None),
        ("POST", "/api/admin/personas", {"name": "denied", "systemPrompt": "x"}),
        ("PUT", "/api/admin/personas/1", {"name": "x"}),
        ("DELETE", "/api/admin/personas/1", None),
        ("GET", "/api/admin/catalog/export", None),
        ("POST", "/api/admin/catalog/import", {"version": 1}),
    ]:
        for who, session in (("user", user), ("guest", guest)):
            status = session.request(method, path, json=body).status_code
            c.check(status == 403, f"{method} {path} -> 403 for {who}", f"(got {status})")
    status = anonymous.get("/api/admin/providers").status_code
    c.check(status == 401, "admin endpoint -> 401 without session", f"(got {status})")
    status = anonymous.get("/api/models").status_code
    c.check(status == 401, "GET /api/models -> 401 without session", f"(got {status})")


def run_providers(c, admin):
    c.section("Providers")
    r = admin.post("/api/admin/providers", json=provider_body("Stored", baseUrl="https://example.invalid/v1",
                                                               apiKey=TEST_KEY, notes="test"))
    c.check(r.status_code == 201, "create provider with stored key -> 201", r.text)
    stored = r.json()
    c.check(stored["apiKeySource"] == "stored" and stored["apiKeyMasked"] == "sk-…WXYZ",
            "stored key: apiKeySource 'stored', apiKeyMasked 'sk-…WXYZ'", str(stored))
    c.check("apiKey" not in stored and "apiKeyEncrypted" not in stored, "no key fields in ProviderOut")

    r = admin.post("/api/admin/providers", json=provider_body("Env", apiKeyEnv="OPENAI_API_KEY",
                                                               baseUrl="https://api.openai.com/v1",
                                                               privacyTier="trusted", currency="USD"))
    env = r.json()
    c.check(r.status_code == 201 and env["apiKeySource"] == "env" and env["apiKeyMasked"] is None,
            "env provider: apiKeySource 'env'", r.text)

    r = admin.post("/api/admin/providers", json=provider_body("Unset env", apiKeyEnv="ZZ_NOT_SET_API_KEY"))
    c.check(r.status_code == 201 and r.json()["apiKeySource"] == "none",
            "env var not set: apiKeySource 'none'", r.text)
    unset_env = r.json()

    r = admin.post("/api/admin/providers", json=provider_body("Disabled", enabled=False, privacyTier="local"))
    disabled = r.json()
    c.check(r.status_code == 201 and disabled["enabled"] is False, "create disabled provider")

    c.check(admin.post("/api/admin/providers", json=provider_body("Stored")).status_code == 409,
            "duplicate provider name -> 409")
    c.check(admin.post("/api/admin/providers", json=provider_body("Bad env", apiKeyEnv="POSTGRES_PASSWORD")
                       ).status_code == 400, "apiKeyEnv POSTGRES_PASSWORD -> 400")
    c.check(admin.post("/api/admin/providers", json=provider_body("Bad env 2", apiKeyEnv="CATALOG_SECRET_KEY")
                       ).status_code == 400, "apiKeyEnv CATALOG_SECRET_KEY -> 400")
    c.check(admin.post("/api/admin/providers", json=provider_body("Bad url", baseUrl="ftp://x")
                       ).status_code == 400, "baseUrl ftp:// -> 400")
    c.check(admin.post("/api/admin/providers", json=provider_body("Bad tier", privacyTier="secret")
                       ).status_code == 422, "invalid privacyTier -> 422")
    r = admin.post("/api/admin/providers", json={"kind": "openai_compatible", "privacyTier": "eu", "apiKey": TEST_KEY})
    c.check(r.status_code == 422 and r.json()["detail"][0]["loc"] == ["body", "name"],
            "missing name -> 422 (the key leak check covers the echo)", r.text)

    # Partial update: apiKey left out keeps the key; null clears notes; "" removes the key
    r = admin.put(f"/api/admin/providers/{stored['id']}", json={"notes": None, "currency": None})
    c.check(r.status_code == 200 and r.json()["apiKeySource"] == "stored" and r.json()["notes"] is None
            and r.json()["currency"] == "EUR", "update: key kept, notes cleared, null currency ignored", r.text)
    r = admin.put(f"/api/admin/providers/{unset_env['id']}", json={"apiKey": "sk-ant-api03-abcdefgh9876"})
    c.check(r.json()["apiKeySource"] == "stored" and r.json()["apiKeyMasked"] == "sk-…9876",
            "update: new key stored and masked", r.text)
    r = admin.put(f"/api/admin/providers/{unset_env['id']}", json={"apiKey": ""})
    c.check(r.json()["apiKeySource"] == "none", "update: apiKey '' removes the key", r.text)
    c.check(admin.put("/api/admin/providers/999999", json={"notes": "x"}).status_code == 404,
            "update unknown provider -> 404")

    row = db.get_llm_provider_by_id(stored["id"])
    c.check(row["api_key_encrypted"] and TEST_KEY not in row["api_key_encrypted"], "key encrypted at rest")
    return stored, env, unset_env, disabled


def run_models(c, admin, user, guest, stored, env, disabled):
    c.section("Models")
    created = {}
    for name, provider, extra in [
        ("Guest Model", stored, {"availableToGuests": True, "sortOrder": 20, "temperature": 0.3,
                                 "inputPricePerMtok": 0.18, "outputPricePerMtok": 0.55, "supportsVision": True}),
        ("Beta Model", stored, {"sortOrder": 10, "reasoning": "always", "reasoningPassback": True,
                                "extraBody": {"provider": {"zdr": True}}, "privacyTier": "untrusted"}),
        ("Alpha Model", stored, {"sortOrder": 10}),
        ("Disabled Model", stored, {"enabled": False, "sortOrder": 0, "availableToGuests": True}),
        ("Aux Model", env, {"isAuxiliary": True, "sortOrder": 50}),
        ("Hidden Provider Model", disabled, {"sortOrder": 0, "availableToGuests": True}),
    ]:
        r = admin.post("/api/admin/models", json=model_body(provider["id"], name, **extra))
        c.check(r.status_code == 201, f"create model '{name}' -> 201", r.text)
        created[name] = r.json()

    guest_model = created["Guest Model"]
    c.check(guest_model["providerName"] == stored["name"] and guest_model["currency"] == "EUR"
            and guest_model["effectivePrivacyTier"] == "eu", "ModelOut joins provider name, currency and tier")
    c.check(created["Beta Model"]["effectivePrivacyTier"] == "untrusted", "model privacy tier overrides provider")
    c.check(abs(guest_model["temperature"] - 0.3) < 1e-6 and guest_model["inputPricePerMtok"] == 0.18,
            "temperature and price round-trip as floats", str(guest_model["temperature"]))
    c.check(admin.post("/api/admin/models", json=model_body(stored["id"], "Alpha Model")).status_code == 409,
            "duplicate display name per provider -> 409")
    c.check(admin.post("/api/admin/models", json=model_body(999999, "Orphan")).status_code == 400,
            "model with unknown provider -> 400")
    c.check(admin.post("/api/admin/models", json=model_body(stored["id"], "Bad", reasoning="maybe")
                       ).status_code == 422, "invalid reasoning mode -> 422")

    r = admin.put(f"/api/admin/models/{guest_model['id']}", json={"temperature": None, "notes": "smoke ok"})
    c.check(r.status_code == 200 and r.json()["temperature"] is None and r.json()["notes"] == "smoke ok"
            and r.json()["inputPricePerMtok"] == 0.18, "update: null clears temperature, rest kept", r.text)
    r = admin.put(f"/api/admin/models/{guest_model['id']}", json={"displayName": f"{PREFIX} Alpha Model"})
    c.check(r.status_code == 409, "rename to a taken display name -> 409", r.text)

    names = [m["displayName"] for m in user.get("/api/models").json()]
    expected = [f"{PREFIX} Alpha Model", f"{PREFIX} Beta Model", f"{PREFIX} Guest Model", f"{PREFIX} Aux Model"]
    c.check(names == expected, "GET /api/models (user): enabled only, by sortOrder then name", str(names))
    public = user.get("/api/models").json()[0]
    c.check(set(public) == {"id", "displayName", "description", "providerName", "privacyTier", "supportsTools",
                            "supportsVision", "reasoning", "contextWindow", "inputPricePerMtok",
                            "outputPricePerMtok", "currency"}, "PublicModel fields", str(sorted(public)))
    guest_names = [m["displayName"] for m in guest.get("/api/models").json()]
    c.check(guest_names == [f"{PREFIX} Guest Model"], "GET /api/models (guest): only enabled guest models",
            str(guest_names))
    admin_names = [m["displayName"] for m in admin.get("/api/admin/models").json()]
    c.check(len(admin_names) == 6, "GET /api/admin/models lists disabled ones too", str(admin_names))
    return created


def run_personas(c, admin, user, guest, models):
    c.section("Personas")
    r = admin.post("/api/admin/personas", json={
        "name": f"{PREFIX} Pirate", "description": "Arr",
        "systemPrompt": "Talk like a {{style}} to {{user_name}} in {{language}} on {{date}}. {{unknown}} {{ mood }}",
        "variables": [{"name": "style", "label": "Style", "default": "pirate"},
                      {"name": "mood", "label": "Mood"}],
        "defaultModelId": models["Beta Model"]["id"], "availableToGuests": True, "sortOrder": 1,
    })
    c.check(r.status_code == 201, "create persona -> 201", r.text)
    pirate = r.json()
    r = admin.post("/api/admin/personas", json={"name": f"{PREFIX} Private", "systemPrompt": "Private",
                                                 "sortOrder": 2})
    private = r.json()
    r = admin.post("/api/admin/personas", json={"name": f"{PREFIX} Off", "systemPrompt": "Off", "enabled": False,
                                                 "availableToGuests": True})
    off = r.json()
    c.check(admin.post("/api/admin/personas", json={"name": f"{PREFIX} Pirate", "systemPrompt": "x"}
                       ).status_code == 409, "duplicate persona name -> 409")
    c.check(admin.post("/api/admin/personas", json={"name": "Dup vars", "systemPrompt": "x", "variables": [
        {"name": "a", "label": "A"}, {"name": "a", "label": "A2"}]}).status_code == 400,
        "duplicate variable -> 400")
    c.check(admin.post("/api/admin/personas", json={"name": "Bad var", "systemPrompt": "x", "variables": [
        {"name": "1bad", "label": "A"}]}).status_code == 422, "invalid variable name -> 422")
    c.check(admin.post("/api/admin/personas", json={"name": "Bad model", "systemPrompt": "x",
                                                     "defaultModelId": 999999}).status_code == 400,
            "unknown default model -> 400")

    user_personas = user.get("/api/personas").json()
    c.check([p["name"] for p in user_personas] == [f"{PREFIX} Pirate", f"{PREFIX} Private"],
            "GET /api/personas (user): enabled only", str([p["name"] for p in user_personas]))
    c.check(user_personas[0]["defaultModelId"] == models["Beta Model"]["id"], "user sees persona default model")
    guest_personas = guest.get("/api/personas").json()
    c.check([p["name"] for p in guest_personas] == [f"{PREFIX} Pirate"], "GET /api/personas (guest): guest only")
    c.check(guest_personas[0]["defaultModelId"] is None, "guest: default model hidden if not a guest model")

    r = admin.put(f"/api/admin/personas/{private['id']}", json={"description": "now described"})
    c.check(r.status_code == 200 and r.json()["systemPrompt"] == "Private", "persona partial update")
    return pirate, private, off


def run_conversations_and_settings(c, user, guest, models, personas):
    c.section("Conversations and settings")
    pirate, private, off = personas
    beta, guest_model = models["Beta Model"], models["Guest Model"]

    r = user.post("/api/conversation/create", json={
        "name": "Catalog test", "participants": ["user", "assistant"], "modelId": beta["id"],
        "personaId": pirate["id"], "personaValues": {"style": "robot"}})
    c.check(r.status_code == 201 and r.json()["modelId"] == beta["id"] and r.json()["personaId"] == pirate["id"]
            and r.json()["personaValues"] == {"style": "robot"}, "create conversation with model and persona",
            r.text)
    conversation = r.json()
    cid = conversation["id"]

    r = user.post("/api/conversation/create", json={"name": "Plain", "participants": ["user"]})
    c.check(r.status_code == 201 and r.json()["modelId"] is None and r.json()["personaId"] is None,
            "create conversation without catalog fields (unchanged behavior)", r.text)

    c.check(user.post("/api/conversation/create", json={"name": "x", "participants": [], "modelId": 999999}
                      ).status_code == 400, "unknown model -> 400")
    c.check(user.post("/api/conversation/create", json={"name": "x", "participants": [],
                                                         "modelId": models["Disabled Model"]["id"]}
                      ).status_code == 403, "disabled model -> 403")
    c.check(user.post("/api/conversation/create", json={"name": "x", "participants": [], "personaId": off["id"]}
                      ).status_code == 403, "disabled persona -> 403")
    c.check(guest.post("/api/conversation/create", json={"name": "x", "participants": [], "modelId": beta["id"]}
                       ).status_code == 403, "guest with non-guest model -> 403")
    c.check(guest.post("/api/conversation/create", json={"name": "x", "participants": [],
                                                          "personaId": private["id"]}).status_code == 403,
            "guest with non-guest persona -> 403")
    r = guest.post("/api/conversation/create", json={"name": "g", "participants": [], "modelId": guest_model["id"],
                                                      "personaId": pirate["id"]})
    c.check(r.status_code == 201, "guest with guest model and persona -> 201", r.text)

    r = user.patch(f"/api/conversation/{cid}", json={"name": "Renamed"})
    c.check(r.status_code == 200 and r.json()["name"] == "Renamed" and r.json()["modelId"] == beta["id"],
            "PATCH name only keeps model", r.text)
    r = user.patch(f"/api/conversation/{cid}", json={"modelId": None})
    c.check(r.json()["modelId"] is None and r.json()["name"] == "Renamed" and r.json()["personaId"] == pirate["id"],
            "PATCH modelId null clears the model only", r.text)
    r = user.patch(f"/api/conversation/{cid}", json={"modelId": guest_model["id"], "personaValues": {"style": "poet"}})
    c.check(r.json()["modelId"] == guest_model["id"] and r.json()["personaValues"] == {"style": "poet"},
            "PATCH model and persona values", r.text)
    c.check(user.patch(f"/api/conversation/{cid}", json={"modelId": 999999}).status_code == 400,
            "PATCH unknown model -> 400")

    listed = {conv["id"]: conv for conv in user.get("/api/conversations").json()}
    c.check(listed[cid]["modelId"] == guest_model["id"] and listed[cid]["personaValues"] == {"style": "poet"},
            "GET /api/conversations carries the catalog fields")
    r = user.get(f"/api/conversation/{cid}")
    c.check(r.json()["modelId"] == guest_model["id"] and r.json()["personaId"] == pirate["id"],
            "GET /api/conversation/{id} carries the catalog fields", r.text)

    r = user.patch(f"/api/conversation/{cid}", json={"personaId": None})
    c.check(r.json()["personaId"] is None and r.json()["personaValues"] is None,
            "PATCH personaId null clears persona and values", r.text)

    # Settings
    r = user.put("/api/settings", json={"theme": "dark", "language": "de", "defaultModelId": beta["id"]})
    c.check(r.status_code == 200 and r.json()["defaultModelId"] == beta["id"], "PUT settings with defaultModelId",
            r.text)
    r = user.put("/api/settings", json={"theme": "light", "language": "de"})
    c.check(r.json()["defaultModelId"] == beta["id"] and r.json()["theme"] == "light",
            "PUT settings without defaultModelId keeps it", r.text)
    c.check(user.get("/api/settings").json()["defaultModelId"] == beta["id"], "GET settings returns defaultModelId")
    c.check(user.put("/api/settings", json={"theme": "light", "language": "de",
                                            "defaultModelId": models["Disabled Model"]["id"]}).status_code == 403,
            "PUT settings with disabled model -> 403")
    c.check(user.put("/api/settings", json={"theme": "light", "language": "de", "defaultModelId": 999999}
                     ).status_code == 400, "PUT settings with unknown model -> 400")
    r = user.put("/api/settings", json={"theme": "light", "language": "de", "defaultModelId": None})
    c.check(r.json()["defaultModelId"] is None, "PUT settings defaultModelId null clears it")
    user.put("/api/settings", json={"theme": "auto", "language": "de", "defaultModelId": beta["id"]})
    c.check(guest.get("/api/settings").json().get("defaultModelId") is None, "guest settings: no default model")
    return conversation


def run_message_sync(c, user, user_id, models):
    c.section("Message sync")
    conversation_id = f"{PREFIX}-sync-{int(time.time())}"
    db.create_conversation(conversation_id, user_id, "Sync test", '["user", "assistant"]')
    now = int(time.time() * 1000)
    usage = {"inputTokens": 10, "outputTokens": 5, "reasoningTokens": None, "cachedInputTokens": None,
             "cost": 0.0001, "currency": "EUR"}
    db.create_agent_message(now, conversation_id, "Assistant", now, "Hi", steps=[],
                            model_id=models["Beta Model"]["id"], model_name="Beta copy", usage=usage)
    db.create_agent_message(now + 1, conversation_id, "Assistant", now + 1, "Env", steps=[])
    db.update_agent_message(now + 1, conversation_id, usage={"inputTokens": 1, "outputTokens": 2})
    db.create_message(now + 2, conversation_id, "user", "Hello", now + 2)
    r = user.get(f"/api/conversation/messages/{conversation_id}/{now + 10}/30")
    by_id = {m["id"]: m for m in r.json()}
    c.check(by_id[now]["modelId"] == models["Beta Model"]["id"] and by_id[now]["modelName"] == "Beta copy"
            and by_id[now]["usage"]["cost"] == 0.0001, "agent message carries modelId, modelName, usage", r.text)
    c.check(by_id[now + 1]["modelId"] is None and by_id[now + 1]["usage"]["outputTokens"] == 2,
            "environment-model message: modelId null, usage updated")
    c.check(by_id[now + 2]["usage"] is None and by_id[now + 2]["modelId"] is None, "text message has no usage")
    db.delete_conversation(conversation_id)


def run_fetch_models(c, admin, stored, env):
    c.section("Fetch models (network)")
    r = admin.post(f"/api/admin/providers/{env['id']}/fetch-models")
    ok = c.check(r.status_code == 200 and len(r.json()["models"]) > 0, "OpenAI (api_key_env) -> model list",
                 r.text[:300])
    if ok:
        fetched = r.json()["models"]
        first = fetched[0]["id"]
        admin.post("/api/admin/models", json={"providerId": env["id"], "displayName": f"{PREFIX} Fetched",
                                               "modelId": first, "sortOrder": 100})
        again = {m["id"]: m for m in admin.post(f"/api/admin/providers/{env['id']}/fetch-models").json()["models"]}
        c.check(again[first]["alreadyAdded"] is True and sum(m["alreadyAdded"] for m in again.values()) == 1,
                "alreadyAdded marks the catalog model", first)
        print(f"        OpenAI: {len(fetched)} models, e.g. {[m['id'] for m in fetched[:3]]}")

    r = admin.post("/api/admin/providers", json=provider_body("Cortecs", baseUrl="https://api.cortecs.ai/v1",
                                                               apiKey="dummy-key-not-real"))
    cortecs = r.json()
    r = admin.post(f"/api/admin/providers/{cortecs['id']}/fetch-models")
    if r.status_code == 200:
        models = r.json()["models"]
        with_context = [m for m in models if m["contextWindow"]]
        c.check(len(models) > 0 and len(with_context) > 0, "Cortecs with a dummy key -> public list with context sizes")
        print(f"        Cortecs: {len(models)} models, {len(with_context)} with contextWindow, "
              f"e.g. {[(m['id'], m['contextWindow'], m['ownedBy']) for m in models[:2]]}")
    else:
        c.check(r.status_code == 502, "Cortecs with a dummy key -> clean 502", r.text)
        print(f"        Cortecs did not accept the dummy key: {r.text[:200]}")

    r = admin.post("/api/admin/providers", json=provider_body("Bad key", baseUrl="https://api.openai.com/v1",
                                                               apiKey="sk-invalid-test-key-000000000000"))
    bad = r.json()
    r = admin.post(f"/api/admin/providers/{bad['id']}/fetch-models")
    c.check(r.status_code == 502 and "401" in r.json()["detail"]
            and "sk-invalid-test-key-000000000000" not in r.text, "invalid key -> 502 with the provider's message",
            r.text[:300])
    print(f"        {r.json()['detail'][:160]}")

    r = admin.post("/api/admin/providers", json=provider_body("Anthropic", kind="anthropic", privacyTier="trusted",
                                                               apiKey="sk-ant-invalid-000000000000"))
    anthropic = r.json()
    r = admin.post(f"/api/admin/providers/{anthropic['id']}/fetch-models")
    c.check(r.status_code == 502 and "401" in r.json()["detail"], "Anthropic with invalid key -> 502", r.text[:300])

    r = admin.post("/api/admin/providers", json=provider_body("Unreachable", baseUrl="https://127.0.0.1:9/v1"))
    unreachable = r.json()
    r = admin.post(f"/api/admin/providers/{unreachable['id']}/fetch-models")
    c.check(r.status_code == 502, "unreachable provider -> 502", r.text[:200])
    for provider in (cortecs, bad, anthropic, unreachable):
        admin.delete(f"/api/admin/providers/{provider['id']}")
    c.check(admin.post("/api/admin/providers/999999/fetch-models").status_code == 404, "unknown provider -> 404")


def run_import_export(c, admin, stored):
    c.section("Import and export")
    r = admin.get("/api/admin/catalog/export")
    c.check(r.status_code == 200 and "attachment" in r.headers.get("content-disposition", ""),
            "export -> 200 as a download")
    first = r.json()
    c.check(first["version"] == 1 and all("api_key" not in p for p in first["providers"]),
            "export without keys has no api_key")
    model_entry = next(m for m in first["models"] if m["display_name"] == f"{PREFIX} Beta Model")
    c.check(model_entry["provider"] == stored["name"] and "id" not in model_entry and "provider_id" not in model_entry,
            "models reference providers by name, no ids")
    persona_entry = next(p for p in first["personas"] if p["name"] == f"{PREFIX} Pirate")
    c.check(persona_entry["default_model"] == {"provider": stored["name"], "display_name": f"{PREFIX} Beta Model"},
            "persona default_model by provider and display name", str(persona_entry["default_model"]))

    r = admin.post("/api/admin/catalog/import", json=first)
    result = r.json()
    c.check(r.status_code == 200 and result["errors"] == []
            and result["providers"] == {"created": 0, "updated": len(first["providers"])}
            and result["models"] == {"created": 0, "updated": len(first["models"])}
            and result["personas"] == {"created": 0, "updated": len(first["personas"])},
            "re-import of the export: all updated, nothing created, no errors", str(result))
    second = admin.get("/api/admin/catalog/export").json()
    c.check(second == first, "export -> import -> export is identical")

    with_keys = admin.get("/api/admin/catalog/export?includeKeys=true", allow_keys=True)
    provider_entry = next(p for p in with_keys.json()["providers"] if p["name"] == stored["name"])
    c.check(provider_entry.get("api_key") == TEST_KEY and with_keys.headers.get("cache-control") == "no-store",
            "export with includeKeys has the decrypted key")
    c.check(all("api_key" not in p for p in with_keys.json()["providers"] if p["name"] != stored["name"]),
            "includeKeys only adds stored keys")

    r = admin.post("/api/admin/catalog/import", json={
        "version": 1,
        "providers": [
            {"name": f"{PREFIX} Imported", "kind": "openai_compatible", "base_url": "https://api.example.com/v1",
             "api_key": "sk-imported-key-55556666", "privacy_tier": "eu", "currency": "EUR", "colour": "red"},
            {"name": f"{PREFIX} Broken", "kind": "nope", "privacy_tier": "eu"},
            {"kind": "openai_compatible"},
            "not an object",
        ],
        "models": [
            {"provider": f"{PREFIX} Imported", "display_name": f"{PREFIX} Imported Model", "model_id": "imp-1",
             "input_price_per_mtok": 1.5, "output_price_per_mtok": 3, "available_to_guests": True, "sort_order": 99},
            {"provider": "No such provider", "display_name": "x", "model_id": "x"},
            {"provider": f"{PREFIX} Imported", "display_name": f"{PREFIX} No id"},
        ],
        "personas": [
            {"name": f"{PREFIX} Imported Persona", "system_prompt": "Hi {{user_name}}",
             "default_model": {"provider": f"{PREFIX} Imported", "display_name": f"{PREFIX} Imported Model"}},
            {"name": f"{PREFIX} Dangling", "system_prompt": "x",
             "default_model": {"provider": "Nope", "display_name": "Nope"}},
        ],
    })
    result = r.json()
    print("        import errors:\n          " + "\n          ".join(result["errors"]))
    c.check(result["providers"]["created"] == 1 and result["models"]["created"] == 1
            and result["personas"]["created"] == 2, "import creates the valid entries", str(result))
    c.check(len(result["errors"]) == 7, "import reports each bad entry and unknown key", str(len(result["errors"])))
    providers = {p["name"]: p for p in admin.get("/api/admin/providers").json()}
    imported = providers[f"{PREFIX} Imported"]
    c.check(imported["apiKeySource"] == "stored" and imported["apiKeyMasked"] == "sk-…6666"
            and imported["modelCount"] == 1, "imported api_key is stored encrypted", str(imported))
    personas = {p["name"]: p for p in admin.get("/api/admin/personas").json()}
    imported_model = next(m for m in admin.get("/api/admin/models").json()
                          if m["displayName"] == f"{PREFIX} Imported Model")
    c.check(personas[f"{PREFIX} Imported Persona"]["defaultModelId"] == imported_model["id"],
            "imported persona default model resolved")
    c.check(personas[f"{PREFIX} Dangling"]["defaultModelId"] is None, "unknown default model left unset")

    # Partial upsert: only the given keys change
    r = admin.post("/api/admin/catalog/import", json={"models": [
        {"provider": f"{PREFIX} Imported", "display_name": f"{PREFIX} Imported Model", "sort_order": 98}]})
    updated = next(m for m in admin.get("/api/admin/models").json() if m["id"] == imported_model["id"])
    c.check(r.json()["models"] == {"created": 0, "updated": 1} and updated["sortOrder"] == 98
            and updated["inputPricePerMtok"] == 1.5, "partial upsert changes only the given keys")
    c.check(admin.post("/api/admin/catalog/import", json={"version": 2}).status_code == 400,
            "unsupported file version -> 400")
    c.check(admin.post("/api/admin/catalog/import", json={"providers": {}}).status_code == 400,
            "sections must be lists -> 400")


def run_resolver(c, models, personas, conversation, user_email):
    from backend.catalog import resolver
    from backend.catalog.resolver import ModelNotAllowed, ModelNotAvailable

    c.section("Resolver (in-process)")
    user_row = db.get_user_by_email(user_email)
    user = {"user_id": user_row["id"], "email": user_row["email"], "is_guest": False}
    guest = {"user_id": 0, "email": "guest_x@guest.com", "is_guest": True}
    beta, guest_model = models["Beta Model"], models["Guest Model"]
    alpha, disabled = models["Alpha Model"], models["Disabled Model"]

    config = resolver.resolve_model(user, model_id=alpha["id"])
    c.check(config.id == alpha["id"] and config.api_key == TEST_KEY, "explicit model_id; stored key decrypted")
    try:
        resolver.resolve_model(user, model_id=disabled["id"])
        c.check(False, "explicit disabled model -> ModelNotAllowed")
    except ModelNotAllowed:
        c.check(True, "explicit disabled model -> ModelNotAllowed")
    try:
        resolver.resolve_model(guest, model_id=beta["id"])
        c.check(False, "guest with non-guest model -> ModelNotAllowed")
    except ModelNotAllowed:
        c.check(True, "guest with non-guest model -> ModelNotAllowed")
    try:
        resolver.resolve_model(user, model_id=models["Hidden Provider Model"]["id"])
        c.check(False, "model of disabled provider -> ModelNotAllowed")
    except ModelNotAllowed:
        c.check(True, "model of disabled provider -> ModelNotAllowed")

    c.check(resolver.resolve_model(user, conversation={"model_id": guest_model["id"]}).id == guest_model["id"],
            "conversation model")
    c.check(resolver.resolve_model(user, conversation={"model_id": disabled["id"]}).id == beta["id"],
            "unusable conversation model -> user default")
    c.check(resolver.resolve_model(user, conversation={"model_id": None}).id == beta["id"], "user default model")
    db.upsert_user_settings(user["user_id"], "auto", "de", default_model_id=None)
    c.check(resolver.resolve_model(user).id == alpha["id"], "no default -> first by sort_order, then name")
    c.check(resolver.resolve_model(guest).id == guest_model["id"], "guest -> first guest model")

    config = resolver.resolve_model(user, model_id=beta["id"])
    c.check(config.reasoning == "always" and config.reasoning_passback is True
            and config.extra_body == {"provider": {"zdr": True}} and config.privacy_tier == "untrusted"
            and config.currency == "EUR" and config.base_url == "https://example.invalid/v1",
            "ModelConfig fields from model and provider")
    config = resolver.resolve_model(user, model_id=guest_model["id"])
    c.check(isinstance(config.input_price_per_mtok, float) and config.supports_vision is True,
            "prices as float, capabilities")
    c.check(resolver.get_model_config(disabled["id"]).id == disabled["id"], "get_model_config ignores enabled")
    try:
        resolver.get_model_config(999999)
        c.check(False, "get_model_config unknown -> ModelNotAvailable")
    except ModelNotAvailable:
        c.check(True, "get_model_config unknown -> ModelNotAvailable")
    aux = resolver.resolve_auxiliary_model()
    c.check(aux and aux.id == models["Aux Model"]["id"] and aux.api_key == os.getenv("OPENAI_API_KEY"),
            "auxiliary model with api_key_env key")

    # Stored key wins over api_key_env
    provider_id = beta["providerId"]
    db.update_llm_provider(provider_id, {"api_key_env": "OPENAI_API_KEY"})
    c.check(resolver.get_model_config(beta["id"]).api_key == TEST_KEY, "stored key wins over api_key_env")
    db.update_llm_provider(provider_id, {"api_key_env": None})

    # Guests without guest models get the environment model
    db.update_llm_model(guest_model["id"], {"available_to_guests": False})
    db.update_llm_model(models["Hidden Provider Model"]["id"], {"available_to_guests": False})
    imported = [m for m in db.get_llm_models(guests_only=True)]
    for row in imported:
        db.update_llm_model(row["id"], {"available_to_guests": False})
    config = resolver.resolve_model(guest)
    c.check(config.id is None and config.provider_name.endswith("(environment)"),
            "guest without guest models -> environment model")
    db.update_llm_model(guest_model["id"], {"available_to_guests": True})

    # Empty catalog (everything disabled) -> environment model, then ModelNotAvailable
    enabled_ids = [m["id"] for m in db.get_llm_models(enabled_only=True)]
    for model_id in enabled_ids:
        db.update_llm_model(model_id, {"enabled": False})
    c.check(resolver.resolve_model(user).id is None, "no enabled model -> environment model")
    saved = {k: os.environ.pop(k) for k in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "LLM_PROVIDER") if k in os.environ}
    try:
        resolver.resolve_model(user)
        c.check(False, "nothing left -> ModelNotAvailable")
    except ModelNotAvailable:
        c.check(True, "nothing left -> ModelNotAvailable")
    c.check(resolver.resolve_auxiliary_model() is None, "no auxiliary and no environment model -> None")
    os.environ.update(saved)
    for model_id in enabled_ids:
        db.update_llm_model(model_id, {"enabled": True})

    c.section("Persona rendering (in-process)")
    pirate = personas[0]
    today = resolver.format_date(date.today())
    prompt = resolver.render_persona_prompt(pirate["id"], {"style": "robot", "mood": "  "},
                                            user_name="Test User", language="de")
    c.check(prompt == f"Talk like a robot to Test User in German on {today}. {{{{unknown}}}} ",
            "values, built-ins, blank -> default, unknown kept", repr(prompt))
    prompt = resolver.render_persona_prompt(pirate["id"], None, user_name="X", language="en")
    c.check(prompt.startswith("Talk like a pirate to X in English"), "variable default", repr(prompt))
    c.check(resolver.format_date(date(2026, 10, 30)) == "Friday, 30 October 2026", "date format")
    c.check(resolver.render_persona_prompt(None, {}, user_name="X", language="en") is None, "no persona -> None")
    c.check(resolver.render_persona_prompt(personas[2]["id"], {}, user_name="X", language="en") is None,
            "disabled persona -> None")
    c.check(resolver.user_display_name(user) == user_row["name"] and resolver.user_display_name(guest) == "Guest",
            "user_display_name: name, 'Guest' for guests")
    db.update_user(user["user_id"], name="")
    c.check(resolver.user_display_name(user) == user_email.split("@")[0], "user_display_name: email prefix")
    db.update_user(user["user_id"], name=user_row["name"])
    rendered = resolver.persona_prompt_for_conversation(
        user, {"persona_id": pirate["id"], "persona_values": {"style": "bard"}})
    c.check(rendered.startswith(f"Talk like a bard to {user_row['name']} in German"),
            "persona_prompt_for_conversation uses name and settings language", repr(rendered))
    c.check(resolver.persona_prompt_for_conversation(guest, {"persona_id": personas[1]["id"]}) is None,
            "guest with non-guest persona -> None")


def run_deletes(c, admin, stored, models, personas):
    c.section("Deletes")
    model_count = len(admin.get("/api/admin/models").json())
    r = admin.delete(f"/api/admin/models/{models['Alpha Model']['id']}")
    c.check(r.status_code == 204 and len(admin.get("/api/admin/models").json()) == model_count - 1, "delete model")
    c.check(admin.delete(f"/api/admin/models/{models['Alpha Model']['id']}").status_code == 404,
            "delete deleted model -> 404")
    r = admin.delete(f"/api/admin/providers/{stored['id']}")
    remaining = [m for m in admin.get("/api/admin/models").json() if m["providerId"] == stored["id"]]
    c.check(r.status_code == 204 and remaining == [], "delete provider deletes its models")
    persona = admin.get("/api/admin/personas").json()
    pirate = next(p for p in persona if p["id"] == personas[0]["id"])
    c.check(pirate["defaultModelId"] is None, "persona default model cleared when its model is deleted")
    c.check(admin.delete(f"/api/admin/personas/{personas[1]['id']}").status_code == 204, "delete persona")
    c.check(admin.delete("/api/admin/personas/999999").status_code == 404, "delete unknown persona -> 404")


def main():
    parser = argparse.ArgumentParser(description="End-to-end check of the model catalog API")
    parser.add_argument("--base-url", default="https://localhost:8445")
    parser.add_argument("--admin-email", default="admin@example.com")
    parser.add_argument("--user-email", default="test@example.com")
    parser.add_argument("--skip-network", action="store_true", help="Skip the fetch-models calls to providers")
    args = parser.parse_args()

    if "test" not in POSTGRES_DB:
        print(f"Refusing to run against database '{POSTGRES_DB}': it wipes the catalog. "
              "Use a database whose name contains 'test'.")
        return 2

    warnings.filterwarnings("ignore", message="Unverified HTTPS request")
    print(f"Catalog test against {args.base_url}, database {POSTGRES_DB}")
    wipe_catalog()

    responses = []
    c = Checks()
    admin = login(args.base_url, responses, args.admin_email)
    user = login(args.base_url, responses, args.user_email)
    guest = login(args.base_url, responses)
    anonymous = Session(args.base_url, responses)
    user_id = db.get_user_by_email(args.user_email)["id"]

    run_admin_rule(c, admin, user, guest, anonymous)
    stored, env, unset_env, disabled = run_providers(c, admin)
    models = run_models(c, admin, user, guest, stored, env, disabled)
    personas = run_personas(c, admin, user, guest, models)
    conversation = run_conversations_and_settings(c, user, guest, models, personas)
    run_message_sync(c, user, user_id, models)
    if not args.skip_network:
        run_fetch_models(c, admin, stored, env)
    run_import_export(c, admin, stored)
    run_resolver(c, models, personas, conversation, args.user_email)
    run_deletes(c, admin, stored, models, personas)

    c.section("Key leaks")
    secrets = [TEST_KEY, "sk-ant-api03-abcdefgh9876", "sk-imported-key-55556666"]
    if os.getenv("OPENAI_API_KEY"):
        secrets.append(os.getenv("OPENAI_API_KEY"))
    leaks = [text[:120] for allow, text in responses if not allow for s in secrets if s in text]
    c.check(not leaks, f"no key in any of {len(responses)} responses (except the includeKeys export)",
            f"{len(leaks)} leak(s)")
    c.check(not any("api_key_encrypted" in text or "apiKeyEncrypted" in text for _, text in responses),
            "no encrypted key in any response")

    db.delete_conversation(conversation["id"])
    wipe_catalog()
    print(f"\n{c.passed} passed, {len(c.failed)} failed")
    for label in c.failed:
        print(f"  FAILED: {label}")
    return 0 if not c.failed else 1


if __name__ == "__main__":
    sys.exit(main())
