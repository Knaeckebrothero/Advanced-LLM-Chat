#!/usr/bin/env python3
"""
End-to-end check of the model catalog: HTTP API, guest filtering, admin rule,
read-only providers with keys from the environment, persona tools, seeding
from a catalog file (in-process), import/export, conversations and settings,
the tools stream-generate sends (against a fake model server), plus the
resolver and persona rendering (in-process, against the same database).

It WIPES the catalog tables (providers, models, personas) of the target
database, so it refuses to run unless the database name contains "test".

Usage: create the database once, then start a backend with the same POSTGRES_DB,
ADMIN_EMAILS containing the admin email, and the test key variable (providers
only read keys from the environment):

    POSTGRES_DB=llm_chat_catalog_test MODEL_CATALOG_FILE= python backend/app_init.py --skip-neo4j --no-certs --seed
    POSTGRES_DB=llm_chat_catalog_test ADMIN_EMAILS=admin@example.com AUTH_MODE=mock \
        ZZ_CATALOG_TEST_API_KEY=sk-test-0123456789abcdefWXYZ PORT=8445 python start_backend.py
    POSTGRES_DB=llm_chat_catalog_test python backend/catalog/tests/catalog_api_test.py --base-url https://localhost:8445

Options: --admin-email, --user-email, --skip-network (no provider calls).
Exit code 0 if every check passed.
"""
import argparse
import json
import os
import sys
import tempfile
import time
import warnings
from datetime import date
from pathlib import Path

# Make the backend package importable when run as a script
PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import httpx  # noqa: E402

from backend.catalog import catalog_file  # noqa: E402
from backend.config import POSTGRES_DB  # noqa: E402
from backend.database import db  # noqa: E402
from backend.llm.tools import TOOL_GROUPS  # noqa: E402

# The key variable of the test providers; the backend must have it set to TEST_KEY
KEY_ENV = "ZZ_CATALOG_TEST_API_KEY"
TEST_KEY = "sk-test-0123456789abcdefWXYZ"
# A key in a seed file, which must be ignored (never stored or returned)
FILE_KEY = "sk-imported-key-55556666"
PREFIX = "zz-test"
ROUTER_URL_ENV = "ZZ_CATALOG_TEST_URL"
TOGGLE_KEY_ENV = "ZZ_CATALOG_TOGGLE_API_KEY"

PROVIDER_OUT_FIELDS = {"id", "name", "kind", "baseUrl", "apiKeyEnv", "apiKeySet", "privacyTier", "currency",
                       "defaultHeaders", "notes", "enabled", "modelCount", "createdAt", "updatedAt"}
PERSONA_OUT_FIELDS = {"id", "name", "description", "systemPrompt", "variables", "tools", "availableToGuests",
                      "enabled", "sortOrder"}
PUBLIC_PERSONA_FIELDS = {"id", "name", "description", "systemPrompt", "variables", "tools"}


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
        self.responses = responses  # Text of every response, for the key leak check

    def request(self, method, path, **kwargs):
        headers = kwargs.pop("headers", {})
        csrf = self.client.cookies.get("csrf_token")
        if csrf:
            headers["X-CSRF-Token"] = csrf
        response = self.client.request(method, path, headers=headers, **kwargs)
        self.responses.append(response.text)
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
        response = session.post("/api/auth/guest-login")
    response.raise_for_status()
    return session


def wipe_catalog():
    """Delete every provider (cascades to models) and persona."""
    for persona in db.get_personas():
        db.delete_persona(persona["id"])
    for provider in db.get_llm_providers():
        db.delete_llm_provider(provider["id"])


def provider_entry(name, **extra):
    """A provider entry of a catalog file."""
    entry = {"name": f"{PREFIX} {name}", "kind": "openai_compatible", "privacy_tier": "eu", "currency": "EUR"}
    entry.update(extra)
    return entry


def seed(**sections):
    """Seed the catalog in-process from a temporary catalog file, as app_init does."""
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "catalog.json"
        path.write_text(json.dumps({"version": 1, **sections}), encoding="utf-8")
        return catalog_file.seed_from_file(path)


def providers_by_name(admin):
    return {p["name"]: p for p in admin.get("/api/admin/providers").json()}


MAIN_PROVIDER = provider_entry("Main", base_url="https://example.invalid/v1", api_key_env=KEY_ENV, notes="test",
                               default_headers={"X-Test": "1"})


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
        ("POST", "/api/admin/providers/1/fetch-models", None),
        ("GET", "/api/admin/tools", None),
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
    c.section("Providers (seeded, read-only)")
    result = seed(providers=[
        MAIN_PROVIDER,
        provider_entry("Env", api_key_env="OPENAI_API_KEY", base_url="https://api.openai.com/v1",
                       privacy_tier="trusted", currency="USD", enabled=True),
        provider_entry("Unset env", api_key_env="ZZ_NOT_SET_API_KEY"),
        provider_entry("Disabled", enabled=False, privacy_tier="local"),
        provider_entry("Router", base_url="${" + ROUTER_URL_ENV + "}/v1", privacy_tier="local"),
        provider_entry("Old key", api_key=FILE_KEY),
        provider_entry("Bad env", api_key_env="POSTGRES_PASSWORD"),
        provider_entry("Bad url", base_url="ftp://x"),
        provider_entry("Bad tier", privacy_tier="secret"),
        {"kind": "openai_compatible", "privacy_tier": "eu"},
    ], models=[
        {"provider": f"{PREFIX} Router", "display_name": f"{PREFIX} Router Model", "model_id": "r"},
    ])
    print("        seed errors:\n          " + "\n          ".join(result.errors))
    c.check(result.providers.created == 5 and result.providers.updated == 0,
            "seed creates the valid providers", str(result))
    errors = " | ".join(result.errors)
    c.check(len(result.errors) == 5 and "apiKeyEnv 'POSTGRES_PASSWORD' is not allowed" in errors
            and "must start with http" in errors and "privacy_tier" in errors and "name is required" in errors
            and "api_key ignored" in errors, "seed reports bad entries and the ignored api_key", errors)
    c.check(result.models.created == 0, "provider with an unset ${VAR} is skipped with its models")

    providers = providers_by_name(admin)
    main, env = providers[f"{PREFIX} Main"], providers[f"{PREFIX} Env"]
    unset_env, disabled = providers[f"{PREFIX} Unset env"], providers[f"{PREFIX} Disabled"]
    c.check(set(main) == PROVIDER_OUT_FIELDS, "ProviderOut fields", str(sorted(main)))
    c.check(main["baseUrl"] == "https://example.invalid/v1" and main["apiKeyEnv"] == KEY_ENV
            and main["currency"] == "EUR" and main["defaultHeaders"] == {"X-Test": "1"} and main["notes"] == "test",
            "provider fields from the file", str(main))
    c.check(main["apiKeySet"] is True, f"apiKeySet true when {KEY_ENV} is set in the backend",
            f"(start the backend with {KEY_ENV}=...)")
    c.check(unset_env["apiKeySet"] is False and unset_env["enabled"] is False,
            "key variable unset: apiKeySet false, seeded disabled", str(unset_env))
    c.check(disabled["enabled"] is False and disabled["apiKeySet"] is False, "disabled provider")
    old_key = providers[f"{PREFIX} Old key"]
    row = db.get_llm_provider_by_id(old_key["id"])
    c.check(old_key["apiKeySet"] is False and old_key["apiKeyEnv"] is None and not row.get("api_key_encrypted")
            and FILE_KEY not in json.dumps(row, default=str), "api_key in the file is not stored", str(row))
    c.check(f"{PREFIX} Router" not in providers and f"{PREFIX} Bad env" not in providers,
            "skipped and invalid providers are not created")

    # Read-only: the write endpoints are gone
    status = admin.post("/api/admin/providers", json={"name": "x"}).status_code
    c.check(status == 405, "POST /api/admin/providers is gone", f"(got {status})")
    for method in ("PUT", "DELETE"):
        status = admin.request(method, f"/api/admin/providers/{main['id']}", json={"notes": "x"}).status_code
        c.check(status in (404, 405), f"{method} /api/admin/providers/{{id}} is gone", f"(got {status})")

    # The file is the providers' source of truth: a re-seed replaces the entry
    changed = {key: value for key, value in MAIN_PROVIDER.items() if key != "default_headers"}
    result = seed(providers=[{**changed, "notes": "changed"}])
    main_now = providers_by_name(admin)[f"{PREFIX} Main"]
    c.check(result.providers.updated == 1 and main_now["id"] == main["id"] and main_now["notes"] == "changed"
            and main_now["defaultHeaders"] is None, "re-seed replaces the provider (removed keys cleared)",
            str(main_now))
    seed(providers=[MAIN_PROVIDER])
    return main, env, unset_env, disabled


def run_tools(c, admin):
    c.section("Tools")
    r = admin.get("/api/admin/tools")
    groups = r.json()
    c.check(r.status_code == 200 and [g["id"] for g in groups] == ["files", "web_search", "knowledge_graph"],
            "GET /api/admin/tools lists the three groups", r.text)
    c.check(all(set(g) == {"id", "available", "reason"} for g in groups), "tool group fields", r.text)
    c.check(groups[0] == {"id": "files", "available": True, "reason": None}, "files is always available")
    c.check(all((g["available"] and g["reason"] is None) or (not g["available"] and g["reason"]) for g in groups),
            "unavailable groups say why", r.text)
    print("        " + ", ".join(f"{g['id']}: {'on' if g['available'] else g['reason']}" for g in groups))
    return [g["id"] for g in groups if g["available"]]


def run_models(c, admin, user, guest, main, env, disabled):
    c.section("Models")
    created = {}
    for name, provider, extra in [
        ("Guest Model", main, {"availableToGuests": True, "sortOrder": 20, "temperature": 0.3,
                                 "inputPricePerMtok": 0.18, "outputPricePerMtok": 0.55, "supportsVision": True}),
        ("Beta Model", main, {"sortOrder": 10, "reasoning": "always", "reasoningPassback": True,
                                "extraBody": {"provider": {"zdr": True}}, "privacyTier": "untrusted"}),
        ("Alpha Model", main, {"sortOrder": 10}),
        ("Disabled Model", main, {"enabled": False, "sortOrder": 0, "availableToGuests": True}),
        ("Aux Model", env, {"isAuxiliary": True, "sortOrder": 50}),
        ("Hidden Provider Model", disabled, {"sortOrder": 0, "availableToGuests": True}),
    ]:
        r = admin.post("/api/admin/models", json=model_body(provider["id"], name, **extra))
        c.check(r.status_code == 201, f"create model '{name}' -> 201", r.text)
        created[name] = r.json()

    guest_model = created["Guest Model"]
    c.check(guest_model["providerName"] == main["name"] and guest_model["currency"] == "EUR"
            and guest_model["effectivePrivacyTier"] == "eu", "ModelOut joins provider name, currency and tier")
    c.check(created["Beta Model"]["effectivePrivacyTier"] == "untrusted", "model privacy tier overrides provider")
    c.check(abs(guest_model["temperature"] - 0.3) < 1e-6 and guest_model["inputPricePerMtok"] == 0.18,
            "temperature and price round-trip as floats", str(guest_model["temperature"]))
    c.check(admin.post("/api/admin/models", json=model_body(main["id"], "Alpha Model")).status_code == 409,
            "duplicate display name per provider -> 409")
    c.check(admin.post("/api/admin/models", json=model_body(999999, "Orphan")).status_code == 400,
            "model with unknown provider -> 400")
    c.check(admin.post("/api/admin/models", json=model_body(main["id"], "Bad", reasoning="maybe")
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


def run_personas(c, admin, user, guest):
    c.section("Personas")
    r = admin.post("/api/admin/personas", json={
        "name": f"{PREFIX} Pirate", "description": "Arr",
        "systemPrompt": "Talk like a {{style}} to {{user_name}} in {{language}} on {{date}}. {{unknown}} {{ mood }}",
        "variables": [{"name": "style", "label": "Style", "default": "pirate"},
                      {"name": "mood", "label": "Mood"}],
        "tools": ["web_search", "files", "files"], "availableToGuests": True, "sortOrder": 1,
    })
    c.check(r.status_code == 201, "create persona -> 201", r.text)
    pirate = r.json()
    c.check(set(pirate) == PERSONA_OUT_FIELDS, "PersonaOut fields (no defaultModelId)", str(sorted(pirate)))
    c.check(pirate["tools"] == ["files", "web_search"], "tools deduplicated, in group order", str(pirate["tools"]))
    r = admin.post("/api/admin/personas", json={"name": f"{PREFIX} Private", "systemPrompt": "Private",
                                                 "sortOrder": 2})
    private = r.json()
    c.check(private["tools"] is None, "tools left out -> null (every enabled tool)", r.text)
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
    c.check(admin.post("/api/admin/personas", json={"name": "Bad tools", "systemPrompt": "x",
                                                     "tools": ["files", "shell"]}).status_code == 422,
            "unknown tool group -> 422")

    user_personas = user.get("/api/personas").json()
    c.check([p["name"] for p in user_personas] == [f"{PREFIX} Pirate", f"{PREFIX} Private"],
            "GET /api/personas (user): enabled only", str([p["name"] for p in user_personas]))
    c.check(set(user_personas[0]) == PUBLIC_PERSONA_FIELDS and user_personas[0]["tools"] == ["files", "web_search"],
            "PublicPersona fields carry tools", str(user_personas[0]))
    guest_personas = guest.get("/api/personas").json()
    c.check([p["name"] for p in guest_personas] == [f"{PREFIX} Pirate"], "GET /api/personas (guest): guest only")

    r = admin.put(f"/api/admin/personas/{private['id']}", json={"description": "now described"})
    c.check(r.status_code == 200 and r.json()["systemPrompt"] == "Private" and r.json()["tools"] is None,
            "persona partial update")
    r = admin.put(f"/api/admin/personas/{private['id']}", json={"tools": []})
    c.check(r.status_code == 200 and r.json()["tools"] == [], "update tools [] -> no tools", r.text)
    r = admin.put(f"/api/admin/personas/{private['id']}", json={"sortOrder": 2})
    c.check(r.json()["tools"] == [], "update without tools keeps them", r.text)
    r = admin.put(f"/api/admin/personas/{private['id']}", json={"tools": None})
    c.check(r.json()["tools"] is None, "update tools null -> every enabled tool again", r.text)
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


def run_fetch_models(c, admin, env):
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

    seed(providers=[
        provider_entry("Cortecs", base_url="https://api.cortecs.ai/v1"),
        provider_entry("Bad key", base_url="https://api.openai.com/v1", api_key_env=KEY_ENV),
        provider_entry("Anthropic", kind="anthropic", privacy_tier="trusted", api_key_env=KEY_ENV),
        provider_entry("Unreachable", base_url="https://127.0.0.1:9/v1"),
    ])
    providers = providers_by_name(admin)
    r = admin.post(f"/api/admin/providers/{providers[f'{PREFIX} Cortecs']['id']}/fetch-models")
    if r.status_code == 200:
        models = r.json()["models"]
        with_context = [m for m in models if m["contextWindow"]]
        c.check(len(models) > 0 and len(with_context) > 0, "Cortecs without a key -> public list with context sizes")
        print(f"        Cortecs: {len(models)} models, {len(with_context)} with contextWindow, "
              f"e.g. {[(m['id'], m['contextWindow'], m['ownedBy']) for m in models[:2]]}")
    else:
        c.check(r.status_code == 502, "Cortecs without a key -> clean 502", r.text)
        print(f"        Cortecs did not answer without a key: {r.text[:200]}")

    r = admin.post(f"/api/admin/providers/{providers[f'{PREFIX} Bad key']['id']}/fetch-models")
    c.check(r.status_code == 502 and "401" in r.json()["detail"] and TEST_KEY not in r.text,
            "invalid key -> 502 with the provider's message", r.text[:300])
    print(f"        {r.json()['detail'][:160]}")
    r = admin.post(f"/api/admin/providers/{providers[f'{PREFIX} Anthropic']['id']}/fetch-models")
    c.check(r.status_code == 502 and "401" in r.json()["detail"], "Anthropic with invalid key -> 502", r.text[:300])
    r = admin.post(f"/api/admin/providers/{providers[f'{PREFIX} Unreachable']['id']}/fetch-models")
    c.check(r.status_code == 502, "unreachable provider -> 502", r.text[:200])
    for name in ("Cortecs", "Bad key", "Anthropic", "Unreachable"):
        db.delete_llm_provider(providers[f"{PREFIX} {name}"]["id"])
    c.check(admin.post("/api/admin/providers/999999/fetch-models").status_code == 404, "unknown provider -> 404")


def run_stream_tools(c, admin, user, available_groups):
    """The tools and system prompt stream-generate sends, per persona tool selection."""
    from backend.llm.tests.fake_openai_server import FakeOpenAIServer, chunk, usage_chunk

    c.section("Stream-generate tools (fake model server)")
    everything = sorted(name for group in available_groups for name in TOOL_GROUPS[group])
    with FakeOpenAIServer() as server:
        seed(providers=[provider_entry("Fake", base_url=server.base_url, api_key_env=KEY_ENV, privacy_tier="local")])
        provider = providers_by_name(admin)[f"{PREFIX} Fake"]
        model = admin.post("/api/admin/models", json=model_body(provider["id"], "Fake Model", sortOrder=200)).json()
        personas = []
        for name, prompt, tools in [("No tools", "You only chat.", []), ("Files only", "You read files.", ["files"]),
                                    ("All tools", "You use everything.", None)]:
            body = {"name": f"{PREFIX} {name}", "systemPrompt": prompt}
            if tools is not None:
                body["tools"] = tools
            personas.append(admin.post("/api/admin/personas", json=body).json())

        sent = {}
        for persona in personas:
            r = user.post("/api/conversation/create", json={
                "name": "Tools test", "participants": ["user", "assistant"], "modelId": model["id"],
                "personaId": persona["id"]})
            cid = r.json()["id"]
            now = int(time.time())
            db.create_message(int(time.time() * 1000), cid, "user", "Hello", now)
            server.script(lambda body: [chunk(content="Ahoy"), chunk(finish_reason="stop"), usage_chunk(5, 2)])
            r = user.post("/api/message/stream-generate", json={"conversationId": cid, "aiParticipant": "assistant"})
            request = server.requests[-1] if server.requests else {}
            system = next((m["content"] for m in request.get("messages", []) if m["role"] == "system"), "")
            sent[persona["name"]] = ([t["function"]["name"] for t in request.get("tools", [])],
                                     "tools" in request, system, r.text)
            db.delete_conversation(cid)

        names, has_tools, system, text = sent[f"{PREFIX} No tools"]
        c.check("event: done" in text and "Ahoy" in text, "stream-generate answers through the fake server",
                text[-300:])
        c.check(not has_tools and system == "You only chat.", "persona tools [] -> no tools, prompt without tool "
                "sections", f"{names} {system!r}")
        names, has_tools, system, _ = sent[f"{PREFIX} Files only"]
        c.check(names == ["get_file_content"] and "## File Access" in system and "## Knowledge Graph" not in system,
                "persona tools ['files'] -> only get_file_content", f"{names} {system[:200]!r}")
        names, _, system, _ = sent[f"{PREFIX} All tools"]
        c.check(sorted(names) == everything and system.startswith("You use everything."),
                "persona tools null -> every enabled tool", f"{names} vs {everything}")
        c.check(not server.errors, "fake server saw no unexpected requests", str(server.errors))

    for persona in personas:
        admin.delete(f"/api/admin/personas/{persona['id']}")
    db.delete_llm_provider(provider["id"])


def run_import_export(c, admin, main):
    c.section("Import and export")
    r = admin.get("/api/admin/catalog/export")
    c.check(r.status_code == 200 and "attachment" in r.headers.get("content-disposition", ""),
            "export -> 200 as a download")
    first = r.json()
    c.check(first["version"] == 1 and all(set(p) == set(catalog_file.PROVIDER_EXPORT_COLUMNS)
                                          for p in first["providers"]),
            "export providers without keys", str(first["providers"][:1]))
    model_entry = next(m for m in first["models"] if m["display_name"] == f"{PREFIX} Beta Model")
    c.check(model_entry["provider"] == main["name"] and "id" not in model_entry and "provider_id" not in model_entry,
            "models reference providers by name, no ids")
    persona_entry = next(p for p in first["personas"] if p["name"] == f"{PREFIX} Pirate")
    c.check(persona_entry["tools"] == ["files", "web_search"] and "default_model" not in persona_entry,
            "persona entries carry tools, no default_model", str(persona_entry))

    r = admin.post("/api/admin/catalog/import", json=first)
    result = r.json()
    c.check(r.status_code == 200 and set(result) == {"models", "personas", "errors"}
            and result["errors"] == [catalog_file.PROVIDERS_IGNORED]
            and result["models"] == {"created": 0, "updated": len(first["models"])}
            and result["personas"] == {"created": 0, "updated": len(first["personas"])},
            "re-import of the export: models and personas updated, providers ignored", str(result))
    second = admin.get("/api/admin/catalog/export").json()
    c.check(second == first, "export -> import -> export is identical")

    # The export also works as MODEL_CATALOG_FILE: providers replaced, the rest kept
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "export.json"
        path.write_text(json.dumps(first), encoding="utf-8")
        seeded = catalog_file.seed_from_file(path)
    c.check(seeded.errors == [] and seeded.providers.updated == len(first["providers"])
            and seeded.models.kept == len(first["models"]) and seeded.personas.kept == len(first["personas"])
            and seeded.models.created == 0 and seeded.personas.created == 0,
            "export seeds as a catalog file: providers updated, models and personas kept", str(seeded))
    c.check(admin.get("/api/admin/catalog/export").json() == first, "seeding the export changes nothing")

    r = admin.post("/api/admin/catalog/import", json={
        "version": 1,
        "colour": "red",
        "providers": [
            {"name": f"{PREFIX} Imported", "kind": "openai_compatible", "base_url": "https://api.example.com/v1",
             "privacy_tier": "eu", "currency": "EUR"},
            {"kind": "openai_compatible"},
        ],
        "models": [
            {"provider": main["name"], "display_name": f"{PREFIX} Imported Model", "model_id": "imp-1",
             "input_price_per_mtok": 1.5, "output_price_per_mtok": 3, "available_to_guests": True, "sort_order": 99,
             "colour": "red"},
            {"provider": "No such provider", "display_name": "x", "model_id": "x"},
            {"provider": main["name"], "display_name": f"{PREFIX} No id"},
            "not an object",
        ],
        "personas": [
            {"name": f"{PREFIX} Imported Persona", "system_prompt": "Hi {{user_name}}", "tools": ["web_search"]},
            {"name": f"{PREFIX} Old export", "system_prompt": "x",
             "default_model": {"provider": main["name"], "display_name": f"{PREFIX} Imported Model"}},
            {"name": f"{PREFIX} Bad tools", "system_prompt": "x", "tools": ["bogus"]},
        ],
    })
    result = r.json()
    print("        import errors:\n          " + "\n          ".join(result["errors"]))
    c.check(result["models"]["created"] == 1 and result["personas"]["created"] == 2,
            "import creates the valid entries", str(result))
    c.check(len(result["errors"]) == 8 and result["errors"].count(catalog_file.PROVIDERS_IGNORED) == 1,
            "import reports each bad entry and unknown key, providers once", str(len(result["errors"])))
    c.check(any("provider 'No such provider' not found" in e for e in result["errors"]),
            "model with an unknown provider is reported")
    providers = providers_by_name(admin)
    c.check(f"{PREFIX} Imported" not in providers and providers[main["name"]]["modelCount"] >= 1,
            "import does not create providers")
    personas = {p["name"]: p for p in admin.get("/api/admin/personas").json()}
    c.check(personas[f"{PREFIX} Imported Persona"]["tools"] == ["web_search"], "imported persona tools")
    c.check(personas[f"{PREFIX} Old export"]["tools"] is None and f"{PREFIX} Bad tools" not in personas,
            "old default_model key ignored, invalid tools rejected")
    imported_model = next(m for m in admin.get("/api/admin/models").json()
                          if m["displayName"] == f"{PREFIX} Imported Model")

    # Partial upsert: only the given keys change
    r = admin.post("/api/admin/catalog/import", json={"models": [
        {"provider": main["name"], "display_name": f"{PREFIX} Imported Model", "sort_order": 98}]})
    updated = next(m for m in admin.get("/api/admin/models").json() if m["id"] == imported_model["id"])
    c.check(r.json()["models"] == {"created": 0, "updated": 1} and updated["sortOrder"] == 98
            and updated["inputPricePerMtok"] == 1.5, "partial upsert changes only the given keys")
    c.check(admin.post("/api/admin/catalog/import", json={"version": 2}).status_code == 400,
            "unsupported file version -> 400")
    c.check(admin.post("/api/admin/catalog/import", json={"providers": {}}).status_code == 400,
            "sections must be lists -> 400")


def run_seeding(c, admin, main, models, personas):
    from backend.config import MODEL_CATALOG_FILE

    c.section("Seeding never overwrites app edits (in-process)")
    guest_model, pirate = models["Guest Model"], personas[0]
    before = next(m for m in admin.get("/api/admin/models").json() if m["id"] == guest_model["id"])
    result = seed(providers=[MAIN_PROVIDER], models=[
        {"provider": main["name"], "display_name": guest_model["displayName"], "model_id": "changed-id",
         "description": "from the file", "sort_order": 1},
        {"provider": main["name"], "display_name": f"{PREFIX} Seeded Model", "model_id": "seeded", "sort_order": 300},
    ], personas=[
        {"name": pirate["name"], "system_prompt": "Changed by the file", "tools": []},
        {"name": f"{PREFIX} Seeded Persona", "system_prompt": "Seeded", "tools": ["files"], "colour": "red"},
    ])
    c.check(result.providers.updated == 1 and result.models.created == 1 and result.models.kept == 1
            and result.personas.created == 1 and result.personas.kept == 1,
            "seed creates missing models and personas, keeps existing ones", str(result))
    c.check(result.errors == [f"personas[1] ({PREFIX} Seeded Persona): unknown key 'colour' ignored"],
            "seed reports unknown keys", str(result.errors))
    after = next(m for m in admin.get("/api/admin/models").json() if m["id"] == guest_model["id"])
    c.check(after == before, "existing model untouched by the seed", str(after))
    pirate_now = next(p for p in admin.get("/api/admin/personas").json() if p["id"] == pirate["id"])
    c.check(pirate_now["systemPrompt"] == pirate["systemPrompt"] and pirate_now["tools"] == ["files", "web_search"],
            "existing persona untouched by the seed", str(pirate_now))
    seeded = {p["name"]: p for p in admin.get("/api/admin/personas").json()}[f"{PREFIX} Seeded Persona"]
    c.check(seeded["tools"] == ["files"], "new persona from the seed has its tools")

    # An edit in the app survives the next deploy
    admin.put(f"/api/admin/models/{guest_model['id']}", json={"description": "edited in the app"})
    seed(providers=[MAIN_PROVIDER], models=[
        {"provider": main["name"], "display_name": guest_model["displayName"], "model_id": "x",
         "description": "from the file"}])
    edited = next(m for m in admin.get("/api/admin/models").json() if m["id"] == guest_model["id"])
    c.check(edited["description"] == "edited in the app", "app edit kept on re-seed", str(edited["description"]))
    admin.put(f"/api/admin/models/{guest_model['id']}", json={"description": before["description"]})

    # ${VAR} in base_url: skipped while unset, filled in once set
    router = provider_entry("Router", base_url="${" + ROUTER_URL_ENV + "}/v1", privacy_tier="local")
    router_model = {"provider": router["name"], "display_name": f"{PREFIX} Router Model", "model_id": "r",
                    "sort_order": 300}
    os.environ.pop(ROUTER_URL_ENV, None)
    result = seed(providers=[router], models=[router_model])
    c.check(result.providers.created == 0 and result.models.created == 0 and result.errors == []
            and router["name"] not in providers_by_name(admin), "unset ${VAR}: provider and its models skipped")
    os.environ[ROUTER_URL_ENV] = "https://router.invalid"
    result = seed(providers=[router], models=[router_model])
    seeded_router = providers_by_name(admin).get(router["name"]) or {}
    c.check(result.providers.created == 1 and result.models.created == 1
            and seeded_router.get("baseUrl") == "https://router.invalid/v1", "set ${VAR}: base URL filled in",
            str(seeded_router))
    os.environ.pop(ROUTER_URL_ENV, None)

    # A provider without its key starts disabled, is enabled once the key is set; `enabled` in the file wins
    toggle = provider_entry("Toggle", api_key_env=TOGGLE_KEY_ENV)
    os.environ.pop(TOGGLE_KEY_ENV, None)
    seed(providers=[toggle])
    off = providers_by_name(admin)[toggle["name"]]["enabled"]
    os.environ[TOGGLE_KEY_ENV] = "sk-toggle-test-0000"
    seed(providers=[toggle])
    on = providers_by_name(admin)[toggle["name"]]["enabled"]
    seed(providers=[{**toggle, "enabled": False}])
    forced = providers_by_name(admin)[toggle["name"]]["enabled"]
    os.environ.pop(TOGGLE_KEY_ENV, None)
    c.check(off is False and on is True and forced is False,
            "key unset -> disabled, set -> enabled, explicit enabled wins", f"{off} {on} {forced}")

    for name in (router["name"], toggle["name"]):
        provider = db.get_llm_provider_by_name(name)
        if provider:
            db.delete_llm_provider(provider["id"])
    seeded_model = next(m for m in admin.get("/api/admin/models").json()
                        if m["displayName"] == f"{PREFIX} Seeded Model")
    admin.delete(f"/api/admin/models/{seeded_model['id']}")
    admin.delete(f"/api/admin/personas/{seeded['id']}")

    # The repository's catalog file is the default seed
    if "MODEL_CATALOG_FILE" not in os.environ:
        c.check(MODEL_CATALOG_FILE == "catalog/models.json", "MODEL_CATALOG_FILE defaults to catalog/models.json")
    repo_file = json.loads(catalog_file.resolve_catalog_path("catalog/models.json").read_text(encoding="utf-8"))
    translator = next(p for p in repo_file["personas"] if p["name"] == "Translator")
    c.check(translator.get("tools") == [] and all("default_model" not in p for p in repo_file["personas"]),
            "catalog/models.json: Translator has no tools, no default_model")


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
    c.check(config.id == alpha["id"] and config.api_key == TEST_KEY, "explicit model_id; key from api_key_env")
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

    # Keys only come from the environment
    c.check(resolver.provider_api_key({"name": "x", "api_key_env": None}) is None
            and resolver.provider_api_key({"name": "x", "api_key_env": "ZZ_NOT_SET_API_KEY"}) is None
            and resolver.api_key_set({"api_key_env": KEY_ENV}) is True
            and resolver.api_key_set({"api_key_env": "ZZ_NOT_SET_API_KEY"}) is False,
            "no key without a set api_key_env variable")

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

    c.section("Persona tool groups (in-process)")
    pirate_id, private_id, off_id = (p["id"] for p in personas)
    c.check(resolver.persona_tool_groups(user, {"persona_id": pirate_id}) == ["files", "web_search"],
            "persona with a selection -> its groups")
    c.check(resolver.persona_tool_groups(user, {"persona_id": private_id}) is None, "tools null -> None (all)")
    db.update_persona(private_id, {"tools": []})
    c.check(resolver.persona_tool_groups(user, {"persona_id": private_id}) == [], "tools [] -> []")
    c.check(resolver.persona_tool_groups(guest, {"persona_id": private_id}) is None,
            "guest with non-guest persona -> None")
    db.update_persona(private_id, {"tools": None})
    c.check(resolver.persona_tool_groups(user, {"persona_id": off_id}) is None, "disabled persona -> None")
    c.check(resolver.persona_tool_groups(user, {"persona_id": None}) is None
            and resolver.persona_tool_groups(user, None) is None, "no persona -> None")


def run_deletes(c, admin, main, models, personas):
    c.section("Deletes")
    model_count = len(admin.get("/api/admin/models").json())
    r = admin.delete(f"/api/admin/models/{models['Alpha Model']['id']}")
    c.check(r.status_code == 204 and len(admin.get("/api/admin/models").json()) == model_count - 1, "delete model")
    c.check(admin.delete(f"/api/admin/models/{models['Alpha Model']['id']}").status_code == 404,
            "delete deleted model -> 404")
    db.delete_llm_provider(main["id"])
    remaining = [m for m in admin.get("/api/admin/models").json() if m["providerId"] == main["id"]]
    c.check(remaining == [], "deleting a provider in the database deletes its models")
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
    os.environ.setdefault(KEY_ENV, TEST_KEY)  # For the in-process resolver; the backend needs it too
    wipe_catalog()

    responses = []
    c = Checks()
    admin = login(args.base_url, responses, args.admin_email)
    user = login(args.base_url, responses, args.user_email)
    guest = login(args.base_url, responses)
    anonymous = Session(args.base_url, responses)
    user_id = db.get_user_by_email(args.user_email)["id"]

    run_admin_rule(c, admin, user, guest, anonymous)
    main_provider, env, unset_env, disabled = run_providers(c, admin)
    available_groups = run_tools(c, admin)
    models = run_models(c, admin, user, guest, main_provider, env, disabled)
    personas = run_personas(c, admin, user, guest)
    conversation = run_conversations_and_settings(c, user, guest, models, personas)
    run_message_sync(c, user, user_id, models)
    run_stream_tools(c, admin, user, available_groups)
    if not args.skip_network:
        run_fetch_models(c, admin, env)
    run_import_export(c, admin, main_provider)
    run_seeding(c, admin, main_provider, models, personas)
    run_resolver(c, models, personas, conversation, args.user_email)
    run_deletes(c, admin, main_provider, models, personas)

    c.section("Key leaks")
    secrets = [TEST_KEY, FILE_KEY, "sk-toggle-test-0000"]
    if os.getenv("OPENAI_API_KEY"):
        secrets.append(os.getenv("OPENAI_API_KEY"))
    leaks = [text[:120] for text in responses for secret in secrets if secret in text]
    c.check(not leaks, f"no key in any of {len(responses)} responses", f"{len(leaks)} leak(s)")
    c.check(not any(field in text for text in responses
                    for field in ("api_key_encrypted", "apiKeyEncrypted", "apiKeyMasked", "apiKeySource")),
            "no stored-key fields in any response")

    db.delete_conversation(conversation["id"])
    wipe_catalog()
    print(f"\n{c.passed} passed, {len(c.failed)} failed")
    for label in c.failed:
        print(f"  FAILED: {label}")
    return 0 if not c.failed else 1


if __name__ == "__main__":
    sys.exit(main())
