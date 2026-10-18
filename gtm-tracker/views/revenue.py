import pandas as pd
import streamlit as st

import data
import fmt
import ui
from views import charts, leads
from views.common import header, num, pick, section, tiles

KIND = {"program": "Full program", "trial_3m": "3-month trial"}


def pick_lead(table, lead_ids, key, goes_to="rv_lead"):
    """Show a payments table in a dialog where clicking a row opens that row's lead (a dialog cannot open another, so the page does it on the rerun)."""
    lead = pick(table, lead_ids, key, 460)
    if not fmt.missing(lead) and lead != "-":
        st.session_state[goes_to] = lead
        st.rerun()


def open_records(stream, start, end):
    """The payments behind one breakdown row, in a dialog (the way leads open on the Leads page)."""
    rows = data.query("revenue", "cash_records", start, end, stream=stream)

    @st.dialog(stream, width="large", on_dismiss="rerun")
    def body():
        total = rows["amount"].sum() if len(rows) else 0
        st.caption(f"{len(rows):,} payments, {fmt.inr(total)} total, collected {start:%d %b} to {end:%d %b %Y}. Newest first.")
        if rows.empty:
            st.info("No payments in this period.")
            return
        who = "Lead" if stream == "Workshop seats" else "Student"
        table = pd.DataFrame({"Paid on": rows["paid_on"].map(fmt.date), "Reference": rows["reference"], who: rows["who"],
                              "Enrolled on": rows["enrolled_on"].map(fmt.date),
                              "Amount": rows["amount"].map(fmt.inr)})
        if stream == "Workshop seats":
            table = table.drop(columns="Enrolled on")
            st.caption("Click a payment to open its lead.")
            pick_lead(table, rows["who"], "cash_pay")
        else:
            st.caption("Click a payment to open the student's enrollment and invoices.")
            pick_lead(table, rows["enrollment_id"], "cash_pay_students", "rv_enrollment")
    body()


def open_onboarded(month, start, end):
    """The students onboarded in one month, in a dialog."""
    rows = data.query("revenue", "onboarded_students", start, end, month=month)

    @st.dialog(f"{pd.Timestamp(month):%b %Y} onboarding", width="large", on_dismiss="rerun")
    def body():
        st.caption(f"{len(rows):,} students enrolled, newest first. Click one to open their enrollment and invoices.")
        table = pd.DataFrame({"Enrolled on": rows["started_on"].map(fmt.date), "Student": rows["student_id"], "Enrollment": rows["enrollment_id"],
                              "Construct": rows["kind"].map(KIND), "Contract value": rows["amount"].map(fmt.inr)})
        pick_lead(table, rows["enrollment_id"], "onboarded_students_table", "rv_enrollment")
    body()


def open_workshop(workshop_id, start, end):
    """The payments for one workshop, in a dialog."""
    rows = data.query("revenue", "workshop_payments_for", start, end, workshop_id=workshop_id)

    @st.dialog(workshop_id, width="large", on_dismiss="rerun")
    def body():
        st.caption(f"{len(rows):,} payments, {int(rows['seats'].sum()) if len(rows) else 0} seats, {fmt.inr(rows['amount'].sum() if len(rows) else 0)} total. Newest first.")
        if rows.empty:
            st.info("No payments for this workshop yet.")
            return
        table = pd.DataFrame({"Paid on": rows["paid_on"].map(fmt.date), "Reference": rows["reference"], "Lead": rows["who"],
                              "Seats": rows["seats"], "Amount": rows["amount"].map(fmt.inr)})
        st.caption("Click a payment to open its lead.")
        pick_lead(table, rows["who"], "workshop_pay")
    body()


def open_invoice(enrollment_id, invoice_id, end):  # invoice_id None titles the dialog by the enrollment alone
    """The student behind an unpaid invoice, in a dialog: who they are, where they came from, and all their invoices."""
    rows = data.query("revenue", "enrollment_invoices", end, end, enrollment_id=enrollment_id)

    @st.dialog(f"{invoice_id} · {enrollment_id}" if invoice_id else enrollment_id, width="large", on_dismiss="rerun")
    def body():
        if rows.empty:
            st.info("No invoices known for this enrollment.")
            return
        r = rows.iloc[0]
        paid = rows["amount"][rows["paid_on"].notna()].sum()
        st.markdown(ui.facts([("Student", r["student_id"]), ("Lead name", r["student_name"]), ("Construct", KIND[r["kind"]]), ("Enrolled", fmt.date(r["started_on"])),
                              ("Trial ends", fmt.date(r["renewal_on"])),
                              ("Campaign", r["campaign_name"]), ("Contract value", fmt.inr(r["contract"])), ("Invoiced", fmt.inr(rows["amount"].sum())),
                              ("Paid", fmt.inr(paid)), ("Unpaid", fmt.inr(rows["amount"].sum() - paid))]), unsafe_allow_html=True)
        st.markdown("**Invoices**")
        table = pd.DataFrame({"Invoice": rows["invoice_id"], "Issued": rows["issued_on"].map(fmt.date),
                              "Due": rows["due_on"].map(fmt.date), "Amount": rows["amount"].map(fmt.inr),
                              "Paid on": rows["paid_on"].map(lambda d: "Unpaid" if fmt.missing(d) else fmt.date(d))})
        st.dataframe(table, hide_index=True, width="stretch", height=min(35 * (len(table) + 1) + 3, 300))
        if r["lead_id"]:
            if st.button("Open the lead's full journey"):
                st.session_state["rv_lead"] = r["lead_id"]
                st.rerun()
    body()


def page():
    start, end = header("Revenue", "Cash collected against target, how students enrolled, and what is still owed.")

    lead, enrollment = st.session_state.pop("rv_lead", None), st.session_state.pop("rv_enrollment", None)
    if lead:
        leads.open_lead(lead, end)
    elif enrollment:
        open_invoice(enrollment, None, end)

    section("Target vs achievement", "Cash collected in the selected period against its share of the monthly targets (each day carries its month's target divided by the days in that month).")
    tv = data.query("revenue", "target_vs_actual", start, end).iloc[0]
    actual, target = num(tv["actual"]), num(tv["target"])
    gap = None if target is None else actual - target
    tiles([("Achieved in the period", fmt.inr(actual), f"{start:%d %b} to {end:%d %b}", None), ("Target for the period", fmt.inr(target), "prorated from the monthly targets", None),
           ("Ahead of target" if gap is None or gap >= 0 else "Behind target", fmt.inr(None if gap is None else abs(gap)), None, None)])
    st.markdown(ui.meter(actual, target), unsafe_allow_html=True)

    section("Where the achieved number comes from", "The achieved cash split by what was paid for. Click a row to see its payments.")
    parts = data.query("revenue", "cash_breakdown", start, end)
    total = parts["amount"].sum()
    st.markdown("**From this period's sign-ups to the achieved number**")
    charts.bridge_bars(charts.bridge_steps(parts.to_dict("records")))
    table = pd.DataFrame({"What was paid for": parts["stream"],
                          "Students enrolled": parts["students"].map(fmt.num),
                          "Contract value": parts["contract"].map(fmt.inr),
                          "Paid so far": parts["paid_new"].map(fmt.inr),
                          "Not collected yet": parts["not_collected"].map(fmt.inr),
                          "Paid by earlier students": parts["earlier"].map(fmt.inr),
                          "Cash collected": parts["amount"].map(fmt.inr),
                          "Share": parts["amount"].map(lambda a: fmt.pct(a / total) if total else fmt.DASH), "Payments": parts["payments"]})
    opened = pick(table, parts["stream"], "revenue_table") or st.session_state.get("rv_open")
    if opened:
        open_records(opened, start, end)

    section("3-month trial vs full program", "Students who enrolled in the period, by construct.")
    split = data.query("revenue", "signup_split", start, end)
    if split.empty:
        st.info("No sign-ups in this period.")
    else:
        split["Construct"] = split["kind"].map(KIND)
        tiles([(row["Construct"], fmt.num(row["students"]), "students enrolled in the period", None) for _, row in split.iterrows()])
        charts.hbars(split, "Construct", "students", color="kind", domain=["program", "trial_3m"])

    section("Students onboarded", "Enrollments started, by month.")
    onboarded = data.query("revenue", "onboarded_monthly", start, end)
    if not onboarded.empty:
        onboarded["Month"] = pd.to_datetime(onboarded["month"]).dt.strftime("%b %Y")
        charts.columns(onboarded, "Month", "students")
        st.caption("Click a month to see its students.")
        month = pick(onboarded[["Month", "students"]], onboarded["month"], "onboarded_table")
        if month is not None:
            open_onboarded(month, start, end)
    else:
        st.info("No sign-ups in this period.")

    section("Program vs workshop revenue", "Cash collected in the period.")
    pw = data.query("revenue", "program_vs_workshop", start, end).set_index("stream")["amount"]
    pw_total = pw.sum()
    tiles([("Program", fmt.inr(pw["program"]), fmt.pct(pw["program"] / pw_total) + " of cash" if pw_total else None, None),
           ("Workshop", fmt.inr(pw["workshop"]), fmt.pct(pw["workshop"] / pw_total) + " of cash" if pw_total else None, None)])

    section("Workshop revenue", "Rs 3,999 per seat, from Razorpay, one workshop a fortnight.")
    ws = data.query("revenue", "workshop_revenue", start, end)
    if ws.empty:
        st.info("No workshop was held in this period.")
    else:
        ws["Workshop"] = pd.to_datetime(ws["held_on"]).dt.strftime("%d %b")
        tiles([("Workshops held", fmt.num(len(ws)), None, None), ("Seats sold", fmt.num(ws["seats"].sum()), None, None), ("Revenue", fmt.inr(ws["amount"].sum()), None, None)])
        charts.columns(ws, "Workshop", "amount", fmt="~s")
        st.caption("Click a workshop to see its payments.")
        workshop = pick(ws[["workshop_id", "held_on", "seats", "amount"]], ws["workshop_id"], "workshop_table")
        if workshop:
            open_workshop(workshop, start, end)

    section("Unpaid invoices", "Invoices issued in the period that were still unpaid on its last day. A short period hides older unpaid invoices; widen it to see them.")
    unpaid = data.query("revenue", "unpaid_invoices", start, end)
    overdue = unpaid[unpaid["days_overdue"] > 0] if not unpaid.empty else unpaid
    tiles([("Unpaid invoices", fmt.num(len(unpaid)), fmt.inr(unpaid["amount"].sum() if len(unpaid) else 0) + " owed", None),
           ("Past due", fmt.num(len(overdue)), fmt.inr(overdue["amount"].sum() if len(overdue) else 0) + " overdue", None)])
    if unpaid.empty:
        st.info("No unpaid invoices in this period.")
    else:
        st.caption("Click an invoice to see the student and where they came from.")
        top = unpaid.head(10).reset_index(drop=True)
        table = pd.DataFrame({"Invoice": top["invoice_id"], "Enrollment": top["enrollment_id"], "Amount": top["amount"].map(fmt.inr),
                              "Due": top["due_on"].map(lambda d: f"{d:%d %b}"), "Days overdue": top["days_overdue"].map(fmt.num)})
        invoice = pick(table, top["invoice_id"], "unpaid_table")
        if invoice:
            open_invoice(top.set_index("invoice_id").loc[invoice, "enrollment_id"], invoice, end)

    section("Renewals coming up", f"3-month trial students whose trial ends in the {data.config()['renewals']['lookahead_days']} days after the period's last day. This does not change with the timeline's start day.")
    st.caption("Forward-looking, so it does not change with the timeline when you only move the start day.")
    renewals = data.query("revenue", "upcoming_renewals", start, end)
    if renewals.empty:
        st.info("No trials end in this window.")
        return
    st.caption("Click a student to see their invoices and where they came from.")
    table = pd.DataFrame({"Student": renewals["student_id"], "Trial ends": renewals["renewal_on"].map(lambda d: f"{d:%d %b %Y}"),
                          "Days left": renewals["days_left"].map(fmt.num), "Trial value": renewals["amount"].map(fmt.inr)})
    enrollment = pick(table, renewals["enrollment_id"], "renewal_table")
    if enrollment:
        open_invoice(enrollment, None, end)
