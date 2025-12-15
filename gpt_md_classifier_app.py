import streamlit as st
from openai import OpenAI
import os
import tempfile
import shutil
import zipfile

# 🔑 OpenAI client 생성
client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"] if "OPENAI_API_KEY" in st.secrets else None)

# UI 기본 설정
st.set_page_config(page_title="📁 Markdown 주제 분류기", page_icon="📚", layout="wide")

# 사이드바
st.sidebar.title("📌 설정 및 정보")
st.sidebar.info("업로드한 Markdown 파일을 ChatGPT로 분석해 주제별로 자동 분류합니다.")
st.sidebar.markdown("[📦 GitHub 저장소 보기](https://github.com/dantejwook/gpt-md-classifier)")

# 메인 헤더
st.title("📁 ChatGPT 기반 Markdown 주제 분류기")
st.markdown("""
AI가 자동으로 마크다운 문서를 분석하고 **주제별로 정리된 폴더**로 나눠줍니다.  
최대 수백 개의 파일도 한 번에 정리할 수 있어요.
""")

# 파일 업로드
uploaded_files = st.file_uploader(
    "⬆️ Markdown (.md) 파일 업로드 (복수 선택 가능)",
    type="md",
    accept_multiple_files=True,
    help="ChatGPT가 자동으로 내용을 분석해 관련 주제로 분류합니다."
)

# API 키 없을 때 경고
if not client.api_key:
    st.error("❗ OpenAI API 키가 설정되지 않았습니다. Streamlit Secrets에 `OPENAI_API_KEY`를 설정해주세요.")
    st.stop()

# GPT 주제 추출 함수 (gpt-5-nano용)
def get_topic_from_gpt(filename, content):
    prompt = f"""
다음 문서의 핵심 주제를
한 단어 또는 두 단어로만 답하세요.

문서 제목: {filename}
내용:
{content[:800]}
"""
    try:
        res = client.chat.completions.create(
            model="gpt-5-nano",
            messages=[
                {"role": "user", "content": prompt}
            ]
        )
        topic = res.choices[0].message.content.strip()
        return topic.replace(" ", "_")
    except Exception as e:
        st.error(f"GPT 처리 중 오류 발생: {e}")
        return "Unknown"

# 메인 처리 로직
if uploaded_files:
    st.subheader("📊 분석 결과")
    with st.spinner("🔍 GPT가 주제를 분석 중입니다. 잠시만 기다려주세요..."):
        temp_dir = tempfile.mkdtemp()
        grouped = {}

        for uploaded_file in uploaded_files:
            content = uploaded_file.read().decode("utf-8")
            filename = uploaded_file.name

            topic = get_topic_from_gpt(filename, content)
            topic_folder = os.path.join(temp_dir, topic)
            os.makedirs(topic_folder, exist_ok=True)

            with open(os.path.join(topic_folder, filename), "w", encoding="utf-8") as f:
                f.write(content)

            grouped.setdefault(topic, []).append(filename)

        st.success("✅ 파일 분류가 완료되었습니다!")

        for topic, files in grouped.items():
            with st.expander(f"📂 {topic} ({len(files)}개 파일)", expanded=False):
                st.markdown("\n".join([f"- `{file}`" for file in files]))

        # ZIP으로 묶기
        zip_path = os.path.join(temp_dir, "grouped_markdowns.zip")
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
            for root, _, files in os.walk(temp_dir):
                for file in files:
                    if file.endswith(".md"):
                        filepath = os.path.join(root, file)
                        arcname = os.path.relpath(filepath, temp_dir)
                        zipf.write(filepath, arcname)

        with open(zip_path, "rb") as fp:
            st.download_button(
                label="📦 ZIP 파일로 다운로드",
                data=fp,
                file_name="grouped_markdowns.zip",
                mime="application/zip",
                help="주제별로 정리된 마크다운 파일들을 압축해서 받습니다."
            )

        # 정리
        shutil.rmtree(temp_dir)
