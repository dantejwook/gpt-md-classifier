# 📁 Streamlit Markdown Auto Classifier (Final version)
import streamlit as st
from openai import OpenAI
import os
import tempfile
import shutil
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from uuid import uuid4
from math import ceil

# ✅ Initialize OpenAI client
client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])

# ✅ UI and page setup
st.set_page_config(page_title="📁 Markdown 자동 병합 분류기", page_icon="📚", layout="wide")
st.title("📁 ChatGPT 기반 Markdown 자동 분류 + 주제 병합")
st.markdown("""
Markdown 파일을 업로드하면 GPT가 자동으로 주제를 분석하고 관련 파일끼리 그룹화합니다.  
ZIP 파일로 다운로드할 수 있으며, 파일 수가 많아도 자동으로 나누어 처리합니다.
""")

# ✅ Init session state
if "processed" not in st.session_state:
    st.session_state.processed = False
    st.session_state.zip_path = None
    st.session_state.grouped = {}
    st.session_state.temp_dir = None
    st.session_state.file_infos = []

# ✅ Manual Reset Button
if st.button("🔄 다시 시작"):
    if st.session_state.temp_dir and os.path.exists(st.session_state.temp_dir):
        shutil.rmtree(st.session_state.temp_dir)
    for key in list(st.session_state.keys()):
        del st.session_state[key]
    st.experimental_rerun()

# ✅ File uploader
uploaded_files = st.file_uploader("⬆️ Markdown (.md) 파일 업로드", type="md", accept_multiple_files=True)

# ✅ GPT topic + summary extraction
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
            model="gpt-3.5-turbo",
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
        return "Unknown", ""

# ✅ GPT: Grouping
def get_grouped_topics(file_infos):
    merge_prompt = """
다음은 여러 마크다운 파일의 주제 및 요약입니다. 주제와 요약이 유사하거나 관련 있는 파일끼리 묶어 5~10개의 그룹으로 나눠주세요.
그리고 각 그룹에 적절한 대표 키워드를 3~5개, 시너지가 있을 만한 내용을 같이 생성해주세요.
출력 형식:
[그룹명]: 파일1.md, 파일2.md
키워드: 키워드1, 키워드2, 키워드3
요약 내용 : 이 둘은 

목록:
"""
        for info in chunk:
            prompt += f"- {info['unique_filename']}: {info['topic']} / {info['summary']}\n"

        try:
            res = client.chat.completions.create(
                model="gpt-5-nano",
                messages=[{"role": "user", "content": prompt}]
            )
            text = res.choices[0].message.content.strip()
            current_group = None
            for line in text.split("\n"):
                if ":" in line and ".md" in line:
                    topic, files_str = line.split(":", 1)
                    filenames = [f.strip() for f in files_str.split(",") if f.strip()]
                    current_group = topic.strip() + f" (Batch {i+1})"
                    grouped[current_group] = {"files": filenames, "keywords": []}
                elif "키워드:" in line and current_group:
                    keyword_str = line.split(":", 1)[1]
                    grouped[current_group]["keywords"] = [k.strip() for k in keyword_str.split(",")]
        except Exception as e:
            st.warning(f"⚠️ 그룹 {i+1} 처리 중 오류: {e}")

    return grouped

# ✅ Process files (only once per session)
if uploaded_files and not st.session_state.processed:
    st.subheader("📊 파일 분석 중...")
    file_infos = []
    file_id_map = {}
    future_to_file = {}

    with ThreadPoolExecutor(max_workers=5) as executor:
        progress = st.progress(0.0)
        status_text = st.empty()

        for uploaded_file in uploaded_files:
            original_name = uploaded_file.name
            unique_filename = f"{uuid4().hex[:8]}_{original_name}"
            content = uploaded_file.read().decode("utf-8")
            future = executor.submit(get_topic_and_summary, original_name, content)
            future_to_file[future] = {
                "filename": original_name,
                "unique_filename": unique_filename,
                "content": content
            }

        for i, future in enumerate(as_completed(future_to_file)):
            info = future_to_file[future]
            info["topic"], info["summary"] = future.result()
            file_infos.append(info)
            file_id_map[info["unique_filename"]] = info
            progress.progress((i + 1) / len(future_to_file))
            status_text.markdown(f"📄 분석 중: {i + 1}/{len(future_to_file)}개 완료")

    grouped = get_grouped_topics_chunked(file_infos)

    # ✅ Save ZIP
    temp_dir = tempfile.mkdtemp()
    saved_files = []

    for group_name, group_data in grouped.items():
        keywords = group_data.get("keywords", [])
        filenames = group_data["files"]
        folder = os.path.join(temp_dir, group_name.replace(" ", "_").replace("/", "_"))
        os.makedirs(folder, exist_ok=True)

        # README
        readme_path = os.path.join(folder, "README.md")
        with open(readme_path, "w", encoding="utf-8") as readme:
            readme.write(f"# {group_name}\n\n")
            if keywords:
                readme.write(f"**📌 키워드:** {', '.join(keywords)}\n\n")
            readme.write("## 📄 포함된 파일 목록\n")
            for f in filenames:
                original_name = f.split("_", 1)[-1] if "_" in f else f
                readme.write(f"- {original_name}\n")
            saved_files.append(readme_path)

        for f in filenames:
            match = file_id_map.get(f)
            if match:
                output_path = os.path.join(folder, match["filename"])
                with open(output_path, "w", encoding="utf-8") as out_file:
                    out_file.write(match["content"])
                saved_files.append(output_path)

    # ZIP path
    zip_path = os.path.join(temp_dir, "merged_markdowns.zip")
    with zipfile.ZipFile(zip_path, "w") as zipf:
        for file in saved_files:
            arcname = os.path.relpath(file, temp_dir)
            zipf.write(file, arcname)

    # ✅ Store in session
    st.session_state.processed = True
    st.session_state.zip_path = zip_path
    st.session_state.grouped = grouped
    st.session_state.temp_dir = temp_dir
    st.session_state.file_infos = file_infos

# ✅ Display result if already processed
if st.session_state.processed:
    st.subheader("🧾 분류 결과 미리보기")
    grouped = st.session_state.grouped
    zip_path = st.session_state.zip_path

    for group_name, group_data in grouped.items():
        st.markdown(f"### 📁 {group_name}")
        st.markdown(f"- 🔑 키워드: {', '.join(group_data.get('keywords', []))}")
        st.markdown(f"- 📄 파일 수: {len(group_data['files'])}")

    # ✅ Download button (no reprocessing)
    with open(zip_path, "rb") as fp:
        st.download_button("📦 병합 ZIP 다운로드", fp, file_name="merged_markdowns.zip", mime="application/zip")

    st.caption("※ ZIP 다운로드 후에도 다시 분석하지 않습니다. 다시 시작하려면 상단의 '🔄 다시 시작' 버튼을 눌러주세요.")
