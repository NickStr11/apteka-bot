"""Script to clear all data from the Google Sheet (keeping headers)."""

import os
import sys
from pathlib import Path

# Add src to path
sys.path.append(str(Path(__file__).parent / "src"))

from database.sheets import get_client, get_sheet, HEADERS

def clear_table():
    print("🧹 Connecting to Google Sheets...")
    
    # Path to credentials file
    creds_path = Path(__file__).parent / "photo-gallery-484020-c9d57645a635.json"
    
    try:
        client = get_client(creds_path)
        sheet = get_sheet(client)
        
        # Get all values to see how many rows we have
        all_values = sheet.get_all_values()
        num_rows = len(all_values)
        
        if num_rows <= 1:
            print("✨ Table is already empty (only headers exist).")
            return

        print(f"🗑️ Found {num_rows - 1} data rows. Clearing...")
        
        # Clear all content
        sheet.clear()
        
        # Re-add headers (this will be done by get_sheet anyway, but let's be explicit)
        sheet.update("A1:J1", [HEADERS])
        sheet.format("A1:J1", {"textFormat": {"bold": True}})
        
        print("✅ Success! Table is now clean.")
        
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    clear_table()
