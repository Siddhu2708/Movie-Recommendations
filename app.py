import streamlit as st
import pandas as pd
import requests
import pickle
import random
import ast
import json
import os
import time as _time
import urllib3
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Suppress InsecureRequestWarning caused by Windows TLS reset (WinError 10054)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ─────────────────────────────────────────────
#  Page Config
# ─────────────────────────────────────────────
st.set_page_config(
    page_title="MovieMind",
    page_icon="🎬",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─────────────────────────────────────────────
#  Global CSS
# ─────────────────────────────────────────────
st.markdown("""
<style>
    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, #0d1b2a 0%, #1b2838 100%);
    }
    [data-testid="stSidebar"] p,
    [data-testid="stSidebar"] span,
    [data-testid="stSidebar"] label { color: #e0e0e0 !important; }

    .stButton > button { border-radius: 10px; font-weight: 600; transition: all 0.2s; }

    /* Movie card */
    .movie-card { text-align: center; padding: 4px 2px; }
    .movie-title {
        font-weight: 700;
        font-size: 15px;
        margin: 8px 0 4px 0;
        line-height: 1.4;
        color: #f0f0f0;
    }
    .movie-genre {
        font-size: 13px;
        color: #f0a500;
        font-weight: 600;
        margin: 0;
        line-height: 1.5;
    }

    /* Search result list feel */
    .search-hint {
        font-size: 13px;
        color: #888;
        padding: 10px 0;
    }

    /* Chat bubbles */
    .user-bubble {
        background: #1e3a5f;
        padding: 10px 14px;
        border-radius: 16px 16px 4px 16px;
        margin: 8px 0 8px auto;
        max-width: 78%;
        color: #fff;
        width: fit-content;
    }
    .bot-bubble {
        background: #1b2838;
        border: 1px solid #2a3f5f;
        padding: 10px 14px;
        border-radius: 16px 16px 16px 4px;
        margin: 8px auto 8px 0;
        max-width: 78%;
        color: #e0e0e0;
        width: fit-content;
    }
    .chat-label { font-size: 10px; color: #888; margin-bottom: 3px; }
    .chat-label-right { font-size: 10px; color: #6aa3d5; margin-bottom: 3px; text-align: right; }
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────
#  Load Data
# ─────────────────────────────────────────────
@st.cache_resource(show_spinner="Loading movie library…")
def load_data():
    with open('movie_data.pkl', 'rb') as f:
        movies, cosine_sim = pickle.load(f)
    return movies, cosine_sim

@st.cache_resource(show_spinner=False)
def load_genre_map():
    """Build a movie_id → genre string map from local CSV (no API needed)."""
    try:
        df = pd.read_csv('tmdb_5000_movies.csv', usecols=['id', 'genres'])
        genre_map = {}
        for _, row in df.iterrows():
            try:
                genres = [g['name'] for g in ast.literal_eval(row['genres'])]
                genre_map[int(row['id'])] = " · ".join(genres[:3]) if genres else "—"
            except Exception:
                genre_map[int(row['id'])] = "—"
        return genre_map
    except Exception:
        return {}

movies, cosine_sim = load_data()
genre_map = load_genre_map()

def get_local_genre(movie_id: int) -> str:
    return genre_map.get(int(movie_id), "—")


BEARER_TOKEN    = ('eyJhbGciOiJIUzI1NiJ9.eyJhdWQiOiJhNjhiNmMwYmNmYTYyYTM0NWRjMWRhMmM3NThmOGYzNS'
                   'IsIm5iZiI6MTc5MTM4NjEzNi44MjUsInN1YiI6IjZhYzY2MjE4OWE2YTI2ZWY0Y2JkN2Q5NSIsIn'
                   'Njb3BlcyI6WyJhcGlfcmVhZCJdLCJ2ZXJzaW9uIjoxfQ.OsoWRfykzZHZ_8WcEIAKQtp8p0jm0BW'
                   'mfuHTvU1mmzk')
TMDB_HEADERS    = {"Authorization": f"Bearer {BEARER_TOKEN}", "accept": "application/json"}
TMDB_IMG_BASE   = "https://image.tmdb.org/t/p/w500"
PLACEHOLDER_IMG = "https://placehold.co/300x450/1b2838/e0e0e0?text=No+Poster"
POSTER_CACHE_FILE = "poster_cache.json"

# ── Persistent disk cache ──────────────────────
def _load_disk_cache() -> dict:
    if os.path.exists(POSTER_CACHE_FILE):
        try:
            with open(POSTER_CACHE_FILE, "r") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def _save_disk_cache(cache: dict):
    try:
        with open(POSTER_CACHE_FILE, "w") as f:
            json.dump(cache, f)
    except Exception:
        pass

if "poster_cache" not in st.session_state:
    st.session_state.poster_cache = _load_disk_cache()

def fetch_poster(movie_id: int) -> str:
    """Fetch poster URL — checks local disk cache first, then TMDB API. Never raises."""
    key = str(movie_id)

    # 1. In-memory + disk cache hit
    if key in st.session_state.poster_cache:
        return st.session_state.poster_cache[key]

    url = f"https://api.themoviedb.org/3/movie/{movie_id}"

    # 2. Try up to 4 times with a fresh session each attempt
    for attempt in range(4):
        try:
            s = requests.Session()
            s.headers.update(TMDB_HEADERS)
            resp = s.get(url, timeout=10, verify=False)
            resp.raise_for_status()
            path = resp.json().get("poster_path")
            result = f"{TMDB_IMG_BASE}{path}" if path else PLACEHOLDER_IMG

            # Save to cache on success
            st.session_state.poster_cache[key] = result
            _save_disk_cache(st.session_state.poster_cache)
            return result

        except Exception:
            if attempt < 3:
                _time.sleep(1.5 * (attempt + 1))   # 1.5s, 3s, 4.5s between retries

    # All retries failed → placeholder (not cached, will retry next time)
    return PLACEHOLDER_IMG


# ─────────────────────────────────────────────
#  Recommendation engine
# ─────────────────────────────────────────────
def get_recommendations(title: str) -> pd.DataFrame:
    try:
        idx     = movies[movies['title'] == title].index[0]
        scores  = sorted(enumerate(cosine_sim[idx]), key=lambda x: x[1], reverse=True)
        indices = [i[0] for i in scores[1:11]]
        return movies[['title', 'movie_id']].iloc[indices]
    except Exception as e:
        st.error(f"Recommendation error: {e}")
        return pd.DataFrame(columns=['title', 'movie_id'])

# ─────────────────────────────────────────────
#  MILI Chatbot
# ─────────────────────────────────────────────
GENRE_KEYWORDS = {
    'action':    ["action", "fight", "explosion", "superhero", "war", "combat"],
    'comedy':    ["comedy", "funny", "laugh", "humor", "hilarious", "comic"],
    'drama':     ["drama", "emotional", "serious", "intense", "powerful"],
    'horror':    ["horror", "scary", "fear", "ghost", "spooky", "creepy", "terror"],
    'romance':   ["romance", "love", "romantic", "relationship", "couple"],
    'sci-fi':    ["sci-fi", "science fiction", "space", "alien", "future", "robot", "scifi"],
    'animation': ["animation", "animated", "cartoon", "pixar", "disney"],
    'crime':     ["crime", "detective", "mystery", "murder", "heist"],
    'fantasy':   ["fantasy", "magic", "wizard", "dragon", "mythical"],
    'adventure': ["adventure", "journey", "quest", "explore"],
    'thriller':  ["thriller", "suspense", "tense", "tension"],
}
GENRE_PICKS = {
    'action':    ["The Dark Knight", "Mad Max: Fury Road", "John Wick", "Avengers: Age of Ultron"],
    'comedy':    ["The Grand Budapest Hotel", "Superbad", "Home Alone", "Bridesmaids"],
    'drama':     ["The Shawshank Redemption", "Forrest Gump", "Schindler's List"],
    'horror':    ["Get Out", "The Conjuring", "Hereditary", "A Quiet Place"],
    'romance':   ["Titanic", "La La Land", "Crazy Rich Asians", "Pride & Prejudice"],
    'sci-fi':    ["Inception", "Interstellar", "The Matrix", "Arrival"],
    'animation': ["Coco", "Spider-Man: Into the Spider-Verse", "Up", "WALL-E"],
    'crime':     ["Pulp Fiction", "The Godfather", "Heat", "No Country for Old Men"],
    'fantasy':   ["The Lord of the Rings", "Harry Potter and the Sorcerer's Stone"],
    'adventure': ["Indiana Jones", "Jurassic Park", "Pirates of the Caribbean"],
    'thriller':  ["Gone Girl", "Prisoners", "Zodiac", "Se7en"],
}

def mili_response(user_input: str) -> str:
    inp = user_input.lower().strip()

    if any(w in inp for w in ['hi','hello','hey','hola','howdy','sup','good morning','good evening']):
        return ("Hey there! I'm **MILI** 🎬, your MovieMind AI companion!\n\n"
                "🎥 *'Movies like Inception'* → Similar recs\n"
                "🎭 *'Suggest a comedy'* → Genre picks\n"
                "⭐ *'Best movies tonight'* → Top picks\n"
                "🎲 *'Surprise me'* → Random pick!\n\nWhat are you in the mood for? 🍿")

    if any(w in inp for w in ['help','what can you do','features']):
        return ("🤖 **MILI's Capabilities:**\n\n"
                "🎬 *'Movies like Inception'* → Similar recommendations\n"
                "🎭 *'I want a thriller'* → Genre-based picks\n"
                "⭐ *'Best movies'* → Top suggestions\n"
                "😢 *'I feel sad'* → Mood-based picks\n"
                "🎲 *'Surprise me'* → Random movie!")

    if any(w in inp for w in ['thank','thanks','ty','great','awesome','cool','nice','perfect']):
        return random.choice([
            "😊 Happy to help! Enjoy the film! 🍿",
            "🎬 You're welcome! Come back anytime!",
            "⭐ You've got great taste — happy watching!",
        ])

    if any(w in inp for w in ['surprise me','random','anything','idk','whatever']):
        pick = movies['title'].sample(1).values[0]
        return f"🎲 How about **{pick}**?\n\nSearch it in the Recommendation tab to find 10 movies just like it! 🍿"

    if any(w in inp for w in ['sad','crying','bored','depressed','lonely']):
        return ("🥺 Sounds like you need a feel-good movie!\n\n"
                "• **Forrest Gump**\n• **The Secret Life of Walter Mitty**\n"
                "• **Chef**\n• **Paddington**\n\nThey'll lift your spirits! 💛")

    if any(w in inp for w in ['excited','pumped','adrenaline','hype','hyped']):
        return ("⚡ You want something electric!\n\n"
                "• **Mad Max: Fury Road**\n• **John Wick**\n"
                "• **Top Gun: Maverick**\n• **Mission: Impossible – Fallout**\n\nBuckle up! 🔥")

    for genre, keywords in GENRE_KEYWORDS.items():
        if any(k in inp for k in keywords):
            picks = "\n".join([f"• {p}" for p in GENRE_PICKS.get(genre, [])])
            return (f"🎭 Great taste! Top **{genre.title()}** picks:\n\n{picks}\n\n"
                    f"💡 Search any of these in the **Recommendation** tab for 10 more like it!")

    matched = None
    for title in movies['title'].values:
        if title.lower() in inp or (len(inp) > 4 and inp in title.lower()):
            matched = title
            break
    if matched:
        recs = get_recommendations(matched)
        if not recs.empty:
            rec_list = "\n".join([f"• {r}" for r in recs['title'].values[:5]])
            return (f"🍿 Since you like **{matched}**, you'll love:\n\n{rec_list}\n\n"
                    f"Search it in the **Recommendation** tab to see all 10 with posters! 🎬")

    if any(w in inp for w in ['best','top','greatest','tonight','today','what to watch','recommend']):
        samples = movies['title'].sample(min(5, len(movies))).tolist()
        return ("⭐ **Tonight's MovieMind Picks:**\n\n"
                + "\n".join([f"• {m}" for m in samples])
                + "\n\nSearch any in the Recommendation tab for 10 more like it! 🎬")

    return ("🤔 I didn't quite catch that! Try:\n\n"
            "• *'Recommend a thriller'*\n"
            "• *'Movies like The Dark Knight'*\n"
            "• *'What should I watch tonight?'*\n"
            "• *'Surprise me!'*\n\nKeep chatting! 🎬")

# ─────────────────────────────────────────────
#  Session State
# ─────────────────────────────────────────────
if 'page' not in st.session_state:
    st.session_state.page = 'recommendation'
if 'chat_history' not in st.session_state:
    st.session_state.chat_history = []
if 'selected_movie' not in st.session_state:
    st.session_state.selected_movie = None

# ─────────────────────────────────────────────
#  SIDEBAR
# ─────────────────────────────────────────────
with st.sidebar:
    col_l, col_m, col_r = st.columns([1, 3, 1])
    with col_m:
        try:
            st.image("logo.jpg", width=160)
        except Exception:
            st.markdown("<h1 style='text-align:center'>🎬</h1>", unsafe_allow_html=True)

    st.markdown(
        "<h2 style='text-align:center;color:#f0a500;margin:0 0 2px 0;'>MovieMind</h2>"
        "<p style='text-align:center;font-size:11px;color:#888;margin:0;'>AI-Powered Movie Discovery</p>",
        unsafe_allow_html=True,
    )
    st.markdown("---")

    is_rec  = st.session_state.page == 'recommendation'
    is_chat = st.session_state.page == 'chatbot'

    if st.button("🎥  Recommendation", use_container_width=True,
                 type="primary" if is_rec else "secondary", key="nav_rec"):
        st.session_state.page = 'recommendation'
        st.rerun()

    st.markdown("<div style='height:6px'></div>", unsafe_allow_html=True)

    if st.button("🤖  MILI Chatbot", use_container_width=True,
                 type="primary" if is_chat else "secondary", key="nav_chat"):
        st.session_state.page = 'chatbot'
        st.rerun()

    st.markdown("---")
    st.markdown(
        f"<p style='text-align:center;font-size:11px;color:#555;'>📽️ {len(movies):,} movies in library</p>"
        "<p style='text-align:center;font-size:11px;color:#555;'>Powered by TMDB API 🎬</p>",
        unsafe_allow_html=True,
    )

# ═════════════════════════════════════════════
#  PAGE: RECOMMENDATION
# ═════════════════════════════════════════════
if st.session_state.page == 'recommendation':
    st.markdown("## 🎥 Movie Recommendations")
    st.markdown("---")

    # ── Live Search Input ─────────────────────
    st.markdown("#### 🔍 Search Movie")
    search_query = st.text_input(
        "Search:",
        placeholder="Start typing a movie name…  e.g.  Inception,  Avatar,  James Bond",
        label_visibility="collapsed",
        key="movie_search",
    )

    # ── Filtered results list ─────────────────
    if not search_query:
        st.markdown(
            "<p class='search-hint'>👆 Type a movie name above to search from <b>{:,}</b> movies</p>".format(len(movies)),
            unsafe_allow_html=True,
        )
        selected_movie = None

    else:
        filtered = [m for m in movies['title'].values if search_query.lower() in m.lower()]

        if not filtered:
            st.warning(f"No movies found matching **'{search_query}'** — try a different name.")
            selected_movie = None
        else:
            st.caption(f"🎬 **{len(filtered)}** result{'s' if len(filtered) != 1 else ''} for *'{search_query}'*")
            selected_movie = st.selectbox(
                "Pick a movie:",
                options=filtered,
                label_visibility="collapsed",
                key="movie_select",
            )

    # ── Recommend button ──────────────────────
    st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
    btn_disabled = selected_movie is None
    if st.button("🔍  Get Recommendations", use_container_width=True,
                 type="primary", disabled=btn_disabled):
        st.session_state.selected_movie = selected_movie

    # ── Show recommendations ──────────────────
    if st.session_state.selected_movie:
        chosen = st.session_state.selected_movie
        recommendations = get_recommendations(chosen)

        if recommendations.empty:
            st.warning("No recommendations found. Try a different movie.")
        else:
            st.markdown("---")
            st.markdown(f"### 🍿 Because you liked  **{chosen}**")

            # Show the selected movie's own genre too
            sel_row = movies[movies['title'] == chosen]
            if not sel_row.empty:
                sel_id = int(sel_row.iloc[0]['movie_id'])
                sel_genre = get_local_genre(sel_id)
                st.markdown(
                    f"<p style='color:#f0a500;font-size:14px;margin-top:-8px;'>🎭 {sel_genre}</p>",
                    unsafe_allow_html=True,
                )

            st.markdown("<div style='height:6px'></div>", unsafe_allow_html=True)

            with st.spinner("Fetching posters…"):
                details = []
                for _, row in recommendations.iterrows():
                    mid   = int(row['movie_id'])
                    poster = fetch_poster(mid)
                    genre  = get_local_genre(mid)   # ← from local CSV, instant & reliable
                    details.append({'title': row['title'], 'poster': poster, 'genre': genre})

            # 2 rows × 5 columns
            for row_start in [0, 5]:
                cols = st.columns(5, gap="small")
                for col, idx in zip(cols, range(row_start, row_start + 5)):
                    if idx < len(details):
                        d = details[idx]
                        with col:
                            st.image(d['poster'], use_column_width=True)
                            st.markdown(
                                f"<div class='movie-card'>"
                                f"<p class='movie-title'>{d['title']}</p>"
                                f"<p class='movie-genre'>🎭 {d['genre']}</p>"
                                f"</div>",
                                unsafe_allow_html=True,
                            )
                if row_start == 0:
                    st.markdown("<div style='height:20px'></div>", unsafe_allow_html=True)

# ═════════════════════════════════════════════
#  PAGE: MILI CHATBOT
# ═════════════════════════════════════════════
elif st.session_state.page == 'chatbot':
    st.markdown("## 🤖 MILI — Movie Intelligence")
    st.markdown("Your AI movie companion. Ask anything — genres, recommendations, or just chat!")
    st.markdown("---")

    # Clear button
    _, col_clear = st.columns([5, 1])
    with col_clear:
        if st.button("🗑️ Clear", use_container_width=True):
            st.session_state.chat_history = []
            st.rerun()

    # Chat display
    chat_box = st.container(height=430)
    with chat_box:
        if not st.session_state.chat_history:
            st.markdown(
                "<div class='bot-bubble'><div class='chat-label'>🤖 MILI</div>"
                "👋 Hey! I'm <b>MILI</b>, your MovieMind assistant!<br>"
                "Ask me to recommend movies, suggest a genre, or just chat! 🎬🍿"
                "</div>",
                unsafe_allow_html=True,
            )

        for msg in st.session_state.chat_history:
            if msg['role'] == 'user':
                st.markdown(
                    f"<div style='display:flex;justify-content:flex-end;'>"
                    f"<div class='user-bubble'><div class='chat-label-right'>You 👤</div>"
                    f"{msg['content']}</div></div>",
                    unsafe_allow_html=True,
                )
            else:
                content_html = msg['content'].replace("\n", "<br>")
                st.markdown(
                    f"<div class='bot-bubble'><div class='chat-label'>🤖 MILI</div>"
                    f"{content_html}</div>",
                    unsafe_allow_html=True,
                )

    # Chat input at root level (preserves history correctly)
    user_input = st.chat_input("Ask MILI about movies…")
    if user_input:
        st.session_state.chat_history.append({'role': 'user', 'content': user_input})
        reply = mili_response(user_input)
        st.session_state.chat_history.append({'role': 'assistant', 'content': reply})
        st.rerun()

    # Quick chips
    st.markdown("**💡 Quick questions:**")
    chips = [
        ("🎭", "Suggest an action movie"),
        ("🍿", "Movies like Inception"),
        ("⭐", "Best movies tonight"),
        ("👻", "Scary horror films"),
    ]
    chip_cols = st.columns(len(chips))
    for c, (icon, text) in zip(chip_cols, chips):
        with c:
            if st.button(f"{icon} {text}", use_container_width=True, key=f"chip_{text}"):
                st.session_state.chat_history.append({'role': 'user', 'content': text})
                st.session_state.chat_history.append({'role': 'assistant', 'content': mili_response(text)})
                st.rerun()
