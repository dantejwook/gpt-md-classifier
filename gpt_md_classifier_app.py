# 📁 Streamlit App: Auto Markdown Classification (Auto-start version)
import streamlit as st
import openai
import os
import tempfile
import shutil
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed

# 🔑 Set OpenAI API Key
openai.api_key = st.secrets.get("OPENAI_API_KEY")

# 📄 Page Setup
st.set_page_config(page_title="📁 Markdown 자동 병합 분류기", page_icon="📚", layout="wide")
st.title("📁 ChatGPT 기반 Markdown 자동 분류 + 주제 병합")
st.markdown("""
업로드한 Markdown 파일들을 GPT가 자동 분석하여 **시너지 있는 주제 그룹**으로 묶어줍니다.  
파일은 10개씩 묶어서 처리되며, 모든 결과는 ZIP으로 다운로드할 수 있습니다.
""")

# ⬆️ File Uploader
uploaded_files = st.file_uploader("⬆️ Markdown (.md) 파일 업로드 (최대 100개)", type="md", accept_multiple_files=True)

# 🔄 Refresh Button UI
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

# 🔁 Refresh logic
if "
