from playwright.sync_api import sync_playwright

GROUPWARE_URL = "http://gw.ramostek.com/"

print("===== 로그인 페이지 구조 확인 시작 =====")

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False, channel="chrome")
    page = browser.new_page()

    page.goto(GROUPWARE_URL, wait_until="networkidle", timeout=60000)
    page.wait_for_timeout(10000)

    print("BODY TEXT:")
    print(page.locator("body").inner_text())

    print("현재 URL:", page.url)
    print("페이지 제목:", page.title())

    print("\n===== INPUT 목록 =====")
    inputs = page.locator("input")
    for i in range(inputs.count()):
        item = inputs.nth(i)
        print("-----")
        print("index:", i)
        print("type:", item.get_attribute("type"))
        print("id:", item.get_attribute("id"))
        print("name:", item.get_attribute("name"))
        print("class:", item.get_attribute("class"))
        print("placeholder:", item.get_attribute("placeholder"))
        print("value:", item.get_attribute("value"))

    print("\n===== BUTTON 목록 =====")
    buttons = page.locator("button, input[type='button'], input[type='submit'], a")
    for i in range(buttons.count()):
        item = buttons.nth(i)
        text = item.inner_text() if item.evaluate("el => el.innerText !== undefined") else ""
        print("-----")
        print("index:", i)
        print("tag:", item.evaluate("el => el.tagName"))
        print("text:", text)
        print("id:", item.get_attribute("id"))
        print("name:", item.get_attribute("name"))
        print("class:", item.get_attribute("class"))
        print("type:", item.get_attribute("type"))
        print("onclick:", item.get_attribute("onclick"))
        print("href:", item.get_attribute("href"))

    print("\n===== FORM 목록 =====")
    forms = page.locator("form")
    for i in range(forms.count()):
        item = forms.nth(i)
        print("-----")
        print("index:", i)
        print("id:", item.get_attribute("id"))
        print("name:", item.get_attribute("name"))
        print("action:", item.get_attribute("action"))
        print("method:", item.get_attribute("method"))

    input("\n확인 후 Enter를 누르면 종료합니다...")
    browser.close()

print("===== 로그인 페이지 구조 확인 끝 =====")
