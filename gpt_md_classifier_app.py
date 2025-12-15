import streamlit as st
from openai import OpenAI
import os
import tempfile
import shutil
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import defaultdict

# ✅ OpenAI client
client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])

# ✅ Streamlit 초기화
st.set_page_config(page_title="📎 태그 기반 Markdown 그룹화기", page_icon="🧩", layout="wide")
st.title("🧩 GPT 기반 Markdown 태그 분류기")

# ✅ 사이드바 설정
model_choice = st.sidebar.selectbox("📌 사용할 GPT 모델", ["gpt-5-nano","gpt-3.5-turbo"], index=0)

if st.sidebar.button("🔄 다시 시작"):
    st.session_state.clear()
    st.experimental_rerun()

# ✅ 업로드
uploaded_files = st.file_uploader("⬆️ Markdown (.md) 파일 업로드", type="md", accept_multiple_files=True)

# ✅ GPT: 태그 추출
def extract_tags(filename, content):
    prompt = f"""
다음은 마크다운 문서입니다. 이 문서에서 주요 키워드 또는 태그 3~5개를 뽑아주세요. 한글 또는 영어 단어로 간결하게 추출하세요.
출력 형식:
태그: tag1, tag2, tag3

문서명: {filename}
내용:
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

# ✅ 태그 기반 그룹핑
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
        group_name = f"Group {group_num}: {tag}"
        grouped[group_name] = {
            "files": [f["filename"] for f in group_files],
            "keywords": list(set(tag for f in group_files for tag in f["tags"]))
        }
        for f in group_files:
            used_files.add(f["filename"])
        group_num += 1

    return grouped

# ✅ 분석 및 처리
if uploaded_files:
    st.subheader("📊 태그 추출 및 그룹화 진행 중...")
    file_infos = []
    seen = set()
    future_to_file = {}

    progress = st.progress(0.0)
    status = st.empty()

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
            status.markdown(f"📄 `{info['filename']}` → 태그: {', '.join(tags)}")

    grouped = group_by_tags(file_infos)

    # ✅ 미리보기
    st.subheader("🧾 그룹화 결과 미리보기")
    temp_dir = tempfile.mkdtemp()
    saved_files = []

    for topic, group_data in grouped.items():
        folder = os.path.join(temp_dir, topic.replace(" ", "_"))
        os.makedirs(folder, exist_ok=True)

        st.markdown(f"### 📁 {topic}")
        st.markdown(f"📌 태그: {', '.join(group_data['keywords'])}")
        st.markdown(f"📄 파일 수: {len(group_data['files'])}")

        readme_path = os.path.join(folder, "README.md")
        with open(readme_path, "w", encoding="utf-8") as readme:
            readme.write(f"# {topic}\n\n")
            readme.write(f"**📌 태그:** {', '.join(group_data['keywords'])}\n\n")
            readme.write("## 📄 포함된 파일\n")
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

    # ✅ ZIP 생성
    zip_path = os.path.join(temp_dir, "grouped_markdowns_by_tags.zip")
    with zipfile.ZipFile(zip_path, "w") as zipf:
        for path in saved_files:
            arcname = os.path.relpath(path, temp_dir)
            zipf.write(path, arcname)

    with open(zip_path, "rb") as fp:
        st.download_button("📥 ZIP 다운로드", fp, file_name="tag_grouped_markdowns.zip", mime="application/zip")

    shutil.rmtree(temp_dir)
    st.caption("※ ZIP 다운로드 후 임시 폴더는 자동 삭제됩니다.")
