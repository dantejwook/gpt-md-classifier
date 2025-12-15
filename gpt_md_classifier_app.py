import streamlit as st
from openai import OpenAI
import os
import tempfile
import shutil
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed

# ✅ OpenAI SDK v1+
client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])

# ✅ 페이지 기본 설정
st.set_page_config(page_title="📁 Markdown 자동 병합 분류기", page_icon="📚", layout="wide")

# ✅ 제목 및 설명
st.title("📁 ChatGPT 기반 Markdown 자동 분류 + 병합 도구")
st.markdown("""
업로드한 Markdown 파일들을 GPT가 자동 분석하여 **시너지 있는 주제 그룹**으로 나눕니다.  
최대 1000개의 파일을 업로드할 수 있으며, 결과는 ZIP으로 다운로드할 수 있습니다.
""")

# ✅ 레이아웃 분할 (왼쪽: 업로드 / 오른쪽: 안내 및 ZIP 다운로드)
left_col, right_col = st.columns([1, 1.2])

# ✅ 파일 업로드
with left_col:
    uploaded_files = st.file_uploader(
        "⬆️ Markdown (.md) 파일 업로드 (최대 1000개)",
        type="md",
        accept_multiple_files=True
    )

# ✅ 분석 결과 저장 변수
grouped = {}
saved_files = []
zip_path = ""
file_infos = []

# ✅ GPT 요약 함수
def get_topic_and_summary(filename, content):
    prompt = f"""
다음은 마크다운 문서입니다. 아래 문서의 주요 주제를 짧게 한 문장으로, 핵심 요약도 한 문장으로 추출해주세요.
출력 형식:
주제: [주제명]
요약: [요약내용]

문서 제목: {filename}
내용:
{content[:1000].rsplit('\\n', 1)[0]}...
"""
    try:
        res = client.chat.completions.create(
            model="gpt-5-nano",  # gpt-5-nano 사용
            messages=[{"role": "user", "content": prompt}]
        )
        text = res.choices[0].message.content.strip()
        topic, summary = "Unknown", ""
        for line in text.split("\n"):
            if line.lower().startswith("주제:"):
                topic = line.split(":", 1)[1].strip()
            elif line.lower().startswith("요약:"):
                summary = line.split(":", 1)[1].strip()
        return topic, summary
    except Exception as e:
        return "Unknown", f"❗ 오류: {str(e)}"

# ✅ GPT 그룹화 함수
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
            model="gpt-5-nano",
            messages=[{"role": "user", "content": merge_prompt}]
        )
        text = res.choices[0].message.content.strip()
        groups, current_group = {}, None
        for line in text.split("\n"):
            if ":" in line and ".md" in line:
                topic, files_str = line.split(":", 1)
                filenames = [f.strip() for f in files_str.split(",") if f.strip()]
                current_group = topic.strip()
                groups[current_group] = {"files": filenames, "keywords": []}
            elif "키워드:" in line and current_group:
                keyword_str = line.split(":", 1)[1]
                groups[current_group]["keywords"] = [k.strip() for k in keyword_str.split(",")]
        return groups
    except Exception as e:
        st.error(f"병합 처리 중 오류 발생: {e}")
        return {}

# ✅ 메인 처리 로직
if uploaded_files:
    st.subheader("📊 파일 분석 및 병합 중...")

    future_to_file = {}
    seen_files = set()

    # ▶️ 하단 레이아웃: 진행 바 및 로그 구역
    progress = st.progress(0.0)
    status_text = st.empty()
    log_container = st.container()

    with ThreadPoolExecutor(max_workers=5) as executor:
        for uploaded_file in uploaded_files:
            filename = uploaded_file.name
            if filename in seen_files:
                continue
            seen_files.add(filename)
            content = uploaded_file.read().decode("utf-8")
            future = executor.submit(get_topic_and_summary, filename, content)
            future_to_file[future] = {"filename": filename, "content": content}

        for i, future in enumerate(as_completed(future_to_file)):
            topic, summary = future.result()
            info = future_to_file[future]
            info["topic"] = topic
            info["summary"] = summary
            file_infos.append(info)

            # ✅ 진행률 및 로그 출력
            percent = (i + 1) / len(future_to_file)
            progress.progress(percent)
            status_text.markdown(f"📄 분석 중: {i+1}/{len(future_to_file)}개 완료")
            log_container.markdown(f"✅ **{info['filename']}** → 주제: _{topic}_ / 요약: _{summary}_")

    # ✅ 그룹 생성
    grouped = get_grouped_topics(file_infos)

    # ✅ 임시 디렉토리 및 ZIP 생성
    temp_dir = tempfile.mkdtemp()
    for topic, group_data in grouped.items():
        filenames = group_data["files"]
        keywords = group_data.get("keywords", [])
        folder = os.path.join(temp_dir, topic.replace(" ", "_"))
        os.makedirs(folder, exist_ok=True)

        # ✅ README 생성
        readme_path = os.path.join(folder, "README.md")
        with open(readme_path, "w", encoding="utf-8") as readme:
            readme.write(f"# {topic}\n\n")
            if keywords:
                readme.write(f"**📌 키워드:** {', '.join(keywords)}\n\n")
            readme.write("## 📄 포함된 파일 목록\n")
            for f in filenames:
                readme.write(f"- {f}\n")
            saved_files.append(readme_path)

        # ✅ 실제 파일 복사
        for f in filenames:
            match = next((item for item in file_infos if item["filename"] == f), None)
            if match:
                full_path = os.path.join(folder, f)
                with open(full_path, "w", encoding="utf-8") as md_file:
                    md_file.write(match["content"])
                saved_files.append(full_path)

    # ✅ ZIP 압축
    zip_path = os.path.join(temp_dir, "merged_markdowns.zip")
    with zipfile.ZipFile(zip_path, "w") as zipf:
        for filepath in saved_files:
            arcname = os.path.relpath(filepath, temp_dir)
            zipf.write(filepath, arcname)

# ✅ 오른쪽 다운로드 영역
with right_col:
    if grouped and saved_files:
        with open(zip_path, "rb") as fp:
            st.download_button("📦 병합 ZIP 다운로드", fp, file_name="merged_markdowns.zip", mime="application/zip")
        st.success("✅ 파일 분석 완료. ZIP 파일을 다운로드하세요.")
    else:
        st.info("파일을 업로드하면 분석이 시작되고, 여기에서 결과를 다운로드할 수 있습니다.")
