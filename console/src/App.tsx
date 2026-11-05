import { Navigate, Route, Routes } from 'react-router-dom';
import { useSession } from './lib/session';
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
  const { session, me, loading } = useSession();
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
