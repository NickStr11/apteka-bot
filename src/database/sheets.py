"""Google Sheets database integration."""

from datetime import datetime
from dataclasses import dataclass
from pathlib import Path
import os
import json

import gspread
from google.oauth2.service_account import Credentials


# Spreadsheet ID from URL
SPREADSHEET_ID = "11LfMaertVlJcwwlUUyh9Wco1STm9-kS8ZXn_M3Pjga4"

# Column headers
HEADERS = [
    "Дата",
    "Заказ", 
    "Телефон",
    "Товары",
    "Сумма",
    "WA статус",
    "SMS статус",
    "Отправлено",
    "Примечание",
]


@dataclass
class OrderRow:
    """Order data for spreadsheet."""
    date: str
    order_number: str
    phone: str
    products: str
    total: float
    wa_status: str = ""
    sms_status: str = ""
    sent: str = ""
    note: str = ""


def get_client(credentials_path: str | Path) -> gspread.Client:
    """Get authenticated gspread client."""
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    
    # Try to load from env var first (for Cloud hosting)
    json_creds = os.environ.get("GOOGLE_CREDENTIALS_JSON")
    if json_creds:
        try:
            creds_dict = json.loads(json_creds)
            creds = Credentials.from_service_account_info(
                creds_dict,
                scopes=scopes,
            )
            return gspread.authorize(creds)
        except Exception as e:
            print(f"⚠️ Error loading credentials from env: {e}")

    # Fallback to file on disk
    creds = Credentials.from_service_account_file(
        str(credentials_path),
        scopes=scopes,
    )
    
    return gspread.authorize(creds)


def get_sheet(client: gspread.Client) -> gspread.Worksheet:
    """Get the main worksheet."""
    spreadsheet = client.open_by_key(SPREADSHEET_ID)
    
    # Get first sheet or create "Заказы"
    try:
        sheet = spreadsheet.worksheet("Заказы")
    except gspread.WorksheetNotFound:
        sheet = spreadsheet.sheet1
        sheet.update_title("Заказы")
    
    # Ensure headers exist
    if sheet.row_count == 0 or sheet.cell(1, 1).value != HEADERS[0]:
        sheet.update("A1:I1", [HEADERS])
        sheet.format("A1:I1", {"textFormat": {"bold": True}})
    
    return sheet


def add_order(
    sheet: gspread.Worksheet,
    order: OrderRow,
) -> int:
    """
    Add order to spreadsheet.
    
    Returns:
        Row number of added order
    """
    row_data = [
        order.date,
        order.order_number,
        order.phone,
        order.products,
        str(order.total),
        order.wa_status,
        order.sms_status,
        order.sent,
        order.note,
    ]
    
    sheet.append_row(row_data)
    # Get the row index of the newly added row
    # (Using sheet.row_count after append is risky if multiple people use it,
    # but append_row doesn't return the row index directly in gspread 3.x)
    # A safer way to find the row index in modern gspread:
    return len(sheet.get_all_values())


def update_order_row(
    sheet: gspread.Worksheet,
    row: int,
    order: OrderRow,
) -> None:
    """Replace all data in a specific row."""
    row_data = [
        order.date,
        order.order_number,
        order.phone,
        order.products,
        str(order.total),
        order.wa_status,
        order.sms_status,
        order.sent,
        order.note,
    ]
    
    # Range from A to I for the given row
    cell_range = f"A{row}:I{row}"
    sheet.update(cell_range, [row_data])


def delete_order_row(sheet: gspread.Worksheet, row: int) -> None:
    """Delete a specific row from the spreadsheet."""
    sheet.delete_rows(row)


def find_order_by_number(
    sheet: gspread.Worksheet,
    order_number: str,
) -> int | None:
    """Find row by order number. Returns row number or None."""
    try:
        cell = sheet.find(order_number, in_column=2)
        return cell.row if cell else None
    except gspread.CellNotFound:
        return None


def update_order_status(
    sheet: gspread.Worksheet,
    row: int,
    wa_status: str | None = None,
    sms_status: str | None = None,
    sent: str | None = None,
) -> None:
    """Update order status in spreadsheet."""
    if wa_status is not None:
        sheet.update_cell(row, 6, wa_status)
    if sms_status is not None:
        sheet.update_cell(row, 7, sms_status)
    if sent is not None:
        sheet.update_cell(row, 8, sent)


def get_pending_orders(sheet: gspread.Worksheet) -> list[tuple[int, OrderRow]]:
    """Get orders that haven't been sent yet."""
    all_values = sheet.get_all_values()
    pending = []
    
    for i, row in enumerate(all_values[1:], start=2):  # Skip header
        if len(row) >= 8 and not row[7]:  # If "Отправлено" is empty
            pending.append((i, OrderRow(
                date=row[0],
                order_number=row[1],
                phone=row[2],
                products=row[3],
                total=float(row[4]) if row[4] else 0,
                wa_status=row[5],
                sms_status=row[6],
                sent=row[7],
                note=row[8] if len(row) > 8 else "",
            )))
    
    return pending
