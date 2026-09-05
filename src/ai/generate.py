import json
import os
from groq import Groq
from src.ai.prompt import SYSTEM_PROMPT, build_user_prompt
from src.utils.logger import get_logger

logger = get_logger("generate")

MODEL = "qwen/qwen3.8-27b"
MAX_TOKENS = 4096


def generate_analysis(data: dict, report_type: str = "morning") -> dict:
    client = Groq(api_key=os.environ["GROQ_API_KEY"])

    try:
        response = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": build_user_prompt(data, report_type)},
            ],
            max_tokens=MAX_TOKENS,
            temperature=0.3,
            response_format={"type": "json_object"},  # JSON 출력 강제
        )

        usage = response.usage
        logger.info(
            "Groq API 사용량 — 입력: %d, 출력: %d",
            usage.prompt_tokens,
            usage.completion_tokens,
        )

        return json.loads(response.choices[0].message.content)

    except json.JSONDecodeError as e:
        logger.error("Groq 응답 JSON 파싱 실패: %s", e)
        raise
    except Exception as e:
        logger.error("Groq API 호출 실패: %s", e)
        raise
