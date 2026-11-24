import { lazy, Suspense, useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Activity,
  ArrowUpRight,
  BarChart3,
  Binary,
  ChartNoAxesCombined,
  ClipboardList,
  GitCompareArrows,
  LayoutGrid,
  Menu,
  Moon,
  Plus,
  Search,
  ShieldCheck,
  Sun,
  X,
} from "lucide-react";
import {
  Link,
  NavLink,
  Route,
  Routes,
  useLocation,
  useNavigate,
} from "react-router-dom";
import { api, type System } from "./data";
import { Loading } from "./ui";
import { DashboardPage, History, Research, SystemPage } from "./Workspace";
const ReportPage = lazy(() => import("./Report"));
const FactReader = lazy(() =>
  import("./Evidence").then((module) => ({ default: module.FactReader })),
);
const SourceReader = lazy(() =>
  import("./Evidence").then((module) => ({ default: module.SourceReader })),
);
const Compare = lazy(() => import("./Compare"));
const Valuation = lazy(() => import("./Valuation"));
const links = [
  [
    "Nghiên cứu",
    [
      { to: "/", title: "Tổng quan", icon: LayoutGrid },
      {
        to: "/nghien-cuu",
        title: "Phân tích doanh nghiệp",
        icon: ChartNoAxesCombined,
      },
      { to: "/so-sanh", title: "So sánh doanh nghiệp", icon: GitCompareArrows },
      { to: "/lich-su", title: "Lịch sử báo cáo", icon: ClipboardList },
    ],
  ],
  [
    "Công cụ",
    [
      { to: "/bang-chung", title: "Trung tâm bằng chứng", icon: ShieldCheck },
      { to: "/dinh-gia", title: "Định giá DCF", icon: Binary },
      { to: "/he-thong", title: "Trạng thái hệ thống", icon: Activity },
    ],
  ],
] as const;

export default function App() {
  const [theme, setTheme] = useState(() =>
    localStorage.getItem("finsight-theme") === "light" ? "light" : "dark",
  );
  const [expanded, setExpanded] = useState(() => window.innerWidth > 900);
  const [search, setSearch] = useState("");
  const navigate = useNavigate();
  const route = useLocation();
  const system = useQuery({
    queryKey: ["system"],
    queryFn: ({ signal }) => api<System>("/system/status", { signal }),
  });
  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    localStorage.setItem("finsight-theme", theme);
  }, [theme]);
  useEffect(() => {
    window.scrollTo(0, 0);
  }, [route.pathname]);
  const current =
    links
      .flatMap((group) => [...group[1]])
      .find((item) => item.to === route.pathname)?.title ??
    "Hồ sơ doanh nghiệp";
  return (
    <div className={"app " + (expanded ? "nav-open" : "")}>
      {expanded && (
        <button
          className="nav-scrim"
          aria-label="Đóng điều hướng"
          onClick={() => setExpanded(false)}
        />
      )}
      <aside
        className="sidebar"
        aria-label="Điều hướng chính"
        inert={!expanded}
      >
        <Link to="/" className="brand">
          <span className="brand-icon">
            <BarChart3 size={22} />
          </span>
          <span>
            FinSight<small>Intelligence</small>
          </span>
        </Link>
        <div className="nav-groups">
          {links.map(([name, items]) => (
            <div className="nav-group" key={name}>
              <span>{name}</span>
              {items.map(({ to, title, icon: Icon }) => (
                <NavLink
                  key={to}
                  end={to === "/"}
                  to={to}
                  onClick={() => {
                    if (window.innerWidth <= 900) setExpanded(false);
                  }}
                >
                  <Icon size={18} />
                  {title}
                </NavLink>
              ))}
            </div>
          ))}
        </div>
        <Link to="/he-thong" className="sidebar-status">
          <i
            className={
              system.data?.mysql === "ready" ? "live-dot" : "offline-dot"
            }
          />
          <span>
            {system.data?.mysql === "ready"
              ? "MySQL đã kết nối"
              : system.isPending
                ? "Đang kiểm tra hệ thống"
                : "Kiểm tra hệ thống"}
          </span>
          <ArrowUpRight size={14} />
        </Link>
      </aside>
      <div className="main-area">
        <header className="topbar">
          <div className="crumb">
            <button
              className="icon-button"
              aria-label={expanded ? "Thu gọn điều hướng" : "Mở điều hướng"}
              aria-expanded={expanded}
              onClick={() => setExpanded(!expanded)}
            >
              {expanded ? <X size={19} /> : <Menu size={19} />}
            </button>
            <span>Không gian nghiên cứu</span>
            <b>/</b>
            <strong>{current}</strong>
          </div>
          <div className="top-actions">
            <form
              className="quick-search"
              onSubmit={(event) => {
                event.preventDefault();
                if (search.trim()) {
                  navigate(
                    "/nghien-cuu?q=" + encodeURIComponent(search.trim()),
                  );
                  setSearch("");
                }
              }}
            >
              <Search size={16} />
              <input
                aria-label="Tìm nhanh doanh nghiệp"
                placeholder="Tìm doanh nghiệp"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                maxLength={100}
              />
            </form>
            <button
              className="icon-button"
              aria-label={
                theme === "dark" ? "Bật giao diện sáng" : "Bật giao diện tối"
              }
              onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
            >
              {theme === "dark" ? <Sun size={18} /> : <Moon size={18} />}
            </button>
            <Link className="button primary new-button" to="/nghien-cuu">
              <Plus size={16} />
              <span>Phân tích mới</span>
            </Link>
          </div>
        </header>
        <main className="content" id="main-content">
          <Suspense fallback={<Loading />}>
            <Routes>
              <Route path="/" element={<DashboardPage />} />
              <Route path="/nghien-cuu" element={<Research />} />
              <Route path="/lich-su" element={<History />} />
              <Route path="/bao-cao/:id" element={<ReportPage />} />
              <Route path="/nguon/:reportId" element={<SourceReader />} />
              <Route path="/so-lieu/:reportId" element={<FactReader />} />
              <Route path="/bang-chung" element={<History evidence />} />
              <Route path="/so-sanh" element={<Compare />} />
              <Route path="/dinh-gia" element={<Valuation />} />
              <Route path="/he-thong" element={<SystemPage />} />
              <Route
                path="*"
                element={
                  <>
                    <h1>Không tìm thấy trang</h1>
                    <Link to="/">Về Tổng quan</Link>
                  </>
                }
              />
            </Routes>
          </Suspense>
        </main>
      </div>
    </div>
  );
}
