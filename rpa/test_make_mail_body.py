from datetime import datetime

# 일단 테스트용 고정값
report_date = datetime(2026, 5, 13)
target_month = 5
product_name = "V6P 132FBGA-2Chip Stack"
monthly_target = "100K"
shipping_qty = "13K"

date_text = f"{report_date.year % 100}년 {report_date.month}월 {report_date.day}일"

mail_body = f"""안녕하세요 3Camp 한훈혜 입니다.

{date_text} 생산일보 전달 드립니다.

- {target_month}월 {product_name}의 생산목표는 {monthly_target} 입니다.

- {target_month}월 출하 누적 수량 {shipping_qty} 입니다.

감사합니다."""

print("===== 메일 본문 시작 =====")
print(mail_body)
print("===== 메일 본문 끝 =====")