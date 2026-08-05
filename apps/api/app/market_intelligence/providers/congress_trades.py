"""U.S. Congress STOCK Act trade tracking from official House PTR disclosures."""

from __future__ import annotations

import io
import logging
import re
import zipfile
from datetime import UTC, datetime
from typing import Any
from xml.etree import ElementTree as ET

import httpx

from app.market_intelligence.freshness import build_freshness, utcnow
from app.market_intelligence.types import DataStatus

logger = logging.getLogger(__name__)

HOUSE_FD_ZIP = "https://disclosures-clerk.house.gov/public_disc/financial-pdfs/{year}FD.zip"
HOUSE_PTR_PDF = "https://disclosures-clerk.house.gov/public_disc/ptr-pdfs/{year}/{doc_id}.pdf"

_TICKER_RE = re.compile(
    r"(?P<name>[A-Za-z0-9][A-Za-z0-9\.\-&,'/\s]{2,80}?)\s*\((?P<ticker>[A-Z]{1,5}(?:\.[A-Z])?)\)\s*\[(?P<asset>[A-Z]{2})\]",
)
_TX_RE = re.compile(
    r"(?P<side>P|S|E)\s*(?:\((?P<sub>partial|full)\))?\s*"
    r"(?P<tx>\d{2}/\d{2}/\d{4})\s*(?P<notify>\d{2}/\d{2}/\d{4})?\s*"
    r"\$(?P<amount>[\d,]+(?:\s*-\s*\$?[\d,]+)?)",
    re.IGNORECASE,
)


def _parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%m/%d/%y"):
        try:
            return datetime.strptime(value.strip(), fmt).replace(tzinfo=UTC)
        except ValueError:
            continue
    return None


def _side_label(side: str, sub: str | None) -> str:
    base = {"P": "Purchase", "S": "Sale", "E": "Exchange"}.get(side.upper(), side)
    if sub:
        return f"{base} ({sub.lower()})"
    return base


async def _download_bytes(url: str) -> bytes | None:
    try:
        async with httpx.AsyncClient(timeout=45.0, follow_redirects=True) as client:
            res = await client.get(url, headers={"User-Agent": "AtlasCongressTracker/1.0"})
            if res.status_code != 200:
                logger.warning("Congress fetch %s -> %s", url, res.status_code)
                return None
            return res.content
    except Exception as exc:
        logger.warning("Congress fetch failed %s: %s", url, exc)
        return None


def _parse_house_index(xml_bytes: bytes, year: int) -> list[dict[str, Any]]:
    root = ET.fromstring(xml_bytes)
    filings: list[dict[str, Any]] = []
    for member in root.findall("Member"):
        filing_type = (member.findtext("FilingType") or "").strip()
        if filing_type != "P":
            continue
        doc_id = (member.findtext("DocID") or "").strip()
        if not doc_id:
            continue
        first = (member.findtext("First") or "").strip()
        last = (member.findtext("Last") or "").strip()
        prefix = (member.findtext("Prefix") or "").strip()
        name = " ".join(p for p in [prefix, first, last] if p)
        state = (member.findtext("StateDst") or "").strip()
        filing_date = _parse_date(member.findtext("FilingDate"))
        filings.append(
            {
                "chamber": "House",
                "member": name,
                "state_district": state,
                "filing_date": filing_date.date().isoformat() if filing_date else None,
                "doc_id": doc_id,
                "year": year,
                "ptr_url": HOUSE_PTR_PDF.format(year=year, doc_id=doc_id),
            }
        )
    filings.sort(key=lambda f: f.get("filing_date") or "", reverse=True)
    return filings


def _extract_trades_from_pdf(pdf_bytes: bytes, filing: dict[str, Any]) -> list[dict[str, Any]]:
    try:
        from pypdf import PdfReader
    except Exception as exc:
        logger.warning("pypdf unavailable: %s", exc)
        return []

    try:
        reader = PdfReader(io.BytesIO(pdf_bytes))
        text = "\n".join((page.extract_text() or "") for page in reader.pages)
    except Exception as exc:
        logger.debug("PTR PDF parse failed %s: %s", filing.get("doc_id"), exc)
        return []

    # Normalize odd null-padded OCR-ish characters from some PTRs
    text = text.replace("\x00", "")
    trades: list[dict[str, Any]] = []

    # Prefer structured ticker blocks
    for match in _TICKER_RE.finditer(text):
        window = text[match.start() : match.start() + 220]
        tx = _TX_RE.search(window) or _TX_RE.search(text[match.end() : match.end() + 160])
        if not tx:
            # Still record ticker presence from filing description lines
            trades.append(
                {
                    **filing,
                    "ticker": match.group("ticker").replace(".", "-")
                    if match.group("ticker") == "BRK.B"
                    else match.group("ticker"),
                    "asset_name": match.group("name").strip(),
                    "asset_type": match.group("asset"),
                    "transaction_type": "Unknown",
                    "transaction_date": None,
                    "amount": None,
                    "data_status": DataStatus.DELAYED.value,
                }
            )
            continue
        ticker = match.group("ticker")
        if ticker == "BRK.B":
            ticker = "BRK-B"
        trades.append(
            {
                **filing,
                "ticker": ticker,
                "asset_name": match.group("name").strip(),
                "asset_type": match.group("asset"),
                "transaction_type": _side_label(tx.group("side"), tx.group("sub")),
                "transaction_date": (
                    _parse_date(tx.group("tx")).date().isoformat() if _parse_date(tx.group("tx")) else None
                ),
                "notification_date": (
                    _parse_date(tx.group("notify")).date().isoformat()
                    if tx.group("notify") and _parse_date(tx.group("notify"))
                    else None
                ),
                "amount": f"${tx.group('amount').replace(' ', '').replace(chr(10), '').replace(chr(13), '')}",
                "data_status": DataStatus.DELAYED.value,
            }
        )

    # Deduplicate identical ticker+date+type rows
    seen: set[tuple[Any, ...]] = set()
    unique: list[dict[str, Any]] = []
    for t in trades:
        key = (t.get("ticker"), t.get("transaction_date"), t.get("transaction_type"), t.get("amount"))
        if key in seen:
            continue
        seen.add(key)
        unique.append(t)
    return unique


async def fetch_congress_trades(*, limit: int = 40, max_filings: int = 12) -> dict[str, Any]:
    """
    Public STOCK Act tracker:
    - House Periodic Transaction Reports from the Clerk of the House (official)
    - Parses recent PTR PDFs for tickers, side, amount bands

    Disclosures can lag trades by up to ~45 days by law. Always labelled delayed.
    """
    year = utcnow().year
    filings: list[dict[str, Any]] = []
    for y in (year, year - 1):
        blob = await _download_bytes(HOUSE_FD_ZIP.format(year=y))
        if not blob:
            continue
        try:
            with zipfile.ZipFile(io.BytesIO(blob)) as zf:
                xml_name = next((n for n in zf.namelist() if n.lower().endswith(".xml")), None)
                if not xml_name:
                    continue
                filings.extend(_parse_house_index(zf.read(xml_name), y))
        except Exception as exc:
            logger.warning("House FD zip parse failed for %s: %s", y, exc)

    filings = sorted(filings, key=lambda f: f.get("filing_date") or "", reverse=True)
    trades: list[dict[str, Any]] = []
    for filing in filings[:max_filings]:
        pdf = await _download_bytes(str(filing["ptr_url"]))
        if not pdf:
            # Still surface the filing itself for transparency
            trades.append(
                {
                    **filing,
                    "ticker": None,
                    "transaction_type": "PTR filed",
                    "amount": None,
                    "note": "Open the official PTR PDF for line-item trades.",
                    "data_status": DataStatus.DELAYED.value,
                }
            )
            continue
        parsed = _extract_trades_from_pdf(pdf, filing)
        if parsed:
            trades.extend(parsed)
        else:
            trades.append(
                {
                    **filing,
                    "ticker": None,
                    "transaction_type": "PTR filed",
                    "amount": None,
                    "note": "PDF indexed; text extraction incomplete — use official link.",
                    "data_status": DataStatus.DELAYED.value,
                }
            )
        if len(trades) >= limit:
            break

    trades = trades[:limit]
    latest = None
    for t in trades:
        d = t.get("filing_date") or t.get("transaction_date")
        if d and (latest is None or d > latest):
            latest = d
    try:
        data_ts = datetime.strptime(latest, "%Y-%m-%d").replace(tzinfo=UTC) if latest else None
    except Exception:
        data_ts = None

    return {
        "items": trades,
        "count": len(trades),
        "filings_indexed": len(filings),
        "freshness": build_freshness(
            provider_name="U.S. House Clerk PTR (STOCK Act)",
            data_timestamp=data_ts or utcnow(),
            data_status=DataStatus.DELAYED if trades else DataStatus.PARTIAL,
            missing_fields=[] if trades else ["house_ptr"],
        ).to_dict(),
        "disclaimer": (
            "Public STOCK Act disclosures from the Clerk of the House. Filings may lag the "
            "actual trade date by up to ~45 days. Atlas does not infer insider intent — this is "
            "a transparency log of disclosed transactions."
        ),
        "source": "house_clerk_ptr",
        "available": bool(trades),
    }
