"use client";

/**
 * Print, or save as PDF — the browser already does both, and the print dialog
 * on every desktop OS offers "Save as PDF" in the same menu. A PDF generator
 * as a dependency would buy a slightly nicer margin and a new package to keep
 * alive. The `@media print` rules in globals.css do the actual work.
 */
export default function PrintButton() {
  return (
    <button
      type="button"
      className="btn btn-secondary btn-small no-print"
      onClick={() => window.print()}
      data-testid="print-plan"
    >
      Print or save as PDF
    </button>
  );
}
