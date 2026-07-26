const EXCEPTION_PATTERN = /\b((?:[A-Z][A-Za-z0-9_.]*)?(?:Error|Exception))\b/;
const ERROR_PREFIX_PATTERN = /^(?:(?:[A-Z][A-Za-z0-9_.]*)?(?:Error|Exception)\s*:\s*)+/;
const TRACEBACK_PATTERN = /\bTraceback\s*\(most recent call last\):/i;

function trimMessage(value) {
  return String(value || "")
    .replace(/^['"]|['"]$/g, "")
    .replace(/\\n/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

export function compactError(value, maxLength = 180) {
  if (value === undefined || value === null || value === "") return value;
  const original = String(value).trim();
  const tracebackIndex = original.search(TRACEBACK_PATTERN);
  const withoutTraceback = tracebackIndex >= 0 ? original.slice(0, tracebackIndex).trim() : original;
  const type = withoutTraceback.match(EXCEPTION_PATTERN)?.[1]
    || original.match(EXCEPTION_PATTERN)?.[1]
    || "Error";

  const quotedWrapper = withoutTraceback.match(/\b(?:[A-Z][A-Za-z0-9_.]*)?(?:Error|Exception)\s*\(\s*(['"])([\s\S]*?)\1\s*\)/);
  const colonMessage = withoutTraceback.match(/\b(?:[A-Z][A-Za-z0-9_.]*)?(?:Error|Exception)\s*:\s*([^\r\n]+)/);
  let message = trimMessage(quotedWrapper?.[2] || colonMessage?.[1] || "");

  if (!message) {
    message = trimMessage(withoutTraceback.replace(EXCEPTION_PATTERN, "").replace(/^\s*[:(]+|[)'"]+$/g, ""));
  }
  message = trimMessage(message.replace(ERROR_PREFIX_PATTERN, ""));

  let result = message ? `${type}: ${message}` : type;
  if (result.length > maxLength) {
    const code = original.match(/\b[A-Z]{2,12}-\d{2,}\b/)?.[0];
    const suffix = code && !result.slice(0, maxLength).includes(code) ? ` (${code})` : "";
    result = `${result.slice(0, Math.max(1, maxLength - suffix.length - 3)).trimEnd()}...${suffix}`;
  }
  return result;
}

export function compactStructuredErrors(value) {
  if (Array.isArray(value)) return value.map(compactStructuredErrors);
  if (value && typeof value === "object") {
    return Object.fromEntries(Object.entries(value).map(([key, item]) => [key, compactStructuredErrors(item)]));
  }
  if (typeof value === "string" && (TRACEBACK_PATTERN.test(value) || EXCEPTION_PATTERN.test(value))) {
    return compactError(value);
  }
  return value;
}
