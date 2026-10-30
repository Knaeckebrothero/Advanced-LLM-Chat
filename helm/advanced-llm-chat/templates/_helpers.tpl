{{/* Names */}}
{{- define "llmchat.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{- define "llmchat.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- if contains $name .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}
{{- end }}

{{/* Labels; call with (dict "ctx" $ "component" "backend") */}}
{{- define "llmchat.selectorLabels" -}}
app.kubernetes.io/name: {{ include "llmchat.name" .ctx }}
app.kubernetes.io/instance: {{ .ctx.Release.Name }}
app.kubernetes.io/component: {{ .component }}
{{- end }}

{{- define "llmchat.labels" -}}
helm.sh/chart: {{ printf "%s-%s" .ctx.Chart.Name .ctx.Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{ include "llmchat.selectorLabels" . }}
app.kubernetes.io/version: {{ .ctx.Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .ctx.Release.Service }}
app.kubernetes.io/part-of: {{ include "llmchat.name" .ctx }}
{{- end }}

{{/* An image; call with (dict "image" .Values.backend.image "ctx" $) */}}
{{- define "llmchat.image" -}}
{{- printf "%s:%s" .image.repository (default .ctx.Chart.AppVersion .image.tag) }}
{{- end }}

{{/* The host of a URL, without the port (for ingress rules) */}}
{{- define "llmchat.host" -}}
{{- regexReplaceAll ":[0-9]+$" (urlParse .).host "" }}
{{- end }}

{{/* A generated secret value that survives upgrades: the given value, else the one already
     in the Secret, else a new random one. Call with (dict "ctx" $ "secret" name "key" key "value" v) */}}
{{- define "llmchat.secretValue" -}}
{{- if .value }}
{{- .value }}
{{- else }}
{{- $existing := lookup "v1" "Secret" .ctx.Release.Namespace .secret }}
{{- if and $existing $existing.data (hasKey $existing.data .key) }}
{{- index $existing.data .key | b64dec }}
{{- else }}
{{- randAlphaNum 32 }}
{{- end }}
{{- end }}
{{- end }}

{{/* Login mode; the bundled Keycloak means oidc */}}
{{- define "llmchat.authMode" -}}
{{- if .Values.keycloak.enabled }}oidc{{ else }}{{ .Values.auth.mode }}{{ end }}
{{- end }}

{{/* Postgres connection */}}
{{- define "llmchat.postgresHost" -}}
{{- if .Values.postgresql.enabled }}{{ include "llmchat.fullname" . }}-postgresql{{ else }}{{ required "postgresql.external.host is required when postgresql.enabled is false" .Values.postgresql.external.host }}{{ end }}
{{- end }}

{{- define "llmchat.postgresPort" -}}
{{- if .Values.postgresql.enabled }}5432{{ else }}{{ .Values.postgresql.external.port }}{{ end }}
{{- end }}

{{- define "llmchat.postgresSecretName" -}}
{{- default (printf "%s-postgresql" (include "llmchat.fullname" .)) .Values.postgresql.existingSecret }}
{{- end }}

{{- define "llmchat.postgresSecretKey" -}}
{{- if .Values.postgresql.existingSecret }}{{ .Values.postgresql.existingSecretKey }}{{ else }}password{{ end }}
{{- end }}

{{/* Environment variables with the Postgres connection (the backend and the init containers) */}}
{{- define "llmchat.postgresEnv" -}}
- name: POSTGRES_HOST
  value: {{ include "llmchat.postgresHost" . | quote }}
- name: POSTGRES_PORT
  value: {{ include "llmchat.postgresPort" . | quote }}
- name: POSTGRES_DB
  value: {{ .Values.postgresql.database | quote }}
- name: POSTGRES_USER
  value: {{ .Values.postgresql.username | quote }}
- name: POSTGRES_PASSWORD
  valueFrom:
    secretKeyRef:
      name: {{ include "llmchat.postgresSecretName" . }}
      key: {{ include "llmchat.postgresSecretKey" . }}
{{- end }}

{{/* An init container that waits until Postgres accepts connections */}}
{{- define "llmchat.waitForPostgres" -}}
- name: wait-for-postgres
  image: {{ include "llmchat.image" (dict "image" .Values.postgresql.image "ctx" .) }}
  imagePullPolicy: {{ .Values.postgresql.image.pullPolicy }}
  command: ["sh", "-c", "until pg_isready -h \"$POSTGRES_HOST\" -p \"$POSTGRES_PORT\" -U \"$POSTGRES_USER\"; do echo waiting for postgres; sleep 2; done"]
  env:
    {{- include "llmchat.postgresEnv" . | nindent 4 }}
{{- end }}

{{/* The backend's settings, secrets and volumes (the backend and its migrate init container) */}}
{{- define "llmchat.backendEnv" -}}
envFrom:
  - configMapRef:
      name: {{ include "llmchat.fullname" . }}-backend
  {{- if .Values.backend.existingSecret }}
  - secretRef:
      name: {{ .Values.backend.existingSecret }}
  {{- end }}
  {{- if .Values.backend.secretEnv }}
  - secretRef:
      name: {{ include "llmchat.fullname" . }}-backend
  {{- end }}
env:
  - name: POSTGRES_PASSWORD
    valueFrom:
      secretKeyRef:
        name: {{ include "llmchat.postgresSecretName" . }}
        key: {{ include "llmchat.postgresSecretKey" . }}
  {{- if .Values.keycloak.enabled }}
  - name: OIDC_CLIENT_SECRET
    valueFrom:
      secretKeyRef:
        name: {{ include "llmchat.fullname" . }}-keycloak
        key: client-secret
  {{- else if and (eq (include "llmchat.authMode" .) "oidc") .Values.auth.oidc.clientSecret }}
  - name: OIDC_CLIENT_SECRET
    valueFrom:
      secretKeyRef:
        name: {{ include "llmchat.fullname" . }}-oidc
        key: client-secret
  {{- end }}
volumeMounts:
  - name: data
    mountPath: /app/.filesystem
  {{- if .Values.backend.catalog }}
  - name: catalog
    mountPath: /app/catalog-custom
    readOnly: true
  {{- end }}
{{- end }}

{{/* Checks of the values that would otherwise fail at runtime */}}
{{- define "llmchat.validate" -}}
{{- $mode := include "llmchat.authMode" . }}
{{- if not (has $mode (list "oidc" "mock" "none")) }}
{{- fail (printf "auth.mode must be oidc, mock or none, not %q" $mode) }}
{{- end }}
{{- if and (eq $mode "oidc") (not .Values.keycloak.enabled) (not .Values.auth.oidc.issuer) }}
{{- fail "auth.mode oidc needs auth.oidc.issuer (or keycloak.enabled)" }}
{{- end }}
{{- if and (not .Values.postgresql.enabled) (not .Values.postgresql.password) (not .Values.postgresql.existingSecret) }}
{{- fail "an external Postgres needs postgresql.password or postgresql.existingSecret" }}
{{- end }}
{{- end }}
