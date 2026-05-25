import os
import requests
from src.utils.logger import get_logger

logger = get_logger("notify")

TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"


def _send_telegram(text: str) -> bool:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        logger.warning("텔레그램 설정 누락 (TELEGRAM_BOT_TOKEN 또는 TELEGRAM_CHAT_ID)")
        return False
    try:
        resp = requests.post(
            TELEGRAM_API.format(token=token),
            json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"},
            timeout=10,
        )
        resp.raise_for_status()
        return True
    except Exception as e:
        logger.error("텔레그램 전송 실패: %s", e)
        return False


def notify_success(date: str, url: str, warnings: list[str]) -> None:
    warn_text = ""
    if warnings:
        warn_text = "\n⚠ 데이터 경고:\n" + "\n".join(f"  · {w}" for w in warnings)
    text = (
        f"✅ <b>재테크 브리핑 발행 완료</b>\n"
        f"📅 {date}\n"
        f"🔗 {url}"
        f"{warn_text}"
    )
    _send_telegram(text)


def notify_failure(date: str, error: str) -> None:
    text = (
        f"❌ <b>재테크 브리핑 실패</b>\n"
        f"📅 {date}\n"
        f"🚨 오류: {error[:300]}"
    )
    _send_telegram(text)
