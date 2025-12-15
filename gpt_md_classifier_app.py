# Streamlit Markdown Classifier App (Auto-Start)
import streamlit as st
import openai
import os
import tempfile
import shutil
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed

# OpenAI API Key
openai.api_key = st.secrets.get("OPENAI_API_KEY")

# UI Settings
st.set_page_config(page_title="📁 Markdown 자동 병합 분류기", page_icon="📚", layout="wide")
st.title("📁 ChatGPT 기반 Markdown 자동 분류 + 주제 병합")
st.markdown("""
업로드한 Markdown 파일들을 GPT가 자동 분석하여 **시너지 있는 주제 그룹**으로 묶어줍니다.  
파일은 10개씩 묶어서 처리되며, 모든 결과는 ZIP으로 다운로드할 수 있습니다.
""")

uploaded_files = st.file_uploader("⬆️ Markdown (.md) 파일 업로드 (최대 100개)", type="md", accept_multiple_files=True)

# ✅ Refresh Button Only
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

# Refresh Logic
if "refresh" in st.experimental_get_query_params():
    st.experimental_rerun()

# GPT Topic Extraction
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
        res = openai.ChatCompletion.create(
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
        st.warning(f"⚠️ {filename} 분석 중 오류: {e}")
        return "Unknown", ""

# GPT Grouping
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
        res = openai.ChatCompletion.create(
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

# 🔄 Auto-run logic
if uploaded_files:
    st.subheader("📊 파일 분석 및 병합 중...")

    file_infos, seen_files = [], set()
    future_to_file = {}

    with ThreadPoolExecutor(max_workers=5) as executor:
        progress = st.progress(0.0)
        status_text = st.empty()

        for uploaded_file in uploaded_files:
            filename = uploaded_file.name
            if filename in seen_files:
                continue
            seen_files.add(filename)
            content = uploaded_file.read().decode("utf-8")
            future = executor.submit(get_topic_and_summary, filename, content)
            future_to_file[future] = {"filename": filename, "content": content}

        for i, future in enumerate(as_completed(future_to_file)):
            result = future.result()
            info = future_to_file[future]
            info["topic"], info["summary"] = result
            file_infos.append(info)
            percent = (i + 1) / len(future_to_file)
            progress.progress(percent)
            status_text.markdown(f"📄 분석 중: {i+1}/{len(future_to_file)}개 완료 ({int(percent*100)}%)")

    grouped = get_grouped_topics(file_infos)

    # 📂 분류 및 저장
    st.subheader("🧾 분류 결과 미리보기")
    temp_dir = tempfile.mkdtemp()
    saved_files = []

    for topic, group_data in grouped.items():
        filenames = group_data["files"]
        keywords = group_data.get("keywords", [])
        st.markdown(f"### 📁 {topic}")
        st.markdown(f"- 🔑 키워드: {', '.join(keywords)}")
        st.markdown(f"- 📄 파일 수: {len(filenames)}")

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
            match = next((item for item in file_infos if item['filename'] == f), None)
            if match:
                full_path = os.path.join(folder, f)
                with open(full_path, "w", encoding="utf-8") as md_file:
                    md_file.write(match["content"])
                saved_files.append(full_path)

    # 📦 ZIP 생성 및 다운로드
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
