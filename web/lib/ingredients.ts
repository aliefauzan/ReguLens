// Parsing a pasted ingredients list.
//
// The rule that governs this file: guessing is worse than asking. A wrong
// amount silently becomes a wrong compliance verdict, so the parser only fills
// in a number when the text is unambiguous, and everything it produces is
// shown to the user for correction before anything is saved.

export type ParsedIngredient = {
  name: string;
  amount: string; // kept as a string: this is form state, not arithmetic
  unit: string;
  note?: string; // why a field was left blank, in words the user can act on
};

const UNIT_PATTERNS: { pattern: RegExp; unit: string }[] = [
  { pattern: /^%|^percent\b|^w\/w/, unit: "percent_w_w" },
  { pattern: /^mg\s*\/\s*kg|^mg per kg|^mg\/l/, unit: "mg_per_kg" },
  { pattern: /^ppm/, unit: "ppm" },
];

// A number followed by something that looks like a unit, anywhere in the chunk.
// The trailing lookahead rather than \b: "(0.08%)" ends on a bracket, and a
// word boundary never fires between two non-word characters.
const AMOUNT =
  /(\d+(?:[.,]\d+)?)\s*(%|percent|w\/w|mg\s*\/\s*kg|mg per kg|mg\/l|ppm|g\s*\/\s*kg|g)(?![a-z])/i;

/** Split a pasted label into individual ingredients. */
function chunk(text: string): string[] {
  return text
    // "Ingredients:" and its Indonesian equivalent are labels, not ingredients.
    .replace(/^\s*(ingredients?|komposisi|bahan)\s*[:.]/i, " ")
    .split(/[\n,;•·]+| and (?=[a-z])/i)
    .map((part) => part.trim())
    .filter(Boolean);
}

function cleanName(value: string): string {
  return value
    .replace(/^[-–—*\d.)\s]+/, "") // list bullets and numbering
    .replace(/\s{2,}/g, " ")
    .replace(/[.\s]+$/, "")
    .trim();
}

/**
 * Read a pasted ingredients list into rows.
 *
 * Deliberately conservative: a chunk longer than 60 characters is prose, not an
 * ingredient, and a unit this system cannot compare (g/kg) leaves the unit
 * blank with a note rather than being converted behind the user's back.
 */
export function parseIngredientList(text: string): ParsedIngredient[] {
  const seen = new Set<string>();
  const rows: ParsedIngredient[] = [];

  for (const raw of chunk(text)) {
    if (raw.length > 60) continue;

    const match = raw.match(AMOUNT);
    let name = cleanName(match ? raw.replace(match[0], " ") : raw);
    // A trailing "(" left behind by "sodium benzoate (0.08%)".
    name = cleanName(name.replace(/\(\s*\)|\(\s*$/g, ""));
    if (!name || name.length < 2) continue;

    const key = name.toLowerCase();
    if (seen.has(key)) continue;
    seen.add(key);

    if (!match) {
      rows.push({ name, amount: "", unit: "" });
      continue;
    }

    const rawUnit = match[2].toLowerCase().trim();
    const known = UNIT_PATTERNS.find((u) => u.pattern.test(rawUnit));
    if (known) {
      rows.push({ name, amount: match[1].replace(",", "."), unit: known.unit });
    } else {
      // We read a number but not a unit we can compare. Say so.
      rows.push({
        name,
        amount: match[1].replace(",", "."),
        unit: "",
        note: `Could not read the unit “${match[2]}” — please pick one.`,
      });
    }
  }

  return rows;
}
