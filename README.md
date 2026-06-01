# YouTube Transcript & Screenshot OCR Chatbot (Transkriptör Chat)

A powerful, premium Flask-based desktop and web application designed to automatically parse, search, extract transcripts from YouTube, perform intelligent multi-column OCR from screenshots, and manage video metadata with a modern, glassmorphic chatbot user interface.

## 🚀 Features

- **📺 YouTube Transcript Extractor**: Instantly fetches YouTube video transcripts using `youtube-transcript-api` (supporting version `1.2.4+` object-based structures).
- **📸 Smart Screenshot OCR**: Integrates with OCR.space Engine 2 to extract text from multi-column video lists or screenshots.
  - **Multi-Video Column Parsing**: Automatically isolates side-by-side columns of video search pages by splitting text fields.
  - **Boundary Title Isolation**: Discards thumbnail timeline stamps and channel info by dynamically matching title coordinates preceding metadata lines.
- **⚡ Synchronous Clipboard Copying**: Bypasses modern browser (Brave, Chrome) security constraints using pre-fetched caching to allow instant, secure copying with one click.
- **💬 Glassmorphic Interactive Chat**: Sleek, modern conversational user interface built with HTML5, CSS3, and modern typography.
- **🛠️ Self-contained Portable Backend**: Run locally on Python 3.11 with minimal setup.

## 🛠️ Tech Stack

- **Backend**: Python, Flask, `youtube-transcript-api`, `requests`, `yt-dlp`
- **Frontend**: Vanilla HTML5, CSS3 (Custom Glassmorphism Design System), Javascript (ES6+)
- **External API**: OCR.space API for advanced optical character recognition.

## ⚙️ Installation & Setup

1. **Clone the repository**:
   ```bash
   git clone <your-repository-url>
   cd transkriptor-chat-app
   ```

2. **Install dependencies**:
   ```bash
   pip install flask youtube-transcript-api requests yt-dlp
   ```

3. **Get your OCR.space API Key**:
   - Register at [ocr.space](https://ocr.space/ocrapi) to get a free API key.
   - Enter it in the app settings interface or replace the placeholder in `app.py`.

4. **Run the application**:
   ```bash
   python app.py
   ```
   - Open your browser and navigate to `http://127.0.0.1:5000`

## 📁 File Structure

- `app.py`: Main Flask application handling routing, YouTube API interaction, OCR post-processing, and server-side transcript caching.
- `README.md`: English documentation.
- `README_TR.md`: Turkish documentation.

---

*Designed and developed with 💙 by Emirhan Kaya.*
