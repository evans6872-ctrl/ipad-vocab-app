[App.py](https://github.com/user-attachments/files/31471709/App.py)
# ipad-vocab-app
English for yuyu
import streamlit as st
import sqlite3
from datetime import datetime, timedelta
import pandas as pd

# 遺忘曲線間隔設定 (天數)
INTERVALS = [1, 2, 4, 7, 15, 30, 60]

# --- 1. 資料庫初始化與操作 ---
def init_db():
    conn = sqlite3.connect('vocab.db')
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS vocab (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            word TEXT UNIQUE,
            meaning TEXT,
            level INTEGER,
            next_review_date DATE,
            mistake_count INTEGER
        )
    ''')
    conn.commit()
    return conn

def add_word(conn, word, meaning):
    c = conn.cursor()
    today = datetime.now().date()
    try:
        c.execute('''
            INSERT INTO vocab (word, meaning, level, next_review_date, mistake_count)
            VALUES (?, ?, 0, ?, 0)
        ''', (word, meaning, today))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False # 單字已存在

def get_due_words(conn):
    c = conn.cursor()
    today = datetime.now().date()
    c.execute('SELECT id, word, meaning, level, mistake_count FROM vocab WHERE next_review_date <= ?', (today,))
    return c.fetchall()

def update_word(conn, word_id, level, remembered, mistake_count):
    c = conn.cursor()
    if remembered:
        new_level = min(level + 1, len(INTERVALS) - 1)
    else:
        new_level = 0 # 忘記了，打回原形
        mistake_count += 1
    
    next_review = datetime.now().date() + timedelta(days=INTERVALS[new_level])
    
    c.execute('''
        UPDATE vocab SET level = ?, next_review_date = ?, mistake_count = ? WHERE id = ?
    ''', (new_level, next_review, mistake_count, word_id))
    conn.commit()

# --- 2. Streamlit UI 介面 ---
st.set_page_config(page_title="遺忘曲線單字 App", page_icon="🧠", layout="centered")

conn = init_db()

st.title("🧠 遺忘曲線單字記憶系統")

# 使用標籤頁切換功能
tab1, tab2, tab3 = st.tabs(["📝 新增單字", "🎯 今日測驗", "📊 弱點分析"])

# --- 標籤頁 1: 新增單字 ---
with tab1:
    st.header("輸入新單字")
    with st.form("add_word_form"):
        new_word = st.text_input("英文單字")
        new_meaning = st.text_input("中文意思")
        submitted = st.form_submit_button("加入計畫")
        
        if submitted:
            if new_word and new_meaning:
                success = add_word(conn, new_word.strip().lower(), new_meaning.strip())
                if success:
                    st.success(f"已成功加入單字：{new_word}")
                else:
                    st.error("這個單字已經在字庫中囉！")
            else:
                st.warning("請填寫單字與意思。")

# --- 標籤頁 2: 今日測驗 ---
with tab2:
    st.header("今日需複習單字")
    due_words = get_due_words(conn)
    
    if not due_words:
        st.info("太棒了！今天的單字都複習完畢囉！🎉")
    else:
        st.write(f"還有 **{len(due_words)}** 個單字待複習")
        
        # 顯示第一個待複習的單字
        current_word = due_words[0]
        word_id, word, meaning, level, mistakes = current_word
        
        st.markdown(f"<h2 style='text-align: center; color: #1E90FF;'>{word}</h2>", unsafe_allow_html=True)
        
        show_answer = st.checkbox("顯示答案")
        if show_answer:
            st.success(f"**中文意思:** {meaning}")
            
            col1, col2 = st.columns(2)
            with col1:
                if st.button("❌ 忘記了 (重置記憶)"):
                    update_word(conn, word_id, level, False, mistakes)
                    st.rerun()
            with col2:
                if st.button("✅ 記得了 (推遲複習)"):
                    update_word(conn, word_id, level, True, mistakes)
                    st.rerun()

# --- 標籤頁 3: 弱點分析 ---
with tab3:
    st.header("你的單字庫與弱點")
    df = pd.read_sql_query("SELECT word AS 單字, meaning AS 意思, next_review_date AS 下次複習日, mistake_count AS 忘記次數 FROM vocab ORDER BY mistake_count DESC", conn)
    
    if not df.empty:
        st.dataframe(df, use_container_width=True)
        st.caption("「忘記次數」越高的單字，代表是你最常忘記的弱點喔！")
    else:
        st.write("目前字庫還是空的。")
