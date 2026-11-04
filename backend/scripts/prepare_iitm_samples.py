"""Builds realistic IIT Madras purchase orders and vendor invoices for testing by hand.

Run from backend/: uv run python scripts/prepare_iitm_samples.py
PDFs go to tests/fixtures/iitm/correct and tests/fixtures/iitm/incorrect, with a
README saying what each one tests. Upload the correct folder first, because some
incorrect invoices depend on what came before. POs that already exist are left alone.

All vendors are fictional, and every GSTIN, PAN and bank account is a placeholder.
"""

import argparse
import asyncio
import sys
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from pathlib import Path

import cv2
import numpy as np
import pymupdf
from pymongo import AsyncMongoClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.config import settings  # noqa: E402
from app.domain.errors import DuplicatePurchaseOrderError  # noqa: E402
from app.domain.models import PurchaseOrder  # noqa: E402
from app.infrastructure.purchase_order_repository import (  # noqa: E402
    MongoPurchaseOrderRepository,
)

OUTPUT = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "iitm"
A4 = (595, 842)
NAVY = (0.09, 0.2, 0.38)
GREY = (0.93, 0.94, 0.96)
BUYER = "Indian Institute of Technology Madras"
BUYER_ADDRESS = "IIT P.O., Chennai, Tamil Nadu 600036"
SPECIMEN = "Sample document created for software testing."


@dataclass(frozen=True)
class Vendor:
    name: str
    address: str
    gstin: str
    phone: str


@dataclass(frozen=True)
class Item:
    description: str
    hsn: str
    quantity: int
    rate: float
    unit: str | None = None

    @property
    def amount(self) -> float:
        return self.quantity * self.rate


@dataclass(frozen=True)
class Order:
    number: str
    vendor: Vendor
    department: str
    indent: str
    date: str
    items: list[Item]
    freight: float = 0
    gst_percent: float = 18

    @property
    def subtotal(self) -> float:
        return sum(item.amount for item in self.items)

    @property
    def gst(self) -> float:
        return round(self.subtotal * self.gst_percent / 100, 2)

    @property
    def total(self) -> float:
        return round(self.subtotal + self.gst + self.freight, 2)

    def as_document(self) -> dict:
        return {
            "po_number": self.number,
            "fields": {
                "organisation": BUYER,
                "department": self.department,
                "indent_no": self.indent,
                "po_date": self.date,
                "vendor": self.vendor.name,
                "vendor_gstin": self.vendor.gstin,
                "delivery_to": f"{self.department}, {BUYER}, {BUYER_ADDRESS}",
                "payment_terms": "Within 30 days of receipt and inspection",
                "currency": "INR",
                "line_items": [
                    {
                        "description": item.description,
                        "hsn": item.hsn,
                        "qty": item.quantity,
                        **({"unit": item.unit} if item.unit else {}),
                        "unit_price": item.rate,
                        "amount": item.amount,
                    }
                    for item in self.items
                ],
                "freight": self.freight,
                "gst_percent": self.gst_percent,
                "sub_total": self.subtotal,
                "gst_amount": self.gst,
                "grand_total": self.total,
            },
        }


@dataclass(frozen=True)
class Invoice:
    order: Order
    number: str | None
    date: str
    reference: str | None
    layout: str = "standard"
    vendor: Vendor | None = None
    items: list[Item] | None = None
    printed_subtotal: float | None = None
    currency: str = "INR"
    items_on_first_page: int | None = None

    @property
    def seller(self) -> Vendor:
        return self.vendor or self.order.vendor

    @property
    def lines(self) -> list[Item]:
        return self.items if self.items is not None else self.order.items

    @property
    def subtotal(self) -> float:
        if self.printed_subtotal is not None:
            return self.printed_subtotal
        return sum(item.amount for item in self.lines)

    @property
    def half_gst(self) -> float:
        return round(self.subtotal * self.order.gst_percent / 200, 2)

    @property
    def total(self) -> float:
        freight = self.order.freight if self.items is None else 0
        return round(self.subtotal + 2 * self.half_gst + freight, 2)


def money(amount: float) -> str:
    """Indian digit grouping, as printed on real invoices: 3,17,420.00"""
    whole, cents = f"{amount:.2f}".split(".")
    if len(whole) <= 3:
        return f"{whole}.{cents}"
    head, tail = whole[:-3], whole[-3:]
    groups = []
    while head:
        groups.insert(0, head[-2:])
        head = head[:-2]
    return f"{','.join(groups)},{tail}.{cents}"


ONES = (
    "Zero One Two Three Four Five Six Seven Eight Nine Ten Eleven Twelve Thirteen "
    "Fourteen Fifteen Sixteen Seventeen Eighteen Nineteen"
).split()
TENS = "Zero Ten Twenty Thirty Forty Fifty Sixty Seventy Eighty Ninety".split()


def under_thousand(value: int) -> str:
    words = []
    if value >= 100:
        words += [ONES[value // 100], "Hundred"]
        value %= 100
    if value >= 20:
        words.append(TENS[value // 10])
        value %= 10
    if value:
        words.append(ONES[value])
    return " ".join(words)


def in_words(amount: float) -> str:
    value = int(amount)
    words = []
    for size, name in ((100000, "Lakh"), (1000, "Thousand")):
        if value >= size:
            words += [under_thousand(value // size), name]
            value %= size
    if value:
        words.append(under_thousand(value))
    return f"Rupees {' '.join(words)} Only"


def right(page, x: float, y: float, text: str, font: str, size: float = 9.5) -> None:
    width = pymupdf.get_text_length(text, fontname=font, fontsize=size)
    page.insert_text((x - width, y), text, fontname=font, fontsize=size)


def draw_table(page, items: list[Item], y: float, start: int, font: str, bold: str) -> float:
    page.draw_rect((42, y - 13, 553, y + 5), color=None, fill=GREY)
    for x, heading in ((46, "S.No"), (76, "Description of Goods / Services"), (320, "HSN/SAC")):
        page.insert_text((x, y), heading, fontname=bold, fontsize=9)
    right(page, 408, y, "Qty", bold, 9)
    right(page, 478, y, "Rate", bold, 9)
    right(page, 549, y, "Amount", bold, 9)
    for index, item in enumerate(items, start=start):
        y += 19
        page.insert_text((46, y), str(index), fontname=font, fontsize=9.5)
        page.insert_text((76, y), item.description, fontname=font, fontsize=9.5)
        page.insert_text((320, y), item.hsn, fontname=font, fontsize=9.5)
        right(page, 408, y, f"{item.quantity} {item.unit}" if item.unit else str(item.quantity), font)
        right(page, 478, y, money(item.rate), font)
        right(page, 549, y, money(item.amount), font)
        page.draw_line((42, y + 6), (553, y + 6), color=(0.8, 0.8, 0.8), width=0.4)
    return y


def draw_totals(page, invoice: Invoice, y: float, font: str, bold: str) -> None:
    half = invoice.order.gst_percent / 2
    rows = [("Taxable Value", invoice.subtotal)]
    if invoice.order.freight and invoice.items is None:
        rows.append(("Freight", invoice.order.freight))
    rows += [(f"CGST @ {half:g}%", invoice.half_gst), (f"SGST @ {half:g}%", invoice.half_gst)]
    for label, amount in rows:
        y += 17
        page.insert_text((360, y), label, fontname=font, fontsize=9.5)
        right(page, 549, y, money(amount), font)
    y += 21
    page.draw_line((355, y - 13), (553, y - 13), width=0.8)
    page.insert_text((360, y), f"Total Amount ({invoice.currency})", fontname=bold, fontsize=10.5)
    right(page, 549, y, money(invoice.total), bold, 10.5)

    page.insert_text((46, y + 26), f"Amount in words: {in_words(invoice.total)}", fontname=font, fontsize=9)
    page.insert_text((46, y + 56), "Bank: State Bank of India, Adyar Branch", fontname=font, fontsize=9)
    page.insert_text((46, y + 69), "A/c No: 00000000000  IFSC: SBIN0000000", fontname=font, fontsize=9)
    page.insert_text((46, y + 82), "Payment within 30 days of acceptance.", fontname=font, fontsize=9)
    page.insert_text((400, y + 56), f"For {invoice.seller.name}"[:34], fontname=font, fontsize=9)
    page.insert_text((430, y + 96), "Authorised Signatory", fontname=font, fontsize=9)


def draw_parties(page, invoice: Invoice, y: float, font: str, bold: str) -> float:
    order = invoice.order
    page.insert_text((46, y), "Bill To", fontname=bold, fontsize=9.5)
    page.insert_text((46, y + 14), BUYER, fontname=font, fontsize=9.5)
    page.insert_text((46, y + 28), order.department, fontname=font, fontsize=9.5)
    page.insert_text((46, y + 42), BUYER_ADDRESS, fontname=font, fontsize=9.5)
    rows = []
    if invoice.number:
        rows.append(f"Invoice No: {invoice.number}")
    if invoice.date:
        rows.append(f"Invoice Date: {invoice.date}")
    if invoice.reference:
        rows.append(invoice.reference)
    rows.append("Place of Supply: Tamil Nadu (33)")
    for index, row in enumerate(rows):
        page.insert_text((330, y + index * 14), row, fontname=font, fontsize=9.5)
    return y + 74


def draw_header(page, invoice: Invoice) -> tuple[float, str, str]:
    seller = invoice.seller
    if invoice.layout == "band":
        page.draw_rect((0, 0, A4[0], 86), color=None, fill=NAVY)
        white = (1, 1, 1)
        page.insert_text((44, 38), seller.name, fontname="hebo", fontsize=16, color=white)
        page.insert_text((44, 54), seller.address, fontname="helv", fontsize=8.5, color=white)
        page.insert_text(
            (44, 67), f"GSTIN: {seller.gstin}  Ph: {seller.phone}", fontname="helv", fontsize=8.5, color=white
        )
        page.insert_text((440, 40), "TAX INVOICE", fontname="hebo", fontsize=13, color=white)
        return 112, "helv", "hebo"
    if invoice.layout == "typed":
        page.draw_rect((42, 36, 553, 104), color=(0, 0, 0), width=1)
        page.insert_text((50, 56), seller.name.upper(), fontname="cobo", fontsize=12)
        page.insert_text((50, 72), seller.address, fontname="cour", fontsize=8.5)
        page.insert_text((50, 86), f"GSTIN: {seller.gstin}  Ph: {seller.phone}", fontname="cour", fontsize=8.5)
        page.insert_text((240, 124), "TAX INVOICE", fontname="cobo", fontsize=12)
        return 146, "cour", "cobo"
    page.insert_text((44, 52), seller.name, fontname="tibo", fontsize=18)
    page.insert_text((44, 68), seller.address, fontname="tiro", fontsize=9.5)
    page.insert_text((44, 81), f"GSTIN: {seller.gstin}   Ph: {seller.phone}", fontname="tiro", fontsize=9.5)
    right(page, 553, 52, "TAX INVOICE", "tibo", 15)
    page.draw_line((42, 92), (553, 92), width=1.2)
    return 114, "tiro", "tibo"


def native(invoice: Invoice) -> pymupdf.Document:
    document = pymupdf.open()
    page = document.new_page(width=A4[0], height=A4[1])
    y, font, bold = draw_header(page, invoice)
    y = draw_parties(page, invoice, y, font, bold)
    split = invoice.items_on_first_page
    shown = invoice.lines[:split] if split else invoice.lines
    end = draw_table(page, shown, y + 16, 1, font, bold)
    if split:
        page.insert_text((46, end + 28), "Continued on next page", fontname=font, fontsize=9)
        page.insert_text((46, 815), SPECIMEN, fontname=font, fontsize=7)
        page = document.new_page(width=A4[0], height=A4[1])
        page.insert_text((44, 54), f"{invoice.seller.name}: Invoice {invoice.number}, page 2", fontname=bold, fontsize=10)
        end = draw_table(page, invoice.lines[split:], 84, split + 1, font, bold)
    draw_totals(page, invoice, end + 10, font, bold)
    page.insert_text((46, 815), SPECIMEN, fontname=font, fontsize=7)
    return document


def pixels(page: pymupdf.Page, dpi: int) -> np.ndarray:
    pixmap = page.get_pixmap(dpi=dpi, colorspace=pymupdf.csRGB, alpha=False)
    return np.frombuffer(pixmap.samples, dtype=np.uint8).reshape(pixmap.height, pixmap.width, 3).copy()


def add_noise(array: np.ndarray, rng: np.random.Generator, spread: float) -> np.ndarray:
    noisy = array.astype(np.float32) + rng.normal(0, spread, array.shape)
    return np.clip(noisy, 0, 255).astype(np.uint8)


def clean(page, rng) -> tuple[np.ndarray, int]:
    return add_noise((pixels(page, 220) * 0.98).astype(np.uint8), rng, 2), 88


def skewed(page, rng) -> tuple[np.ndarray, int]:
    array = pixels(page, 200)
    height, width, _ = array.shape
    turn = cv2.getRotationMatrix2D((width / 2, height / 2), 3.5, 1)
    return add_noise(cv2.warpAffine(array, turn, (width, height), borderValue=(248, 248, 246)), rng, 4), 82


def blurry(page, rng) -> tuple[np.ndarray, int]:
    return add_noise(cv2.GaussianBlur(pixels(page, 180), (7, 7), 0), rng, 3), 78


def noisy(page, rng) -> tuple[np.ndarray, int]:
    array = add_noise((cv2.GaussianBlur(pixels(page, 170), (3, 3), 0) * 0.93).astype(np.uint8), rng, 15)
    specks = rng.random(array.shape[:2])
    array[specks < 0.002] = 30
    return array, 62


def fax(page, rng) -> tuple[np.ndarray, int]:
    grey = cv2.cvtColor(pixels(page, 130), cv2.COLOR_RGB2GRAY)
    binary = np.where(grey < 170, 0, 255).astype(np.uint8)
    specks = rng.random(binary.shape)
    binary[specks < 0.002] = 0
    binary = cv2.resize(binary, None, fx=2, fy=2, interpolation=cv2.INTER_NEAREST)
    return cv2.cvtColor(binary, cv2.COLOR_GRAY2RGB), 82


def faint(page, rng) -> tuple[np.ndarray, int]:
    pale = 255 - (255 - pixels(page, 200).astype(np.float32)) * 0.4
    return add_noise((pale * 0.97).astype(np.uint8), rng, 3), 85


def sideways(page, rng) -> tuple[np.ndarray, int]:
    return add_noise(np.rot90(pixels(page, 200)).copy(), rng, 3), 82


def phone(page, rng) -> tuple[np.ndarray, int]:
    sheet = pixels(page, 210)
    height, width, _ = sheet.shape
    source = np.float32([[0, 0], [width, 0], [width, height], [0, height]])
    target = np.float32(
        [
            [width * 0.05, height * 0.03],
            [width * 0.95, height * 0.045],
            [width * 0.985, height * 0.97],
            [width * 0.02, height * 0.955],
        ]
    )
    warp = cv2.getPerspectiveTransform(source, target)
    photo = cv2.warpPerspective(sheet, warp, (width, height), borderValue=(92, 84, 76))
    lit = np.clip(photo * np.linspace(0.78, 1.05, width)[None, :, None] * np.linspace(1.03, 0.88, height)[:, None, None], 0, 255)
    return add_noise(cv2.GaussianBlur(lit.astype(np.uint8), (3, 3), 0), rng, 6), 76


def to_jpeg(array: np.ndarray, quality: int) -> bytes:
    height, width, _ = array.shape
    return pymupdf.Pixmap(pymupdf.csRGB, width, height, array.tobytes(), False).tobytes(
        "jpeg", jpg_quality=quality
    )


def scanned(treatment: Callable, seed: int) -> Callable[[Invoice], bytes]:
    def build(invoice: Invoice) -> bytes:
        rng = np.random.default_rng(seed)
        output = pymupdf.open()
        for page in native(invoice):
            array, quality = treatment(page, rng)
            height, width, _ = array.shape
            size = (A4[1], A4[0]) if width > height else A4
            sheet = output.new_page(width=size[0], height=size[1])
            sheet.insert_image(sheet.rect, stream=to_jpeg(array, quality))
        return output.tobytes(deflate=True)

    return build


def digital(invoice: Invoice) -> bytes:
    return native(invoice).tobytes(deflate=True)


def locked(invoice: Invoice) -> bytes:
    return native(invoice).tobytes(
        encryption=pymupdf.PDF_ENCRYPT_AES_256, user_pw="iitm2026", owner_pw="owner2026"
    )


KAVERI = Vendor("Kaveri Scientific Instruments Pvt Ltd", "14, Sardar Patel Road, Guindy, Chennai 600032", "33AAACK0000A1Z5", "044 4000 1101")
CORO = Vendor("Coromandel Lab Supplies", "7, Anna Salai, Teynampet, Chennai 600018", "33AAAFC0000B1Z3", "044 4000 1102")
ADYAR = Vendor("Adyar Office Systems", "22, LB Road, Adyar, Chennai 600020", "33AAAFA0000C1Z9", "044 4000 1103")
NOVA = Vendor("TechNova Computing Pvt Ltd", "3rd Floor, OMR, Thoraipakkam, Chennai 600097", "33AAACT0000D1Z7", "044 4000 1104")
MARINA = Vendor("Marina Power Solutions", "45, Mount Road, Nandanam, Chennai 600035", "33AAAFM0000E1Z2", "044 4000 1105")
GUINDY = Vendor("Guindy Print House", "9, Race Course Road, Guindy, Chennai 600032", "33AAAFG0000F1Z6", "044 4000 1106")
VELA = Vendor("Velachery Electricals", "18, Bypass Road, Velachery, Chennai 600042", "33AAAFV0000G1Z1", "044 4000 1107")
SERVE = Vendor("Tharamani Facility Services", "5, Rajiv Gandhi Salai, Tharamani, Chennai 600113", "33AAAFT0000H1Z4", "044 4000 1108")
GLASS = Vendor("Mylapore Glassware Works", "31, Kutchery Road, Mylapore, Chennai 600004", "33AAAFM0000J1Z8", "044 4000 1109")
NET = Vendor("Besant Network Solutions Pvt Ltd", "12, Elliots Beach Road, Besant Nagar, Chennai 600090", "33AAACB0000K1Z3", "044 4000 1110")
OPTIC = Vendor("Sembiam Optics and Imaging", "60, Paper Mills Road, Perambur, Chennai 600011", "33AAAFS0000L1Z7", "044 4000 1111")
BALA = Vendor("Nungambakkam Furniture Works", "2, Haddows Road, Nungambakkam, Chennai 600006", "33AAAFN0000M1Z5", "044 4000 1112")
PORT = Vendor("Ennore Industrial Traders", "88, Ennore High Road, Chennai 600057", "33AAAFE0000N1Z9", "044 4000 1113")
CHROM = Vendor("Perungudi Chromatography Supplies", "6, Industrial Estate, Perungudi, Chennai 600096", "33AAAFP0000P1Z2", "044 4000 1114")
IMPORT = Vendor("Pallavaram Precision Imports", "27, GST Road, Pallavaram, Chennai 600043", "33AAAFP0000Q1Z6", "044 4000 1115")
OTHER = Vendor("Tambaram Trading Company", "101, Velachery Road, Tambaram, Chennai 600045", "33AAAFT0000R1Z0", "044 4000 1116")


def order(serial: str, vendor: Vendor, department: str, indent: str, items: list[Item], freight: float = 0) -> Order:
    return Order(f"IITM/PUR/2026-27/{serial}", vendor, department, indent, "02 Oct 2026", items, freight)


O_SCOPES = order("0417", KAVERI, "Department of Electrical Engineering", "EE/IND/2026/118", [
    Item("Digital Storage Oscilloscope, 200 MHz, 4 Channel", "90302000", 2, 86500),
    Item("Arbitrary Function Generator, 25 MHz", "85432010", 4, 24000),
])
O_REAGENTS = order("0418", CORO, "Department of Chemistry", "CY/IND/2026/067", [
    Item("Acetonitrile, HPLC Grade, 2.5 L", "29269000", 12, 3200),
    Item("Nitrile Gloves, Box of 100", "40151900", 40, 450),
], freight=1500)
O_CHAIRS = order("0419", ADYAR, "Central Library", "LIB/IND/2026/022", [
    Item("Ergonomic Reading Chair", "94013000", 30, 6800),
    Item("Study Carrel Desk", "94033090", 10, 14500),
])
O_WORKSTATIONS = order("0420", NOVA, "Department of Computer Science and Engineering", "CS/IND/2026/205", [
    Item("Workstation, Intel Xeon, 64 GB RAM, 2 TB SSD", "84714900", 6, 148000),
    Item("27 inch IPS Monitor", "85285200", 6, 21500),
])
O_UPS = order("0421", MARINA, "Department of Mechanical Engineering", "ME/IND/2026/091", [
    Item("Online UPS, 10 kVA", "85044010", 2, 118000),
    Item("SMF Battery, 12 V 100 Ah", "85072000", 32, 9400),
])
O_PRINT = order("0422", GUINDY, "Office of Academic Courses", "AC/IND/2026/014", [
    Item("Convocation Booklet, 80 pages", "49011010", 1500, 95),
    Item("Certificate Folder, Embossed", "48201090", 1500, 42),
])
O_CABLE = order("0423", VELA, "Estate Office", "EO/IND/2026/176", [
    Item("Copper Armoured Cable, 4 Core, 16 sq mm (metre)", "85446020", 400, 610),
    Item("MCCB, 100 A, 4 Pole", "85362090", 8, 7200),
])
O_SERVICE = order("0424", SERVE, "Estate Office", "EO/IND/2026/180", [
    Item("Housekeeping Services, Academic Zone (per month)", "998533", 6, 145000),
])
O_GLASS = order("0425", GLASS, "Department of Biotechnology", "BT/IND/2026/058", [
    Item("Borosilicate Beaker Set, 50 to 1000 ml", "70179090", 25, 1850),
    Item("Volumetric Flask, 500 ml, Class A", "70179090", 60, 780),
])
O_SWITCHES = order("0426", NET, "Computer Centre", "CC/IND/2026/133", [
    Item("48 Port Gigabit Managed Switch", "85176290", 8, 62000),
    Item("10G SFP+ Transceiver Module", "85177090", 16, 8900),
])
O_MICROSCOPE = order("0427", OPTIC, "Department of Applied Mechanics", "AM/IND/2026/041", [
    Item("Metallurgical Microscope, Trinocular", "90118000", 2, 212000),
    Item("Digital Microscope Camera, 12 MP", "85258900", 2, 48000),
    Item("Objective Lens, 100X Oil", "90021100", 4, 26500),
    Item("Polishing Machine, Double Disc", "84649090", 1, 135000),
    Item("Mounting Press, Hot Type", "84793000", 1, 168000),
    Item("Precision Cut-off Machine", "84615019", 1, 245000),
    Item("Hardness Tester, Vickers", "90248000", 1, 389000),
    Item("Sample Storage Desiccator", "70179090", 6, 7400),
    Item("Polishing Cloth Set", "59119090", 20, 1450),
    Item("Diamond Suspension, 1 Micron", "34059090", 10, 5200),
    Item("Mounting Resin, 1 kg", "39073090", 12, 3100),
    Item("Installation and Training", "998729", 1, 45000),
])
O_FURNITURE = order("0428", BALA, "Hostel Administration", "HA/IND/2026/099", [
    Item("Steel Cot with Mattress", "94032010", 50, 11200),
    Item("Study Table with Drawer", "94033090", 50, 6200),
])
O_LOCKERS = order("0429", PORT, "Department of Ocean Engineering", "OE/IND/2026/027", [
    Item("Steel Storage Rack, Heavy Duty", "94032090", 12, 18500),
])
O_COLUMNS = order("0430", CHROM, "Department of Chemistry", "CY/IND/2026/071", [
    Item("HPLC Column, C18, 250 mm", "90279090", 6, 42000),
    Item("Guard Column Kit", "90279090", 6, 13500),
])
O_CAMERA = order("0431", IMPORT, "Department of Aerospace Engineering", "AE/IND/2026/084", [
    Item("High Speed Camera, 1000 fps", "85258900", 1, 625000),
    Item("Camera Tripod, Heavy Duty", "96200000", 2, 18500),
])
O_PROJECTORS = order("0432", NOVA, "Office of Academic Courses", "AC/IND/2026/019", [
    Item("Laser Projector, 6000 Lumens", "85286200", 5, 186000),
    Item("Motorised Projection Screen", "90106000", 5, 24500),
])
O_BENCHES = order("0433", ADYAR, "Department of Physics", "PH/IND/2026/073", [
    Item("Anti Vibration Lab Bench", "94032090", 4, 96000),
])
O_STEEL = order("0435", PORT, "Estate Office", "EO/IND/2026/191", [
    Item("TMT Steel Rod, 12 mm, Fe 500", "72142090", 2, 62000, unit="MT"),
])
O_SPECTRO = order("0434", IMPORT, "Department of Physics", "PH/IND/2026/081", [
    Item("UV-Vis Spectrophotometer", "90273010", 1, 465000),
    Item("Quartz Cuvette Set", "70179090", 4, 6800),
    Item("Sample Holder Assembly", "90279090", 2, 19500),
    Item("Deuterium Lamp", "85394900", 2, 28000),
    Item("Tungsten Halogen Lamp", "85392190", 2, 9500),
    Item("Calibration Standard Kit", "90279090", 1, 54000),
    Item("Spectroscopy Software Licence", "997331", 1, 72000),
    Item("Installation and Training", "998729", 1, 25000),
])

ORDERS = [
    O_SCOPES, O_REAGENTS, O_CHAIRS, O_WORKSTATIONS, O_UPS, O_PRINT, O_CABLE, O_SERVICE, O_GLASS,
    O_SWITCHES, O_MICROSCOPE, O_FURNITURE, O_LOCKERS, O_COLUMNS, O_CAMERA, O_PROJECTORS, O_BENCHES,
    O_SPECTRO, O_STEEL,
]

SCOPES_INVOICE = Invoice(O_SCOPES, "KSI/26-27/0893", "09 Oct 2026", f"PO No: {O_SCOPES.number}")


def first_month(number: str, month: str) -> list[Item]:
    return [Item(f"Housekeeping Services, Academic Zone, {month} 2026", "998533", 1, 145000)]


@dataclass(frozen=True)
class Sample:
    folder: str
    slug: str
    quality: str
    tests: str
    po: str
    expected: str
    invoice: Invoice
    build: Callable[[Invoice], bytes]
    answer: str = "-"


SAMPLES = [
    Sample("correct", "01-clear-digital", "Clear digital PDF", "Matches the PO exactly", O_SCOPES.number, "Accept",
           SCOPES_INVOICE, digital),
    Sample("correct", "02-clean-scan-with-freight", "Clean scan", "Freight and CGST/SGST add up to the PO", O_REAGENTS.number, "Accept",
           Invoice(O_REAGENTS, "CLS/1147/26-27", "11 Oct 2026", f"Purchase Order: {O_REAGENTS.number}", layout="band"),
           scanned(clean, 1)),
    Sample("correct", "03-skewed-scan", "Skewed scan, 3.5 degrees", "Exact match", O_CHAIRS.number, "Accept",
           Invoice(O_CHAIRS, "AOS-2026-3312", "12 Oct 2026", f"PO Ref: {O_CHAIRS.number}", layout="typed"),
           scanned(skewed, 2)),
    Sample("correct", "04-blurry-scan", "Blurry scan", "Exact match", O_WORKSTATIONS.number, "Accept",
           Invoice(O_WORKSTATIONS, "TN/INV/5521", "13 Oct 2026", f"P.O. No.: {O_WORKSTATIONS.number}"),
           scanned(blurry, 3)),
    Sample("correct", "05-noisy-scan", "Noisy, speckled scan", "Exact match", O_UPS.number, "Accept",
           Invoice(O_UPS, "MPS/26-27/208", "14 Oct 2026", f"PO No: {O_UPS.number}", layout="band"),
           scanned(noisy, 4)),
    Sample("correct", "06-fax-copy", "Low-resolution black and white fax", "Exact match", O_PRINT.number, "Accept",
           Invoice(O_PRINT, "GPH-1809", "15 Oct 2026", f"Order Ref: {O_PRINT.number}", layout="typed"),
           scanned(fax, 5)),
    Sample("correct", "07-phone-photo", "Phone photo, angled with uneven light", "Exact match", O_CABLE.number, "Accept",
           Invoice(O_CABLE, "VE/2026/774", "16 Oct 2026", f"PO No: {O_CABLE.number}"),
           scanned(phone, 6)),
    Sample("correct", "08-faint-scan", "Faint, pale scan", "PO quoted only indirectly, without the IITM prefix", O_GLASS.number, "Accept",
           Invoice(O_GLASS, "MGW-3390", "17 Oct 2026", "Your Order: PUR/2026-27/0425", layout="band"),
           scanned(faint, 7)),
    Sample("correct", "09-rotated-scan", "Scanned sideways, 90 degrees", "Exact match", O_SWITCHES.number, "Accept",
           Invoice(O_SWITCHES, "BNS/INV/2641", "18 Oct 2026", f"PO No: {O_SWITCHES.number}"),
           scanned(sideways, 8)),
    Sample("correct", "10-two-page-digital", "Clear digital, 2 pages, 12 items", "Long itemised invoice matches the PO", O_MICROSCOPE.number, "Accept",
           Invoice(O_MICROSCOPE, "SOI/26-27/412", "19 Oct 2026", f"PO No: {O_MICROSCOPE.number}", items_on_first_page=7),
           digital),
    Sample("correct", "11-split-bill-first-month", "Clear digital", "First monthly bill on a six-month PO, so partial billing", O_SERVICE.number, "Accept",
           Invoice(O_SERVICE, "TFS/OCT/1021", "31 Oct 2026", f"PO No: {O_SERVICE.number}", items=first_month("", "October")),
           digital),
    Sample("correct", "12-billed-in-kg-po-in-tonnes", "Clear digital PDF", "Billed as 2,000 kg against a PO for 2 tonnes", O_STEEL.number, "Accept",
           Invoice(O_STEEL, "EIT/26-27/0457", "21 Oct 2026", f"PO No: {O_STEEL.number}",
                   items=[Item("TMT Steel Rod, 12 mm, Fe 500", "72142090", 2000, 62, unit="kg")]),
           digital),
    Sample("incorrect", "01-clear-digital-overbilled", "Clear digital PDF", "About 15% over the PO", O_FURNITURE.number, "Reject",
           Invoice(O_FURNITURE, "NFW/5567", "10 Oct 2026", f"PO No: {O_FURNITURE.number}",
                   items=[Item("Steel Cot with Mattress", "94032010", 50, 12880), Item("Study Table with Drawer", "94033090", 50, 7130)]),
           digital),
    Sample("incorrect", "02-clean-scan-wrong-vendor", "Clean scan", "A different company quotes a real PO", O_LOCKERS.number, "Reject",
           Invoice(O_LOCKERS, "TTC-9921", "11 Oct 2026", f"PO No: {O_LOCKERS.number}", vendor=OTHER, layout="band"),
           scanned(clean, 11)),
    Sample("incorrect", "03-skewed-scan-5pct-over", "Skewed scan, 3.5 degrees", "About 5% over the PO", O_COLUMNS.number, "Review",
           Invoice(O_COLUMNS, "PCS/26-27/660", "12 Oct 2026", f"PO No: {O_COLUMNS.number}", layout="typed",
                   items=[Item("HPLC Column, C18, 250 mm", "90279090", 6, 44100), Item("Guard Column Kit", "90279090", 6, 14175)]),
           scanned(skewed, 12)),
    Sample("incorrect", "04-blurry-scan-bad-maths", "Blurry scan", "Line items don't add up to the taxable value", O_PROJECTORS.number, "Review",
           Invoice(O_PROJECTORS, "TN/INV/5602", "13 Oct 2026", f"P.O. No.: {O_PROJECTORS.number}", printed_subtotal=1030000),
           scanned(blurry, 13)),
    Sample("incorrect", "05-noisy-scan-extra-item", "Noisy, speckled scan", "Bills an item that isn't on the PO, though the total is under it", O_BENCHES.number, "Review",
           Invoice(O_BENCHES, "AOS-2026-3498", "14 Oct 2026", f"PO Ref: {O_BENCHES.number}", layout="band",
                   items=[Item("Anti Vibration Lab Bench", "94032090", 3, 96000), Item("Executive Sofa Set", "94016100", 1, 45000)]),
           scanned(noisy, 14)),
    Sample("incorrect", "06-fax-duplicate-of-correct-01", "Low-resolution black and white fax", "Re-sent copy of correct 01, so the file differs but the invoice doesn't", O_SCOPES.number, "Reject",
           replace(SCOPES_INVOICE, layout="typed"), scanned(fax, 15)),
    Sample("incorrect", "07-phone-photo-no-invoice-number", "Phone photo, angled with uneven light", "The invoice number is missing", O_CAMERA.number, "Review",
           Invoice(O_CAMERA, None, "16 Oct 2026", f"PO No: {O_CAMERA.number}"),
           scanned(phone, 16)),
    Sample("incorrect", "08-faint-unknown-po", "Faint, pale scan", "Quotes a PO that doesn't exist", "IITM/PUR/2026-27/0999 (not on file)", "Pauses, then Review",
           Invoice(O_SWITCHES, "BNS/INV/2702", "17 Oct 2026", "PO No: IITM/PUR/2026-27/0999", layout="band",
                   items=[Item("Rack Mount Patch Panel", "85366990", 10, 3400)]),
           scanned(faint, 17), "Click There is no PO"),
    Sample("incorrect", "09-rotated-split-bill-too-far", "Scanned sideways, 90 degrees", "Taken with correct 11, this bill takes the six-month PO over its limit", O_SERVICE.number, "Reject",
           Invoice(O_SERVICE, "TFS/NOV/1102", "30 Nov 2026", f"PO No: {O_SERVICE.number}",
                   items=[Item("Housekeeping Services, Academic Zone, Nov to Apr", "998533", 6, 145000)]),
           scanned(sideways, 18)),
    Sample("incorrect", "10-two-page-wrong-currency", "Clear digital, 2 pages", "Billed in USD against an INR PO", O_SPECTRO.number, "Review",
           Invoice(O_SPECTRO, "PPI/26-27/318", "19 Oct 2026", f"PO No: {O_SPECTRO.number}", items_on_first_page=5, currency="USD"),
           digital),
    Sample("incorrect", "11-password-protected", "Password-protected PDF", "Can't be opened, so a person must look at it", "Unreadable", "Review",
           Invoice(O_BENCHES, "AOS-2026-3510", "20 Oct 2026", f"PO Ref: {O_BENCHES.number}"), locked),
]


def path_for(sample: Sample) -> Path:
    return OUTPUT / sample.folder / f"{sample.slug}.pdf"


def readme() -> str:
    def table(folder: str) -> str:
        rows = [
            f"| `{s.slug}.pdf` | {s.quality} | {s.tests} | {s.po} | {s.expected} | {s.answer} |"
            for s in SAMPLES
            if s.folder == folder
        ]
        return "\n".join(
            ["| File | Quality | What it tests | PO | Expected | At the pause |", "|---|---|---|---|---|---|", *rows]
        )

    return (
        "# IIT Madras test invoices\n\n"
        "Generated by `scripts/prepare_iitm_samples.py`, which also adds the purchase orders.\n\n"
        "Upload `correct` first, in numbered order, then `incorrect`. Incorrect 06 and 09 depend "
        "on correct 01 and 11. To start again, delete those runs in the app.\n\n"
        "Every vendor is fictional, and every GSTIN, PAN and bank account is a placeholder. "
        "Each invoice carries a small footer saying it is a test document.\n\n"
        f"## Correct\n\n{table('correct')}\n\n## Incorrect\n\n{table('incorrect')}\n"
    )


def write_samples() -> None:
    for folder in ("correct", "incorrect"):
        (OUTPUT / folder).mkdir(parents=True, exist_ok=True)
    for sample in SAMPLES:
        path_for(sample).write_bytes(sample.build(sample.invoice))
    (OUTPUT / "README.md").write_text(readme(), encoding="utf-8")
    print(f"Wrote {len(SAMPLES)} invoices to {OUTPUT}")


async def seed_purchase_orders() -> None:
    client = AsyncMongoClient(settings.MONGO_DB_URL)
    repository = MongoPurchaseOrderRepository(client[settings.MONGO_DB_NAME])
    await repository.ensure_indexes()
    added = 0
    for item in ORDERS:
        try:
            await repository.insert(PurchaseOrder(**item.as_document()))
            added += 1
        except DuplicatePurchaseOrderError:
            pass
    await client.close()
    print(f"Added {added} of {len(ORDERS)} POs to {settings.MONGO_DB_NAME}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--files-only", action="store_true", help="do not touch the database")
    args = parser.parse_args()
    write_samples()
    if not args.files_only:
        asyncio.run(seed_purchase_orders())
