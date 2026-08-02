import { useEffect, useMemo, useState } from "react";
import {
  auditRecords,
  dashboardRuns,
  findings,
  governanceReplayEvents,
  governanceWarnings,
  incidents,
  latencyTraceSeries,
  modelLatency,
  privacyEvidence,
  sloTimeline,
  slos,
  traces
} from "./data.js";

const navItems = [
  ["dashboard", "Dashboard"],
  ["traces", "Traces"],
  ["explorer", "Trace explorer"],
  ["incidents", "Incidents"],
  ["slos", "SLOs"],
  ["governance", "Governance"],
  ["create", "Create project"]
];

const fmtMs = (value) => (value >= 1000 ? `${(value / 1000).toFixed(2)}s` : `${value}ms`);
const statusClass = (status) => ({
  healthy: "success",
  breach: "critical",
  risk: "warning",
  open: "warning"
}[status] || status);

function StatusChip({ value, type = "status-chip" }) {
  return <span className={`${type} ${statusClass(value)}`}>{value}</span>;
}

function PageHead({ title, action }) {
  return (
    <div className="page-head">
      <h2>{title}</h2>
      {action}
    </div>
  );
}

function MetricCards({ items }) {
  return (
    <div className="metric-grid">
      {items.map((item) => (
        <article className="metric-card" key={item.label}>
          <span>{item.label}</span>
          <strong>{item.value}</strong>
        </article>
      ))}
    </div>
  );
}

function LineChart({ data, unit = "ms" }) {
  const width = 760;
  const height = 220;
  const pad = 44;
  const max = Math.max(...data.map((d) => d.value)) * 1.15;
  const points = data.map((d, i) => {
    const x = pad + (i * (width - pad * 2)) / Math.max(data.length - 1, 1);
    const y = height - pad - (d.value / max) * (height - pad * 2);
    return { ...d, x, y };
  });
  const ticks = [0, 0.25, 0.5, 0.75, 1].map((ratio) => ({
    value: Math.round(max * ratio),
    y: height - pad - ratio * (height - pad * 2)
  }));

  return (
    <div className="chart">
      <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label="line chart">
        <defs>
          <linearGradient id="lineGrad" x1="0" x2="1">
            <stop stopColor="#41a6ff" />
            <stop offset="1" stopColor="#69e6d3" />
          </linearGradient>
        </defs>
        {ticks.map((tick) => (
          <g key={tick.y}>
            <line x1={pad} x2={width - pad} y1={tick.y} y2={tick.y} stroke="currentColor" opacity=".08" />
            <text x={pad - 8} y={tick.y + 4} textAnchor="end" fill="currentColor" opacity=".5" fontSize="10">
              {tick.value}
              {unit}
            </text>
          </g>
        ))}
        <polyline points={points.map((p) => `${p.x},${p.y}`).join(" ")} fill="none" stroke="url(#lineGrad)" strokeWidth="3" />
        {points.map((p) => (
          <circle key={p.label} cx={p.x} cy={p.y} r="6" fill="#41a6ff">
            <title>{p.detail}</title>
          </circle>
        ))}
      </svg>
    </div>
  );
}

function BarChart({ data, unit = "tokens", horizontal = false }) {
  const width = 560;
  const height = 220;
  const pad = horizontal ? 34 : 46;
  const max = Math.max(...data.map((d) => d.value)) * 1.12;

  if (horizontal) {
    const rowH = (height - pad) / data.length;
    const plotX = 138;
    const plotW = width - 190;
    return (
      <div className="chart">
        <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label="bar chart">
          <defs>
            <linearGradient id="barGradH" x1="0" x2="1">
              <stop stopColor="#41a6ff" />
              <stop offset="1" stopColor="#a78bfa" />
            </linearGradient>
          </defs>
          {data.map((d, i) => {
            const y = 18 + i * rowH;
            const barW = (plotW * d.value) / max;
            return (
              <g key={d.label}>
                <text x="0" y={y + 15} fill="currentColor" opacity=".58" fontSize="11">
                  {d.label.length > 18 ? `${d.label.slice(0, 15)}...` : d.label}
                </text>
                <rect x={plotX} y={y} width={barW} height="20" rx="4" fill="url(#barGradH)">
                  <title>{d.detail}</title>
                </rect>
              </g>
            );
          })}
        </svg>
      </div>
    );
  }

  const slot = (width - pad * 2) / data.length;
  return (
    <div className="chart">
      <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label="bar chart">
        <defs>
          <linearGradient id="barGrad" y1="1" y2="0">
            <stop stopColor="#41a6ff" />
            <stop offset="1" stopColor="#69e6d3" />
          </linearGradient>
        </defs>
        {data.map((d, i) => {
          const h = ((height - pad * 2) * d.value) / max;
          const barWidth = Math.max(8, slot * 0.42);
          const x = pad + i * slot + (slot - barWidth) / 2;
          const y = height - pad - h;
          return (
            <rect key={d.label} x={x} y={y} width={barWidth} height={h} rx="4" fill="url(#barGrad)">
              <title>{d.detail}</title>
            </rect>
          );
        })}
      </svg>
    </div>
  );
}

function TraceGraph({ trace }) {
  const slots = [
    { x: 55, y: 215 },
    { x: 165, y: 145 },
    { x: 165, y: 285 },
    { x: 300, y: 105 },
    { x: 300, y: 215 },
    { x: 455, y: 160 },
    { x: 455, y: 285 },
    { x: 605, y: 215 },
    { x: 765, y: 215 }
  ];
  const glyph = { start: "S", agent: "A", llm: "L", tool: "T", http: "H", final: "F" };
  const graphSpans = [
    { name: "Start", kind: "start", status: "success", duration: 0 },
    ...trace.spansList,
    { name: "PromptRedaction", kind: "agent", status: "captured", duration: 64 },
    { name: "AuditSink", kind: "http", status: "success", duration: 118 },
    { name: "Final", kind: "final", status: trace.status === "error" ? "error" : "success", duration: trace.duration }
  ].slice(0, slots.length);
  const nodes = graphSpans.map((span, i) => ({
    ...span,
    ...slots[i],
    glyph: glyph[span.kind] || "S",
    color: span.status === "error" ? "#ff6270" : span.kind === "llm" ? "#a78bfa" : span.kind === "tool" ? "#f6bc45" : span.kind === "start" ? "#41a6ff" : "#37d39a"
  }));
  const links = nodes.slice(0, -1).map((_, index) => [index, index + 1]);

  return (
    <div className="graph">
      <svg viewBox="0 0 820 430" role="img" aria-label="Trace graph">
        <defs>
          <linearGradient id="graphEdge" x1="0" x2="1">
            <stop stopColor="#41a6ff" />
            <stop offset="1" stopColor="#a78bfa" />
          </linearGradient>
          <marker id="graphArrow" markerWidth="10" markerHeight="10" refX="8" refY="3" orient="auto" markerUnits="strokeWidth">
            <path d="M0,0 L0,6 L8,3 z" fill="#7f91aa" opacity=".75" />
          </marker>
        </defs>
        {links.map(([from, to]) => (
          <path key={`${from}-${to}`} className="graph-edge" d={`M ${nodes[from].x + 23} ${nodes[from].y} L ${nodes[to].x - 24} ${nodes[to].y}`} markerEnd="url(#graphArrow)" />
        ))}
        {nodes.map((node) => (
          <g key={`${node.name}-${node.x}`} className="graph-node">
            <circle cx={node.x} cy={node.y} r="20" fill={node.color} opacity=".92" />
            <text x={node.x} y={node.y + 5} textAnchor="middle" fill="#061018" fontSize="13" fontWeight="900">
              {node.glyph}
            </text>
            <title>{`${node.name} | ${node.kind.toUpperCase()} - ${node.status.toUpperCase()} | ${fmtMs(node.duration)}`}</title>
          </g>
        ))}
      </svg>
    </div>
  );
}

function AuthScreen({ mode, setMode, onAuth, toggleTheme }) {
  return (
    <main className="auth-screen">
      <section className="auth-brand">
        <div className="auth-brand-row">
          <div className="brand-mark"><img src="/favicon.svg" alt="AgentSRE logo" /></div>
          <h1>AgentSRE</h1>
        </div>
        <h2>operate production AI agents with traceable reliability</h2>
        <p>SDK-based LangGraph, LLM, tool, latency, cost, redaction, and governance telemetry for enterprise agent teams.</p>
      </section>
      <section className="auth-panel">
        <button className="icon-button floating-theme" type="button" aria-label="Toggle theme" onClick={toggleTheme}>Th</button>
        <div className="tab-row" role="tablist">
          <button className={`tab ${mode === "login" ? "active" : ""}`} type="button" onClick={() => setMode("login")}>Login</button>
          <button className={`tab ${mode === "register" ? "active" : ""}`} type="button" onClick={() => setMode("register")}>Register</button>
        </div>
        <form className="auth-form" onSubmit={(event) => { event.preventDefault(); onAuth(); }}>
          {mode === "register" && <label>Full name<input type="text" defaultValue="Shrut Suman" autoComplete="name" /></label>}
          <label>Email<input type="email" defaultValue="user@example.com" autoComplete="email" /></label>
          <label>Password<input type="password" autoComplete="current-password" /></label>
          <button className="primary-button" type="submit">{mode === "register" ? "Register" : "Login"}</button>
        </form>
      </section>
    </main>
  );
}

function Sidebar({ page, setPage, logout }) {
  return (
    <aside id="sidebar" className="sidebar">
      <div className="sidebar-brand">
        <div className="brand-mark small"><img src="/favicon.svg" alt="AgentSRE logo" /></div>
        <span>AgentSRE</span>
      </div>
      <nav className="nav-list" aria-label="Primary">
        {navItems.map(([id, label]) => (
          <button key={id} className={`nav-item ${page === id ? "active" : ""}`} type="button" onClick={() => setPage(id)}>{label}</button>
        ))}
      </nav>
      <footer className="sidebar-footer">
        <span>user@example.com</span>
        <button type="button" onClick={logout}><span aria-hidden="true">Out</span> Logout</button>
      </footer>
    </aside>
  );
}

function Topbar({ setToast, toggleTheme }) {
  return (
    <header className="topbar">
      <h1 id="pageTitle">Agent Operations</h1>
      <div className="topbar-actions">
        <select aria-label="Project selector" onChange={(event) => setToast(`${event.target.value.replace("Project: ", "")} selected.`)}>
          <option>Project: AI Travel Ops</option>
          <option>Project: Customer Care Copilot</option>
          <option>Project: Research Studio</option>
        </select>
        <button className="icon-button" type="button" aria-label="Refresh" onClick={() => setToast("Telemetry refreshed from the selected project.")}>Rf</button>
        <button className="icon-button" type="button" aria-label="Toggle theme" onClick={toggleTheme}>Th</button>
      </div>
    </header>
  );
}

function Dashboard({ setPage }) {
  const totalCost = traces.reduce((sum, trace) => sum + trace.cost, 0).toFixed(3);
  return (
    <>
      <PageHead title="Dashboard" action={<button className="secondary-button" type="button" onClick={() => setPage("traces")}>Open traces</button>} />
      <MetricCards items={[
        { label: "Executions", value: traces.length },
        { label: "Open incidents", value: incidents.filter((i) => i.status === "open").length },
        { label: "Total cost", value: `$${totalCost}` },
        { label: "Failed traces", value: traces.filter((trace) => trace.status === "failed").length }
      ]} />
      <div className="dashboard-grid">
        <article className="chart-card span-8">
          <h3>Trace latency</h3>
          <LineChart data={latencyTraceSeries} />
        </article>
        <article className="chart-card span-4">
          <h3>Token volume</h3>
          <BarChart data={dashboardRuns} />
        </article>
        <article className="chart-card span-6">
          <h3>Model latency</h3>
          <BarChart data={modelLatency} unit="ms" horizontal />
        </article>
        <article className="panel span-6">
          <h3>Reliability findings</h3>
          <div className="timeline">
            {findings.map((finding, index) => (
              <div className="timeline-item" key={finding}>
                <span className={`severity-chip ${index === 0 ? "critical" : "medium"}`}>{index === 0 ? "critical" : "watch"}</span>
                <span>{finding}</span>
                <span>{traces[index]?.id}</span>
              </div>
            ))}
          </div>
        </article>
      </div>
    </>
  );
}

function Traces({ openTrace, setSelectedTrace, setPage }) {
  return (
    <>
      <PageHead title="Traces" action={<button className="secondary-button" type="button" onClick={() => setPage("explorer")}>Trace explorer</button>} />
      <MetricCards items={[
        { label: "Total traces", value: traces.length },
        { label: "LLM calls", value: traces.reduce((sum, t) => sum + t.llm, 0) },
        { label: "Tool calls", value: traces.reduce((sum, t) => sum + t.tools, 0) },
        { label: "Failed", value: traces.filter((t) => t.status === "error").length }
      ]} />
      <div className="table-wrap">
        <table>
          <thead><tr><th>Trace</th><th>Agent</th><th>Root</th><th>Status</th><th>Duration</th><th>Tokens</th><th>Cost</th><th>Action</th></tr></thead>
          <tbody>
            {traces.map((trace) => (
              <tr key={trace.id} className="clickable" onClick={() => openTrace(trace)}>
                <td data-label="Trace">{trace.id}</td>
                <td data-label="Agent">{trace.agent}</td>
                <td data-label="Root">{trace.root}</td>
                <td data-label="Status"><StatusChip value={trace.status} /></td>
                <td data-label="Duration">{fmtMs(trace.duration)}</td>
                <td data-label="Tokens">{trace.tokens.toLocaleString()}</td>
                <td data-label="Cost">${trace.cost.toFixed(3)}</td>
                <td data-label="Action"><button className="view-button compact-button" type="button" onClick={(event) => { event.stopPropagation(); setSelectedTrace(trace); setPage("explorer"); }}>Explore</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}

function Explorer({ trace, setPage }) {
  return (
    <>
      <PageHead title="Trace explorer" action={<button className="secondary-button" type="button" onClick={() => setPage("traces")}>Back to traces</button>} />
      <MetricCards items={[
        { label: "Spans", value: trace.spans },
        { label: "LLM calls", value: trace.llm },
        { label: "Tool calls", value: trace.tools },
        { label: "Redactions", value: trace.id === "trc_a7d412" ? "2" : "1" }
      ]} />
      <article className="panel"><h3>{trace.agent} / {trace.root}</h3><TraceGraph trace={trace} /></article>
      <div className="split-grid" style={{ marginTop: 16 }}>
        <article className="panel">
          <h3>Timeline</h3>
          <div className="timeline">
            {trace.spansList.map((span) => (
              <div className="timeline-item" key={span.name}>
                <span>{span.name}</span>
                <span><StatusChip value={span.status} /> <span className="tiny-chip">{span.kind}</span></span>
                <span>{fmtMs(span.duration)}</span>
              </div>
            ))}
          </div>
        </article>
        <article className="panel">
          <h3>Risk signals</h3>
          <div className="timeline">
            <div className="timeline-item"><span className={`severity-chip ${trace.status === "error" ? "critical" : "medium"}`}>{trace.status === "error" ? "critical" : "captured"}</span><span>{trace.status === "error" ? "Model confidence block detected" : "Redaction and replay evidence captured"}</span><span>{trace.id}</span></div>
            <div className="timeline-item"><span className="severity-chip warning">watch</span><span>Cost and latency remain under current SLO target</span><span>{fmtMs(trace.duration)}</span></div>
          </div>
        </article>
      </div>
    </>
  );
}

function Incidents() {
  return (
    <>
      <PageHead title="Incidents" />
      <MetricCards items={[
        { label: "Open incidents", value: "2" },
        { label: "Critical", value: "1" },
        { label: "High", value: "1" },
        { label: "Medium", value: "1" }
      ]} />
      <div className="table-wrap">
        <table>
          <thead><tr><th>Severity</th><th>Status</th><th>Rule</th><th>Incident</th><th>Agent</th><th>Recommendation</th></tr></thead>
          <tbody>
            {incidents.map((incident) => (
              <tr key={incident.incident}>
                <td data-label="Severity"><StatusChip value={incident.severity} type="severity-chip" /></td>
                <td data-label="Status">{incident.status}</td>
                <td data-label="Rule">{incident.rule}</td>
                <td data-label="Incident">{incident.incident}</td>
                <td data-label="Agent">{incident.agent}</td>
                <td data-label="Recommendation">{incident.recommendation}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}

function SLOs({ setToast }) {
  return (
    <>
      <PageHead title="SLOs" />
      <MetricCards items={[
        { label: "Configured SLOs", value: slos.length },
        { label: "Enabled", value: slos.filter((s) => s.enabled).length },
        { label: "Success count", value: "3.8k" },
        { label: "Loop count", value: "2" }
      ]} />
      <div className="table-wrap">
        <table>
          <thead><tr><th>Metric</th><th>Target</th><th>Status</th><th>Updated</th><th>Action</th></tr></thead>
          <tbody>
            {slos.map((slo) => (
              <tr key={slo.metric}>
                <td data-label="Metric">{slo.metric}</td>
                <td data-label="Target"><div className="inline-row"><input defaultValue={slo.target} aria-label={`${slo.metric} target`} /><span>{slo.unit}</span></div></td>
                <td data-label="Status"><StatusChip value={slo.status} /></td>
                <td data-label="Updated">{slo.updated}</td>
                <td data-label="Action"><div className="inline-row"><label className="switch"><input type="checkbox" defaultChecked={slo.enabled} /><span className="slider"></span></label><button className="view-button" type="button" onClick={() => setToast("SLO target saved and audit event captured.")}>Save</button></div></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <article className="panel slo-panel">
        <div className="slo-panel-head"><h3>SLO health events</h3><span className="tiny-chip">{sloTimeline.length} rules evaluated</span></div>
        <div className="slo-timeline">
          {sloTimeline.map((event) => (
            <div className={`slo-event ${event.state}`} key={event.time}>
              <div className="slo-time">{event.time}</div>
              <div className={`slo-dot ${statusClass(event.state)}`}></div>
              <div className="slo-event-body">
                <div className="slo-event-title"><strong>{event.metric}</strong><StatusChip value={event.state} /></div>
                <div className="slo-event-type">{event.type}</div>
                <p>{event.observed}</p>
                <span className="tiny-chip">{event.evidence}</span>
              </div>
            </div>
          ))}
        </div>
      </article>
    </>
  );
}

function Governance({ openGovernanceReplay }) {
  return (
    <>
      <PageHead title="Governance" />
      <MetricCards items={[
        { label: "Audit events", value: auditRecords.length },
        { label: "Redactions", value: privacyEvidence.reduce((sum, item) => sum + item.maskedFields, 0) },
        { label: "Warnings", value: governanceWarnings.length },
        { label: "Replay events", value: governanceReplayEvents.length }
      ]} />
      <div className="governance-grid">
        <article className="evidence-panel span-12">
          <div className="governance-card-head"><h3>Warnings</h3><button className="secondary-button" type="button" onClick={openGovernanceReplay}>Open replay</button></div>
          {governanceWarnings.map((warning) => <div className="evidence-row" key={warning.message}><StatusChip value={warning.severity} type="severity-chip" /><span>{warning.message}</span><span>{warning.source}</span></div>)}
        </article>
        <article className="table-wrap span-12">
          <h3>Privacy and redaction evidence</h3>
          <table>
            <thead><tr><th>Field</th><th>Redaction applied</th><th>Redaction types</th><th>Capture policy</th><th>Masked fields</th></tr></thead>
            <tbody>
              {privacyEvidence.map((item) => (
                <tr key={item.field}><td data-label="Field">{item.field}</td><td data-label="Redaction applied"><StatusChip value="captured" /></td><td data-label="Redaction types">{item.types}</td><td data-label="Capture policy">{item.policy}</td><td data-label="Masked fields">{item.maskedFields}</td></tr>
              ))}
            </tbody>
          </table>
        </article>
        <article className="table-wrap span-12">
          <h3>Audit trail</h3>
          <table>
            <thead><tr><th>ID</th><th>Actor</th><th>Action</th><th>Agent</th><th>Execution</th><th>Metadata</th><th>Created</th></tr></thead>
            <tbody>
              {auditRecords.map((record) => (
                <tr key={record.id}><td data-label="ID">{record.id}</td><td data-label="Actor">{record.actor_user_id}</td><td data-label="Action">{record.action}</td><td data-label="Agent">{record.agent_id}</td><td data-label="Execution">{record.execution_id}</td><td data-label="Metadata">{record.metadata}</td><td data-label="Created">{record.created_at}</td></tr>
              ))}
            </tbody>
          </table>
        </article>
      </div>
    </>
  );
}

function CreateProject({ setToast }) {
  const [key, setKey] = useState("");
  return (
    <>
      <PageHead title="Create project" />
      <div className="project-grid">
        <article className="panel">
          <h3>Create project</h3>
          <form className="form-grid" onSubmit={(event) => { event.preventDefault(); setToast("AI Claims Automation created with project-level isolation."); }}>
            <label>Project name<input defaultValue="AI Claims Automation" /></label>
            <label>Description<textarea rows="5" defaultValue="Production claims agent observability with LangGraph traces, SLOs, and governance evidence." /></label>
            <button className="primary-button" type="submit">Create project</button>
          </form>
        </article>
        <article className="panel">
          <h3>Project API keys and SDK instructions</h3>
          <div className="key-row">
            <label style={{ flex: 1 }}>Key name<input defaultValue="production-sdk" /></label>
            <button className="primary-button" type="button" onClick={() => setKey(`ags_live_${Math.random().toString(36).slice(2, 5).toUpperCase()}_${Math.random().toString(36).slice(2)}`)}>Generate key</button>
          </div>
          <div className={`alert ${key ? "show" : ""}`}>{key ? `Generated key shown once: ${key}` : ""}</div>
          <div className="key-list">
            <div className="key-item"><span>ags_live_9KQ...</span><span>2026-07-05</span></div>
            <div className="key-item"><span>ags_live_2BM...</span><span>2026-07-03</span></div>
          </div>
          <pre className="code-panel">{`# Environment
AGENTSRE_PROJECT_ID=proj_ai_travel_ops
AGENTSRE_API_KEY=ags_live_********
AGENTSRE_ENDPOINT=http://localhost:8080/v1/executions

pip install -e ./sdk

import agentsre_sdk

agentsre_sdk.init(
    project_id="proj_ai_travel_ops",
    api_key=os.environ["AGENTSRE_API_KEY"],
    instrument_langgraph=True,
)`}</pre>
        </article>
      </div>
    </>
  );
}

function Drawer({ drawer, close }) {
  if (!drawer) return null;
  const item = drawer.item;
  return (
    <>
      <div className="drawer-shade open" onClick={close}></div>
      <aside className="trace-drawer open" aria-hidden="false">
        <div className="drawer-header">
          <div>
            <h3>{item.id || "Governance replay"}</h3>
            <span className="tiny-chip">governance.execution.full</span>
          </div>
          <button className="icon-button" type="button" aria-label="Close drawer" onClick={close}>x</button>
        </div>
        {drawer.kind === "trace" && <TraceDrawer trace={item} />}
        {drawer.kind === "governance" && <GovernanceDrawer />}
      </aside>
    </>
  );
}

function TraceDrawer({ trace }) {
  return (
    <div className="span-list">
      {trace.spansList.map((span, index) => (
        <article className="span-row expanded" key={`${span.name}-${index}`}>
          <div className="span-summary">
            <span className="tiny-chip">{index + 1}</span>
            <div><strong>{span.name}</strong><div className="span-meta"><StatusChip value={span.status} /><span className="tiny-chip">{span.kind}</span><span className="tiny-chip">{fmtMs(span.duration)}</span></div></div>
          </div>
          <div className="span-details">
            <div className="detail-cell"><b>Input</b>{span.input || span.arguments || "N/A"}</div>
            <div className="detail-cell"><b>Output</b>{span.output || span.toolOutput || span.error || "N/A"}</div>
          </div>
        </article>
      ))}
    </div>
  );
}

function GovernanceDrawer() {
  return (
    <div className="replay-timeline">
      {governanceReplayEvents.map((event) => (
        <div className="replay-event" key={event.time}>
          <div className="replay-time">{event.time}</div>
          <div className={`replay-dot ${statusClass(event.status)}`}></div>
          <div className="replay-body">
            <strong>{event.type}</strong>
            <p>{event.detail}</p>
            <span className="tiny-chip">{event.evidence}</span>
          </div>
        </div>
      ))}
    </div>
  );
}

export default function App() {
  const [authed, setAuthed] = useState(false);
  const [authMode, setAuthMode] = useState("login");
  const [theme, setTheme] = useState("theme-dark");
  const [page, setPage] = useState("dashboard");
  const [selectedTrace, setSelectedTrace] = useState(traces[0]);
  const [drawer, setDrawer] = useState(null);
  const [toast, setToast] = useState("");

  useEffect(() => {
    document.body.className = `${theme} ${authed ? "" : "auth-active"}`;
  }, [theme, authed]);

  useEffect(() => {
    if (!toast) return undefined;
    const timer = window.setTimeout(() => setToast(""), 2600);
    return () => window.clearTimeout(timer);
  }, [toast]);

  const pageContent = useMemo(() => {
    const props = { setPage, setToast };
    if (page === "dashboard") return <Dashboard {...props} />;
    if (page === "traces") return <Traces openTrace={(trace) => setDrawer({ kind: "trace", item: trace })} setSelectedTrace={setSelectedTrace} {...props} />;
    if (page === "explorer") return <Explorer trace={selectedTrace} {...props} />;
    if (page === "incidents") return <Incidents />;
    if (page === "slos") return <SLOs {...props} />;
    if (page === "governance") return <Governance openGovernanceReplay={() => setDrawer({ kind: "governance", item: {} })} />;
    return <CreateProject {...props} />;
  }, [page, selectedTrace]);

  const toggleTheme = () => setTheme((value) => (value === "theme-dark" ? "theme-light" : "theme-dark"));

  if (!authed) {
    return <AuthScreen mode={authMode} setMode={setAuthMode} onAuth={() => { setAuthed(true); setToast(`${authMode === "register" ? "Register" : "Login"} successful.`); }} toggleTheme={toggleTheme} />;
  }

  return (
    <div id="appShell" className="app-shell">
      <Sidebar page={page} setPage={setPage} logout={() => setAuthed(false)} />
      <section className="workspace">
        <Topbar setToast={setToast} toggleTheme={toggleTheme} />
        <div className="content">
          <section className="page active">{pageContent}</section>
        </div>
      </section>
      <Drawer drawer={drawer} close={() => setDrawer(null)} />
      <div className={`toast ${toast ? "show" : ""}`} aria-live="polite">{toast}</div>
    </div>
  );
}
