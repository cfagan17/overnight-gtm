// Static facts about the loops, mirrored from agents/loops/*/loop.yaml.
export type LoopMeta = { loop: string; name: string; job: string; cadence: string; area: string; skills: string[]; color: string };

export const LOOPS: LoopMeta[] = [
  { loop: 'market_model', name: 'Market model', job: 'Scores accounts against the ideal customer profile.', cadence: 'Every 3 nights', area: 'Strategy', skills: ['evidence', 'market-model'], color: '#60a5fa' },
  { loop: 'account_program', name: 'Account program', job: 'Writes the approach plan for one account.', cadence: 'Nightly', area: 'Selling', skills: ['evidence', 'account-plan', 'meddpicc'], color: '#a78bfa' },
  { loop: 'outreach', name: 'Outreach', job: 'Carries out the next step of an approved plan.', cadence: 'Nightly', area: 'Selling', skills: ['evidence', 'outreach-policy'], color: '#a78bfa' },
  { loop: 'conversation_capture', name: 'Conversation capture', job: 'Turns each call into evidence, commitments and field updates.', cadence: 'After every call', area: 'Selling', skills: ['evidence', 'conversation-capture', 'meddpicc', 'stages'], color: '#a78bfa' },
  { loop: 'deal_inspection', name: 'Deal inspection', job: 'Finds the deals most at risk and proposes one next step each.', cadence: 'Nightly', area: 'Selling', skills: ['evidence', 'deal-inspection', 'meddpicc'], color: '#a78bfa' },
  { loop: 'forecast', name: 'Forecast', job: 'Makes an independent forecast call by segment.', cadence: 'Weekly', area: 'Planning', skills: ['evidence', 'forecast-method'], color: '#34d399' },
  { loop: 'post_sale_health', name: 'Customer health', job: 'Scores customer health and flags churn risk or expansion.', cadence: 'Every 2 nights', area: 'Customers', skills: ['evidence', 'health-score'], color: '#f472b6' },
  { loop: 'partner_intelligence', name: 'Partner intelligence', job: 'Reviews partner activity and proposes partner plays.', cadence: 'Weekly', area: 'Partners', skills: ['evidence', 'partner-strategy'], color: '#fbbf24' },
  { loop: 'product_feedback', name: 'Product feedback', job: 'Groups customer feedback into themes for the product team.', cadence: 'Weekly', area: 'Customers', skills: ['evidence', 'product-feedback'], color: '#f472b6' },
  { loop: 'territory_capacity', name: 'Territories and capacity', job: 'Proposes the territory carve and capacity model.', cadence: 'Each planning cycle', area: 'Planning', skills: ['evidence', 'territory-method'], color: '#34d399' },
  { loop: 'comp_ops', name: 'Comp ops', job: 'Proposes credit splits and payouts each pay period.', cadence: 'Every 2 weeks', area: 'Planning', skills: ['evidence', 'comp-credit'], color: '#34d399' },
  { loop: 'operating_design', name: 'Sales process design', job: 'Proposes changes to how the GTM system itself works.', cadence: 'Quarterly', area: 'Strategy', skills: ['evidence', 'operating-design'], color: '#60a5fa' },
];
export const LOOP = Object.fromEntries(LOOPS.map((l) => [l.loop, l]));
export const loopName = (l: string) => LOOP[l]?.name || l;

export const LEVELS = ['Observe', 'Suggest', 'Act with approval', 'Act and report', 'Act on its own'];
export const LEVEL_HELP = [
  'Reads and records evidence only.',
  'Proposes. A person acts on it or not.',
  'Queues actions. A person approves each one.',
  'Acts within its allowlist and reports. People review samples.',
  'Acts on its own within policy. People audit.',
];

export const ACTION_LABEL: Record<string, string> = {
  propose_strategy: 'Account plan', flag_risk: 'Deal risk', update_field: 'Field update', schedule_touch: 'Outreach step',
  flag_churn_risk: 'Churn risk', flag_expansion: 'Expansion', propose_icp_change: 'ICP change', propose_partner: 'New partner',
  product_theme: 'Product theme', propose_credit: 'Comp credit', propose_carve: 'Territory carve', propose_skill_version: 'Skill change',
};

export const STAGES = [
  { id: 'opportunity', name: 'Opportunity' }, { id: 'proposal-sent', name: 'Proposal sent' },
  { id: 'in-negociation', name: 'Negotiation' }, { id: 'won', name: 'Won' }, { id: 'lost', name: 'Lost' },
];

export const PERSONAS = [
  { key: 'maya', email: 'ana.rep@northwind.example', name: 'Maya Chen', role: 'Account executive', see: 'Her review inbox and her accounts in West Enterprise.', color: '#2dd4bf' },
  { key: 'sam', email: 'riley.ops@northwind.example', name: 'Sam Rivera', role: 'Rev Ops, owner', see: 'Everything. Owns the loops, prompts, promotions and policies.', color: '#fb923c' },
  { key: 'vic', email: 'vic.vp@northwind.example', name: 'Vic Moreno', role: 'VP Sales', see: 'Both regions, the forecast, and how the loops are doing.', color: '#60a5fa' },
  { key: 'cy', email: 'cy.rep@northwind.example', name: 'Cy Nakamura', role: 'Account executive, East', see: 'Only the East. Row-level security hides the West.', color: '#a78bfa' },
  { key: 'pat', email: 'pat.partners@northwind.example', name: 'Pat Quinn', role: 'Partner manager', see: 'Partner plans and partner-sourced deals.', color: '#f472b6' },
  { key: 'morgan', email: 'fin.readonly@northwind.example', name: 'Morgan Lee', role: 'Finance, read-only', see: 'Everything, read-only. Comp and territory sign-off stays with owners.', color: '#34d399' },
];
