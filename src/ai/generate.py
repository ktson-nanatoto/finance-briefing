import json
import os
import google.generativeai as genai
from src.ai.prompt import SYSTEM_PROMPT, build_user_prompt
from src.utils.logger import get_logger

logger = get_logger("generate")

MODEL = "gemini-2.5-flash"
MAX_TOKENS = 4096


def generate_analysis(data: dict) -> dict:
    genai.configure(api_key=os.environ["GEMINI_API_KEY"])

    model = genai.GenerativeModel(
        model_name=MODEL,
        system_instruction=SYSTEM_PROMPT,
        generation_config=genai.GenerationConfig(
            max_output_tokens=MAX_TOKENS,
            temperature=0.3,
        ),
    )

    try:
        response = model.generate_content(build_user_prompt(data))
        raw = response.text.strip()

        usage = response.usage_metadata
        logger.info(
            "Gemini API 사용량 — 입력: %d, 출력: %d",
            usage.prompt_token_count,
            usage.candidates_token_count,
        )

        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.strip()

        return json.loads(raw)

    except json.JSONDecodeError as e:
        logger.error("Gemini 응답 JSON 파싱 실패: %s", e)
        raise
    except Exception as e:
        logger.error("Gemini API 호출 실패: %s", e)
        raise
