import { lazy, Suspense, type ReactNode } from "react";
import { Route, Routes } from "react-router-dom";
import { useI18n } from "../shared/i18n/runtime";
import { AppShell } from "./layout/AppShell";

const BootPage = lazy(async () => ({
  default: (await import("../pages/BootPage")).BootPage,
}));
const CreatePage = lazy(async () => ({
  default: (await import("../pages/CreatePage")).CreatePage,
}));
const GenerationPage = lazy(async () => ({
  default: (await import("../pages/GenerationPage")).GenerationPage,
}));
const HistoryPage = lazy(async () => ({
  default: (await import("../pages/HistoryPage")).HistoryPage,
}));
const HomePage = lazy(async () => ({
  default: (await import("../pages/HomePage")).HomePage,
}));
const PlansPage = lazy(async () => ({
  default: (await import("../pages/PlansPage")).PlansPage,
}));
const ProfilePage = lazy(async () => ({
  default: (await import("../pages/ProfilePage")).ProfilePage,
}));
const VideoPage = lazy(async () => ({
  default: (await import("../pages/VideoPage")).VideoPage,
}));

function RouteLoader() {
  const { tx } = useI18n();
  return (
    <div className="route-loader" role="status" aria-label={tx("common.loading")}>
      <span aria-hidden>K</span>
      <i />
    </div>
  );
}

function LazyPage({ children }: { children: ReactNode }) {
  return <Suspense fallback={<RouteLoader />}>{children}</Suspense>;
}

export function AppRouter() {
  return (
    <Routes>
      <Route
        path="/boot"
        element={
          <LazyPage>
            <BootPage />
          </LazyPage>
        }
      />
      <Route element={<AppShell />}>
        <Route
          index
          element={
            <LazyPage>
              <HomePage />
            </LazyPage>
          }
        />
        <Route
          path="create"
          element={
            <LazyPage>
              <CreatePage />
            </LazyPage>
          }
        />
        <Route
          path="video"
          element={
            <LazyPage>
              <VideoPage />
            </LazyPage>
          }
        />
        <Route
          path="generations/:id"
          element={
            <LazyPage>
              <GenerationPage />
            </LazyPage>
          }
        />
        <Route
          path="history"
          element={
            <LazyPage>
              <HistoryPage />
            </LazyPage>
          }
        />
        <Route
          path="plans"
          element={
            <LazyPage>
              <PlansPage />
            </LazyPage>
          }
        />
        <Route
          path="profile"
          element={
            <LazyPage>
              <ProfilePage />
            </LazyPage>
          }
        />
      </Route>
    </Routes>
  );
}
