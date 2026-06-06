# Deploying Transkriptor Chat to Render

I have configured the project files for deployment. Here is the simple step-by-step guide to publishing your website online:

## Step 1: Create a GitHub Repository
1. Go to [GitHub](https://github.com/) and create a new private or public repository (e.g. named `transkriptor-chat`).
2. Upload the files inside the `transkriptor-chat-app` folder (especially `app.py` and `requirements.txt`) to this repository.

## Step 2: Deploy to Render
1. Go to [Render](https://render.com/) and sign up for a free account.
2. Click **New +** and select **Web Service**.
3. Connect your GitHub account and select your `transkriptor-chat` repository.
4. Configure the Web Service settings:
   - **Name:** `transkriptor-chat` (or any name you prefer)
   - **Runtime:** `Python`
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `gunicorn app:app`
   - **Instance Type:** `Free`
5. Click **Deploy Web Service**.

Render will build the application and provide you with a live public URL (e.g., `https://transkriptor-chat.onrender.com`).
