from flask import Flask, render_template, request, jsonify, redirect, url_for, flash, session, make_response
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta
import requests
from bs4 import BeautifulSoup
from pytube import YouTube
import os
from urllib.parse import urlparse
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from werkzeug.security import generate_password_hash, check_password_hash
from flask_cors import CORS

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///bookmarks.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = os.urandom(24)  # For session management
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=30)  # Cookie expires in 30 days
CORS(app, resources={r"/*": {"origins": "*"}})  # Enable CORS for all routes
db = SQLAlchemy(app)

# YouTube API setup
YOUTUBE_API_KEY = 'YOUR_API_KEY'  # You'll need to replace this with your actual API key
youtube = build('youtube', 'v3', developerKey=YOUTUBE_API_KEY)

# API key for extension authentication
EXTENSION_API_KEY = "your-secret-api-key-123"  # Change this to a secure key

# Simple user model
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(120), nullable=False)

class Bookmark(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    url = db.Column(db.String(500), nullable=False)
    title = db.Column(db.String(200))
    thumbnail = db.Column(db.String(500))
    type = db.Column(db.String(20))  # 'url', 'youtube', 'article', 'note'
    note = db.Column(db.Text)
    completed = db.Column(db.Boolean, default=False)
    favicon = db.Column(db.String(500))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'url': self.url,
            'title': self.title,
            'thumbnail': self.thumbnail,
            'type': self.type,
            'note': self.note,
            'completed': self.completed,
            'favicon': self.favicon,
            'created_at': self.created_at.isoformat()
        }

def extract_video_id(url):
    """Extract video ID from various YouTube URL formats."""
    if 'youtube.com/watch?v=' in url:
        return url.split('youtube.com/watch?v=')[1].split('&')[0]
    elif 'youtu.be/' in url:
        return url.split('youtu.be/')[1].split('?')[0]
    return None

def get_youtube_info(url):
    try:
        video_id = extract_video_id(url)
        if not video_id:
            return None

        # Get the video page
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        response = requests.get(url, headers=headers)
        soup = BeautifulSoup(response.text, 'html.parser')

        # Try to get title from meta tags
        title = None
        for meta in soup.find_all('meta'):
            if meta.get('property') == 'og:title':
                title = meta.get('content')
                break
            elif meta.get('name') == 'title':
                title = meta.get('content')
                break

        # If no title found in meta tags, try to get it from the page title
        if not title:
            title_tag = soup.find('title')
            if title_tag:
                title = title_tag.text.strip()
                # Remove " - YouTube" from the end if present
                if title.endswith(' - YouTube'):
                    title = title[:-10]

        # Get thumbnail URL
        thumbnail_url = None
        for meta in soup.find_all('meta'):
            if meta.get('property') == 'og:image':
                thumbnail_url = meta.get('content')
                break

        # If no thumbnail found in meta tags, use the default YouTube thumbnail URL
        if not thumbnail_url and video_id:
            thumbnail_url = f"https://img.youtube.com/vi/{video_id}/maxresdefault.jpg"

        return {
            'title': title or f"YouTube Video ({video_id})",
            'thumbnail': thumbnail_url,
            'type': 'youtube'
        }
    except Exception as e:
        print(f"Error getting YouTube info: {str(e)}")
        # Fallback with just the video ID
        video_id = extract_video_id(url)
        if video_id:
            return {
                'title': f"YouTube Video ({video_id})",
                'thumbnail': f"https://img.youtube.com/vi/{video_id}/maxresdefault.jpg",
                'type': 'youtube'
            }
        return {
            'title': "YouTube Video",
            'thumbnail': None,
            'type': 'youtube'
        }

def get_url_info(url):
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        title = soup.title.string if soup.title else url
        favicon = None
        domain = urlparse(url).netloc
        
        # Try to find favicon
        favicon_link = soup.find('link', rel=lambda x: x and ('icon' in x.lower() or 'shortcut' in x.lower()))
        if favicon_link and favicon_link.get('href'):
            favicon = favicon_link['href']
            if not favicon.startswith('http'):
                if favicon.startswith('//'):
                    favicon = 'https:' + favicon
                elif favicon.startswith('/'):
                    favicon = f'https://{domain}{favicon}'
                else:
                    favicon = f'https://{domain}/{favicon}'
        
        if not favicon:
            favicon = f'https://{domain}/favicon.ico'
            
        return {
            'title': title,
            'favicon': favicon,
            'type': 'url'
        }
    except:
        return None

def get_article_info(url):
    try:
        response = requests.get(url)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Get title
        title = None
        og_title = soup.find('meta', property='og:title')
        if og_title:
            title = og_title['content']
        else:
            title_tag = soup.find('title')
            if title_tag:
                title = title_tag.text.strip()
        
        # Get image
        image = None
        og_image = soup.find('meta', property='og:image')
        if og_image:
            image = og_image['content']
        else:
            # Try to find the first large image in the article
            images = soup.find_all('img')
            for img in images:
                if img.get('src') and (img.get('width', '0').isdigit() and int(img.get('width', '0')) > 200) or \
                   (img.get('height', '0').isdigit() and int(img.get('height', '0')) > 200):
                    image = img['src']
                    if not image.startswith('http'):
                        # Handle relative URLs
                        base_url = urlparse(url)
                        image = f"{base_url.scheme}://{base_url.netloc}{image}"
                    break
        
        return {
            'title': title or url,
            'image': image
        }
    except Exception as e:
        print(f"Error fetching article info: {e}")
        return None

# Create tables
with app.app_context():
    db.create_all()

# Create default user if none exists
def create_default_user():
    with app.app_context():
        if not User.query.first():
            default_user = User(
                username='admin',
                password_hash=generate_password_hash('admin123')
            )
            db.session.add(default_user)
            db.session.commit()

create_default_user()

@app.route('/')
def index():
    query = request.args.get('q', '')
    if query:
        # Check if the query is a domain
        if any(query.endswith(ext) for ext in ['.com', '.org', '.net', '.io', '.edu', '.gov', '.me', '.info']) or query == 'youtube.com':
            # Try to match the domain exactly first
            bookmarks = Bookmark.query.filter(
                (Bookmark.url.like(f'%{query}%')) |
                (Bookmark.url.like(f'%{query.replace(".com", "")}%'))
            ).order_by(Bookmark.created_at.desc()).all()
            
            # If no exact matches, try to match the domain without www
            if not bookmarks and query.startswith('www.'):
                bookmarks = Bookmark.query.filter(
                    Bookmark.url.like(f'%{query[4:]}%')
                ).order_by(Bookmark.created_at.desc()).all()
        else:
            bookmarks = Bookmark.query.filter(
                (Bookmark.title.ilike(f'%{query}%')) |
                (Bookmark.note.ilike(f'%{query}%'))
            ).order_by(Bookmark.created_at.desc()).all()
    else:
        bookmarks = Bookmark.query.order_by(Bookmark.created_at.desc()).all()
    return render_template('index.html', bookmarks=bookmarks, urlparse=urlparse, is_authenticated=session.get('authenticated', False))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        remember = request.form.get('remember') == 'on'
        
        user = User.query.filter_by(username=username).first()
        
        if user and check_password_hash(user.password_hash, password):
            session['authenticated'] = True
            session['username'] = username
            session.permanent = remember  # Set session to permanent if "remember me" is checked
            
            response = make_response(redirect(url_for('index')))
            if remember:
                # Set a secure cookie that expires in 30 days
                response.set_cookie('remember_token', 
                                  value=generate_password_hash(username),
                                  max_age=30*24*60*60,  # 30 days in seconds
                                  httponly=True,
                                  secure=True)
            return response
        else:
            return render_template('login.html', error='Invalid username or password')
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('authenticated', None)
    session.pop('username', None)
    response = make_response(redirect(url_for('index')))
    response.delete_cookie('remember_token')
    return response

@app.before_request
def before_request():
    # Check for remember me cookie
    if not session.get('authenticated') and request.cookies.get('remember_token'):
        # Validate the remember token and log the user in
        username = session.get('username')
        if username:
            user = User.query.filter_by(username=username).first()
            if user:
                session['authenticated'] = True
                session.permanent = True

@app.route('/add', methods=['POST'])
def add_bookmark():
    # Check for API key in headers (extension) or session (website)
    api_key = request.headers.get('X-API-Key')
    if not api_key or api_key != EXTENSION_API_KEY:
        if not session.get('authenticated'):
            return jsonify({'error': 'Authentication required'}), 401
    
    # Handle both JSON and form data
    if request.is_json:
        data = request.json
    else:
        data = request.form
    
    url = data.get('url', '').strip()
    note = data.get('note', '').strip()
    
    if not url:
        return jsonify({'error': 'URL is required'}), 400
    
    # Check if it's a YouTube URL
    if 'youtube.com' in url or 'youtu.be' in url:
        info = get_youtube_info(url)
        if info:
            bookmark = Bookmark(
                url=url,
                title=info['title'],
                thumbnail=info['thumbnail'],
                note=note
            )
        else:
            bookmark = Bookmark(url=url, note=note)
    else:
        # Try to get article info
        info = get_article_info(url)
        if info:
            bookmark = Bookmark(
                url=url,
                title=info['title'],
                thumbnail=info['image'],
                note=note
            )
        else:
            bookmark = Bookmark(url=url, note=note)
    
    db.session.add(bookmark)
    db.session.commit()
    
    if request.is_json:
        return jsonify({'message': 'Bookmark added successfully'}), 201
    else:
        return redirect(url_for('index'))

@app.route('/toggle/<int:id>', methods=['POST'])
def toggle_bookmark(id):
    if not session.get('authenticated'):
        return redirect(url_for('login'))
        
    bookmark = Bookmark.query.get_or_404(id)
    bookmark.completed = not bookmark.completed
    db.session.commit()
    return jsonify({'success': True})

@app.route('/delete/<int:id>', methods=['DELETE'])
def delete_bookmark(id):
    if not session.get('authenticated'):
        return redirect(url_for('login'))
        
    bookmark = Bookmark.query.get_or_404(id)
    db.session.delete(bookmark)
    db.session.commit()
    return jsonify({'success': True})

if __name__ == '__main__':
    app.run(debug=True) 