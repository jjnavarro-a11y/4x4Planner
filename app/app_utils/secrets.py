# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Secure secret resolution using Google Cloud Secret Manager and ADC with env fallback."""

from __future__ import annotations

import base64
import functools
import json
import logging
import os
import urllib.request

import google.auth
from google.auth.transport.requests import Request

logger = logging.getLogger(__name__)


@functools.lru_cache(maxsize=64)
def get_secret(
    secret_id: str,
    project_id: str | None = None,
    version: str = "latest",
    default: str | None = None,
) -> str | None:
    """Retrieves a secret from Google Cloud Secret Manager or environment variables.

    Resolution order:
    1. Environment variable matching `secret_id` (for local development or Cloud Run /
       Agent Runtime secret-mounted env vars).
    2. Google Cloud Secret Manager API using Application Default Credentials (ADC)
       when `USE_SECRET_MANAGER=true` or when running in GCP with a project ID.
    3. Provided `default` fallback value.

    Args:
        secret_id: Name of the secret or environment variable (e.g. 'GOOGLE_MAPS_API_KEY').
        project_id: Optional GCP project ID (defaults to `GOOGLE_CLOUD_PROJECT` or ADC).
        version: Secret version to access (default: 'latest').
        default: Default value if the secret is not configured.

    Returns:
        The resolved secret string, or `default` if unavailable.
    """
    env_val = os.environ.get(secret_id)
    if env_val:
        return env_val

    if os.environ.get("INTEGRATION_TEST", "").lower() in ("true", "1"):
        return default

    use_sm = os.environ.get("USE_SECRET_MANAGER", "").lower() in ("true", "1")
    if not use_sm:
        return default

    resolved_project = project_id or os.environ.get("GOOGLE_CLOUD_PROJECT")
    try:
        credentials, adc_project = google.auth.default(
            scopes=["https://www.googleapis.com/auth/cloud-platform"]
        )
        resolved_project = resolved_project or adc_project
        if not resolved_project:
            return default

        # Prefer google-cloud-secret-manager SDK if installed
        try:
            from google.cloud import secretmanager  # type: ignore[import-untyped]

            client = secretmanager.SecretManagerServiceClient(credentials=credentials)
            name = f"projects/{resolved_project}/secrets/{secret_id}/versions/{version}"
            response = client.access_secret_version(request={"name": name}, timeout=4.0)
            return response.payload.data.decode("utf-8")
        except ImportError:
            # Fallback to Secret Manager REST API via ADC bearer token
            if not credentials.valid:
                credentials.refresh(Request())
            url = (
                f"https://secretmanager.googleapis.com/v1/projects/{resolved_project}"
                f"/secrets/{secret_id}/versions/{version}:access"
            )
            req = urllib.request.Request(
                url,
                headers={"Authorization": f"Bearer {credentials.token}"},
            )
            with urllib.request.urlopen(req, timeout=4.0) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                encoded = data.get("payload", {}).get("data", "")
                if encoded:
                    return base64.b64decode(encoded).decode("utf-8")
    except Exception as exc:
        logger.debug(
            "Secret '%s' not found in Secret Manager: %s", secret_id, type(exc).__name__
        )

    return default


def mask_secret(value: str | None) -> str:
    """Masks a secret value for safe display or diagnostic logging."""
    if not value:
        return "<unset>"
    if len(value) <= 6:
        return "***"
    return f"{value[:2]}***{value[-2:]}"
