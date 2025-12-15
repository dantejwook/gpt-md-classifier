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
