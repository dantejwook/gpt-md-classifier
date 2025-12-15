import streamlit as st
from openai import OpenAI
import os
import tempfile
import shutil
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed

# ✅ OpenAI SDK v1+
client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])

# ✅ 페이지 설정
st.set_page_config(page_title="📁 Markdown 자동 분류기", page_icon="📚", layout="wide")
st.title("📁 ChatGPT 기반 Markdown 자동 분류 + 병합 도구")

st.markdown("""
Markdown 파일을 업로드하면 GPT가 내용을 분석하고 주제별로 그룹화하여 ZIP 파일로 제공합니다.
""")

# ✅ 세션 상태 초기화
if "zip_path" not in st.session_state:
    st.session_state.zip_path = None
    st.session_state.grouped = None
    st.session_state.file_infos = None
    st.session_state.analysis_done = False
    st.session_state.show_confirm = False  # 초기화 확장창 표시 여부

# ✅ 사이드바: 모델 선택 + 초기화 버튼
st.sidebar.markdown("## ⚙️ 설정")

model_choice = st.sidebar.selectbox(
    "📌 사용할 GPT 모델",
    ["gpt-5-nano", "gpt-3.5-turbo"],
    index=0,
)

# 🔄 초기화 요청 → 확장 확인창 띄우기
if st.sidebar.button("🔄 다시 시작"):
    st.session_state.show_confirm = True

# ✅ 초기화 확인창
if st.session_state.show_confirm:
    with st.sidebar.expander("⚠️ 정말 초기화할까요?", expanded=True):
        st.warning("모든 분석 결과와 업로드된 파일이 초기화됩니다.")
        col1, col2 = st.columns(2)
        with col1:
            if st.button("✅ 예, 초기화할게요"):
                st.session_state.clear()
                st.experimental_rerun()
        with col2:
            if st.button("❌ 취소"):
                st.session_state.show_confirm = False

# ✅ 좌우 컬럼
left_col, right_col = st.columns([1, 2.5])

with left_col:
    uploaded_files = st.file_uploader("⬆️ Markdown (.md) 파일 업로드", type="md", accept_multiple_files=True)

with right_col:
    st.markdown("### 📦 다운로드 박스")
    if st.session_state.analysis_done and st.session_state.zip_path:
        with open(st.session_state.zip_path, "rb") as fp:
            st.download_button("📥 ZIP 다운로드", fp, file_name="merged_markdowns.zip", mime="application/zip")
        st.success("✅ 분석이 완료되었습니다. ZIP 파일을 다운로드하세요.")
    else:
        st.info("파일을 업로드하면 분석이 시작되고 이곳에 ZIP 다운로드가 표시됩니다.")

# ✅ GPT 요약 분석 함수
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
            model=model_choice,
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

# ✅ GPT 그룹핑
def get_grouped_topics(file_infos):
    merge_prompt = """
다음은 여러 마크다운 파일의 주제 및 요약입니다. 관련 있는 파일끼리 5~10개의 그룹으로 나눠주세요.
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

# ✅ 자동 분석 시작
if uploaded_files and not st.session_state.analysis_done:
    st.subheader("📊 파일 분석 중...")

    file_infos = []
    seen_files = set()
    future_to_file = {}

    progress = st.progress(0.0)
    status_text = st.empty()
    log_container = st.container()

    with ThreadPoolExecutor(max_workers=10) as executor:
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

            percent = (i + 1) / len(future_to_file)
            progress.progress(percent)
            status_text.markdown(f"📄 분석 중: {i+1}/{len(future_to_file)}개 완료")
            log_container.markdown(f"✅ **{info['filename']}**")

    grouped = get_grouped_topics(file_infos)

    # ✅ ZIP 생성
    temp_dir = tempfile.mkdtemp()
    saved_files = []

    for topic, group_data in grouped.items():
        filenames = group_data["files"]
        keywords = group_data.get("keywords", [])
        folder = os.path.join(temp_dir, topic.replace(" ", "_"))
        os.makedirs(folder, exist_ok=True)

        readme_path = os.path.join(folder, "README.md")
        with open(readme_path, "w", encoding="utf-8") as readme:
            readme.write(f"# {topic}\n\n")
            if keywords:
                readme.write(f"**📌 키워드:** {', '.join(keywords)}\n\n")
            readme.write("## 📄 포함된 파일 목록\n")
            for f in filenames:
                readme.write(f"- {f}\n")
            saved_files.append(readme_path)

        for f in filenames:
            match = next((item for item in file_infos if item["filename"] == f), None)
            if match:
                full_path = os.path.join(folder, f)
                with open(full_path, "w", encoding="utf-8") as md_file:
                    md_file.write(match["content"])
                saved_files.append(full_path)

    zip_path = os.path.join(temp_dir, "merged_markdowns.zip")
    with zipfile.ZipFile(zip_path, "w") as zipf:
        for filepath in saved_files:
            arcname = os.path.relpath(filepath, temp_dir)
            zipf.write(filepath, arcname)

    # ✅ 세션 상태 저장
    st.session_state.zip_path = zip_path
    st.session_state.grouped = grouped
    st.session_state.file_infos = file_infos
    st.session_state.analysis_done = True
