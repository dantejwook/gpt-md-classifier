import streamlit as st
from openai import OpenAI
import os
import tempfile
import shutil
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
import time
import json
import openai
import backoff

# OpenAI Client 생성
client = OpenAI(api_key=st.secrets.get("OPENAI_API_KEY"))

st.set_page_config(
    page_title="📁 Markdown 자동 병합 분류기",
    page_icon="📚",
    layout="wide"
)

st.title("📁 ChatGPT 기반 Markdown 자동 분류 + 주제 병합")
st.markdown("""
업로드한 Markdown 파일들을 GPT가 자동 분석하여 **시너지 있는 주제 그룹**으로 묶어줍니다.  
파일은 10개씩 묶어서 처리되며, 모든 결과는 ZIP으로 다운로드할 수 있습니다.
""")

uploaded_files = st.file_uploader(
    "⬆️ Markdown (.md) 파일 업로드 (최대 100개)",
    type="md",
    accept_multiple_files=True
)

if not client.api_key:
    st.error("❗ OpenAI API 키가 설정되지 않았습니다.")
    st.stop()

# ------------------------------
# Retry 처리 - GPT 요청 재시도
# ------------------------------
@backoff.on_exception(backoff.expo, openai.RateLimitError, max_tries=3)
def get_topic_and_summary(filename, content):
    prompt = f"""
다음은 마크다운 문서입니다. 아래 문서의 주요 주제를 짧게 한 문장으로, 핵심 요약도 한 문장으로 추출해주세요.
출력 형식:
주제: [주제명]
요약: [요약내용]

문서 제목: {filename}
내용:
{content[:1000]}
"""
    try:
        res = client.chat.completions.create(
            model="gpt-3.5-turbo",  # 혹은 gpt-4-turbo 사용 가능
            messages=[{"role": "user", "content": prompt}]
        )
        text = res.choices[0].message.content.strip()
        topic = "Unknown"
        summary = ""
        for line in text.split("\n"):
            if line.lower().startswith("주제:"):
                topic = line.split(":", 1)[1].strip()
            elif line.lower().startswith("요약:"):
                summary = line.split(":", 1)[1].strip()
        return topic or "Unknown", summary
    except Exception as e:
        st.warning(f"⚠️ {filename} 처리 중 오류 발생: {e}")
        return "Unknown", ""


def get_grouped_topics(file_infos):
    merge_prompt = """
다음은 여러 마크다운 파일의 주제 및 요약입니다. 주제와 요약이 유사하거나 관련 있는 파일끼리 묶어 5~10개의 그룹으로 나눠주세요.
그리고 각 그룹에 적절한 대표 키워드를 3~5개 생성해주세요.
출력 형식:
[그룹명]: 파일1.md, 파일2.md
키워드: 키워드1, 키워드2, 키워드3

목록:
"""
    for info in file_infos:
        merge_prompt += f"- {info['filename']}: {info['topic']} / {info['summary']}\n"

    try:
        res = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": merge_prompt}]
        )
        text = res.choices[0].message.content.strip()
        groups = {}
        current_group = None
        for line in text.split("\n"):
            if ":" in line and ".md" in line:
                topic, files_str = line.split(":", 1)
                filenames = [f.strip() for f in files_str.split(",") if f.strip()]
                current_group = topic.strip()
                groups[current_group] = {"files": filenames, "keywords": []}
            elif "키워드:" in line and current_group:
                keyword_str = line.split(":", 1)[1]
                groups[current_group]["keywords"] = [k.strip() for k in keyword_str.split(",")]
        return g
