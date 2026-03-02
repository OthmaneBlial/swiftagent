import { BrowserRouter, Routes, Route } from 'react-router';
import Home from './pages/Home';
import Execution from './pages/Execution';
import History from './pages/History';
import Layout from './components/layout/Layout';

export default function Router() {
    return (
        <BrowserRouter>
            <Routes>
                <Route element={<Layout />}>
                    <Route path="/" element={<Home />} />
                    <Route path="/task/:taskId" element={<Execution />} />
                    <Route path="/history" element={<History />} />
                </Route>
            </Routes>
        </BrowserRouter>
    );
}
