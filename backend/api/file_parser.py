"""
api/file_parser.py - Handles incoming file uploads (PDF, DOCX, Image) and extracts plain text.
Requires pdfplumber, python-docx, Pillow, and google-generativeai for images.
"""
import io
import pdfplumber
import docx
from PIL import Image
import google.generativeai as genai
from fastapi import UploadFile

from config import settings

genai.configure(api_key=settings.gemini_api_key)

class FileParser:
    @staticmethod
    async def parse_file(file: UploadFile) -> str:
        """
        Extract text from PDF, DOCX, TXT, or Image.
        """
        content = await file.read()
        filename = file.filename.lower()
        
        if filename.endswith(".pdf"):
            text = ""
            # pdfplumber takes a bytes stream
            with pdfplumber.open(io.BytesIO(content)) as pdf:
                for page in pdf.pages:
                    extracted = page.extract_text()
                    if extracted:
                        text += extracted + "\n"
            return text
            
        elif filename.endswith(".docx"):
            doc = docx.Document(io.BytesIO(content))
            return "\n".join([paragraph.text for paragraph in doc.paragraphs])
            
        elif filename.endswith((".png", ".jpg", ".jpeg")):
            # Use Gemini Vision for OCR/Analysis
            image = Image.open(io.BytesIO(content))
            # gemini-1.5-flash natively supports multimodal
            model = genai.GenerativeModel(settings.gemini_model)
            prompt = "Extract all text and clinical information from this image verbatim. Output only the plain text. Preserve structure."
            response = await model.generate_content_async([prompt, image])
            return response.text
            
        else:
            # Assume plain text
            try:
                return content.decode("utf-8")
            except UnicodeDecodeError:
                return content.decode("latin-1", errors="ignore")
