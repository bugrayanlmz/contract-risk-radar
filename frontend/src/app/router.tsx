import { QueryClient, useMutation, useQuery } from "@tanstack/react-query";
import {
  createBrowserRouter,
  Link,
  Navigate,
  Outlet,
  useLocation,
  useNavigate,
} from "react-router-dom";
import { FileText, LogOut, Plus, ArrowUpRight } from "lucide-react";
import { logout } from "../api/generated/sdk.gen";
import { meQuery, errorMessage } from "../api/queries";
import { ErrorBox, Footer, Loading, Logo } from "../components/shared";
import { Landing } from "../pages/Landing";
import { Auth } from "../pages/Auth";
import { Dashboard } from "../pages/Dashboard";
import { Upload } from "../pages/Upload";
import { DocumentPage } from "../pages/Document";
import { useUploadStore } from "../stores/upload";

export const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: true } },
});

function AppLayout() {
  const user = useQuery(meQuery);
  const navigate = useNavigate();
  const location = useLocation();
  const signOut = useMutation({
    mutationFn: async () => logout(),
    onSuccess: () => {
      queryClient.clear();
      useUploadStore.getState().reset();
      navigate("/login");
    },
  });
  if (user.isPending)
    return (
      <div className="shell">
        <Logo />
        <Loading />
        <Footer />
      </div>
    );
  if (!user.data)
    return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  return (
    <div className="shell">
      <header className="app-header">
        <Logo />
        <nav>
          <Link
            className={location.pathname === "/app" ? "active" : ""}
            to="/app"
          >
            <FileText size={16} /> My contracts
          </Link>
          <Link className="button small" to="/app/upload">
            <Plus size={16} /> New analysis
          </Link>
          <button
            className="icon-button"
            aria-label="Sign out"
            title={user.data.email}
            onClick={() => signOut.mutate()}
            disabled={signOut.isPending}
          >
            <LogOut size={18} />
          </button>
        </nav>
      </header>
      {signOut.isError && <ErrorBox message={errorMessage(signOut.error)} />}
      <main className="app-main">
        <Outlet />
      </main>
      <Footer />
    </div>
  );
}

function NotFound() {
  return (
    <div className="shell">
      <header className="public-header">
        <Logo />
      </header>
      <main className="auth-main">
        <h1>Page not found</h1>
        <Link className="button" to="/">
          Back to home <ArrowUpRight size={16} />
        </Link>
      </main>
      <Footer />
    </div>
  );
}

export const router = createBrowserRouter([
  { path: "/", element: <Landing /> },
  { path: "/login", element: <Auth /> },
  { path: "/register", element: <Auth register /> },
  {
    path: "/app",
    element: <AppLayout />,
    children: [
      { index: true, element: <Dashboard /> },
      { path: "upload", element: <Upload /> },
      { path: "documents/:id", element: <DocumentPage /> },
    ],
  },
  { path: "*", element: <NotFound /> },
]);
