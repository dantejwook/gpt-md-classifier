# 📁 Streamlit App: Markdown Auto Classifier (chunked, OpenAI v1+)
import streamlit as st
from openai import OpenAI
import os
import tempfile
import shutil
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from uuid import uuid4
from math import ceil

# ✅ Initialize OpenAI client (SDK v1+)
client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])

# ✅ Page Setup
st.set_page_config(page_title="📁 Markdown 자동 병합 분류기", page_icon="📚", layout="wide")
st.title("📁 ChatGPT 기반 Markdown 자동 분류 + 주제 병합")
st.markdown("""
업로드한 Markdown 파일들을 GPT가 자동 분석하여 **시너지 있는 주제 그룹**으로 묶어줍니다.  
많은 파일(예: 80개 이상)은 자동으로 여러 번에 나눠서 처리됩니다.
""")

# ✅ Upload Area
uploaded_files = st.file_uploader("⬆️ Markdown (.md) 파일 업로드", type="md", accept_multiple_files=True)

# ✅ Refresh Button
st.markdown("""
<style>
.button-container {
    display: flex;
    gap: 10px;
    margin-bottom: 20px;
}
.button-container .refresh-button button {
    background-color: #4CAF50;
    color: white;
    font-weight: bold;
    width: 100%;
}
</style>
<div class="button-container">
  <div class="refresh-button">
    <form action="?refresh=1">
      <button type="submit">🔄 전체 새로고침</button>
    </form>
  </div>
</div>
""", unsafe_allow_html=True)

if "refresh" in st.experimental_get_query_params():
    st.experimental_rerun()

# ✅ GPT: Topic + Summary
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

# ✅ GPT: Grouping by chunk (≤30 files per batch)
def get_grouped_topics_chunked(file_infos, chunk_size=30):
    total_chunks = ceil(len(file_infos) / chunk_size)
    grouped = {}

    for i in range(total_chunks):
        chunk = file_infos[i * chunk_size:(i + 1) * chunk_size]
        prompt = """
다음은 여러 마크다운 파일의 주제 및 요약입니다. 반드시 **모든 파일을 포함하여**, 관련된 파일끼리 묶어 3~10개의 그룹으로 나눠주세요.
각 그룹에 3~5개의 키워드도 생성해주세요.
출력 형식:
[그룹명]: 파일1.md, 파일2.md
키워드: 키워드1, 키워드2, 키워드3

목록:
"""
        for info in chunk:
            prompt += f"- {info['unique_filename']}: {info['topic']} / {info['summary']}\n"

        try:
            res = client.chat.completions.create(
                model="gpt-3.5-turbo",
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

# ✅ Main Logic
if uploaded_files:
    st.subheader("📊 파일 분석 및 병합 중...")
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
                "content": content,
            }

        for i, future in enumerate(as_completed(future_to_file)):
            result = future.result()
            info = future_to_file[future]
            info["topic"], info["summary"] = result
            file_infos.append(info)
            file_id_map[info["unique_filename"]] = info
            percent = (i + 1) / len(future_to_file)
            progress.progress(percent)
            status_text.markdown(f"📄 분석 중: {i+1}/{len(future_to_file)}개 완료 ({int(percent * 100)}%)")

    grouped = get_grouped_topics_chunked(file_infos)

    st.subheader("🧾 분류 결과 미리보기")
    temp_dir = tempfile.mkdtemp()
    saved_files = []

    for group_name, data in grouped.items():
        filenames = data["files"]
        keywords = data.get("keywords", [])
        st.markdown(f"### 📁 {group_name}")
        st.markdown(f"- 🔑 키워드: {', '.join(keywords)}")
        st.markdown(f"- 📄 파일 수: {len(filenames)}")

        folder = os.path.join(temp_dir, group_name.replace(" ", "_").replace("/", "_"))
        os.makedirs(folder, exist_ok=True)

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
                with open(output_path, "w", encoding="utf-8") as md_file:
                    md_file.write(match["content"])
                saved_files.append(output_path)

    if saved_files:
        zip_path = os.path.join(temp_dir, "merged_markdowns.zip")
        with zipfile.ZipFile(zip_path, "w") as zipf:
            for filepath in saved_files:
                arcname = os.path.relpath(filepath, temp_dir)
                zipf.write(filepath, arcname)

        with open(zip_path, "rb") as fp:
            st.download_button("📦 병합 ZIP 다운로드", fp, file_name="merged_markdowns.zip", mime="application/zip")

        shutil.rmtree(temp_dir)
        st.caption("※ ZIP 파일 다운로드 이후 임시 폴더는 자동 삭제됩니다.")
    else:
        st.error("⚠️ 병합된 파일이 저장되지 않았습니다.")
