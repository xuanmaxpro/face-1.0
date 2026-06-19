from playwright.sync_api import sync_playwright
import os

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1440, "height": 900})

    # 直接打开 HTML 文件
    html_path = os.path.abspath("f:/Users/xiaoxuan/face/templates/index.html")
    page.goto(f"file:///{html_path}")
    page.wait_for_load_state('networkidle')

    # 截图
    page.screenshot(path="f:/Users/xiaoxuan/face/screenshot.png", full_page=True)
    print("Screenshot saved to screenshot.png")

    browser.close()
