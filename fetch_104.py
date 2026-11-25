import json
import os
import re
from urllib.parse import quote
from datetime import datetime, timezone, timedelta
from playwright.sync_api import sync_playwright

SKILL_KEYWORDS = [
    "產品策略", "使用者研究", "需求分析", "Roadmap", "資料分析", "A/B 測試",
    "跨部門協作", "專案管理", "時程規劃", "風險管理", "敏捷開發", "Scrum",
    "Jira", "SQL", "Python", "UI/UX", "Wireframe", "商業分析", "客戶溝通",
    "簡報表達", "預算控管", "範疇管理", "品質管理", "利害關係人管理",
    "API", "SaaS", "AI", "數據視覺化"
]


def extract_skills(text):
    found = [s for s in SKILL_KEYWORDS if s.lower() in text.lower()]
    return found if found else ["跨部門協作", "需求分析", "專案管理"]


def parse_years(period_desc):
    m = re.search(r"(\d+)", str(period_desc or ""))
    return int(m.group(1)) if m else 0


def scrape_with_browser(page, keyword, role_label):
    captured_items = []

    def handle_response(response):
        if "/jobs/search/api/jobs" in response.url or "/jobs/search/list" in response.url:
            try:
                data = response.json()
                items = data.get("data", {}).get("list", [])
                if not items and isinstance(data.get("data"), list):
                    items = data.get("data", [])
                captured_items.extend(items)
            except Exception:
                pass

    page.on("response", handle_response)
    url = f"https://www.104.com.tw/jobs/search/?ro=1&keyword={quote(keyword)}&order=15&asc=0"
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(5000)
    except Exception as e:
        print(f"載入 {keyword} 頁面時發生異常: {e}")
    finally:
        page.remove_listener("response", handle_response)

    print(f"[{keyword}] 攔截到 {len(captured_items)} 筆原始資料")

    results = []
    for item in captured_items:
        if str(item.get("jobType")) == "1":
            continue
        raw_id = str(item.get("jobNo") or item.get("id") or "0")
        job_id = int(re.sub(r"\D", "", raw_id) or 0)
        if not job_id:
            continue

        addr = item.get("jobAddrNoDesc", "")
        city = addr[:3] if len(addr) >= 3 else "台北市"
        salary_low = item.get("salaryLow")
        salary_high = item.get("salaryHigh")
        min_pay = int(salary_low) if salary_low and int(salary_low) > 0 else None
        max_pay = int(salary_high) if salary_high and int(salary_high) >= (min_pay or 0) else min_pay

        desc = item.get("description", "") or ""
        title = item.get("jobName", "")
        skills = extract_skills(title + " " + desc)

        link_obj = item.get("link", {})
        job_url = link_obj.get("job", "") if isinstance(link_obj, dict) else str(link_obj)
        if job_url and not job_url.startswith("http"):
            job_url = "https:" + job_url

        results.append({
            "id": job_id,
            "sourceType": "104",
            "title": title,
            "company": item.get("custName", ""),
            "city": city,
            "min": min_pay,
            "max": max_pay,
            "role": role_label,
            "years": parse_years(item.get("periodDesc", "")),
            "skills": skills,
            "evidence": [f"職務說明提及 {s}" for s in skills],
            "mode": "遠端" if "遠端" in desc else ("混合辦公" if "混合" in desc else "現場"),
            "type": "實習" if "實習" in title else "全職",
            "url": job_url,
            "jd": desc[:300] + ("..." if len(desc) > 300 else ""),
        })
    return results


if __name__ == "__main__":
    os.makedirs("data", exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
            locale="zh-TW",
        )
        page = context.new_page()
        pm_jobs = scrape_with_browser(page, "產品經理 PM", "PM")
        pjm_jobs = scrape_with_browser(page, "專案經理 PjM", "PJM")
        browser.close()

    all_jobs = {j["id"]: j for j in (pm_jobs + pjm_jobs)}
    job_list = list(all_jobs.values())
    tw_now = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M:%S")

    with open("data/jobs.json", "w", encoding="utf-8") as f:
        json.dump({"updatedAt": tw_now, "jobs": job_list}, f, ensure_ascii=False, indent=2)

    with open("data/sync-status.json", "w", encoding="utf-8") as f:
        json.dump({
            "overall": "healthy" if job_list else "degraded",
            "lastSuccess": tw_now,
            "sources": {"104": {"status": "connected" if job_list else "empty", "count": len(job_list)}},
        }, f, ensure_ascii=False, indent=2)

    print(f"成功更新 {len(job_list)} 筆職缺至 data/jobs.json")
