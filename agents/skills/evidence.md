# Skill: evidence

Every loop loads this skill. It is the rule that makes everything else checkable.

## What evidence is
One sourced observation about one subject: a quote from a call, an email from the person, a usage
metric, a contract on file, something a seller saw first-hand. Record it with `record_evidence`.
Give the source (`source_uri`) precisely enough that a human can open it: a call link with a
timestamp, an email id, a query.

## Strength is not yours to set
The database sets strength from the kind of evidence. You never grade your own certainty.

| Strong | Weak |
| --- | --- |
| call_quote, email_from_contact, signature_block, meeting_attended, product_usage, crm_record, rep_observation | partner_report, enrichment_vendor, web_page, social_post, inferred |

## Rules
1. No id, no claim. Every statement about an account or a person cites evidence ids.
2. Weak evidence can shape a question to ask. It is never stated as a fact.
3. Never infer a person's role, seniority or authority without evidence of it. A blank is better
   than a confident wrong fact, because nobody can tell the wrong fact is wrong.
4. When new evidence contradicts old evidence, record the new row and call `supersede_evidence`.
   Do not argue with history. Evidence is append-only.
5. When evidence conflicts and you cannot tell which is right, call `escalate` with both ids.
