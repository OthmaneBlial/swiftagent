import { BrowserRouter, Routes, Route } from 'react-router';
import Home from './pages/Home';
import Execution from './pages/Execution';
import History from './pages/History';
import Settings from './pages/Settings';
import Files from './pages/Files';
import Layout from './components/layout/Layout';

export default function Router() {
    return (
        <BrowserRouter>
            <Routes>
                <Route element={<Layout />}>
                    <Route path="/" element={<Home />} />
                    <Route path="/task/:taskId" element={<Execution />} />
                    <Route path="/history" element={<History />} />
                    <Route path="/files" element={<Files />} />
                    <Route path="/settings" element={<Settings />} />
                </Route>
            </Routes>
        </BrowserRouter>
    );
}
