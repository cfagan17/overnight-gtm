# Skill: stages

Deal stages and their exit criteria. Stage names match Atomic CRM's defaults. An agent may
propose a stage change only when the exit criteria for the current stage are evidenced.

| Stage | Means | Exit to next stage requires evidence of |
| --- | --- | --- |
| opportunity | A qualified conversation about a real problem | Pain identified, a metric, and an agreed next step |
| proposal-sent | A proposal or pricing is with the buyer | Buyer engaged on the proposal, economic buyer known, decision process known |
| in-negociation | Terms are being negotiated | Paper process started (legal or security review), verbal selection |
| won | Signed | A signed order form or contract on file (crm_record) |
| lost | The buyer chose otherwise or stopped | The buyer said so, or 60 days without response after two follow-ups |
| delayed | A real decision moved out | The buyer gave a new date |

## Rules
- Moving forward needs strong evidence. Moving backward (or to delayed) can be proposed on weak
  evidence, as a question for the owner.
- `won` is never set by an agent. Closing is a human act tied to a signed document.
- The operating design loop may propose new exit criteria. They take effect only when an owner
  approves a new version of this skill.
