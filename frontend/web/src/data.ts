export interface Run {
  id: string;
  status: string;
  ticker: string;
  as_of: string;
  created_at: string;
  request: ResearchRequest;
  company_name?: string | null;
  industry?: string | null;
}
export interface ResearchRequest {
  ticker: string;
  as_of: string;
  years: number;
  mode: string;
  search_budget?: number;
  peers: string[];
  market_reference?: { close: number; date: string; currency: "USD"; url: string } | null;
}
export interface Company {
  ticker: string;
  name: string;
  cik: number;
  industry: string;
  exchange: string;
}
export interface Fact {
  key: string;
  value: number;
  unit: string;
  start: string | null;
  end: string;
  filed: string;
  period: string;
  form: string;
  accession: string;
  concept: string;
  url: string;
}
export interface Ratio {
  period?: "FY" | "Q";
  key: string;
  value: number | null;
  unit: string;
  end: string | null;
  filed: string | null;
  inputs: string[];
  formula: string;
  reason: string;
}
export interface Evidence {
  id: string;
  title: string;
  kind: string;
  locator: string;
  text: string;
  url: string;
  published: string | null;
  report_end: string | null;
  quality: string;
}
interface NumericClaim {
  key: string;
  value: number;
  unit: string;
  end: string;
  period?: string | null;
}
export interface Claim {
  reason_code?: string;
  id: string;
  role: string;
  status: string;
  reason: string;
  evidence_ids: string[];
  counter_ids: string[];
  claim: {
    text: string;
    dimension: string;
    stance: string;
    numeric: NumericClaim | null;
    comparisons?: NumericClaim[];
    references: { evidence_id: string; quote: string }[];
  };
}
export function claimVerificationLabel(claim: Claim) {
  if (claim.status !== "UNVERIFIED") return undefined;
  if (claim.reason_code === "FILING_DATE_AS_PERIOD") return "Nhầm ngày nộp hồ sơ với ngày kết thúc kỳ";
  if (!claim.evidence_ids.length && !claim.counter_ids.length)
    return "Chưa có nguồn liên kết";
  if (claim.reason_code === "NUMERIC_SCOPE") return "Cần đối chiếu đúng phạm vi chỉ tiêu";
  if (claim.reason_code === "NUMERIC_SCALE")
    return "Có nguồn · Sai thang đơn vị";
  if (claim.reason_code === "INCOMPLETE_COMPARISON")
    return "Thiếu dữ liệu cho một vế so sánh";
  if (
    ["MISSING_NUMERIC", "AMBIGUOUS_NUMERIC", "NUMERIC_PERIOD"].includes(
      claim.reason_code ?? "",
    ) ||
    claim.reason.startsWith("Thiếu dữ liệu duy nhất")
  ) {
    return "Có nguồn · Chưa đối chiếu số liệu";
  }
  return "Có nguồn · Chưa xác minh nội dung";
}

export interface Score {
  supported: number;
  total_claims: number;
  supported_rate: number;
  primary_evidence: number;
  total_dimensions: number;
  covered_dimensions: string[];
  contradicted_claims: number;
  unresolved_conflicts: number;
  latest_publication: string | null;
}
export interface Report {
  id: string;
  company: Company;
  request: ResearchRequest;
  status: string;
  version: string;
  created_at: string;
  scores: Score;
  summary_ids: string[];
  lead_assessment?: { topic: string; text: string; claim_ids: string[]; context_ids?: string[]; confidence?: string; basis?: string; mode?: string }[];
  leadership_updates?: Evidence[];
  external_context?: Record<"news" | "social", {
    status: string;
    found: number;
    read: number;
    excerpts?: number;
    analyzed?: number;
    pending?: number;
    queued?: number;
    excluded_after_cutoff?: number;
    attempted?: number;
    links?: {url: string; title: string}[];
    error?: string;
    unreadable_reasons?: Record<string, number>;
    observations: { id: string; title: string; url: string; published: string; observation: string; quote: string; source_type?: string; confidence?: string; reason?: string; dimension?: string; analysis_status?: string }[];
  }>;
  topic_coverage?: Record<string, {total: number; supported: number; agent_status: string}>;
  retrieval?: {
    collected_chunks: number;
    indexed_chunks: number;
    indexed_documents: number;
    cited_documents: number;
    sec_reused?: number;
    sec_fetched?: number;
  };
  facts: Fact[];
  ratios: Ratio[];
  claims: Claim[];
  evidence: Evidence[];
  warnings: string[];
  agents: Record<string, { count: number; status: string }>;
  usage: Record<string, number>;
  elapsed_seconds: number | null;
  estimated_cost_usd: number | null;
  peers: {
    ticker: string;
    name: string;
    end: string;
    unit: string;
    revenue: number;
    ratios: Record<string, number | null>;
    url: string;
    same_sic?: boolean;
    price_date?: string | null;
    market_url?: string | null;
  }[];
  changes: {
    key: string;
    end: string;
    unit: string;
    prior: Fact;
    current: Fact;
    resolved: boolean;
  }[];
  market: {
    currency?: string;
    market_cap?: number;
    market_cap_date?: string;
    source?: string;
    url?: string;
    observations?: { date: string; close: number }[];
  };
}
export interface Dashboard {
  companies: number;
  reports: number;
  evidence_count: number;
  claim_count: number;
  latest_scores: Score | null;
  latest_cost_usd: number | null;
}
export interface System {
  mysql: string;
  sec_configured: boolean;
  brave_configured: boolean;
  gemini_configured: boolean;
  embedding_enabled: boolean;
  market_persistence: boolean;
}
export interface Progress {
  run: Run;
  events: { status: string; message: string; at: string }[];
}
export interface Signal {
  title: string;
  period: string;
  end: string;
  text: string;
  inputs: Fact[];
}
export interface Investment {
  signals: Signal[];
  driver_ids: string[];
  risk_ids: string[];
  eps: Fact | null;
  price: { date: string; close: number; currency: string; url: string | null } | null;
}
export interface DCFResult {
  base: Valuation;
  sensitivity: {
    discount: number;
    terminal_growth: number;
    valuation: Valuation | null;
  }[];
}
interface Valuation {
  per_share: number;
  enterprise_value: number;
  equity_value: number;
  terminal_value: number;
}

export async function api<T>(path: string, options?: RequestInit): Promise<T> {
  const result = await fetch("/api/v1" + path, {
    ...options,
    headers: { Accept: "application/json", ...options?.headers },
  });
  if (!result.ok) {
    const payload = await result.json().catch(() => null);
    throw new Error(
      typeof payload?.detail === "string"
        ? payload.detail
        : "Yêu cầu không thành công (" + result.status + ").",
    );
  }
  return result.status === 204 ? (undefined as T) : result.json();
}

export const post = <T>(path: string, payload?: unknown) =>
  api<T>(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload ?? {}),
  });

export const runStates: Record<string, string> = {
  pending: "Đang chờ",
  collecting: "Thu thập dữ liệu",
  validating: "Chuẩn hóa số liệu",
  retrieving: "Truy xuất bằng chứng",
  analyzing: "Phân tích",
  verifying: "Kiểm chứng",
  generating: "Tổng hợp báo cáo",
  completed: "Hoàn tất",
  partial: "Có giới hạn",
  failed: "Thất bại",
};
export const verification: Record<string, string> = {
  SUPPORTED: "Có bằng chứng hỗ trợ",
  PARTIALLY_SUPPORTED: "Được hỗ trợ một phần",
  CONTRADICTED: "Có bằng chứng phản bác",
  UNVERIFIED: "Chưa đủ bằng chứng xác minh",
  NOT_APPLICABLE: "Không áp dụng",
};
export const dimensions: Record<string, string> = {
  company: "Mô hình kinh doanh",
  financial: "Sức khỏe tài chính",
  growth: "Tăng trưởng",
  moat: "Lợi thế cạnh tranh",
  industry: "Ngành và đối thủ",
  governance: "Quản trị doanh nghiệp",
  risk: "Rủi ro",
  valuation: "Định giá",
};
export const roles: Record<string, string> = {
  business: "Chuyên gia mô hình kinh doanh",
  financial: "Chuyên gia tài chính",
  market: "Chuyên gia định giá",
  risk: "Chuyên gia rủi ro",
  lead: "Lead · Tổng hợp",
  external_context: "Bối cảnh báo chí và mạng xã hội",
  verification: "Kiểm chứng",
  cross_examination: "Phản biện",
  computed: "Phép tính tài chính",
};
export const periods: Record<string, string> = {
  FY: "Năm tài chính",
  Q: "Quý",
  YTD: "Lũy kế",
  instant: "Tại thời điểm",
};
export const metricNames: Record<string, string> = {
  revenue: "Doanh thu",
  gross_profit: "Lợi nhuận gộp",
  research_and_development_expense: "Chi phí nghiên cứu và phát triển",
  research_and_development_expense_growth:
    "Tăng trưởng chi phí nghiên cứu và phát triển",
  operating_income: "Lợi nhuận hoạt động",
  operating_expenses: "Chi phí hoạt động",
  operating_expenses_growth: "Tăng trưởng chi phí hoạt động",
  net_income: "Lợi nhuận ròng",
  eps_diluted: "Lãi pha loãng trên mỗi cổ phiếu",
  assets: "Tổng tài sản",
  liabilities: "Tổng nợ phải trả",
  equity: "Vốn chủ sở hữu",
  cash: "Tiền và tương đương tiền",
  ocf: "Dòng tiền hoạt động",
  capex: "Chi đầu tư",
  current_assets: "Tài sản ngắn hạn",
  current_liabilities: "Nợ ngắn hạn",
  debt_current: "Nợ dài hạn đến hạn trả",
  debt_noncurrent: "Nợ vay dài hạn",
  short_borrowings: "Vay ngắn hạn",
  shares: "Cổ phiếu đang lưu hành",
  da: "Khấu hao và phân bổ",
  pretax: "Lợi nhuận trước thuế",
  tax: "Chi phí thuế thu nhập",
  revenue_growth: "Tăng trưởng doanh thu",
  net_income_growth: "Tăng trưởng lợi nhuận ròng",
  gross_margin: "Biên lợi nhuận gộp",
  operating_margin: "Biên lợi nhuận hoạt động",
  net_margin: "Biên lợi nhuận ròng",
  roe: "Sinh lời trên vốn chủ sở hữu (ROE)",
  roa: "Sinh lời trên tài sản (ROA)",
  roic: "Sinh lời trên vốn đầu tư (ROIC)",
  current_ratio: "Hệ số thanh toán hiện hành",
  debt_equity: "Nợ vay trên vốn chủ sở hữu",
  net_debt: "Nợ vay ròng",
  fcf: "Dòng tiền tự do",
  fcf_margin: "Biên dòng tiền tự do",
  cash_conversion: "Dòng tiền hoạt động trên lợi nhuận ròng",
  pe: "Giá trên lợi nhuận (P/E)",
  pb: "Giá trên giá trị sổ sách (P/B)",
  p_fcf: "Giá trên dòng tiền tự do (P/FCF)",
  ev_ebitda: "Giá trị doanh nghiệp trên EBITDA",
};
const formulaTerms: Record<string, string> = {
  ...metricNames,
  average: "Bình quân",
  interest_bearing_debt: "Nợ vay chịu lãi",
  invested_capital: "Vốn đầu tư",
  market_cap: "Vốn hóa",
  reported_debt: "Nợ đã xác định",
  reported_debt_less_cash: "Nợ đã xác định trừ tiền mặt",
  interest_coverage: "Khả năng trả lãi",
  debt_current_total: "Tổng nợ vay ngắn hạn",
  interest_expense: "Chi phí lãi vay",
  consolidated_profit: "Lợi nhuận hợp nhất",
};
export const formulaText = (formula: string) =>
  formula.replace(/[a-z_]+/g, (token) =>
    token.startsWith("prior_") && formulaTerms[token.slice(6)]
      ? formulaTerms[token.slice(6)] + " kỳ trước"
      : (formulaTerms[token] ?? token),
  );
export const displayDate = (date?: string | null) =>
  date ? date.slice(0, 10).split("-").reverse().join("/") : "—";
export const displayTime = (date: string) =>
  new Date(date).toLocaleString("vi-VN", {
    dateStyle: "short",
    timeStyle: "short",
  });
export const today = () => new Date().toISOString().slice(0, 10);
export const number = (value: number, digits = 2) =>
  new Intl.NumberFormat("vi-VN", { maximumFractionDigits: digits }).format(
    value,
  );
export const unitName = (unit: string) =>
  unit === "x" ? "lần" : unit.replace("shares", "cổ phiếu");
export const valueText = (
  value: number | null | undefined,
  unit: string,
  compact = false,
) => {
  if (value == null) return "Chưa có dữ liệu";
  if (compact && unit === "USD" && Math.abs(value) >= 1e6) {
    const billion = Math.abs(value) >= 1e9;
    return (
      number(value / (billion ? 1e9 : 1e6)) +
      (billion ? " tỷ USD" : " triệu USD")
    );
  }
  return number(value) + (unit === "%" ? "%" : " " + unitName(unit));
};
export const terminal = (status: string) =>
  ["completed", "partial", "failed"].includes(status);
export const readable = (status: string) =>
  ["completed", "partial"].includes(status);
export const factKey = (fact: Fact) =>
  [fact.accession, fact.concept, fact.start ?? "-", fact.end, fact.unit].join(
    "/",
  );
export async function evidenceId(fact: Fact) {
  const digest = await crypto.subtle.digest(
    "SHA-256",
    new TextEncoder().encode(factKey(fact)),
  );
  return (
    "X:" +
    Array.from(new Uint8Array(digest).slice(0, 12), (byte) =>
      byte.toString(16).padStart(2, "0"),
    ).join("")
  );
}
export const validSource = (source: string | undefined) => {
  try {
    return source && new URL(source).protocol === "https:" ? source : undefined;
  } catch {
    return undefined;
  }
};
export const claimText = (claim: Claim) => {
  const n = claim.claim.numeric;
  return claim.role === "computed" && n && claim.claim.dimension !== "valuation"
    ? (metricNames[n.key] ?? n.key) +
        " kỳ kết thúc " +
        displayDate(n.end) +
        " là " +
        valueText(n.value, n.unit, true) +
        "."
    : claim.claim.text;
};
