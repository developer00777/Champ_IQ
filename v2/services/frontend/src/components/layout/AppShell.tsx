import { Suspense } from 'react';
import { Outlet } from 'react-router-dom';
import { Sidebar } from './Sidebar';
import { MobileNav } from './MobileNav';
import { ErrorBoundary } from '@/components/ErrorBoundary';
import { Loader2 } from 'lucide-react';

function PageSpinner() {
  return (
    <div className="flex items-center justify-center min-h-[200px]">
      <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
    </div>
  );
}

export function AppShell() {
  return (
    <div className="flex h-screen bg-background">
      {/* Desktop sidebar */}
      <Sidebar className="hidden md:flex w-64" />

      {/* Right panel: mobile nav header + scrollable main */}
      <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
        {/* Mobile top bar */}
        <header className="md:hidden flex items-center h-14 px-4 border-b bg-card shrink-0">
          <MobileNav />
          <span className="ml-3 font-semibold text-sm">ChampIQ V2</span>
        </header>

        {/* Main content area */}
        <main className="flex-1 overflow-auto">
          <div className="p-6 max-w-7xl mx-auto">
            <ErrorBoundary>
              <Suspense fallback={<PageSpinner />}>
                <Outlet />
              </Suspense>
            </ErrorBoundary>
          </div>
        </main>
      </div>
    </div>
  );
}
