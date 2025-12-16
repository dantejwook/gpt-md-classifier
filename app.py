import streamlit as st
import os
import pdfplumber
import markdown2
import openai
import tempfile
import zipfile
from sklearn.cluster import KMeans
import numpy as np
from typing import List

# ===============================
# OpenAI API Key 설정
# ===============================
openai.api_key = (
    st.secrets["OPENAI_API_KEY"]
    if "OPENAI_API_KEY" in st.secrets
    else os.getenv("OPENAI_API_KEY")
)

# ===============================
# 1. 문서 텍스트 추출
# ===============================
def extract_text(file) -> str:
    name = file.name.lower()

    if name.endswith(".pdf"):
        with pdfplumber.open(file) as pdf:
            return "\n".join(
                [page.extract_text() or "" for page in pdf.pages]
            )

    elif name.endswith(".md"):
        return markdown2.markdown(file.read().decode("utf-8"))

    elif name.endswith(".txt"):
        return file.read().decode("utf-8")

    return ""

# ===============================
# 2. 임베딩 생성
# ===============================
def get_embedding(text: str) -> List[float]:
    response = openai.embeddings.create(
        model="text-embedding-3-small",
        input=text[:8000]  # 길이 제한
    )
    return response.data[0].embedding

# ===============================
# 3. 클러스터링
# ===============================
def cluster_embeddings(embeddings: List[List[float]], n_clusters: int):
    kmeans = KMeans(n_clusters=n_clusters, random_state=42)
    return kmeans.fit_predict(embeddings)

# ===============================
# 4. ZIP 파일 생성
# ===============================
def create_zip_from_clusters(clustered_docs: dict) -> bytes:
    with tempfile.TemporaryDirectory() as temp_dir:
        zip_path = os.path.join(temp_dir, "clustered_documents.zip")

        # 클러스터별 폴더 생성
        for cluster_id, docs in clustered_docs.items():
            cluster_dir = os.path.join(temp_dir, f"cluster_{cluster_id}")
            os.makedirs(cluster_dir, exist_ok=True)

            for filename, text in docs:
                base = os.path.splitext(filename)[0]
                path = os.path.join(cluster_dir, f"{base}.txt")
                with open(path, "w", encoding="utf-8") as f:
                    f.write(text)

        # ZIP 압축
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
            for root, _, files in os.walk(temp_dir):
                for file in files:
                    if file.endswith(".zip"):
                        continue
                    full_path = os.path.join(root, file)
                    arcname = os.path.relpath(full_path, temp_dir)
                    zipf.write(full_path, arcname)

        # Streamlit 다운로드용 바이너리 반환
        with open(zip_path, "rb") as f:
            return f.read()

# ===============================
# 5. Streamlit UI
# ===============================
st.set_page_config(page_title="Embedding 문서 분류기", layout="wide")

st.title("📄 Embedding 기반 문서 자동 분류기")
st.markdown("""
- 문서를 업로드하면 **임베딩 기반으로 의미적 분류**
- 결과를 **클러스터별 폴더 구조로 ZIP 다운로드**
""")

uploaded_files = st.file_uploader(
    "문서 업로드 (.txt, .md, .pdf)",
    type=["txt", "md", "pdf"],
    accept_multiple_files=True
)

if uploaded_files:
    with st.spinner("문서 분석 및 임베딩 생성 중..."):
        texts = []
        names = []

        for file in uploaded_files:
            text = extract_text(file)
            if text.strip():
                texts.append(text)
                names.append(file.name)

        embeddings = [get_embedding(text) for text in texts]

    n_clusters = st.slider(
        "클러스터 개수",
        min_value=2,
        max_value=min(10, len(embeddings)),
        value=3
    )

    labels = cluster_embeddings(embeddings, n_clusters)

    # 클러스터 결과 정리
    clustered_docs = {}
    for label, name, text in zip(labels, names, texts):
        clustered_docs.setdefault(label, []).append((name, text))

    st.success("✅ 문서 분류 완료")

    # 결과 미리보기
    for cluster_id, docs in clustered_docs.items():
        with st.expander(f"📁 Cluster {cluster_id} ({len(docs)}개 문서)"):
            for name, _ in docs:
                st.markdown(f"- {name}")

    # ZIP 다운로드
    zip_bytes = create_zip_from_clusters(clustered_docs)

    st.download_button(
        label="📦 분류 결과 ZIP 다운로드",
        data=zip_bytes,
        file_name="clustered_documents.zip",
        mime="application/zip"
    )
