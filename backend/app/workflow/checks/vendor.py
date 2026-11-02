import re

from app.workflow.checks.base import CheckContext, CheckResult, passed, reject, review

_GSTIN = re.compile(r"\d{2}[A-Z]{5}\d{4}[A-Z][0-9A-Z]Z[0-9A-Z]")
_COMPANY_NOISE = {"PVT", "PRIVATE", "LTD", "LIMITED", "LLC", "INC", "CO", "CORP", "THE", "AND"}


def company_words(name: str | None) -> set[str]:
    words = re.findall(r"[A-Z0-9]+", (name or "").upper())
    return set(words) - _COMPANY_NOISE


class VendorCheck:
    """The vendor's GSTIN settles who sent the invoice when the PO records one.
    Without it, rejecting needs both the LLM and the names to disagree, because
    a wrong rejection of a real supplier is hard to notice."""

    name = "vendor"

    def run(self, context: CheckContext) -> CheckResult:
        expected = gstins_in(" ".join(str(value) for value in context.order.fields.values()))
        printed = gstins_in(context.invoice_text)
        if expected and printed:
            return self._by_gstin(context, expected, printed)
        return self._by_name(context)

    def _by_gstin(
        self, context: CheckContext, expected: set[str], printed: set[str]
    ) -> CheckResult:
        listed = ", ".join(sorted(expected))
        if any(_same_gstin(a, b) for a in expected for b in printed):
            return passed(self, f"The vendor's GSTIN {listed} is on the invoice.")
        verification = context.verification
        invoice_vendor, po_vendor = verification.invoice.vendor, verification.purchase_order.vendor
        names = f"{invoice_vendor} / {po_vendor}"
        if company_words(invoice_vendor) & company_words(po_vendor):
            return review(
                self,
                f"The vendor's name matches ({names}), but the PO's GSTIN {listed} "
                "is not on the invoice.",
            )
        return reject(
            self,
            f"The vendor does not match the PO: {names}, and the PO's GSTIN is not on the invoice.",
        )

    def _by_name(self, context: CheckContext) -> CheckResult:
        verification = context.verification
        invoice_vendor = company_words(verification.invoice.vendor)
        po_vendor = company_words(verification.purchase_order.vendor)
        if not invoice_vendor or not po_vendor:
            return review(self, "The vendor could not be compared with the PO.")

        names = f"{verification.invoice.vendor} / {verification.purchase_order.vendor}"
        shared = invoice_vendor & po_vendor
        if invoice_vendor == po_vendor or (shared and verification.vendor_match == "yes"):
            return passed(self, f"The vendor matches: {names}.")
        if not shared and verification.vendor_match == "no":
            return reject(self, f"The vendor does not match the PO: {names}.")
        return review(self, f"The vendor match is unclear: {names}.")


def gstins_in(text: str) -> set[str]:
    """GSTINs in the text, read without spaces because scans sometimes split them."""
    return set(_GSTIN.findall("".join(text.split()).upper()))


def _same_gstin(a: str, b: str) -> bool:
    """Allows two misread characters, which OCR makes on poor scans. A different
    business's GSTIN differs in far more places."""
    return sum(x != y for x, y in zip(a, b, strict=True)) <= 2
