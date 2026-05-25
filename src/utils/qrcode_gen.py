import base64
import io
import qrcode
from qrcode.image.pure import PyPNGImage
from src.utils.logger import get_logger

logger = get_logger("qrcode_gen")


def generate_qr_base64(url: str) -> str:
    """URL을 QR코드로 변환하여 base64 문자열로 반환 (HTML img src 임베드용)"""
    try:
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=4,
            border=2,
        )
        qr.add_data(url)
        qr.make(fit=True)
        img = qr.make_image(image_factory=PyPNGImage)
        buf = io.BytesIO()
        img.save(buf)
        return base64.b64encode(buf.getvalue()).decode("utf-8")
    except Exception as e:
        logger.error("QR코드 생성 실패: %s", e)
        return ""
