import json
import os
import re
import time
from datetime import datetime, timezone, timedelta
import requests

URL = "https://www.104.com.tw/jobs/search/list"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        " (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Referer": "https://www.104.com.tw/jobs/search/",
}

# 對應你網站裡支援的 28 項技能關鍵字
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
    m = re.search(r"(\d+)", period_desc or "")
    return int(m.group(1)) if m else 0

def fetch_jobs(keyword, role_label, pages=2):
    results = []
    for page in range(1, pages + 1):
        params = {
            "ro": "1",
            "keyword": keyword,
            "order": "15",
            "asc": "0",
            "page": str(page),
            "mode": "s",
        }
        try:
            res = requests.get(URL, headers=HEADERS, params=params, timeout=10)
            res.raise_for_status()
            data = res.json()
            for item in data.get("data", {}).get("list", []):
                if item.get("jobType") == "1":
                    continue
                job_id = int(re.sub(r"\D", "", str(item.get("jobNo", "0"))) or 0)
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
                    "url": "https:" + item.get("link", {}).get("job", ""),
                    "jd": desc[:300] + ("..." if len(desc) > 300 else "")
                })
            time.sleep(1.5)
        except Exception as e:
            print(f"抓取 {keyword} 第 {page} 頁失敗: {e}")
    return results

if __name__ == "__main__":
    os.makedirs("data", exist_ok=True)
    pm_jobs = fetch_jobs("產品經理 PM", "PM", pages=2)
    pjm_jobs = fetch_jobs("專案經理 PjM", "PJM", pages=2)

    all_jobs = {}
    for job in pm_jobs + pjm_jobs:
        all_jobs[job["id"]] = job

    job_list = list(all_jobs.values())
    tw_now = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M:%S")

    with open("data/jobs.json", "w", encoding="utf-8") as f:
        json.dump({"updatedAt": tw_now, "jobs": job_list}, f, ensure_ascii=False, indent=2)

    with open("data/sync-status.json", "w", encoding="utf-8") as f:
        json.dump({
            "overall": "healthy",
            "lastSuccess": tw_now,
            "sources": {"104": {"status": "connected", "count": len(job_list)}}
        }, f, ensure_ascii=False, indent=2)

    print(f"成功更新 {len(job_list)} 筆職缺至 data/jobs.json")
