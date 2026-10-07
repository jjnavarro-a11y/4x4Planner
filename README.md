# four-by-four-planner

Production-grade **4x4 Road Trip & Overlanding Planner Agent** built with the Google Agent Development Kit (ADK).

## Key Capabilities & Architecture

1. **Tool & Interface Design (`app/tools.py`, `app/app_utils/typing.py`)**
   - All tools use strict Pydantic input parameters and return strict `StrictToolModel(BaseModel)` schemas (`extra="forbid"`): `TrailSearchOutput`, `RigCompatibilityOutput`, `FuelPlanOutput`, `TrailWeatherOutput`, `SavedRigProfileOutput`, and `BackcountryPermitApprovalOutput`.
   - Every tool includes structured `recovery_instructions` so the LLM can self-correct when a trail is rejected for mechanical incompatibility or exceeds the 75% backcountry fuel budget.

2. **Context & Memory (`app/app_utils/memory_config.py`, `app/app_utils/services.py`)**
   - **Vertex AI Memory Bank:** Uses `VertexAiMemoryBankService` in production and `InMemoryMemoryService` locally, configured with `memory_bank_config` (`ReasoningEngineContextSpecMemoryBankConfig`) for both managed and custom overlanding memory topics (`user_4x4_rig_build_profile`, `backcountry_safety_and_camping_preferences`).
   - **State & Artifact Persistence:** `PreloadMemoryTool()`, `initialize_overlanding_state` (`before_agent_callback`), `generate_memories_callback` (`after_agent_callback` calling `add_session_to_memory()`), and `save_user_rig_profile` persist vehicle builds across turns/sessions in `user:rig_profile` and as JSON artifacts.
   - **Context Compaction & Caching:** Configured with `EventsCompactionConfig` (`LlmEventSummarizer`) and `ContextCacheConfig`.

3. **Orchestration & Logic (`app/agent.py`, `app/app_utils/safety_plugins.py`)**
   - **Multi-Model Routing:**
     - `gemini-3.8-flash` on `four_by_four_planner` (Coordinator Agent)
     - `gemini-2.5-flash` on `web_trail_researcher` (`AgentTool`) and `LlmEventSummarizer`
     - `gemini-2.5-pro` on `safety_compliance_auditor` (`AgentTool`) for deep multi-constraint backcountry risk auditing
   - **Runner-Wide Safety Plugins (`BasePlugin`):** `OffroadSafetyGuardrailPlugin` (two-phase session-poisoning defense via `on_user_message_callback` + `before_run_callback`, PII redaction, and Intent-vs-Outcome capture), `ReflectAndRetryToolPlugin`, `ContextFilterPlugin`, and `BigQueryAgentAnalyticsPlugin`.
   - **Human-in-the-Loop (HITL):** `ResumabilityConfig(is_resumable=True)` and `FunctionTool(submit_backcountry_trip_registration, require_confirmation=requires_high_risk_confirmation)` require explicit human approval for extreme trails (`>= 7/10`), solo advanced routes (`>= 6/10`), or permit-required traverses.

4. **Observability & Tracing (`app/app_utils/telemetry.py`, `app/fast_api_app.py`)**
   - **OpenTelemetry Tracing:** Enabled via `otel_to_cloud = True` in `app/fast_api_app.py`.
   - **Structured JSON Logging:** `StructuredJsonFormatter` and `StructuredAuditLogger` emit trace-correlated JSON logs to stdout and Google Cloud Logging (`log_struct`).
   - **Intent vs. Outcome Capture:** `IntentOutcomeTracker` pairs every `IntentRecord` with its `OutcomeRecord` (`IntentOutcomeAuditEntry`) across `user_prompt`, `agent`, `model`, and `tool` lifecycle stages.
   - **PII Redaction:** `PiiRedactor` and `PiiRedactionFilter` scrub emails, phone numbers, SSNs, credit cards, API keys, VINs, and sensitive keys across prompts, tool payloads, and logs.

5. **Infrastructure & CI/CD (`deployment/terraform/`, `.github/workflows/`, `app/app_utils/secrets.py`)**
   - **Terraform IaC:** Single-project (`deployment/terraform/single-project/`) and multi-environment CI/CD (`deployment/terraform/cicd/`) modules provisioning Vertex AI, Cloud Run, IAM, GCS, BigQuery/Cloud Trace telemetry sinks, Workload Identity Federation, and Secret Manager (`google_secret_manager_secret`).
   - **GitHub Actions CI/CD:** Automated PR evaluation/test gates (`.github/workflows/pr_checks.yaml`), staging deployment (`staging.yaml`), and production deployment (`deploy-to-prod.yaml`).
   - **Secret Management:** `app/app_utils/secrets.py` integrates Google Cloud Secret Manager via ADC with local environment variable fallback.

## Project Structure

```
four-by-four-planner/
├── app/
│   ├── agent.py                        # Multi-model coordinator, sub-agents, HITL, compaction & cache config
│   ├── tools.py                        # Deterministic tools with strict Pydantic schemas
│   ├── fast_api_app.py                 # FastAPI server with OTel tracing, MemoryService & audit routes
│   └── app_utils/
│       ├── typing.py                   # Strict Pydantic tool output, telemetry & feedback schemas
│       ├── safety_plugins.py           # OffroadSafetyGuardrailPlugin (BasePlugin)
│       ├── telemetry.py                # StructuredJsonFormatter, PiiRedactor & IntentOutcomeTracker
│       ├── memory_config.py            # Vertex AI Memory Bank config & state/memory callbacks
│       ├── secrets.py                  # Google Cloud Secret Manager helper with ADC
│       └── services.py                 # Session, Artifact, and Memory service factories
├── .github/workflows/                  # GitHub Actions CI/CD pipelines (PR checks, staging, prod)
├── deployment/terraform/               # Terraform IaC (single-project & cicd)
├── eval/                               # Evaluation dataset & rubric metrics
├── tests/                              # Unit, integration, and load tests
├── GEMINI.md                           # AI-assisted development guide
└── pyproject.toml                      # Project dependencies
```

## Quick Start

```bash
uv run pytest tests/unit
agents-cli lint
agents-cli eval run
```
