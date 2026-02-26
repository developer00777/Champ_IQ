import { lazy, useEffect, Suspense } from 'react';
import { Routes, Route, Navigate } from 'react-router-dom';
import { useAuthStore } from '@/stores/authStore';
import { ToastProvider } from '@/components/ui/toast';
import { AppShell } from '@/components/layout/AppShell';
import { ProtectedRoute } from '@/components/layout/ProtectedRoute';
import { Loader2 } from 'lucide-react';

// Code-split page bundles — each page loads only when navigated to
const Login = lazy(() => import('@/pages/Login'));
const Dashboard = lazy(() => import('@/pages/Dashboard'));
const AddProspect = lazy(() => import('@/pages/AddProspect'));
const ProspectDetail = lazy(() => import('@/pages/ProspectDetail'));
const Settings = lazy(() => import('@/pages/Settings'));

function App() {
  const { initialize } = useAuthStore();

  useEffect(() => {
    initialize();
  }, [initialize]);

  return (
    <ToastProvider>
      <Routes>
        {/* Public */}
        <Route
          path="/login"
          element={
            <Suspense fallback={<div className="min-h-screen flex items-center justify-center"><Loader2 className="h-6 w-6 animate-spin text-muted-foreground" /></div>}>
              <Login />
            </Suspense>
          }
        />

        {/* Protected — AppShell provides sidebar + mobile nav + Suspense + ErrorBoundary */}
        <Route
          element={
            <ProtectedRoute>
              <AppShell />
            </ProtectedRoute>
          }
        >
          <Route path="/" element={<Dashboard />} />
          <Route path="/add-prospect" element={<AddProspect />} />
          <Route path="/prospects/:id" element={<ProspectDetail />} />
          <Route path="/settings" element={<Settings />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </ToastProvider>
  );
}

export default App;
