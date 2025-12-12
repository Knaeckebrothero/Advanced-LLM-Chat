{{/*
Expand the name of the chart.
*/}}
{{- define "fessi.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
*/}}
{{- define "fessi.fullname" -}}
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

{{/*
Create chart name and version as used by the chart label.
*/}}
{{- define "fessi.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels
*/}}
{{- define "fessi.labels" -}}
helm.sh/chart: {{ include "fessi.chart" . }}
{{ include "fessi.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{/*
Selector labels
*/}}
{{- define "fessi.selectorLabels" -}}
app.kubernetes.io/name: {{ include "fessi.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
Frontend labels
*/}}
{{- define "fessi.frontend.labels" -}}
{{ include "fessi.labels" . }}
app.kubernetes.io/component: frontend
{{- end }}

{{- define "fessi.frontend.selectorLabels" -}}
{{ include "fessi.selectorLabels" . }}
app.kubernetes.io/component: frontend
{{- end }}

{{/*
Backend labels
*/}}
{{- define "fessi.backend.labels" -}}
{{ include "fessi.labels" . }}
app.kubernetes.io/component: backend
{{- end }}

{{- define "fessi.backend.selectorLabels" -}}
{{ include "fessi.selectorLabels" . }}
app.kubernetes.io/component: backend
{{- end }}

{{/*
PostgreSQL labels
*/}}
{{- define "fessi.postgresql.labels" -}}
{{ include "fessi.labels" . }}
app.kubernetes.io/component: postgresql
{{- end }}

{{- define "fessi.postgresql.selectorLabels" -}}
{{ include "fessi.selectorLabels" . }}
app.kubernetes.io/component: postgresql
{{- end }}

{{/*
Neo4j labels
*/}}
{{- define "fessi.neo4j.labels" -}}
{{ include "fessi.labels" . }}
app.kubernetes.io/component: neo4j
{{- end }}

{{- define "fessi.neo4j.selectorLabels" -}}
{{ include "fessi.selectorLabels" . }}
app.kubernetes.io/component: neo4j
{{- end }}

{{/*
Create the name of the service account to use
*/}}
{{- define "fessi.serviceAccountName" -}}
{{- if .Values.serviceAccount.create }}
{{- default (include "fessi.fullname" .) .Values.serviceAccount.name }}
{{- else }}
{{- default "default" .Values.serviceAccount.name }}
{{- end }}
{{- end }}

{{/*
Return the proper image name
*/}}
{{- define "fessi.image" -}}
{{- $registryName := .global.imageRegistry -}}
{{- $repositoryName := .image.repository -}}
{{- $tag := .image.tag | toString -}}
{{- printf "%s/%s:%s" $registryName $repositoryName $tag -}}
{{- end -}}

{{/*
Return the PostgreSQL hostname
*/}}
{{- define "fessi.postgresql.host" -}}
{{- printf "%s-postgresql" (include "fessi.fullname" .) -}}
{{- end -}}

{{/*
Return the Neo4j hostname
*/}}
{{- define "fessi.neo4j.host" -}}
{{- printf "%s-neo4j" (include "fessi.fullname" .) -}}
{{- end -}}

{{/*
Return the Neo4j Bolt URI
*/}}
{{- define "fessi.neo4j.uri" -}}
{{- printf "bolt://%s:%d" (include "fessi.neo4j.host" .) (int .Values.neo4j.service.boltPort) -}}
{{- end -}}
