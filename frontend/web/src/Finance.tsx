import { useMemo, useState } from "react";
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import {
  displayDate,
  factKey,
  metricNames,
  number,
  periods,
  validSource,
  valueText,
  type Fact,
  type Report,
} from "./data";
import { EvidenceButton, SourceLink, type Selection } from "./Evidence";
import { Section, State } from "./ui";

const groups = [
  {
    id: "income",
    label: "Kết quả kinh doanh",
    keys: ["revenue", "gross_profit", "operating_income", "net_income"],
  },
  { id: "cash", label: "Dòng tiền", keys: ["ocf", "capex", "fcf"] },
  {
    id: "balance",
    label: "Bảng cân đối",
    keys: ["assets", "liabilities", "equity", "cash"],
  },
  {
    id: "margin",
    label: "Biên lợi nhuận",
    keys: ["gross_margin", "operating_margin", "net_margin", "fcf_margin"],
  },
  { id: "returns", label: "Sinh lời", keys: ["roe", "roa", "roic"] },
];
const scales = [
  { factor: 1, label: "USD" },
  { factor: 1e3, label: "Nghìn USD" },
  { factor: 1e6, label: "Triệu USD" },
  { factor: 1e9, label: "Tỷ USD" },
];
const seriesColors = ["#5593ff", "#26b6ae", "#a78bfa", "#e6a252"];

export default function Finance({
  report,
  open,
}: {
  report: Report;
  open: (selection: Selection) => void;
}) {
  const [period, setPeriod] = useState("FY"),
    [groupId, setGroup] = useState("income"),
    [scale, setScale] = useState(1e9),
    [query, setQuery] = useState("");
  const [page, setPage] = useState(0);
  const [view, setView] = useState<"facts" | "ratios">("facts");
  const group = groups.find((item) => item.id === groupId)!;
  const percentages = ["margin", "returns"].includes(groupId);
  const unit = percentages
    ? "%"
    : scales.find((item) => item.factor === scale)!.label;
  const factMap = useMemo(
    () => new Map(report.facts.map((fact) => [factKey(fact), fact])),
    [report.facts],
  );
  const validDates = new Set(
    report.facts
      .filter((fact) => fact.period === period)
      .map((fact) => fact.end),
  );
  const currentFacts = report.facts.filter(
    (fact) =>
      fact.period === period ||
      (fact.period === "instant" &&
        (validDates.has(fact.end) || !validDates.size)),
  );
  const graph = new Map<string, Record<string, number | string>>();
  const periodRatios = report.ratios.filter(
    (row) => (row.period ?? "FY") === period,
  );
  const input = percentages
    ? periodRatios
    : [
        ...currentFacts.filter((fact) =>
          groupId === "balance"
            ? fact.period === "instant"
            : fact.period === period,
        ),
        ...(period === "FY"
          ? periodRatios.filter((ratio) => ratio.key === "fcf")
          : []),
      ];
  for (const row of input) {
    if (
      !row.end ||
      row.value == null ||
      row.unit !== (percentages ? "%" : "USD") ||
      !group.keys.includes(row.key)
    )
      continue;
    const point = graph.get(row.end) ?? { period: row.end };
    if (point[row.key] === undefined)
      point[row.key] = row.value / (percentages ? 1 : scale);
    graph.set(row.end, point);
  }
  const graphRows = [...graph.values()].sort((a, b) =>
    String(a.period).localeCompare(String(b.period)),
  );
  const graphKeys = group.keys.filter((key) =>
    graphRows.some((row) => key in row),
  );
  const tableRows = (view === "facts" ? currentFacts : periodRatios).filter(
    (row) =>
      (metricNames[row.key] ?? row.key)
        .toLowerCase()
        .includes(query.trim().toLowerCase()),
  );
  return (
    <>
      <section className="panel">
        <Section
          title="Diễn biến tài chính"
          detail={
            "Đơn vị: " + unit + " · Nguồn: SEC EDGAR và các phép tính từ hồ sơ."
          }
        />
        <div className="filter-row chart-controls">
          <label>
            Nhóm chỉ tiêu
            <select value={groupId} onChange={(e) => setGroup(e.target.value)}>
              {groups.map((g) => (
                <option value={g.id} key={g.id}>
                  {g.label}
                </option>
              ))}
            </select>
          </label>
          <label>
            Loại kỳ
            <select
              value={period}
              onChange={(e) => {
                setPeriod(e.target.value);
                setPage(0);
              }}
            >
              <option value="FY">Năm tài chính</option>
              <option value="Q">Quý</option>
            </select>
          </label>
          {!percentages && (
            <label>
              Đơn vị biểu đồ
              <select
                value={scale}
                onChange={(e) => setScale(Number(e.target.value))}
              >
                {scales.map((item) => (
                  <option value={item.factor} key={item.factor}>
                    {item.label}
                  </option>
                ))}
              </select>
            </label>
          )}
        </div>
        {graphRows.length ? (
          <div
            className="chart"
            aria-label={group.label + " theo kỳ, đơn vị " + unit}
          >
            <ResponsiveContainer width="100%" height="100%">
              <LineChart
                data={graphRows}
                margin={{ top: 10, right: 18, bottom: 8, left: 12 }}
              >
                <CartesianGrid
                  vertical={false}
                  stroke="var(--border)"
                  strokeDasharray="4 5"
                />
                <XAxis
                  dataKey="period"
                  tickFormatter={(value) => displayDate(String(value))}
                  minTickGap={26}
                  tick={{ fill: "var(--muted)", fontSize: 11 }}
                  stroke="var(--border)"
                />
                <YAxis
                  width={64}
                  tickFormatter={(value) => number(Number(value), 1)}
                  tick={{ fill: "var(--muted)", fontSize: 11 }}
                  stroke="var(--border)"
                />
                <Tooltip
                  labelFormatter={(value) => displayDate(String(value))}
                  formatter={(value) =>
                    typeof value === "number"
                      ? number(value) + " " + unit
                      : String(value)
                  }
                  contentStyle={{
                    background: "var(--panel)",
                    borderColor: "var(--border)",
                    borderRadius: 10,
                  }}
                />
                <Legend />
                {graphKeys.map((key, index) => (
                  <Line
                    key={key}
                    type="linear"
                    name={metricNames[key]}
                    dataKey={key}
                    stroke={seriesColors[index]}
                    strokeWidth={2.5}
                    dot={{ r: 3 }}
                    isAnimationActive={false}
                  />
                ))}
              </LineChart>
            </ResponsiveContainer>
          </div>
        ) : (
          <State title="Chưa đủ dữ liệu cho biểu đồ này">
            {percentages && period === "Q"
              ? "Báo cáo này chưa có tỷ số đã tính cho nhóm chỉ tiêu theo quý."
              : "Chọn nhóm chỉ tiêu hoặc kỳ báo cáo khác."}
          </State>
        )}
      </section>
      {!!report.market.observations?.length && (
        <section className="panel">
          <Section
            title="Giá đóng cửa"
            detail={
              "Nguồn Yahoo Finance · " +
              (report.market.currency ?? "Tiền tệ theo nguồn")
            }
          />
          <div className="chart">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={report.market.observations}>
                <CartesianGrid vertical={false} stroke="var(--border)" />
                <XAxis
                  dataKey="date"
                  tickFormatter={(value) => displayDate(String(value))}
                  minTickGap={45}
                />
                <YAxis tickFormatter={(value) => number(Number(value), 1)} />
                <Tooltip
                  labelFormatter={(value) => displayDate(String(value))}
                />
                <Line
                  dataKey="close"
                  name="Giá đóng cửa"
                  stroke={seriesColors[0]}
                  dot={false}
                  isAnimationActive={false}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
          {validSource(report.market.url) && (
            <SourceLink href={report.market.url!}>
              Mở nguồn thị trường
            </SourceLink>
          )}
        </section>
      )}
      <section className="panel">
        <Section
          title="Bảng số liệu tài chính"
          detail={
            view === "facts"
              ? "Số liệu chuẩn hóa từ hồ sơ SEC."
              : "Tỷ số do hệ thống tính từ số liệu đầu vào."
          }
        />
        <div className="filter-row">
          <label>
            Loại số liệu
            <select
              value={view}
              onChange={(e) => {
                setView(e.target.value === "facts" ? "facts" : "ratios");
                setPage(0);
              }}
            >
              <option value="facts">Số liệu công bố</option>
              <option value="ratios">Tỷ số và công thức</option>
            </select>
          </label>
          <label>
            Tìm chỉ tiêu
            <input
              value={query}
              placeholder="Doanh thu, lợi nhuận…"
              onChange={(e) => {
                setQuery(e.target.value);
                setPage(0);
              }}
            />
          </label>
        </div>
        {tableRows.length ? (
          <>
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>Chỉ tiêu</th>
                    <th>Kỳ kết thúc</th>
                    <th>Giá trị</th>
                    <th>Công bố</th>
                    <th>Nguồn và phép tính</th>
                  </tr>
                </thead>
                <tbody>
                  {tableRows
                    .slice(page * 15, (page + 1) * 15)
                    .map((row, index) => (
                      <tr key={row.key + "-" + row.end + "-" + index}>
                        <td>
                          {metricNames[row.key] ?? row.key}
                          {"period" in row && (
                            <small className="table-note">
                              {periods[row.period ?? "FY"] ?? row.period}
                            </small>
                          )}
                        </td>
                        <td>{displayDate(row.end)}</td>
                        <td className="numeric">
                          {valueText(row.value, row.unit)}
                          {"reason" in row && row.reason && (
                            <small className="table-note">{row.reason}</small>
                          )}
                        </td>
                        <td>{displayDate(row.filed)}</td>
                        <td>
                          <EvidenceButton
                            onClick={() =>
                              open({
                                title: metricNames[row.key] ?? row.key,
                                facts:
                                  "inputs" in row
                                    ? row.inputs.flatMap((key) => {
                                        const fact = factMap.get(key);
                                        return fact ? [fact] : [];
                                      })
                                    : [row as Fact],
                                urls:
                                  "inputs" in row
                                    ? row.inputs.filter(
                                        (input) => !!validSource(input),
                                      )
                                    : undefined,
                                formula:
                                  "formula" in row ? row.formula : undefined,
                                detail: valueText(row.value, row.unit),
                              })
                            }
                          />
                        </td>
                      </tr>
                    ))}
                </tbody>
              </table>
            </div>
            <div className="pagination">
              <span>{tableRows.length} dòng</span>
              <button
                className="button"
                disabled={!page}
                onClick={() => setPage(page - 1)}
              >
                Trang trước
              </button>
              <button
                className="button"
                disabled={(page + 1) * 15 >= tableRows.length}
                onClick={() => setPage(page + 1)}
              >
                Trang sau
              </button>
            </div>
          </>
        ) : (
          <State title="Không có số liệu phù hợp" />
        )}
      </section>
      {!!report.changes.length && (
        <section className="panel">
          <Section title="Thay đổi giữa các lần công bố" />
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Chỉ tiêu</th>
                  <th>Kỳ kết thúc</th>
                  <th>Công bố trước</th>
                  <th>Công bố sau</th>
                  <th>Bằng chứng</th>
                </tr>
              </thead>
              <tbody>
                {report.changes.slice(0, 30).map((row, index) => (
                  <tr key={index}>
                    <td>{metricNames[row.key] ?? row.key}</td>
                    <td>{displayDate(row.end)}</td>
                    <td>{valueText(row.prior.value, row.unit)}</td>
                    <td>{valueText(row.current.value, row.unit)}</td>
                    <td>
                      <EvidenceButton
                        onClick={() =>
                          open({
                            title: metricNames[row.key] ?? row.key,
                            facts: [row.prior, row.current],
                          })
                        }
                      />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </>
  );
}
