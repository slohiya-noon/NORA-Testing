# # Create test.py
# import streamlit as st
# st.title('Hello')
# st.write('Working!')

from gradio_client import Client

client = Client("https://slohiya-nora-kokoro.hf.space")
print(client.view_api())