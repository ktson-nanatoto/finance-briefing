import json
import os
import sys
import shutil
from datetime import datetime, timezone, timedelta
from pathlib import Path

from dotenv import load_dotenv
from jinja2 import Environment, FileSystemLoader

from src.crawlers import us_market, kr_market, macro, news, realestate
from src.ai.generate import generate_analysis
from src.utils.logger import get_logger
from src.utils.validator import validate
from src.utils.notify import notify_success, notify_failure
from src.utils.qrcode_gen import generate_qr_base64

load_dotenv()

logger = get_logger("main")

KST = timezone(timedelta(hours=9))
BASE_DIR = Path(__file__).parent.parent
OUTPUT_DIR = BASE_DIR / "output"
ARCHIVE_DIR = OUTPUT_DIR / "archive"
CACHE_DIR = BASE_DIR / "cache"
TEMPLATE_DIR = BASE_DIR / "src" / "templates"

PAGES_URL = os.environ.get("PAGES_URL", "https://your-username.github.io/finance-briefing/")


def load_cache() -> dict | None:
    cache_files = sorted(CACHE_DIR.glob("*.json"), reverse=True)
    if cache_files:
        try:
            with open(cache_files[0], encoding="utf-8") as f:
                logger.info("캐시 로드: %s", cache_files[0].name)
                return json.load(f)
        except Exception as e:
            logger.error("캐시 로드 실패: %s", e)
    return None


def save_cache(date_str: str, data: dict) -> None:
    CACHE_DIR.mkdir(exist_ok=True)
    path = CACHE_DIR / f"{date_str}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    # 최근 7일치만 유지
    old_files = sorted(CACHE_DIR.glob("*.json"), reverse=True)[7:]
    for old in old_files:
        old.unlink(missing_ok=True)


def collect_data() -> tuple[dict, bool]:
    """모든 크롤러 실행. 필수 데이터 실패 시 캐시 fallback."""
    logger.info("데이터 수집 시작")
    data = {
        "us_market": us_market.fetch(),
        "kr_market": kr_market.fetch(),
        "macro": macro.fetch(),
        "news": news.fetch(),
        "realestate": realestate.fetch(),
    }
    logger.info("데이터 수집 완료")

    is_valid, warnings = validate(data)
    if not is_valid:
        cached = load_cache()
        if cached:
            logger.warning("필수 데이터 누락 — 캐시 데이터로 fallback")
            # 뉴스는 최신 유지, 시세만 캐시로 교체
            for key in ("us_market", "kr_market", "macro"):
                data[key] = cached.get(key, data[key])
        else:
            logger.error("캐시도 없음 — 수집된 데이터로 진행")

    return data, warnings


def render_html(data: dict, analysis: dict, date_str: str, warnings: list[str]) -> str:
    qr_base64 = generate_qr_base64(PAGES_URL)
    env = Environment(loader=FileSystemLoader(str(TEMPLATE_DIR)))
    template = env.get_template("briefing.html.j2")
    return template.render(
        date=date_str,
        data=data,
        analysis=analysis,
        warnings=warnings,
        qr_base64=qr_base64,
    )


def save_output(html: str, date_str: str) -> None:
    OUTPUT_DIR.mkdir(exist_ok=True)
    ARCHIVE_DIR.mkdir(exist_ok=True)

    # 최신 브리핑
    index_path = OUTPUT_DIR / "index.html"
    with open(index_path, "w", encoding="utf-8") as f:
        f.write(html)

    # 아카이브
    archive_path = ARCHIVE_DIR / f"{date_str}.html"
    shutil.copy(index_path, archive_path)
    logger.info("저장 완료: %s, %s", index_path, archive_path)


def main() -> None:
    now = datetime.now(KST)
    date_str = now.strftime("%Y-%m-%d")
    date_display = now.strftime("%Y년 %m월 %d일 (%a)")
    report_type = "afternoon" if now.hour >= 10 else "morning"
    archive_key = f"{date_str}-{'1200' if report_type == 'afternoon' else '0630'}"

    logger.info("===== 브리핑 생성 시작: %s (%s) =====", date_str, report_type)

    try:
        # 1. 데이터 수집
        data, warnings = collect_data()

        # 2. 캐시 저장
        save_cache(date_str, {k: v for k, v in data.items() if k != "news"})

        # 3. AI 분석
        logger.info("Groq API 호출 중")
        analysis = generate_analysis(data, report_type)
        logger.info("AI 분석 완료")

        # 4. HTML 렌더링
        html = render_html(data, analysis, date_display, warnings)

        # 5. 파일 저장
        save_output(html, archive_key)

        # 6. 텔레그램 알림 (성공)
        notify_success(date_display, PAGES_URL, warnings, report_type)
        logger.info("===== 브리핑 생성 완료 =====")

    except Exception as e:
        logger.exception("브리핑 생성 실패: %s", e)
        notify_failure(date_display if 'date_display' in locals() else date_str, str(e))
        sys.exit(1)


if __name__ == "__main__":
    main()
