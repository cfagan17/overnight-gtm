# Skill: account plan

Method for the account program loop: how to plan the approach to one account.

## Order of work
1. Why now. Find the one or two strongest recent signals (usage change, new leader, funding,
   a project, a trigger event in the buyer's words). If nothing is recent and strong, the right
   plan is to wait, and say what signal would change that.
2. Entry points. Up to three people, each with the reason they are the right door, from evidence.
   Prefer people with pain and influence over people with titles.
3. Sender. Who on our side should make first contact: rep, executive, SE, partner, or agent.
   - Partner-sourced or partner-owned accounts go through the partner (policy).
   - Strategic accounts and executives get a human sender. Agents send only where the reviewer
     history shows they are accepted for this segment.
4. Channel and sequence. The first three touches and the purpose of each. Each touch earns the next.
5. Content. What each touch carries, tied to evidence of what this account cares about.
6. Risks. What would make this plan wrong.
7. What would change it. The signal that should trigger a new version.

## Learn from review
Read the last versions of the plan and how the owner reviewed them (accepted, edited, rejected,
and their edits). If owners keep changing the same thing, do it their way and say so.

## Output shape
```json
{"why_now": [{"claim": "...", "evidence": [1]}],
 "entry_points": [{"contact_id": 1, "reason": "...", "evidence": [2]}],
 "sender": {"type": "rep|executive|se|partner|agent", "reason": "..."},
 "channel_and_sequence": [{"step": 1, "channel": "email", "purpose": "..."}],
 "content": [{"step": 1, "carries": "...", "evidence": [3]}],
 "risks": ["..."], "what_would_change_it": "..."}
```
Every `evidence` id must also be cited by the decision you file with the plan. The database
refuses the plan otherwise.
