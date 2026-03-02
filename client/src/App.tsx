import { useEffect } from 'react';
import Router from './router';
import { ws } from './lib/swiftagent';

export default function App() {
  useEffect(() => {
    // Connect WebSocket on mount
    ws.connect();
    return () => ws.disconnect();
  }, []);

  return <Router />;
}
