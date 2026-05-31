"""
POS CSV loader — seeds the pos_transactions table from the real Brigade_Bangalore CSV.
Runs at API startup. Idempotent (ON CONFLICT DO NOTHING).

Real CSV column mapping:
  order_id, order_date (dd-MM-yyyy), order_time (HH:mm:ss),
  store_id (ST1008), total_amount, customer_number, salesperson_id
"""
import csv
from datetime import datetime, timezone
import os
import structlog
from sqlalchemy.orm import Session
from sqlalchemy import text

log = structlog.get_logger(__name__)

# IST = UTC+5:30
IST_OFFSET_HOURS = 5.5


def parse_ist_to_utc(date_str: str, time_str: str) -> datetime:
    """Parse 'dd-MM-yyyy' + 'HH:mm:ss' in IST → UTC datetime."""
    dt_local = datetime.strptime(f"{date_str} {time_str}", "%d-%m-%Y %H:%M:%S")
    # Convert IST (UTC+5:30) to UTC
    from datetime import timedelta
    utc_dt = dt_local - timedelta(hours=IST_OFFSET_HOURS)
    return utc_dt.replace(tzinfo=timezone.utc)


def load_pos_csv(db: Session, csv_path: str | None = None) -> int:
    """
    Load POS transactions from CSV into the database.
    Returns number of rows inserted.
    """
    if csv_path is None:
        csv_path = os.getenv("POS_CSV_PATH", "/app/data/pos_transactions.csv")

    if not os.path.exists(csv_path):
        log.warning("pos_csv_not_found", path=csv_path)
        return 0

    inserted = 0
    seen_orders = set()

    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            order_id = row.get("order_id", "").strip()
            if not order_id or order_id in seen_orders:
                continue   # Skip duplicates within the file (same order, multiple items)
            seen_orders.add(order_id)

            try:
                txn_time = parse_ist_to_utc(
                    row["order_date"].strip(),
                    row["order_time"].strip()
                )
                basket = float(row.get("total_amount") or 0)
                store_id = row.get("store_id", "ST1008").strip()
                customer_number = row.get("customer_number", "").strip()
                salesperson_id = row.get("salesperson_id", "").strip()

                db.execute(text("""
                    INSERT INTO pos_transactions
                        (order_id, store_id, transaction_time, basket_value,
                         customer_number, salesperson_id)
                    VALUES
                        (:order_id, :store_id, :txn_time, :basket,
                         :customer_number, :salesperson_id)
                    ON CONFLICT (order_id) DO NOTHING
                """), {
                    "order_id":        order_id,
                    "store_id":        store_id,
                    "txn_time":        txn_time.isoformat(),
                    "basket":          basket,
                    "customer_number": customer_number,
                    "salesperson_id":  salesperson_id,
                })
                inserted += 1

            except Exception as e:
                log.warning("pos_row_skip", order_id=order_id, error=str(e))

    db.commit()
    log.info("pos_csv_loaded", path=csv_path, rows_inserted=inserted)
    return inserted
