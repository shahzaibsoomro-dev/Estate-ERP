"""Built-in document templates. Seeded once (by code); staff can edit or add their own."""

HEADER = """<div class="doc-head">
  <div><div class="doc-brand">{{company.name}}</div><div class="doc-sub">{{company.address}}</div><div class="doc-sub">{{company.phone}} {{company.email}}</div></div>
  <div class="doc-meta">Document <b>{{doc.no}}</b><br>Date <b>{{today}}</b></div>
</div>"""

PARTIES = """<div class="doc-grid">
  <div><span>Customer:</span> <b>{{customer.name}}</b></div>
  <div><span>CNIC:</span> {{customer.cnic}}</div>
  <div><span>S/O, D/O, W/O:</span> {{customer.father_name}}</div>
  <div><span>Phone:</span> {{customer.phone}}</div>
  <div><span>Project:</span> {{project.name}}</div>
  <div><span>Unit:</span> <b>{{unit.no}}</b> {{unit.type}}</div>
  <div><span>Booking no:</span> {{booking.no}}</div>
  <div><span>Booking date:</span> {{booking.date}}</div>
</div>"""

FOOT = """<div class="doc-foot">This is a system-generated document from {{company.name}}. Figures are as of {{today}}. For queries contact {{company.contact}}.</div>"""

DEFAULT_TEMPLATES = [
    {
        "code": "payment_plan",
        "name": "Payment Plan Schedule",
        "kind": "payment_plan",
        "description": "Full installment schedule with paid and outstanding amounts.",
        "body_html": HEADER + """
<h1>Payment Plan Schedule</h1>
""" + PARTIES + """
<div class="doc-box"><b>Sale price:</b> {{booking.sale_price}} &nbsp;·&nbsp; <b>Paid:</b> {{booking.paid}} ({{booking.pct_paid}}) &nbsp;·&nbsp; <b>Balance:</b> {{booking.outstanding}}</div>
<h2>Installments</h2>
{{table.installments}}
<p class="doc-muted">Milestone installments become due when construction reaches the stated stage. Please pay on or before each due date.</p>
""" + FOOT,
    },
    {
        "code": "allotment_letter",
        "name": "Allotment Letter",
        "kind": "letter",
        "description": "Confirms allotment of the unit to the customer.",
        "body_html": HEADER + """
<h1>Provisional Allotment Letter</h1>
<p>Dear <b>{{customer.name}}</b>,</p>
<p>We are pleased to confirm the provisional allotment of <b>Unit {{unit.no}}</b> ({{unit.type}}, floor {{unit.floor}}, {{unit.area}} sq. yd) in <b>{{project.name}}</b>, {{project.location}}, against booking <b>{{booking.no}}</b> dated {{booking.date}}.</p>
<div class="doc-grid">
  <div><span>Total sale price:</span> <b>{{booking.sale_price}}</b></div>
  <div><span>Booking amount:</span> {{booking.down_payment}}</div>
  <div><span>CNIC:</span> {{customer.cnic}}</div>
  <div><span>Expected possession:</span> {{booking.possession_date}}</div>
</div>
<p>This allotment is subject to timely payment of all installments as per the agreed payment plan, and to the terms and conditions of the sale agreement.</p>
<div class="doc-sign"><div>Authorised signatory</div><div>Customer signature</div></div>
""" + FOOT,
    },
    {
        "code": "statement_of_account",
        "name": "Statement of Account",
        "kind": "statement",
        "description": "Payments received and current balance.",
        "body_html": HEADER + """
<h1>Statement of Account</h1>
""" + PARTIES + """
<div class="doc-grid">
  <div><span>Sale price:</span> <b>{{booking.sale_price}}</b></div>
  <div><span>Total received:</span> <b>{{booking.paid}}</b></div>
  <div><span>Outstanding:</span> <b>{{booking.outstanding}}</b></div>
  <div><span>Overdue now:</span> <b>{{booking.overdue_amount}}</b></div>
</div>
<h2>Payments received</h2>
{{table.payments}}
""" + FOOT,
    },
    {
        "code": "demand_notice",
        "name": "Payment Demand Notice",
        "kind": "notice",
        "description": "Reminder listing overdue installments.",
        "body_html": HEADER + """
<h1>Payment Demand Notice</h1>
<p>Dear <b>{{customer.name}}</b> (CNIC {{customer.cnic}}),</p>
<p>Our records show the following installments for <b>Unit {{unit.no}}</b>, <b>{{project.name}}</b> (booking {{booking.no}}) are overdue:</p>
{{table.overdue}}
<div class="doc-box">Total overdue: <b>{{booking.overdue_amount}}</b>. Kindly clear the outstanding amount within 15 days of this notice to avoid late-payment charges as per your agreement.</div>
<p>If you have already paid, please share the payment reference with our office so we can update your account.</p>
<div class="doc-sign"><div>Recovery department</div><div></div></div>
""" + FOOT,
    },
]


def seed_default_templates(conn) -> None:
    for t in DEFAULT_TEMPLATES:
        conn.execute(
            """INSERT OR IGNORE INTO document_templates(code, name, kind, description, body_html, requires_booking)
               VALUES(?,?,?,?,?,1)""",
            (t["code"], t["name"], t["kind"], t["description"], t["body_html"]),
        )
    for key, val in (("company_name", "Haven Builders"), ("company_address", ""),
                     ("company_phone", ""), ("company_email", "")):
        conn.execute("INSERT OR IGNORE INTO company_settings(key, value) VALUES(?, ?)", (key, val))


def upgrade_default_templates(conn) -> None:
    """Fix-ups for built-in templates that staff have not edited."""
    conn.execute(
        """UPDATE document_templates
           SET body_html = REPLACE(body_html, 'For queries contact {{company.phone}}.', 'For queries contact {{company.contact}}.')
           WHERE code IS NOT NULL AND created_by IS NULL AND updated_at = created_at"""
    )
