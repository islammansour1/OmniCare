import { useEffect, useState } from 'react';
import { ChatShell } from './components/Chat/ChatShell';
import { getSession } from './lib/api';

export default function App() {
  const [userId, setUserId] = useState(() => localStorage.getItem('omnicare-user-id') ?? '');
  const [error, setError] = useState('');
  useEffect(() => {
    getSession().then(s => {
      setUserId(s.user_id);
      localStorage.setItem('omnicare-user-id', s.user_id);
    }).catch(() => setError('Unable to start your session. Reload to retry.'));
  }, []);
  return <div className="h-dvh w-full bg-slate-50 font-sans text-slate-900 antialiased">
    {userId ? <ChatShell userId={userId} /> : <p role="status" className="p-8">{error || 'Opening your session…'}</p>}
  </div>;
}
