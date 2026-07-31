import { useQuery } from "@tanstack/react-query";
import { useEffect } from "react";
import { Navigate, NavLink, Outlet, useLocation } from "react-router-dom";
import { api, getToken } from "../../shared/api/client";
import { useI18n } from "../../shared/i18n/runtime";
import { Icon, type IconName } from "../../shared/ui/Icon";
import { OfflineBanner } from "../../shared/ui/OfflineBanner";
import { SkeletonBlock } from "../../shared/ui/Skeleton";
import { currentAppPath } from "../navigation";

type NavItem = {
  to: string;
  end?: boolean;
  icon: IconName;
  label: "nav.home" | "nav.create" | "nav.history" | "nav.plans" | "nav.profile";
  create?: boolean;
};

const navItems: NavItem[] = [
  { to: "/", end: true, icon: "home", label: "nav.home" },
  { to: "/history", icon: "history", label: "nav.history" },
  { to: "/create", icon: "create", label: "nav.create", create: true },
  { to: "/plans", icon: "star", label: "nav.plans" },
  { to: "/profile", icon: "profile", label: "nav.profile" },
];

export function AppShell() {
  const { tx, setLanguage } = useI18n();
  const location = useLocation();
  const isCreateRoute = location.pathname === "/create" || location.pathname === "/video";
  const isWideRoute =
    location.pathname === "/" ||
    location.pathname === "/create" ||
    location.pathname === "/video";
  const topRailTitle =
    location.pathname === "/history"
      ? tx("nav.history")
      : location.pathname === "/plans"
        ? tx("nav.plans")
        : location.pathname === "/profile"
          ? tx("nav.profile")
          : null;
  const meQuery = useQuery({
    queryKey: ["me"],
    queryFn: () => api.getMe(),
    enabled: Boolean(getToken()),
  });
  const profileLanguage = meQuery.data?.language;

  useEffect(() => {
    if (profileLanguage) setLanguage(profileLanguage);
  }, [profileLanguage, setLanguage]);

  if (!getToken()) {
    return (
      <Navigate
        to="/boot"
        replace
        state={{ returnTo: currentAppPath(location) }}
      />
    );
  }

  return (
    <div className={`app-shell${isWideRoute ? " is-wide" : ""}`}>
      <OfflineBanner />
      {topRailTitle ? (
        <header className="app-top-rail">
          <NavLink to="/" className="top-rail-brand" aria-label={tx("nav.home")}>
            <span className="brand-mark" aria-hidden>K</span>
            <span>KELBET</span>
          </NavLink>
          <span className="top-rail-context">{topRailTitle}</span>
          <NavLink to="/plans" className="top-rail-balance" aria-label={tx("home.available")}>
            <span aria-hidden>◆</span>
            <strong>{meQuery.data?.available ?? "—"}</strong>
          </NavLink>
        </header>
      ) : null}
      <main className="app-main">
        {meQuery.isLoading ? <SkeletonBlock rows={4} /> : <Outlet />}
      </main>
      <nav className="bottom-nav" aria-label="Main">
        {navItems.map((item) => {
          const forcedActive = item.create && isCreateRoute;
          return (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              className={({ isActive }) =>
                `nav-link${item.create ? " create-nav" : ""}${isActive || forcedActive ? " active" : ""}`
              }
              aria-current={forcedActive ? "page" : undefined}
            >
              <span className="nav-icon">
                <Icon name={item.icon} />
              </span>
              <span>{tx(item.label)}</span>
            </NavLink>
          );
        })}
      </nav>
    </div>
  );
}
