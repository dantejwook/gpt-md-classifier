import streamlit as st
from openai import OpenAI
import os
import tempfile
import shutil
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
import time
import json

# 🔑 OpenAI client 생성
client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"] if "OPENAI_API_KEY" in st.secrets else None)

# UI 기본 설정
st.set_page_config(page_title="📁 Markdown 주제 분류기 (자동 병합 포함)", page_icon="📚", layout="wide")

st.title("📁 ChatGPT 기반 Markdown 자동 분류 + 주제 병합")
st.markdown("""
AI가 마크다운 파일을 분석해 비슷한 문서끼리 **의미적으로 묶고**, 주제별로 폴더를 자동 생성합니다.
""")

uploaded_files = st.file_uploader("⬆️ Markdown (.md) 파일 업로드", type="md", accept_multiple_files=True)

if not client.api_key:
    st.error("❗ OpenAI API 키가 설정되지 않았습니다.")
    st.stop()

# GPT-5-nano: 파일별 주제 + 요약 추출
def get_topic_and_summary(filename, content):
    prompt = f"""
다음 문서의 핵심 주제와 간단한 내용을 각각 한 문장으로 요약하세요.

출력 예시:
주제: 데이터 분석
요약: 이 문서는 pandas와 numpy를 활용한 데이터 처리 과정을 설명합니다.

문서 제목: {filename}
내용:
{content[:800]}
"""
    try:
        res = client.chat.completions.create(
            model="gpt-5-nano",
            messages=[{"role": "user", "content": prompt}]
        )
        lines = res.choices[0].message.content.strip().split("\n")
        topic = lines[0].replace("주제:", "").strip()
        summary = lines[1].replace("요약:", "").strip() if len(lines) > 1 else ""
        return topic, summary
    except Exception as e:
        return "Unknown", ""

# GPT-3.5-turbo: 병합 요청
def get_grouped_topics(file_infos):
    merge_prompt = """
다음은 여러 마크다운 파일의 주제와 요약 내용입니다.
서로 유사하거나 시너지가 있는 파일끼리 묶고, 각 그룹에 어울리는 주제를 붙여주세요.
너무 세분화하지 말고, 총 5~10개의 그룹으로 압축해서 보여주세요.

출력 예시:
- 데이터 분석: file1.md, file2.md
- AI 응용: file3.md, file4.md

입력:
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
        for line in text.split("\n"):
            if ":" in line:
                topic, files_str = line.split(":", 1)
                filenames = [f.strip() for f in files_str.split(",") if f.strip()]
                groups[topic.strip()] = filenames
        return groups
    except Exception as e:
        st.error(f"병합 처리 중 오류 발생: {e}")
        return {}

if uploaded_files:
    st.subheader("📊 파일 분석 및 병합 중...")
    progress = st.progress(0)
    file_infos = []

    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = []
        for i, uploaded_file in enumerate(uploaded_files):
            content = uploaded_file.read().decode("utf-8")
            filename = uploaded_file.name
            futures.append(executor.submit(get_topic_and_summary, filename, content))
            file_infos.append({"filename": filename, "content": content})

        for i, future in enumerate(as_completed(futures)):
            topic, summary = future.result()
            file_infos[i]["topic"] = topic
            file_infos[i]["summary"] = summary
            progress.progress((i+1)/len(uploaded_files))

    grouped = get_grouped_topics(file_infos)

    # 임시 폴더 생성 및 저장
    temp_dir = tempfile.mkdtemp()
    for group_topic, filenames in grouped.items():
        group_folder = os.path.join(temp_dir, group_topic.replace(" ", "_"))
        os.makedirs(group_folder, exist_ok=True)
        for name in filenames:
            match = next((f for f in file_infos if f["filename"] == name), None)
            if match:
                with open(os.path.join(group_folder, name), "w", encoding="utf-8") as f:
                    f.write(match["content"])

    st.success("✅ 파일 분류 및 병합이 완료되었습니다!")

    for topic, files in grouped.items():
        with st.expander(f"📂 {topic} ({len(files)}개)"):
            for f in files:
                st.markdown(f"- `{f}`")

    # 압축 및 다운로드
    zip_path = os.path.join(temp_dir, "merged_markdowns.zip")
    with zipfile.ZipFile(zip_path, "w") as zipf:
        for root, _, files in os.walk(temp_dir):
            for file in files:
                filepath = os.path.join(root, file)
                arcname = os.path.relpath(filepath, temp_dir)
                zipf.write(filepath, arcname)

    with open(zip_path, "rb") as fp:
        st.download_button("📦 병합 결과 ZIP 다운로드", fp, file_name="merged_markdowns.zip", mime="application/zip")

    shutil.rmtree(temp_dir)
