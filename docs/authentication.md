# Authentication

Guests can always chat: a first visit starts a guest session (its own user, rate-limited by IP address, deleted once the session has expired). `AUTH_MODE` decides how everyone else logs in:

| `AUTH_MODE` | Login | For |
|---|---|---|
| `none` (default) | None, guests only | A public demo without accounts |
| `oidc` | Through an OpenID Connect provider such as Keycloak | Every deployment with accounts |
| `mock` | Any email, no password | Development and the test scripts only. Anyone can log in as anyone, including an admin |

The default is `none`, so a deployment that forgets the setting can't expose the mock login. The development `.env` (from `.env.example`) sets `AUTH_MODE=mock`. The backend refuses to start with an unknown mode or incomplete OIDC settings.

Code: `backend/security/oidc.py` (the flow), `backend/api/auth.py` (endpoints), `backend/security/auth.py` (sessions, `is_admin`), `src/app/auth/auth.service.ts` and `src/app/login/` (frontend).

## How a login works (`oidc`)

The backend is a confidential client and runs the authorization code flow with PKCE itself. The browser never sees a token; the login ends in the same session cookie as every other login.

1. The login page asks `GET /api/auth/config` for the mode and shows "Log in with Keycloak" (`OIDC_DISPLAY_NAME`).
2. The button opens `GET /api/auth/oidc/login`. It redirects to the provider with state, nonce and a PKCE challenge, and keeps them in a short-lived cookie (`oidc_login`, 10 minutes, path `/api/auth/oidc`).
3. After the login the provider redirects to `GET /api/auth/oidc/callback`. The backend checks the state, swaps the code for tokens (client secret and PKCE verifier), checks the ID token's signature, issuer, audience, lifetime and nonce, and reads the roles.
4. It finds or creates the user (see [Users](#users)), creates the session (replacing the guest session) and redirects to `FRONTEND_URL/auth/callback`. The frontend then loads the user, clears the guest's chats stored in the browser, and syncs.
5. A refused or failed login ends on `FRONTEND_URL/login?error=...` (`auth_failed`, `provider_unavailable`, `forbidden`, `email_in_use`), and the login page explains it.

**Logout** ends the app session and returns the provider's logout URL (`logoutUrl`, with the ID token kept in the session row). The frontend sends the browser there, so the provider's session ends too and the next login asks for the password again. The provider then redirects to `FRONTEND_URL`, where the app starts a guest session.

**Sessions** last `SESSION_TIMEOUT_HOURS` (24) and are refreshed as before, independently of the provider. Disabling a user or changing their roles in Keycloak takes effect at their next login, so at the latest when the session expires.

## Settings

| Setting | Meaning |
|---|---|
| `OIDC_ISSUER` | The provider's issuer, e.g. `https://auth.example.com/realms/home` for a Keycloak realm. Required |
| `OIDC_CLIENT_ID`, `OIDC_CLIENT_SECRET` | The confidential client. Required |
| `OIDC_ADMIN_ROLE` | Role or group that makes a user an admin (manages models and agents). Empty: no role does |
| `OIDC_REQUIRED_ROLE` | Role or group a user needs to log in at all. Empty: everyone the provider accepts |
| `OIDC_DISPLAY_NAME` | Shown on the login button (default `Keycloak`) |
| `OIDC_SCOPES` | Default `openid profile email` |
| `OIDC_DISCOVERY_URL` | Where the backend reads the provider's metadata, if it reaches the provider under another address than the browser (the bundled Keycloak). Default: the issuer's `/.well-known/openid-configuration` |
| `OIDC_REDIRECT_URI` | The callback as the browser reaches it. Default: `API_URL` + `/api/auth/oidc/callback`, else the request's own address |
| `API_URL` | The backend's address in the browser (the frontend container uses it too) |
| `FRONTEND_URL` | Where logins and logouts end. Default: the first `CORS_ORIGINS` entry, else `https://localhost:4200` |
| `ADMIN_EMAILS` | Also admins, but with `oidc` only if the provider says the email is verified |

Roles are collected from Keycloak's realm roles and the client roles of `OIDC_CLIENT_ID` (Keycloak puts both into the access token by default), and from `roles` and `groups` claims, which other providers use. Groups count with and without their leading slash (`/family` and `family`); Keycloak only sends groups with a "Group Membership" mapper on the client.

The backend reaches the provider for the metadata, the signing keys and the token exchange. If the provider's certificate comes from a private CA, set `SSL_CERT_FILE` to a bundle that has the public CAs and yours: it replaces the trusted CAs of every outgoing request, the model providers' included.

## Users

- A user is found by the provider's subject id (`users.oidc_sub`), so a changed email or name at the provider follows at the next login.
- The first login links an existing user with the same email (e.g. from the mock login), so its chats are kept, but only if the provider says the email is verified. Otherwise the login is refused with `email_in_use`: tick "Email verified" for the user in Keycloak and log in again.
- A provider that shares no email gets a placeholder (`oidc_<hash>@oidc.invalid`).
- Guests are never admins; a guest who logs in starts with an empty chat list (the guest's chats are not carried over).

## Option 1: the bundled Keycloak (docker compose)

`docker/docker-compose.keycloak.yml` adds Keycloak (with its own Postgres) to either compose file, imports the realm `llm-chat` from `helm/advanced-llm-chat/files/llm-chat-realm.json` (shared with the Helm chart) on its first start, and sets the backend to `AUTH_MODE=oidc` with it:

```bash
# docker/.env
KEYCLOAK_ADMIN_PASSWORD=...    # the Keycloak console's user "admin"
OIDC_CLIENT_SECRET=...         # e.g. openssl rand -hex 24

cd docker
docker compose -f docker-compose.yml -f docker-compose.keycloak.yml up -d
```

Then open the console at `http://localhost:8180`, switch to the realm `llm-chat`, and create users: username, email with "Email verified" on, first and last name, and a password (Credentials tab). Give admins the realm role `admin`. The realm has no self-registration.

The browser reaches Keycloak at `KEYCLOAK_URL` (default `http://localhost:8180`), the backend inside the network at `http://keycloak:8080` (`KC_HOSTNAME_BACKCHANNEL_DYNAMIC`). Behind a reverse proxy with TLS, set `KEYCLOAK_URL`, `API_URL` and `FRONTEND_URL` to the public addresses before the first start (the realm's redirect URIs are filled from them once), and add `KC_PROXY_HEADERS=xforwarded`.

## Option 2: the bundled Keycloak (Helm)

The Helm chart (`helm/advanced-llm-chat`) does the same with `keycloak.enabled: true` and `keycloak.url` (Keycloak's public address, which needs its own host on the ingress). It generates the console's admin password and the client secret (Secret `<release>-advanced-llm-chat-keycloak`) and keeps Keycloak's database `keycloak` in the chart's Postgres. See the chart's README.

## Option 3: your own Keycloak

Create a client in your realm (Clients, Create client):

1. Client type OpenID Connect, client ID e.g. `llm-chat`.
2. Client authentication on; authentication flow "Standard flow" only.
3. Valid redirect URIs: `<API_URL>/api/auth/oidc/callback`. Valid post logout redirect URIs: `<FRONTEND_URL>`. Web origins can stay empty (the browser never talks to Keycloak by script).
4. Advanced, "Proof Key for Code Exchange Code Challenge Method": `S256` (the backend always sends it; this makes Keycloak require it).
5. Copy the secret from the Credentials tab into `OIDC_CLIENT_SECRET`.
6. Decide who is an admin: a realm role you already have (e.g. `admin`), or a client role on `llm-chat`, assigned to the users. Set `OIDC_ADMIN_ROLE` to its name.
7. If the realm allows self-registration, set `OIDC_REQUIRED_ROLE` (e.g. a client role `user` that you assign by hand), so new accounts can't use the paid models right away.

```bash
AUTH_MODE=oidc
OIDC_ISSUER=https://auth.example.com/realms/home
OIDC_CLIENT_ID=llm-chat
OIDC_CLIENT_SECRET=...
OIDC_ADMIN_ROLE=admin
OIDC_REQUIRED_ROLE=llm-chat-user
API_URL=https://chat-api.example.com
FRONTEND_URL=https://chat.example.com
```

Users who should keep the chats of an earlier (mock login) account need "Email verified" in Keycloak.

## Updating an existing installation

- Run `python backend/app_init.py --prod` once: it adds `users.oidc_sub` and `sessions.auth_method`, `is_admin` and `id_token`.
- Set `AUTH_MODE`. Without it there is no login any more; development setups need `AUTH_MODE=mock` in `.env`.
- Outside `mock` mode, sessions from the mock login (and sessions from before `auth_method` existed that aren't guest sessions) end at their next request.

## Tests

`backend/security/tests/oidc_test.py` checks the whole flow against a real Keycloak (the bundled one): login and callback, PKCE/state/nonce, cookies, admin and plain users, logout at the provider, session refresh, name and email changes, linking by verified email, refused, tampered and replayed logins, and that mock sessions end. Some checks run in-process (required role, admin emails, settings). Its docstring has the commands.
