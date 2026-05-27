import requests

SUPABASE_URL = "https://kajqvkeqvfniongwgocy.supabase.co"
SUPABASE_KEY = "sb_publishable_3s4eIDhnOAGTRkXyu96pdQ_KW5xOHKk"

HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation",
}

def supabase_get(table: str):
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    res = requests.get(url, headers=HEADERS)
    res.raise_for_status()
    return res.json()


def supabase_get_eq(table: str, column: str, value: str):
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    res = requests.get(url, headers=HEADERS, params={column: f"eq.{value}"})
    res.raise_for_status()
    return res.json()

def supabase_insert(table: str, data: list[dict]):
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    res = requests.post(url, headers=HEADERS, json=data)
    res.raise_for_status()
    return res.json()

def supabase_delete_all(table: str):
    url = f"{SUPABASE_URL}/rest/v1/{table}?id=not.is.null"
    res = requests.delete(url, headers=HEADERS)
    res.raise_for_status()
    return res.text


def supabase_delete_where(table: str, column: str, value: str) -> str:
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    res = requests.delete(url, headers=HEADERS, params={column: f"eq.{value}"})
    res.raise_for_status()
    return res.text


def supabase_delete_by_filters(table: str, filters: dict[str, str]) -> str:
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    params = {k: f"eq.{v}" for k, v in filters.items()}
    res = requests.delete(url, headers=HEADERS, params=params)
    res.raise_for_status()
    return res.text


def supabase_patch_by_filters(table: str, filters: dict[str, str], payload: dict) -> str:
    """PostgREST PATCH: ``filters``에 맞는 모든 행을 ``payload``로 갱신합니다."""
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    params = {k: f"eq.{v}" for k, v in filters.items()}
    res = requests.patch(url, headers=HEADERS, params=params, json=payload)
    res.raise_for_status()
    return res.text
