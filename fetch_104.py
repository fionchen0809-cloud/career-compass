import json
import os
import re
import time
from datetime import datetime, timezone, timedelta
import requests

SEARCH_PAGE_URL = "https://www.104.com.tw/jobs/search/"
API_URL = "https://www.104.com.tw/jobs/search/api/jobs"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        " (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7",
    "Referer": "https://www.104.com.tw/jobs/search/",
    "Origin": "https://www.104.com.tw",
}

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


def fetch_jobs(session, keyword, role_label, pages=2):
    results = []
    for page in range(1, pages + 1):
        params = {
            "ro": "1",
            "keyword": keyword,
            "order": "15",
            "asc": "0",
            "page": str(page),
            "mode": "s",
            "jobsource": "index_s",
        }
        try:
            res = session.get(API_URL, headers=HEADERS, params=params, timeout=15)
            print(f"[{keyword}] 第 {page} 頁狀態碼: {res.status_code}")
            if res.status_code != 200:
                print(f"回應內容前 200 字: {res.text[:200]}")
                continue

            data = res.json()
            # 相容 104 新舊兩種 JSON 結構
            job_list = data.get("data", {}).get("list", [])
            if not job_list and isinstance(data.get("data"), list):
                job_list = data.get("data", [])

            print(f"[{keyword}] 第 {page} 頁取得 {len(job_list)} 筆原始資料")

            for item in job_list:
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
            time.sleep(2)
        except Exception as e:
            print(f"抓取 {keyword} 第 {page} 頁發生例外: {e}")
    return results


if __name__ == "__main__":
    os.makedirs("data", exist_ok=True)

    # 先用 Session 造訪搜尋頁取得合法 Cookie
    s = requests.Session()
    try:
        init_res = s.get(SEARCH_PAGE_URL, headers=HEADERS, timeout=15)
        print(f"初始化 Cookie 狀態碼: {init_res.status_code}")
        time.sleep(1.5)
    except Exception as e:
        print(f"初始化連線失敗: {e}")

    pm_jobs = fetch_jobs(s, "產品經理 PM", "PM", pages=2)
    pjm_jobs = fetch_jobs(s, "專案經理 PjM", "PJM", pages=2)

    all_jobs = {}
    for job in pm_jobs + pjm_jobs:
        all_jobs[job["id"]] = job

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

    print(f"=== 最終結果：成功更新 {len(job_list)} 筆職缺至 data/jobs.json ===")
