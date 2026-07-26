import { jsPDF } from "jspdf";

const PAGE_WIDTH = 210;
const PAGE_HEIGHT = 297;
const MARGIN = 16;
const CONTENT_WIDTH = PAGE_WIDTH - (MARGIN * 2);

function text(value) {
  if (value === null || value === undefined || value === "") return "N/A";
  if (typeof value === "object") return "Structured payload omitted from report.";
  return String(value);
}

export function downloadIncidentReportPdf(report) {
  const pdf = new jsPDF({ unit: "mm", format: "a4" });
  let y = MARGIN;

  const ensure = (height = 12) => {
    if (y + height <= PAGE_HEIGHT - MARGIN) return;
    pdf.addPage();
    y = MARGIN;
    pageHeader();
  };

  const pageHeader = () => {
    pdf.setTextColor(42, 142, 222);
    pdf.setFont("helvetica", "bold");
    pdf.setFontSize(10);
    pdf.text("AgentSRE", MARGIN, y);
    pdf.setDrawColor(205, 215, 226);
    pdf.line(MARGIN, y + 3, PAGE_WIDTH - MARGIN, y + 3);
    y += 10;
  };

  const heading = (value) => {
    ensure(14);
    y += 3;
    pdf.setTextColor(24, 52, 75);
    pdf.setFont("helvetica", "bold");
    pdf.setFontSize(14);
    pdf.text(value, MARGIN, y);
    y += 6;
  };

  const paragraph = (value, options = {}) => {
    if (!value) return;
    pdf.setTextColor(55, 66, 81);
    pdf.setFont("helvetica", options.bold ? "bold" : "normal");
    pdf.setFontSize(options.size || 9.5);
    const lines = pdf.splitTextToSize(text(value), options.width || CONTENT_WIDTH);
    ensure((lines.length * 4.8) + 2);
    pdf.text(lines, options.x || MARGIN, y);
    y += (lines.length * 4.8) + 2;
  };

  const fields = (items) => {
    const visible = (items || []).filter((item) => item.value !== null && item.value !== undefined && item.value !== "");
    if (!visible.length) return;
    const labelWidth = 49;
    const valueWidth = CONTENT_WIDTH - labelWidth;
    const drawHeader = () => {
      ensure(9);
      pdf.setFillColor(220, 236, 245);
      pdf.setDrawColor(178, 199, 214);
      pdf.rect(MARGIN, y, CONTENT_WIDTH, 8, "FD");
      pdf.line(MARGIN + labelWidth, y, MARGIN + labelWidth, y + 8);
      pdf.setTextColor(35, 54, 70);
      pdf.setFont("helvetica", "bold");
      pdf.setFontSize(9);
      pdf.text("Field", MARGIN + 2, y + 5.2);
      pdf.text("Value", MARGIN + labelWidth + 2, y + 5.2);
      y += 8;
    };
    drawHeader();
    visible.forEach((item) => {
      pdf.setFontSize(9);
      const labelLines = pdf.splitTextToSize(text(item.label), labelWidth - 4);
      const valueLines = pdf.splitTextToSize(text(item.value), valueWidth - 4);
      const rowHeight = Math.max(8, Math.max(labelLines.length, valueLines.length) * 4.4 + 4);
      if (y + rowHeight > PAGE_HEIGHT - MARGIN) {
        pdf.addPage();
        y = MARGIN;
        pageHeader();
        drawHeader();
      }
      pdf.setFillColor(255, 255, 255);
      pdf.setDrawColor(190, 207, 220);
      pdf.rect(MARGIN, y, CONTENT_WIDTH, rowHeight, "FD");
      pdf.line(MARGIN + labelWidth, y, MARGIN + labelWidth, y + rowHeight);
      pdf.setTextColor(34, 45, 58);
      pdf.setFont("helvetica", "normal");
      pdf.text(labelLines, MARGIN + 2, y + 5.3);
      pdf.text(valueLines, MARGIN + labelWidth + 2, y + 5.3);
      y += rowHeight;
    });
    y += 2;
  };

  const bullets = (items) => {
    (items || []).forEach((item) => {
      ensure(10);
      const lines = pdf.splitTextToSize(text(item), CONTENT_WIDTH - 7);
      pdf.setTextColor(55, 66, 81);
      pdf.setFont("helvetica", "normal");
      pdf.setFontSize(9.5);
      pdf.text("-", MARGIN, y);
      pdf.text(lines, MARGIN + 5, y);
      y += (lines.length * 4.8) + 2;
    });
  };

  pageHeader();
  pdf.setTextColor(24, 38, 56);
  pdf.setFont("helvetica", "bold");
  pdf.setFontSize(20);
  pdf.text("AgentSRE Trace Incident Report", MARGIN, y);
  y += 8;

  heading("Report metadata");
  fields(report.metadataFields);
  heading("Incident identity");
  fields(report.identity);
  heading("Executive assessment");
  fields(report.executiveFields);
  heading("Detection evidence");
  fields(report.evidence);
  heading("Run context");
  fields(report.runFields);
  heading("Operational diagnostics");
  fields(report.operationalFields);

  if (report.sloFields?.length) {
    heading("SLO evidence");
    fields(report.sloFields);
  }

  heading("Root cause analysis");
  fields(report.rootCauseFields);

  if (report.failedTools?.length) {
    heading("Failed tool diagnostics");
    report.failedTools.forEach((tool, index) => {
      fields([{ label: `Tool ${index + 1}`, value: tool.name }, ...tool.fields]);
    });
  }

  if (report.llmDiagnostics?.length || report.grounding?.length) {
    heading("LLM and grounding diagnostics");
    report.llmDiagnostics.forEach((item, index) => fields([{ label: `LLM call ${index + 1}`, value: "Captured model diagnostics" }, ...item.fields]));
    if (report.grounding.length) fields(report.grounding.map((item, index) => ({ label: `Grounding finding ${index + 1}`, value: item })));
  }

  heading("Remediation and prevention");
  fields(report.remediationFields);

  if (report.timeline?.length) {
    heading("Significant event timeline");
    fields(report.timeline.map((event) => ({
      label: `Event ${event.sequence}`,
      value: [`Name: ${event.name}`, `Type: ${event.type}`, `Status: ${event.status}`, `Duration: ${event.duration}`, event.message ? `Detail: ${event.message}` : null].filter(Boolean).join("\n"),
    })));
  }

  const pageCount = pdf.getNumberOfPages();
  for (let page = 1; page <= pageCount; page += 1) {
    pdf.setPage(page);
    pdf.setTextColor(115, 128, 145);
    pdf.setFontSize(8);
    pdf.text("AgentSRE Trace Incident Report", MARGIN, PAGE_HEIGHT - 8);
    pdf.text(`Generated ${report.generatedAt} | Page ${page} of ${pageCount}`, PAGE_WIDTH - MARGIN, PAGE_HEIGHT - 8, { align: "right" });
  }

  const safeId = text(report.incidentId).replace(/[^a-zA-Z0-9_-]/g, "-");
  pdf.save(`agentsre-incident-${safeId}.pdf`);
}
