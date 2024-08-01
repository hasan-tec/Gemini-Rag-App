import streamlit as st
import requests
from bs4 import BeautifulSoup
import json
import numpy as np
from sklearn.metrics.pairwise import cosine_similarity
import time
import hashlib
import os

# Caching
@st.cache_resource
def cache_embedding(embedding):
    cache_path = "cache"
    if not os.path.exists(cache_path):
        os.makedirs(cache_path)
    hash_key = hashlib.sha256(str(embedding).encode()).hexdigest()
    cache_file = os.path.join(cache_path, f"{hash_key}.npy")
    np.save(cache_file, embedding)
    return cache_file

@st.cache_resource
def load_cached_embedding(cache_file):
    return np.load(cache_file)

# Utility functions
def fetch_and_clean_content(url):
    response = requests.get(url)
    soup = BeautifulSoup(response.content, 'html.parser')
    text = soup.get_text(separator=' ', strip=True)
    return text

def chunk_text(text, chunk_size=1000, overlap=100):
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunk = text[start:end]
        chunks.append(chunk)
        start = end - overlap
    return chunks

def get_embedding(api_key, text, model="embedding-001"):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:embedContent"
    headers = {"Content-Type": "application/json"}
    data = {
        "model": model,
        "content": {"parts": [{"text": text}]}
    }
    response = requests.post(url, headers=headers, params={"key": api_key}, json=data)
    result = response.json()
    if 'embedding' in result:
        embedding = result['embedding']['values']
        cache_file = cache_embedding(embedding)
        return load_cached_embedding(cache_file)
    else:
        st.error(f"Error in embedding API response: {json.dumps(result, indent=2)}")
        return None

def query_gemini(api_key, question, context):
    url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash-latest:generateContent"
    headers = {"Content-Type": "application/json"}
    data = {
        "contents": [
            {"parts": [{"text": f"Context: {context}\n\nQuestion: {question}"}]}
        ]
    }
    response = requests.post(url, headers=headers, params={"key": api_key}, json=data)
    return response.json()

def get_hybrid_context(chunks, query, api_key):
    keyword_contexts = []
    for chunk in chunks:
        if query.lower() in chunk.lower():
            keyword_contexts.append(chunk)
    keyword_context = " ".join(keyword_contexts[:3])  # Limit to top 3 keyword matches

    query_embedding = get_embedding(api_key, query)
    similarities = cosine_similarity([query_embedding], st.session_state.embeddings)[0]
    most_similar_idxs = np.argsort(similarities)[-3:]  # Get top 3 similar chunks
    semantic_context = " ".join([chunks[idx] for idx in most_similar_idxs])
    
    hybrid_context = keyword_context + " " + semantic_context
    return hybrid_context

# Streamlit app
st.set_page_config(layout="wide", page_title="Enhanced Gemini RAG App")

st.title("Enhanced Gemini RAG App")

# Sidebar
with st.sidebar:
    api_key = st.text_input("Enter your Gemini API Key:", type="password")
    url = st.text_input("Enter the URL to scrape:")
    chunk_size = st.number_input("Chunk size:", min_value=500, max_value=2000, value=1000, step=100)
    overlap = st.number_input("Overlap:", min_value=0, max_value=500, value=100, step=50)
    embedding_model = st.selectbox("Select Embedding Model:", ["embedding-001", "embedding-002"])

    if st.button("Scrape and Process"):
        if not api_key or not url:
            st.warning("Please enter both API key and URL.")
        else:
            with st.spinner("Scraping and processing content..."):
                start_time = time.time()
                content = fetch_and_clean_content(url)
                chunks = chunk_text(content, chunk_size, overlap)
                st.session_state.embeddings = []
                st.session_state.chunks = chunks
                for chunk in chunks:
                    embedding = get_embedding(api_key, chunk, embedding_model)
                    if embedding is not None:  # Corrected line
                        st.session_state.embeddings.append(embedding)
                processing_time = time.time() - start_time
                st.success(f"Processed {len(st.session_state.embeddings)} chunks in {processing_time:.2f} seconds.")

# Main content
st.markdown("<h1 style='text-align: center;'>Chat with Gemini</h1>", unsafe_allow_html=True)

# Initialize chat history
if 'chat_history' not in st.session_state:
    st.session_state.chat_history = []

# Display chat history
for message in st.session_state.chat_history:
    st.write(message)

question = st.text_input("Ask a question:")
if st.button("Get Answer"):
    if not api_key or not question:
        st.warning("Please enter both API key and question.")
    else:
        with st.spinner("Generating answer..."):
            # Check if the question is related to the parsed data
            if 'embeddings' in st.session_state:
                hybrid_context = get_hybrid_context(st.session_state.chunks, question, api_key)
                response = query_gemini(api_key, question, hybrid_context)
            else:
                # Use chat history as context
                chat_context = "\n".join(st.session_state.chat_history)
                response = query_gemini(api_key, question, chat_context)

            if 'candidates' in response and response['candidates']:
                try:
                    candidate = response['candidates'][0]
                    if candidate.get('finishReason') == 'SAFETY':
                        st.warning("The response was flagged for safety reasons and could not be processed.")
                    else:
                        answer = candidate['content']['parts'][0]['text']
                        st.success("Answer generated successfully!")
                        st.write(answer)
                        # Add question and answer to chat history
                        st.session_state.chat_history.append(f"**User:** {question}")
                        st.session_state.chat_history.append(f"**Assistant:** {answer}")
                except KeyError as e:
                    st.error(f"Error in accessing response content: {e}")
            else:
                st.error(f"Error in API response: {json.dumps(response, indent=2)}")

# User feedback
feedback = st.text_area("Provide feedback on the answer:", "")
if st.button("Submit Feedback"):
    st.write("Thank you for your feedback!")

# Styling
st.markdown(
    """
    <style>
    .stApp {
        max-width: 100%;
        margin: 0 auto;
    }
    </style>
    """,
    unsafe_allow_html=True
)
