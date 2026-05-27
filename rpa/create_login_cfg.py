from pathlib import Path
from cryptography.fernet import Fernet
import configparser
import getpass

BASE_DIR = Path(__file__).resolve().parent.parent

CONFIG_PATH = BASE_DIR / "Login.cfg"
KEY_PATH = BASE_DIR / "login_crypto.key"

print("===== Login.cfg 생성 시작 =====")

# =========================
# 암호화 키 생성
# =========================

if not KEY_PATH.exists():

    key = Fernet.generate_key()

    with open(KEY_PATH, "wb") as f:
        f.write(key)

    print(f"암호화 키 생성 완료: {KEY_PATH}")

else:

    with open(KEY_PATH, "rb") as f:
        key = f.read()

    print("기존 암호화 키 사용")

cipher = Fernet(key)

# =========================
# 로그인 정보 입력
# =========================

user_id = input("그룹웨어 아이디 입력: ")
user_pw = getpass.getpass("그룹웨어 비밀번호 입력: ")

encrypted_pw = cipher.encrypt(
    user_pw.encode("utf-8")
).decode("utf-8")

# =========================
# cfg 저장
# =========================

config = configparser.ConfigParser()

config["GROUPWARE"] = {
    "ID": user_id,
    "PASSWORD": encrypted_pw,
}

with open(CONFIG_PATH, "w", encoding="utf-8") as f:
    config.write(f)

print("===== Login.cfg 생성 완료 =====")
print(f"저장 위치: {CONFIG_PATH}")
print("비밀번호는 암호화되어 저장되었습니다.")