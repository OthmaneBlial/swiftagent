import { useEffect } from 'react';
import Router from './router';
import { api, ws } from './lib/swiftagent';
import { applyTheme } from './lib/theme';
import ToastViewport from './components/ui/ToastViewport';
import { toast } from './lib/toast';

let wsConsumers = 0;

export default function App() {
    useEffect(() => {
        wsConsumers += 1;
        ws.connect();

        return () => {
            wsConsumers -= 1;
            if (wsConsumers <= 0) {
                ws.disconnect();
            }
        };
    }, []);

    useEffect(() => {
        let cancelled = false;

        api.getSettings()
            .then((settings) => {
                if (!cancelled) {
                    applyTheme(settings.theme);
                }
            })
            .catch((error: Error) => {
                if (!cancelled) {
                    toast.error('Failed to load settings', error.message);
                }
            });

        return () => {
            cancelled = true;
        };
    }, []);

    return (
        <>
            <Router />
            <ToastViewport />
        </>
    );
}
