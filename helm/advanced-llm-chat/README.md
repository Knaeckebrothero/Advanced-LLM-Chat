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
- **The nightly consolidation** of the agents' memory (`backend.memoryDream`, default on): a CronJob that goes over every knowledge base with conversations since its last run, writes a journal per week, tidies the memory up and keeps the patterns it sees (`docs/knowledge_base.md`). `backend.memoryDream.timeZone` (e.g. `Europe/Berlin`) is the schedule's time zone and the memory's (`MEMORY_TIME_ZONE`). Docker compose has no such job.
- **An ingress** (`ingress.enabled`) for the hosts in `urls` and `keycloak.url`. If the frontend and backend share one address, `/api` goes to the backend. Without the ingress, route the addresses to the services yourself (e.g. with a tunnel).

TLS ends at the ingress or tunnel; the pods speak plain HTTP.

## Security

- **Guests.** Anyone who reaches the app can chat as a guest, with the models and agents marked for guests. What a guest uses is counted per client address: answers, titles, speech, uploads, stored messages and guest logins each have a limit (`GUEST_MAX_ANSWERS` and the other `GUEST_*` settings in `backend.env`, see `docs/authentication.md`). The limits bound what a visitor can cost; give the model keys of a public server spending limits at the provider as well.
- **The client's address.** The guests' limits count by IP address. The backend takes it from `X-Forwarded-For` only when the request comes from an address in `backend.forwardedAllowIps`, and then takes the last entry that isn't one of those addresses: what the proxy added, not what a visitor wrote into the header. The default is the private address ranges, which covers an ingress controller or tunnel inside the cluster. Set the proxy's own address or range if you can: with the default, a visitor on a private address (a local network) can still fake its address if the proxy passes the header on instead of overwriting it. `*` trusts whatever the client claims, so use it only behind a proxy that overwrites the header.
- **Content-Security-Policy.** The frontend's nginx sends `script-src 'self'`: the browser runs scripts only from the app's own files, no inline script and no `eval`, so a script that got into the page (a gap in the sanitising of an answer) doesn't run. Styles stay inline (Angular adds them). A CDN in front may rewrite the frontend's cache headers: `assets/env.js` (the backend's address) must reach browsers with `no-cache`.
- **Users.** The backend runs as the image's user `app` (uid and gid 10001) without capabilities, as do its init containers and the memory job (`backend.podSecurityContext`, `backend.securityContext`); `fsGroup` gives it the volume. The frontend's nginx starts as root to open port 80, runs its workers as the user `nginx` and keeps only the capabilities for that (`frontend.securityContext`). Postgres and Keycloak run as their images do.
- **Network policies** (`networkPolicy.enabled`, default off; the cluster's network plugin must enforce them). The pods then accept connections only from each other, and the HTTP ports of the frontend, the backend and the bundled Keycloak from `networkPolicy.ingressFrom`: a list of NetworkPolicy peers such as the ingress controller's namespace, or empty for anyone. `networkPolicy.restrictEgress` also limits what the pods reach: the cluster's DNS, each other, and the internet without the private address ranges (IPv4). A backend that was taken over can then still call the model providers, but not other workloads, the Kubernetes API, the nodes or the local network. What the backend needs on a private address (a model server in the cluster, an OIDC provider or MCP server on the local network, an external Postgres) goes into `networkPolicy.extraEgress`:

```yaml
networkPolicy:
  enabled: true
  ingressFrom:
    - namespaceSelector:
        matchLabels:
          kubernetes.io/metadata.name: ingress-nginx
  restrictEgress: true
  extraEgress:
    - to:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: models
      ports:
        - port: 8080
```

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

## Upgrading

**The backend no longer runs as root**, and an existing volume holds the files it wrote as root. Where the kubelet applies `fsGroup` to the volume, nothing is to do: on the first start it gives the old files the group 10001 with write access (ReadWriteOnce volumes of most CSI drivers, and `local` volumes such as those of a current k3s's local-path storage). Volumes that ignore `fsGroup` (hostPath, NFS, some ReadWriteMany drivers) keep root's files, and the backend then fails to start with `Permission denied: '/app/.filesystem/logs/application.log'`. For those, start it once with these values: as root, the image hands the files to `app` and then drops root itself.

```yaml
backend:
  podSecurityContext:
    runAsNonRoot: false
    runAsUser: 0
  securityContext:
    capabilities:
      add: [CHOWN, SETUID, SETGID]
```

Remove them again after that start. (Or change the owner yourself: `chown -R 10001:10001` on the volume's directory.)

**`backend.forwardedAllowIps` was `*`** and is now the private address ranges (see [Security](#security)). If your ingress controller or tunnel reaches the backend from another address, set that address: otherwise all guests share the proxy's address and its limit.

## Taking over an existing deployment

Keep the data by pointing the chart at it: `postgresql.enabled: false` with `postgresql.external` (or the existing Postgres service), the old credentials, and `backend.persistence.existingClaim` for the old file volume. The init container then migrates the existing database on the first start.

Uploaded files are expected under `files/` on the volume (`FILES_DIR=/app/.filesystem/files`). Older deployments kept them elsewhere: move them there, or set `FILES_DIR` in `backend.env`. The backend runs as uid 10001; see [Upgrading](#upgrading) if the old volume ignores `fsGroup`.

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
