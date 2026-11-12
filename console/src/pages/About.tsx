import { Github } from 'lucide-react';
import { Card, Page } from '../components/ui';

const LAYERS = [
  ['5', 'People', 'Review, correct, and decide how far to trust each loop. In Slack day to day, in this console for the full picture.', '#be185d'],
  ['4', 'Loops', 'Twelve agent loops, one per Rev Ops function, each a plain-English prompt that runs every night or week.', '#b45309'],
  ['3', 'Primitives', 'Evidence, decisions, strategies, experiments, policies, commitments, runs, skills: the why behind every change.', '#1d4ed8'],
  ['2', 'Control plane', 'Who can see and change what, enforced in Postgres. Agents have no direct write access.', '#047857'],
  ['1', 'Ledger', 'Accounts, contacts, deals, contracts, territories. Supabase here, or Salesforce or HubSpot beside it.', '#0f766e'],
];

export default function About() {
  return (
    <Page kicker="About" title="What this console is, and is not">
      <div className="grid gap-6 xl:grid-cols-[1fr_420px]">
        <div className="space-y-6">
          <Card>
            <div className="space-y-4 text-[15px] leading-relaxed text-ink-muted">
              <p><b className="text-ink">Overnight</b> puts frontier models at the center of how go to market makes decisions. Each Rev Ops function becomes a loop that reads all of the data on a schedule, decides what to do, and writes down why. People review the work, and each loop earns more autonomy only as fast as its record allows.</p>
              <p><b className="text-ink">Day to day, nobody needs this console.</b> Reps review in a Slack message each morning. Agents work through database functions. Analysts query the primitives with SQL. The console is the window onto all of it: for the Rev Ops owner running the loops, for a leader asking why, and for anyone evaluating the model.</p>
              <p><b className="text-ink">The console holds no rules.</b> Every button calls a database function that checks permissions, scope and policy itself, and row-level security decides what each person sees. Sign in as Cy and the West disappears. Try to promote a loop that has not cleared the bar, and the database refuses.</p>
            </div>
          </Card>
          <Card title="The five layers" pad={false}>
            <ul className="divide-y divide-night-600/60">{LAYERS.map(([n, name, text, c]) => (
              <li key={n} className="flex gap-4 px-5 py-4"><span className="mt-0.5 w-16 shrink-0 text-xs font-bold" style={{ color: c }}>Layer {n}</span><div><div className="font-bold">{name}</div><div className="mt-0.5 text-sm text-ink-muted">{text}</div></div></li>
            ))}</ul>
          </Card>
        </div>
        <div className="space-y-6">
          <Card title="Open source">
            <p className="text-sm text-ink-muted">Everything here, the database, the twelve loop prompts, the skills, the runner, the tests and this console, is in one repo. Point your own AI at it.</p>
            <a className="btn-primary mt-4" href="https://github.com/cfagan17/overnight-gtm" target="_blank" rel="noreferrer"><Github size={16} />github.com/cfagan17/overnight-gtm</a>
          </Card>
          <Card title="About the demo">
            <ul className="space-y-2 text-sm text-ink-muted">
              <li>Northwind Data and everyone in it are fictional.</li>
              <li>The Acme Orchards plan in Maya's inbox is a real Claude run, unedited.</li>
              <li>The rest of the history is generated from a fixed seed: two months of runs, reviews, a model upgrade, one violation and a holdout experiment.</li>
              <li>What you do here is real in the demo database, which is reset regularly.</li>
            </ul>
          </Card>
          <Card title="Built by"><p className="text-sm text-ink-muted">Cameron Fagan, with Claude.</p></Card>
        </div>
      </div>
    </Page>
  );
}
