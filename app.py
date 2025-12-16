import streamlit as st
import os
import pdfplumber
import markdown2
import openai
import tempfile
import zipfile
from sklearn.cluster import KMeans
from typing import List, Dict, Tuple

# ===============================
# OpenAI API Key
# ===============================
openai.api_key = (
    st.secrets["OPENAI_API_KEY"]
    if "OPENAI_API_KEY" in st.secrets
    else os.getenv("OPENAI_API_KEY")
)

# ===============================
# 1. 텍스트 추출 (임베딩용)
# ===============================
def extract_text_for_embedding(file) -> str:
    name = file.name.lower()

    if name.endswith(".pdf"):
        with pdfplumber.open(file) as pdf:
            return "\n".join([page.extract_text() or "" for page in pdf.pages])

    elif name.endswith(".md"):
        return file.read().decode("utf-8")

    elif name.endswith(".txt"):
        return file.read().decode("utf-8")

    return ""

# ===============================
# 2. 임베딩 생성
# ===============================
def get_embedding(text: str) -> List[float]:
    response = openai.embeddings.create(
        model="text-embedding-3-small",
        input=text[:8000]
    )
    return response.data[0].embedding

# ===============================
# 3. 클러스터링
# ===============================
def cluster_embeddings(embeddings: List[List[float]], n_clusters: int):
    model = KMeans(n_clusters=n_clusters, random_state=42)
    return model.fit_predict(embeddings)

# ===============================
# 4. 클러스터 요약 (Markdown)
# ===============================
def summarize_cluster_md(texts: List[str], filenames: List[str]) -> str:
    joined = "\n\n".join(texts)[:4000]

    prompt = f"""
아래 문서 묶음을 분석해서 Markdown 형식으로 정리해 주세요.

포함 문서:
{chr(10).join('- ' + f for f in filenames)}

요구 형식:

## 📌 공통 주제
- 한 문장

## 📝 요약
- 3~5줄 요약

## 🏷 주요 키워드
- 키워드 나열 (bullet)

문서 내용:
{joined}
"""

    response = openai.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[{"role": "user", "content": prompt}]
    )
    return response.choices[0].message.content.strip()

# ===============================
# 5. ZIP 생성 (포맷 유지)
# ===============================
def create_cluster_zip(
    clustered_docs: Dict[int, List[Tuple[str, bytes, str]]]
) -> bytes:
    with tempfile.TemporaryDirectory() as temp_dir:
        zip_path = os.path.join(temp_dir, "clustered_documents.zip")

        for cluster_id, docs in clustered_docs.items():
            cluster_dir = os.path.join(temp_dir, f"cluster_{cluster_id}")
            os.makedirs(cluster_dir, exist_ok=True)

            texts_for_summary = []
            filenames = []

            for filename, raw_bytes, extracted_text in docs:
                filenames.append(filename)
                texts_for_summary.append(extracted_text)

                file_path = os.path.join(cluster_dir, filename)
                with open(file_path, "wb") as f:
                    f.write(raw_bytes)

            # README.md 생성
            summary_md = summarize_cluster_md(texts_for_summary, filenames)
            with open(
                os.path.join(cluster_dir, "README.md"),
                "w",
                encoding="utf-8"
            ) as f:
                f.write(summary_md)

        # ZIP 압축
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
            for root, _, files in os.walk(temp_dir):
                for file in files:
                    if file.endswith(".zip"):
                        continue
                    full_path = os.path.join(root, file)
                    arcname = os.path.relpath(full_path, temp_dir)
                    zipf.write(full_path, arcname)

        with open(zip_path, "rb") as f:
            return f.read()

# ===============================
# 6. Streamlit UI
# ===============================
st.set_page_config("문서 자동 분류기", layout="wide")
st.title("📂 Embedding 기반 문서 분류 + Markdown 정리")

uploaded_files = st.file_uploader(
    "문서 업로드 (.pdf, .md, .txt)",
    type=["pdf", "md", "txt"],
    accept_multiple_files=True
)

if uploaded_files:
    with st.spinner("임베딩 생성 중..."):
        extracted_texts = []
        embeddings = []
        raw_files = []

        for file in uploaded_files:
            raw_bytes = file.read()
            text = extract_text_for_embedding(file)

            if text.strip():
                extracted_texts.append(text)
                embeddings.append(get_embedding(text))
                raw_files.append((file.name, raw_bytes, text))

    n_clusters = st.slider(
        "클러스터 개수",
        2,
        min(10, len(embeddings)),
        3
    )

    labels = cluster_embeddings(embeddings, n_clusters)

    clustered_docs = {}
    for label, file_data in zip(labels, raw_files):
        clustered_docs.setdefault(label, []).append(file_data)

    st.success("✅ 문서 분류 완료")

    for cid, docs in clustered_docs.items():
        with st.expander(f"📁 Cluster {cid}"):
            for name, _, _ in docs:
                st.markdown(f"- {name}")

    zip_bytes = create_cluster_zip(clustered_docs)

    st.download_button(
        "📦 클러스터 결과 ZIP 다운로드",
        data=zip_bytes,
        file_name="clustered_documents.zip",
        mime="application/zip"
    )
