import logging
from datetime import date
from sqlalchemy import func, or_, and_
from app.database import SessionLocal
from app.models.config import LabGroup, Lab, LabIcAssignment, Budget, BudgetPeriod
from app.models.staging import PurchaseRequestLine, PurchaseRequest
from app.models.auth import User
from app.services.email_service import send_threshold_alert

logger = logging.getLogger(__name__)


def check_and_notify_lab_thresholds(lab_id: int):
    with SessionLocal() as db:
        lab = db.query(Lab).filter(Lab.lab_id == lab_id).first()
        if not lab:
            return

        # 1. Determine the CURRENT Fiscal Year based on today's date
        today = date.today()
        current_period = (
            db.query(BudgetPeriod)
            .filter(BudgetPeriod.start_date <= today, BudgetPeriod.end_date >= today)
            .first()
        )

        if not current_period:
            return

        # 2. FY-Aware Budget Math
        total_budget = (
            db.query(func.sum(Budget.budget_amount))
            .filter(
                Budget.lab_id == lab_id, Budget.period_id == current_period.period_id
            )
            .scalar()
            or 0
        )

        if total_budget <= 0:
            lab.notified_50 = False
            lab.notified_80 = False
            lab.notified_95 = False
            lab.notified_100 = False
            db.commit()
            return

        # 3. FY-Aware & Status-Aware Spent Math
        total_spent = (
            db.query(func.sum(PurchaseRequestLine.amount_gst))
            .join(PurchaseRequest, PurchaseRequest.pr_id == PurchaseRequestLine.pr_id)
            .filter(
                PurchaseRequestLine.lab_id == lab_id,
                PurchaseRequest.request_date >= current_period.start_date,
                PurchaseRequest.request_date <= current_period.end_date,
                or_(
                    PurchaseRequestLine.pr_status.is_(None),
                    and_(
                        PurchaseRequestLine.pr_status.not_ilike("%reject%"),
                        PurchaseRequestLine.pr_status.not_ilike("%cancel%"),
                    ),
                ),
            )
            .scalar()
            or 0
        )

        utilization_pct = (float(total_spent) / float(total_budget)) * 100

        # --- SMART FY RESET ---
        if lab.alert_period_id != current_period.period_id:
            lab.notified_50 = False
            lab.notified_80 = False
            lab.notified_95 = False
            lab.notified_100 = False
            lab.alert_period_id = current_period.period_id

        # Secondary Reset: if an admin manually increases the budget later
        was_100 = bool(getattr(lab, "notified_100", False))
        was_95 = bool(lab.notified_95)
        was_80 = bool(lab.notified_80)

        if utilization_pct < 100 and was_100:
            lab.notified_100 = False
        if utilization_pct < 95 and was_95:
            lab.notified_95 = False
        if utilization_pct < 80 and was_80:
            lab.notified_80 = False
        if utilization_pct < 50 and lab.notified_50:
            lab.notified_50 = False

        # If a budget increase dropped utilization from a higher bracket (>=80/95/100%)
        # down into a lower bracket (e.g. 50%..79.9%), unlatch that bracket's flag.
        if (was_100 or was_95 or was_80) and 50 <= utilization_pct < 80:
            lab.notified_50 = False
        elif (was_100 or was_95) and 80 <= utilization_pct < 95:
            lab.notified_80 = False
        elif was_100 and 95 <= utilization_pct < 100:
            lab.notified_95 = False
        # ----------------------

        threshold_hit = None
        if utilization_pct >= 100 and not getattr(lab, "notified_100", False):
            threshold_hit = 100
            lab.notified_100 = True
            lab.notified_95 = True
            lab.notified_80 = True
            lab.notified_50 = True
        elif utilization_pct >= 95 and not lab.notified_95:
            threshold_hit = 95
            lab.notified_95 = True
            lab.notified_80 = True
            lab.notified_50 = True
        elif utilization_pct >= 80 and not lab.notified_80:
            threshold_hit = 80
            lab.notified_80 = True
            lab.notified_50 = True
        elif utilization_pct >= 50 and not lab.notified_50:
            threshold_hit = 50
            lab.notified_50 = True

        db.commit()

        if not threshold_hit:
            return

        # Gather recipients: all active Primary & Secondary Lab ICs + Team Leads
        recipients = []

        lab_ics = (
            db.query(User)
            .join(LabIcAssignment, LabIcAssignment.user_id == User.user_id)
            .filter(
                LabIcAssignment.lab_id == lab.lab_id,
                User.role_id == 3,
                User.is_active.is_(True),
            )
            .all()
        )
        for ic in lab_ics:
            if ic.email:
                recipients.append(ic.email)

        team_leads = (
            db.query(User)
            .filter(
                User.lab_group_id == lab.lab_group_id,
                User.role_id == 2,
                User.is_active.is_(True),
            )
            .all()
        )
        for lead in team_leads:
            if lead.email:
                recipients.append(lead.email)

        recipients = list(set(recipients))

        if not recipients:
            return

        spent_str = f"${float(total_spent):,.2f}"
        budget_str = f"${float(total_budget):,.2f}"

        # --- EMAIL CONTENT & COLOR PROGRESSION ---
        if threshold_hit == 50:
            subject, color = (
                f"Notice: {lab.lab_name} has reached 50% Budget Utilization",
                "#2563eb",  # Blue
            )
            message = "You have utilized half of your allocated lab budget. Please review upcoming planned expenses."
        elif threshold_hit == 80:
            subject, color = (
                f"WARNING: {lab.lab_name} has reached 80% Budget Utilization",
                "#eab308",  # Yellow
            )
            message = "Your lab is approaching its budget limit. Please prioritize essential purchases only."
        elif threshold_hit == 95:
            subject, color = (
                f"CRITICAL: {lab.lab_name} has reached 95% Budget Utilization",
                "#ea580c",  # Orange
            )
            message = "Immediate attention required. Your lab budget is nearly exhausted. Please review spending carefully."
        else:  # Exceeded
            subject, color = (
                f"EXCEEDED: {lab.lab_name} has EXCEEDED its Budget",
                "#dc2626",  # Red
            )
            message = "Action required. Your lab budget has been completely exhausted and exceeded. Please review and adjust your spending immediately."

        html_body = f"""
        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; border: 1px solid #e5e7eb; border-radius: 8px; overflow: hidden;">
            <div style="background-color: {color}; padding: 20px; text-align: center; color: white;">
                <h2 style="margin: 0;">Budget Threshold Alert</h2>
            </div>
            <div style="padding: 24px;">
                <p style="font-size: 16px; color: #374151;">Hello,</p>
                <p style="font-size: 16px; color: #374151;">
                    This is an automated notification that <strong>{lab.lab_code} - {lab.lab_name}</strong> has crossed the
                    <strong style="color: {color};">{threshold_hit}%</strong> budget utilization threshold.
                </p>
                <div style="background-color: #f3f4f6; padding: 16px; border-radius: 6px; margin: 20px 0;">
                    <p style="margin: 0 0 8px 0;"><strong>Total Allocated Budget:</strong> {budget_str}</p>
                    <p style="margin: 0 0 8px 0;"><strong>Current Spending:</strong> {spent_str}</p>
                    <p style="margin: 0;"><strong>Current Utilization:</strong> {utilization_pct:.1f}%</p>
                </div>
                <p style="font-size: 16px; color: {color}; font-weight: bold;">{message}</p>
            </div>
        </div>
        """
        send_threshold_alert(recipients, subject, html_body)


def check_and_notify_lab_group_thresholds(lab_group_id: int):
    with SessionLocal() as db:
        group = db.query(LabGroup).filter(LabGroup.lab_group_id == lab_group_id).first()
        if not group:
            return

        # 1. Determine the CURRENT Fiscal Year
        today = date.today()
        current_period = (
            db.query(BudgetPeriod)
            .filter(BudgetPeriod.start_date <= today, BudgetPeriod.end_date >= today)
            .first()
        )

        if not current_period:
            return

        # 2. FY-Aware Budget Math (The Lab Group Envelope)
        total_budget = (
            db.query(func.sum(Budget.budget_amount))
            .filter(
                Budget.lab_group_id == lab_group_id,
                Budget.lab_id.is_(None),  # Explicitly grab the envelope
                Budget.period_id == current_period.period_id,
            )
            .scalar()
            or 0
        )

        if total_budget <= 0:
            group.notified_50 = False
            group.notified_80 = False
            group.notified_95 = False
            group.notified_100 = False
            db.commit()
            return

        # 3. FY-Aware & Status-Aware Spent Math (Sum of ALL labs in this group)
        total_spent = (
            db.query(func.sum(PurchaseRequestLine.amount_gst))
            .join(PurchaseRequest, PurchaseRequest.pr_id == PurchaseRequestLine.pr_id)
            .join(Lab, Lab.lab_id == PurchaseRequestLine.lab_id)
            .filter(
                Lab.lab_group_id == lab_group_id,
                PurchaseRequest.request_date >= current_period.start_date,
                PurchaseRequest.request_date <= current_period.end_date,
                or_(
                    PurchaseRequestLine.pr_status.is_(None),
                    and_(
                        PurchaseRequestLine.pr_status.not_ilike("%reject%"),
                        PurchaseRequestLine.pr_status.not_ilike("%cancel%"),
                    ),
                ),
            )
            .scalar()
            or 0
        )

        utilization_pct = (float(total_spent) / float(total_budget)) * 100

        # --- SMART FY RESET (Now tracked on the Lab Group) ---
        if group.alert_period_id != current_period.period_id:
            group.notified_50 = False
            group.notified_80 = False
            group.notified_95 = False
            group.notified_100 = False
            group.alert_period_id = current_period.period_id

        # Secondary Reset: if an admin manually increases the budget envelope later
        was_100 = bool(getattr(group, "notified_100", False))
        was_95 = bool(group.notified_95)
        was_80 = bool(group.notified_80)

        if utilization_pct < 100 and was_100:
            group.notified_100 = False
        if utilization_pct < 95 and was_95:
            group.notified_95 = False
        if utilization_pct < 80 and was_80:
            group.notified_80 = False
        if utilization_pct < 50 and group.notified_50:
            group.notified_50 = False

        if (was_100 or was_95 or was_80) and 50 <= utilization_pct < 80:
            group.notified_50 = False
        elif (was_100 or was_95) and 80 <= utilization_pct < 95:
            group.notified_80 = False
        elif was_100 and 95 <= utilization_pct < 100:
            group.notified_95 = False
        # ----------------------

        threshold_hit = None
        if utilization_pct >= 100 and not getattr(group, "notified_100", False):
            threshold_hit = 100
            group.notified_100 = True
            group.notified_95 = True
            group.notified_80 = True
            group.notified_50 = True
        elif utilization_pct >= 95 and not group.notified_95:
            threshold_hit = 95
            group.notified_95 = True
            group.notified_80 = True
            group.notified_50 = True
        elif utilization_pct >= 80 and not group.notified_80:
            threshold_hit = 80
            group.notified_80 = True
            group.notified_50 = True
        elif utilization_pct >= 50 and not group.notified_50:
            threshold_hit = 50
            group.notified_50 = True

        db.commit()

        if not threshold_hit:
            return

        # Lab Group alerts go only to the responsible active Team Leads.
        recipients = []

        team_leads = (
            db.query(User)
            .filter(
                User.lab_group_id == group.lab_group_id,
                User.role_id == 2,
                User.is_active.is_(True),
            )
            .all()
        )
        for lead in team_leads:
            if lead.email:
                recipients.append(lead.email)

        recipients = list(set(recipients))

        if not recipients:
            return

        spent_str = f"${float(total_spent):,.2f}"
        budget_str = f"${float(total_budget):,.2f}"

        # --- EMAIL CONTENT & COLOR PROGRESSION ---
        if threshold_hit == 50:
            subject, color = (
                f"Notice: Lab Group {group.lab_group_name} has reached 50% Budget Utilization",
                "#2563eb",  # Blue
            )
            message = "Your Lab Group has utilized half of its total allocated budget envelope. Please review upcoming planned expenses."
        elif threshold_hit == 80:
            subject, color = (
                f"WARNING: Lab Group {group.lab_group_name} has reached 80% Budget Utilization",
                "#eab308",  # Yellow
            )
            message = "Your Lab Group is approaching its budget envelope limit. Please prioritize essential purchases only."
        elif threshold_hit == 95:
            subject, color = (
                f"CRITICAL: Lab Group {group.lab_group_name} has reached 95% Budget Utilization",
                "#ea580c",  # Orange
            )
            message = "Immediate attention required. Your Lab Group budget is nearly exhausted. Please review spending across all underlying labs carefully."
        else:  # Exceeded
            subject, color = (
                f"EXCEEDED: Lab Group {group.lab_group_name} has EXCEEDED its Budget",
                "#dc2626",  # Red
            )
            message = "Action required. Your Lab Group budget has been completely exhausted and exceeded. Please adjust spending immediately."

        html_body = f"""
        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; border: 1px solid #e5e7eb; border-radius: 8px; overflow: hidden;">
            <div style="background-color: {color}; padding: 20px; text-align: center; color: white;">
                <h2 style="margin: 0;">Budget Threshold Alert</h2>
            </div>
            <div style="padding: 24px;">
                <p style="font-size: 16px; color: #374151;">Hello,</p>
                <p style="font-size: 16px; color: #374151;">
                    This is an automated notification that the <strong>{group.wbs_code or "Department"} - {group.lab_group_name}</strong> Lab Group has crossed the
                    <strong style="color: {color};">{threshold_hit}%</strong> overall budget utilization threshold.
                </p>
                <div style="background-color: #f3f4f6; padding: 16px; border-radius: 6px; margin: 20px 0;">
                    <p style="margin: 0 0 8px 0;"><strong>Total Group Envelope:</strong> {budget_str}</p>
                    <p style="margin: 0 0 8px 0;"><strong>Total Group Spending:</strong> {spent_str}</p>
                    <p style="margin: 0;"><strong>Current Utilization:</strong> {utilization_pct:.1f}%</p>
                </div>
                <p style="font-size: 16px; color: {color}; font-weight: bold;">{message}</p>
            </div>
        </div>
        """
        send_threshold_alert(recipients, subject, html_body)
