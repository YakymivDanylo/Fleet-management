{{/* Chart name. */}}
{{- define "fleet.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/* Base name <release>-<chart>; collapsed when the release name already contains the chart name. */}}
{{- define "fleet.fullname" -}}
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

{{/* Name of one component: <fullname>-<component>. Args: dict "root" $ "component" "api". */}}
{{- define "fleet.componentName" -}}
{{- printf "%s-%s" (include "fleet.fullname" .root) .component | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/* Selector labels (immutable). Args: dict "root" $ "component" "api". */}}
{{- define "fleet.selectorLabels" -}}
app.kubernetes.io/name: {{ include "fleet.name" .root }}
app.kubernetes.io/instance: {{ .root.Release.Name }}
app.kubernetes.io/component: {{ .component }}
{{- end }}

{{/* Full label set. Args: dict "root" $ "component" "api". */}}
{{- define "fleet.labels" -}}
helm.sh/chart: {{ printf "%s-%s" .root.Chart.Name .root.Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{ include "fleet.selectorLabels" . }}
app.kubernetes.io/version: {{ .root.Chart.AppVersion | quote }}
app.kubernetes.io/part-of: fleet-management
app.kubernetes.io/managed-by: {{ .root.Release.Service }}
{{- end }}

{{/* Image reference; an empty tag falls back to Chart.appVersion. Args: dict "image" .Values.image "root" $. */}}
{{- define "fleet.image" -}}
{{- printf "%s:%s" .image.repository (.image.tag | default .root.Chart.AppVersion | toString) }}
{{- end }}

{{/* Names of shared objects and in-cluster service hosts. Arg: root context. */}}
{{- define "fleet.configName" -}}{{ include "fleet.componentName" (dict "root" . "component" "config") }}{{- end }}
{{- define "fleet.secretName" -}}{{ include "fleet.componentName" (dict "root" . "component" "secret") }}{{- end }}
{{- define "fleet.postgresHost" -}}{{ include "fleet.componentName" (dict "root" . "component" "postgres") }}{{- end }}
{{- define "fleet.redisHost" -}}{{ include "fleet.componentName" (dict "root" . "component" "redis") }}{{- end }}
{{- define "fleet.rabbitmqHost" -}}{{ include "fleet.componentName" (dict "root" . "component" "rabbitmq") }}{{- end }}

{{/*
Secret value resolution: explicit value > value already stored in the cluster Secret > random.
Keeps generated passwords stable across upgrades without storing them in values files.
Args: dict "root" $ "key" "POSTGRES_PASSWORD" "value" .Values.secret.postgresPassword.
*/}}
{{- define "fleet.secretValue" -}}
{{- if .value -}}
{{- .value -}}
{{- else -}}
{{- $existing := lookup "v1" "Secret" .root.Release.Namespace (include "fleet.secretName" .root) -}}
{{- if and $existing $existing.data (hasKey $existing.data .key) -}}
{{- index $existing.data .key | b64dec -}}
{{- else -}}
{{- randAlphaNum 24 -}}
{{- end -}}
{{- end -}}
{{- end }}
