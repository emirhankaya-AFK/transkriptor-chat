import re
import os
import base64
import requests
import time
import http.cookiejar
from flask import Flask, request, jsonify, render_template_string
from youtube_transcript_api import YouTubeTranscriptApi
import yt_dlp

# Monkey patch requests Session.request to force a default timeout of 2.5 seconds.
# This prevents third-party libraries like youtube_transcript_api from hanging on dead/slow proxies.
orig_request = requests.Session.request
def timed_request(self, method, url, *args, **kwargs):
    if 'timeout' not in kwargs or kwargs['timeout'] is None:
        kwargs['timeout'] = 2.5
    return orig_request(self, method, url, *args, **kwargs)
requests.Session.request = timed_request

app = Flask(__name__)
WORKING_PROXY = None

def load_youtube_cookies_session():
    session = requests.Session()
    # Search for cookies.txt in common directories
    candidate_paths = [
        'cookies.txt',
        'transkriptor-chat-app/cookies.txt',
        os.path.join(os.path.dirname(__file__), 'cookies.txt') if '__file__' in globals() else 'cookies.txt',
        os.path.join(os.path.dirname(__file__), 'transkriptor-chat-app', 'cookies.txt') if '__file__' in globals() else 'transkriptor-chat-app/cookies.txt'
    ]
    cookie_file = None
    for p in candidate_paths:
        if os.path.exists(p):
            cookie_file = p
            break
            
    if cookie_file:
        try:
            cj = http.cookiejar.MozillaCookieJar(cookie_file)
            cj.load(ignore_discard=True, ignore_expires=True)
            session.cookies = cj
            print(f"Successfully loaded YouTube cookies from {cookie_file}")
        except Exception as e:
            print(f"Failed to load cookies from {cookie_file}: {e}")
    else:
        print("No cookies.txt found. Proceeding without cookies.")
    return session, cookie_file

# IP-based rate limiting configuration
IP_LIMITS = {}
IS_LOCAL = os.environ.get('PORT') is None and os.environ.get('RENDER') is None
MAX_REQUESTS = 999999 if IS_LOCAL else 5
BAN_DURATION = 300  # 5 minutes in seconds
WINDOW_DURATION = 300  # 5 minutes in seconds


def get_client_ip():
    return request.headers.get('X-Forwarded-For', request.remote_addr).split(',')[0].strip()

def check_rate_limit(ip):
    now = time.time()
    if ip not in IP_LIMITS:
        IP_LIMITS[ip] = {
            'count': 0,
            'banned_until': 0,
            'first_request': now
        }
    
    info = IP_LIMITS[ip]
    
    # Check if user is currently banned
    if info['banned_until'] > now:
        return False, int(info['banned_until'] - now)
    
    # Reset window if duration exceeded
    if now - info['first_request'] > WINDOW_DURATION:
        info['count'] = 0
        info['first_request'] = now
        
    return True, 0

def increment_rate_limit(ip):
    info = IP_LIMITS[ip]
    info['count'] += 1
    if info['count'] > MAX_REQUESTS:
        info['banned_until'] = time.time() + BAN_DURATION
        return False, BAN_DURATION
    return True, 0


# Premium glassmorphic Chat UI
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="tr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Transkriptör Chat - Çoklu Video Altyazı Asistanı</title>
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700;800&display=swap" rel="stylesheet">
    {% if logo_base64 %}
    <link rel="icon" type="image/png" href="data:image/png;base64,{{ logo_base64 }}">
    {% endif %}
    <style>
        :root {
            --bg-color: #0b0f19;
            --card-bg: rgba(17, 25, 40, 0.6);
            --border-color: rgba(255, 255, 255, 0.08);
            --primary: #6366f1;
            --primary-hover: #4f46e5;
            --accent: #10b981;
            --text-main: #f3f4f6;
            --text-muted: #9ca3af;
            --user-msg-bg: rgba(99, 102, 241, 0.15);
            --bot-msg-bg: rgba(255, 255, 255, 0.03);
        }

        * {
            box-sizing: border-box;
            margin: 0;
            padding: 0;
            font-family: 'Outfit', sans-serif;
            scroll-behavior: smooth;
        }

        body {
            background-color: var(--bg-color);
            color: var(--text-main);
            height: 100vh;
            display: flex;
            flex-direction: column;
            overflow: hidden;
            background-image: 
                radial-gradient(at 0% 0%, rgba(99, 102, 241, 0.12) 0px, transparent 50%),
                radial-gradient(at 100% 100%, rgba(16, 185, 129, 0.08) 0px, transparent 50%);
            position: relative;
        }

        ::-webkit-scrollbar {
            width: 8px;
        }
        ::-webkit-scrollbar-track {
            background: rgba(0, 0, 0, 0.1);
        }
        ::-webkit-scrollbar-thumb {
            background: rgba(255, 255, 255, 0.08);
            border-radius: 4px;
        }
        ::-webkit-scrollbar-thumb:hover {
            background: rgba(255, 255, 255, 0.15);
        }

        .app-container {
            display: flex;
            flex: 1;
            height: calc(100vh - 70px);
            overflow: hidden;
            position: relative;
        }

        header {
            height: 70px;
            border-bottom: 1px solid var(--border-color);
            background: rgba(11, 15, 25, 0.8);
            backdrop-filter: blur(12px);
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 0 2rem;
            z-index: 100;
        }

        .logo {
            font-size: 1.5rem;
            font-weight: 800;
            background: linear-gradient(135deg, #6366f1, #10b981);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            display: flex;
            align-items: center;
            gap: 0.5rem;
        }

        .badge {
            background: rgba(16, 185, 129, 0.15);
            border: 1px solid rgba(16, 185, 129, 0.3);
            color: #34d399;
            padding: 0.2rem 0.6rem;
            border-radius: 9999px;
            font-size: 0.7rem;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.05em;
        }

        .btn-settings {
            background: rgba(255, 255, 255, 0.05);
            border: 1px solid rgba(255, 255, 255, 0.1);
            color: white;
            width: 40px;
            height: 40px;
            border-radius: 50%;
            cursor: pointer;
            display: flex;
            align-items: center;
            justify-content: center;
            transition: all 0.2s ease;
        }

        .btn-settings:hover {
            background: rgba(255, 255, 255, 0.15);
            transform: rotate(45deg);
        }

        .chat-container {
            flex: 1;
            display: flex;
            flex-direction: column;
            background: rgba(0, 0, 0, 0.1);
            position: relative;
        }

        .messages-list {
            flex: 1;
            overflow-y: auto;
            padding: 2rem;
            display: flex;
            flex-direction: column;
            gap: 1.5rem;
        }

        .message {
            display: flex;
            flex-direction: column;
            max-width: 85%;
            border-radius: 20px;
            padding: 1.25rem 1.5rem;
            line-height: 1.6;
            animation: fadeIn 0.3s ease;
        }

        .message.user {
            align-self: flex-end;
            background: var(--user-msg-bg);
            border: 1px solid rgba(99, 102, 241, 0.25);
            border-bottom-right-radius: 4px;
        }

        .message.bot {
            align-self: flex-start;
            background: var(--bot-msg-bg);
            border: 1px solid var(--border-color);
            border-bottom-left-radius: 4px;
            width: 100%;
            max-width: 90%;
        }

        .message-meta {
            font-size: 0.75rem;
            color: var(--text-muted);
            margin-bottom: 0.5rem;
            font-weight: 600;
            display: flex;
            align-items: center;
            gap: 0.5rem;
        }

        .message-content {
            font-size: 0.95rem;
        }

        .input-panel {
            padding: 1.5rem 2rem;
            background: rgba(11, 15, 25, 0.85);
            border-top: 1px solid var(--border-color);
            backdrop-filter: blur(10px);
            display: flex;
            flex-direction: column;
            gap: 0.75rem;
        }

        .input-wrapper {
            display: flex;
            background: rgba(255, 255, 255, 0.03);
            border: 2px solid rgba(255, 255, 255, 0.08);
            border-radius: 16px;
            padding: 0.5rem;
            align-items: center;
            transition: all 0.2s ease;
            gap: 0.5rem;
        }

        .input-wrapper:focus-within {
            border-color: var(--primary);
            box-shadow: 0 0 0 4px rgba(99, 102, 241, 0.12);
        }

        .rich-input {
            flex: 1;
            background: transparent;
            border: none;
            outline: none;
            color: white;
            font-size: 1rem;
            padding: 0.75rem 0.5rem;
            min-height: 24px;
            max-height: 150px;
            overflow-y: auto;
            white-space: pre-wrap;
            word-break: break-word;
        }

        .rich-input:empty:before {
            content: attr(placeholder);
            color: #6b7280;
            cursor: text;
        }

        .btn-attach {
            background: transparent;
            border: none;
            color: var(--text-muted);
            width: 44px;
            height: 44px;
            border-radius: 12px;
            cursor: pointer;
            display: flex;
            align-items: center;
            justify-content: center;
            transition: all 0.2s ease;
        }

        .btn-attach:hover {
            color: var(--accent);
            background: rgba(255, 255, 255, 0.05);
        }

        .btn-send {
            background: var(--primary);
            color: white;
            border: none;
            width: 48px;
            height: 48px;
            border-radius: 12px;
            cursor: pointer;
            display: flex;
            align-items: center;
            justify-content: center;
            transition: all 0.2s ease;
        }

        .btn-send:hover {
            background: var(--primary-hover);
            transform: scale(1.03);
        }

        .btn-send:active {
            transform: scale(0.97);
        }

        .input-hints {
            display: flex;
            justify-content: space-between;
            align-items: center;
            font-size: 0.8rem;
            color: var(--text-muted);
        }

        .paste-tip {
            display: flex;
            align-items: center;
            gap: 0.5rem;
            color: var(--accent);
            font-weight: 500;
        }

        .videos-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
            gap: 1.25rem;
            margin-top: 1rem;
            width: 100%;
        }

        .video-card {
            background: rgba(0, 0, 0, 0.25);
            border: 1px solid var(--border-color);
            border-radius: 16px;
            overflow: hidden;
            display: flex;
            flex-direction: column;
            transition: all 0.2s ease;
        }

        .video-card:hover {
            border-color: rgba(99, 102, 241, 0.4);
            transform: translateY(-2px);
        }

        .video-thumb-container {
            position: relative;
            width: 100%;
            padding-top: 56.25%;
            background: #000;
        }

        .video-thumb-container img {
            position: absolute;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            object-fit: cover;
        }

        .video-info {
            padding: 1rem;
            display: flex;
            flex-direction: column;
            flex: 1;
            gap: 0.5rem;
        }

        .video-title {
            font-size: 0.95rem;
            font-weight: 600;
            line-height: 1.4;
            color: white;
            display: -webkit-box;
            -webkit-line-clamp: 2;
            -webkit-box-orient: vertical;
            overflow: hidden;
            min-height: 2.7em;
        }

        .video-channel {
            font-size: 0.8rem;
            color: var(--text-muted);
        }

        .video-actions {
            display: flex;
            gap: 0.5rem;
            margin-top: auto;
            padding-top: 0.75rem;
            border-top: 1px solid rgba(255, 255, 255, 0.05);
        }

        .btn-card {
            flex: 1;
            padding: 0.5rem;
            font-size: 0.8rem;
            font-weight: 600;
            border-radius: 8px;
            cursor: pointer;
            border: 1px solid rgba(255, 255, 255, 0.1);
            background: rgba(255,255,255,0.03);
            color: white;
            transition: all 0.15s ease;
            text-align: center;
            text-decoration: none;
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 0.25rem;
        }

        .btn-card.primary {
            background: var(--primary);
            border-color: transparent;
        }

        .btn-card.primary:hover {
            background: var(--primary-hover);
        }

        .btn-card.warning-btn {
            background: rgba(245, 158, 11, 0.2);
            border-color: rgba(245, 158, 11, 0.4);
            color: #fbbf24;
        }

        .btn-card.warning-btn:hover {
            background: rgba(245, 158, 11, 0.3);
            border-color: rgba(245, 158, 11, 0.6);
        }

        .btn-card:hover {
            background: rgba(255,255,255,0.1);
        }

        .sidebar {
            width: 450px;
            border-left: 1px solid var(--border-color);
            background: rgba(17, 25, 40, 0.75);
            backdrop-filter: blur(20px);
            display: flex;
            flex-direction: column;
            transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
            z-index: 50;
            overflow: hidden;
        }

        .sidebar.closed {
            width: 0;
            border-left: none;
        }

        .sidebar-header {
            padding: 1.5rem;
            border-bottom: 1px solid var(--border-color);
            display: flex;
            justify-content: space-between;
            align-items: center;
        }

        .sidebar-header h3 {
            font-size: 1.1rem;
            font-weight: 700;
        }

        .btn-close {
            background: transparent;
            border: none;
            color: var(--text-muted);
            font-size: 1.5rem;
            cursor: pointer;
        }

        .sidebar-content {
            flex: 1;
            overflow-y: auto;
            padding: 1.5rem;
            display: flex;
            flex-direction: column;
            gap: 1.5rem;
        }

        .transcript-lines {
            display: flex;
            flex-direction: column;
            gap: 0.75rem;
        }

        .t-line {
            display: flex;
            gap: 1rem;
            padding: 0.5rem;
            border-radius: 8px;
            transition: background 0.15s ease;
        }

        .t-line:hover {
            background: rgba(255, 255, 255, 0.03);
        }

        .t-time {
            color: var(--accent);
            font-weight: 600;
            font-family: monospace;
            font-size: 0.85rem;
            min-width: 50px;
            cursor: pointer;
        }

        .t-time:hover {
            text-decoration: underline;
        }

        .t-text {
            color: #d1d5db;
            font-size: 0.9rem;
            line-height: 1.5;
        }

        .msg-image-preview {
            max-width: 250px;
            border-radius: 12px;
            margin-top: 0.5rem;
            border: 1px solid rgba(255,255,255,0.1);
        }

        .toast {
            position: fixed;
            bottom: 2rem;
            right: 2rem;
            background: var(--accent);
            color: white;
            padding: 1rem 1.5rem;
            border-radius: 10px;
            font-weight: 600;
            box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.3);
            transform: translateY(200%);
            transition: transform 0.3s cubic-bezier(0.4, 0, 0.2, 1);
            z-index: 10000;
        }

        .toast.show {
            transform: translateY(0);
        }

        .drag-overlay {
            display: none;
            position: absolute;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: rgba(99, 102, 241, 0.15);
            backdrop-filter: blur(8px);
            border: 4px dashed var(--primary);
            border-radius: 8px;
            z-index: 9999;
            justify-content: center;
            align-items: center;
            flex-direction: column;
            pointer-events: none;
        }

        .drag-overlay h2 {
            font-size: 2rem;
            font-weight: 800;
            color: white;
            margin-top: 1rem;
        }

        .chat-loading {
            display: flex;
            align-items: center;
            gap: 0.5rem;
            color: var(--text-muted);
            font-size: 0.9rem;
            font-weight: 500;
            padding: 1rem;
            align-self: flex-start;
            background: var(--bot-msg-bg);
            border: 1px solid var(--border-color);
            border-radius: 15px;
            animation: pulse 1.5s infinite;
        }

        .settings-modal-overlay {
            display: none;
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: rgba(8, 12, 20, 0.6);
            backdrop-filter: blur(10px);
            z-index: 10000;
            justify-content: center;
            align-items: center;
            animation: fadeIn 0.25s ease-in-out;
        }

        .settings-modal-card {
            background: rgba(15, 23, 42, 0.92);
            border: 1px solid rgba(255, 255, 255, 0.08);
            border-radius: 24px;
            padding: 2.25rem;
            width: 90%;
            max-width: 500px;
            box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.5), 0 0 40px rgba(99, 102, 241, 0.15);
            position: relative;
            backdrop-filter: blur(20px);
            animation: scaleIn 0.3s cubic-bezier(0.34, 1.56, 0.64, 1);
        }

        .settings-input {
            width: 100%;
            background: rgba(255, 255, 255, 0.03);
            border: 1px solid rgba(255, 255, 255, 0.08);
            border-radius: 12px;
            padding: 0.85rem 1rem;
            color: white;
            font-family: inherit;
            font-size: 0.95rem;
            outline: none;
            transition: all 0.2s ease;
        }

        .settings-input:focus {
            border-color: var(--primary);
            background: rgba(255, 255, 255, 0.06);
            box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.15);
        }

        @keyframes scaleIn {
            from { transform: scale(0.9); opacity: 0; }
            to { transform: scale(1); opacity: 1; }
        }

        @keyframes pulse {
            0%, 100% { opacity: 0.6; }
            50% { opacity: 1; }
        }

        @keyframes fadeIn {
            from { opacity: 0; transform: translateY(10px); }
            to { opacity: 1; transform: translateY(0); }
        }
    </style>
</head>
<body>

    <div class="drag-overlay" id="dragOverlay">
        <svg width="64" height="64" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M12 16.5V9.75m0 0l3 3m-3-3l-3 3M6.75 19.5a4.5 4.5 0 01-1.41-8.775 5.25 5.25 0 0110.233-2.33 3 3 0 013.758 3.848A3.752 3.752 0 0118 19.5H6.75z"></path></svg>
        <h2>Ekran Görüntüsünü Buraya Bırakın</h2>
    </div>

    <header>
        <div class="logo">
            {% if logo_base64 %}
            <img src="data:image/png;base64,{{ logo_base64 }}" alt="Logo" style="width: 32px; height: 32px; border-radius: 50%; object-fit: cover; border: 1.5px solid rgba(255, 255, 255, 0.2); box-shadow: 0 0 10px rgba(99, 102, 241, 0.5);">
            {% endif %}
            <span>Transkriptör Chat</span>
            <span class="badge">Gemini OCR Aktif</span>
        </div>
        <div style="display: flex; align-items: center; gap: 1rem;">
            {% if cookies_loaded %}
            <span class="badge" style="background: rgba(16, 185, 129, 0.15); border: 1px solid rgba(16, 185, 129, 0.3); color: #34d399; cursor: pointer; text-transform: none;" onclick="showCookiesHelp()">🍪 Çerezler: Aktif</span>
            {% else %}
            <span class="badge" style="background: rgba(239, 68, 68, 0.15); border: 1px solid rgba(239, 68, 68, 0.3); color: #f87171; cursor: pointer; text-transform: none;" onclick="showCookiesHelp()">🍪 Çerezler: Yüklenmedi (429 Riski)</span>
            {% endif %}
            <button class="btn-settings" id="btnOpenSettings" title="Uygulama Ayarları">
                <svg width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M9.594 3.94c.09-.542.56-.94 1.11-.94h2.593c.55 0 1.02.398 1.11.94l.213 1.281c.063.374.313.686.645.87.074.04.147.083.22.127.324.196.72.257 1.075.124l1.217-.456a1.125 1.125 0 011.37.49l1.296 2.247a1.125 1.125 0 01-.26 1.43l-1.003.828c-.293.241-.438.613-.43.992a7.723 7.723 0 010 .255c-.008.378.137.75.43.991l1.004.827c.424.35.534.954.26 1.43l-1.298 2.247a1.125 1.125 0 01-1.369.491l-1.217-.456c-.355-.133-.75-.072-1.076.124a6.57 6.57 0 01-.22.128c-.331.183-.581.495-.644.869l-.213 1.28c-.09.543-.56.941-1.11.941h-2.594c-.55 0-1.02-.398-1.11-.94l-.213-1.281c-.062-.374-.312-.686-.644-.87a6.52 6.52 0 01-.22-.127c-.325-.196-.72-.257-1.076-.124l-1.217.456a1.125 1.125 0 01-1.369-.49l-1.297-2.247a1.125 1.125 0 01.26-1.43l1.004-.827c.292-.24.437-.613.43-.992a6.932 6.932 0 010-.255c.007-.378-.138-.75-.43-.991l-1.004-.827a1.125 1.125 0 01-.26-1.43l1.297-2.247a1.125 1.125 0 011.37-.491l1.216.456c.356.133.751.072 1.076-.124.072-.044.146-.087.22-.128.332-.183.582-.495.645-.869l.214-1.28z"></path><path stroke-linecap="round" stroke-linejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"></path></svg>
            </button>
        </div>
    </header>

    <div class="app-container">
        <div class="chat-container">
            <div class="messages-list" id="messagesList">
                <div class="message bot">
                    <div class="message-meta">🤖 Transkriptör Asistanı</div>
                    <div class="message-content">
                        Merhaba! Ben sizin çoklu video transkript asistanınızım. 
                        <br><br>
                        <strong>Kararlı Altyazı Aktarımı Devrede:</strong>
                        <ul style="margin-left: 1.5rem; margin-top: 0.5rem;">
                            <li>Sürüm 1.2.4'ün getirdiği karmaşık altyazı objeleri, tarayıcınızın okuyabileceği **standart listelere (JSON)** dönüştürüldü!</li>
                            <li>Tüm dillerdeki videoların altyazıları artık hatasız olarak önbelleğe alınmakta ve kopyalanmaktadır.</li>
                        </ul>
                    </div>
                </div>
            </div>

            <div class="input-panel">
                <div class="input-wrapper">
                    <button class="btn-attach" id="btnAttach" title="Ekran Görüntüsü Yükle">
                        <svg width="22" height="22" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M2.25 15.75l5.159-5.159a2.25 2.25 0 013.182 0l5.159 5.159m-1.5-1.5l1.409-1.409a2.25 2.25 0 013.182 0l2.909 2.909m-18 3.75h16.5a1.5 1.5 0 001.5-1.5V6a1.5 1.5 0 00-1.5-1.5H3.75A1.5 1.5 0 002.25 6v12a1.5 1.5 0 001.5 1.5zm10.5-11.25h.008v.008h-.008V8.25zm.375 0a.375.375 0 11-.75 0 .375.375 0 01.75 0z"></path></svg>
                    </button>
                    <input type="file" id="fileSelector" accept="image/*" style="display: none;">

                    <textarea class="rich-input" id="chatInput" placeholder="Bir YouTube linki yapıştırın veya doğrudan ekran görüntüsü kopyalayıp buraya Ctrl+V yapın..." style="resize: none; font-family: inherit; height: 28px; padding-top: 5px; padding-bottom: 5px; box-sizing: border-box;"></textarea>
                    
                    <button class="btn-send" id="btnSend">
                        <svg width="20" height="20" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M6 12L3.269 3.126A59.768 59.768 0 0121.485 12 59.77 59.77 0 013.27 20.876L5.999 12zm0 0h7.5"></path></svg>
                    </button>
                </div>
                <div class="input-hints">
                    <div class="paste-tip">
                        <svg width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2"></path></svg>
                        Görsel sürükleyip bırakabilir ya da 📎 butonunu kullanabilirsiniz. Ayarlar panelinden Gemini API anahtarınızı girerek OCR kalitesini artırın!
                    </div>
                    <div>Sınırsız Yerel Motor</div>
                </div>
            </div>
        </div>

        <div class="sidebar closed" id="sidebar">
            <div class="sidebar-header">
                <h3 id="sidebarTitle">Altyazı Detayı</h3>
                <button class="btn-close" id="btnCloseSidebar">×</button>
            </div>
            <div class="sidebar-content" style="height: calc(100% - 60px); display: flex; flex-direction: column;">
                <div style="display: flex; gap: 0.5rem; margin-bottom: 0.5rem;">
                    <button class="btn-card primary" id="btnCopyFullTranscript" style="padding: 0.75rem;">
                        Tüm Metni Kopyala
                    </button>
                    <button class="btn-card" id="btnDownloadTranscriptTxt" style="padding: 0.75rem;">
                        TXT İndir
                    </button>
                </div>
                <button class="btn-card" id="btnEditTranscript" style="padding: 0.6rem; margin-bottom: 0.75rem; width: 100%; font-size: 0.85rem;" onclick="triggerSidebarEdit()">
                    ✏️ Altyazıyı Düzenle / Manuel Yapıştır
                </button>
                <div class="transcript-lines" id="sidebarLines" style="flex: 1; overflow-y: auto;">
                </div>
            </div>
        </div>
    </div>

    <!-- Settings Modal -->
    <div class="settings-modal-overlay" id="settingsModal">
        <div class="settings-modal-card">
            <h3 style="font-size: 1.25rem; font-weight: 700; margin-bottom: 1.5rem; display: flex; align-items: center; gap: 0.5rem;">
                ⚙️ Uygulama Ayarları
            </h3>
            
            <div style="display: flex; flex-direction: column; gap: 1.25rem; margin-bottom: 2rem;">
                <div>
                    <label style="display: block; font-size: 0.85rem; font-weight: 600; color: var(--text-muted); margin-bottom: 0.5rem;">OCR Analiz Motoru</label>
                    <select id="settingOcrEngine" class="settings-input" style="background: rgba(0,0,0,0.4); border: 1px solid var(--border-color);">
                        <option value="gemini">Google Gemini 1.5 Flash (Önerilen - Kusursuz & Hızlı)</option>
                        <option value="ocr_space">OCR.space Ücretsiz Genel API (Yavaş & Rate Limitli)</option>
                    </select>
                </div>
                
                <div id="geminiKeyContainer">
                    <label style="display: block; font-size: 0.85rem; font-weight: 600; color: var(--text-muted); margin-bottom: 0.5rem; display: flex; justify-content: space-between;">
                        <span>Gemini API Key</span>
                        <a href="https://aistudio.google.com/" target="_blank" style="color: var(--primary); text-decoration: none;">Ücretsiz Anahtar Al ↗</a>
                    </label>
                    <input type="password" id="settingGeminiKey" class="settings-input" placeholder="AIzaSy...">
                </div>
            </div>
            
            <div style="display: flex; gap: 0.75rem;">
                <button class="btn-card primary" id="btnSaveSettings" style="padding: 0.75rem; font-size: 0.9rem; font-weight: 600;">💾 Ayarları Kaydet</button>
                <button class="btn-card" id="btnCloseSettings" style="padding: 0.75rem; font-size: 0.9rem;">Kapat</button>
            </div>
        </div>
    </div>

    <div class="toast" id="toast">Kopyalandı!</div>

    <script>
        const chatInput = document.getElementById('chatInput');
        const btnSend = document.getElementById('btnSend');
        const messagesList = document.getElementById('messagesList');
        const sidebar = document.getElementById('sidebar');
        const sidebarTitle = document.getElementById('sidebarTitle');
        const sidebarLines = document.getElementById('sidebarLines');
        const btnCloseSidebar = document.getElementById('btnCloseSidebar');
        const btnCopyFullTranscript = document.getElementById('btnCopyFullTranscript');
        const btnDownloadTranscriptTxt = document.getElementById('btnDownloadTranscriptTxt');
        const toast = document.getElementById('toast');
        
        const btnAttach = document.getElementById('btnAttach');
        const fileSelector = document.getElementById('fileSelector');
        const dragOverlay = document.getElementById('dragOverlay');

        // Settings Modal Elements
        const btnOpenSettings = document.getElementById('btnOpenSettings');
        const btnCloseSettings = document.getElementById('btnCloseSettings');
        const btnSaveSettings = document.getElementById('btnSaveSettings');
        const settingsModal = document.getElementById('settingsModal');
        const settingOcrEngine = document.getElementById('settingOcrEngine');
        const settingGeminiKey = document.getElementById('settingGeminiKey');

        // Local cache of pre-fetched transcripts
        const loadedTranscripts = {};
        let activeTranscript = [];
        let activeVideoTitle = "";

        // Settings LocalStorage Management
        const savedEngine = localStorage.getItem('ocr_engine') || 'ocr_space';
        const savedKey = localStorage.getItem('gemini_api_key') || '';
        settingOcrEngine.value = savedEngine;
        settingGeminiKey.value = savedKey;

        function toggleGeminiKeyVisibility() {
            const container = document.getElementById('geminiKeyContainer');
            if (settingOcrEngine.value === 'gemini') {
                container.style.display = 'block';
            } else {
                container.style.display = 'none';
            }
        }
        settingOcrEngine.addEventListener('change', toggleGeminiKeyVisibility);
        toggleGeminiKeyVisibility();

        btnOpenSettings.addEventListener('click', () => {
            settingsModal.style.display = 'flex';
        });

        btnCloseSettings.addEventListener('click', () => {
            settingsModal.style.display = 'none';
        });

        btnSaveSettings.addEventListener('click', () => {
            localStorage.setItem('ocr_engine', settingOcrEngine.value);
            localStorage.setItem('gemini_api_key', settingGeminiKey.value);
            settingsModal.style.display = 'none';
            showToast("Ayarlar başarıyla kaydedildi!");
        });

        settingsModal.addEventListener('click', (e) => {
            if (e.target === settingsModal) {
                settingsModal.style.display = 'none';
            }
        });

        btnSend.addEventListener('click', () => {
            const val = chatInput.value.trim();
            if (val) {
                addUserMessage(val);
                chatInput.value = "";
                processTextQuery(val);
            }
        });

        chatInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                btnSend.click();
            }
        });

        btnAttach.addEventListener('click', () => {
            fileSelector.click();
        });

        fileSelector.addEventListener('change', (e) => {
            const file = e.target.files[0];
            if (file) {
                processImageFile(file);
            }
        });

        window.addEventListener('dragenter', (e) => {
            e.preventDefault();
            dragOverlay.style.display = 'flex';
        });

        window.addEventListener('dragover', (e) => {
            e.preventDefault();
        });

        window.addEventListener('dragleave', (e) => {
            if (e.relatedTarget === null || e.clientX === 0) {
                dragOverlay.style.display = 'none';
            }
        });

        window.addEventListener('drop', (e) => {
            e.preventDefault();
            dragOverlay.style.display = 'none';
            
            const file = e.dataTransfer.files[0];
            if (file && file.type.startsWith('image/')) {
                processImageFile(file);
            }
        });

        // --- CLIPBOARD PASTE INTERCEPTOR (ONLY CAPTURES IMAGES) ---
        function handlePasteEvent(e) {
            try {
                const clipboardData = e.clipboardData || window.clipboardData;
                if (!clipboardData) return;
                
                let imageFound = false;
                
                // 1. Check files
                if (clipboardData.files && clipboardData.files.length > 0) {
                    for (let file of clipboardData.files) {
                        if (file && file.type && file.type.startsWith('image/')) {
                            imageFound = true;
                            e.preventDefault();
                            e.stopPropagation();
                            processImageFile(file);
                            break;
                        }
                    }
                }
                
                // 2. Check items
                if (!imageFound && clipboardData.items) {
                    for (let item of clipboardData.items) {
                        if (item && ((item.type && item.type.indexOf('image') !== -1) || item.kind === 'file')) {
                            const blob = item.getAsFile();
                            if (blob) {
                                imageFound = true;
                                e.preventDefault();
                                e.stopPropagation();
                                processImageFile(blob);
                                break;
                            }
                        }
                    }
                }
                
                // 3. Removed Auto-submit text! Let the browser handle standard text paste into chatInput.
            } catch (err) {
                console.error("Paste intercept error:", err);
            }
        }

        // Register directly on chatInput to intercept instantly when it is focused
        chatInput.addEventListener('paste', handlePasteEvent);

        // Register globally as capturing for other paste targets
        document.addEventListener('paste', function(e) {
            if (document.activeElement !== chatInput) {
                handlePasteEvent(e);
            }
        }, true);

        // --- CLIENT SIDE CANVAS IMAGE COMPRESSION ---
        function processImageFile(file) {
            showToast("Görsel algılandı, sıkıştırılıyor...");
            const reader = new FileReader();
            reader.onload = function(event) {
                const img = new Image();
                img.onload = function() {
                    const canvas = document.createElement('canvas');
                    let width = img.width;
                    let height = img.height;
                    const max_size = 1280;
                    
                    if (width > height) {
                        if (width > max_size) {
                            height *= max_size / width;
                            width = max_size;
                        }
                    } else {
                        if (height > max_size) {
                            width *= max_size / height;
                            height = max_size;
                        }
                    }
                    
                    canvas.width = width;
                    canvas.height = height;
                    const ctx = canvas.getContext('2d');
                    ctx.drawImage(img, 0, 0, width, height);
                    
                    // Compress to JPEG with 0.8 quality to minimize payload size and improve response speed
                    const compressedBase64 = canvas.toDataURL('image/jpeg', 0.8);
                    
                    addUserImageMessage(compressedBase64);
                    processOcrQuery(compressedBase64);
                };
                img.src = event.target.result;
            };
            reader.readAsDataURL(file);
        }

        // Direct drag and drop support on chatInput textarea
        chatInput.addEventListener('dragover', (e) => {
            e.preventDefault();
        });
        chatInput.addEventListener('drop', (e) => {
            e.preventDefault();
            const file = e.dataTransfer.files[0];
            if (file && file.type.startsWith('image/')) {
                processImageFile(file);
            }
        });

        btnCloseSidebar.addEventListener('click', () => {
            sidebar.classList.add('closed');
        });

        function addUserMessage(text) {
            const msg = document.createElement('div');
            msg.className = 'message user';
            msg.innerHTML = `
                <div class="message-meta">👤 Siz</div>
                <div class="message-content">${escapeHtml(text)}</div>
            `;
            messagesList.appendChild(msg);
            scrollChat();
        }

        function addUserImageMessage(base64Image) {
            const msg = document.createElement('div');
            msg.className = 'message user';
            msg.innerHTML = `
                <div class="message-meta">👤 Ekran Görüntüsü Yüklediniz</div>
                <div class="message-content">
                    <img src="${base64Image}" class="msg-image-preview" alt="Ekran Görüntüsü">
                </div>
            `;
            messagesList.appendChild(msg);
            scrollChat();
        }

        function addBotLoadingMessage(text="Analiz ediliyor...") {
            const msg = document.createElement('div');
            msg.className = 'chat-loading';
            msg.id = 'tempLoader';
            msg.innerHTML = `
                <svg width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24" style="animation: spin 1s linear infinite;"><path d="M4 4v5h.582m15.356 2A8.001 8.001 0 1121.21 8H18.5"></path></svg>
                <span>${text}</span>
            `;
            messagesList.appendChild(msg);
            scrollChat();
            return msg;
        }

        function removeLoader() {
            const loader = document.getElementById('tempLoader');
            if (loader) loader.remove();
        }

        function showToast(message) {
            toast.textContent = message;
            toast.classList.add('show');
            setTimeout(() => {
                toast.classList.remove('show');
            }, 3000);
        }

        function scrollChat() {
            messagesList.scrollTop = messagesList.scrollHeight;
        }

        function escapeHtml(text) {
            return text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
        }

        async function processTextQuery(url) {
            addBotLoadingMessage("Video analiz ediliyor...");
            try {
                const response = await fetch('/api/transcript', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({ url })
                });
                const data = await response.json();
                removeLoader();

                if (data.status === 'success') {
                    // Cache transcript
                    loadedTranscripts[data.video_id] = data.transcript;
                    addBotVideoResponse([data]);
                } else {
                    addBotSimpleResponse(`Hata oluştu: ${data.message}`);
                }
            } catch (e) {
                removeLoader();
                addBotSimpleResponse("Sunucuya bağlanılamadı.");
            }
        }

        async function processOcrQuery(base64Image) {
            const engine = localStorage.getItem('ocr_engine') || 'ocr_space';
            const apiKey = localStorage.getItem('gemini_api_key') || '';
            
            if (engine === 'gemini' && !apiKey) {
                removeLoader();
                addBotSimpleResponse("Gemini API Anahtarı girilmemiş. Lütfen sağ üstteki Ayarlar ⚙️ çarkından anahtarınızı girin veya OCR.space motorunu seçin.");
                return;
            }

            addBotLoadingMessage(engine === 'gemini' ? "Gemini AI ile videolar tespit ediliyor..." : "OCR.space ile metin taranıyor...");
            try {
                const response = await fetch('/api/ocr', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({ 
                        image: base64Image,
                        api_key: apiKey,
                        ocr_engine: engine
                    })
                });
                const data = await response.json();
                removeLoader();

                if (data.status === 'success') {
                    // Cache all pre-fetched transcripts into memory!
                    data.results.forEach(vid => {
                        if (vid.transcript) {
                            loadedTranscripts[vid.video_id] = vid.transcript;
                        }
                    });
                    addBotVideoResponse(data.results);
                } else {
                    addBotSimpleResponse(`Tarama tamamlandı ancak bir sorun oluştu: ${data.message}`);
                }
            } catch (e) {
                removeLoader();
                addBotSimpleResponse("Ekran görüntüsü OCR işlemi başarısız oldu.");
            }
        }

        function addBotSimpleResponse(text) {
            const msg = document.createElement('div');
            msg.className = 'message bot';
            msg.innerHTML = `
                <div class="message-meta">🤖 Transkriptör Asistanı</div>
                <div class="message-content">${escapeHtml(text)}</div>
            `;
            messagesList.appendChild(msg);
            scrollChat();
        }

        window.showCookiesHelp = function() {
            alert("YouTube Çerezleri (cookies.txt) Yönlendirmesi:

" +
                  "Eğer YouTube'dan altyazı çekerken 429 (Too Many Requests) hatası alıyorsanız:
" +
                  "1. Tarayıcınıza 'Get cookies.txt LOCALLY' veya 'Cookie-Editor' eklentisini kurun.
" +
                  "2. YouTube.com adresine gidip eklenti üzerinden çerezleri Netscape formatında dışa aktarın.
" +
                  "3. Dosyayı 'cookies.txt' adıyla bu uygulamanın çalıştığı klasöre kaydedin.
" +
                  "4. Uygulamayı yeniden başlatın.");
        };

        function hasCriticalError(transcript) {
            return !transcript || (transcript.length === 1 && transcript[0].text.includes("Kritik Hata"));
        }

        function getActionButtonsHtml(videoId, title, hasError) {
            const encodedTitle = encodeURIComponent(title);
            if (hasError) {
                return `
                    <button class="btn-card warning-btn" onclick="openTranscriptSidebar('${videoId}', '${encodedTitle}', true)">
                        ✍️ Yapıştır
                    </button>
                    <button class="btn-card" onclick="openTranscriptSidebar('${videoId}', '${encodedTitle}', false)">
                        🔍 Detay
                    </button>
                `;
            } else {
                return `
                    <button class="btn-card primary" onclick="copyTranscriptDirectly('${videoId}')">
                        📋 Kopyala
                    </button>
                    <button class="btn-card" onclick="openTranscriptSidebar('${videoId}', '${encodedTitle}', false)">
                        🔍 Detay
                    </button>
                `;
            }
        }

        function addBotVideoResponse(videos) {
            const msg = document.createElement('div');
            msg.className = 'message bot';
            
            let videosHtml = "";
            videos.forEach((vid, idx) => {
                const safeTitle = escapeHtml(vid.title);
                const hasError = hasCriticalError(vid.transcript);
                const actionBtnHtml = getActionButtonsHtml(vid.video_id, vid.title, hasError);
                videosHtml += `
                    <div class="video-card" id="card-${vid.video_id}">
                        <div class="video-thumb-container">
                            <img src="${vid.thumbnail}" alt="Thumbnail">
                        </div>
                        <div class="video-info">
                            <div class="video-title" title="${safeTitle}">${safeTitle}</div>
                            <div class="video-channel">👤 ${escapeHtml(vid.author)}</div>
                            <div class="video-actions" id="actions-${vid.video_id}">
                                ${actionBtnHtml}
                            </div>
                        </div>
                    </div>
                `;
            });

            msg.innerHTML = `
                <div class="message-meta">🤖 Transkriptör Asistanı</div>
                <div class="message-content">
                    Ekran görüntünüzde / girdinizde tespit edilen videolar ve altyazı durumları:
                    <div class="videos-grid">
                        ${videosHtml}
                    </div>
                </div>
            `;
            messagesList.appendChild(msg);
            scrollChat();
        }

        // --- INSTANT SYNCHRONOUS CLIPBOARD WRITING (ZERO LATENCY, ZERO BLOCKS) ---
        window.copyTranscriptDirectly = async function(videoId) {
            const transcript = loadedTranscripts[videoId];
            if (!transcript || transcript.length === 0) {
                showToast("Altyazı önbellekte bulunamadı!", "warning");
                return;
            }
            
            try {
                const fullText = transcript.map(l => l.text).join(' ');
                await navigator.clipboard.writeText(fullText);
                showToast("Altyazı metni başarıyla panoya kopyalandı!");
            } catch (e) {
                const success = fallbackCopyTextToClipboard(transcript.map(l => l.text).join(' '));
                if (!success) {
                    showToast("Pano erişim hatası! Lütfen 'Detay' panelinden kopyalayın.", "warning");
                }
            }
        };

        function fallbackCopyTextToClipboard(text) {
            const textArea = document.createElement("textarea");
            textArea.value = text;
            textArea.style.top = "0";
            textArea.style.left = "0";
            textArea.style.position = "fixed";
            document.body.appendChild(textArea);
            textArea.focus();
            textArea.select();
            let successful = false;
            try {
                successful = document.execCommand('copy');
            } catch (err) {}
            document.body.removeChild(textArea);
            return successful;
        }

        let activeVideoIdForEdit = null;

        window.openTranscriptSidebar = function(videoId, encodedTitle, forceEdit = false) {
            activeVideoTitle = decodeURIComponent(encodedTitle);
            sidebarTitle.textContent = activeVideoTitle;
            sidebar.classList.remove('closed');
            activeVideoIdForEdit = videoId;

            const transcript = loadedTranscripts[videoId];
            const hasError = hasCriticalError(transcript);

            if (hasError || forceEdit) {
                renderSidebarPasteInterface(videoId);
            } else {
                activeTranscript = transcript;
                renderSidebarLines(transcript, videoId);
            }
        };

        window.triggerSidebarEdit = function() {
            if (activeVideoIdForEdit) {
                openTranscriptSidebar(activeVideoIdForEdit, encodeURIComponent(activeVideoTitle), true);
            }
        };

        function renderSidebarPasteInterface(videoId) {
            const transcript = loadedTranscripts[videoId];
            const existingText = (transcript && !hasCriticalError(transcript)) ? transcript.map(l => l.text).join('
') : "";
            
            sidebarLines.innerHTML = `
                <div style="margin-bottom: 1rem; color: #f59e0b; font-size: 0.85rem; line-height: 1.4;">
                    ⚠️ YouTube altyazı çekimini engelledi veya altyazı bulunamadı. Lütfen altyazıyı manuel yapıştırıp kaydedin.
                </div>
                <div style="display: flex; flex-direction: column; gap: 0.75rem; height: calc(100% - 60px);">
                    <textarea id="manualSubInput" placeholder="Buraya altyazı metnini yapıştırın... (Düz metin veya zaman damgalı satırlar desteklenir)" style="width: 100%; flex: 1; min-height: 250px; background: rgba(0, 0, 0, 0.3); border: 1px solid var(--border-color); border-radius: 8px; color: var(--text-main); padding: 0.75rem; resize: vertical; font-family: inherit; font-size: 0.9rem; outline: none; line-height: 1.5;"></textarea>
                    <button class="btn-card primary" onclick="saveManualTranscript('${videoId}')" style="width: 100%; padding: 0.85rem; font-weight: 600;">
                        💾 Altyazıyı Kaydet
                    </button>
                    ${(transcript && !hasCriticalError(transcript)) ? `<button class="btn-card" onclick="openTranscriptSidebar('${videoId}', '${encodeURIComponent(activeVideoTitle)}', false)" style="width: 100%; padding: 0.5rem; font-size: 0.8rem; margin-top: 0.25rem;">İptal Et</button>` : ''}
                </div>
            `;
            
            document.getElementById('manualSubInput').value = existingText;
            document.getElementById('manualSubInput').focus();
        }

        window.saveManualTranscript = function(videoId) {
            const textarea = document.getElementById('manualSubInput');
            if (!textarea) return;
            const inputVal = textarea.value.trim();
            if (!inputVal) {
                showToast("Lütfen geçerli bir metin girin!", "warning");
                return;
            }

            // Parse pasted subtitles
            const parsedLines = parsePastedTranscript(inputVal);
            loadedTranscripts[videoId] = parsedLines;
            
            // Re-render sidebar in view mode
            openTranscriptSidebar(videoId, encodeURIComponent(activeVideoTitle), false);
            
            // Also update the video card UI in the chat list
            updateVideoCardButtons(videoId);
            
            showToast("Altyazı başarıyla güncellendi!");
        };

        window.updateVideoCardButtons = function(videoId) {
            const container = document.getElementById(`actions-${videoId}`);
            if (container) {
                const hasError = hasCriticalError(loadedTranscripts[videoId]);
                container.innerHTML = getActionButtonsHtml(videoId, activeVideoTitle, hasError);
            }
        };

        function parsePastedTranscript(text) {
            const lines = text.split('
');
            const result = [];
            let currentSec = 0;
            
            lines.forEach(line => {
                const trimmed = line.trim();
                if (!trimmed) return;
                
                // Try to detect timestamp like [01:23] or 12:34 or [1:23:45] or 01:23.45
                const timestampMatch = trimmed.match(/^(?:\[?\(?)?(\d{1,2})?:?(\d{1,2}):(\d{2})(?:\.\d+)?(?:\]?\)?\s*-?\s*)?(.*)$/);
                
                if (timestampMatch) {
                    const hours = timestampMatch[1] ? parseInt(timestampMatch[1]) : 0;
                    const minutes = parseInt(timestampMatch[2]);
                    const seconds = parseInt(timestampMatch[3]);
                    const content = timestampMatch[4].trim();
                    
                    const timeInSeconds = (hours * 3600) + (minutes * 60) + seconds;
                    if (content) {
                        result.push({
                            text: content,
                            start: timeInSeconds,
                            duration: 2.0 // default duration estimation
                        });
                        currentSec = timeInSeconds;
                    }
                } else {
                    // Just raw text line, assume sequential timestamps spaced by 3 seconds
                    result.push({
                        text: trimmed,
                        start: currentSec,
                        duration: 3.0
                    });
                    currentSec += 3.0;
                }
            });
            
            // If nothing parsed, return a single line with full text
            if (result.length === 0) {
                result.push({
                    text: text,
                    start: 0,
                    duration: 10
                });
            }
            return result;
        }

        function renderSidebarLines(lines, videoId) {
            sidebarLines.innerHTML = "";
            lines.forEach(l => {
                const div = document.createElement('div');
                div.className = 't-line';

                const time = document.createElement('span');
                time.className = 't-time';
                time.textContent = formatTime(l.start);
                time.onclick = () => {
                    window.open(`https://youtube.com/watch?v=${videoId}&t=${Math.floor(l.start)}s`, '_blank');
                };

                const text = document.createElement('span');
                text.className = 't-text';
                text.innerHTML = l.text;

                div.appendChild(time);
                div.appendChild(text);
                sidebarLines.appendChild(div);
            });
        }

        function formatTime(seconds) {
            const h = Math.floor(seconds / 3600);
            const m = Math.floor((seconds % 3600) / 60);
            const s = Math.floor(seconds % 60);
            const mStr = String(m).padStart(2, '0');
            const sStr = String(s).padStart(2, '0');
            if (h > 0) return `${h}:${mStr}:${sStr}`;
            return `${mStr}:${sStr}`;
        }

        btnCopyFullTranscript.addEventListener('click', () => {
            if (!activeTranscript.length) return;
            const fullText = activeTranscript.map(l => l.text).join(' ');
            navigator.clipboard.writeText(fullText);
            showToast("Bütün metin kopyalandı!");
        });

        btnDownloadTranscriptTxt.addEventListener('click', () => {
            if (!activeTranscript.length) return;
            let output = "";
            activeTranscript.forEach(l => {
                output += `[${formatTime(l.start)}] ${l.text}
`;
            });
            const filename = `${activeVideoTitle.replace(/[^a-z0-9]/gi, '_').toLowerCase()}_altyazi.txt`;
            
            const blob = new Blob([output], { type: 'text/plain;charset=utf-8;' });
            const url = URL.createObjectURL(blob);
            const link = document.createElement("a");
            link.setAttribute("href", url);
            link.setAttribute("download", filename);
            link.style.visibility = 'hidden';
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
        });
    </script>
</body>
</html>
"""

def extract_video_id(url):
    pattern = r'(?:https?:\/\/)?(?:www\.)?(?:youtube\.com\/(?:[^\/\n\s]+\/\S+\/|(?:v|e(?:mbed)?)\/|\S*?[?&]v=)|youtu\.be\/)([a-zA-Z0-9_-]{11})'
    match = re.search(pattern, url)
    return match.group(1) if match else None

def search_youtube_via_proxies(query):
    import socket
    import random
    
    orig_timeout = socket.getdefaulttimeout()
    socket.setdefaulttimeout(4) # Allow 4 seconds for DNS/TCP handshake
    
    print(f"Attempting proxy rotation fallback for search: {query}...")
    try:
        url = "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/http.txt"
        res = requests.get(url, timeout=5)
        if res.status_code != 200:
            socket.setdefaulttimeout(orig_timeout)
            return None
        proxies_list = [line.strip() for line in res.text.split('\n') if line.strip()]
        if not proxies_list:
            socket.setdefaulttimeout(orig_timeout)
            return None
    except Exception as e:
        print("Failed to load proxies for search:", e)
        socket.setdefaulttimeout(orig_timeout)
        return None
        
    random.shuffle(proxies_list)
    
    # Try first 30 proxies
    for idx, proxy_ip in enumerate(proxies_list[:30], 1):
        proxy_url = f"http://{proxy_ip}"
        ydl_opts = {
            'quiet': True,
            'default_search': 'ytsearch1',
            'skip_download': True,
            'js_runtimes': {'node': {}},
            'proxy': proxy_url
        }
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(query, download=False)
                if 'entries' in info and len(info['entries']) > 0:
                    entry = info['entries'][0]
                    print(f"SUCCESS! Searched YouTube using proxy {proxy_url}")
                    socket.setdefaulttimeout(orig_timeout)
                    return {
                        'video_id': entry['id'],
                        'title': entry['title'],
                        'author': entry.get('uploader', 'Unknown Channel'),
                        'thumbnail': entry.get('thumbnail', f"https://img.youtube.com/vi/{entry['id']}/hqdefault.jpg")
                    }
        except Exception as e:
            pass
            
    print("All proxies failed for search.")
    socket.setdefaulttimeout(orig_timeout)
    return None

def search_youtube(query):
    try:
        _, cookie_file = load_youtube_cookies_session()
        ydl_opts = {
            'quiet': True,
            'default_search': 'ytsearch1',
            'skip_download': True,
            'js_runtimes': {'node': {}}
        }
        if cookie_file:
            ydl_opts['cookiefile'] = cookie_file
            
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(query, download=False)
            if 'entries' in info and len(info['entries']) > 0:
                entry = info['entries'][0]
                return {
                    'video_id': entry['id'],
                    'title': entry['title'],
                    'author': entry.get('uploader', 'Unknown Channel'),
                    'thumbnail': entry.get('thumbnail', f"https://img.youtube.com/vi/{entry['id']}/hqdefault.jpg")
                }
    except Exception as e:
        print("YT Search Error:", e, "Trying proxy rotation fallback...")
        return search_youtube_via_proxies(query)
    return None

def fetch_transcript_via_proxies(video_id):
    global WORKING_PROXY
    import socket
    import random
    
    orig_timeout = socket.getdefaulttimeout()
    
    # 1. Try cached working proxy first
    if WORKING_PROXY:
        print(f"Trying cached working proxy: {WORKING_PROXY}...")
        socket.setdefaulttimeout(2.5) # Allow slightly more time for the cached one
        try:
            session = requests.Session()
            session.proxies = {'http': WORKING_PROXY, 'https': WORKING_PROXY}
            api = YouTubeTranscriptApi(http_client=session)
            transcript_data = api.fetch(video_id, languages=('tr', 'en'))
            if transcript_data:
                print(f"SUCCESS! Retrieved transcript using cached proxy {WORKING_PROXY}!")
                formatted_transcript = []
                if hasattr(transcript_data, 'to_raw_data'):
                    raw_data = transcript_data.to_raw_data()
                elif hasattr(transcript_data, 'snippets'):
                    raw_data = []
                    for snippet in transcript_data.snippets:
                        raw_data.append({
                            'text': snippet.text,
                            'start': snippet.start,
                            'duration': snippet.duration
                        })
                elif isinstance(transcript_data, list):
                    raw_data = transcript_data
                else:
                    raw_data = list(transcript_data)
                    
                for entry in raw_data:
                    if isinstance(entry, dict):
                        formatted_transcript.append({
                            'text': entry.get('text', ''),
                            'start': entry.get('start', 0.0),
                            'duration': entry.get('duration', 0.0)
                        })
                socket.setdefaulttimeout(orig_timeout)
                return formatted_transcript
        except Exception as e:
            print(f"Cached proxy {WORKING_PROXY} failed: {e}. Clearing cache.")
            WORKING_PROXY = None
            
    # 2. Cache failed or not set. Try proxy rotation
    socket.setdefaulttimeout(1.5) # Set 1.5s timeout for fast proxy rotation checks
    print(f"Attempting proxy rotation fallback for transcript of {video_id}...")
    try:
        url = "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/http.txt"
        res = requests.get(url, timeout=5)
        if res.status_code != 200:
            socket.setdefaulttimeout(orig_timeout)
            return None
        proxies_list = [line.strip() for line in res.text.split('\n') if line.strip()]
        if not proxies_list:
            socket.setdefaulttimeout(orig_timeout)
            return None
    except Exception as e:
        print("Failed to load fallback proxies:", e)
        socket.setdefaulttimeout(orig_timeout)
        return None
        
    random.shuffle(proxies_list)
    
    # Try up to 15 proxies to avoid freezing the server
    for idx, proxy_ip in enumerate(proxies_list[:15], 1):
        proxy_url = f"http://{proxy_ip}"
        proxies_config = {'http': proxy_url, 'https': proxy_url}
        try:
            session = requests.Session()
            session.proxies = proxies_config
            api = YouTubeTranscriptApi(http_client=session)
            transcript_data = api.fetch(video_id, languages=('tr', 'en'))
            if transcript_data:
                print(f"SUCCESS! Retrieved transcript using proxy {proxy_url}!")
                # Save as working proxy for next requests
                WORKING_PROXY = proxy_url
                
                formatted_transcript = []
                if hasattr(transcript_data, 'to_raw_data'):
                    raw_data = transcript_data.to_raw_data()
                elif hasattr(transcript_data, 'snippets'):
                    raw_data = []
                    for snippet in transcript_data.snippets:
                        raw_data.append({
                            'text': snippet.text,
                            'start': snippet.start,
                            'duration': snippet.duration
                        })
                elif isinstance(transcript_data, list):
                    raw_data = transcript_data
                else:
                    raw_data = list(transcript_data)
                    
                for entry in raw_data:
                    if isinstance(entry, dict):
                        formatted_transcript.append({
                            'text': entry.get('text', ''),
                            'start': entry.get('start', 0.0),
                            'duration': entry.get('duration', 0.0)
                        })
                
                socket.setdefaulttimeout(orig_timeout)
                return formatted_transcript
        except Exception as e:
            pass
            
    print("All fallback proxies failed.")
    socket.setdefaulttimeout(orig_timeout)
    return None

def fetch_transcript_api_safely(video_id):
    """Instantiates api and fetches transcripts, formatting FetchedTranscript to JSON list of dicts."""
    try:
        session, _ = load_youtube_cookies_session()
        api = YouTubeTranscriptApi(http_client=session)
        transcript_data = None
        
        # 1. Fetch transcript using new instance-based fetch method
        try:
            transcript_data = api.fetch(video_id, languages=('tr', 'en'))
        except Exception as e1:
            print(f"Primary fetch failed for {video_id}: {e1}")
            try:
                transcript_list = api.list(video_id)
                transcript = next(iter(transcript_list))
                transcript_data = transcript.fetch()
            except Exception as e2:
                print(f"Fallback list/fetch failed for {video_id}: {e2}. Trying proxy rotation...")
                return fetch_transcript_via_proxies(video_id)
                
        if not transcript_data:
            return None
            
        # 2. Convert custom FetchedTranscript object into serializable list of dicts!
        formatted_transcript = []
        if hasattr(transcript_data, 'to_raw_data'):
            return transcript_data.to_raw_data()
        elif hasattr(transcript_data, 'snippets'):
            # Modern 1.2.4 FetchedTranscript object with snippet objects
            for snippet in transcript_data.snippets:
                formatted_transcript.append({
                    'text': snippet.text,
                    'start': snippet.start,
                    'duration': snippet.duration
                })
        elif isinstance(transcript_data, list):
            # Classic list of dicts structure fallback
            for entry in transcript_data:
                formatted_transcript.append({
                    'text': entry.get('text', ''),
                    'start': entry.get('start', 0.0),
                    'duration': entry.get('duration', 0.0)
                })
        return formatted_transcript
        
    except Exception as e:
        print("Fetch transcript safely error:", e)
        return None

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route('/api/rate-limit-status')
def rate_limit_status():
    ip = get_client_ip()
    allowed, remaining = check_rate_limit(ip)
    
    info = IP_LIMITS.get(ip, {'count': 0, 'banned_until': 0, 'first_request': time.time()})
    
    return jsonify({
        'ip': ip,
        'count': min(info['count'], MAX_REQUESTS),
        'max': MAX_REQUESTS,
        'is_banned': not allowed,
        'remaining_ban': remaining
    })

@app.route('/api/transcript', methods=['POST'])
def get_transcript():
    data = request.json or {}
    url = data.get('url', '')
    
    video_id = extract_video_id(url)
    if not video_id:
        if len(url) == 11 and re.match(r'^[a-zA-Z0-9_-]+$', url):
            video_id = url
        else:
            return jsonify({'status': 'error', 'message': 'Invalid YouTube URL or Video ID!'})
            
    transcript_data = fetch_transcript_api_safely(video_id)
    if not transcript_data:
        return jsonify({'status': 'error', 'message': 'Could not retrieve subtitles (Subtitles might be disabled on this video).'})

    video_title = "YouTube Video"
    video_author = "YouTube Channel"
    video_thumb = f"https://img.youtube.com/vi/{video_id}/hqdefault.jpg"
    
    try:
        ydl_opts = {
            'quiet': True,
            'skip_download': True,
            'socket_timeout': 5
        }
        if WORKING_PROXY:
            ydl_opts['proxy'] = WORKING_PROXY
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(f"https://www.youtube.com/watch?v={video_id}", download=False)
            video_title = info.get('title', video_title)
            video_author = info.get('uploader', video_author)
            video_thumb = info.get('thumbnail', video_thumb)
    except Exception as e:
        print("Metadata extraction error:", e)

    return jsonify({
        'status': 'success',
        'video_id': video_id,
        'title': video_title,
        'author': video_author,
        'thumbnail': video_thumb,
        'transcript': transcript_data
    })

def is_good_match(query, video_title):
    q_words = [w for w in re.findall(r'[a-zA-Z0-9çğıöşüÇĞİÖŞÜ]+', query.lower()) if len(w) > 2]
    t_words = set(re.findall(r'[a-zA-Z0-9çğıöşüÇĞİÖŞÜ]+', video_title.lower()))
    if not q_words:
        return True
    matches = sum(1 for w in q_words if w in t_words)
    required = 2 if len(q_words) >= 3 else 1
    return matches >= required


def call_gemini_api(api_key, model, contents, system_instruction=None):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    headers = {"Content-Type": "application/json"}
    payload = {"contents": contents}
    if system_instruction:
        payload["systemInstruction"] = {
            "parts": [{"text": system_instruction}]
        }
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=30)
        if response.status_code == 200:
            res_json = response.json()
            text = res_json['candidates'][0]['content']['parts'][0]['text']
            return text, True
        else:
            return f"Gemini API Error ({response.status_code}): {response.text}", False
    except Exception as e:
        return f"Connection Error: {str(e)}", False

@app.route('/api/ocr', methods=['POST'])
def process_ocr():
    # 1. Rate Limit Validation
    ip = get_client_ip()
    allowed, remaining = check_rate_limit(ip)
    if not allowed:
        return jsonify({'status': 'error', 'message': f'IP Banned. Please wait {remaining} seconds.'}), 429
        
    # Increment rate limit count
    success, ban_time = increment_rate_limit(ip)
    if not success:
        return jsonify({'status': 'error', 'message': f'IP Banned. Too many requests.'}), 429

    data = request.json or {}
    image_base64 = data.get('image', '')
    api_key = data.get('api_key', '')
    ocr_engine = data.get('ocr_engine', 'ocr_space')
    
    if not image_base64:
        return jsonify({'status': 'error', 'message': 'Could not retrieve image data!'})
        
    try:
        if ',' in image_base64:
            image_base64_clean = image_base64.split(',')[1]
            mime_type = image_base64.split(',')[0].split(';')[0].split(':')[1]
        else:
            image_base64_clean = image_base64
            mime_type = 'image/png'
            
        # 2. Run OCR based on selected engine
        if ocr_engine == 'gemini' and api_key:
            print("Using Gemini Multimodal OCR...", flush=True)
            prompt = (
                "Identify the YouTube video titles and channel names in this image. "
                "For each video, return a JSON list containing its title and channel name. "
                "Format: [{\"title\": \"video title\", \"channel\": \"channel name\"}]. "
                "Return raw JSON only, no markdown or any other explanation text."
            )
            contents = [{
                "parts": [
                    {"text": prompt},
                    {
                        "inlineData": {
                            "mimeType": mime_type,
                            "data": image_base64_clean
                        }
                    }
                ]
            }]
            ai_res, success = call_gemini_api(api_key, "gemini-1.5-flash", contents)
            if not success:
                return jsonify({'status': 'error', 'message': f"Gemini API Error: {ai_res}"})
            
            clean_json = re.sub(r'```json|```', '', ai_res).strip()
            import json
            try:
                videos_data = json.loads(clean_json)
            except Exception as parse_err:
                print("Failed to parse Gemini JSON:", parse_err, flush=True)
                print("Raw Gemini output:", ai_res, flush=True)
                return jsonify({'status': 'error', 'message': f"Failed to parse Gemini output as JSON. Output: {ai_res}"})
            
            final_results = []
            seen_video_ids = set()
            
            for vid in videos_data:
                title = vid.get('title', '').strip()
                channel = vid.get('channel', '').strip()
                if not title:
                    continue
                
                q = f"{channel} {title}".strip()
                print(f"Trying search (Gemini Match): '{q}'", flush=True)
                video_meta = search_youtube(q)
                
                if not video_meta and title:
                    print(f"Trying search (Title only): '{title}'", flush=True)
                    video_meta = search_youtube(title)
                
                if video_meta:
                    if is_good_match(title, f"{video_meta['title']} {video_meta['author']}"):
                        if video_meta['video_id'] not in seen_video_ids:
                            transcript_data = fetch_transcript_api_safely(video_meta['video_id'])
                            if transcript_data:
                                video_meta['transcript'] = transcript_data
                            else:
                                video_meta['transcript'] = [{
                                    'text': '[Critical Error: YouTube blocked transcript fetch from this IP (429) or subtitles are disabled.]',
                                    'start': 0.0,
                                    'duration': 0.0
                                }]
                            final_results.append(video_meta)
                            seen_video_ids.add(video_meta['video_id'])
            
            if final_results:
                return jsonify({
                    'status': 'success',
                    'results': final_results
                })
            else:
                return jsonify({'status': 'error', 'message': 'No matching videos found on YouTube.'})
                
        # 3. Fallback to OCR.space
        payload = {
            'base64Image': f"data:{mime_type};base64,{image_base64_clean}",
            'language': 'eng',
            'isOverlayRequired': False,
            'OCREngine': '2',
            'detectOrientation': 'true',
            'scale': 'true'
        }
        
        ocr_api_key = os.environ.get('OCR_API_KEY', 'helloworld')
        headers = {'apikey': ocr_api_key}
        ocr_response = requests.post(
            'https://api.ocr.space/parse/image',
            data=payload,
            headers=headers
        )
        ocr_result = ocr_response.json()
        
        if ocr_result.get('OCRExitCode') == 1:
            parsed_text = ocr_result['ParsedResults'][0]['ParsedText'].strip()
            print("--- RAW OCR TEXT ---\n", parsed_text)
            
            if not parsed_text:
                return jsonify({'status': 'error', 'message': 'No readable text found in the screenshot!'})
            
            # 1. COLUMN SPLITTING
            column_split_lines = []
            for raw_line in parsed_text.split('\n'):
                parts = re.split(r'\s{2,}', raw_line.strip())
                for part in parts:
                    part_cleaned = part.strip()
                    if part_cleaned:
                        column_split_lines.append(part_cleaned)
                        
            print("--- COLUMN-SPLIT LINES ---\n", column_split_lines)
            
            # Filter duration and index noise
            clean_lines = []
            for line in column_split_lines:
                line_cleaned = re.sub(r'\b(?:\d{1,2}:)?\d{1,2}:\d{2}\b', '', line)
                line_cleaned = re.sub(r'^\d+$', '', line_cleaned)
                line_cleaned = line_cleaned.strip()
                if len(line_cleaned) > 1:
                    clean_lines.append(line_cleaned)
            
            # --- ULTIMATE ROBUST ANCHOR QUERY GENERATOR ---
            meta_indicators = ['views', 'izlenme', 'görüntüleme', 'ago', 'önce', '•', 'view', 'day', 'hour', 'week', 'month', 'year', 'gün', 'saat', 'hafta', 'ay', 'yıl']
            
            final_results = []
            
            # Find all anchors
            anchors = []
            for i, line in enumerate(clean_lines):
                is_anchor = False
                if '•' in line:
                    if any(term in line.lower() for term in ['view', 'izlenme', 'görüntüleme', 'ago', 'önce', 'gün', 'saat', 'yıl', 'ay']):
                        is_anchor = True
                else:
                    has_views = re.search(r'\b\d+(?:\.\d+)?[KMB]?(?:\s*views|\s*görüntüleme|\s*izlenme|\s*izleyici|\s*görüntülenmesi)', line, re.IGNORECASE)
                    has_time = any(term in line.lower() for term in ['ago', 'önce', 'day', 'hour', 'week', 'month', 'year', 'gün', 'saat', 'hafta', 'ay', 'yıl'])
                    if has_views and has_time:
                        is_anchor = True
                if is_anchor:
                    anchors.append(i)
            
            print("Detected anchors indices:", anchors)
            
            # Process each anchor
            for anchor_idx in anchors[:4]:  # limit to top 4 detected videos
                anchor_line = clean_lines[anchor_idx]
                
                # 1. Extract Channel Name from anchor line
                channel_name = ""
                channel_match = re.search(r'^(.*?)\s*(?:•|\b\d+(?:\.\d+)?[KMB]?(?:\s*views|\s*görüntüleme|\s*izlenme|\s*izleyici|\s*görüntülenmesi))', anchor_line, re.IGNORECASE)
                if channel_match:
                    channel_name = channel_match.group(1).strip()
                    channel_name = re.sub(r'[|$?!\(\)\[\]\-\*\:\•]', '', channel_name).strip()
                
                # 2. Extract preceding candidate title lines
                preceding = []
                for offset in range(1, 5):
                    idx = anchor_idx - offset
                    if idx >= 0:
                        line_val = clean_lines[idx]
                        is_meta = any(term in line_val.lower() for term in meta_indicators) or re.search(r'\b\d+[KMB]\b', line_val)
                        is_noise = re.match(r'^(?:\d{1,2}:)?\d{1,2}:\d{2}$', line_val) or line_val.isdigit()
                        if not is_meta and not is_noise and len(line_val) > 2:
                            cleaned_val = re.sub(r'[|$?!\(\)\[\]\-\*\:]', ' ', line_val).strip()
                            if cleaned_val:
                                preceding.append(cleaned_val)
                
                candidates = []
                if len(preceding) == 1:
                    candidates.append(f"{channel_name} {preceding[0]}")
                    candidates.append(preceding[0])
                elif len(preceding) == 2:
                    candidates.append(f"{channel_name} {preceding[1]} {preceding[0]}")
                    candidates.append(f"{preceding[1]} {preceding[0]}")
                    candidates.append(f"{channel_name} {preceding[0]}")
                    candidates.append(preceding[0])
                elif len(preceding) >= 3:
                    candidates.append(f"{channel_name} {preceding[2]} {preceding[1]} {preceding[0]}")
                    candidates.append(f"{preceding[2]} {preceding[1]} {preceding[0]}")
                    candidates.append(f"{channel_name} {preceding[1]} {preceding[0]}")
                    candidates.append(f"{preceding[1]} {preceding[0]}")
                
                clean_candidates = []
                for cand in candidates:
                    cand_clean = re.sub(r'\s+', ' ', cand).strip()
                    if cand_clean:
                        words = cand_clean.split()
                        if len(words) > 12:
                            cand_clean = " ".join(words[:12])
                        if cand_clean not in clean_candidates:
                            clean_candidates.append(cand_clean)
                
                print(f"Anchor {anchor_idx} clean candidates:", clean_candidates)
                
                matched_video = None
                for q in clean_candidates:
                    print(f"Trying search: '{q}'")
                    video_meta = search_youtube(q)
                    if video_meta and is_good_match(q, video_meta['title']):
                        transcript_data = fetch_transcript_api_safely(video_meta['video_id'])
                        if transcript_data:
                            video_meta['transcript'] = transcript_data
                        else:
                            video_meta['transcript'] = [{
                                'text': '[Kritik Hata: YouTube bu IP adresinden alt yazı çekilmesini engelledi (429 Too Many Requests) veya alt yazılar devre dışı. Lütfen dış bağlantıyı kullanarak alt yazıyı alın ve buraya yapıştırın.]',
                                'start': 0.0,
                                'duration': 0.0
                            }]
                        matched_video = video_meta
                        break
                        
                if matched_video:
                    final_results.append(matched_video)
            
            if final_results:
                return jsonify({
                    'status': 'success',
                    'results': final_results
                })
            else:
                print("Sequential search returned 0 results. Executing raw line search...")
                for line in clean_lines[:3]:
                    is_meta = any(term in line.lower() for term in meta_indicators) or re.search(r'\b\d+[KMB]\b', line)
                    is_duration = re.match(r'^(?:\d{1,2}:)?\d{1,2}:\d{2}$', line) or line.isdigit()
                    if not is_meta and not is_duration and len(line) > 12:
                        raw_q = re.sub(r'[|$?!\(\)\[\]\-\*\:]', ' ', line).strip()
                        print(f"Last resort search: '{raw_q}'")
                        video_meta = search_youtube(raw_q)
                        if video_meta:
                            transcript_data = fetch_transcript_api_safely(video_meta['video_id'])
                            if transcript_data:
                                video_meta['transcript'] = transcript_data
                            else:
                                video_meta['transcript'] = [{
                                    'text': '[Kritik Hata: YouTube bu IP adresinden alt yazı çekilmesini engelledi (429 Too Many Requests) veya alt yazılar devre dışı. Lütfen dış bağlantıyı kullanarak alt yazıyı alın ve buraya yapıştırın.]',
                                    'start': 0.0,
                                    'duration': 0.0
                                }]
                            final_results.append(video_meta)
                            if len(final_results) >= 3:
                                break
                                
                if final_results:
                    return jsonify({
                        'status': 'success',
                        'results': final_results
                    })
                    
                return jsonify({'status': 'error', 'message': f"No matching video found!"})
        else:
            error_details = ocr_result.get('ErrorMessage') or ocr_result.get('ErrorMessageDescription') or 'OCR server failed to read the image.'
            if isinstance(error_details, list):
                error_details = ", ".join(error_details)
            return jsonify({'status': 'error', 'message': f'OCR error: {error_details}'})
            
    except Exception as e:
        return jsonify({'status': 'error', 'message': f"System error: {str(e)}"})

if __name__ == '__main__':
    print("----------------------------------------------------------------")
    print("Transkriptor Chat server successfully started!")
    print("Please open http://127.0.0.1:5000 in your browser.")
    print("----------------------------------------------------------------")
    app.run(debug=False, port=5000)

