import json
import time
import requests

URL = "https://www.104.com.tw/jobs/search/list"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        " (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Referer": "https://www.104.com.tw/jobs/search/",
}


def fetch_jobs(keyword, category_label, pages=2):
    results = []
    for page in range(1, pages + 1):
        params = {
            "ro": "1",  # 1: 全職
            "keyword": keyword,
            "order": "15",  # 15: 依更新日期排序
            "asc": "0",
            "page": str(page),
            "mode": "s",
        }
        try:
            res = requests.get(URL, headers=HEADERS, params=params, timeout=10)
            res.raise_for_status()
            data = res.json()
            job_list = data.get("data", {}).get("list", [])

            for item in job_list:
                # 過濾掉廣告職缺
                if item.get("jobType") == "1":
                    continue
                results.append({
                    "id": item.get("jobNo"),
                    "category": category_label,  # 標記是 PM 還是 PjM
                    "title": item.get("jobName", ""),
                    "company": item.get("custName", ""),
                    "industry": item.get("coIndustryDesc", ""),
                    "location": item.get("jobAddrNoDesc", ""),
                    "salary": item.get("salaryDesc", ""),
                    "experience": item.get("periodDesc", ""),
                    "education": item.get("optionEdu", ""),
                    "description": item.get("description", ""),
                    "link": "https:" + item.get("link", {}).get("job", ""),
                    "updatedAt": item.get("appearDateDesc", ""),
                })
            time.sleep(1.5)  # 禮貌性延遲，避免請求過快被擋
        except Exception as e:
            print(f"抓取 {keyword} 第 {page} 頁失敗: {e}")
    return results


if __name__ == "__main__":
    pm_jobs = fetch_jobs("產品經理 PM", "PM", pages=2)
    pjm_jobs = fetch_jobs("專案經理 PjM", "PjM", pages=2)

    # 合併並去除重複職缺
    all_jobs = {}
    for job in pm_jobs + pjm_jobs:
        if job["id"]:
            all_jobs[job["id"]] = job

    output = list(all_jobs.values())
    with open("jobs.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"成功更新 {len(output)} 筆職缺至 jobs.json")
