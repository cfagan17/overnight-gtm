"""Tool definitions: what the model sees, and which database function each one calls.

The model never sees or passes a run id. The runner adds it, so an agent cannot act
inside another agent's run even if a prompt told it to.
"""
from __future__ import annotations

import json

SUBJECT_TYPES = ["company", "contact", "deal", "partner", "territory", "skill", "loop"]

# name -> (rpc function, description, input schema properties, required, rpc arg order)
# rpc arg order lists the function's parameters after p_run_id, mapped from input keys.
TOOLS: dict[str, dict] = {
    "get_account_context": {
        "rpc": "get_account_context", "run_arg": "p_run_id",
        "description": "Everything visible about one account: company, contacts, open deals with partner credit, "
                       "contracts, latest evidence, last three strategy versions with their reviews, open commitments, "
                       "and whether the account is in an experiment holdout.",
        "properties": {"company_id": {"type": "integer"}},
        "required": ["company_id"],
        "args": {"p_company_id": "company_id"},
    },
    "search_evidence": {
        "rpc": "search_evidence", "run_arg": "p_run_id",
        "description": "Search evidence about one subject, newest first, excluding superseded rows.",
        "properties": {"subject_type": {"type": "string", "enum": SUBJECT_TYPES}, "subject_id": {"type": "string"},
                       "kinds": {"type": "array", "items": {"type": "string"}},
                       "since": {"type": "string", "description": "ISO timestamp"},
                       "limit": {"type": "integer"}},
        "required": ["subject_type", "subject_id"],
        "args": {"p_subject_type": "subject_type", "p_subject_id": "subject_id", "p_kinds": "kinds",
                 "p_since": "since", "p_limit": "limit"},
    },
    "get_policies": {
        "rpc": "get_policies", "run_arg": "p_run_id",
        "description": "Active rules of engagement, and for a contact: do-not-contact status, touches in the last "
                       "14 days, and partner credit on the account.",
        "properties": {"contact_id": {"type": "integer"}},
        "required": [],
        "args": {"p_contact_id": "contact_id"},
    },
    "record_evidence": {
        "rpc": "record_evidence", "run_arg": "p_run_id",
        "description": "Record one sourced observation. Strength is set by the database from the kind.",
        "properties": {"subject_type": {"type": "string", "enum": SUBJECT_TYPES}, "subject_id": {"type": "string"},
                       "kind": {"type": "string", "enum": ["call_quote", "email_from_contact", "signature_block",
                                "meeting_attended", "product_usage", "crm_record", "rep_observation",
                                "partner_report", "enrichment_vendor", "web_page", "social_post", "inferred"]},
                       "claim": {"type": "string", "description": "The observation in one or two sentences. Quote when quoting."},
                       "source_uri": {"type": "string", "description": "Where a human can check it: call link with timestamp, email id, URL"},
                       "observed_at": {"type": "string", "description": "ISO timestamp of when it was observed"}},
        "required": ["subject_type", "subject_id", "kind", "claim", "source_uri", "observed_at"],
        "args": {"p_subject_type": "subject_type", "p_subject_id": "subject_id", "p_kind": "kind", "p_claim": "claim",
                 "p_source_uri": "source_uri", "p_observed_at": "observed_at"},
    },
    "supersede_evidence": {
        "rpc": "supersede_evidence", "run_arg": "p_run_id",
        "description": "Mark an older evidence row as superseded by a newer one about the same subject.",
        "properties": {"old_id": {"type": "integer"}, "new_id": {"type": "integer"}},
        "required": ["old_id", "new_id"],
        "args": {"p_old_id": "old_id", "p_new_id": "new_id"},
    },
    "propose_decision": {
        "rpc": "propose_decision", "run_arg": "p_run_id",
        "description": "Propose a decision for human review, citing at least one evidence id. Actions used by the "
                       "write tools: propose_strategy, update_field (payload: table, field, row_id, value), "
                       "schedule_touch, propose_skill_version. Other actions (flag_risk, propose_partner, ...) are "
                       "recommendations a human acts on.",
        "properties": {"action": {"type": "string"}, "subject_type": {"type": "string", "enum": SUBJECT_TYPES},
                       "subject_id": {"type": "string"}, "rationale": {"type": "string"},
                       "evidence_ids": {"type": "array", "items": {"type": "integer"}, "minItems": 1},
                       "payload": {"type": "object"}},
        "required": ["action", "subject_type", "subject_id", "rationale", "evidence_ids"],
        "args": {"p_action": "action", "p_subject_type": "subject_type", "p_subject_id": "subject_id",
                 "p_rationale": "rationale", "p_evidence_ids": "evidence_ids", "p_payload": "payload"},
    },
    "propose_strategy": {
        "rpc": "propose_strategy", "run_arg": "p_run_id",
        "description": "File a new strategy version for an account, partner or territory. Every evidence id in the "
                       "plan must be cited by the decision.",
        "properties": {"decision_id": {"type": "integer"}, "subject_type": {"type": "string", "enum": ["company", "partner", "territory"]},
                       "subject_id": {"type": "string"}, "plan": {"type": "object"}},
        "required": ["decision_id", "subject_type", "subject_id", "plan"],
        "args": {"p_decision_id": "decision_id", "p_subject_type": "subject_type", "p_subject_id": "subject_id", "p_plan": "plan"},
    },
    "apply_field_update": {
        "rpc": "apply_field_update", "run_arg": "p_run_id",
        "description": "Change one allowlisted field, citing an update_field decision with strong evidence. Applies at "
                       "level 3 and above, queues for the record owner at level 2.",
        "properties": {"decision_id": {"type": "integer"}, "table": {"type": "string", "enum": ["deals", "contacts", "companies"]},
                       "row_id": {"type": "integer"}, "field": {"type": "string"}, "value": {}},
        "required": ["decision_id", "table", "row_id", "field", "value"],
        "args": {"p_decision_id": "decision_id", "p_table": "table", "p_row_id": "row_id", "p_field": "field", "p_value": "value"},
    },
    "schedule_touch": {
        "rpc": "schedule_touch", "run_arg": "p_run_id",
        "description": "Schedule an outbound touch for a schedule_touch decision. Policies are checked by the database.",
        "properties": {"decision_id": {"type": "integer"}, "contact_id": {"type": "integer"},
                       "channel": {"type": "string", "enum": ["email", "call", "linkedin", "meeting", "partner_intro", "sms", "event"]},
                       "sender_type": {"type": "string", "enum": ["agent", "rep", "executive", "partner", "se"]},
                       "purpose": {"type": "string"}, "content_ref": {"type": "string"}, "scheduled_for": {"type": "string"}},
        "required": ["decision_id", "contact_id", "channel", "sender_type", "purpose"],
        "args": {"p_decision_id": "decision_id", "p_contact_id": "contact_id", "p_channel": "channel",
                 "p_sender_type": "sender_type", "p_purpose": "purpose", "p_content_ref": "content_ref",
                 "p_scheduled_for": "scheduled_for"},
    },
    "propose_external_update": {
        "rpc": "propose_external_update", "run_arg": "p_run_id",
        "description": "Sidecar mode: propose a change to one allowlisted field in Salesforce or HubSpot, citing an "
                       "update_external_field decision (payload: system, object, field, value) with strong evidence. "
                       "Approved at level 3 and above, waits for the record owner at level 2. A writeback worker sends it.",
        "properties": {"decision_id": {"type": "integer"}, "system": {"type": "string", "enum": ["salesforce", "hubspot"]},
                       "object": {"type": "string"}, "record_id": {"type": "string"}, "field": {"type": "string"}, "value": {}},
        "required": ["decision_id", "system", "object", "record_id", "field", "value"],
        "args": {"p_decision_id": "decision_id", "p_system": "system", "p_object": "object", "p_record_id": "record_id",
                 "p_field": "field", "p_value": "value"},
    },
    "create_commitment": {
        "rpc": "create_commitment", "run_arg": "p_run_id",
        "description": "Record something our side promised the customer, pointing to the evidence of the promise.",
        "properties": {"subject_type": {"type": "string", "enum": ["company"]}, "subject_id": {"type": "string"},
                       "promise": {"type": "string"}, "due_on": {"type": "string", "description": "YYYY-MM-DD"},
                       "evidence_id": {"type": "integer"}},
        "required": ["subject_type", "subject_id", "promise", "evidence_id"],
        "args": {"p_subject_type": "subject_type", "p_subject_id": "subject_id", "p_promise": "promise",
                 "p_due_on": "due_on", "p_evidence_id": "evidence_id"},
    },
    "escalate": {
        "rpc": "escalate", "run_arg": "p_run_id",
        "description": "Hand a case to a named human with the reason. Use when unsure or when evidence conflicts.",
        "properties": {"subject_type": {"type": "string", "enum": SUBJECT_TYPES}, "subject_id": {"type": "string"},
                       "to_user": {"type": "string", "description": "auth user id of an active human"},
                       "reason": {"type": "string"}},
        "required": ["subject_type", "subject_id", "to_user", "reason"],
        "args": {"p_subject_type": "subject_type", "p_subject_id": "subject_id", "p_to_user": "to_user", "p_reason": "reason"},
    },
    "propose_skill_version": {
        "rpc": "propose_skill_version", "run_arg": "p_run_id",
        "description": "Propose a new version of a skill file, citing a propose_skill_version decision. An owner approves it.",
        "properties": {"decision_id": {"type": "integer"}, "name": {"type": "string"}, "body": {"type": "string"}},
        "required": ["decision_id", "name", "body"],
        "args": {"p_decision_id": "decision_id", "p_name": "name", "p_body": "body"},
    },
}

# Postgres types for RPC arguments that need a cast when called over a direct connection.
CASTS = {"p_skill_versions": "jsonb", "p_evidence_ids": "bigint[]", "p_kinds": "text[]", "p_payload": "jsonb", "p_plan": "jsonb", "p_value": "jsonb",
         "p_since": "timestamptz", "p_observed_at": "timestamptz", "p_scheduled_for": "timestamptz", "p_due_on": "date",
         "p_to_user": "uuid"}
JSON_ARGS = {"p_payload", "p_plan", "p_value", "p_skill_versions"}


def anthropic_tools(names: list[str]) -> list[dict]:
    """Tool list in the Anthropic Messages API format."""
    return [{"name": n, "description": TOOLS[n]["description"],
             "input_schema": {"type": "object", "properties": TOOLS[n]["properties"], "required": TOOLS[n]["required"]}}
            for n in names]


def rpc_args(name: str, tool_input: dict) -> dict:
    spec = TOOLS[name]
    out = {}
    for arg, key in spec["args"].items():
        if key in tool_input and tool_input[key] is not None:
            v = tool_input[key]
            # ids that are text in the database (subject ids) may arrive as numbers from a model
            out[arg] = str(v) if arg == "p_subject_id" else v
    return out


if __name__ == "__main__":
    print(json.dumps(anthropic_tools(list(TOOLS)), indent=2))
