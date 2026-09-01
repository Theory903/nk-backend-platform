{{- define "nk-backend.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- define "nk-backend.fullname" -}}
{{- default (include "nk-backend.name" .) .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- define "nk-backend.labels" -}}
app.kubernetes.io/name: {{ include "nk-backend.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}
{{- define "nk-backend.image" -}}
{{- if and (or (eq .Values.runtime.environment "production") (eq .Values.runtime.environment "prod") (eq .Values.runtime.environment "staging")) (not .Values.image.digest) -}}
{{ .Values.image.repository }}@{{ required "image.digest is required for production deployments" .Values.image.digest }}
{{- else if .Values.image.digest -}}
{{ .Values.image.repository }}@{{ .Values.image.digest }}
{{- else -}}
{{ .Values.image.repository }}:{{ required "image.tag or image.digest is required" .Values.image.tag }}
{{- end -}}
{{- end }}
{{- define "nk-backend.secretName" -}}
{{- if .Values.externalSecrets.enabled -}}
{{ include "nk-backend.fullname" . }}
{{- else -}}
{{ required "secrets.existingSecret is required when externalSecrets is disabled" .Values.secrets.existingSecret }}
{{- end -}}
{{- end }}
{{- define "nk-backend.runtimeEnv" -}}
- name: __APP_ENV_PREFIX___ENVIRONMENT
  value: {{ .Values.runtime.environment | quote }}
- name: __APP_ENV_PREFIX___ALLOWED_HOSTS
  value: {{ .Values.runtime.allowedHosts | quote }}
- name: __APP_ENV_PREFIX___CORS_ALLOWED_ORIGINS
  value: {{ .Values.runtime.corsAllowedOrigins | quote }}
- name: __APP_ENV_PREFIX___SECURITY_REQUIRE_AUTH
  value: {{ .Values.runtime.securityRequireAuth | quote }}
{{- if .Values.runtime.identityEnabled }}
- name: __APP_ENV_PREFIX___AUTH_STORE_BACKEND
  value: {{ .Values.runtime.authStoreBackend | quote }}
{{- end }}
{{- end }}
{{- define "nk-backend.migrationSecretName" -}}
{{- if .Values.externalSecrets.enabled -}}
{{ include "nk-backend.fullname" . }}-migration
{{- else -}}
{{ required "migrationSecrets.existingSecret is required when migrations are enabled" .Values.migrationSecrets.existingSecret }}
{{- end }}
{{- end }}
