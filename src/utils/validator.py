from src.utils.logger import get_logger

logger = get_logger("validator")

# 필수 필드: 없으면 fallback 발동
REQUIRED_FIELDS = [
    ("kr_market", "usd_krw"),
    ("kr_market", "kospi"),
    ("us_market", "sp500"),
]

# 이상치 임계값: 전일 대비 변동률 ±이 수치 초과 시 경고
ANOMALY_THRESHOLD_PCT = 20.0


def validate(data: dict) -> tuple[bool, list[str]]:
    warnings = []
    is_valid = True

    # 필수 필드 체크
    for section, key in REQUIRED_FIELDS:
        section_data = data.get(section, {})
        field_data = section_data.get(key, {})
        if not field_data or "error" in field_data:
            logger.warning("필수 데이터 누락: %s.%s", section, key)
            warnings.append(f"필수 데이터 누락: {section}.{key}")
            is_valid = False

    # 이상치 탐지: change_pct가 임계값 초과 시 경고 (수집 실패는 아님)
    for section in ("kr_market", "us_market"):
        section_data = data.get(section, {})
        for key, field_data in section_data.items():
            if not isinstance(field_data, dict):
                continue
            change_pct = field_data.get("change_pct")
            if change_pct is not None and abs(change_pct) > ANOMALY_THRESHOLD_PCT:
                msg = f"이상치 감지: {section}.{key} 변동률 {change_pct:.2f}% (임계값 ±{ANOMALY_THRESHOLD_PCT}%)"
                logger.warning(msg)
                warnings.append(msg)

    return is_valid, warnings
