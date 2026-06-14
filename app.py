import re
import os
import base64
import requests
import time
import http.cookiejar
from flask import Flask, request, jsonify, render_template_string
from youtube_transcript_api import YouTubeTranscriptApi
import yt_dlp

app = Flask(__name__)

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
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Transkriptor Chat - Multi-Video Subtitle Assistant</title>
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700;800&display=swap" rel="stylesheet">
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

        .rate-limit-banner {
            width: 100%;
            padding: 0.6rem 1rem;
            font-size: 0.85rem;
            font-weight: 600;
            text-align: center;
            transition: all 0.3s ease;
            z-index: 1000;
            background: rgba(16, 185, 129, 0.15);
            border-bottom: 1px solid rgba(16, 185, 129, 0.3);
            color: #34d399;
            display: flex;
            justify-content: center;
            align-items: center;
            gap: 0.5rem;
        }

        .rate-limit-banner.banned {
            background: rgba(239, 68, 68, 0.15);
            border-bottom: 1px solid rgba(239, 68, 68, 0.3);
            color: #f87171;
        }

        .app-container {
            display: flex;
            flex: 1;
            height: calc(100vh - 110px);
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
            flex-shrink: 0;
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
            flex-shrink: 0;
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

        .btn-card:hover {
            background: rgba(255,255,255,0.1);
        }

        .sidebar {
            width: 450px;
            max-width: 450px;
            border-left: 1px solid var(--border-color);
            background: rgba(17, 25, 40, 0.75);
            backdrop-filter: blur(20px);
            display: flex;
            flex-direction: column;
            transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
            z-index: 50;
            overflow: hidden;
            flex-shrink: 0;
        }

        .sidebar.closed {
            width: 0;
            max-width: 0;
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

    <div class="rate-limit-banner" id="rateLimitBanner">
        📷 Image OCR Limits: Checking status...
    </div>

    <div class="drag-overlay" id="dragOverlay">
        <svg width="64" height="64" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M12 16.5V9.75m0 0l3 3m-3-3l-3 3M6.75 19.5a4.5 4.5 0 01-1.41-8.775 5.25 5.25 0 0110.233-2.33 3 3 0 013.758 3.848A3.752 3.752 0 0118 19.5H6.75z"></path></svg>
        <h2>Drop Screenshot Here</h2>
    </div>

    <header>
        <div class="logo">
            <span>Transkriptor Chat</span>
            <span class="badge">Stable JSON Output</span>
        </div>
    </header>

    <div class="app-container">
        <div class="chat-container">
            <div class="messages-list" id="messagesList">
                <div class="message bot">
                    <div class="message-meta">🤖 Transkriptor Assistant</div>
                    <div class="message-content">
                        Hello! I am your multi-video transcript assistant.
                        <br><br>
                        <strong>Stable Subtitle Pipeline Enabled:</strong>
                        <ul style="margin-left: 1.5rem; margin-top: 0.5rem;">
                            <li>Convert complex multi-layered subtitle structures to standard serializable JSON format.</li>
                            <li>Allows seamless translation caching and transcript exports.</li>
                            <li>Paste a YouTube video link directly or upload/paste a screenshot of videos to start!</li>
                        </ul>
                    </div>
                </div>
            </div>

            <div class="input-panel">
                <div class="input-wrapper">
                    <button class="btn-attach" id="btnAttach" title="Upload Screenshot">
                        <svg width="22" height="22" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M2.25 15.75l5.159-5.159a2.25 2.25 0 013.182 0l5.159 5.159m-1.5-1.5l1.409-1.409a2.25 2.25 0 013.182 0l2.909 2.909m-18 3.75h16.5a1.5 1.5 0 001.5-1.5V6a1.5 1.5 0 00-1.5-1.5H3.75A1.5 1.5 0 002.25 6v12a1.5 1.5 0 001.5 1.5zm10.5-11.25h.008v.008h-.008V8.25zm.375 0a.375.375 0 11-.75 0 .375.375 0 01.75 0z"></path></svg>
                    </button>
                    <input type="file" id="fileSelector" accept="image/*" style="display: none;">

                    <div class="rich-input" id="chatInput" contenteditable="true" placeholder="Paste a YouTube link or drag/paste screenshots here..."></div>
                    
                    <button class="btn-send" id="btnSend">
                        <svg width="20" height="20" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M6 12L3.269 3.126A59.768 59.768 0 0121.485 12 59.77 59.77 0 013.27 20.876L5.999 12zm0 0h7.5"></path></svg>
                    </button>
                </div>
                <div class="input-hints">
                    <div class="paste-tip">
                        <svg width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2"></path></svg>
                        Click in the input area and press Ctrl+V to paste link or screenshots directly!
                    </div>
                    <div>Local Engine Enabled</div>
                </div>
            </div>
        </div>

        <div class="sidebar closed" id="sidebar">
            <div class="sidebar-header">
                <h3 id="sidebarTitle">Transcript Detail</h3>
                <button class="btn-close" id="btnCloseSidebar">×</button>
            </div>
            <div class="sidebar-content">
                <div style="display: flex; gap: 0.5rem;">
                    <button class="btn-card primary" id="btnCopyFullTranscript" style="padding: 0.75rem;">
                        Copy Full Text
                    </button>
                    <button class="btn-card" id="btnDownloadTranscriptTxt" style="padding: 0.75rem;">
                        Download TXT
                    </button>
                </div>
                <div class="transcript-lines" id="sidebarLines">
                </div>
            </div>
        </div>
    </div>

    <div class="toast" id="toast">Copied to clipboard!</div>

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

        // Local cache of pre-fetched transcripts
        const loadedTranscripts = {};
        let activeTranscript = [];
        let activeVideoTitle = "";
        let banTimer = null;

        // Rate Limit Status Banner Updater
        async function updateRateLimitBanner() {
            try {
                const res = await fetch('/api/rate-limit-status');
                const data = await res.json();
                const banner = document.getElementById('rateLimitBanner');
                
                if (data.is_banned) {
                    banner.className = 'rate-limit-banner banned';
                    if (banTimer) clearInterval(banTimer);
                    let remaining = data.remaining_ban;
                    
                    const updateText = () => {
                        banner.innerHTML = `🚨 <strong>IP Ban 5 min</strong> | Your IP is banned. Try again in ${remaining}s.`;
                    };
                    updateText();
                    
                    banTimer = setInterval(() => {
                        remaining--;
                        if (remaining <= 0) {
                            clearInterval(banTimer);
                            updateRateLimitBanner();
                        } else {
                            updateText();
                        }
                    }, 1000);
                } else {
                    banner.className = 'rate-limit-banner ok';
                    banner.innerHTML = `📷 Image OCR Requests: <strong>${data.count}/${data.max}</strong> (Over-limit triggers an IP Ban of 5 min).`;
                }
            } catch (e) {
                console.error("Failed to fetch rate limit status:", e);
            }
        }

        // Initialize Rate Limit Banner Status
        updateRateLimitBanner();

        btnSend.addEventListener('click', () => {
            const val = chatInput.textContent.trim();
            if (val) {
                addUserMessage(val);
                chatInput.innerHTML = "";
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

        // --- SINGLE GLOBAL CAPTURING PASTE INTERCEPTOR ---
        document.addEventListener('paste', function(e) {
            const clipboardData = e.clipboardData || window.clipboardData;
            if (!clipboardData) return;
            
            let imageFound = false;
            
            if (clipboardData.files && clipboardData.files.length > 0) {
                for (let file of clipboardData.files) {
                    if (file.type.startsWith('image/')) {
                        imageFound = true;
                        e.preventDefault();
                        e.stopPropagation();
                        processImageFile(file);
                        break;
                    }
                }
            }
            
            if (!imageFound && clipboardData.items) {
                for (let item of clipboardData.items) {
                    if (item.type.indexOf('image') !== -1 || item.kind === 'file') {
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
        }, true);

        function processImageFile(file) {
            const reader = new FileReader();
            reader.onload = function(event) {
                addUserImageMessage(event.target.result);
                processOcrQuery(event.target.result);
            };
            reader.readAsDataURL(file);
        }

        btnCloseSidebar.addEventListener('click', () => {
            sidebar.classList.add('closed');
        });

        function addUserMessage(text) {
            const msg = document.createElement('div');
            msg.className = 'message user';
            msg.innerHTML = `
                <div class="message-meta">👤 You</div>
                <div class="message-content">${escapeHtml(text)}</div>
            `;
            messagesList.appendChild(msg);
            scrollChat();
        }

        function addUserImageMessage(base64Image) {
            const msg = document.createElement('div');
            msg.className = 'message user';
            msg.innerHTML = `
                <div class="message-meta">👤 Uploaded Screenshot</div>
                <div class="message-content">
                    <img src="${base64Image}" class="msg-image-preview" alt="Screenshot">
                </div>
            `;
            messagesList.appendChild(msg);
            scrollChat();
        }

        function addBotLoadingMessage(text="Analyzing...") {
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

        function showToast(message, type="success") {
            toast.textContent = message;
            if (type === "warning") {
                toast.style.background = "#ef4444";
            } else {
                toast.style.background = "var(--accent)";
            }
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
            addBotLoadingMessage("Analyzing video...");
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
                    addBotSimpleResponse(`Error: ${data.message}`);
                }
            } catch (e) {
                removeLoader();
                addBotSimpleResponse("Failed to connect to the server.");
            }
        }

        async function processOcrQuery(base64Image) {
            addBotLoadingMessage("Scanning image for videos and matching transcripts...");
            try {
                const response = await fetch('/api/ocr', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({ image: base64Image })
                });
                
                // Always update rate limit banner status
                await updateRateLimitBanner();

                if (response.status === 429) {
                    removeLoader();
                    addBotSimpleResponse("Action Banned: Too many image upload requests. You have been banned for 5 minutes. IP Ban 5 min is active.");
                    return;
                }

                const data = await response.json();
                removeLoader();

                if (data.status === 'success') {
                    // Cache all pre-fetched transcripts into memory
                    data.results.forEach(vid => {
                        if (vid.transcript) {
                            loadedTranscripts[vid.video_id] = vid.transcript;
                        }
                    });
                    addBotVideoResponse(data.results);
                } else {
                    addBotSimpleResponse(`Scan finished but an issue occurred: ${data.message}`);
                }
            } catch (e) {
                removeLoader();
                addBotSimpleResponse("Screenshot OCR processing failed.");
                await updateRateLimitBanner();
            }
        }

        function addBotSimpleResponse(text) {
            const msg = document.createElement('div');
            msg.className = 'message bot';
            msg.innerHTML = `
                <div class="message-meta">🤖 Transkriptor Assistant</div>
                <div class="message-content">${escapeHtml(text)}</div>
            `;
            messagesList.appendChild(msg);
            scrollChat();
        }

        function addBotVideoResponse(videos) {
            const msg = document.createElement('div');
            msg.className = 'message bot';
            
            let videosHtml = "";
            videos.forEach((vid, idx) => {
                const safeTitle = escapeHtml(vid.title);
                videosHtml += `
                    <div class="video-card">
                        <div class="video-thumb-container">
                            <img src="${vid.thumbnail}" alt="Thumbnail">
                        </div>
                        <div class="video-info">
                            <div class="video-title" title="${safeTitle}">${safeTitle}</div>
                            <div class="video-channel">👤 ${escapeHtml(vid.author)}</div>
                            <div class="video-actions">
                                <button class="btn-card primary" onclick="copyTranscriptDirectly('${vid.video_id}')">
                                    📋 Copy
                                </button>
                                <button class="btn-card" onclick="openTranscriptSidebar('${vid.video_id}', '${encodeURIComponent(vid.title)}')">
                                    🔍 Detail
                                </button>
                            </div>
                        </div>
                    </div>
                `;
            });

            msg.innerHTML = `
                <div class="message-meta">🤖 Transkriptor Assistant</div>
                <div class="message-content">
                    I found and matched <strong>${videos.length} video(s)</strong> from your screenshot:
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
                showToast("Transcript not found in cache!", "warning");
                return;
            }
            
            try {
                const fullText = transcript.map(l => l.text).join(' ');
                await navigator.clipboard.writeText(fullText);
                showToast("Transcript copied to clipboard successfully!");
            } catch (e) {
                const success = fallbackCopyTextToClipboard(transcript.map(l => l.text).join(' '));
                if (!success) {
                    showToast("Clipboard access error! Please copy from the 'Detail' panel.", "warning");
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

        window.openTranscriptSidebar = function(videoId, encodedTitle) {
            activeVideoTitle = decodeURIComponent(encodedTitle);
            sidebarTitle.textContent = activeVideoTitle;
            sidebar.classList.remove('closed');

            const transcript = loadedTranscripts[videoId];
            if (transcript) {
                activeTranscript = transcript;
                renderSidebarLines(transcript, videoId);
            } else {
                sidebarLines.innerHTML = `<div style='color:#ef4444'>Transcript not found in cache!</div>`;
            }
        };

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
            showToast("Full transcript copied!");
        });

        btnDownloadTranscriptTxt.addEventListener('click', () => {
            if (!activeTranscript.length) return;
            let output = "";
            activeTranscript.forEach(l => {
                output += `[${formatTime(l.start)}] ${l.text}\n`;
            });
            const filename = `${activeVideoTitle.replace(/[^a-z0-9]/gi, '_').toLowerCase()}_transcript.txt`;
            
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
        url = "https://raw.githubusercontent.com/TheSpeedX/SOCKS-List/master/http.txt"
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
    import socket
    import random
    
    # Store original timeout to restore it later
    orig_timeout = socket.getdefaulttimeout()
    socket.setdefaulttimeout(3) # Set 3s timeout for fast proxy testing
    
    print(f"Attempting proxy rotation fallback for transcript of {video_id}...")
    try:
        url = "https://raw.githubusercontent.com/TheSpeedX/SOCKS-List/master/http.txt"
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
    
    # Try all proxies in the list (unlimited)
    for idx, proxy_ip in enumerate(proxies_list, 1):
        proxy_url = f"http://{proxy_ip}"
        proxies_config = {'http': proxy_url, 'https': proxy_url}
        try:
            session = requests.Session()
            session.proxies = proxies_config
            api = YouTubeTranscriptApi(http_client=session)
            transcript_data = api.fetch(video_id, languages=('tr', 'en'))
            if transcript_data:
                print(f"SUCCESS! Retrieved transcript using proxy {proxy_url}!")
                
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
            # Silent fallback
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
        ydl_opts = {'quiet': True, 'skip_download': True}
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
    
    if not image_base64:
        return jsonify({'status': 'error', 'message': 'Could not retrieve image data!'})
        
    try:
        if ',' in image_base64:
            image_base64 = image_base64.split(',')[1]
            
        payload = {
            'base64Image': f"data:image/png;base64,{image_base64}",
            'language': 'eng',
            'isOverlayRequired': False,
            'OCREngine': '2',
            'detectOrientation': 'true',
            'scale': 'true'
        }
        
        api_key = os.environ.get('OCR_API_KEY', 'helloworld')
        headers = {'apikey': api_key}
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

