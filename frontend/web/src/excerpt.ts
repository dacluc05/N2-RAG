interface Match {
  start: number;
  end: number;
}

function normalized(text: string) {
  let value = "";
  const offsets: number[] = [];
  for (let i = 0; i < text.length; i++) {
    const char = text[i];
    if (/[\s\u00ad\u200b-\u200d\u2060\ufeff]/u.test(char)) continue;
    value += char.replace(/[’‘]/g, "'").replace(/[“”]/g, '"').toLowerCase();
    offsets.push(i);
  }
  return { value, offsets };
}

export function matchExcerpt(text: string, quote?: string): Match | undefined {
  if (!quote?.trim()) return;
  const exact = text.indexOf(quote.trim());
  if (exact >= 0) return { start: exact, end: exact + quote.trim().length };
  const original = normalized(text);
  const target = normalized(quote).value;
  const index = target ? original.value.indexOf(target) : -1;
  if (index >= 0) {
    return {
      start: original.offsets[index],
      end: original.offsets[index + target.length - 1] + 1,
    };
  }
}

function encodeTerm(text: string) {
  return encodeURIComponent(text).replace(
    /[-!'()*]/g,
    (char) => "%" + char.charCodeAt(0).toString(16).toUpperCase(),
  );
}

function anchorTerms(passage: string) {
  // SEC table exports delimit cells with pipes. A fragment must match one rendered cell.
  const tableLabel = passage.split(/\r?\n/).filter(line => /\s\|\s/.test(line))
    .map(line => line.split("|")[0].trim())
    .find(label => /^[\p{L}]/u.test(label) && label.split(/\s+/).length >= 2);
  if (tableLabel) return [tableLabel];
  if (/\s\|\s/.test(passage)) return [];
  // Text Fragment terms must fit within one block of the source page.
  const lines = passage
    .split(/[\r\n]+/)
    .map((line) => line.trim().split(/\s+/).filter(Boolean));
  const words =
    lines.find((line) => line.length >= 6) ??
    lines.reduce((a, b) => (b.length > a.length ? b : a), []);
  if (words.length < 3) return [];
  const full = words.join(" ");
  if (words.length <= 20 && full.length <= 200) return [full];
  return [words.slice(0, 9).join(" "), words.slice(-9).join(" ")];
}

export function sourceTarget(
  url: string,
  kind: string,
  locator: string,
  passage: string,
) {
  const page = /^trang\s+(\d+)/i.exec(locator)?.[1];
  const pdf =
    !!page ||
    kind.toLowerCase() === "pdf" ||
    new URL(url).pathname.toLowerCase().endsWith(".pdf");
  const document = url.split("#")[0];
  if (pdf && page)
    return { href: document + "#page=" + page, mode: "page" as const };
  const terms = pdf || kind === "xbrl" || kind === "market" ? [] : anchorTerms(passage);
  if (terms.length)
    return {
      href: url.split(":~:")[0] + (url.includes("#") ? "" : "#") + ":~:text=" + terms.map(encodeTerm).join(","),
      mode: "text" as const,
    };
  return { href: url, mode: "document" as const };
}
