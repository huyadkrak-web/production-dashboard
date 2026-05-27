import pyautogui
import pyperclip
import time

mail_body = """안녕하세요 3Camp 한훈혜 입니다.

26년 5월 13일 생산일보 전달 드립니다.

- 5월 V6P 132FBGA-2Chip Stack의 생산목표는 100K 입니다.

- 5월 출하 누적 수량 13K 입니다.

감사합니다."""

print("===== 메일 본문 붙여넣기 테스트 =====")

print("5초 안에 그룹웨어 메일 본문 입력칸을 클릭하세요.")

time.sleep(5)

# 클립보드 복사
pyperclip.copy(mail_body)

# Ctrl + V 붙여넣기
pyautogui.hotkey("ctrl", "v")

print("메일 본문 붙여넣기 완료!")