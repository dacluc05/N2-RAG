import { useEffect, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import {
  ArrowRight,
  ArrowUpRight,
  Building2,
  ChartNoAxesCombined,
  Clock3,
  Database,
  FileCheck2,
  FileText,
  Search,
  ShieldCheck,
} from "lucide-react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import {
  api,
  displayDate,
  displayTime,
  number,
  post,
  readable,
  runStates,
  terminal,
  today,
  type Company,
  type Dashboard,
  type Progress,
  type ResearchRequest,
  type Run,
  type System,
} from "./data";
import {
  Badge,
  ConnectionList,
  Heading,
  Loading,
  OpenReport,
  Section,
  State,
  Stat,
} from "./ui";

export const useHistory = () =>
  useQuery({
    queryKey: ["reports"],
    queryFn: ({ signal }) => api<Run[]>("/reports?limit=100", { signal }),
  });
const useSystem = () =>
  useQuery({
    queryKey: ["system"],
    queryFn: ({ signal }) => api<System>("/system/status", { signal }),
  });

export function DashboardPage() {
  const navigate = useNavigate();
  const [search, setSearch] = useState("");
  const history = useHistory(),
    system = useSystem();
  const totals = useQuery({
    queryKey: ["dashboard"],
    queryFn: ({ signal }) => api<Dashboard>("/dashboard", { signal }),
  });
  const score = totals.data?.latest_scores;
  const latest = history.data?.find((run) => readable(run.status));
  return (
    <>
      <Heading
        title="Tổng quan nghiên cứu"
        detail="Theo dõi báo cáo, chất lượng bằng chứng và hoạt động phân tích doanh nghiệp."
      />
      <section className="hero">
        <div className="hero-inner">
          <div className="hero-label">
            <ChartNoAxesCombined size={18} /> Nghiên cứu doanh nghiệp
          </div>
          <h2>FinSight Intelligence</h2>
          <p>
            Khám phá tình hình tài chính, triển vọng và rủi ro của doanh nghiệp.
            Đối chiếu từng nhận định với nguồn đã lưu.
          </p>
          <form
            className="hero-search"
            onSubmit={(e) => {
              e.preventDefault();
              if (search.trim())
                navigate("/nghien-cuu?q=" + encodeURIComponent(search.trim()));
            }}
          >
            <Search size={20} />
            <input
              aria-label="Tên doanh nghiệp hoặc mã chứng khoán"
              placeholder="Tên doanh nghiệp hoặc mã chứng khoán"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              maxLength={100}
              required
            />
            <button className="button primary">
              Tra cứu <ArrowRight size={16} />
            </button>
          </form>
          <div className="hero-links">
            <Link to="/nghien-cuu?mode=deep">
              Nghiên cứu chuyên sâu <ArrowUpRight size={14} />
            </Link>
            {latest && (
              <Link to={"/bao-cao/" + latest.id}>
                Mở báo cáo gần nhất <ArrowUpRight size={14} />
              </Link>
            )}
          </div>
        </div>
      </section>
      {totals.isPending ? (
        <Loading />
      ) : totals.isError ? (
        <State
          error
          title="Chưa tải được thống kê"
          retry={() => void totals.refetch()}
        >
          {totals.error.message}
        </State>
      ) : (
        <div className="stats four">
          <Stat
            label="Doanh nghiệp đã nghiên cứu"
            value={number(totals.data.companies)}
            icon={<Building2 size={18} />}
          />
          <Stat
            label="Báo cáo đã lưu"
            value={number(totals.data.reports)}
            detail={number(totals.data.claim_count) + " nhận định đã lưu"}
            icon={<FileText size={18} />}
          />
          <Stat
            label="Nhận định có bằng chứng"
            value={score ? score.supported + " / " + score.total_claims : "—"}
            detail="Phiên gần nhất"
            icon={<ShieldCheck size={18} />}
          />
          <Stat
            label="Bằng chứng đã lưu"
            value={number(totals.data.evidence_count)}
            detail={
              score
                ? number(score.primary_evidence) +
                  " nguồn sơ cấp ở phiên gần nhất"
                : undefined
            }
            icon={<FileCheck2 size={18} />}
          />
        </div>
      )}
      <div className="dashboard-grid">
        <section className="panel">
          <Section
            title="Nghiên cứu gần đây"
            detail="Các phiên đã lưu theo thời điểm tạo."
            action={
              <Link className="button subtle" to="/lich-su">
                Xem lịch sử <ArrowRight size={15} />
              </Link>
            }
          />
          {history.isPending ? (
            <Loading />
          ) : history.isError ? (
            <State
              error
              title="Chưa tải được lịch sử"
              retry={() => void history.refetch()}
            >
              {history.error.message}
            </State>
          ) : history.data.length ? (
            <RunTable rows={history.data.slice(0, 6)} />
          ) : (
            <State title="Chưa có báo cáo">Tạo một phân tích để bắt đầu.</State>
          )}
        </section>
        <section className="panel">
          <Section title="Nguồn dữ liệu" action={<Database size={19} />} />
          <ConnectionList state={system.data} />
          {score?.latest_publication && (
            <p className="muted source-date">
              <Clock3 size={15} /> Nguồn mới nhất ·{" "}
              {displayDate(score.latest_publication)}
            </p>
          )}
        </section>
      </div>
    </>
  );
}

function RunTable({ rows, evidence }: { rows: Run[]; evidence?: boolean }) {
  return (
    <div className="table-scroll">
      <table>
        <thead>
          <tr>
            <th>Mã</th>
            <th>Mốc dữ liệu</th>
            <th>Trạng thái</th>
            <th>Thời điểm tạo</th>
            <th>
              <span className="sr-only">Thao tác</span>
            </th>
          </tr>
        </thead>
        <tbody>
          {rows.map((run) => (
            <tr key={run.id}>
              <td>
                <strong className="ticker">{run.ticker}</strong>
                {run.company_name && (
                  <small className="table-note">{run.company_name}</small>
                )}
                {run.industry && (
                  <small className="table-note">{run.industry}</small>
                )}
              </td>
              <td>{displayDate(run.as_of)}</td>
              <td>
                <Badge status={run.status} />
              </td>
              <td className="muted">{displayTime(run.created_at)}</td>
              <td>
                {readable(run.status) ? (
                  evidence ? (
                    <Link
                      className="button subtle"
                      to={"/bao-cao/" + run.id + "?tab=evidence"}
                    >
                      Xem bằng chứng <ArrowUpRight size={15} />
                    </Link>
                  ) : (
                    <OpenReport id={run.id} />
                  )
                ) : (
                  <Link
                    className="button subtle"
                    to={"/nghien-cuu?run=" + run.id}
                  >
                    Xem tiến trình <ArrowUpRight size={15} />
                  </Link>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function History({ evidence = false }: { evidence?: boolean }) {
  const [ticker, setTicker] = useState(""),
    [term, setTerm] = useState(""),
    [status, setStatus] = useState(""),
    [after, setAfter] = useState(""),
    [order, setOrder] = useState("desc"),
    [page, setPage] = useState(0);
  useEffect(() => {
    const timer = window.setTimeout(() => setTerm(ticker.trim()), 250);
    return () => clearTimeout(timer);
  }, [ticker]);
  const filters = new URLSearchParams({
    limit: "13",
    offset: String(page * 12),
  });
  if (term) filters.set("q", term);
  if (after) filters.set("after", after);
  if (order === "asc") filters.set("oldest", "true");
  if (status) filters.append("status", status);
  else if (evidence)
    for (const state of ["completed", "partial"])
      filters.append("status", state);
  const filterString = filters.toString();
  const history = useQuery({
    queryKey: ["history", filterString],
    queryFn: ({ signal }) => api<Run[]>("/reports?" + filterString, { signal }),
  });
  const rows = history.data ?? [];
  return (
    <>
      <Heading
        title={evidence ? "Trung tâm bằng chứng" : "Lịch sử báo cáo"}
        detail={
          evidence
            ? "Chọn báo cáo để tra cứu nhận định, bằng chứng trái chiều và tài liệu gốc."
            : "Xem lại các phiên nghiên cứu theo mốc dữ liệu và thời điểm phân tích."
        }
      />
      <section className="panel">
        <div className="filter-row">
          <label>
            Tên doanh nghiệp hoặc mã
            <input
              value={ticker}
              maxLength={100}
              onChange={(e) => {
                setTicker(e.target.value);
                setPage(0);
              }}
              placeholder="Apple, AAPL, NVDA…"
            />
          </label>
          <label>
            Trạng thái
            <select
              value={status}
              onChange={(e) => {
                setStatus(e.target.value);
                setPage(0);
              }}
            >
              <option value="">Tất cả</option>
              {(evidence
                ? ["completed", "partial"]
                : Object.keys(runStates)
              ).map((s) => (
                <option key={s} value={s}>
                  {runStates[s]}
                </option>
              ))}
            </select>
          </label>
          <label>
            Mốc dữ liệu từ ngày
            <input
              type="date"
              value={after}
              onChange={(e) => {
                setAfter(e.target.value);
                setPage(0);
              }}
              max={today()}
            />
          </label>
          <label>
            Sắp xếp
            <select
              value={order}
              onChange={(e) => {
                setOrder(e.target.value);
                setPage(0);
              }}
            >
              <option value="desc">Mới nhất</option>
              <option value="asc">Cũ nhất</option>
            </select>
          </label>
        </div>
        {history.isPending ? (
          <Loading />
        ) : history.isError ? (
          <State
            error
            title="Chưa tải được báo cáo"
            retry={() => void history.refetch()}
          >
            {history.error.message}
          </State>
        ) : rows.length ? (
          <>
            <RunTable rows={rows.slice(0, 12)} evidence={evidence} />
            <div className="pagination">
              <span>Trang {page + 1}</span>
              <button
                className="button"
                disabled={!page}
                onClick={() => setPage(page - 1)}
              >
                Trang trước
              </button>
              <button
                className="button"
                disabled={rows.length <= 12}
                onClick={() => setPage(page + 1)}
              >
                Trang sau
              </button>
            </div>
          </>
        ) : (
          <State title="Chưa có phiên phù hợp">Thử điều chỉnh bộ lọc.</State>
        )}
      </section>
    </>
  );
}

export function Research() {
  const [params, setParams] = useSearchParams();
  const [input, setInput] = useState(params.get("q") ?? "");
  const [lookup, setLookup] = useState(input);
  const [ticker, setTicker] = useState("");
  const [mode, setMode] = useState(
    params.get("mode") === "deep" ? "deep" : "standard",
  );
  const [asOf, setAsOf] = useState(today),
    [years, setYears] = useState(10),
    [peers, setPeers] = useState(""),
    [budget, setBudget] = useState("");
  const [referencePrice, setReferencePrice] = useState("");
  const [priceDate, setPriceDate] = useState("");
  const [priceUrl, setPriceUrl] = useState("");
  const system = useSystem();
  const config = useQuery({
    queryKey: ["ui-config"],
    queryFn: ({ signal }) =>
      api<{ search_budget: number }>("/ui/config", { signal }),
  });
  useEffect(() => {
    const value = params.get("q");
    if (value) {
      setInput(value);
      setLookup(value);
      setTicker("");
    }
    if (params.get("mode") === "deep") setMode("deep");
  }, [params]);
  const search = useQuery({
    queryKey: ["company-search", lookup],
    queryFn: ({ signal }) =>
      api<Company[]>("/companies/search?q=" + encodeURIComponent(lookup), {
        signal,
      }),
    enabled: lookup.trim().length > 0,
  });
  const start = useMutation({
    mutationFn: (data: ResearchRequest) =>
      post<{ id: string; created: boolean }>("/analysis", data),
    onSuccess: (data) => setParams({ run: data.id }),
  });
  const runId = params.get("run");
  return (
    <>
      <Heading
        title="Phân tích doanh nghiệp"
        detail="Chọn doanh nghiệp, kỳ tài chính và phạm vi nghiên cứu."
      />
      {runId && <ProgressPanel id={runId} />}
      <div className="dashboard-grid">
        <section className="panel">
          <Section title="Thiết lập phiên nghiên cứu" />
          <form
            className="search-inline"
            onSubmit={(e) => {
              e.preventDefault();
              setLookup(input.trim());
            }}
          >
            <label className="grow">
              Tên doanh nghiệp hoặc mã chứng khoán
              <input
                value={input}
                onChange={(e) => setInput(e.target.value)}
                maxLength={100}
                placeholder="Apple, AAPL, NVDA…"
              />
            </label>
            <button className="button">
              <Search size={16} />
              Tra cứu SEC
            </button>
          </form>
          {search.isFetching && (
            <p role="status" className="muted">
              Đang tra cứu doanh nghiệp…
            </p>
          )}
          {search.isError && (
            <p role="alert" className="error-text">
              {search.error.message}
            </p>
          )}
          {search.data &&
            (search.data.length ? (
              <div className="matches">
                {search.data.slice(0, 10).map((company) => (
                  <button
                    key={company.ticker}
                    className={
                      "button " + (ticker === company.ticker ? "selected" : "")
                    }
                    onClick={() => setTicker(company.ticker)}
                  >
                    <strong>{company.ticker}</strong>
                    {company.name}
                  </button>
                ))}
              </div>
            ) : (
              <p className="muted">Không tìm thấy doanh nghiệp phù hợp.</p>
            ))}
          <form
            className="research-form"
            onSubmit={(e) => {
              e.preventDefault();
              if (start.isPending) return;
              start.mutate({
                ticker: ticker.trim(),
                as_of: asOf,
                years,
                mode,
                peers: peers
                  .split(",")
                  .map((item) => item.trim())
                  .filter(Boolean),
                ...(budget !== "" ? { search_budget: Number(budget) } : {}),
                ...(referencePrice ? { market_reference: {
                  close: Number(referencePrice), date: priceDate, currency: "USD" as const, url: priceUrl,
                } } : {}),
              });
            }}
          >
            <div className="filter-row">
              <label>
                Mã chứng khoán
                <input
                  value={ticker}
                  onChange={(e) => setTicker(e.target.value.toUpperCase())}
                  required
                  maxLength={12}
                />
              </label>
              <label>
                Mốc chốt dữ liệu (UTC)
                <input
                  type="date"
                  value={asOf}
                  min="1995-01-01"
                  max={today()}
                  required
                  onChange={(e) => setAsOf(e.target.value)}
                />
              </label>
              <label>
                Số năm tài chính
                <input
                  type="number"
                  min="2"
                  max="10"
                  value={years}
                  required
                  onChange={(e) => setYears(Number(e.target.value))}
                />
              </label>
            </div>
            <fieldset>
              <legend>Chế độ nghiên cứu</legend>
              <div className="mode-grid">
                {[
                  ["standard", "Tiêu chuẩn", "Phạm vi tài liệu tiêu chuẩn."],
                  [
                    "deep",
                    "Chuyên sâu",
                    "Mở rộng phạm vi tài liệu và truy xuất trong ngân sách.",
                  ],
                ].map(([value, title, detail]) => (
                  <label
                    className={"mode " + (mode === value ? "selected" : "")}
                    key={value}
                  >
                    <input
                      type="radio"
                      name="mode"
                      value={value}
                      checked={mode === value}
                      onChange={() => setMode(value)}
                    />
                    <span>
                      <strong>{title}</strong>
                      <small>{detail}</small>
                    </span>
                  </label>
                ))}
              </div>
            </fieldset>
            <div className="filter-row">
              <label>
                Mã đối chiếu
                <input
                  value={peers}
                  maxLength={45}
                  placeholder="Tự chọn cho nhóm bán dẫn hoặc nhập mã"
                  onChange={(e) => setPeers(e.target.value)}
                />
              </label>
              <label>
                Giới hạn yêu cầu tìm kiếm
                <input
                  type="number"
                  min="0"
                  max={config.data?.search_budget}
                  value={budget}
                  placeholder={
                    config.data
                      ? "Mặc định: " + config.data.search_budget
                      : "Theo cấu hình"
                  }
                  onChange={(e) => setBudget(e.target.value)}
                />
              </label>
            </div>
            <details>
              <summary>Giá tham chiếu có nguồn</summary>
              <div className="filter-row">
                <label>Giá USD/cổ phiếu
                  <input type="number" min="0.000001" step="any" value={referencePrice}
                    onChange={(event) => setReferencePrice(event.target.value)} />
                </label>
                <label>Ngày giá
                  <input type="date" required={!!referencePrice} max={asOf} value={priceDate}
                    onChange={(event) => setPriceDate(event.target.value)} />
                </label>
                <label>Nguồn giá HTTPS
                  <input type="url" pattern="https://.+" required={!!referencePrice} value={priceUrl}
                    onChange={(event) => setPriceUrl(event.target.value)} />
                </label>
              </div>
            </details>
            {start.isError && (
              <p role="alert" className="error-text">
                {start.error.message}
              </p>
            )}
            <button
              className="button primary"
              disabled={start.isPending || !ticker.trim()}
            >
              {start.isPending ? "Đang gửi…" : "Bắt đầu phân tích"}{" "}
              <ArrowRight size={16} />
            </button>
          </form>
        </section>
        <section className="panel">
          <Section title="Kết nối dữ liệu" />
          <ConnectionList state={system.data} />
          <p className="muted">
            Brave, Gemini và SEC hiển thị tình trạng cấu hình. Kết quả truy cập
            thực tế được ghi trong phiên nghiên cứu.
          </p>
        </section>
      </div>
    </>
  );
}

function ProgressPanel({ id }: { id: string }) {
  const progress = useQuery({
    queryKey: ["progress", id],
    queryFn: ({ signal }) =>
      api<Progress>("/analysis/" + id + "/progress", { signal }),
    refetchInterval: (query) =>
      query.state.data && terminal(query.state.data.run.status) ? false : 3000,
  });
  const [, setTick] = useState(0);
  const done = !!progress.data && terminal(progress.data.run.status);
  useEffect(() => {
    if (done) return;
    const timer = window.setInterval(() => setTick((t) => t + 1), 1000);
    return () => clearInterval(timer);
  }, [done]);
  if (progress.isPending) return <Loading />;
  if (progress.isError)
    return (
      <State
        error
        title="Chưa lấy được tiến trình"
        retry={() => void progress.refetch()}
      >
        {progress.error.message}
      </State>
    );
  const { run, events } = progress.data;
  const ended =
    done && events.length
      ? Date.parse(events[events.length - 1].at)
      : Date.now();
  const seconds = Math.max(
    0,
    Math.floor((ended - Date.parse(run.created_at)) / 1000),
  );
  return (
    <section className="panel progress-panel">
      <Section
        title={"Tiến trình · " + run.ticker}
        detail={number(seconds) + " giây từ khi tạo phiên"}
        action={<Badge status={run.status} />}
      />
      <ol className="timeline">
        {events.map((event, index) => (
          <li key={event.at + index}>
            <span>
              <strong>{runStates[event.status] ?? event.status}</strong>
              <small>{displayTime(event.at)}</small>
            </span>
            <p>{event.message}</p>
          </li>
        ))}
      </ol>
      {!events.length && <p className="muted">Phiên đang chờ sự kiện xử lý.</p>}
      {readable(run.status) && <OpenReport id={id} />}
    </section>
  );
}

export function SystemPage() {
  const system = useSystem();
  return (
    <>
      <Heading
        title="Trạng thái hệ thống"
        detail="Theo dõi cơ sở dữ liệu và cấu hình nguồn cung cấp."
      />
      {system.isPending ? (
        <Loading />
      ) : system.isError ? (
        <State
          error
          title="Máy chủ chưa sẵn sàng"
          retry={() => void system.refetch()}
        >
          {system.error.message}
        </State>
      ) : (
        <div className="dashboard-grid">
          <section className="panel">
            <Section title="Kết nối và cấu hình" />
            <ConnectionList state={system.data} />
          </section>
          <section className="panel">
            <Section title="Phương pháp nghiên cứu" />
            <p>
              FinSight thu thập hồ sơ SEC, chuẩn hóa dữ liệu tài chính, truy
              xuất bằng chứng và đối chiếu các nhận định trước khi lưu báo cáo.
            </p>
            <p>
              Trạng thái có bằng chứng phản ánh kết quả đối chiếu trong phạm vi
              tài liệu của phiên. Đây không phải kết quả kiểm toán độc lập.
            </p>
            <p className="muted">
              Truy xuất ngữ nghĩa:{" "}
              {system.data.embedding_enabled ? "Đã bật" : "Đang tắt"}. Lưu dữ
              liệu thị trường:{" "}
              {system.data.market_persistence ? "Đã bật" : "Đang tắt"}.
            </p>
          </section>
        </div>
      )}
    </>
  );
}
