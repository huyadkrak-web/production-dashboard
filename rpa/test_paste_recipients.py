import pyautogui
import pyperclip
import time

to_recipients = (
    "tschang@ctst.co.kr; "
    "sjh@ctst.co.kr; "
    "ykjang@ctst.co.kr; "
    "msoh@ctst.co.kr; "
    "ktaejun@ctst.co.kr; "
    "ojs@ctst.co.kr; "
    "cge@ctst.co.kr"
)

cc_recipients = "ws.sin@ctst.co.kr"

print("===== 수신자 자동 입력 테스트 =====")

print("5초 안에 '받는 사람' 입력칸을 클릭하세요.")
time.sleep(5)

pyperclip.copy(to_recipients)
pyautogui.hotkey("ctrl", "v")
pyautogui.press("enter")

print("받는 사람 입력 완료")

print("5초 안에 '참조' 입력칸을 클릭하세요.")
time.sleep(5)

pyperclip.copy(cc_recipients)
pyautogui.hotkey("ctrl", "v")
pyautogui.press("enter")

print("참조 입력 완료")
print("===== 수신자 자동 입력 테스트 끝 =====")