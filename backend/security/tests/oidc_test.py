#!/usr/bin/env python3
"""
End-to-end check of the login through an OIDC provider (AUTH_MODE=oidc) against a real
Keycloak: the login and its callback, admin roles, linking existing users by verified
email, refused and tampered logins, logout at the provider, session refresh, and that
mock and older sessions stop counting. Some checks run in-process (required role,
admin emails, settings), against the same database.

It creates users in the Keycloak realm (deleted at the end) and adds the backend's
callback and FRONTEND_URL to the client's allowed redirects. It refuses to run unless
the database name contains "test".

Usage, with the bundled Keycloak (docker/docker-compose.keycloak.yml) and its secrets:

    cd docker && docker compose -f docker-compose.yml -f docker-compose.keycloak.yml up -d keycloak && cd ..
    POSTGRES_DB=llm_chat_auth_test python backend/app_init.py --skip-neo4j --no-certs
    POSTGRES_DB=llm_chat_auth_test AUTH_MODE=oidc OIDC_ISSUER=http://localhost:8180/realms/llm-chat \
        OIDC_CLIENT_ID=llm-chat OIDC_CLIENT_SECRET=<secret> OIDC_ADMIN_ROLE=admin \
        FRONTEND_URL=https://localhost:4200 PORT=8446 python start_backend.py
    POSTGRES_DB=llm_chat_auth_test KEYCLOAK_ADMIN_PASSWORD=<password> \
        python backend/security/tests/oidc_test.py --base-url https://localhost:8446

Options: --keycloak-url (http://localhost:8180), --realm (llm-chat), --client-id (llm-chat),
--frontend-url (the backend's FRONTEND_URL, https://localhost:4200), --admin-role (admin).
Exit code 0 if every check passed.
"""
import argparse
import html
import os
import re
import sys
import time
import uuid
import warnings
from datetime import datetime, timedelta, UTC
from pathlib import Path
from urllib.parse import parse_qs, urlparse

# Make the backend package importable when run as a script
PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import httpx  # noqa: E402
from sqlalchemy import update  # noqa: E402

from backend.config import POSTGRES_DB  # noqa: E402
from backend.database import db  # noqa: E402
from backend.database.tables import sessions  # noqa: E402
from backend.security import oidc  # noqa: E402

PASSWORD = "Test-password-4711"


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


class KeycloakAdmin:
    """The Keycloak admin API for one realm, as the bootstrap admin of the master realm."""

    def __init__(self, url, realm, password):
        self.url = url.rstrip("/")
        self.realm = realm
        self.password = password
        self.token = None
        self.token_at = 0.0
        self.user_ids = []

    def request(self, method, path, **kwargs):
        # Admin tokens of the master realm live for a minute
        if not self.token or time.monotonic() - self.token_at > 30:
            response = httpx.post(f"{self.url}/realms/master/protocol/openid-connect/token", data={
                "grant_type": "password", "client_id": "admin-cli", "username": "admin", "password": self.password})
            response.raise_for_status()
            self.token, self.token_at = response.json()["access_token"], time.monotonic()
        response = httpx.request(method, f"{self.url}/admin/realms/{self.realm}{path}",
                                 headers={"Authorization": f"Bearer {self.token}"}, timeout=30, **kwargs)
        response.raise_for_status()
        return response

    def create_user(self, username, email, first_name, last_name, verified, roles=()):
        response = self.request("POST", "/users", json={
            "username": username, "email": email, "firstName": first_name, "lastName": last_name,
            "enabled": True, "emailVerified": verified,
            "credentials": [{"type": "password", "value": PASSWORD, "temporary": False}]})
        user_id = response.headers["location"].rsplit("/", 1)[1]
        self.user_ids.append(user_id)
        for role in roles:
            role_rep = self.request("GET", f"/roles/{role}").json()
            self.request("POST", f"/users/{user_id}/role-mappings/realm", json=[role_rep])
        return user_id

    def update_user(self, user_id, **fields):
        user = self.request("GET", f"/users/{user_id}").json()
        self.request("PUT", f"/users/{user_id}", json={**user, **fields})

    def allow_redirects(self, client_id, callback, frontend):
        """Adds the backend's callback and the frontend (after logout) to the client's allowed redirects."""
        client = self.request("GET", "/clients", params={"clientId": client_id}).json()[0]
        changed = False
        if callback not in client["redirectUris"]:
            client["redirectUris"].append(callback)
            changed = True
        attributes = client.setdefault("attributes", {})
        logout_uris = [uri for uri in attributes.get("post.logout.redirect.uris", "").split("##") if uri]
        if frontend not in logout_uris:
            attributes["post.logout.redirect.uris"] = "##".join(logout_uris + [frontend])
            changed = True
        if changed:
            self.request("PUT", f"/clients/{client['id']}", json=client)

    def delete_users(self):
        for user_id in self.user_ids:
            try:
                self.request("DELETE", f"/users/{user_id}")
            except httpx.HTTPError as e:
                print(f"  (could not delete Keycloak user {user_id}: {e})")


def new_browser():
    """A client with its own cookies, like a browser; redirects are followed by hand."""
    return httpx.Client(verify=False, timeout=30, follow_redirects=False)


def to_keycloak(browser, method, url, **kwargs):
    """
    A request to Keycloak. Keycloak marks its cookies Secure; browsers still send them to
    http://localhost, httpx doesn't, so they're unmarked here.
    """
    for cookie in browser.cookies.jar:
        if cookie.path.startswith("/realms/"):
            cookie.secure = False
    return browser.request(method, url, **kwargs)


def query(url):
    return {key: values[0] for key, values in parse_qs(urlparse(url).query).items()}


def login_form_action(page):
    """The action of Keycloak's login form, or None if the page has none."""
    for tag in re.findall(r"<form\b[^>]*>", page):
        if 'id="kc-form-login"' in tag:
            action = re.search(r'action="([^"]+)"', tag)
            return html.unescape(action.group(1)) if action else None
    return None


def login(browser, base_url, username, password=PASSWORD):
    """
    Logs in through the provider like a browser. Returns the backend's last response (a
    redirect to the frontend) and whether Keycloak asked for the password.
    """
    response = browser.get(f"{base_url}/api/auth/oidc/login")
    if response.status_code != 302:
        return response, False
    page = to_keycloak(browser, "GET", response.headers["location"])
    asked = page.status_code == 200
    if asked:
        action = login_form_action(page.text)
        if not action:
            return page, asked
        page = to_keycloak(browser, "POST", action,
                           data={"username": username, "password": password, "credentialId": ""})
    callback = page.headers.get("location", "")
    if not callback.startswith(base_url):
        return page, asked
    return browser.get(callback), asked


def me(browser, base_url):
    response = browser.get(f"{base_url}/api/auth/me")
    return response.json()["user"] if response.status_code == 200 else None


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--base-url", default="https://localhost:8446")
    parser.add_argument("--keycloak-url", default="http://localhost:8180")
    parser.add_argument("--realm", default="llm-chat")
    parser.add_argument("--client-id", default="llm-chat")
    parser.add_argument("--frontend-url", default="https://localhost:4200")
    parser.add_argument("--admin-role", default="admin")
    args = parser.parse_args()

    if "test" not in POSTGRES_DB:
        print(f"Refusing to run against database {POSTGRES_DB!r}: its name must contain 'test'")
        return 2
    admin_password = os.getenv("KEYCLOAK_ADMIN_PASSWORD")
    if not admin_password:
        print("Set KEYCLOAK_ADMIN_PASSWORD (the Keycloak console's admin)")
        return 2
    warnings.filterwarnings("ignore", message="Unverified HTTPS request")

    base = args.base_url.rstrip("/")
    frontend = args.frontend_url.rstrip("/")
    issuer = f"{args.keycloak_url.rstrip('/')}/realms/{args.realm}"
    run = uuid.uuid4().hex[:8]
    c = Checks()
    keycloak = KeycloakAdmin(args.keycloak_url, args.realm, admin_password)
    try:
        keycloak.allow_redirects(args.client_id, f"{base}/api/auth/oidc/callback", frontend)
        alice = keycloak.create_user(f"alice-{run}", f"alice.{run}@example.com", "Alice", "Admin", True,
                                     roles=[args.admin_role])
        keycloak.create_user(f"bob-{run}", f"bob.{run}@example.com", "Bob", "User", True)
        bob_id = keycloak.user_ids[-1]
        keycloak.create_user(f"carol-{run}", f"carol.{run}@example.com", "Carol", "Linked", True)
        keycloak.create_user(f"dave-{run}", f"dave.{run}@example.com", "Dave", "Unverified", False)

        c.section("Login options")
        config = httpx.get(f"{base}/api/auth/config", verify=False).json()
        c.check(config.get("mode") == "oidc", "GET /api/auth/config says oidc", config)
        c.check(bool(config.get("providerName")), "it names the provider for the button", config)
        response = httpx.post(f"{base}/api/auth/mock-login", json={"email": f"alice.{run}@example.com"}, verify=False)
        c.check(response.status_code == 404, "the mock login is gone", response.status_code)

        c.section("Login as an admin")
        browser = new_browser()
        response = browser.get(f"{base}/api/auth/oidc/login")
        location = response.headers.get("location", "")
        params = query(location)
        c.check(response.status_code == 302 and location.startswith(f"{issuer}/protocol/openid-connect/auth"),
                "/api/auth/oidc/login redirects to Keycloak's login page", location[:120])
        c.check(params.get("code_challenge_method") == "S256" and params.get("code_challenge")
                and params.get("state") and params.get("nonce"), "with PKCE, state and nonce", params)
        c.check(params.get("redirect_uri") == f"{base}/api/auth/oidc/callback", "and the backend's callback",
                params.get("redirect_uri"))
        c.check("oidc_login" in browser.cookies, "the pending login waits in a cookie")
        browser.close()

        browser = new_browser()
        guest = browser.post(f"{base}/api/auth/guest-login", json={})
        guest_key = browser.cookies.get("session")
        c.check(guest.status_code == 200 and guest_key, "a guest session first", guest.status_code)
        response, asked = login(browser, base, f"alice-{run}")
        c.check(asked, "Keycloak asks for the password")
        c.check(response.status_code == 302 and response.headers.get("location") == f"{frontend}/auth/callback",
                "the callback ends on the frontend's /auth/callback", (response.status_code, response.headers.get("location")))
        set_cookies = response.headers.get_list("set-cookie")
        c.check(any(h.startswith("session=") and "HttpOnly" in h and "Secure" in h for h in set_cookies),
                "it sets an httpOnly, secure session cookie")
        c.check(any(h.startswith("csrf_token=") for h in set_cookies), "and the CSRF cookie")
        c.check(any(h.startswith("oidc_login=") and "Max-Age=0" in h for h in set_cookies)
                or any(h.startswith('oidc_login=""') for h in set_cookies), "and deletes the pending login's cookie")
        c.check("id_token" not in response.text and "access_token" not in response.text,
                "no token reaches the browser")
        user = me(browser, base)
        c.check(user and user["email"] == f"alice.{run}@example.com", "GET /me is Alice", user)
        c.check(user and user.get("name") == "Alice Admin", "with her name from Keycloak", user and user.get("name"))
        c.check(user and user["is_guest"] is False and user["isAdmin"] is True, "not a guest, and an admin (role)", user)
        c.check(db.get_session(guest_key) is None, "the guest session is gone")
        response = browser.get(f"{base}/api/admin/tools")
        c.check(response.status_code == 200, "an admin endpoint answers", response.status_code)
        alice_app_id = user["id"] if user else None
        alice_row = db.get_user_by_id(alice_app_id) if alice_app_id else None
        c.check(alice_row and alice_row.get("oidc_sub") == alice, "the user is linked to Keycloak's subject id",
                alice_row and alice_row.get("oidc_sub"))
        session_row = db.get_session(browser.cookies.get("session"))
        c.check(session_row and session_row["auth_method"] == "oidc" and session_row["is_admin"]
                and session_row["id_token"], "the session row: oidc, admin, ID token", session_row and {
                    k: session_row[k] for k in ("auth_method", "is_admin")})

        c.section("Session refresh keeps the login")
        with db.connection() as conn:
            conn.execute(update(sessions).where(sessions.c.session_key == browser.cookies.get("session"))
                         .values(expires_at=datetime.now(UTC).replace(tzinfo=None) + timedelta(minutes=30)))
        old_key = browser.cookies.get("session")
        response = browser.post(f"{base}/api/auth/refresh-session")
        new_key = browser.cookies.get("session")
        c.check(response.status_code == 200 and new_key and new_key != old_key, "refresh-session gives a new session",
                response.status_code)
        new_row = db.get_session(new_key) if new_key else None
        c.check(new_row and new_row["auth_method"] == "oidc" and new_row["is_admin"] and new_row["id_token"],
                "it keeps oidc, admin and the ID token")
        user = me(browser, base)
        c.check(user and user["isAdmin"] is True, "still an admin after the refresh")

        c.section("Logout")
        response = browser.post(f"{base}/api/auth/logout")
        logout_url = response.json().get("logoutUrl") or ""
        params = query(logout_url)
        c.check(logout_url.startswith(f"{issuer}/protocol/openid-connect/logout"),
                "logout returns Keycloak's logout URL", logout_url[:120])
        c.check(params.get("id_token_hint") and params.get("post_logout_redirect_uri") == frontend
                and params.get("client_id") == args.client_id, "with the ID token and the way back to the frontend",
                {k: v[:20] for k, v in params.items()})
        c.check(me(browser, base) is None, "the app session is gone")
        response = to_keycloak(browser, "GET", logout_url) if logout_url else httpx.Response(0)
        c.check(response.status_code == 302 and response.headers.get("location", "").startswith(frontend),
                "Keycloak ends its session and returns to the frontend",
                (response.status_code, response.headers.get("location")))
        response, asked = login(browser, base, f"alice-{run}")
        c.check(asked, "the next login asks for the password again")
        user = me(browser, base)
        c.check(user and user["id"] == alice_app_id, "and finds the same user by its subject id", user)

        c.section("Without the provider's logout")
        browser.post(f"{base}/api/auth/logout")
        response, asked = login(browser, base, f"alice-{run}")
        c.check(not asked and me(browser, base) is not None,
                "Keycloak's session would log the user straight back in (why logoutUrl exists)")
        browser.close()

        c.section("A user without the admin role")
        browser = new_browser()
        login(browser, base, f"bob-{run}")
        user = me(browser, base)
        c.check(user and user["email"] == f"bob.{run}@example.com" and user["isAdmin"] is False,
                "Bob logs in, not an admin", user)
        response = browser.get(f"{base}/api/admin/tools")
        c.check(response.status_code == 403, "admin endpoints refuse him", response.status_code)
        bob_app_id = user["id"] if user else None
        browser.close()

        c.section("Changes at the provider")
        keycloak.update_user(alice, firstName="Alicia")
        keycloak.update_user(bob_id, email=f"bob.new.{run}@example.com", emailVerified=True)
        browser = new_browser()
        login(browser, base, f"alice-{run}")
        user = me(browser, base)
        c.check(user and user.get("name") == "Alicia Admin", "a new name follows at the next login",
                user and user.get("name"))
        browser.close()
        browser = new_browser()
        login(browser, base, f"bob-{run}")
        user = me(browser, base)
        c.check(user and user["id"] == bob_app_id and user["email"] == f"bob.new.{run}@example.com",
                "so does a new email, for the same user", user)
        browser.close()

        c.section("Existing users")
        carol_app = db.create_user(f"carol.{run}@example.com", "Carol (before Keycloak)")
        dave_app = db.create_user(f"dave.{run}@example.com", "Dave (before Keycloak)")
        browser = new_browser()
        login(browser, base, f"carol-{run}")
        user = me(browser, base)
        c.check(user and user["id"] == carol_app["id"], "a verified email links the existing user (chats kept)", user)
        browser.close()
        browser = new_browser()
        response, _ = login(browser, base, f"dave-{run}")
        location = response.headers.get("location", "")
        c.check(location == f"{frontend}/login?error=email_in_use",
                "an unverified email of an existing user is refused (email_in_use)", location)
        c.check(me(browser, base) is None, "without a session")
        c.check(db.get_user_by_id(dave_app["id"]).get("oidc_sub") is None, "and the existing user stays unlinked")
        browser.close()

        c.section("Broken and tampered logins")
        browser = new_browser()
        browser.get(f"{base}/api/auth/oidc/login")
        response = browser.get(f"{base}/api/auth/oidc/callback", params={"code": "x", "state": "wrong"})
        c.check(response.headers.get("location") == f"{frontend}/login?error=auth_failed",
                "a wrong state ends on the login page (auth_failed)", response.headers.get("location"))
        c.check(me(browser, base) is None, "without a session")
        browser.close()

        browser = new_browser()
        response = browser.get(f"{base}/api/auth/oidc/callback", params={"code": "x", "state": "y"})
        c.check(response.headers.get("location") == f"{frontend}/login?error=auth_failed",
                "a callback without a started login fails")
        response = browser.get(f"{base}/api/auth/oidc/callback", params={"code": "x", "state": "y"},
                               headers={"Cookie": "oidc_login=not-base64-json"})
        c.check(response.headers.get("location") == f"{frontend}/login?error=auth_failed", "a broken cookie fails")
        response = browser.get(f"{base}/api/auth/oidc/callback", params={"error": "access_denied"})
        c.check(response.headers.get("location") == f"{frontend}/login?error=auth_failed",
                "the provider's error ends on the login page")
        browser.close()

        # Replaying a used code: catch the callback URL and the pending login's cookie
        browser = new_browser()
        response = browser.get(f"{base}/api/auth/oidc/login")
        pending_cookie = browser.cookies.get("oidc_login")
        page = to_keycloak(browser, "GET", response.headers["location"])
        page = to_keycloak(browser, "POST", login_form_action(page.text), data={
            "username": f"bob-{run}", "password": PASSWORD, "credentialId": ""})
        callback = page.headers["location"]
        browser.get(callback)
        replay = new_browser()
        response = replay.get(callback, headers={"Cookie": f"oidc_login={pending_cookie}"})
        c.check(response.headers.get("location") == f"{frontend}/login?error=auth_failed",
                "a code can't be used twice", response.headers.get("location"))
        c.check(me(replay, base) is None, "the replay gets no session")
        browser.close()
        replay.close()

        browser = new_browser()
        response, _ = login(browser, base, f"bob-{run}", password="wrong-password")
        c.check(response.status_code == 200 and me(browser, base) is None, "a wrong password gets nowhere")
        browser.close()

        c.section("Mock and older sessions end in oidc mode")
        mock_key = f"zz-test-mock-{run}"
        legacy_key = f"zz-test-legacy-{run}"
        expires = datetime.now(UTC).replace(tzinfo=None) + timedelta(hours=1)
        db.create_session(mock_key, carol_app["id"], carol_app["email"], expires, auth_method="mock")
        db.create_session(legacy_key, carol_app["id"], carol_app["email"], expires)
        with db.connection() as conn:
            conn.execute(update(sessions).where(sessions.c.session_key == legacy_key).values(auth_method=None))
        for key, label in ((mock_key, "a mock login session"), (legacy_key, "a session from before auth_method")):
            response = httpx.get(f"{base}/api/auth/me", headers={"Cookie": f"session={key}"}, verify=False)
            c.check(response.status_code == 401, f"{label} no longer counts", response.status_code)
            c.check(db.get_session(key) is None, f"{label} is deleted")

        c.section("In-process: required role, admin emails, settings")
        saved = (oidc.OIDC_REQUIRED_ROLE, oidc.OIDC_ADMIN_ROLE, oidc.ADMIN_EMAILS, oidc.AUTH_MODE,
                 oidc.OIDC_CLIENT_SECRET)
        try:
            login_info = oidc.OidcLogin(sub=f"zz-test-sub-{run}", email=f"erin.{run}@example.com",
                                        email_verified=True, name="Erin", roles={"family"}, id_token="x")
            oidc.OIDC_REQUIRED_ROLE = "chat-user"
            try:
                oidc.user_for_login(login_info)
                refused = None
            except oidc.LoginRefused as e:
                refused = e.reason
            c.check(refused == "forbidden", "OIDC_REQUIRED_ROLE refuses users without it", refused)
            c.check(db.get_user_by_oidc_sub(login_info.sub) is None, "and creates no user")
            oidc.OIDC_REQUIRED_ROLE = "family"
            erin = oidc.user_for_login(login_info)
            c.check(erin and erin["oidc_sub"] == login_info.sub, "a user with the role gets in (groups count)")
            no_email = oidc.OidcLogin(sub=f"zz-test-noemail-{run}", email=None, email_verified=False, name=None,
                                      roles=set(), id_token="x")
            oidc.OIDC_REQUIRED_ROLE = ""
            nobody = oidc.user_for_login(no_email)
            c.check(nobody["email"].endswith("@oidc.invalid"), "a login without an email gets a placeholder", nobody)

            oidc.OIDC_ADMIN_ROLE = ""
            oidc.ADMIN_EMAILS = {login_info.email}
            c.check(oidc.grants_admin(login_info), "ADMIN_EMAILS counts for a verified email")
            login_info.email_verified = False
            c.check(not oidc.grants_admin(login_info), "but not for an unverified one")
            oidc.OIDC_ADMIN_ROLE = "family"
            c.check(oidc.grants_admin(login_info), "OIDC_ADMIN_ROLE counts either way")

            c.check(oidc._roles({"realm_access": {"roles": ["admin"]},
                                 "resource_access": {oidc.OIDC_CLIENT_ID: {"roles": ["editor"]}, "other": {"roles": ["x"]}},
                                 "groups": ["/family"], "roles": "not-a-list"}) == {"admin", "editor", "/family", "family"},
                    "roles: realm and own client roles, groups with and without the path")
            c.check(oidc.decode_pending("bm90IGpzb24") is None and oidc.decode_pending(None) is None,
                    "a broken pending login decodes to None")

            oidc.AUTH_MODE = "bogus"
            try:
                oidc.check_config()
                error = None
            except ValueError as e:
                error = str(e)
            c.check(error and "AUTH_MODE" in error, "an unknown AUTH_MODE stops the startup", error)
            oidc.AUTH_MODE, oidc.OIDC_CLIENT_SECRET = "oidc", ""
            try:
                oidc.check_config()
                error = None
            except ValueError as e:
                error = str(e)
            c.check(error and "OIDC_CLIENT_SECRET" in error, "so does a missing OIDC setting", error)
        finally:
            (oidc.OIDC_REQUIRED_ROLE, oidc.OIDC_ADMIN_ROLE, oidc.ADMIN_EMAILS, oidc.AUTH_MODE,
             oidc.OIDC_CLIENT_SECRET) = saved
    finally:
        keycloak.delete_users()

    print(f"\n{c.passed} passed, {len(c.failed)} failed")
    for label in c.failed:
        print(f"  - {label}")
    return 0 if not c.failed else 1


if __name__ == "__main__":
    sys.exit(main())
