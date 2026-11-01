# Skill: MEDDPICC

Qualification framework for enterprise and mid-market deals. Used by deal inspection,
conversation capture and the account program. Each element is either evidenced or unknown.
Never mark an element as met without an evidence id.

| Element | Met when there is evidence of | Typical strong evidence |
| --- | --- | --- |
| Metrics | A number the buyer cares about and our effect on it | call_quote with the number |
| Economic buyer | The person who can approve the spend, and their stated view | meeting_attended plus call_quote |
| Decision criteria | What the buyer will compare on, in their words | call_quote, email_from_contact |
| Decision process | The steps, people and dates to a decision | email_from_contact with the plan |
| Paper process | Legal, security review, procurement steps and owners | email_from_contact, crm_record |
| Identify pain | The problem, its cost, and who feels it | call_quote |
| Champion | Someone with influence who sells for us when we are not there, and has acted on it | email_from_contact showing action |
| Competition | Alternatives being considered, including doing nothing | call_quote |

## How to use it
- Score each element as evidenced, partial (weak evidence only) or unknown. Report the ids.
- A deal in a late stage with economic buyer or paper process unknown is a risk. Say so.
- A champion is shown by action (introductions, internal forwarding, pushing a meeting), not by
  friendliness. Friendly with no action is "partial".
- Do not fill elements from enrichment data or job titles alone.
