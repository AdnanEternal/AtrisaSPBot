import json
from urllib.request import Request, urlopen
from urllib.parse import urlencode
from collections import Counter

API = "https://api.openverse.org/v1"

# استفاده از اعتبارنامه‌ای که قبلاً ثبت کرده‌ای
with open("openverse_credentials.json", encoding="utf-8") as f:
    credentials = json.load(f)

def get_json(url, data=None, headers=None):
    request = Request(
        url,
        data=data,
        headers=headers or {},
        method="POST" if data is not None else "GET",
    )
    with urlopen(request, timeout=30) as response:
        return json.load(response)

# دریافت توکن
token = get_json(
    f"{API}/auth_tokens/token/",
    data=urlencode({
        "grant_type": "client_credentials",
        "client_id": credentials["client_id"],
        "client_secret": credentials["client_secret"],
    }).encode(),
    headers={
        "Content-Type": "application/x-www-form-urlencoded",
        "User-Agent": "AtrisaSPBot/4.0",
    },
)["access_token"]

headers = {
    "Authorization": f"Bearer {token}",
    "User-Agent": "AtrisaSPBot/4.0",
}

# عبارت‌های جست‌وجوی مرتبط با نوزاد و شیرخوار انسان
queries = [
    "baby",
    "babies",
    "newborn",
    "infant",
    "cute baby",
    "smiling baby",
    "laughing baby",
    "baby portrait",
    "baby playing",
    "happy baby",
    "baby face",
    "toddler",
]

categories = Counter()
tags = Counter()
total_reported = 0

print("در حال بررسی Openverse...\n")

for query in queries:
    params = urlencode({
        "q": query,
        "page": 1,
        "page_size": 20,
        "mature": "false",
    })

    try:
        result = get_json(
            f"{API}/images/?{params}",
            headers=headers,
        )

        total_reported += result.get("result_count", 0)

        for item in result.get("results", []):
            category = item.get("category")
            if category:
                categories[category] += 1

            for tag in item.get("tags", []):
                if isinstance(tag, dict):
                    name = tag.get("name", "")
                else:
                    name = str(tag)

                name = name.strip().casefold()
                if name:
                    tags[name] += 1

        print(
            f"{query:18} | "
            f"نتایج گزارش‌شده: {result.get('result_count', 0)}"
        )

    except Exception as error:
        print(f"{query}: خطا - {error}")

print("\n" + "=" * 45)
print("دسته‌بندی‌های کلی تصاویر:")



print("\n" + "=" * 45)
print(f"مجموع نتایج گزارش‌شده در جست‌وجوها: {total_reported}")
print(f"تعداد برچسب‌های متمایز: {len(tags)}")
print("\nتمام شد؛ هیچ تصویری دانلود و هیچ فایلی ساخته نشد.")