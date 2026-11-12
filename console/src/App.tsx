import { useEffect, useRef } from 'react';
import { Navigate, Route, Routes, useSearchParams } from 'react-router-dom';
import { useSession } from './lib/session';
import { DEMO } from './lib/supabase';
import { PERSONAS } from './lib/meta';
import Layout from './components/Layout';
import { Spinner, Toasts } from './components/ui';
import Login from './pages/Login';
import Today from './pages/Today';
import Reviews from './pages/Reviews';
import Accounts from './pages/Accounts';
import Account from './pages/Account';
import Pipeline from './pages/Pipeline';
import Loops from './pages/Loops';
import Loop from './pages/Loop';
import { Run, Runs } from './pages/Runs';
import Experiments from './pages/Experiments';
import Insights from './pages/Insights';
import { Audit, Policies } from './pages/Policies';
import Slack from './pages/Slack';
import About from './pages/About';

export default function App() {
  const { session, me, loading, signInAs } = useSession();
  // Demo only: ?as=maya on any page signs the visitor in as that demo person, then opens the page.
  // It works for the six people on the sign-in page and nobody else, and does nothing when the
  // console points at a real project. It gives no access the sign-in page does not already give.
  const [params, setParams] = useSearchParams();
  const want = DEMO ? PERSONAS.find((p) => p.key === params.get('as')?.toLowerCase()) : undefined;
  const started = useRef(false);
  useEffect(() => {
    if (!want) return;
    const strip = () => { const p = new URLSearchParams(params); p.delete('as'); setParams(p, { replace: true }); };
    if (me?.email === want.email) return strip();
    if (loading || started.current) return;
    started.current = true;
    signInAs(want.email).then((err) => { if (err) strip(); });
  }, [want?.email, me?.email, loading]); // eslint-disable-line
  if (want) return <div className="grid h-full place-items-center"><Spinner /></div>;
  if (loading && !session) return <div className="grid h-full place-items-center"><Spinner /></div>;
  if (!session || !me) return <><Login /><Toasts /></>;
  return (
    <Layout>
      <Routes>
        <Route path="/" element={<Today />} />
        <Route path="/reviews" element={<Reviews />} />
        <Route path="/accounts" element={<Accounts />} />
        <Route path="/accounts/:id" element={<Account />} />
        <Route path="/pipeline" element={<Pipeline />} />
        <Route path="/loops" element={<Loops />} />
        <Route path="/loops/:loop" element={<Loop />} />
        <Route path="/runs" element={<Runs />} />
        <Route path="/runs/:id" element={<Run />} />
        <Route path="/experiments" element={<Experiments />} />
        <Route path="/insights" element={<Insights />} />
        <Route path="/policies" element={<Policies />} />
        <Route path="/audit" element={<Audit />} />
        <Route path="/slack" element={<Slack />} />
        <Route path="/about" element={<About />} />
        <Route path="*" element={<Navigate to="/" />} />
      </Routes>
      <Toasts />
    </Layout>
  );
}
