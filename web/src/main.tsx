import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import { Toaster } from "sonner";
import { Layout } from "./components/Layout";
import "./index.css";
import { useAppState } from "./lib/hooks";
import { TaskProvider } from "./lib/tasks";
import { useTheme } from "./lib/theme";
import Compose from "./pages/Compose";
import Dashboard from "./pages/Dashboard";
import Discover from "./pages/Discover";
import HistoryPage from "./pages/History";
import Pipeline from "./pages/Pipeline";
import SendPage from "./pages/Send";
import SettingsPage from "./pages/Settings";

const queryClient = new QueryClient({ defaultOptions: { queries: { refetchOnWindowFocus: true, staleTime: 2000, retry: 1 } } });

function App() {
  const { data: state } = useAppState();
  const theme = useTheme();
  return (
    <TaskProvider initial={state?.tasks ?? []}>
      <Routes>
        <Route element={<Layout state={state} theme={theme} />}>
          <Route index element={<Dashboard />} />
          <Route path="discover" element={<Discover />} />
          <Route path="pipeline" element={<Pipeline />} />
          <Route path="compose" element={<Compose />} />
          <Route path="send" element={<SendPage />} />
          <Route path="history" element={<HistoryPage />} />
          <Route path="settings" element={<SettingsPage />} />
        </Route>
      </Routes>
      <Toaster position="bottom-right" richColors closeButton theme={theme.resolved} />
    </TaskProvider>
  );
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </QueryClientProvider>
  </StrictMode>,
);
