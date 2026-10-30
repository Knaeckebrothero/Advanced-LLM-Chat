# Advanced LLM Chat Helm chart

Deploys the frontend (nginx), the backend (FastAPI), Postgres, and optionally Keycloak. Every merge into `main` publishes the chart as `oci://ghcr.io/knaeckebrothero/charts/advanced-llm-chat` with the same version as its images (see `.github/workflows/docker-build.yml`).

```bash
helm install chat oci://ghcr.io/knaeckebrothero/charts/advanced-llm-chat --version <version> \
  --namespace chat --create-namespace -f my-values.yaml
```

All settings are in [`values.yaml`](values.yaml). The backend's own settings are described in the repository's `.env.example` and in `docs/` (login: `docs/authentication.md`).

## What it runs

- **Frontend and backend** with their services. The backend runs `app_init --prod` in an init container before every start: it creates missing tables and columns and seeds the model catalog (providers are updated, existing models and agents are kept).
- **Postgres** (`postgresql.enabled`, default on) as a StatefulSet with a volume, and a generated password that survives upgrades. With `postgresql.enabled: false` it uses `postgresql.external`.
- **Keycloak** (`keycloak.enabled`, default off) with the realm `llm-chat` (`files/llm-chat-realm.json`, shared with docker compose), its database `keycloak` in the same Postgres, and the backend set to log in through it.
- **A volume** for uploaded files, the TTS cache and logs (`backend.persistence`).
- **An ingress** (`ingress.enabled`) for the hosts in `urls` and `keycloak.url`. If the frontend and backend share one address, `/api` goes to the backend. Without the ingress, route the addresses to the services yourself (e.g. with a tunnel).

TLS ends at the ingress or tunnel; the pods speak plain HTTP. The backend trusts `X-Forwarded-For` from any peer (`backend.forwardedAllowIps`), since only the ingress or tunnel reaches it; guests are rate-limited by that address.

## Login

Guests can always chat. `auth.mode` decides how everyone else logs in (`docs/authentication.md`):

- `none` (default): guests only.
- `oidc` with your own provider: `auth.oidc.issuer`, `clientId`, and the client secret in `auth.oidc.clientSecret` or as `OIDC_CLIENT_SECRET` in `backend.existingSecret`. Register `<urls.backend>/api/auth/oidc/callback` as the redirect URI and `<urls.frontend>` as the post logout redirect URI.
- `keycloak.enabled: true`: the bundled Keycloak at `keycloak.url`. Its admin password and the client secret are generated (Secret `<release>-advanced-llm-chat-keycloak`).
- `mock`: development only.

## Examples

Bundled Keycloak and Postgres behind an ingress:

```yaml
urls:
  frontend: https://chat.example.com
  backend: https://chat.example.com      # one address: /api goes to the backend
keycloak:
  enabled: true
  url: https://auth.example.com
ingress:
  enabled: true
  className: traefik
  annotations:
    cert-manager.io/cluster-issuer: letsencrypt
  tls:
    - secretName: chat-tls
      hosts: [chat.example.com, auth.example.com]
backend:
  secretEnv:
    CORTECS_API_KEY: "..."
```

Your own Keycloak, secrets from an existing Secret (e.g. made by External Secrets), a tunnel instead of an ingress:

```yaml
urls:
  frontend: https://chat.example.com
  backend: https://chat-api.example.com
auth:
  mode: oidc
  oidc:
    issuer: https://auth.example.com/realms/home
    clientId: llm-chat
    adminRole: admin
    requiredRole: llm-chat-user   # needed if the realm allows self-registration
backend:
  existingSecret: chat-secrets    # OIDC_CLIENT_SECRET, CORTECS_API_KEY, MODEL_ROUTER_KEY, ...
  env:
    MODEL_ROUTER_API: https://router.example.com/v1
postgresql:
  existingSecret: chat-secrets
  existingSecretKey: POSTGRES_PASSWORD
```

## Taking over an existing deployment

Keep the data by pointing the chart at it: `postgresql.enabled: false` with `postgresql.external` (or the existing Postgres service), the old credentials, and `backend.persistence.existingClaim` for the old file volume. The init container then migrates the existing database on the first start.

Uploaded files are expected under `files/` on the volume (`FILES_DIR=/app/.filesystem/files`). Older deployments kept them elsewhere: move them there, or set `FILES_DIR` in `backend.env`.

## With Fleet

```yaml
helm:
  chart: oci://ghcr.io/knaeckebrothero/charts/advanced-llm-chat
  version: 0.1.42          # pin a release; the images have the same tag
  releaseName: chat
  valuesFiles:
    - values.yaml
```

The chart package is published to GHCR; if it was created as private, make it public in the package settings (or give the cluster pull credentials).
