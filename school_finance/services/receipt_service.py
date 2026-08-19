"""Generate a PDF receipt for a single payment.

Visual design:
  - Accent color (#185FA5) for the receipt bar, section rules, and balance line.
  - Colored status badge (PAID / PARTIAL / BALANCE DUE) computed from balance.
  - Shaded panels behind Student Information and the amounts block.
  - QR code encoding the receipt number for authenticity.
  - Consistent vertical rhythm via PAD_XS / PAD_SM / PAD_MD / PAD_LG constants.

Amounts block (template-aligned, compact so it still fits one A5 page):
  - FEE BREAKDOWN: single term-fee line (no itemised description), the waiver
    is subtracted (green, shown in parentheses) and Net Amount Due is the
    total to be paid minus any waiver. A sub-line notes any previous balance.
  - TOTAL AMOUNT PAID THIS RECEIPT line.
  - ACCOUNT FINANCIAL SUMMARY: Total Payable (up to the current term),
    Previous Payments (paid before this receipt), Current Payment, and the
    CURRENT OUTSTANDING BALANCE as the focal line.

Robustness:
  - Header text is wrapped with c.stringWidth() instead of one fixed line.
  - payment_details footer keeps the true first N lines in original order.
  - datetime.strptime is guarded with try/except, falling back to the raw string.
  - receipt_no is sanitized before being used as a filename.
  - Header box height is computed from what is actually populated.

Nice-to-have:
  - DUPLICATE watermark when a receipt is reprinted (print_count > 1).
"""
import os
import datetime

from reportlab.lib.pagesizes import A5
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader

from db.database import get_connection, BASE_DIR
from models.school import get_school_info
from models.term import get_term
from models.fee_structure import get_fee
from models.student import get_balance, get_term_balance
from models.payment import amount_in_words

RECEIPTS_DIR = os.path.join(BASE_DIR, "receipts")

# --- Spacing constants (consistent vertical rhythm) ---
PAD_XS = 2 * mm
PAD_SM = 4 * mm
PAD_MD = 6 * mm
PAD_LG = 10 * mm

# --- Color palette ---
ACCENT = colors.HexColor("#185FA5")           # deep blue accent
ACCENT_LIGHT = colors.HexColor("#E8F0F8")      # light tint for bar fills
PANEL_BG = colors.HexColor("#F5F5F5")          # light gray for shaded panels
PANEL_BORDER = colors.HexColor("#CCCCCC")
TEXT_DARK = colors.black
TEXT_MUTED = colors.HexColor("#666666")
STATUS_COLORS = {
    "PAID": colors.HexColor("#2E7D32"),          # green
    "PARTIAL": colors.HexColor("#F57C00"),       # amber
    "BALANCE DUE": colors.HexColor("#C62828"),   # red
}


def _sanitize_filename(name):
    """Strip to alnum + hyphens/underscores for safe filenames."""
    safe = "".join(ch for ch in name if ch.isalnum() or ch in "-_").strip()
    return safe or "receipt"


def _wrap_text(c, text, font, size, max_width):
    """Wrap *text* into lines that each fit within *max_width*."""
    words = text.split()
    if not words:
        return []
    lines = []
    current = ""
    for word in words:
        test = f"{current} {word}".strip()
        if c.stringWidth(test, font, size) <= max_width:
            current = test
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def _draw_shaded_panel(c, x, y, w, h, fill_color=PANEL_BG):
    """Draw a shaded panel with a light fill and thin border."""
    c.saveState()
    c.setFillColor(fill_color)
    c.setStrokeColor(PANEL_BORDER)
    c.setLineWidth(0.5)
    c.rect(x, y, w, h, fill=1, stroke=1)
    c.restoreState()


def _draw_accent_rule(c, x1, y, x2, color=ACCENT, width=1.2):
    """Draw a horizontal rule in the accent color."""
    c.saveState()
    c.setStrokeColor(color)
    c.setLineWidth(width)
    c.line(x1, y, x2, y)
    c.restoreState()


def _draw_status_badge(c, x, y, status, width=28 * mm, height=6 * mm):
    """Draw a colored status badge as a filled rounded rectangle with white text."""
    color = STATUS_COLORS.get(status, colors.grey)
    c.saveState()
    c.setFillColor(color)
    c.setStrokeColor(color)
    c.roundRect(x, y, width, height, 2 * mm, fill=1, stroke=1)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 8)
    c.drawCentredString(x + width / 2, y + 1.8 * mm, status)
    c.restoreState()


def _compute_status(balance_after, total_fee, credit_balance=0.0):
    """Compute payment status label from balance, total fee, and credit."""
    if credit_balance > 0:
        return "CREDIT"
    if balance_after <= 0:
        return "PAID"
    if total_fee > 0 and balance_after >= total_fee:
        return "BALANCE DUE"
    return "PARTIAL"


def _draw_qr_code(c, data, x, y, size=16 * mm):
    """Draw a QR code at (*x*, *y*).  Returns True on success."""
    try:
        from reportlab.graphics.barcode.qr import QrCodeWidget
        from reportlab.graphics.shapes import Drawing
        from reportlab.graphics import renderPDF

        qr = QrCodeWidget(data)
        bounds = qr.getBounds()
        w = bounds[2] - bounds[0]
        h = bounds[3] - bounds[1]
        d = Drawing(size, size, transform=[size / w, 0, 0, size / h, 0, 0])
        d.add(qr)
        renderPDF.draw(d, c, x, y)
        return True
    except Exception:
        return False


def _format_date(date_str):
    """Parse a date string and return a human-readable format, with fallback."""
    if not date_str:
        return "N/A"
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            dt = datetime.datetime.strptime(date_str, fmt)
            return dt.strftime("%d %B %Y")
        except (ValueError, TypeError):
            continue
    return date_str


def _draw_dashed_line(c, x1, y, x2):
    """Draw a dashed horizontal line for tear-off separators."""
    c.saveState()
    c.setDash(2, 1)
    c.setLineWidth(0.5)
    c.setStrokeColor(colors.HexColor("#999999"))
    c.line(x1, y, x2, y)
    c.restoreState()


def _resolve_signature(username):
    """Return a validated signature image path for *username*.

    Looks up the user's ``signature_path`` in the database and verifies the
    file exists on disk.  Returns ``None`` when no signature is available so
    the caller can fall back to the dashed-line placeholder.
    """
    if not username:
        return None
    try:
        from models.user import get_user_by_username
        user = get_user_by_username(username.strip())
    except Exception:
        return None
    if not user:
        return None
    sig_path = user.get("signature_path")
    if sig_path and os.path.isfile(sig_path):
        return sig_path
    return None


def generate_receipt(payment_id, student, term_id, balance_after):
    """Build a PDF receipt for a payment and log it in the receipts table."""
    conn = get_connection()
    payment = conn.execute(
        "SELECT * FROM payments WHERE id = ?", (payment_id,)
    ).fetchone()
    if payment is None:
        raise ValueError("Payment not found")

    payment = dict(payment)
    student = dict(student)
    term = get_term(term_id) if term_id else None
    term_name = term["term_name"] if term else "N/A"
    year = term["year"] if term else datetime.datetime.now().year

    info = get_school_info()
    school_name = info.get("school_name") or "SCHOOL NAME HERE"
    motto = info.get("motto") or ""
    address = info.get("address") or ""
    phone = info.get("phone") or ""
    logo_path = info.get("logo_path") or ""
    payment_details = info.get("payment_details") or ""

    # --- Compute fee info (gross / waiver / net) ---
    fee = get_fee(student["grade"], term_id) if term_id else None
    current_term_gross = fee["amount"] if fee else 0.0
    if current_term_gross == 0.0:
        current_term_gross = conn.execute(
            "SELECT COALESCE(SUM(amount), 0) AS total FROM charges WHERE student_id = ?"
            + (" AND term_id = ?" if term_id else ""),
            ((payment["student_id"], term_id) if term_id else (payment["student_id"],)),
        ).fetchone()["total"]

    # Partial waiver total for this term (sum of active, non-revoked waivers)
    current_term_waiver = 0.0
    if term_id:
        wrow = conn.execute(
            "SELECT COALESCE(SUM(amount), 0) AS total FROM waivers "
            "WHERE student_id = ? AND term_id = ? AND revoked_at IS NULL",
            (payment["student_id"], term_id),
        ).fetchone()
        current_term_waiver = wrow["total"] if wrow else 0.0

    current_term_net = round(current_term_gross - current_term_waiver, 2)

    previous_balance = 0.0
    if term_id:
        previous_balance = (
            get_balance(payment["student_id"])
            - get_term_balance(payment["student_id"], term_id)
        )
        if previous_balance < 0:
            previous_balance = 0.0
        # previous_balance is computed AFTER the payment has been applied
        # (generate_receipt runs after add_payment), so it already reflects
        # the FIFO allocation of this payment.  Add back the portion of this
        # payment that was applied to previous-term charges so that
        # previous_balance shows the amount owed BEFORE this payment.
        current_term_alloc = conn.execute(
            "SELECT COALESCE(SUM(pa.amount), 0) AS total FROM payment_allocations pa "
            "JOIN charges c ON pa.charge_id = c.id "
            "WHERE pa.payment_id = ? AND c.term_id = ?",
            (payment_id, term_id),
        ).fetchone()["total"]
        alloc_to_previous = payment["amount"] - current_term_alloc
        previous_balance += alloc_to_previous
        if previous_balance < 0:
            previous_balance = 0.0

    # net_total is the true amount the student owes (gross minus waivers)
    total_fee = current_term_net + previous_balance
    # gross_total preserves the original required amount for display
    gross_total = current_term_gross + previous_balance
    from models.student_credits import get_available_credit
    credit_balance = get_available_credit(payment["student_id"])
    status = _compute_status(balance_after, total_fee, credit_balance)

    # Previous Payments = all prior non-voided payments received before this
    # receipt (money already collected toward the account, shown in the
    # ACCOUNT FINANCIAL SUMMARY block of the template).
    prev_paid_row = conn.execute(
        "SELECT COALESCE(SUM(amount), 0) AS total FROM payments "
        "WHERE student_id = ? AND voided = 0 AND id != ?",
        (payment["student_id"], payment_id),
    ).fetchone()
    prev_paid = prev_paid_row["total"] if prev_paid_row else 0.0

    # --- Sanitize filename ---
    safe_receipt_no = _sanitize_filename(payment["receipt_no"])
    os.makedirs(RECEIPTS_DIR, exist_ok=True)
    file_name = f"{safe_receipt_no}.pdf"
    file_path = os.path.join(RECEIPTS_DIR, file_name)

    # --- Check for reprint (print_count tracking) ---
    existing_receipt = conn.execute(
        "SELECT print_count FROM receipts WHERE receipt_no = ?",
        (payment["receipt_no"],),
    ).fetchone()
    is_reprint = existing_receipt is not None
    if is_reprint:
        print_count = (existing_receipt["print_count"] or 1) + 1
    else:
        print_count = 1

    # --- Build PDF ---
    c = canvas.Canvas(file_path, pagesize=A5)
    width, height = A5

    margin = 8 * mm
    x = margin
    w = width - 2 * margin
    y = height - margin # cursor moving downward

    # ================================================================
    # DUPLICATE WATERMARK (behind everything, only for reprints)
    # ================================================================
    if print_count > 1:
        c.saveState()
        c.translate(width / 2, height / 2)
        c.rotate(35)
        c.setFillColor(colors.HexColor("#F0F0F0"))
        c.setFont("Helvetica-Bold", 48)
        c.drawCentredString(0, 0, "DUPLICATE")
        c.restoreState()

    # ================================================================
    # HEADER SECTION (dynamic height based on populated fields)
    # ================================================================
    # Compute school name wrapping (needs canvas for stringWidth)
    name_lines = _wrap_text(c, school_name, "Helvetica-Bold", 11, w - 10 * mm)
    name_size = 13
    if len(name_lines) > 2:
        name_size = 11
        while name_size > 9 and len(
            _wrap_text(c, school_name, "Helvetica-Bold", name_size, w - 10 * mm)
        ) > 2:
            name_size -= 0.5
        name_lines = _wrap_text(
            c, school_name, "Helvetica-Bold", name_size, w - 10 * mm
        )

    # Compute header height: base (logo+name) + 5mm per optional field + padding.
    # The logo's space is only reserved when a logo actually exists, so a
    # school with no logo gets a compact header instead of empty white space.
    has_logo = bool(logo_path and os.path.isfile(logo_path))
    optional_count = sum(1 for f in (motto, address, phone) if f)
    header_h = 22 * mm if has_logo else 10 * mm  # base: logo space (if any) + name
    if len(name_lines) > 1:
        header_h += 5 * mm  # extra line for wrapped name
    header_h += optional_count * 5 * mm + PAD_SM

    _draw_shaded_panel(c, x, y - header_h, w, header_h, fill_color=colors.white)

    # Logo (centered at top)
    logo_bottom = y
    if has_logo:
        try:
            img_w, img_h = ImageReader(logo_path).getSize()
            max_w, max_h = 28 * mm, 20 * mm
            scale = min(max_w / img_w, max_h / img_h)
            draw_w, draw_h = img_w * scale, img_h * scale
            mask = "auto" if logo_path.lower().endswith(".png") else None
            c.drawImage(
                logo_path,
                (width - draw_w) / 2,
                y - draw_h - 2 * mm,
                draw_w,
                draw_h,
                mask=mask,
            )
            logo_bottom = y - draw_h - 2 * mm
        except Exception:
            pass

    # School name (wrapped, centered)
    text_y = logo_bottom - PAD_SM
    c.setFont("Helvetica-Bold", name_size)
    for line in name_lines[:2]:
        c.drawCentredString(width / 2, text_y, line)
        text_y -= 5 * mm

    # Motto
    if motto:
        c.setFont("Helvetica-Oblique", 7.5)
        c.drawCentredString(width / 2, text_y, f'"{motto}"')
        text_y -= 5 * mm

    # Address (wrapped, centered)
    if address:
        addr_lines = _wrap_text(c, address, "Helvetica", 7.5, w - 10 * mm)
        c.setFont("Helvetica", 7.5)
        for line in addr_lines[:2]:
            c.drawCentredString(width / 2, text_y, line)
            text_y -= 4 * mm

    # Phone
    if phone:
        c.setFont("Helvetica", 7.5)
        c.drawCentredString(width / 2, text_y, f"Tel: {phone}")

    y -= header_h + PAD_SM

    # ================================================================
    # OFFICIAL RECEIPT BAR + STATUS BADGE
    # ================================================================
    bar_h = 8 * mm
    # Accent-tinted fill with accent border
    c.saveState()
    c.setFillColor(ACCENT_LIGHT)
    c.setStrokeColor(ACCENT)
    c.setLineWidth(1.0)
    c.rect(x, y - bar_h, w, bar_h, fill=1, stroke=1)
    c.restoreState()
    # Accent rules above and below the bar
    _draw_accent_rule(c, x, y, x + w, color=ACCENT, width=1.5)
    _draw_accent_rule(c, x, y - bar_h, x + w, color=ACCENT, width=1.5)

    # Bar text (black for readability)
    c.setFont("Helvetica-Bold", 9)
    c.drawCentredString(width / 2, y - 7 * mm, "OFFICIAL SCHOOL RECEIPT")

    # Status badge (right side of bar)
    badge_w = 28 * mm
    badge_h = 6 * mm
    _draw_status_badge(
        c,
        x + w - badge_w - 3 * mm,
        y - bar_h / 2 - badge_h / 2,
        status,
        width=badge_w,
        height=badge_h,
    )

    y -= bar_h + PAD_SM

    # ================================================================
    # RECEIPT DETAILS (Receipt No, Date, Year, Term)
    # ================================================================
    date_str = _format_date(payment["date_paid"])
    c.setFont("Helvetica-Bold", 10)
    c.drawString(x + 5 * mm, y - 5 * mm, f"Receipt No: {payment['receipt_no']}")
    c.setFont("Helvetica", 10)
    c.drawString(x + w * 0.55, y - 5 * mm, f"Date: {date_str}")
    c.drawString(x + 5 * mm, y - 11 * mm, f"Academic Year: {year}")
    c.drawString(x + w * 0.55, y - 11 * mm, f"Term: {term_name}")

    y -= 13 * mm + PAD_SM

    # ================================================================
    # STUDENT INFORMATION PANEL (shaded)
    # ================================================================
    panel_h = 17 * mm
    _draw_shaded_panel(c, x, y - panel_h, w, panel_h)

    c.setFont("Helvetica-Bold", 8)
    c.drawCentredString(width / 2, y - 6 * mm, "STUDENT INFORMATION")

    student_class = student["grade"]
    if student.get("stream"):
        student_class = f"{student['grade']} {student['stream']}"
    c.setFont("Helvetica", 7.5)
    c.drawString(x + 5 * mm, y - 12 * mm, f"Student Name: {student['full_name']}")
    c.drawString(
        x + 5 * mm, y - 16 * mm, f"Admission No: {student['admission_no'] or '-'}"
    )
    c.drawString(x + w * 0.55, y - 16 * mm, f"Class: {student_class}")

    y -= panel_h + PAD_SM

    # ================================================================
    # PAYMENT METHOD
    # ================================================================
    #
    # The section height is IDENTICAL whether or not a detail line is
    # drawn.  M-Pesa / In-Kind receipts therefore do NOT push the
    # amounts panel any lower than Cash / Bank receipts do.
    #
    # Previously the extra "TRANSACTION CODE / DESCRIPTION" line cost
    # an extra 6 mm of vertical space, which made the Amount-in-Words
    # panel climb up over the bottom of the amounts panel and cover
    # the CURRENT OUTSTANDING BALANCE row.
    # ================================================================
    c.setFont("Helvetica-Bold", 8)
    c.drawString(
        x + 5 * mm, y - 5 * mm, f"PAYMENT METHOD: {payment['method']}"
    )

    method_detail = None
    if payment["method"] == "M-Pesa" and payment["mpesa_code"]:
        method_detail = f"TRANSACTION CODE: {payment['mpesa_code']}"
    elif payment["method"] == "In-Kind" and payment["in_kind_desc"]:
        method_detail = f"DESCRIPTION: {payment['in_kind_desc']}"

    if method_detail:
        c.setFont("Helvetica", 7.5)
        c.drawString(
            x + 5 * mm,
            y - 9.5 * mm,
            method_detail,
        )

    # Fixed 8 mm budget for every method (two compact lines fit).
    y -= 8 * mm + PAD_SM

    # ================================================================
    # AMOUNTS PANEL — PROFESSIONAL HALF-A4 RECEIPT LAYOUT
    #
    # Structure:
    #
    #   FEE BREAKDOWN
    #       Term Fee                         KSh gross
    #       Less: Fee Waiver                KSh waiver   [if any]
    #       Previous Balance                KSh balance  [if any]
    #       ----------------------------------------------------------
    #       TOTAL AMOUNT DUE                KSh total
    #
    #   AMOUNT PAID THIS RECEIPT            KSh payment
    #
    #   ACCOUNT FINANCIAL SUMMARY
    #       Total Payable                   KSh total
    #       Previous Payments               KSh previous payments
    #       Current Payment                 KSh current payment
    #
    #       CURRENT OUTSTANDING BALANCE     KSh balance
    #
    #   AMOUNT IN WORDS:
    #       Kenya Shillings ...
    # ================================================================

    has_waiver = current_term_waiver > 0

    # ------------------------------------------------
    # BUILD ROWS
    # ------------------------------------------------

    rows = []  # (kind, label, value)

    # ================================================================
    # FEE BREAKDOWN
    # ================================================================

    rows.append(("HEAD", "FEE BREAKDOWN", ""))

    if term_name != "N/A":
        row_title = f"Term Fee — {term_name}, {year}"
    else:
        row_title = "Term Fee"

    rows.append(("item", row_title, current_term_gross))

    # Fee waiver, if applicable
    if has_waiver:
        rows.append(("credit", "Less: Fee Waiver", -current_term_waiver))

    # Previous balance is displayed separately
    if previous_balance > 0:
        rows.append(("item", "Previous Balance", previous_balance))

    # Total amount due
    rows.append(("TOTALDUE", "TOTAL AMOUNT DUE", total_fee))

    # ================================================================
    # CURRENT PAYMENT
    # ================================================================

    rows.append((
        "TOTALPAID",
        "AMOUNT PAID THIS RECEIPT",
        payment["amount"]
    ))

    # ================================================================
    # ACCOUNT FINANCIAL SUMMARY
    # ================================================================

    rows.append(("HEAD", "ACCOUNT FINANCIAL SUMMARY", ""))

    rows.append((
        "item",
        "Total Payable",
        total_fee
    ))

    rows.append((
        "item",
        "Previous Payments",
        prev_paid
    ))

    rows.append((
        "item",
        "Current Payment",
        payment["amount"]
    ))

    # Account credit, if applicable
    if credit_balance > 0:
        rows.append((
            "credit",
            "Account Credit (Overpayment)",
            -credit_balance
        ))

    # Outstanding balance
    rows.append((
        "BALANCE",
        "CURRENT OUTSTANDING BALANCE",
        balance_after
    ))


    # ================================================================
    # ROW HEIGHTS
    # ================================================================

    row_h = {
        "HEAD": 5.0 * mm,
        "item": 4.0 * mm,
        "credit": 4.0 * mm,
        "TOTALDUE": 5.0 * mm,
        "TOTALPAID": 6.0 * mm,
        "BALANCE": 9.0 * mm,
    }


    # ================================================================
    # CALCULATE PANEL HEIGHT
    # ================================================================

    amounts_h = (
        sum(row_h[kind] for kind, _, _ in rows)
        + 6.0 * mm
    )


    # ================================================================
    # DRAW MAIN SHADED PANEL
    # ================================================================

    _draw_shaded_panel(
        c,
        x,
        y - amounts_h,
        w,
        amounts_h
    )


    # ================================================================
    # START DRAWING ROWS
    # ================================================================

    cur_y = y - 5.5 * mm


    for kind, label, value in rows:

        # ============================================================
        # SECTION HEADER
        # ============================================================

        if kind == "HEAD":

            c.saveState()

            c.setFillColor(ACCENT)
            c.setFont(
                "Helvetica-Bold",
                8.5
            )

            c.drawString(
                x + 5 * mm,
                cur_y,
                label
            )

            # Thin separator below heading
            _draw_accent_rule(
                c,
                x + 5 * mm,
                cur_y - 1.7 * mm,
                x + w - 5 * mm,
                color=colors.HexColor("#B7CFE6"),
                width=0.7
            )

            c.restoreState()


        # ============================================================
        # TOTAL AMOUNT DUE
        # ============================================================

        elif kind == "TOTALDUE":

            c.saveState()

            # Separator line above total
            c.setStrokeColor(
                colors.HexColor("#B7CFE6")
            )
            c.setLineWidth(0.7)

            c.line(
                x + 5 * mm,
                cur_y + 1.5 * mm,
                x + w - 5 * mm,
                cur_y + 1.5 * mm
            )

            c.setFillColor(TEXT_DARK)

            c.setFont(
                "Helvetica-Bold",
                9
            )

            c.drawString(
                x + 5 * mm,
                cur_y - 2.5 * mm,
                label
            )

            c.drawRightString(
                x + w - 5 * mm,
                cur_y - 2.5 * mm,
                f"KSh {value:,.2f}"
            )

            c.restoreState()


        # ============================================================
        # AMOUNT PAID THIS RECEIPT
        # ============================================================

        elif kind == "TOTALPAID":

            c.saveState()

            # Light accent background
            c.setFillColor(
                colors.HexColor("#EAF2F8")
            )
            c.setStrokeColor(
                colors.HexColor("#B7CFE6")
            )
            c.setLineWidth(0.7)

            c.roundRect(
                x + 3 * mm,
                cur_y - 4.5 * mm,
                w - 6 * mm,
                6.5 * mm,
                1.2 * mm,
                fill=1,
                stroke=1
            )

            c.setFillColor(ACCENT)

            c.setFont(
                "Helvetica-Bold",
                9.5
            )

            c.drawString(
                x + 6 * mm,
                cur_y - 2.5 * mm,
                label
            )

            c.drawRightString(
                x + w - 6 * mm,
                cur_y - 2.5 * mm,
                f"KSh {value:,.2f}"
            )

            c.restoreState()

            # Extra breathing room before the next section
            cur_y -= 1.5 * mm


        # ============================================================
        # CURRENT OUTSTANDING BALANCE
        # ============================================================

        elif kind == "BALANCE":

            c.saveState()

            # Stronger highlighted balance box
            c.setFillColor(
                colors.HexColor("#E6F0FA")
            )

            c.setStrokeColor(
                ACCENT
            )

            c.setLineWidth(0.9)

            c.roundRect(
                x + 3 * mm,
                cur_y - 6.0 * mm,
                w - 6 * mm,
                8.5 * mm,
                1.5 * mm,
                fill=1,
                stroke=1
            )

            c.setFillColor(ACCENT)

            c.setFont(
                "Helvetica-Bold",
                9.5
            )

            c.drawString(
                x + 6 * mm,
                cur_y - 2.5 * mm,
                label
            )

            c.drawRightString(
                x + w - 6 * mm,
                cur_y - 2.5 * mm,
                f"KSh {value:,.2f}"
            )

            c.restoreState()


        # ============================================================
        # CREDIT / WAIVER
        # ============================================================

        elif kind == "credit":

            c.saveState()

            c.setFillColor(
                colors.HexColor("#2E7D32")
            )

            c.setFont(
                "Helvetica",
                8.5
            )

            c.drawString(
                x + 5 * mm,
                cur_y,
                label
            )

            c.drawRightString(
                x + w - 5 * mm,
                cur_y,
                f"KSh ({abs(value):,.2f})"
            )

            c.restoreState()


        # ============================================================
        # NORMAL FINANCIAL ROW
        # ============================================================

        else:

            c.saveState()

            c.setFillColor(TEXT_DARK)

            c.setFont(
                "Helvetica",
                8.5
            )

            c.drawString(
                x + 5 * mm,
                cur_y,
                label
            )

            c.drawRightString(
                x + w - 5 * mm,
                cur_y,
                f"KSh {value:,.2f}"
            )

            c.restoreState()


        # Move to next row
        cur_y -= row_h[kind]


    # ================================================================
    # MOVE BELOW AMOUNTS PANEL
    # ================================================================

    y -= amounts_h + PAD_SM


    # ================================================================
    # AMOUNT IN WORDS
    # ================================================================

    amount_words = amount_in_words(
        payment["amount"]
    )

    words_text = (
        f"Amount in Words: {amount_words}"
    )

    # Wrap text to fit half-A4 width
    words_lines = _wrap_text(
        c,
        words_text,
        "Helvetica-Oblique",
        7.5,
        w - 10 * mm
    )


    # Height of the Amount in Words panel
    words_h = max(
        8 * mm,
        len(words_lines) * 3.5 * mm + 4 * mm
    )


    # ------------------------------------------------
    # RESERVE SPACE FOR THE FIXED FOOTER
    # ------------------------------------------------

    footer_bottom = 6 * mm


    # Top of the footer/signature area.
    # Nothing above this point should overlap the footer.
    footer_top = footer_bottom + 29 * mm


    # Current y is the position immediately below the amounts panel.
    #
    # Natural position: the words panel sits right under the amounts
    # panel.  If it would reach into the reserved footer area, it is
    # pulled up into the band that runs from the amounts panel down to
    # the footer and shrunk so it can never overlap the amounts panel.
    #
    # That is what keeps Amount in Words from covering the CURRENT
    # OUTSTANDING BALANCE row -- which used to happen on M-Pesa /
    # In-Kind receipts because their extra payment-method line ate
    # 6 mm of vertical space.
    words_top = y
    words_bottom = words_top - words_h

    if words_bottom < footer_top:

        # Space available between the amounts panel and the footer.
        words_band = y - footer_top

        # Only shrink; never let the panel exceed the band.
        words_h = min(words_h, max(words_band, 8 * mm))

        # Pin the panel bottom to the top of the footer reserve so
        # the amounts panel and the footer stay cleanly separated.
        words_top = footer_top + words_h
        words_bottom = footer_top


    # ------------------------------------------------
    # DRAW AMOUNT-IN-WORDS PANEL
    # ------------------------------------------------

    _draw_shaded_panel(
        c,
        x,
        words_bottom,
        w,
        words_h,
        fill_color=colors.white
    )




    # ------------------------------------------------
    # DRAW AMOUNT-IN-WORDS TEXT
    # ------------------------------------------------

    # Use text metrics that fit the clamped panel height so the
    # words never spill below the panel / into the footer.
    words_font = 7.5
    words_line = 3.5 * mm
    while (
        len(words_lines) * words_line + 4 * mm > words_h
        and words_h >= 8 * mm
        and words_line > 2.0 * mm
    ):
        words_line -= 0.3 * mm
        words_font -= 0.3

    words_y = words_top - 4 * mm

    c.saveState()

    c.setFillColor(
        colors.HexColor("#555555")
    )

    c.setFont(
        "Helvetica-Oblique",
        words_font
    )

    for line in words_lines:

        c.drawString(
            x + 5 * mm,
            words_y,
            line
        )

        words_y -= words_line

    c.restoreState()




    # ------------------------------------------------
    # Update y
    # ------------------------------------------------

    y = words_bottom - PAD_SM

    # ================================================================
    # FIXED BOTTOM FOOTER AREA
    #
    # The footer is positioned from the bottom of the A5 page rather
    # than continuing to subtract from the main "y" position.
    #
    # footer_bottom / footer_top were reserved in the AMOUNT IN WORDS
    # section above, so nothing can overlap the footer area.
    # ================================================================

    # ------------------------------------------------
    # THANK-YOU MESSAGE — FIXED AT VERY BOTTOM
    # ------------------------------------------------

    thank_you_y = footer_bottom + 1.5 * mm

    c.saveState()

    c.setFillColor(
        colors.HexColor("#555555")
    )

    c.setFont(
        "Helvetica-Oblique",
        7.5
    )

    c.drawCentredString(
        width / 2,
        thank_you_y + 4 * mm,
        "Thank you for making your payment."
    )

    c.drawCentredString(
        width / 2,
        thank_you_y,
        "Please keep this receipt for future reference."
    )

    c.restoreState()


    # ------------------------------------------------
    # PAYMENT DETAILS
    # ------------------------------------------------
    #
    # Payment details are placed ABOVE the thank-you
    # message and limited to 3 lines so they cannot
    # push the footer outside the A5 page.
    # ------------------------------------------------

    if payment_details:

        lines = []

        for part in payment_details.splitlines():

            part = part.strip()

            while len(part) > 90:

                idx = part.rfind(" ", 0, 90)

                if idx == -1:
                    idx = 90

                lines.append(part[:idx])

                part = part[idx:].lstrip()

            if part:
                lines.append(part)

        # Maximum of 3 lines on the compact A5 receipt
        footer_lines = lines[:3]

        payment_y = footer_bottom + 11 * mm

        c.saveState()

        c.setFillColor(
            colors.HexColor("#666666")
        )

        c.setFont(
            "Helvetica-Oblique",
            6.8
        )

        for i, line in enumerate(footer_lines):

            c.drawCentredString(
                width / 2,
                payment_y + (
                    (len(footer_lines) - 1 - i) * 3.0 * mm
                ),
                line
            )

        c.restoreState()


    # ================================================================
    # SIGNATURE + QR CODE
    # ================================================================

    # Fixed signature area above the payment details
    sig_y = footer_bottom + 25 * mm

    signature_path = _resolve_signature(
        payment.get("received_by")
    )


    # ------------------------------------------------
    # SIGNATURE LINE
    # ------------------------------------------------

    c.saveState()

    c.setStrokeColor(
        colors.HexColor("#999999")
    )

    c.setLineWidth(0.5)

    c.line(
        x + 5 * mm,
        sig_y,
        x + 60 * mm,
        sig_y
    )

    c.restoreState()


    # ------------------------------------------------
    # RECEIVED BY
    # ------------------------------------------------

    c.setFillColor(TEXT_DARK)

    c.setFont(
        "Helvetica",
        7.5
    )

    c.drawString(
        x + 5 * mm,
        sig_y - 4 * mm,
        "Received By: Bursar"
    )


    # ------------------------------------------------
    # SIGNATURE IMAGE
    # ------------------------------------------------

    if signature_path:

        try:

            sig_w, sig_h = ImageReader(
                signature_path
            ).getSize()

            max_w = 18 * mm
            max_h = 6 * mm

            scale = min(
                max_w / sig_w,
                max_h / sig_h,
                1.0
            )

            draw_w = sig_w * scale
            draw_h = sig_h * scale

            mask = (
                "auto"
                if signature_path.lower().endswith(".png")
                else None
            )

            c.drawImage(
                signature_path,
                x + 5 * mm,
                sig_y + 0.5 * mm,
                draw_w,
                draw_h,
                mask=mask,
            )

        except Exception:

            c.setFont(
                "Helvetica",
                7
            )

            c.drawString(
                x + 5 * mm,
                sig_y - 8 * mm,
                "Signature: __________________"
            )

    else:

        c.setFont(
            "Helvetica",
            7
        )

        c.drawString(
            x + 5 * mm,
            sig_y - 8 * mm,
            "Signature: __________________"
        )


    # ================================================================
    # QR CODE
    # ================================================================

    qr_size = 10 * mm

    qr_data = f"Receipt:{payment['receipt_no']}"

    _draw_qr_code(
        c,
        data=qr_data,
        x=x + w - qr_size - 4 * mm,
        y=sig_y - qr_size + 1 * mm,
        size=qr_size,
    )


    # ================================================================
    # KEEP MAIN Y ABOVE THE FOOTER
    # ================================================================

    y = footer_top


    # ================================================================
    # SAVE
    # ================================================================

    c.showPage()
    c.save()


def generate_bulk_receipt(bulk_payment_id, bulk_payment, items):
    """Build a PDF master receipt for a bulk payment (NGO / sponsor).

    Uses the same visual style as generate_receipt:
      - School header with logo, name, motto, address, phone
      - Accent receipt bar
      - Shaded info panels
      - QR code
      - Footer
    """
    bulk_payment = dict(bulk_payment)
    os.makedirs(RECEIPTS_DIR, exist_ok=True)

    receipt_no = bulk_payment["receipt_no"]
    file_path = os.path.join(RECEIPTS_DIR, f"bulk_{receipt_no}.pdf")

    info = get_school_info()
    school_name = info.get("school_name") or "SCHOOL NAME HERE"
    motto = info.get("motto") or ""
    address = info.get("address") or ""
    phone = info.get("phone") or ""
    logo_path = info.get("logo_path") or ""
    payment_details = info.get("payment_details") or ""

    term = get_term(bulk_payment["term_id"]) if bulk_payment["term_id"] else None
    term_name = term["term_name"] if term else "N/A"
    year = term["year"] if term else datetime.datetime.now().year

    date_str = _format_date(bulk_payment["date_paid"])

    c = canvas.Canvas(file_path, pagesize=A5)
    width, height = A5

    margin = 12 * mm
    x = margin
    w = width - 2 * margin
    y = height - margin

    # ================================================================
    # HEADER SECTION (same style as single receipt)
    # ================================================================
    name_lines = _wrap_text(c, school_name, "Helvetica-Bold", 13, w - 10 * mm)
    name_size = 13
    if len(name_lines) > 2:
        name_size = 11
        while name_size > 9 and len(
            _wrap_text(c, school_name, "Helvetica-Bold", name_size, w - 10 * mm)
        ) > 2:
            name_size -= 0.5
        name_lines = _wrap_text(
            c, school_name, "Helvetica-Bold", name_size, w - 10 * mm
        )

    has_logo = bool(logo_path and os.path.isfile(logo_path))
    optional_count = sum(1 for f in (motto, address, phone) if f)
    header_h = 22 * mm if has_logo else 10 * mm
    if len(name_lines) > 1:
        header_h += 5 * mm
    header_h += optional_count * 5 * mm + PAD_SM

    _draw_shaded_panel(c, x, y - header_h, w, header_h, fill_color=colors.white)

    logo_bottom = y
    if has_logo:
        try:
            img_w, img_h = ImageReader(logo_path).getSize()
            max_w, max_h = 28 * mm, 20 * mm
            scale = min(max_w / img_w, max_h / img_h)
            draw_w, draw_h = img_w * scale, img_h * scale
            mask = "auto" if logo_path.lower().endswith(".png") else None
            c.drawImage(
                logo_path,
                (width - draw_w) / 2,
                y - draw_h - 2 * mm,
                draw_w,
                draw_h,
                mask=mask,
            )
            logo_bottom = y - draw_h - 2 * mm
        except Exception:
            pass

    text_y = logo_bottom - PAD_SM
    c.setFont("Helvetica-Bold", name_size)
    for line in name_lines[:2]:
        c.drawCentredString(width / 2, text_y, line)
        text_y -= 5 * mm

    if motto:
        c.setFont("Helvetica-Oblique", 9)
        c.drawCentredString(width / 2, text_y, f'"{motto}"')
        text_y -= 5 * mm

    if address:
        addr_lines = _wrap_text(c, address, "Helvetica", 9, w - 10 * mm)
        c.setFont("Helvetica", 9)
        for line in addr_lines[:2]:
            c.drawCentredString(width / 2, text_y, line)
            text_y -= 4 * mm

    if phone:
        c.setFont("Helvetica", 9)
        c.drawCentredString(width / 2, text_y, f"Tel: {phone}")

    y -= header_h + PAD_SM

    # ================================================================
    # RECEIPT BAR
    # ================================================================
    bar_h = 10 * mm
    c.saveState()
    c.setFillColor(ACCENT_LIGHT)
    c.setStrokeColor(ACCENT)
    c.setLineWidth(1.0)
    c.rect(x, y - bar_h, w, bar_h, fill=1, stroke=1)
    c.restoreState()
    _draw_accent_rule(c, x, y, x + w, color=ACCENT, width=1.5)
    _draw_accent_rule(c, x, y - bar_h, x + w, color=ACCENT, width=1.5)

    c.setFont("Helvetica-Bold", 11)
    c.drawCentredString(width / 2, y - 7 * mm, "OFFICIAL BULK PAYMENT RECEIPT")

    badge_w = 28 * mm
    badge_h = 6 * mm
    _draw_status_badge(
        c,
        x + w - badge_w - 3 * mm,
        y - bar_h / 2 - badge_h / 2,
        "PAID",
        width=badge_w,
        height=badge_h,
    )

    y -= bar_h + PAD_SM

    # ================================================================
    # RECEIPT DETAILS
    # ================================================================
    c.setFont("Helvetica-Bold", 10)
    c.drawString(x + 5 * mm, y - 5 * mm, f"Receipt No: {receipt_no}")
    c.setFont("Helvetica", 10)
    c.drawString(x + w * 0.55, y - 5 * mm, f"Date: {date_str}")
    c.drawString(x + 5 * mm, y - 11 * mm, f"Academic Year: {year}")
    c.drawString(x + w * 0.55, y - 11 * mm, f"Term: {term_name}")

    y -= 13 * mm + PAD_SM

    # ================================================================
    # ORGANISATION / PAYER PANEL
    # ================================================================
    org_lines = 2
    if bulk_payment.get("payer_contact"):
        org_lines += 1
    if bulk_payment.get("reference_no"):
        org_lines += 1
    org_panel_h = org_lines * 5 * mm + 6 * mm
    _draw_shaded_panel(c, x, y - org_panel_h, w, org_panel_h)

    c.setFont("Helvetica-Bold", 10)
    c.drawCentredString(width / 2, y - 6 * mm, "PAYER / ORGANISATION INFORMATION")

    c.setFont("Helvetica", 9)
    c.drawString(x + 5 * mm, y - 11 * mm, f"Organisation: {bulk_payment['payer_name']}")
    c.drawString(x + w * 0.55, y - 11 * mm, f"Method: {bulk_payment['method']}")

    contact_y = y - 16 * mm
    if bulk_payment.get("payer_contact"):
        c.drawString(x + 5 * mm, contact_y, f"Contact: {bulk_payment['payer_contact']}")
        contact_y -= 4 * mm
    if bulk_payment.get("reference_no"):
        c.drawString(x + 5 * mm, contact_y, f"Reference: {bulk_payment['reference_no']}")

    y -= org_panel_h + PAD_SM

    # ================================================================
    # STUDENTS COVERED
    # ================================================================
    c.setFont("Helvetica-Bold", 10)
    c.drawString(x + 5 * mm, y - 5 * mm, "Students Covered:")
    y -= 8 * mm

    c.setFont("Helvetica", 9)
    for idx, item in enumerate(items, start=1):
        student_name = item["full_name"]
        grade = item["grade"]
        amount = item["amount"]
        line = f"{idx}. {student_name} ({grade})  -  KES {amount:,.2f}"
        c.drawString(x + 5 * mm, y, line)
        y -= 4 * mm
        if y < 25 * mm:
            c.showPage()
            y = h - 10 * mm
            c.setFont("Helvetica", 9)

    # ================================================================
    # AMOUNTS PANEL
    # ================================================================
    amounts_h = 3 * 6 * mm + 9 * mm
    _draw_shaded_panel(c, x, y - amounts_h, w, amounts_h)

    line_h = 6 * mm
    cur_y = y - 8 * mm
    c.setFont("Helvetica", 10)
    c.drawString(x + 5 * mm, cur_y, "Total Amount Paid:")
    c.drawRightString(x + w - 5 * mm, cur_y, f"KSh {bulk_payment['total_amount']:,.2f}")

    cur_y -= line_h
    c.drawString(x + 5 * mm, cur_y, "Students Count:")
    c.drawRightString(x + w - 5 * mm, cur_y, str(len(items)))

    cur_y -= 8 * mm
    c.saveState()
    c.setFillColor(ACCENT)
    c.setFont("Helvetica-Bold", 12)
    c.drawString(x + 5 * mm, cur_y, "TOTAL:")
    c.drawRightString(x + w - 5 * mm, cur_y, f"KSh {bulk_payment['total_amount']:,.2f}")
    c.restoreState()

    y -= amounts_h + PAD_SM

    # ================================================================
    # SIGNATURE + QR CODE
    # ================================================================
    sig_y = y - 5 * mm
    signature_path = _resolve_signature(bulk_payment.get("created_by"))

    c.saveState()
    c.setStrokeColor(colors.HexColor("#999999"))
    c.setLineWidth(0.5)
    c.line(x + 5 * mm, sig_y, x + 70 * mm, sig_y)
    c.restoreState()

    c.setFont("Helvetica", 9)
    c.drawString(
        x + 5 * mm,
        sig_y - 5 * mm,
        "Received By: Bursar",
    )

    if signature_path:
        try:
            sig_w, sig_h = ImageReader(signature_path).getSize()
            max_w, max_h = 22 * mm, 10 * mm
            scale = min(max_w / sig_w, max_h / sig_h, 1.0)
            draw_w, draw_h = sig_w * scale, sig_h * scale
            mask = "auto" if signature_path.lower().endswith(".png") else None
            c.drawImage(
                signature_path,
                x + 5 * mm,
                sig_y - draw_h - 4 * mm,
                draw_w,
                draw_h,
                mask=mask,
            )
        except Exception:
            c.drawString(
                x + 5 * mm, sig_y - 11 * mm,
                "Authorised Signature: __________________",
            )
    else:
        c.drawString(
            x + 5 * mm, sig_y - 11 * mm, "Authorised Signature: __________________"
        )

    qr_size = 16 * mm
    qr_data = f"BulkReceipt:{receipt_no}"
    _draw_qr_code(
        c,
        data=qr_data,
        x=x + w - qr_size - 2 * mm,
        y=sig_y - qr_size + 2 * mm,
        size=qr_size,
    )

    y -= 18 * mm

    # ================================================================
    # PAYMENT DETAILS FOOTER
    # ================================================================
    if payment_details:
        lines = []
        for part in payment_details.splitlines():
            part = part.strip()
            while len(part) > 90:
                idx = part.rfind(" ", 0, 90)
                if idx == -1:
                    idx = 90
                lines.append(part[:idx])
                part = part[idx:].lstrip()
            if part:
                lines.append(part)
        c.setFont("Helvetica-Oblique", 7)
        for i, line in enumerate(lines[:4]):
            c.drawCentredString(
                width / 2, y - 4 * mm - i * 3.5 * mm, line
            )
        y -= 4 * mm + min(len(lines), 4) * 3.5 * mm + PAD_SM

    # ================================================================
    # THANK YOU FOOTER
    # ================================================================
    c.setFont("Helvetica-Oblique", 8)
    c.drawCentredString(
        width / 2, y - 4 * mm, "Thank you for your kind support."
    )
    c.drawCentredString(
        width / 2,
        y - 8 * mm,
        "Please keep this receipt for future reference.",
    )

    c.showPage()
    c.save()

    conn = get_connection()
    existing = conn.execute(
        "SELECT id, print_count FROM receipts WHERE receipt_no = ?",
        (receipt_no,),
    ).fetchone()
    if existing:
        print_count = (existing["print_count"] or 1) + 1
        conn.execute(
            "UPDATE receipts SET file_path = ?, print_count = ? WHERE receipt_no = ?",
            (file_path, print_count, receipt_no),
        )
    else:
        conn.execute(
            "INSERT INTO receipts (payment_id, receipt_no, file_path, print_count) "
            "VALUES (?, ?, ?, ?)",
            (None, receipt_no, file_path, 1),
        )
    conn.commit()
    return file_path
