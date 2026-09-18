import time
from playwright.sync_api import sync_playwright

def track_tsn_sports():
    print("Starting TSN NFL, F1, CFL, & La Liga Tracker... Press Ctrl+C to stop.")
    
    try:
        while True:
            print(f"\n--- Checking TSN for NFL, F1, CFL, & La Liga at {time.strftime('%Y-%m-%d %H:%M:%S')} ---")
            
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page()
                
                # Navigate to the TSN live page
                page.goto("https://www.tsn.ca/live/", timeout=60000)
                page.wait_for_timeout(3000)
                
                # Scroll down to load all cards/sections
                for _ in range(3):
                    page.evaluate("window.scrollBy(0, document.body.scrollHeight)")
                    page.wait_for_timeout(1500)
                
                cards = page.locator(".c-promo-card, .schedule-item, .event-row, [class*='schedule']").all()
                
                seen_texts = set()
                found_count = 0
                
                # Expanded keywords list including La Liga and related soccer terms
                target_keywords = [
                    "nfl", "f1", "formula 1", "grand prix", "cfl", 
                    "la liga", "spanish soccer", "real madrid", "barcelona"
                ]
                
                for card in cards:
                    try:
                        text = card.inner_text().strip()
                        if text and text not in seen_texts:
                            seen_texts.add(text)
                            lower_text = text.lower()
                            
                            # Check if ANY of the target keywords appear in the text
                            if any(keyword in lower_text for keyword in target_keywords):
                                lines = [line.strip() for line in text.split('\n') if line.strip()]
                                if len(lines) >= 2:
                                    found_count += 1
                                    print(f"\n[Event #{found_count}]")
                                    print(f"  Time / Status : {lines[0]}")
                                    print(f"  Event Title   : {' - '.join(lines[1:])}")
                                    print("-" * 40)
                    except Exception:
                        continue
                            
                if found_count == 0:
                    print("No active or upcoming NFL, F1, CFL, or La Liga events found on this pass.")
                    
                browser.close()
            
            # Wait 300 seconds (5 minutes) before running the check again
            print("\nWaiting 300 seconds for the next check...")
            time.sleep(300)
            
    except KeyboardInterrupt:
        print("\nTracker stopped by user.")

if __name__ == "__main__":
    track_tsn_sports()