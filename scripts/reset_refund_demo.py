"""预览或重置三张退款演示订单，便于重复演示完整闭环。"""

import argparse
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.core.database import SessionLocal, init_db
from app.models import Order, RefundRequest, Ticket


DEMO_ORDER_STATES = {
    10001: "shipped",
    10002: "delivered",
    10007: "pending",
}


def reset(*, apply: bool) -> None:
    init_db()
    db = SessionLocal()
    try:
        orders = (
            db.query(Order)
            .filter(Order.id.in_(DEMO_ORDER_STATES))
            .order_by(Order.id)
            .all()
        )
        found_ids = {order.id for order in orders}
        missing = set(DEMO_ORDER_STATES) - found_ids
        if missing:
            raise RuntimeError(f"缺少Demo订单: {sorted(missing)}")

        refunds = (
            db.query(RefundRequest)
            .filter(RefundRequest.order_id.in_(DEMO_ORDER_STATES))
            .all()
        )
        ticket_ids = {
            refund.ticket_id for refund in refunds if refund.ticket_id is not None
        }
        print("退款Demo重置预览：")
        for order in orders:
            target = DEMO_ORDER_STATES[order.id]
            print(f"  订单 {order.id}: {order.status} -> {target}")
        print(f"  将删除退款单: {[refund.id for refund in refunds] or '无'}")
        print(f"  将删除关联工单: {sorted(ticket_ids) or '无'}")

        if not apply:
            print("未执行修改；确认后使用 --apply。")
            return

        for refund in refunds:
            db.delete(refund)
        db.flush()
        if ticket_ids:
            db.query(Ticket).filter(Ticket.id.in_(ticket_ids)).delete(
                synchronize_session=False
            )
        for order in orders:
            order.status = DEMO_ORDER_STATES[order.id]
        db.commit()
        print("退款Demo场景已重置，可重新演示。")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--apply",
        action="store_true",
        help="实际执行重置；不提供时只显示预览",
    )
    args = parser.parse_args()
    reset(apply=args.apply)


if __name__ == "__main__":
    main()
