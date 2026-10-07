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

"""Observability, Structured JSON Logging, PII Redaction, and Intent-vs-Outcome Telemetry."""

from __future__ import annotations

import datetime
import json
import logging
import os
import re
import time
from typing import Any, Literal

from opentelemetry import trace

from app.app_utils.typing import (
    IntentOutcomeAuditEntry,
    IntentRecord,
    OutcomeRecord,
)

SERVICE_NAME = "four-by-four-planner"
tracer = trace.get_tracer(f"{SERVICE_NAME}.telemetry")

# ---------------------------------------------------------------------------
# 1. Deterministic PII Redaction Engine
# ---------------------------------------------------------------------------

_PII_PATTERNS: tuple[tuple[str, re.Pattern[str], str], ...] = (
    (
        "email",
        re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
        "[REDACTED_EMAIL]",
    ),
    (
        "ssn",
        re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
        "[REDACTED_SSN]",
    ),
    (
        "credit_card",
        re.compile(r"\b(?:\d[ -]*?){13,16}\b"),
        "[REDACTED_CREDIT_CARD]",
    ),
    (
        "phone",
        re.compile(r"(?:(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]\d{3}[-.\s]\d{4})\b"),
        "[REDACTED_PHONE]",
    ),
    (
        "api_key",
        re.compile(
            r"\b(?:AIza[0-9A-Za-z\-_]{35}|ya29\.[0-9A-Za-z\-_]+|sk-[0-9A-Za-z]{20,})\b"
        ),
        "[REDACTED_API_KEY]",
    ),
    (
        "vin",
        re.compile(r"\b[A-HJ-NPR-Z0-9]{17}\b"),
        "[REDACTED_VIN]",
    ),
)

_SENSITIVE_FIELD_NAMES: frozenset[str] = frozenset(
    {
        "password",
        "passwd",
        "secret",
        "api_key",
        "apikey",
        "access_token",
        "refresh_token",
        "authorization",
        "ssn",
        "social_security",
        "credit_card",
        "card_number",
        "phone_number",
        "email_address",
        "driver_license",
        "vin",
    }
)


class PiiRedactor:
    """Scrubs Personal Identifiable Information (PII) and credentials from strings and data structures."""

    @staticmethod
    def redact_text(text: str) -> tuple[str, int]:
        """Redacts PII patterns from a string and returns `(redacted_text, redaction_count)`."""
        if not text:
            return text, 0
        total_redactions = 0
        scrubbed = text
        for _name, pattern, replacement in _PII_PATTERNS:
            scrubbed, count = pattern.subn(replacement, scrubbed)
            total_redactions += count
        return scrubbed, total_redactions

    @classmethod
    def redact_data(cls, value: Any) -> tuple[Any, int]:
        """Recursively redacts PII from dicts, lists, tuples, and strings."""
        if isinstance(value, str):
            return cls.redact_text(value)
        if isinstance(value, dict):
            redacted_dict: dict[str, Any] = {}
            total = 0
            for k, v in value.items():
                key_str = str(k)
                if key_str.lower() in _SENSITIVE_FIELD_NAMES:
                    redacted_dict[key_str] = "[REDACTED_SENSITIVE_FIELD]"
                    total += 1
                else:
                    clean_v, count = cls.redact_data(v)
                    redacted_dict[key_str] = clean_v
                    total += count
            return redacted_dict, total
        if isinstance(value, list):
            redacted_list = []
            total = 0
            for item in value:
                clean_item, count = cls.redact_data(item)
                redacted_list.append(clean_item)
                total += count
            return redacted_list, total
        if isinstance(value, tuple):
            redacted_items = []
            total = 0
            for item in value:
                clean_item, count = cls.redact_data(item)
                redacted_items.append(clean_item)
                total += count
            return tuple(redacted_items), total
        return value, 0

    @classmethod
    def redact_structure(cls, value: Any) -> Any:
        """Recursively redacts PII from a structure and returns only the sanitized value."""
        scrubbed, _ = cls.redact_data(value)
        return scrubbed


def redact_pii_text(text: str) -> str:
    """Convenience helper returning only the PII-scrubbed string."""
    scrubbed, _ = PiiRedactor.redact_text(text)
    return scrubbed


def redact_pii_data(data: Any) -> Any:
    """Convenience helper returning only the PII-scrubbed data structure."""
    scrubbed, _ = PiiRedactor.redact_data(data)
    return scrubbed


class PiiRedactionFilter(logging.Filter):
    """Python logging.Filter that scrubs PII from all log records before emission."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg, redaction_count = PiiRedactor.redact_text(record.msg)
            record.pii_redacted_count = (
                getattr(record, "pii_redacted_count", 0) + redaction_count
            )
        if record.args:
            if isinstance(record.args, dict):
                record.args, c = PiiRedactor.redact_data(record.args)
            elif isinstance(record.args, tuple):
                record.args, c = PiiRedactor.redact_data(record.args)
            else:
                c = 0
            record.pii_redacted_count = getattr(record, "pii_redacted_count", 0) + c
        return True


# ---------------------------------------------------------------------------
# 2. Structured JSON Logging with OpenTelemetry Trace Correlation
# ---------------------------------------------------------------------------


def _get_current_trace_context() -> tuple[str | None, str | None]:
    """Extracts the active OpenTelemetry trace_id and span_id if present."""
    span = trace.get_current_span()
    if not span:
        return None, None
    ctx = span.get_span_context()
    if not ctx.is_valid:
        return None, None
    return f"{ctx.trace_id:032x}", f"{ctx.span_id:016x}"


class StructuredJsonFormatter(logging.Formatter):
    """Formats Python log records as single-line structured JSON objects for Cloud Logging."""

    def format(self, record: logging.LogRecord) -> str:
        trace_id, span_id = _get_current_trace_context()
        message = record.getMessage()
        clean_message, msg_redactions = PiiRedactor.redact_text(message)

        payload: dict[str, Any] = {
            "timestamp": datetime.datetime.now(datetime.UTC).isoformat(),
            "severity": record.levelname,
            "service_name": SERVICE_NAME,
            "logger": record.name,
            "message": clean_message,
            "event_type": getattr(record, "event_type", "application_log"),
            "pii_redacted_count": getattr(record, "pii_redacted_count", 0)
            + msg_redactions,
        }
        if trace_id:
            payload["logging.googleapis.com/trace"] = trace_id
            payload["trace_id"] = trace_id
        if span_id:
            payload["logging.googleapis.com/spanId"] = span_id
            payload["span_id"] = span_id

        structured_data = getattr(record, "structured_data", None)
        if structured_data is not None:
            clean_data, data_redactions = PiiRedactor.redact_data(structured_data)
            payload["data"] = clean_data
            payload["pii_redacted_count"] += data_redactions

        if record.exc_info:
            exc_text = self.formatException(record.exc_info)
            payload["exception"], _ = PiiRedactor.redact_text(exc_text)

        return json.dumps(payload, default=str)


class StructuredAuditLogger:
    """Emits PII-redacted structured JSON logs to stdout and Google Cloud Logging."""

    def __init__(self) -> None:
        self._logger = logging.getLogger(f"{SERVICE_NAME}.audit")
        self._logger.setLevel(logging.INFO)
        if not self._logger.handlers:
            handler = logging.StreamHandler()
            handler.setFormatter(StructuredJsonFormatter())
            handler.addFilter(PiiRedactionFilter())
            self._logger.addHandler(handler)
            self._logger.propagate = False

        self._cloud_logger: Any = None
        should_init_cloud_client = bool(
            os.environ.get("K_SERVICE")
            or os.environ.get("AGENT_ENGINE_ID")
            or os.environ.get("ENABLE_CLOUD_LOGGING_RPC", "").lower() in ("true", "1")
        )
        if should_init_cloud_client and not os.environ.get("INTEGRATION_TEST"):
            try:
                from google.cloud import logging as google_cloud_logging

                client = google_cloud_logging.Client()
                self._cloud_logger = client.logger(SERVICE_NAME)
            except Exception:
                self._cloud_logger = None

    def log_event(
        self,
        event_type: str,
        message: str,
        data: dict[str, Any] | None = None,
        severity: Literal["INFO", "WARNING", "ERROR"] = "INFO",
    ) -> dict[str, Any]:
        """Logs a PII-scrubbed structured JSON event and returns the emitted payload."""
        clean_msg, msg_redactions = PiiRedactor.redact_text(message)
        clean_data, data_redactions = PiiRedactor.redact_data(data or {})
        trace_id, span_id = _get_current_trace_context()

        entry: dict[str, Any] = {
            "timestamp": datetime.datetime.now(datetime.UTC).isoformat(),
            "severity": severity,
            "service_name": SERVICE_NAME,
            "event_type": event_type,
            "message": clean_msg,
            "pii_redacted_count": msg_redactions + data_redactions,
            "data": clean_data,
        }
        if trace_id:
            entry["trace_id"] = trace_id
        if span_id:
            entry["span_id"] = span_id

        extra = {
            "event_type": event_type,
            "structured_data": clean_data,
            "pii_redacted_count": msg_redactions + data_redactions,
        }
        log_level = getattr(logging, severity, logging.INFO)
        self._logger.log(log_level, clean_msg, extra=extra)

        if self._cloud_logger is not None:
            try:
                self._cloud_logger.log_struct(entry, severity=severity)
            except Exception:
                pass

        return entry

    def log_struct(
        self,
        payload: dict[str, Any],
        severity: Literal["INFO", "WARNING", "ERROR"] = "INFO",
    ) -> dict[str, Any]:
        """Logs an arbitrary structured dictionary after PII redaction."""
        event_type = str(
            payload.get("log_type") or payload.get("event_type") or "structured_log"
        )
        message = str(payload.get("text") or payload.get("message") or event_type)
        return self.log_event(
            event_type=event_type,
            message=message,
            data=payload,
            severity=severity,
        )


audit_logger = StructuredAuditLogger()


# ---------------------------------------------------------------------------
# 3. Specific Intent vs. Outcome Capture
# ---------------------------------------------------------------------------


class IntentOutcomeTracker:
    """Tracks declared intent vs. actual execution outcome across agent, model, and tool steps."""

    def __init__(self) -> None:
        self._pending_intents: dict[str, tuple[IntentRecord, int]] = {}
        self.completed_entries: list[IntentOutcomeAuditEntry] = []

    def record_intent(
        self,
        *,
        invocation_id: str,
        session_id: str,
        actor: str,
        stage: Literal["agent", "model", "tool", "user_prompt"],
        declared_intent: str,
        raw_inputs: dict[str, Any] | None = None,
    ) -> IntentRecord:
        """Captures and logs the sanitized intent prior to step execution."""
        clean_intent, count_1 = PiiRedactor.redact_text(declared_intent)
        clean_inputs, count_2 = PiiRedactor.redact_data(raw_inputs or {})
        record = IntentRecord(
            invocation_id=invocation_id,
            session_id=session_id,
            actor=actor,
            stage=stage,
            declared_intent=clean_intent,
            sanitized_inputs=clean_inputs,
            timestamp_start_ms=round(time.time() * 1000.0, 2),
        )
        key = f"{stage}:{actor}:{invocation_id}"
        self._pending_intents[key] = (record, count_1 + count_2)

        span = trace.get_current_span()
        if span and span.is_recording():
            span.set_attribute("offroad.intent.actor", actor)
            span.set_attribute("offroad.intent.stage", stage)
            span.set_attribute("offroad.intent.declared", clean_intent)

        audit_logger.log_event(
            event_type="intent_captured",
            message=f"[{stage.upper()} INTENT] {actor}: {clean_intent}",
            data=record.model_dump(mode="json"),
            severity="INFO",
        )
        return record

    def record_outcome(
        self,
        *,
        invocation_id: str,
        session_id: str,
        actor: str,
        stage: Literal["agent", "model", "tool", "user_prompt"],
        status: Literal["success", "blocked_by_guardrail", "error", "pending_hitl"],
        intent_fulfilled: bool,
        actual_outcome_summary: str,
        safety_verdict: str = "PASS",
        discrepancy_reason: str | None = None,
        fallback_declared_intent: str = "Execute requested step safely",
    ) -> IntentOutcomeAuditEntry:
        """Pairs the actual outcome with its prior IntentRecord and emits a structured audit log."""
        key = f"{stage}:{actor}:{invocation_id}"
        now_ms = round(time.time() * 1000.0, 2)
        prior = self._pending_intents.pop(key, None)

        if prior is not None:
            intent_record, prior_redactions = prior
            latency_ms = max(0.0, round(now_ms - intent_record.timestamp_start_ms, 2))
        else:
            intent_record = IntentRecord(
                invocation_id=invocation_id,
                session_id=session_id,
                actor=actor,
                stage=stage,
                declared_intent=redact_pii_text(fallback_declared_intent),
                sanitized_inputs={},
                timestamp_start_ms=now_ms,
            )
            prior_redactions = 0
            latency_ms = 0.0

        clean_summary, out_redactions = PiiRedactor.redact_text(actual_outcome_summary)
        clean_discrepancy = (
            redact_pii_text(discrepancy_reason) if discrepancy_reason else None
        )

        outcome_record = OutcomeRecord(
            invocation_id=invocation_id,
            actor=actor,
            stage=stage,
            status=status,
            intent_fulfilled=intent_fulfilled,
            safety_verdict=safety_verdict,
            actual_outcome_summary=clean_summary,
            discrepancy_reason=clean_discrepancy,
            latency_ms=latency_ms,
        )

        entry = IntentOutcomeAuditEntry(
            intent=intent_record,
            outcome=outcome_record,
            pii_redacted_count=prior_redactions + out_redactions,
        )
        self.completed_entries.append(entry)

        span = trace.get_current_span()
        if span and span.is_recording():
            span.set_attribute("offroad.outcome.status", status)
            span.set_attribute("offroad.outcome.intent_fulfilled", intent_fulfilled)
            span.set_attribute("offroad.outcome.safety_verdict", safety_verdict)
            span.set_attribute("offroad.outcome.latency_ms", latency_ms)
            span.set_attribute(
                "offroad.telemetry.pii_redacted_count", entry.pii_redacted_count
            )

        severity: Literal["INFO", "WARNING", "ERROR"] = (
            "INFO"
            if (status == "success" and intent_fulfilled)
            else (
                "WARNING"
                if status in ("blocked_by_guardrail", "pending_hitl")
                else "ERROR"
            )
        )
        audit_logger.log_event(
            event_type="intent_vs_outcome",
            message=(
                f"[{stage.upper()} INTENT vs OUTCOME] {actor} | "
                f"intent='{intent_record.declared_intent}' -> "
                f"outcome='{clean_summary}' (fulfilled={intent_fulfilled}, "
                f"safety={safety_verdict}, latency_ms={latency_ms})"
            ),
            data=entry.model_dump(mode="json"),
            severity=severity,
        )
        return entry


intent_outcome_tracker = IntentOutcomeTracker()


def setup_telemetry() -> None:
    """Configures OpenTelemetry GenAI environment defaults and structured JSON logging."""
    os.environ.setdefault("OTEL_SERVICE_NAME", SERVICE_NAME)
    os.environ.setdefault(
        "OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT", "NO_CONTENT"
    )
    os.environ.setdefault("ADK_CAPTURE_MESSAGE_CONTENT_IN_SPANS", "false")

    root_logger = logging.getLogger()
    if not any(isinstance(f, PiiRedactionFilter) for f in root_logger.filters):
        root_logger.addFilter(PiiRedactionFilter())
