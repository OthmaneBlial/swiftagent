import { lazy, Suspense, type ReactNode } from 'react';
import { BrowserRouter, Routes, Route } from 'react-router';
import Layout from './components/layout/Layout';

const Home = lazy(() => import('./pages/Home'));
const Execution = lazy(() => import('./pages/Execution'));
const History = lazy(() => import('./pages/History'));
const Settings = lazy(() => import('./pages/Settings'));
const Files = lazy(() => import('./pages/Files'));

function Page({ children }: { children: ReactNode }) {
    return (
        <Suspense fallback={<div className="p-6 text-sm text-muted-foreground">Loading view...</div>}>
            {children}
        </Suspense>
    );
}

export default function Router() {
    return (
        <BrowserRouter>
            <Routes>
                <Route element={<Layout />}>
                    <Route path="/" element={<Page><Home /></Page>} />
                    <Route path="/task/:taskId" element={<Page><Execution /></Page>} />
                    <Route path="/history" element={<Page><History /></Page>} />
                    <Route path="/files" element={<Page><Files /></Page>} />
                    <Route path="/settings" element={<Page><Settings /></Page>} />
                </Route>
            </Routes>
        </BrowserRouter>
    );
}
