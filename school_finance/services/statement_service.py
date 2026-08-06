"""Generate a full fee statement PDF for one student.

Visual design (matches receipt_service so both documents feel like one system):
  - Accent color (#185FA5) for term-section labels, rules, and balance line.
  - Colored status badge (PAID / OUTSTANDING / CREDIT) computed from balance.
  - Shaded panel behind Student Information.
  - Zebra shading on alternating transaction rows for readability.
  - Outstanding balance is the largest/boldest element on the page.
  - "Page X of Y" footer via two-pass NumberedCanvas.

Robustness:
  - Page-break check fires inside charge/payment loops, not just after.
  - Table header (DATE/DESCRIPTION/DEBIT/CREDIT/BALANCE) is redrawn on every
    continuation page via a helper.
  - Terms with payments but no charges are rendered (not skipped).
  - Descriptions are truncated with an ellipsis to signal data loss.
  - Statement numbers use a DB counter (statement_counter table), not file count.
  - School name/address/motto are wrapped with c.stringWidth(), not single-line.
"""
import os
import datetime

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader

from db.database import BASE_DIR, get_connection
from models.school import get_school_info
from models.payment import list_payments_for_student, list_charges_for_student
from models.student import calculate_student_balances, get_balance, get_term_balance

STATEMENTS_DIR = os.path.join(BASE_DIR, "statements")

# --- Spacing constants (consistent vertical rhythm) ---
PAD_XS = 2 * mm
PAD_SM = 4 * mm
PAD_MD = 6 * mm
PAD_LG = 10 * mm

# --- Color palette (matches receipt_service) ---
ACCENT = colors.HexColor("#185FA5")           # deep blue accent
ACCENT_LIGHT = colors.HexColor("#E8F0F8")      # light tint for bar fills
PANEL_BG = colors.HexColor("#F5F5F5")          # light gray for shaded panels
PANEL_BORDER = colors.HexColor("#CCCCCC")
TEXT_DARK = colors.black
TEXT_MUTED = colors.HexColor("#666666")
ZEBRA_BG = colors.HexColor("#F8F9FA")          # very light gray for zebra rows
STATUS_COLORS = {
    "PAID": colors.HexColor("#2E7D32"),          # green
    "OUTSTANDING": colors.HexColor("#C62828"),   # red
    "CREDIT": colors.HexColor("#1565C0"),        # blue
}


class NumberedCanvas(canvas.Canvas):
    """Canvas subclass that draws 'Page X of Y' on every page.

    Uses a two-pass approach: content is rendered into saved page states
    during the first pass, then each page is re-emitted with the footer
    drawn once the total page count is known.
    """

    def __init__(self, *args, **kwargs):
        canvas.Canvas.__init__(self, *args, **kwargs)
        self._saved_page_states = []
        self._page_counter = 0

    def showPage(self):
        """Save current page state and start a new page (first pass)."""
        self._page_counter += 1
        # Save state excluding our own bookkeeping attributes
        state = {k: v for k, v in self.__dict__.items()
                 if k not in ('_saved_page_states', '_page_counter')}
        self._saved_page_states.append((self._page_counter, state))
        self._startPage()

    def save(self):
        """Re-emit each page with footer drawn (second pass), then save."""
        saved_states = list(self._saved_page_states)
        num_pages = len(saved_states)
        for page_num, state in saved_states:
            self.__dict__.update(state)
            self._draw_page_footer(page_num, num_pages)
            canvas.Canvas.showPage(self)
        canvas.Canvas.save(self)

    def _draw_page_footer(self, page_num, page_count):
        """Draw the 'Page X of Y' footer at the bottom of each page."""
        self.saveState()
        self.setFont("Helvetica", 8)
        self.setFillColor(TEXT_MUTED)
        self.drawCentredString(A4[0] / 2, 8 * mm,
                               f"Page {page_num} of {page_count}")
        self.restoreState()


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


def _draw_status_badge(c, x, y, status, width=32 * mm, height=7 * mm):
    """Draw a colored status badge as a filled rounded rectangle with white text."""
    color = STATUS_COLORS.get(status, colors.grey)
    c.saveState()
    c.setFillColor(color)
    c.setStrokeColor(color)
    c.roundRect(x, y, width, height, 2 * mm, fill=1, stroke=1)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 9)
    c.drawCentredString(x + width / 2, y + 2 * mm, status)
    c.restoreState()


def _truncate_desc(text, max_len=35):
    """Truncate a description to *max_len* characters, adding an ellipsis if cut."""
    if not text:
        return ""
    if len(text) <= max_len:
        return text
    return text[:max_len - 1] + "\u2026"


def _format_date(date_str):
    """Extract YYYY-MM-DD from a datetime/date string, with fallback."""
    if not date_str:
        return ""
    return date_str[:10]


def _draw_table_header(c, x, table_y, col_widths, col_labels):
    """Draw the DATE/DESCRIPTION/DEBIT/CREDIT/BALANCE header row.

    Called at the top of the table and after every page break so that
    continuation pages always have labeled columns.

    Returns the updated y-cursor (below the header + rule).
    """
    c.saveState()
    c.setFont("Helvetica-Bold", 9)
    c.setFillColor(ACCENT)
    cx = x
    for label, cw in zip(col_labels, col_widths):
        c.drawString(cx, table_y, label)
        cx += cw
    c.restoreState()
    table_y -= 4 * mm
    _draw_accent_rule(c, x, table_y, x + sum(col_widths),
                      color=ACCENT, width=1.0)
    table_y -= 3 * mm
    return table_y


def _get_term_allocated_payments(student_id, term_id):
    """Get total payments allocated to a specific term via FIFO."""
    conn = get_connection()
    row = conn.execute(
        "SELECT COALESCE(SUM(pa.amount), 0) AS total FROM payment_allocations pa "
        "JOIN charges c ON pa.charge_id = c.id "
        "WHERE c.student_id = ? AND c.term_id = ?",
        (student_id, term_id),
    ).fetchone()
    return row["total"] if row else 0.0


def _get_term_waivers(student_id, term_id):
    """Return active (non-revoked) waiver rows for a student in a term."""
    conn = get_connection()
    return [dict(r) for r in conn.execute(
        "SELECT w.*, c.amount AS gross_amount, c.description, "
        "t.term_name, t.year "
        "FROM waivers w "
        "JOIN charges c ON w.charge_id = c.id "
        "JOIN terms t ON w.term_id = t.id "
        "WHERE w.student_id = ? AND w.term_id = ? AND w.revoked_at IS NULL "
        "ORDER BY w.granted_at",
        (student_id, term_id),
    ).fetchall()]


def _next_statement_no(year):
    """Get the next statement number using a DB counter (per-year).

    Uses a ``statement_counter`` table so that deleting or moving PDF files
    does not cause number collisions.  The counter is scoped per year,
    matching the ``ST-{year}-####`` format.
    """
    conn = get_connection()
    conn.execute(
        "CREATE TABLE IF NOT EXISTS statement_counter ("
        "year INTEGER PRIMARY KEY, last_number INTEGER NOT NULL DEFAULT 0)"
    )
    row = conn.execute(
        "SELECT last_number FROM statement_counter WHERE year = ?", (year,)
    ).fetchone()
    if row:
        next_num = row["last_number"] + 1
        conn.execute(
            "UPDATE statement_counter SET last_number = ? WHERE year = ?",
            (next_num, year),
        )
    else:
        next_num = 1
        conn.execute(
            "INSERT INTO statement_counter (year, last_number) VALUES (?, ?)",
            (year, next_num),
        )
    conn.commit()
    return f"ST-{year}-{next_num:04d}"


def generate_statement(student, term_id=None, year=None):
    """student: sqlite3.Row from students table. term_id: optional term filter. year: optional year filter."""
    student = dict(student)
    conn = get_connection()

    all_charges = list_charges_for_student(student["id"])
    all_payments = list_payments_for_student(student["id"])
    balance = get_balance(student["id"])

    term_balances = calculate_student_balances(student["id"])

    terms = conn.execute(
        "SELECT * FROM terms ORDER BY year ASC, "
        "CASE term_name WHEN 'Term I' THEN 1 WHEN 'Term II' THEN 2 WHEN 'Term III' THEN 3 END ASC"
    ).fetchall()

    if year:
        terms = [t for t in terms if t["year"] == year]
    if term_id:
        terms = [t for t in terms if t["id"] == term_id]

    info = get_school_info()
    school_name = info.get("school_name") or "SCHOOL NAME HERE"
    motto = info.get("motto") or ""
    address = info.get("address") or ""
    phone = info.get("phone") or ""
    email = info.get("email") or ""
    logo_path = info.get("logo_path") or ""
    payment_details = info.get("payment_details") or ""

    term = None
    if term_id:
        from models.term import get_term
        term = get_term(term_id)
    term_name = term["term_name"] if term else "N/A"
    year_for_label = term["year"] if term else (year or datetime.datetime.now().year)

    statement_no = _next_statement_no(year_for_label)

    now = datetime.datetime.now()
    statement_date = now.strftime("%d %B %Y")
    if term:
        period_start = datetime.datetime(term["year"], 1, 1).strftime("%B %Y")
        period_end = now.strftime("%B %Y")
        period = f"{period_start} \u2013 {period_end}"
    elif year:
        period = f"January {year} \u2013 December {year}"
    else:
        period_start = datetime.datetime(now.year, 1, 1).strftime("%B %Y")
        period_end = now.strftime("%B %Y")
        period = f"{period_start} \u2013 {period_end}"

    os.makedirs(STATEMENTS_DIR, exist_ok=True)
    safe_name = "".join(ch for ch in student["full_name"] if ch.isalnum() or ch == " ").strip()
    file_name = f"Statement_{safe_name.replace(' ', '_')}_{student['id']}.pdf"
    file_path = os.path.join(STATEMENTS_DIR, file_name)

    c = NumberedCanvas(file_path, pagesize=A4)
    width, height = A4

    margin = 12 * mm
    x = margin
    y = height - margin
    w = width - 2 * margin

    # ================================================================
    # HEADER SECTION (shaded panel, dynamic height, wrapped text)
    # ================================================================
    # Compute school name wrapping (needs canvas for stringWidth)
    name_lines = _wrap_text(c, school_name, "Helvetica-Bold", 14, w - 10 * mm)
    name_size = 14
    if len(name_lines) > 2:
        name_size = 12
        while name_size > 10 and len(
            _wrap_text(c, school_name, "Helvetica-Bold", name_size, w - 10 * mm)
        ) > 2:
            name_size -= 0.5
        name_lines = _wrap_text(
            c, school_name, "Helvetica-Bold", name_size, w - 10 * mm
        )

    # Compute header height: base (logo+name) + 5mm per optional field + padding
    optional_count = sum(1 for f in (motto, address, phone, email) if f)
    header_h = 32 * mm  # base: logo space + name
    if len(name_lines) > 1:
        header_h += 5 * mm  # extra line for wrapped name
    header_h += optional_count * 5 * mm + PAD_SM

    _draw_shaded_panel(c, x, y - header_h, w, header_h, fill_color=colors.white)

    # Logo (centered at top)
    logo_bottom = y
    if logo_path and os.path.isfile(logo_path):
        try:
            img_w, img_h = ImageReader(logo_path).getSize()
            max_w, max_h = 28 * mm, 22 * mm
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

    # Motto (wrapped, centered)
    if motto:
        motto_lines = _wrap_text(c, f'"{motto}"', "Helvetica-Oblique", 9, w - 10 * mm)
        c.setFont("Helvetica-Oblique", 9)
        for line in motto_lines[:2]:
            c.drawCentredString(width / 2, text_y, line)
            text_y -= 4 * mm

    # Address (wrapped, centered)
    if address:
        addr_lines = _wrap_text(c, address, "Helvetica", 9, w - 10 * mm)
        c.setFont("Helvetica", 9)
        for line in addr_lines[:2]:
            c.drawCentredString(width / 2, text_y, line)
            text_y -= 4 * mm

    # Phone
    if phone:
        c.setFont("Helvetica", 9)
        c.drawCentredString(width / 2, text_y, f"Tel: {phone}")
        text_y -= 4 * mm

    # Email
    if email:
        c.setFont("Helvetica", 9)
        c.drawCentredString(width / 2, text_y, f"Email: {email}")

    y -= header_h + PAD_SM

    # ================================================================
    # STATEMENT BAR + STATUS BADGE
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
    c.drawCentredString(width / 2, y - 7 * mm, "STUDENT FEE STATEMENT")

    # Status badge (right side of bar)
    status = "PAID" if balance == 0 else ("OUTSTANDING" if balance > 0 else "CREDIT")
    badge_w = 32 * mm
    badge_h = 7 * mm
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
    # STATEMENT DETAILS (Statement No, Date, Year, Term, Period)
    # ================================================================
    c.setFont("Helvetica-Bold", 10)
    c.drawString(x, y - 5 * mm, f"Statement No: {statement_no}")
    c.setFont("Helvetica", 10)
    c.drawString(x + w * 0.55, y - 5 * mm, f"Statement Date: {statement_date}")
    c.drawString(x, y - 11 * mm, f"Academic Year: {year_for_label}")
    c.drawString(x + w * 0.55, y - 11 * mm, f"Term: {term_name}")
    c.drawString(x, y - 17 * mm, f"Period: {period}")

    y -= 19 * mm + PAD_SM

    # ================================================================
    # STUDENT INFORMATION PANEL (shaded)
    # ================================================================
    panel_h = 18 * mm
    _draw_shaded_panel(c, x, y - panel_h, w, panel_h)

    c.setFont("Helvetica-Bold", 10)
    c.drawCentredString(width / 2, y - 6 * mm, "STUDENT INFORMATION")

    student_class = student["grade"]
    if student["stream"]:
        student_class = f"{student['grade']} {student['stream']}"
    c.setFont("Helvetica", 9)
    c.drawString(x + 5 * mm, y - 12 * mm, f"Student Name: {student['full_name']}")
    c.drawString(x + 5 * mm, y - 16 * mm,
                 f"Admission No: {student['admission_no'] or '-'}")
    c.drawString(x + w * 0.55, y - 16 * mm, f"Class: {student_class}")

    y -= panel_h + PAD_SM

    # ================================================================
    # TRANSACTION TABLE
    # ================================================================
    col_widths = [22 * mm, 55 * mm, 22 * mm, 22 * mm, 25 * mm]
    col_labels = ["DATE", "DESCRIPTION", "DEBIT", "CREDIT", "BALANCE"]
    table_y = y - 2 * mm

    # Draw header row (also used for continuation pages)
    table_y = _draw_table_header(c, x, table_y, col_widths, col_labels)

    c.setFont("Helvetica", 9)
    running = 0.0
    total_debit = 0.0
    total_credit = 0.0
    total_waiver = 0.0
    row_index = 0  # for zebra shading

    def _check_page_break():
        """If we're near the bottom, start a new page and redraw the header."""
        nonlocal table_y, row_index
        if table_y < 30 * mm:
            c.showPage()
            table_y = height - 20 * mm
            table_y = _draw_table_header(c, x, table_y, col_widths, col_labels)
            row_index = 0  # reset zebra on new page

    for term in terms:
        term_charges = [ch for ch in all_charges if ch["term_id"] == term["id"]]
        term_payments = [p for p in all_payments if p["term_id"] == term["id"]]

        # Render if the term has either charges or payments (not just charges)
        if not term_charges and not term_payments:
            continue

        # Check page break before starting a new term section
        _check_page_break()

        term_key = f"{term['term_name']} {term['year']}"

        # Term section label in accent color
        c.saveState()
        c.setFillColor(ACCENT)
        c.setFont("Helvetica-Bold", 10)
        c.drawString(x, table_y, term_key)
        c.restoreState()
        _draw_accent_rule(c, x, table_y - 2 * mm, x + sum(col_widths),
                          color=ACCENT_LIGHT, width=0.8)
        table_y -= 6 * mm

        # Charges
        for ch in term_charges:
            _check_page_break()

            # Zebra shading
            if row_index % 2 == 1:
                c.saveState()
                c.setFillColor(ZEBRA_BG)
                c.rect(x, table_y - 1 * mm, sum(col_widths), 5 * mm,
                       fill=1, stroke=0)
                c.restoreState()

            date_str = _format_date(ch["date_added"])
            desc = _truncate_desc(ch["description"] or "Charge")
            running += ch["amount"]
            total_debit += ch["amount"]
            c.setFont("Helvetica", 9)
            c.drawString(x, table_y, date_str)
            c.drawString(x + col_widths[0], table_y, desc)
            c.drawRightString(
                x + col_widths[0] + col_widths[1] + col_widths[2], table_y,
                f"{ch['amount']:,.2f}")
            c.drawRightString(
                x + col_widths[0] + col_widths[1] + col_widths[2] + col_widths[3],
                table_y, "\u2014")
            c.drawRightString(
                x + sum(col_widths), table_y, f"{running:,.2f}")
            table_y -= 5 * mm
            row_index += 1

        # Wavier rows (credits that reduce the net amount owed)
        term_waivers = _get_term_waivers(student["id"], term["id"])
        for wv in term_waivers:
            _check_page_break()

            # Zebra shading
            if row_index % 2 == 1:
                c.saveState()
                c.setFillColor(ZEBRA_BG)
                c.rect(x, table_y - 1 * mm, sum(col_widths), 5 * mm,
                       fill=1, stroke=0)
                c.restoreState()

            date_str = _format_date(wv["granted_at"])
            desc = _truncate_desc(
                (wv["reason"] or "Fee Waiver")
                + (f" (Charge: {wv['description'] or 'Fee'})" if wv["description"] else "")
            )
            running -= wv["amount"]
            total_waiver += wv["amount"]
            c.setFont("Helvetica", 9)
            c.setFillColor(colors.HexColor("#2E7D32"))  # green for waiver
            c.drawString(x, table_y, date_str)
            c.drawString(x + col_widths[0], table_y, desc)
            c.drawRightString(
                x + col_widths[0] + col_widths[1] + col_widths[2], table_y,
                "\u2014")
            c.drawRightString(
                x + col_widths[0] + col_widths[1] + col_widths[2] + col_widths[3],
                table_y, f"{wv['amount']:,.2f}")
            c.drawRightString(
                x + sum(col_widths), table_y, f"{running:,.2f}")
            c.setFillColor(colors.black)
            table_y -= 5 * mm
            row_index += 1

        # Payments
        allocated = _get_term_allocated_payments(student["id"], term["id"])
        if allocated > 0:
            for p in term_payments:
                _check_page_break()

                # Zebra shading
                if row_index % 2 == 1:
                    c.saveState()
                    c.setFillColor(ZEBRA_BG)
                    c.rect(x, table_y - 1 * mm, sum(col_widths), 5 * mm,
                           fill=1, stroke=0)
                    c.restoreState()

                date_str = _format_date(p["date_paid"])
                desc = _truncate_desc(
                    f"{p['method']} Payment"
                    + (f" ({p['receipt_no']})" if p["receipt_no"] else "")
                )
                running -= p["amount"]
                total_credit += p["amount"]
                c.setFont("Helvetica", 9)
                c.drawString(x, table_y, date_str)
                c.drawString(x + col_widths[0], table_y, desc)
                c.drawRightString(
                    x + col_widths[0] + col_widths[1] + col_widths[2], table_y,
                    "\u2014")
                c.drawRightString(
                    x + col_widths[0] + col_widths[1] + col_widths[2] + col_widths[3],
                    table_y, f"{p['amount']:,.2f}")
                c.drawRightString(
                    x + sum(col_widths), table_y, f"{running:,.2f}")
                table_y -= 5 * mm
                row_index += 1

        # Term balance line
        _check_page_break()
        term_bal = term_balances.get(term["id"], 0.0)
        c.setFont("Helvetica-Bold", 9)
        c.drawString(x, table_y, f"Balance for {term_key}:")
        c.drawRightString(x + sum(col_widths), table_y,
                          f"KSh {term_bal:,.2f}")
        table_y -= 6 * mm
        row_index = 0  # reset zebra for next term

    # ================================================================
    # TOTALS + OUTSTANDING BALANCE (shaded panel — visual focal point)
    # Layout:
    #   Total Charges (Gross):     KSh X
    #   Less: Fee Waivers:         KSh X   (if waivers exist)
    #   Net Amount Billed:         KSh X   (if waivers exist)
    #   Total Payments Received:   KSh X
    #   OUTSTANDING BALANCE:       KSh X
    # ================================================================
    _check_page_break()
    table_y -= 3 * mm

    # Calculate panel height based on content
    totals_lines = 3  # gross, payments, balance
    if total_waiver > 0:
        totals_lines += 2  # waiver + net
    totals_h = totals_lines * 6 * mm + 9 * mm
    _draw_shaded_panel(c, x, table_y - totals_h, w, totals_h)

    line_h = 6 * mm
    cur_y = table_y - 8 * mm

    # Total Charges (Gross)
    c.setFont("Helvetica", 10)
    c.drawString(x + 5 * mm, cur_y, "Total Charges (Gross):")
    c.drawRightString(x + w - 5 * mm, cur_y,
                      f"KSh {total_debit:,.2f}")

    # Less: Fee Waivers + Net Amount Billed (if waivers exist)
    if total_waiver > 0:
        cur_y -= line_h
        c.setFont("Helvetica", 9)
        c.setFillColor(colors.HexColor("#2E7D32"))  # green for credit
        c.drawString(x + 5 * mm, cur_y, "Less: Fee Waivers:")
        c.drawRightString(x + w - 5 * mm, cur_y,
                          f"KSh {total_waiver:,.2f}")
        c.setFillColor(colors.black)

        cur_y -= line_h
        c.setFont("Helvetica-Bold", 9)
        c.drawString(x + 5 * mm, cur_y, "Net Amount Billed:")
        c.drawRightString(x + w - 5 * mm, cur_y,
                          f"KSh {total_debit - total_waiver:,.2f}")

    # Total Payments Received
    cur_y -= line_h
    c.setFont("Helvetica", 10)
    c.drawString(x + 5 * mm, cur_y, "Total Payments Received:")
    c.drawRightString(x + w - 5 * mm, cur_y,
                      f"KSh {total_credit:,.2f}")

    # Outstanding balance — largest/boldest element (visual focal point)
    cur_y -= 8 * mm
    c.saveState()
    c.setFillColor(ACCENT)
    c.setFont("Helvetica-Bold", 14)
    c.drawString(x + 5 * mm, cur_y, "OUTSTANDING BALANCE:")
    c.drawRightString(x + w - 5 * mm, cur_y,
                      f"KSh {balance:,.2f}")
    c.restoreState()

    table_y -= totals_h + PAD_SM

    # ================================================================
    # STATUS BADGE (bottom)
    # ================================================================
    _check_page_break()
    status_panel_h = 10 * mm
    _draw_shaded_panel(c, x, table_y - status_panel_h, w, status_panel_h)

    c.setFont("Helvetica-Bold", 10)
    c.drawString(x + 5 * mm, table_y - 6 * mm, "PAYMENT STATUS:")
    _draw_status_badge(
        c,
        x + 45 * mm,
        table_y - 8 * mm,
        status,
        width=32 * mm,
        height=7 * mm,
    )

    table_y -= status_panel_h + PAD_LG

    # ================================================================
    # FOOTER NOTES
    # ================================================================
    c.setFont("Helvetica", 9)
    c.drawString(x + 5 * mm, table_y,
                 "Please clear the outstanding balance by the required payment date.")
    table_y -= 5 * mm
    c.drawString(x + 5 * mm, table_y,
                 f"Generated By: {payment_details or 'School Management System'}")
    table_y -= 5 * mm
    c.drawString(x + 5 * mm, table_y, f"Generated On: {statement_date}")
    table_y -= 5 * mm
    c.drawString(x + 5 * mm, table_y, "This is a computer-generated statement.")

    c.showPage()
    c.save()
    return file_path