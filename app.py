import json
import os
import ssl
import urllib.request
import threading
import time
from datetime import datetime
from flask import Flask, render_template, jsonify, request
from deep_translator import GoogleTranslator

# Configuration
API_URL = 'https://huggingface.co/api/daily_papers'

app = Flask(__name__)

# In-memory store (no local file)
papers_store = []
store_lock = threading.Lock()

# --- Data Fetching and Translation (ALL papers, no filtering) ---
def translate_text(text, max_len=1500):
    """Translate English text to Chinese, with retry and rate-limit protection."""
    if not text:
        return text
    truncated = text[:max_len]
    for attempt in range(3):
        try:
            result = GoogleTranslator(source='auto', target='zh-CN').translate(truncated)
            time.sleep(0.5)  # Rate-limit: small delay between calls
            return result
        except Exception as e:
            if attempt < 2:
                time.sleep(2 * (attempt + 1))  # Exponential backoff
            else:
                print(f"Translation failed after 3 attempts: {e}")
                return text

def fetch_all_papers():
    """Fetch ALL trending papers from Hugging Face and translate them."""
    print("Background Task: Fetching ALL trending papers from Hugging Face...")
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    req = urllib.request.Request(API_URL, headers={'User-Agent': 'Mozilla/5.0'})
    
    results = []
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=20) as response:
            papers = json.loads(response.read().decode())
            total = len(papers)
            print(f"Fetched {total} papers. Starting translation...")
            
            for i, p in enumerate(papers):
                paper = p.get('paper', {})
                eng_title = paper.get('title', '')
                eng_summary = paper.get('summary', '')
                paper_id = paper.get('id', '')
                url = f"https://huggingface.co/papers/{paper_id}"
                
                # Detect domain tags automatically
                text_lower = (eng_title + " " + eng_summary).lower()
                domain_keywords = {
                    '机器人': ['robot', 'robotics', 'manipulation', 'grasp'],
                    '物流': ['logistics', 'warehouse', 'supply chain', 'delivery'],
                    '自动驾驶': ['autonomous driving', 'self-driving', 'vehicle'],
                    '具身智能': ['embodied', 'embodiment'],
                    '导航': ['navigation', 'path planning', 'slam'],
                    '强化学习': ['reinforcement learning', 'rl', 'reward'],
                    '视觉': ['vision', 'visual', 'image', 'video'],
                    '语言模型': ['language model', 'llm', 'nlp', 'text'],
                    '多模态': ['multimodal', 'multi-modal'],
                    '扩散模型': ['diffusion', 'denoising'],
                    '生成式AI': ['generative', 'generation', 'gan'],
                    '3D': ['3d', 'point cloud', 'mesh', 'nerf'],
                    '医疗': ['medical', 'clinical', 'health', 'biomedical'],
                    '语音': ['speech', 'audio', 'voice'],
                    '安全': ['safety', 'security', 'adversarial', 'red-team'],
                    '智能体': ['agent', 'agentic', 'tool use'],
                }
                matched_tags = []
                for zh_tag, en_keywords in domain_keywords.items():
                    if any(kw in text_lower for kw in en_keywords):
                        matched_tags.append(zh_tag)
                if not matched_tags:
                    matched_tags = ['综合']
                
                # Translate
                zh_title = translate_text(eng_title)
                zh_summary = translate_text(eng_summary, 1500)
                
                results.append({
                    'title': zh_title,
                    'eng_title': eng_title,
                    'summary': zh_summary,
                    'eng_summary': eng_summary,
                    'url': url,
                    'matched_keywords': matched_tags,
                    'date_scraped': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                })
                
                print(f"  [{i+1}/{total}] Translated: {eng_title[:60]}...")
                
    except Exception as e:
        print(f"Error fetching data: {e}")
    
    return results

def background_scraper():
    """Background thread: fetch all papers and store in memory."""
    global papers_store
    data = fetch_all_papers()
    with store_lock:
        papers_store = data
    print(f"Done! {len(data)} papers loaded into memory.")

# Fire background job on startup
thread = threading.Thread(target=background_scraper)
thread.daemon = True
thread.start()

# --- Routes ---
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/papers', methods=['GET'])
def api_papers():
    with store_lock:
        return jsonify(papers_store)

@app.route('/api/refresh', methods=['POST'])
def api_refresh():
    """Manually trigger a re-scrape."""
    t = threading.Thread(target=background_scraper)
    t.daemon = True
    t.start()
    return jsonify({'status': 'ok', 'message': '后台已重新启动抓取翻译进程，请稍后刷新页面查看最新数据。'})

@app.route('/api/chat', methods=['POST'])
def api_chat():
    user_message = request.json.get('message', '').strip()
    
    with store_lock:
        papers = list(papers_store)

    if not user_message:
        return jsonify({'response': "请输入您感兴趣的关键词或话题，我会为您在全库中检索相关文献。"})

    query_lower = user_message.lower()
    matched_papers = []
    
    # Match against all fields
    for p in papers:
        score = 0
        searchable = (
            p['title'] + ' ' + p['summary'] + ' ' +
            p.get('eng_title', '') + ' ' + p.get('eng_summary', '') + ' ' +
            ' '.join(p['matched_keywords'])
        ).lower()
        
        # Split query into individual words/chars for flexible matching
        query_tokens = [w for w in query_lower.split() if len(w) >= 1]
        
        for token in query_tokens:
            if token in searchable:
                score += 1
        
        # Also check for broad intent
        if any(kw in query_lower for kw in ['所有', '全部', '最新', '列表']):
            score += 1
            
        if score > 0:
            matched_papers.append((score, p))
    
    # Sort by relevance score
    matched_papers.sort(key=lambda x: x[0], reverse=True)
    matched_papers = [p for _, p in matched_papers]

    if not matched_papers:
        return jsonify({'response': f'在当前 {len(papers)} 篇文献库中，没有找到与 "{user_message}" 相关的论文。您可以尝试换一个关键词（如"视觉"、"机器人"、"强化学习"、"扩散模型"等）。'})

    top = matched_papers[:5]
    
    greeting = f"📚 在全库 {len(papers)} 篇论文中，为您匹配到 <strong>{len(matched_papers)}</strong> 篇相关成果！以下为最相关的几篇：<br><br>"
    links_html = ""
    for i, p in enumerate(top):
        tags_str = ' '.join([f'<span style="background:rgba(139,92,246,0.3);padding:2px 8px;border-radius:10px;font-size:0.75em;margin-right:4px;">{t}</span>' for t in p['matched_keywords']])
        links_html += f"""<div style="margin-bottom:12px;padding:10px;background:rgba(255,255,255,0.05);border-radius:10px;">
            <strong>{i+1}. <a href='{p['url']}' target='_blank' style='color:#38bdf8;text-decoration:none;'>{p['title']}</a></strong><br>
            <span style='font-size:0.8em;color:#64748b;font-style:italic;'>{p.get('eng_title','')}</span><br>
            <div style="margin:5px 0;">{tags_str}</div>
            <span style='font-size:0.85em;color:#94a3b8;'>{p['summary'][:80]}...</span>
        </div>"""
    
    if len(matched_papers) > 5:
        links_html += f"<br><i style='color:#64748b;'>还有 {len(matched_papers) - 5} 篇由于篇幅限制未展示，您可以使用更精确的关键词缩小范围。</i>"

    return jsonify({'response': greeting + links_html})

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    print("=" * 60)
    print("  RoboLogistics AI Dashboard Server (本地 & 云端兼容模式)")
    print(f"  服务已启动在 0.0.0.0:{port}")
    print("  按 Ctrl+C 停止服务器")
    print("=" * 60)
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)
