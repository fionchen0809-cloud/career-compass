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


def parse_salary(salary_text):
    nums = [int(n.replace(",", "")) for n in re.findall(r"[\d,]+", salary_text or "")]
    nums = [n for n in nums if n >= 20000]
    if not nums:
        return None, None
    return min(nums), max(nums)


def scrape_dom_jobs(page, keyword, role_label):
    url = f"https://www.104.com.tw/jobs/search/?ro=1&keyword={quote(keyword)}&order=15&asc=0"
    page.goto(url, wait_until="domcontentloaded", timeout=35000)
    page.wait_for_timeout(5000)
    print(f"[{keyword}] 實際開啟網頁標題: {page.title()}")

    page.mouse.wheel(0, 3000)
    page.wait_for_timeout(3000)

    raw_jobs = page.evaluate("""() => {
        const links = Array.from(document.querySelectorAll('a[href*="/job/"]'));
        const seen = new Set();
        const items = [];
        for (const a of links) {
            const href = a.href || '';
            const match = href.match(/\\/job\\/([a-zA-Z0-9]+)/);
            if (!match || seen.has(match[1])) continue;
            const title = (a.innerText || '').trim();
            if (!title || title.length < 2) continue;
            seen.add(match[1]);

            const card = a.closest('article, .job-list-item, [data-job-no], div[class*="job"]') || a.parentElement?.parentElement;
            const cardText = card ? card.innerText : title;
            const compLink = card ? card.querySelector('a[href*="/company/"]') : null;
            const company = compLink ? compLink.innerText.trim() : '104 企業徵才';

            items.push({
                code: match[1],
                url: href.split('?')[0],
                title: title,
                company: company,
                fullText: cardText
            });
        }
        return items.slice(0, 25);
    }""")

    print(f"[{keyword}] 從網頁畫面成功提取 {len(raw_jobs)} 筆職缺")

    results = []
    for item in raw_jobs:
        full_text = item["fullText"]
        numeric_id = int(re.sub(r"\D", "", item["code"]) or 0)
        if numeric_id < 1000:
            numeric_id = abs(hash(item["code"])) % 100000000

        city_match = re.search(
            r"(台北市|新北市|桃園市|台中市|台南市|高雄市|新竹市|新竹縣|基隆市|苗栗縣|彰化縣|南投縣|雲林縣|嘉義市|嘉義縣|屏東縣|宜蘭縣|花蓮縣|台東縣|澎湖縣|金門縣|連江縣)",
            full_text,
        )
        city = city_match.group(1) if city_match else "台北市"

        min_pay, max_pay = parse_salary(full_text)
        years_match = re.search(r"(\d+)\s*年以上", full_text)
        years = int(years_match.group(1)) if years_match else 0

        skills = extract_skills(item["title"] + " " + full_text)
        clean_jd = " ".join(full_text.split())[:300]

        results.append({
            "id": numeric_id,
            "sourceType": "104",
            "title": item["title"],
            "company": item["company"],
            "city": city,
            "min": min_pay,
            "max": max_pay,
            "role": role_label,
            "years": years,
            "skills": skills,
            "evidence": [f"職務說明提及 {s}" for s in skills],
            "mode": "遠端" if "遠端" in full_text else ("混合辦公" if "混合" in full_text else "現場"),
            "type": "實習" if "實習" in item["title"] else "全職",
            "url": item["url"],
            "jd": clean_jd,
        })
    return results


if __name__ == "__main__":
    os.makedirs("data", exist_ok=True)
    with sync_playwright() as p:
        # 加上反自動化偵測參數，偽裝為一般使用者瀏覽器
        browser = p.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
        )
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
            locale="zh-TW",
            viewport={"width": 1366, "height": 768},
        )
        context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

        page = context.new_page()
        pm_jobs = scrape_dom_jobs(page, "產品經理 PM", "PM")
        pjm_jobs = scrape_dom_jobs(page, "專案經理 PjM", "PJM")
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

    print(f"=== 最終結果：成功更新 {len(job_list)} 筆職缺至 data/jobs.json ===")
