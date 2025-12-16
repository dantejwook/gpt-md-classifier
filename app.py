import streamlit as st
import os
import pdfplumber
import markdown2
import openai
import tempfile
from sklearn.cluster import KMeans
import numpy as np
from typing import List
from io import StringIO

# Set your OpenAI key
openai.api_key = st.secrets["OPENAI_API_KEY"] if "OPENAI_API_KEY" in st.secrets else os.getenv("OPENAI_API_KEY")

# ----- 1. 문서 텍스트 추출 -----
def extract_text(file) -> str:
    name = file.name.lower()
    if name.endswith(".pdf"):
        with pdfplumber.open(file) as pdf:
            return "\n".join([page.extract_text() or "" for page in pdf.pages])
    elif name.endswith(".md"):
        return markdown2.markdown(file.read().decode("utf-8"))
    elif name.endswith(".txt"):
        return file.read().decode("utf-8")
    else:
        return ""

# ----- 2. 임베딩 생성 -----
def get_embedding(text: str) -> List[float]:
    response = openai.embeddings.create(
        model="text-embedding-3-small",
        input=text[:8000]  # truncate if too long
    )
    return response.data[0].embedding

# ----- 3. 클러스터링 -----
def cluster_embeddings(embeddings: List[List[float]], n_clusters: int):
    kmeans = KMeans(n_clusters=n_clusters, random_state=42)
    labels = kmeans.fit_predict(embeddings)
    return labels

# ----- 4. 클러스터 요약 (GPT 사용 optional) -----
def summarize_cluster(docs: List[str]):
    joined = "\n\n".join(docs)
    prompt = f"다음 문서들의 공통 주제를 간결하게 요약해 주세요:\n\n{joined[:4000]}"
    response = openai.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[{"role": "user", "content": prompt}]
    )
    return response.choices[0].message.content.strip()

# ----- 5. Streamlit UI -----
st.title("📄 Embedding 기반 문서 분류기")
st.markdown("문서를 업로드하면 임베딩을 기반으로 의미적으로 유사한 문서끼리 자동 분류합니다.")

uploaded_files = st.file_uploader("문서 파일 업로드 (.txt, .md, .pdf)", type=["txt", "md", "pdf"], accept_multiple_files=True)

if uploaded_files:
    with st.spinner("문서 처리 중..."):
        docs_text = []
        file_names = []
        for file in uploaded_files:
            text = extract_text(file)
            if text:
                docs_text.append(text)
                file_names.append(file.name)

        embeddings = [get_embedding(text) for text in docs_text]

        n_clusters = st.slider("분류 개수(KMeans 클러스터 수)", 2, min(10, len(embeddings)), 3)

        labels = cluster_embeddings(embeddings, n_clusters)

        # 클러스터별 문서 정리
        clustered_docs = {}
        for label, name, text in zip(labels, file_names, docs_text):
            clustered_docs.setdefault(label, []).append((name, text))

    st.success("분류 완료! 📁")

    for cluster_id, docs in clustered_docs.items():
        with st.expander(f"📂 클러스터 {cluster_id} — 문서 {len(docs)}개"):
            st.markdown("**포함 문서:**")
            for name, _ in docs:
                st.markdown(f"- {name}")

            if st.checkbox(f"클러스터 {cluster_id} 요약 보기", key=f"sum_{cluster_id}"):
                with st.spinner("GPT로 클러스터 주제 분석 중..."):
                    cluster_texts = [text for _, text in docs]
                    summary = summarize_cluster(cluster_texts)
                    st.markdown(f"**공통 주제 요약:** {summary}")
