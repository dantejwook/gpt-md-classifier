import streamlit as st
from openai import OpenAI
import os
import tempfile
import shutil
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import defaultdict, Counter
import time

# 🌐 다국어 설정
LANG = st.sidebar.selectbox("🌐 Language", ["한국어", "English"])
is_ko = LANG == "한국어"

# 텍스트 딕셔너리
T = {
    "title": "🧩 GPT 기반 Markdown 태그 분류기" if is_ko else "🧩 GPT-based Markdown Tag Grouper",
    "desc": "Markdown 파일을 업로드하면 GPT가 태그를 추출하고 그룹화하여 ZIP 파일로 제공합니다." if is_ko else "Upload markdown files, and GPT will extract tags and group them into a ZIP.",
    "upload": "⬆️ Markdown (.md) 파일 업로드" if is_ko else "⬆️ Upload Markdown Files",
    "model": "📌 사용할 GPT 모델" if is_ko else "📌 GPT Model",
    "restart": "🔄 다시 시작" if is_ko else "🔄 Restart",
    "confirm_restart": "정말 다시 시작하시겠습니까?" if is_ko else "Are you sure you want to restart?",
    "yes": "예" if is_ko else "Yes",
    "no": "아니오" if is_ko else "No",
    "progress_title": "📊 태그 추출 및 그룹화 진행 중..." if is_ko else "📊 Extracting tags and grouping...",
    "progress_done": "✅ 분석 완료" if is_ko else "✅ Analysis complete",
    "download_btn": "📥 ZIP 다운로드" if is_ko else "📥 Download ZIP",
    "caption": "※ 다운로드 후 임시 폴더는 자동 삭제됩니다." if is_ko else "※ Temp folder is deleted after download.",
    "group": "그룹" if is_ko else "Group",
    "tag": "태그" if is_ko else "Tags",
    "file_count": "📄 파일 수" if is_ko else "📄 File count"
}

# ✅ OpenAI Client
client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])

# ✅ Streamlit 설정
st.set_page_config(page_title="📁 Markdown 자동 분류기", page_icon="📚", layout="wide")
st.title(T["title"])
st.markdown(T["desc"])

# ✅ 사이드바 설정
model_choice = st.sidebar.selectbox(T["model"], ["gpt-5-nano"], index=0)

# 🔁 다시 시작 버튼
if st.sidebar.button(T["restart"]):
    if st.sidebar.radio(T["confirm_restart"], [T["yes"], T["no"]]) == T["yes"]:
        st.session_state.clear()
        st.experimental_rerun()

# ✅ 업로드 UI
left_col, right_col = st.columns([1.5, 2.5])
with left_col:
    uploaded_files = st.file_uploader(T["upload"], type="md", accept_multiple_files=True)

with right_col:
    if "zip_path" in st.session_state and st.session_state["zip_path"]:
        with open(st.session_state["zip_path"], "rb") as fp:
            st.download_button(T["download_btn"], fp, file_name="tag_grouped_markdowns.zip", mime="application/zip")
        st.success(T["progress_done"])
        st.caption(T["caption"])

# ✅ 상태 메시지 상단 고정
def show_fixed_status(msg):
    st.markdown(f"""
    <div style="
        position: fixed;
        top: 0;
        left: 0;
        width: 100%;
        background-color: #fceabb;
        color: black;
        padding: 10px;
        z-index: 1000;
        text-align: center;
        font-weight: bold;
        border-bottom: 1px solid #e0e0e0;
    ">
        {msg}
    </div>
    <br><br><br>
    """, unsafe_allow_html=True)

# ✅ GPT: 키워드 추출 함수
def extract_tags(filename, content):
    prompt = f"""
다음은 마크다운 문서입니다. 이 문서에서 주요 키워드 또는 주제 3~5개를 뽑아주세요. 한글 또는 영어 단어로 간결하게 추출하세요.
출력 형식:
태그: tag1, tag2, tag3

문서명: {filename}
내용:
{content[:1000].rsplit('\\n', 1)[0]}...
""" if is_ko else f"""
This is a markdown file. Please extract 3 to 5 major keywords or tags that represent its topic. Output in a simple list format.
Output format:
Tags: tag1, tag2, tag3

Filename: {filename}
Content:
{content[:1000].rsplit('\\n', 1)[0]}...
"""
    try:
        res = client.chat.completions.create(
            model=model_choice,
            messages=[{"role": "user", "content": prompt}]
        )
        text = res.choices[0].message.content.strip()
        tags = []
        for line in text.split("\n"):
            if "태그:" in line or "Tags:" in line:
                tag_str = line.split(":", 1)[1]
                tags = [t.strip().lower() for t in tag_str.split(",") if t.strip()]
        return tags
    except Exception as e:
        return []

# ✅ 태그 기반 그룹핑 함수
def group_by_tags(file_infos):
    tag_to_files = defaultdict(list)
    for info in file_infos:
        for tag in info["tags"]:
            tag_to_files[tag].append(info)

    grouped = {}
    used_files = set()
    group_num = 1

    for tag, files in tag_to_files.items():
        group_files = [f for f in files if f["filename"] not in used_files]
        if not group_files:
            continue
        group_name = f"{T['group']} {group_num}: {tag}"
        grouped[group_name] = {
            "files": [f["filename"] for f in group_files],
            "keywords": list(set(t for f in group_files for t in f["tags"]))
        }
        for f in group_files:
            used_files.add(f["filename"])
        group_num += 1
    return grouped

# ✅ 좌우 컬럼 UI
left, right = st.columns([1.2, 2.8])
with left:
    uploaded_files = st.file_uploader(T["upload_label"], type="md", accept_multiple_files=True)

with right:
    st.markdown(f"### {T['download_box']}")
    if st.session_state.analysis_done and st.session_state.zip_path:
        with open(st.session_state.zip_path, "rb") as fp:
            st.download_button(T["download_btn"], fp, file_name="tag_grouped_markdowns.zip", mime="application/zip")
        st.success(T["download_info"])
    else:
        st.info(T["waiting_info"])

# ✅ 메인 실행
if uploaded_files and "zip_path" not in st.session_state:
    start_time = time.time()
    show_fixed_status(T["progress_title"])

    file_infos = []
    seen = set()
    future_to_file = {}
    progress = st.progress(0.0)
    status = st.empty()
    log_area = st.container()

    with ThreadPoolExecutor(max_workers=10) as executor:
        for file in uploaded_files:
            name = file.name
            if name in seen:
                continue
            seen.add(name)
            content = file.read().decode("utf-8")
            future = executor.submit(extract_tags, name, content)
            future_to_file[future] = {"filename": name, "content": content}

        for i, future in enumerate(as_completed(future_to_file)):
            tags = future.result()
            info = future_to_file[future]
            info["tags"] = tags
            file_infos.append(info)

            percent = (i + 1) / len(future_to_file)
            progress.progress(percent)
            status.markdown(f"📄 `{info['filename']}` → {T['tag']}: {', '.join(tags)}")

    grouped = group_by_tags(file_infos)

    # ✅ 그룹 결과 저장
    temp_dir = tempfile.mkdtemp()
    saved_files = []

    for topic, group_data in grouped.items():
        folder = os.path.join(temp_dir, topic.replace(" ", "_"))
        os.makedirs(folder, exist_ok=True)

        readme_path = os.path.join(folder, "README.md")
        with open(readme_path, "w", encoding="utf-8") as readme:
            readme.write(f"# {topic}\n\n")
            readme.write(f"**📌 {T['tag']}:** {', '.join(group_data['keywords'])}\n\n")
            readme.write(f"## 📄 {T['file_count']}\n")
            for fname in group_data["files"]:
                readme.write(f"- {fname}\n")
            saved_files.append(readme_path)

        for fname in group_data["files"]:
            match = next((f for f in file_infos if f["filename"] == fname), None)
            if match:
                path = os.path.join(folder, fname)
                with open(path, "w", encoding="utf-8") as f:
                    f.write(match["content"])
                saved_files.append(path)

    # ✅ 키워드  빈도 요약
    all_tags = [tag for f in file_infos for tag in f["tags"]]
    tag_counts = Counter(all_tags)
    summary_path = os.path.join(temp_dir, "tags_summary.md")
    with open(summary_path, "w", encoding="utf-8") as f:
        f.write("# 📊 키워드 사용 빈도 요약\n\n" if is_ko else "# 📊 Tag Usage Summary\n\n")
        f.write("| 키워드 | 사용 횟수 |\n|------|----------|\n" if is_ko else "| Tag | Count |\n|------|----------|\n")
        for tag, count in tag_counts.most_common():
            f.write(f"| `{tag}` | {count} |\n")
    saved_files.append(summary_path)

    # ✅ ZIP 압축
    zip_path = os.path.join(temp_dir, "tag_grouped_markdowns.zip")
    with zipfile.ZipFile(zip_path, "w") as zipf:
        for path in saved_files:
            arcname = os.path.relpath(path, temp_dir)
            zipf.write(path, arcname)

    elapsed = time.time() - start_time
    minutes, seconds = divmod(elapsed, 60)
    show_fixed_status(T["progress_done"])
    st.success(f"⏱ 분석 소요 시간: {int(minutes)}분 {int(seconds)}초" if is_ko else f"⏱ Elapsed time: {int(minutes)} min {int(seconds)} sec")

    # ✅ 세션 저장
    st.experimental_rerun()
