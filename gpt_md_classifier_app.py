import streamlit as st
from openai import OpenAI
import os
import tempfile
import shutil
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import defaultdict
import time

# ✅ OpenAI client
client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])

# ✅ 언어 설정
LANG = st.sidebar.selectbox("🌐 Language / 언어", ["한국어", "English"])
is_ko = LANG == "한국어"

# ✅ 텍스트 사전
T = {
    "title": "🧩 ai 파일 태그,키워드 분류기" if is_ko else "🧩 ai-Based keyword / Tag Classifier",
    "upload_label": "⬆️ Markdown (.md) 파일 업로드" if is_ko else "⬆️ Upload Markdown (.md) files",
    "download_box": "📦 ZIP 다운로드 박스" if is_ko else "📦 ZIP Download Box",
    "download_btn": "📥 ZIP 다운로드" if is_ko else "📥 Download ZIP",
    "download_info": "✅ 분석이 완료되었습니다. ZIP 파일을 다운로드하세요." if is_ko else "✅ Analysis complete. Download the ZIP file.",
    "waiting_info": "📂 파일을 업로드하면 분석이 자동 시작됩니다." if is_ko else "📂 Upload files to start analysis.",
    "progress_title": "📊 태그 추출 및 그룹화 진행 중..." if is_ko else "📊 Tag extraction and grouping in progress...",
    "progress_done": "✅ 분석 완료" if is_ko else "✅ Analysis complete",
    "preview_title": "🧾 그룹화 결과 미리보기" if is_ko else "🧾 Preview Grouped Results",
    "group_files": "📄 파일 수" if is_ko else "📄 Files",
    "keywords": "📌 태그" if is_ko else "📌 Tags",
    "restart_confirm": "정말 다시 시작하시겠습니까?" if is_ko else "Are you sure you want to restart?",
    "restart_btn": "🔄 다시 시작" if is_ko else "🔄 Restart",
    "model_label": "📌 사용할 GPT 모델" if is_ko else "📌 GPT Model to Use",
    "caption": "※ ZIP 다운로드 후 임시 폴더는 자동 삭제됩니다." if is_ko else "※ Temporary folder will be deleted after ZIP download.",
    "analyzing": "분석 중..." if is_ko else "Analyzing...",
    "tags": "태그" if is_ko else "Tags",
    "prompt": (
        "다음은 마크다운 문서입니다. 이 문서에서 주요 키워드 또는 태그 3~5개를 뽑아주세요. "
        "한글 또는 영어 단어로 간결하게 추출하세요.\n출력 형식:\n태그: tag1, tag2, tag3"
        if is_ko else
        "The following is a Markdown document. Extract 3 to 5 key tags or keywords from this content. "
        "Return them as simple English or Korean words.\nFormat:\nTags: tag1, tag2, tag3"
    )
}

# ✅ 페이지 설정
st.set_page_config(page_title=T["title"], page_icon="🧩", layout="wide")
st.title(T["title"])

# ✅ 모델 선택 + 다시 시작 버튼
model_choice = st.sidebar.selectbox(T["model_label"], ["gpt-5-nano", "gpt-4", "gpt-3.5-turbo"], index=0)
if st.sidebar.button(T["restart_btn"]):
    if st.sidebar.radio(T["restart_confirm"], ["아니오", "예"] if is_ko else ["No", "Yes"], index=0, key="reset_confirm") == ("예" if is_ko else "Yes"):
        st.session_state.clear()
        st.experimental_rerun()

# ✅ 세션 초기화
if "zip_path" not in st.session_state:
    st.session_state.zip_path = None
    st.session_state.analysis_done = False
    st.session_state.grouped = None
    st.session_state.file_infos = None

# ✅ 고정 상태 메시지 함수
def show_fixed_status(msg):
    st.markdown(
        f"""
        <div style="
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            background-color: #fef3c7;
            color: #000;
            padding: 12px 20px;
            z-index: 1000;
            font-weight: bold;
            border-bottom: 1px solid #e0e0e0;
            text-align: center;
        ">
        {msg}
        </div>
        <br><br><br>
        """,
        unsafe_allow_html=True
    )

# ✅ GPT 태그 추출 함수
def extract_tags(filename, content):
    prompt = f"{T['prompt']}\n\n문서명: {filename}\n내용:\n{content[:1000].rsplit('\\n', 1)[0]}..."
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
    except Exception:
        return []

# ✅ 태그 기반 그룹핑
def group_by_tags(file_infos):
    tag_to_files = defaultdict(list)
    for info in file_infos:
        for tag in info["tags"]:
            tag_to_files[tag].append(info)

    grouped = {}
    used = set()
    group_num = 1
    for tag, files in tag_to_files.items():
        group_files = [f for f in files if f["filename"] not in used]
        if not group_files:
            continue
        group_name = f"Group {group_num}: {tag}"
        grouped[group_name] = {
            "files": [f["filename"] for f in group_files],
            "keywords": list(set(tag for f in group_files for tag in f["tags"]))
        }
        for f in group_files:
            used.add(f["filename"])
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

# ✅ 분석 및 그룹핑
if uploaded_files and not st.session_state.analysis_done:
    show_fixed_status(T["progress_title"])
    start_time = time.time()

    file_infos = []
    seen = set()
    future_to_file = {}

    progress = st.empty()
    status_text = st.empty()
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
            status_text.markdown(f"📄 `{info['filename']}` {T['analyzing']} ({int(percent*100)}%)")
            log_area.markdown(f"✅ `{info['filename']}` → {T['tags']}: {', '.join(tags)}")

    grouped = group_by_tags(file_infos)

    # ✅ 결과 ZIP 생성
    st.subheader(T["preview_title"])
    temp_dir = tempfile.mkdtemp()
    saved_files = []

    for topic, group_data in grouped.items():
        folder = os.path.join(temp_dir, topic.replace(" ", "_"))
        os.makedirs(folder, exist_ok=True)

        st.markdown(f"### 📁 {topic}")
        st.markdown(f"- {T['keywords']}: {', '.join(group_data['keywords'])}")
        st.markdown(f"- {T['group_files']}: {len(group_data['files'])}")

        readme_path = os.path.join(folder, "README.md")
        with open(readme_path, "w", encoding="utf-8") as readme:
            readme.write(f"# {topic}\n\n")
            readme.write(f"**{T['keywords']}:** {', '.join(group_data['keywords'])}\n\n")
            readme.write("## 📄 파일 목록\n")
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

    zip_path = os.path.join(temp_dir, "tag_grouped_markdowns.zip")
    with zipfile.ZipFile(zip_path, "w") as zipf:
        for file in saved_files:
            arcname = os.path.relpath(file, temp_dir)
            zipf.write(file, arcname)

    st.session_state.zip_path = zip_path
    st.session_state.analysis_done = True
    st.session_state.grouped = grouped
    st.session_state.file_infos = file_infos

    shutil.rmtree(temp_dir)
    elapsed = time.time() - start_time
    minutes, seconds = divmod(elapsed, 60)

    show_fixed_status(T["progress_done"])
    st.success(f"⏱ 분석 소요 시간: {int(minutes)}분 {int(seconds)}초" if is_ko else f"⏱ Elapsed time: {int(minutes)}m {int(seconds)}s")
    st.caption(T["caption"])
